"""
Candle Synchronization Service

Сервис для автоматической синхронизации свечей:
- Проверка пропусков при старте
- Фоновое обновление в реальном времени
- Догрузка недостающих данных
"""

import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SyncConfig:
    """Конфигурация синхронизации"""
    # Интервалы для обновления
    intervals_to_sync: List[str] = None
    
    # Настройки догрузки
    max_gap_days: int = 30          # Макс пропуск для авто-догрузки
    check_gaps_on_start: bool = True
    
    def __post_init__(self):
        if self.intervals_to_sync is None:
            # ✅ ВСЕ доступные интервалы по умолчанию
            self.intervals_to_sync = ["1m", "5m", "15m", "1h", "4h", "1d"]
    
    def get_sync_interval_seconds(self, interval: str) -> int:
        """
        Получить интервал обновления в секундах для каждого таймфрейма
        
        Args:
            interval: Таймфрейм (1m, 5m, 15m, 1h, 4h, 1d)
            
        Returns:
            Секунды между обновлениями
        """
        sync_intervals = {
            "1m": 60,       # Каждую минуту
            "5m": 300,      # Каждые 5 минут  
            "15m": 900,     # Каждые 15 минут
            "1h": 3660,     # Каждый час + 1 мин
            "4h": 14460,    # Каждые 4 часа + 1 мин
            "1d": 86460     # Каждый день + 1 мин
        }
        return sync_intervals.get(interval, 3600)  # По умолчанию 1 час


