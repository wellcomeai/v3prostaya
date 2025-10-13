"""
Candle Aggregator Service

Агрегирует WebSocket ticker данные в OHLCV свечи и сохраняет в БД.

Поддерживает:
- Множественные символы одновременно
- Множественные интервалы (1m, 5m, 15m, 1h, 1d)
- Автоматическое сохранение при закрытии свечи
- Thread-safe операции
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from decimal import Decimal
from collections import defaultdict
import traceback

from database.models.market_data import MarketDataCandle, CandleInterval
from database.repositories import get_market_data_repository

logger = logging.getLogger(__name__)


@dataclass
class CandleBuilder:
    """Строитель свечи - собирает данные тиков в OHLCV"""
    
    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    
    # OHLCV данные
    open_price: Optional[Decimal] = None
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    volume: Decimal = field(default_factory=lambda: Decimal('0'))
    
    # Метаданные
    tick_count: int = 0
    first_tick_time: Optional[datetime] = None
    last_tick_time: Optional[datetime] = None
    
    def update_with_tick(self, price: float, volume: float, timestamp: datetime):
        """
        Обновляет свечу новым тиком
        
        Args:
            price: Цена тика
            volume: Объем тика
            timestamp: Время тика
        """
        price_decimal = Decimal(str(price))
        volume_decimal = Decimal(str(volume))
        
        # Первый тик - устанавливаем open
        if self.open_price is None:
            self.open_price = price_decimal
            self.high_price = price_decimal
            self.low_price = price_decimal
            self.first_tick_time = timestamp
        
        # Обновляем high/low
        if self.high_price is None or price_decimal > self.high_price:
            self.high_price = price_decimal
        
        if self.low_price is None or price_decimal < self.low_price:
            self.low_price = price_decimal
        
        # Close всегда последняя цена
        self.close_price = price_decimal
        
        # Накапливаем объем
        self.volume += volume_decimal
        
        # Обновляем метаданные
        self.tick_count += 1
        self.last_tick_time = timestamp
    
    def is_complete(self) -> bool:
        """Проверяет, готова ли свеча к сохранению"""
        return all([
            self.open_price is not None,
            self.high_price is not None,
            self.low_price is not None,
            self.close_price is not None,
            self.tick_count > 0
        ])
    
    def to_market_data_candle(self) -> Optional[MarketDataCandle]:
        """
        Преобразует строитель в MarketDataCandle для сохранения в БД
        
        Returns:
            MarketDataCandle или None если свеча не готова
        """
        if not self.is_complete():
            logger.warning(f"⚠️ Свеча {self.symbol} {self.interval} не готова к сохранению (ticks={self.tick_count})")
            return None
        
        try:
            candle = MarketDataCandle(
                symbol=self.symbol.upper(),
                interval=self.interval,
                open_time=self.open_time,
                close_time=self.close_time,
                open_price=self.open_price,
                high_price=self.high_price,
                low_price=self.low_price,
                close_price=self.close_price,
                volume=self.volume,
                quote_volume=None,  # Не доступно из WebSocket тиков
                number_of_trades=self.tick_count,
                data_source="bybit_websocket",
                raw_data=None
            )
            
            return candle
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания свечи {self.symbol} {self.interval}: {e}")
            return None


class CandleAggregator:
    """
    🚀 Агрегатор WebSocket тиков в OHLCV свечи с автоматическим сохранением в БД
    
    Функции:
    - Обработка ticker updates от WebSocket
    - Формирование свечей для множественных интервалов
    - Автоматическое сохранение готовых свечей в БД
    - Поддержка множественных символов
    - Детальная статистика
    """
    
    def __init__(self, 
                 symbols: List[str],
                 intervals: List[str] = None,
                 batch_save: bool = False,
                 batch_size: int = 100):
        """
        Инициализация агрегатора
        
        Args:
            symbols: Список символов для агрегации
            intervals: Список интервалов (по умолчанию: 1m, 5m, 15m, 1h, 1d)
            batch_save: Сохранять свечи батчами (для производительности)
            batch_size: Размер батча
        """
        self.symbols = [s.upper() for s in symbols]
        self.intervals = intervals or ["1m", "5m", "15m", "1h", "1d"]
        self.batch_save = batch_save
        self.batch_size = batch_size
        
        # Текущие строители свечей: {symbol: {interval: CandleBuilder}}
        self.current_builders: Dict[str, Dict[str, CandleBuilder]] = defaultdict(dict)
        
        # Очередь готовых свечей для батчевого сохранения
        self.pending_candles: List[MarketDataCandle] = []
        
        # Статистика
        self.stats = {
            "ticks_received": 0,
            "ticks_by_symbol": defaultdict(int),
            "candles_created": 0,
            "candles_saved": 0,
            "candles_by_interval": defaultdict(int),
            "save_errors": 0,
            "last_tick_time": None,
            "last_save_time": None,
            "start_time": datetime.now()
        }
        
        # Repository для сохранения
        self.repository = None
        
        # Состояние
        self.is_running = False
        self.save_task = None
        
        logger.info(f"🏗️ CandleAggregator инициализирован")
        logger.info(f"   • Символы: {', '.join(self.symbols)}")
        logger.info(f"   • Интервалы: {', '.join(self.intervals)}")
        logger.info(f"   • Батчевое сохранение: {batch_save}")
    
    async def start(self):
        """Запускает агрегатор"""
        try:
            logger.info("🚀 Запуск CandleAggregator...")
            
            # Получаем repository
            from database.repositories import get_market_data_repository
            self.repository = await get_market_data_repository()
            
            if not self.repository:
                raise RuntimeError("Failed to get MarketDataRepository")
            
            # Инициализируем строители для всех символов и интервалов
            for symbol in self.symbols:
                await self._initialize_builders_for_symbol(symbol)
            
            self.is_running = True
            
            # Запускаем фоновую задачу периодического сохранения
            if self.batch_save:
                self.save_task = asyncio.create_task(self._periodic_save_task())
            
            logger.info(f"✅ CandleAggregator запущен для {len(self.symbols)} символов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска CandleAggregator: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def _initialize_builders_for_symbol(self, symbol: str):
        """Инициализирует строители свечей для символа"""
        now = datetime.now(timezone.utc)
        
        for interval in self.intervals:
            # Вычисляем границы текущей свечи
            open_time, close_time = self._calculate_candle_boundaries(now, interval)
            
            # Создаем строителя
            builder = CandleBuilder(
                symbol=symbol,
                interval=interval,
                open_time=open_time,
                close_time=close_time
            )
            
            self.current_builders[symbol][interval] = builder
            
            logger.debug(f"🏗️ Инициализирован builder для {symbol} {interval}: {open_time} - {close_time}")
    
    def _calculate_candle_boundaries(self, timestamp: datetime, interval: str) -> tuple:
        """
        Вычисляет границы свечи для заданного времени
        
        Args:
            timestamp: Текущее время
            interval: Интервал свечи
            
        Returns:
            (open_time, close_time)
        """
        interval_enum = CandleInterval(interval)
        interval_seconds = interval_enum.to_seconds()
        
        # Округляем время до начала интервала
        timestamp_seconds = int(timestamp.timestamp())
        interval_start = (timestamp_seconds // interval_seconds) * interval_seconds
        interval_end = interval_start + interval_seconds - 1
        
        open_time = datetime.fromtimestamp(interval_start, tz=timezone.utc)
        close_time = datetime.fromtimestamp(interval_end, tz=timezone.utc)
        
        return open_time, close_time
    
    async def process_ticker_update(self, symbol: str, ticker_data: dict):
        """
        Обрабатывает обновление тикера от WebSocket
        
        Args:
            symbol: Символ
            ticker_data: Данные тикера от WebSocket
        """
        try:
            # Извлекаем данные
            price = float(ticker_data.get('lastPrice', 0))
            volume = float(ticker_data.get('volume24h', 0))
            timestamp = datetime.now(timezone.utc)
            
            if price <= 0:
                logger.warning(f"⚠️ Невалидная цена для {symbol}: {price}")
                return
            
            # Обновляем статистику
            self.stats["ticks_received"] += 1
            self.stats["ticks_by_symbol"][symbol] += 1
            self.stats["last_tick_time"] = timestamp
            
            # Обновляем все интервалы
            symbol = symbol.upper()
            if symbol not in self.current_builders:
                await self._initialize_builders_for_symbol(symbol)
            
            for interval in self.intervals:
                await self._process_tick_for_interval(
                    symbol, interval, price, volume, timestamp
                )
            
            logger.debug(f"📊 Обработан тик {symbol}: ${price:,.2f}, Vol: {volume:,.0f}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки тика {symbol}: {e}")
            logger.error(traceback.format_exc())
    
    async def _process_tick_for_interval(self, 
                                        symbol: str, 
                                        interval: str,
                                        price: float,
                                        volume: float,
                                        timestamp: datetime):
        """Обрабатывает тик для конкретного интервала"""
        try:
            builder = self.current_builders[symbol].get(interval)
            
            if not builder:
                logger.warning(f"⚠️ Нет builder для {symbol} {interval}")
                return
            
            # Проверяем, не закончился ли интервал
            if timestamp > builder.close_time:
                # Свеча готова - сохраняем
                await self._finalize_and_save_candle(symbol, interval)
                
                # Создаем новый строитель
                open_time, close_time = self._calculate_candle_boundaries(timestamp, interval)
                builder = CandleBuilder(
                    symbol=symbol,
                    interval=interval,
                    open_time=open_time,
                    close_time=close_time
                )
                self.current_builders[symbol][interval] = builder
            
            # Обновляем строителя тиком
            builder.update_with_tick(price, volume, timestamp)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки тика для {symbol} {interval}: {e}")
    
    async def _finalize_and_save_candle(self, symbol: str, interval: str):
        """Завершает и сохраняет готовую свечу"""
        try:
            builder = self.current_builders[symbol].get(interval)
            
            if not builder or not builder.is_complete():
                logger.debug(f"🔍 Свеча {symbol} {interval} не готова к сохранению")
                return
            
            # Преобразуем в MarketDataCandle
            candle = builder.to_market_data_candle()
            
            if not candle:
                logger.warning(f"⚠️ Не удалось создать свечу {symbol} {interval}")
                return
            
            # Обновляем статистику
            self.stats["candles_created"] += 1
            self.stats["candles_by_interval"][interval] += 1
            
            # Сохраняем
            if self.batch_save:
                # Добавляем в очередь для батчевого сохранения
                self.pending_candles.append(candle)
                logger.debug(f"📦 Свеча {symbol} {interval} добавлена в очередь (размер={len(self.pending_candles)})")
                
                # Если достигли размера батча - сохраняем
                if len(self.pending_candles) >= self.batch_size:
                    await self._save_pending_candles()
            else:
                # Сохраняем сразу
                await self._save_single_candle(candle)
            
        except Exception as e:
            logger.error(f"❌ Ошибка финализации свечи {symbol} {interval}: {e}")
            logger.error(traceback.format_exc())
            self.stats["save_errors"] += 1
    
    async def _save_single_candle(self, candle: MarketDataCandle):
        """Сохраняет одну свечу в БД"""
        try:
            if not self.repository:
                logger.error("❌ Repository не инициализирован")
                return
            
            success = await self.repository.insert_candle(candle)
            
            if success:
                self.stats["candles_saved"] += 1
                self.stats["last_save_time"] = datetime.now()
                logger.info(f"✅ Свеча сохранена: {candle.symbol} {candle.interval} @ ${candle.close_price} (O:{candle.open_time})")
            else:
                logger.error(f"❌ Не удалось сохранить свечу {candle.symbol} {candle.interval}")
                self.stats["save_errors"] += 1
                
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения свечи: {e}")
            self.stats["save_errors"] += 1
    
    async def _save_pending_candles(self):
        """Сохраняет накопленные свечи батчем"""
        try:
            if not self.pending_candles:
                return
            
            if not self.repository:
                logger.error("❌ Repository не инициализирован")
                return
            
            logger.info(f"💾 Сохранение батча из {len(self.pending_candles)} свечей...")
            
            inserted, updated = await self.repository.bulk_insert_candles(
                self.pending_candles
            )
            
            self.stats["candles_saved"] += inserted + updated
            self.stats["last_save_time"] = datetime.now()
            
            logger.info(f"✅ Батч сохранен: {inserted} новых, {updated} обновлено")
            
            # Очищаем очередь
            self.pending_candles.clear()
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения батча: {e}")
            logger.error(traceback.format_exc())
            self.stats["save_errors"] += 1
    
    async def _periodic_save_task(self):
        """Фоновая задача для периодического сохранения батчей"""
        logger.info("🔄 Запущена задача периодического сохранения")
        
        while self.is_running:
            try:
                # Сохраняем каждые 30 секунд
                await asyncio.sleep(30)
                
                if self.pending_candles:
                    logger.info(f"⏰ Периодическое сохранение: {len(self.pending_candles)} свечей")
                    await self._save_pending_candles()
                
            except asyncio.CancelledError:
                logger.info("🔄 Задача периодического сохранения отменена")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в задаче периодического сохранения: {e}")
                await asyncio.sleep(5)
    
    async def stop(self):
        """Останавливает агрегатор"""
        try:
            logger.info("🛑 Остановка CandleAggregator...")
            self.is_running = False
            
            # Останавливаем фоновую задачу
            if self.save_task and not self.save_task.done():
                self.save_task.cancel()
                try:
                    await self.save_task
                except asyncio.CancelledError:
                    pass
            
            # Сохраняем все незавершенные свечи
            logger.info("💾 Сохранение незавершенных свечей...")
            
            for symbol in self.symbols:
                for interval in self.intervals:
                    builder = self.current_builders[symbol].get(interval)
                    if builder and builder.is_complete():
                        await self._finalize_and_save_candle(symbol, interval)
            
            # Сохраняем оставшийся батч
            if self.pending_candles:
                await self._save_pending_candles()
            
            # Логируем финальную статистику
            uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
            logger.info(f"📊 Финальная статистика CandleAggregator:")
            logger.info(f"   • Время работы: {uptime:.0f}с")
            logger.info(f"   • Тиков обработано: {self.stats['ticks_received']}")
            logger.info(f"   • Свечей создано: {self.stats['candles_created']}")
            logger.info(f"   • Свечей сохранено: {self.stats['candles_saved']}")
            logger.info(f"   • Ошибок сохранения: {self.stats['save_errors']}")
            
            for interval, count in self.stats["candles_by_interval"].items():
                logger.info(f"   • {interval}: {count} свечей")
            
            logger.info("✅ CandleAggregator остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки CandleAggregator: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику агрегатора"""
        uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
        
        return {
            **self.stats,
            "uptime_seconds": uptime,
            "ticks_per_second": self.stats["ticks_received"] / uptime if uptime > 0 else 0,
            "symbols": self.symbols,
            "intervals": self.intervals,
            "active_builders": sum(len(builders) for builders in self.current_builders.values()),
            "pending_candles_count": len(self.pending_candles),
            "is_running": self.is_running
        }


# Export
__all__ = ["CandleAggregator", "CandleBuilder"]
