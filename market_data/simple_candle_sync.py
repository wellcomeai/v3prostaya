"""
Simple Candle Sync Service

Простой и надежный синхронизатор свечей через REST API Bybit.
Замена сложного CandleAggregator - БЕЗ WebSocket тиков, БЕЗ deadlock.

Особенности:
- Получает готовые OHLCV от Bybit (не строим сами)
- Работает со списком символов
- Автоматическая проверка и заполнение пропусков
- Надежное восстановление при сбоях
- Минимум кода, максимум надежности
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import traceback

logger = logging.getLogger(__name__)


@dataclass
class SyncSchedule:
    """Расписание синхронизации для интервала"""
    interval: str           # Наш формат (1m, 5m, 15m, 1h, 4h, 1d)
    update_seconds: int     # Как часто обновлять
    bybit_interval: str     # Формат Bybit API
    
    @classmethod
    def get_default_schedule(cls) -> List['SyncSchedule']:
        """Дефолтное расписание для всех интервалов"""
        return [
            cls("1m", 60, "1"),          # Каждую минуту
            cls("5m", 300, "5"),         # Каждые 5 минут
            cls("15m", 900, "15"),       # Каждые 15 минут
            cls("1h", 3600, "60"),       # Каждый час
            cls("4h", 14400, "240"),     # Каждые 4 часа
            cls("1d", 86400, "D"),       # Раз в день
        ]


class SimpleCandleSync:
    """
    🚀 Простой синхронизатор свечей через REST API Bybit
    
    Преимущества:
    - Надежные OHLCV данные от Bybit (не строим сами)
    - Нет deadlock (простые insert)
    - Автоматическое восстановление пропусков
    - Легкая отладка
    - Минимум кода
    """
    
    def __init__(self, 
                 symbols: List[str],
                 bybit_client,           # BybitClient instance
                 repository,             # MarketDataRepository instance
                 schedule: List[SyncSchedule] = None,
                 check_gaps_on_start: bool = True):
        """
        Args:
            symbols: Список символов ["BTCUSDT", "ETHUSDT", ...]
            bybit_client: BybitClient для REST запросов
            repository: MarketDataRepository для сохранения
            schedule: Расписание синхронизации (default: все интервалы)
            check_gaps_on_start: Проверять пропуски при старте
        """
        self.symbols = [s.upper() for s in symbols]
        self.bybit_client = bybit_client
        self.repository = repository
        self.schedule = schedule or SyncSchedule.get_default_schedule()
        self.check_gaps_on_start = check_gaps_on_start
        
        # Задачи синхронизации
        self.sync_tasks: List[asyncio.Task] = []
        self.is_running = False
        
        # Статистика
        self.stats = {
            "start_time": None,
            "candles_synced": 0,
            "api_calls": 0,
            "errors": 0,
            "last_sync_by_interval": {},  # {interval: datetime}
            "gaps_found": 0,
            "gaps_filled": 0
        }
        
        logger.info("🔧 SimpleCandleSync инициализирован")
        logger.info(f"   • Символы: {', '.join(self.symbols)}")
        logger.info(f"   • Интервалы: {', '.join([s.interval for s in self.schedule])}")
        logger.info(f"   • Проверка пропусков: {'✅' if check_gaps_on_start else '❌'}")
    
    async def start(self):
        """Запуск синхронизации для всех символов и интервалов"""
        try:
            logger.info("🚀 Запуск SimpleCandleSync...")
            self.is_running = True
            self.stats["start_time"] = datetime.now()
            
            # Шаг 1: Проверка и заполнение пропусков (если включено)
            if self.check_gaps_on_start:
                await self._check_and_fill_all_gaps()
            
            # Шаг 2: Создаем задачу для каждого интервала
            for schedule_item in self.schedule:
                task = asyncio.create_task(
                    self._sync_interval_loop(schedule_item)
                )
                self.sync_tasks.append(task)
                
                logger.info(f"✅ Запущен цикл {schedule_item.interval} "
                          f"(каждые {schedule_item.update_seconds}с)")
            
            logger.info(f"🎯 Всего запущено {len(self.sync_tasks)} задач синхронизации")
            logger.info(f"📊 Символы: {len(self.symbols)}, Интервалы: {len(self.schedule)}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска SimpleCandleSync: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def _check_and_fill_all_gaps(self):
        """Проверка и заполнение пропусков для ВСЕХ символов и интервалов"""
        try:
            logger.info("🔍 Проверка пропусков для всех символов и интервалов...")
            
            now = datetime.now(timezone.utc)
            gaps_to_fill = []
            
            # Проверяем КАЖДЫЙ символ и КАЖДЫЙ интервал
            for symbol in self.symbols:
                for schedule_item in self.schedule:
                    interval = schedule_item.interval
                    
                    try:
                        # Проверяем пропуски
                        gap_info = await self.repository.check_data_gaps(
                            symbol=symbol,
                            interval=interval,
                            expected_end=now
                        )
                        
                        if gap_info and gap_info.get("has_gap"):
                            missing = gap_info.get("missing_candles", "unknown")
                            gap_start = gap_info.get("gap_start")
                            gap_end = gap_info.get("gap_end")
                            
                            logger.warning(f"⚠️ Пропуск [{symbol}] {interval}: {missing} свечей")
                            
                            # Добавляем в список для заполнения
                            if isinstance(missing, int) and missing < 5000:  # Защита
                                gaps_to_fill.append({
                                    "symbol": symbol,
                                    "interval": interval,
                                    "bybit_interval": schedule_item.bybit_interval,
                                    "gap_start": gap_start,
                                    "gap_end": gap_end,
                                    "missing_candles": missing
                                })
                                self.stats["gaps_found"] += 1
                            else:
                                logger.warning(f"⚠️ Пропуск слишком большой ({missing}), пропускаем")
                        
                    except Exception as e:
                        logger.error(f"❌ Ошибка проверки [{symbol}] {interval}: {e}")
                        continue
            
            # Заполняем все найденные пропуски
            if gaps_to_fill:
                logger.info(f"📥 Найдено {len(gaps_to_fill)} пропусков, начинаю заполнение...")
                
                for gap in gaps_to_fill:
                    try:
                        await self._fill_gap(gap)
                        self.stats["gaps_filled"] += 1
                        await asyncio.sleep(0.2)  # Rate limit защита
                    except Exception as e:
                        logger.error(f"❌ Ошибка заполнения пропуска: {e}")
                        self.stats["errors"] += 1
                
                logger.info(f"✅ Заполнено {self.stats['gaps_filled']}/{len(gaps_to_fill)} пропусков")
            else:
                logger.info(f"✅ Пропусков не найдено, все данные актуальны")
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки пропусков: {e}")
            logger.error(traceback.format_exc())
    
    async def _fill_gap(self, gap: Dict[str, Any]):
        """Заполняет один пропуск через REST API"""
        try:
            symbol = gap["symbol"]
            interval = gap["interval"]
            bybit_interval = gap["bybit_interval"]
            gap_start = gap["gap_start"]
            gap_end = gap["gap_end"]
            missing_candles = gap["missing_candles"]
            
            logger.info(f"📥 Заполнение [{symbol}] {interval}: ~{missing_candles} свечей")
            
            # Вычисляем количество запросов (по 200 свечей за раз)
            candles_per_request = 200
            num_requests = (missing_candles // candles_per_request) + 1
            num_requests = min(num_requests, 50)  # Ограничение для защиты
            
            total_saved = 0
            
            # Загружаем свечи партиями
            for i in range(num_requests):
                try:
                    # Запрос к Bybit через существующий клиент
                    response = await self.bybit_client._make_request(
                        '/v5/market/kline',
                        params={
                            'category': 'linear',
                            'symbol': symbol,
                            'interval': bybit_interval,
                            'limit': candles_per_request
                        }
                    )
                    
                    self.stats["api_calls"] += 1
                    
                    # Парсим и сохраняем
                    if response.get('result', {}).get('list'):
                        raw_candles = response['result']['list']
                        saved = await self._save_candles_batch(
                            symbol, interval, raw_candles
                        )
                        total_saved += saved
                    
                    await asyncio.sleep(0.2)  # Rate limit
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка запроса {i+1}/{num_requests}: {e}")
                    self.stats["errors"] += 1
                    break
            
            logger.info(f"✅ [{symbol}] {interval}: загружено {total_saved} свечей")
            
        except Exception as e:
            logger.error(f"❌ Ошибка заполнения пропуска: {e}")
            raise
    
    async def _sync_interval_loop(self, schedule: SyncSchedule):
        """
        Бесконечный цикл синхронизации для одного интервала
        
        Args:
            schedule: Расписание для интервала
        """
        interval = schedule.interval
        logger.info(f"🔁 Цикл {interval} запущен")
        
        while self.is_running:
            try:
                # Синхронизируем ВСЕ символы для этого интервала
                synced_count = await self._sync_interval_all_symbols(schedule)
                
                # Обновляем время последней синхронизации
                self.stats["last_sync_by_interval"][interval] = datetime.now()
                
                if synced_count > 0:
                    logger.debug(f"✅ {interval}: {synced_count}/{len(self.symbols)} символов")
                
                # Ждем до следующего обновления
                await asyncio.sleep(schedule.update_seconds)
                
            except asyncio.CancelledError:
                logger.info(f"🛑 Цикл {interval} остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле {interval}: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(60)  # При ошибке ждем минуту
    
    async def _sync_interval_all_symbols(self, schedule: SyncSchedule) -> int:
        """Синхронизация всех символов для одного интервала"""
        interval = schedule.interval
        bybit_interval = schedule.bybit_interval
        
        synced_count = 0
        
        for symbol in self.symbols:
            try:
                # Получаем последние 2 свечи (последняя может быть незакрытой)
                response = await self.bybit_client._make_request(
                    '/v5/market/kline',
                    params={
                        'category': 'linear',
                        'symbol': symbol,
                        'interval': bybit_interval,
                        'limit': 2
                    }
                )
                
                self.stats["api_calls"] += 1
                
                # Парсим и сохраняем
                if response.get('result', {}).get('list'):
                    raw_candles = response['result']['list']
                    saved = await self._save_candles_batch(
                        symbol, interval, raw_candles
                    )
                    
                    if saved > 0:
                        synced_count += 1
                        self.stats["candles_synced"] += saved
                
                # Небольшая задержка между символами
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"❌ [{symbol}] {interval}: {e}")
                self.stats["errors"] += 1
                continue
        
        return synced_count
    
    async def _save_candles_batch(self, symbol: str, interval: str, 
                                  raw_candles: List) -> int:
        """
        Парсит и сохраняет батч свечей
        
        Args:
            symbol: Символ
            interval: Интервал
            raw_candles: Сырые данные от Bybit
            
        Returns:
            Количество сохраненных свечей
        """
        try:
            from database.models.market_data import MarketDataCandle
            
            saved_count = 0
            
            for raw_candle in raw_candles:
                try:
                    # Создаем MarketDataCandle из Bybit данных
                    candle = MarketDataCandle.create_from_bybit_data(
                        symbol=symbol,
                        interval=interval,
                        bybit_candle=raw_candle
                    )
                    
                    # Сохраняем (ON CONFLICT = update)
                    success = await self.repository.insert_candle(candle)
                    
                    if success:
                        saved_count += 1
                    
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга свечи [{symbol}] {interval}: {e}")
                    continue
            
            return saved_count
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения батча: {e}")
            return 0
    
    async def stop(self):
        """Остановка всех задач синхронизации"""
        try:
            logger.info("🛑 Остановка SimpleCandleSync...")
            self.is_running = False
            
            # Останавливаем все задачи
            for task in self.sync_tasks:
                if not task.done():
                    task.cancel()
            
            if self.sync_tasks:
                await asyncio.gather(*self.sync_tasks, return_exceptions=True)
            
            # Финальная статистика
            uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
            logger.info("📊 Финальная статистика SimpleCandleSync:")
            logger.info(f"   • Время работы: {uptime:.0f}с")
            logger.info(f"   • Свечей синхронизировано: {self.stats['candles_synced']}")
            logger.info(f"   • API запросов: {self.stats['api_calls']}")
            logger.info(f"   • Пропусков заполнено: {self.stats['gaps_filled']}")
            logger.info(f"   • Ошибок: {self.stats['errors']}")
            
            logger.info("✅ SimpleCandleSync остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику"""
        uptime = None
        if self.stats["start_time"]:
            uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
        
        return {
            **self.stats,
            "uptime_seconds": uptime,
            "symbols_count": len(self.symbols),
            "intervals_count": len(self.schedule),
            "active_tasks": len([t for t in self.sync_tasks if not t.done()]),
            "is_running": self.is_running,
            "candles_per_second": self.stats["candles_synced"] / uptime if uptime and uptime > 0 else 0,
            "success_rate": ((self.stats["api_calls"] - self.stats["errors"]) / self.stats["api_calls"] * 100) if self.stats["api_calls"] > 0 else 100,
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Получить статус здоровья"""
        stats = self.get_stats()
        
        return {
            "healthy": self.is_running and stats["errors"] < 100,
            "is_running": self.is_running,
            "uptime_seconds": stats["uptime_seconds"],
            "candles_synced": stats["candles_synced"],
            "success_rate": stats["success_rate"],
            "last_sync_times": self.stats["last_sync_by_interval"],
            "errors": stats["errors"]
        }


# Export
__all__ = ["SimpleCandleSync", "SyncSchedule"]