class CandleSyncService:
    """
    Сервис синхронизации свечей
    
    Функции:
    1. Проверка пропусков при старте → догрузка
    2. Фоновое обновление 1m/5m/15m/1h/4h/1d в реальном времени
    3. Мониторинг состояния синхронизации
    """
    
    def __init__(self, 
                 repository,  # MarketDataRepository
                 rest_api_provider,  # RestApiProvider
                 historical_loader=None,  # HistoricalDataLoader (optional)
                 config: SyncConfig = None):
        """
        Инициализация сервиса
        
        Args:
            repository: Репозиторий для работы с БД
            rest_api_provider: REST API для получения свечей
            historical_loader: Загрузчик истории (для больших пропусков)
            config: Конфигурация синхронизации
        """
        self.repository = repository
        self.rest_api = rest_api_provider
        self.historical_loader = historical_loader
        self.config = config or SyncConfig()
        
        # Состояние
        self.is_running = False
        self.sync_tasks: List[asyncio.Task] = []
        
        # Статистика
        self.stats = {
            "gaps_found": 0,
            "gaps_filled": 0,
            "candles_synced": 0,
            "sync_errors": 0,
            "start_time": None
            # last_sync_{interval} будут добавляться динамически
        }
        
        logger.info("🔄 CandleSyncService инициализирован")
    
    async def start(self, symbol: str = "BTCUSDT") -> bool:
        """
        Запуск сервиса синхронизации
        
        Что делает:
        1. Проверяет пропуски при старте
        2. Догружает если нужно
        3. Запускает фоновые задачи обновления
        """
        try:
            logger.info(f"🚀 Запуск синхронизации для {symbol}")
            self.stats["start_time"] = datetime.now()
            
            # Шаг 1: Проверка и заполнение пропусков
            if self.config.check_gaps_on_start:
                await self._check_and_fill_gaps(symbol)
            
            # Шаг 2: Запуск фоновых задач
            self.is_running = True
            await self._start_sync_tasks(symbol)
            
            logger.info("✅ Синхронизация запущена успешно")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска синхронизации: {e}")
            return False
    
    async def _check_and_fill_gaps(self, symbol: str):
        """
        Проверка и заполнение пропусков в данных
        
        Зачем: При старте бота догрузить недостающие дни
        """
        try:
            logger.info("🔍 Проверка пропусков в данных...")
            
            now = datetime.now(timezone.utc)
            gaps_to_fill = []
            
            # Проверяем каждый интервал
            for interval in self.config.intervals_to_sync:
                gap_info = await self.repository.check_data_gaps(
                    symbol=symbol,
                    interval=interval,
                    expected_end=now
                )
                
                if gap_info and gap_info.get("has_gap"):
                    gaps_to_fill.append((interval, gap_info))
                    self.stats["gaps_found"] += 1
                    
                    missing = gap_info.get("missing_candles", "unknown")
                    logger.warning(f"⚠️ Пропуск найден: {interval} - {missing} свечей")
            
            # Заполняем пропуски
            if gaps_to_fill:
                await self._fill_gaps(symbol, gaps_to_fill)
            else:
                logger.info("✅ Пропусков не найдено, данные актуальны")
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки пропусков: {e}")
    
    async def _fill_gaps(self, symbol: str, gaps: List[tuple]):
        """
        Заполнение найденных пропусков
        
        Зачем: Догрузить недостающие данные через REST API
        """
        try:
            logger.info(f"📥 Заполнение {len(gaps)} пропусков...")
            
            for interval, gap_info in gaps:
                gap_start = gap_info.get("gap_start")
                gap_end = gap_info.get("gap_end")
                missing_candles = gap_info.get("missing_candles")
                
                # Всегда используем REST API (он умеет делать несколько запросов)
                logger.info(f"🌐 Загрузка {missing_candles} свечей через REST API")
                await self._fill_gap_with_rest(symbol, interval, gap_start, gap_end)
                
                self.stats["gaps_filled"] += 1
                
        except Exception as e:
            logger.error(f"❌ Ошибка заполнения пропусков: {e}")
            self.stats["sync_errors"] += 1
    
    async def _fill_gap_with_rest(self, symbol: str, interval: str, 
                                  start: datetime, end: datetime):
        """Заполнение небольшого пропуска через REST API"""
        try:
            # Конвертируем interval в формат Bybit
            interval_map = {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "1h": "60",
                "4h": "240",
                "1d": "D"
            }
            
            bybit_interval = interval_map.get(interval, "60")
            
            logger.info(f"📥 Заполнение пропуска {symbol} {interval}: {start} → {end}")
            
            # Импортируем модели
            from database.models.market_data import CandleInterval, MarketDataCandle
            
            # Вычисляем сколько запросов нужно (max 200 свечей за запрос)
            interval_enum = CandleInterval(interval)
            interval_seconds = interval_enum.to_seconds()
            
            total_seconds = (end - start).total_seconds()
            total_candles = int(total_seconds / interval_seconds)
            
            candles_per_request = 200
            num_requests = (total_candles // candles_per_request) + 1
            
            logger.info(f"📊 Загружаю ~{total_candles} свечей за {num_requests} запросов")
            
            all_candles = []
            current_end = end
            
            # Загружаем свечи партиями от новых к старым
            for i in range(num_requests):
                # Получаем порцию свечей
                kline_response = await self.rest_api.get_kline_data(
                    symbol=symbol,
                    interval=bybit_interval,
                    limit=candles_per_request
                )
                
                if not kline_response.get('result', {}).get('list'):
                    logger.warning(f"⚠️ Нет данных в ответе на запрос #{i+1}")
                    break
                
                # Парсим свечи
                raw_candles = kline_response['result']['list']
                for raw_candle in raw_candles:
                    try:
                        candle = MarketDataCandle.create_from_bybit_data(
                            symbol=symbol,
                            interval=interval,
                            bybit_candle=raw_candle
                        )
                        
                        # Добавляем только если в нужном диапазоне
                        if start <= candle.open_time <= end:
                            all_candles.append(candle)
                            
                    except Exception as e:
                        logger.error(f"❌ Ошибка парсинга свечи: {e}")
                        continue
                
                # Если получили самые старые данные
                oldest_candle_time = datetime.fromtimestamp(int(raw_candles[-1][0]) / 1000, tz=timezone.utc)
                if oldest_candle_time <= start:
                    logger.info(f"✅ Достигнута начальная дата {start}")
                    break
                
                # Небольшая задержка между запросами
                await asyncio.sleep(0.2)
                
                logger.info(f"📊 Запрос {i+1}/{num_requests}: получено {len(raw_candles)} свечей")
            
            # Сохраняем в БД батчем
            if all_candles:
                inserted, updated = await self.repository.bulk_insert_candles(all_candles)
                self.stats["candles_synced"] += inserted + updated
                logger.info(f"✅ Загружено {len(all_candles)} свечей ({inserted} новых, {updated} обновлено)")
            else:
                logger.warning(f"⚠️ Не получено ни одной свечи для заполнения пропуска")
                
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки через REST: {e}")
            logger.error(traceback.format_exc())
            self.stats["sync_errors"] += 1
    
    async def _fill_gap_with_loader(self, symbol: str, interval: str,
                                   start: datetime, end: datetime):
        """Заполнение большого пропуска через HistoricalDataLoader"""
        try:
            if not self.historical_loader:
                logger.warning("⚠️ HistoricalDataLoader недоступен, пропускаю")
                return
            
            logger.info(f"📦 Загрузка через HistoricalDataLoader: {start} → {end}")
            
            # Используем существующий loader
            result = await self.historical_loader.load_historical_data(
                intervals=[interval],
                start_time=start,
                end_time=end
            )
            
            if result.get("success"):
                candles_loaded = result.get("total_candles_loaded", 0)
                self.stats["candles_synced"] += candles_loaded
                logger.info(f"✅ Загружено {candles_loaded} свечей через Loader")
            else:
                logger.error("❌ Ошибка загрузки через Loader")
                self.stats["sync_errors"] += 1
                
        except Exception as e:
            logger.error(f"❌ Ошибка использования Loader: {e}")
            self.stats["sync_errors"] += 1
    
    async def _start_sync_tasks(self, symbol: str):
        """
        Запуск фоновых задач синхронизации
        
        ✅ Динамически создаёт задачи для ВСЕХ интервалов из конфига
        """
        try:
            logger.info(f"🔄 Запуск синхронизации для интервалов: {self.config.intervals_to_sync}")
            
            # Создаём задачу для КАЖДОГО интервала
            for interval in self.config.intervals_to_sync:
                # Получаем интервал обновления в секундах
                sync_interval_seconds = self.config.get_sync_interval_seconds(interval)
                
                # Создаём и запускаем задачу
                task = asyncio.create_task(
                    self._sync_loop(symbol, interval, sync_interval_seconds)
                )
                self.sync_tasks.append(task)
                
                logger.info(f"✅ Запущена синхронизация {interval} (каждые {sync_interval_seconds}с)")
            
            logger.info(f"🎯 Всего запущено {len(self.sync_tasks)} задач синхронизации")
                
        except Exception as e:
            logger.error(f"❌ Ошибка запуска задач: {e}")
    
    async def _sync_loop(self, symbol: str, interval: str, sleep_seconds: int):
        """
        Бесконечный цикл синхронизации для конкретного интервала
        
        Зачем: Каждые N секунд обновлять свечи через REST API
        """
        logger.info(f"🔁 Запущен цикл синхронизации {interval} (каждые {sleep_seconds}с)")
        
        while self.is_running:
            try:
                # Получаем последнюю свечу через REST
                await self._sync_latest_candle(symbol, interval)
                
                # Обновляем статистику динамически
                self.stats[f"last_sync_{interval}"] = datetime.now()
                
                # Ждем до следующего обновления
                await asyncio.sleep(sleep_seconds)
                
            except asyncio.CancelledError:
                logger.info(f"🛑 Цикл синхронизации {interval} остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле синхронизации {interval}: {e}")
                self.stats["sync_errors"] += 1
                await asyncio.sleep(60)  # При ошибке ждем минуту
    
    async def _sync_latest_candle(self, symbol: str, interval: str):
        """Синхронизация последней свечи"""
        try:
            # Конвертируем interval
            interval_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"}
            bybit_interval = interval_map.get(interval, "60")
            
            # Получаем последнюю свечу
            kline_response = await self.rest_api.get_kline_data(
                symbol=symbol,
                interval=bybit_interval,
                limit=1
            )
            
            if not kline_response.get('result', {}).get('list'):
                return
            
            # Парсим и сохраняем
            from database.models.market_data import MarketDataCandle
            raw_candle = kline_response['result']['list'][0]
            candle = MarketDataCandle.create_from_bybit_data(
                symbol=symbol,
                interval=interval,
                bybit_candle=raw_candle
            )
            
            success = await self.repository.insert_candle(candle)
            if success:
                self.stats["candles_synced"] += 1
                logger.debug(f"✅ Обновлена свеча {interval}: ${candle.close_price}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка синхронизации свечи {interval}: {e}")
            self.stats["sync_errors"] += 1
    
    async def stop(self):
        """Остановка сервиса"""
        logger.info("🛑 Остановка сервиса синхронизации...")
        self.is_running = False
        
        # Останавливаем задачи
        for task in self.sync_tasks:
            if not task.done():
                task.cancel()
        
        if self.sync_tasks:
            await asyncio.gather(*self.sync_tasks, return_exceptions=True)
        
        logger.info("✅ Сервис синхронизации остановлен")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику синхронизации"""
        uptime = None
        if self.stats["start_time"]:
            uptime = datetime.now() - self.stats["start_time"]
        
        return {
            **self.stats,
            "is_running": self.is_running,
            "active_tasks": len([t for t in self.sync_tasks if not t.done()]),
            "uptime": str(uptime).split('.')[0] if uptime else None
        }


# Export
__all__ = ["CandleSyncService", "SyncConfig"]
