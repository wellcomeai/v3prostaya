"""
SimpleFuturesSync - Надежная синхронизация фьючерсных свечей через YFinance REST API

Аналог SimpleCandleSync, но для CME фьючерсов (MCL, MGC, MES, MNQ).
Использует Yahoo Finance API через библиотеку yfinance.

Особенности:
- Периодическая синхронизация свечей фьючерсов
- Проверка и заполнение пропусков
- Учет ограничений YFinance на исторические данные
- Параллельная работа с SimpleCandleSync (крипта)
- Надежность и отказоустойчивость

Author: Trading Bot Team
Version: 1.0.0
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from database.models.market_data import CandleInterval, MarketDataCandle

logger = logging.getLogger(__name__)


class SyncStatus(Enum):
    """Статус синхронизации"""
    IDLE = "idle"
    RUNNING = "running"
    SYNCING = "syncing"
    CHECKING_GAPS = "checking_gaps"
    FILLING_GAP = "filling_gap"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class FuturesSyncSchedule:
    """Расписание синхронизации для одного интервала фьючерсов"""
    interval: str
    sync_period_minutes: int
    lookback_candles: int = 100
    
    def __post_init__(self):
        self.last_sync: Optional[datetime] = None
        self.next_sync: Optional[datetime] = None
        self.sync_count: int = 0
        self.error_count: int = 0
        self.last_error: Optional[str] = None


class SimpleFuturesSync:
    """
    🚀 Простой и надежный сервис синхронизации фьючерсных свечей
    
    Работает аналогично SimpleCandleSync, но для Yahoo Finance фьючерсов:
    - Периодически обновляет свечи через YFinance REST API
    - Проверяет пропуски при старте
    - Заполняет обнаруженные пропуски
    - Работает параллельно с SimpleCandleSync (крипта)
    
    YFinance ограничения на историю:
    - 1m: максимум 7 дней
    - 5m, 15m: максимум 60 дней
    - 1h: максимум 730 дней (2 года)
    - 1d, 1w: практически без ограничений
    """
    
    # Ограничения YFinance на исторические данные
    YFINANCE_LIMITS = {
        "1m": timedelta(days=7),
        "5m": timedelta(days=60),
        "15m": timedelta(days=60),
        "1h": timedelta(days=730),
        "4h": timedelta(days=730),
        "1d": timedelta(days=36500),
        "1w": timedelta(days=36500)
    }
    
    def __init__(
        self,
        symbols: List[str],
        repository,
        check_gaps_on_start: bool = True,
        max_gap_fill_attempts: int = 3
    ):
        """
        Инициализация SimpleFuturesSync
        
        Args:
            symbols: Список фьючерсных символов (MCL, MGC, MES, MNQ)
            repository: MarketDataRepository для работы с БД
            check_gaps_on_start: Проверять пропуски при запуске
            max_gap_fill_attempts: Максимум попыток заполнить пропуск
        """
        self.symbols = symbols
        self.repository = repository
        self.check_gaps_on_start = check_gaps_on_start
        self.max_gap_fill_attempts = max_gap_fill_attempts
        
        # Статус
        self.is_running = False
        self.status = SyncStatus.IDLE
        self.start_time: Optional[datetime] = None
        
        # Задачи
        self._sync_task: Optional[asyncio.Task] = None
        self._tasks: List[asyncio.Task] = []
        
        # Расписание синхронизации для разных интервалов
        self.schedule: List[FuturesSyncSchedule] = [
            FuturesSyncSchedule(interval="1m", sync_period_minutes=1, lookback_candles=60),
            FuturesSyncSchedule(interval="5m", sync_period_minutes=5, lookback_candles=50),
            FuturesSyncSchedule(interval="15m", sync_period_minutes=15, lookback_candles=40),
            FuturesSyncSchedule(interval="1h", sync_period_minutes=60, lookback_candles=25),
            FuturesSyncSchedule(interval="4h", sync_period_minutes=240, lookback_candles=20),
            FuturesSyncSchedule(interval="1d", sync_period_minutes=1440, lookback_candles=10)
        ]
        
        # Статистика
        self.stats = {
            "start_time": None,
            "total_syncs": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
            "candles_synced": 0,
            "gaps_found": 0,
            "gaps_filled": 0,
            "yfinance_calls": 0,
            "yfinance_errors": 0,
            "last_sync": None,
            "last_error": None
        }
        
        # YFinance client (будет инициализирован при старте)
        self.yf = None
        
        logger.info(f"🏗️ SimpleFuturesSync initialized")
        logger.info(f"   • Symbols: {', '.join(symbols)}")
        logger.info(f"   • Check gaps on start: {check_gaps_on_start}")
        logger.info(f"   • Intervals: {[s.interval for s in self.schedule]}")
    
    async def start(self):
        """Запустить сервис синхронизации"""
        if self.is_running:
            logger.warning("SimpleFuturesSync уже запущен")
            return
        
        try:
            logger.info("🚀 Запуск SimpleFuturesSync...")
            
            # Проверяем доступность yfinance
            try:
                import yfinance as yf
                self.yf = yf
                logger.info("✅ yfinance library loaded")
            except ImportError as e:
                error_msg = f"yfinance not installed: {e}"
                logger.error(f"❌ {error_msg}")
                raise ImportError("Install with: pip install yfinance") from e
            
            # Проверяем репозиторий
            if not self.repository:
                raise Exception("Repository not initialized")
            
            self.is_running = True
            self.status = SyncStatus.RUNNING
            self.start_time = datetime.now(timezone.utc)
            self.stats["start_time"] = self.start_time
            
            # Проверка пропусков при старте
            if self.check_gaps_on_start:
                logger.info("🔍 Проверка пропусков в данных фьючерсов...")
                await self._check_all_gaps()
            
            # Запускаем основной цикл синхронизации
            self._sync_task = asyncio.create_task(self._sync_loop())
            self._tasks.append(self._sync_task)
            
            logger.info("✅ SimpleFuturesSync запущен успешно")
            logger.info(f"   • Активных задач: {len(self._tasks)}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска SimpleFuturesSync: {e}")
            self.is_running = False
            self.status = SyncStatus.ERROR
            self.stats["last_error"] = str(e)
            raise
    
    async def stop(self):
        """Остановить сервис синхронизации"""
        if not self.is_running:
            logger.warning("SimpleFuturesSync уже остановлен")
            return
        
        logger.info("🛑 Остановка SimpleFuturesSync...")
        
        self.is_running = False
        self.status = SyncStatus.STOPPED
        
        # Отменяем все задачи
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        # Ждем завершения задач
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        self._sync_task = None
        
        logger.info("✅ SimpleFuturesSync остановлен")
    
    async def _sync_loop(self):
        """Основной цикл синхронизации"""
        logger.info("🔄 Запущен основной цикл синхронизации фьючерсов")
        
        while self.is_running:
            try:
                current_time = datetime.now(timezone.utc)
                
                # Проверяем каждый интервал
                for schedule in self.schedule:
                    # Инициализация next_sync при первом запуске
                    if schedule.next_sync is None:
                        schedule.next_sync = current_time
                    
                    # Пора синхронизировать?
                    if current_time >= schedule.next_sync:
                        await self._sync_interval(schedule)
                
                # Пауза перед следующей итерацией
                await asyncio.sleep(30)  # Проверяем каждые 30 секунд
                
            except asyncio.CancelledError:
                logger.info("Цикл синхронизации отменен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле синхронизации: {e}")
                self.stats["failed_syncs"] += 1
                self.stats["last_error"] = str(e)
                await asyncio.sleep(60)  # Пауза после ошибки
    
    async def _sync_interval(self, schedule: FuturesSyncSchedule):
        """
        Синхронизация одного интервала для всех символов
        
        Args:
            schedule: Расписание интервала
        """
        interval = schedule.interval
        
        try:
            self.status = SyncStatus.SYNCING
            logger.info(f"📊 Синхронизация {interval} для {len(self.symbols)} фьючерсов...")
            
            sync_start = datetime.now(timezone.utc)
            total_synced = 0
            
            # Синхронизируем каждый символ
            for symbol in self.symbols:
                try:
                    synced = await self._sync_candles(
                        symbol=symbol,
                        interval=interval,
                        lookback_candles=schedule.lookback_candles
                    )
                    total_synced += synced
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка синхронизации {symbol} {interval}: {e}")
                    schedule.error_count += 1
                    schedule.last_error = str(e)
                    self.stats["yfinance_errors"] += 1
            
            # Обновляем статистику
            schedule.last_sync = sync_start
            schedule.next_sync = sync_start + timedelta(minutes=schedule.sync_period_minutes)
            schedule.sync_count += 1
            
            self.stats["total_syncs"] += 1
            self.stats["successful_syncs"] += 1
            self.stats["candles_synced"] += total_synced
            self.stats["last_sync"] = sync_start
            
            duration = (datetime.now(timezone.utc) - sync_start).total_seconds()
            logger.info(f"✅ Синхронизация {interval} завершена: {total_synced} свечей за {duration:.1f}s")
            logger.info(f"   • Следующая синхронизация: {schedule.next_sync.strftime('%H:%M:%S')}")
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка синхронизации {interval}: {e}")
            schedule.error_count += 1
            schedule.last_error = str(e)
            self.stats["failed_syncs"] += 1
            self.stats["last_error"] = str(e)
            
            # Планируем повторную попытку через минуту
            schedule.next_sync = datetime.now(timezone.utc) + timedelta(minutes=1)
        
        finally:
            self.status = SyncStatus.RUNNING
    
    async def _sync_candles(self, symbol: str, interval: str, lookback_candles: int) -> int:
        """
        Синхронизация свечей для одного символа и интервала
        
        Args:
            symbol: Фьючерсный символ (MCL, MGC, MES, MNQ)
            interval: Интервал свечей
            lookback_candles: Сколько последних свечей загрузить
            
        Returns:
            Количество синхронизированных свечей
        """
        try:
            # Получаем последнюю свечу из БД
            last_candle_time = await self.repository.get_latest_candle_time(symbol, interval)
            
            # Определяем период загрузки
            end_time = datetime.now(timezone.utc)
            
            if last_candle_time:
                # Догружаем с последней известной свечи
                start_time = last_candle_time
                logger.debug(f"📥 {symbol} {interval}: догрузка с {start_time.strftime('%Y-%m-%d %H:%M')}")
            else:
                # Первая загрузка - берем lookback_candles
                interval_enum = CandleInterval(interval)
                interval_seconds = interval_enum.to_seconds()
                
                start_time = end_time - timedelta(seconds=interval_seconds * lookback_candles)
                logger.debug(f"📥 {symbol} {interval}: первая загрузка, {lookback_candles} свечей")
            
            # Проверяем ограничения YFinance
            max_history = self.YFINANCE_LIMITS.get(interval, timedelta(days=730))
            min_allowed_start = end_time - max_history
            
            if start_time < min_allowed_start:
                logger.warning(f"⚠️ {symbol} {interval}: start_time {start_time.date()} старше лимита YFinance")
                logger.warning(f"   • Корректирую на {min_allowed_start.date()}")
                start_time = min_allowed_start
            
            # Загружаем данные через YFinance
            candles = await self._fetch_yfinance_data(symbol, interval, start_time, end_time)
            
            if not candles:
                logger.debug(f"📭 {symbol} {interval}: нет новых данных")
                return 0
            
            # Сохраняем в БД
            candle_objects = []
            
            for candle_dict in candles:
                try:
                    candle = MarketDataCandle.create_from_yfinance_data(
                        symbol=symbol,
                        interval=interval,
                        yf_data=candle_dict
                    )
                    candle_objects.append(candle)
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга свечи {symbol}: {e}")
                    continue
            
            if candle_objects:
                inserted, updated = await self.repository.bulk_insert_candles(
                    candles=candle_objects,
                    batch_size=500
                )
                
                total_saved = inserted + updated
                logger.info(f"✅ {symbol} {interval}: синхронизировано {total_saved} свечей (insert={inserted}, update={updated})")
                return total_saved
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ Ошибка синхронизации {symbol} {interval}: {e}")
            raise
    
    async def _fetch_yfinance_data(
        self, 
        symbol: str, 
        interval: str, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Загрузка данных через YFinance API
        
        Args:
            symbol: Фьючерсный символ
            interval: Интервал свечей
            start_time: Начало периода
            end_time: Конец периода
            
        Returns:
            Список свечей в формате Dict
        """
        try:
            self.stats["yfinance_calls"] += 1
            
            # YFinance маппинг интервалов
            yf_interval_map = {
                "1m": "1m",
                "5m": "5m",
                "15m": "15m",
                "1h": "1h",
                "4h": "4h",
                "1d": "1d",
                "1w": "1wk"
            }
            
            yf_interval = yf_interval_map.get(interval, interval)
            
            # Создаем ticker
            ticker = self.yf.Ticker(symbol)
            
            # Запускаем синхронный вызов в executor
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None,
                lambda: ticker.history(
                    start=start_time,
                    end=end_time,
                    interval=yf_interval,
                    auto_adjust=False,
                    actions=False
                )
            )
            
            if df.empty:
                logger.debug(f"📭 YFinance: нет данных для {symbol} {interval}")
                return []
            
            # Конвертируем DataFrame в список словарей
            candles = []
            for index, row in df.iterrows():
                candle_dict = {
                    "Datetime": index.to_pydatetime(),
                    "Open": row["Open"],
                    "High": row["High"],
                    "Low": row["Low"],
                    "Close": row["Close"],
                    "Volume": row["Volume"]
                }
                candles.append(candle_dict)
            
            logger.debug(f"✅ YFinance: получено {len(candles)} свечей для {symbol} {interval}")
            return candles
            
        except Exception as e:
            logger.error(f"❌ YFinance API error для {symbol} {interval}: {e}")
            self.stats["yfinance_errors"] += 1
            raise
    
    async def _check_all_gaps(self):
        """Проверка пропусков во всех символах и интервалах"""
        self.status = SyncStatus.CHECKING_GAPS
        logger.info("🔍 Проверка пропусков в данных фьючерсов...")
        
        gaps_found = 0
        
        for symbol in self.symbols:
            for schedule in self.schedule:
                interval = schedule.interval
                
                try:
                    # Проверяем пропуски
                    expected_end = datetime.now(timezone.utc)
                    gap_info = await self.repository.check_data_gaps(
                        symbol=symbol,
                        interval=interval,
                        expected_end=expected_end
                    )
                    
                    if gap_info and gap_info.get("has_gap"):
                        gaps_found += 1
                        self.stats["gaps_found"] += 1
                        
                        gap_start = gap_info.get("gap_start")
                        gap_end = gap_info.get("gap_end")
                        missing = gap_info.get("missing_candles", "unknown")
                        
                        logger.warning(f"⚠️ Пропуск найден: {symbol} {interval}")
                        logger.warning(f"   • Период: {gap_start} → {gap_end}")
                        logger.warning(f"   • Недостает свечей: {missing}")
                        
                        # Пытаемся заполнить пропуск
                        await self._fill_gap(symbol, interval, gap_start, gap_end)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка проверки пропусков {symbol} {interval}: {e}")
        
        if gaps_found > 0:
            logger.info(f"✅ Проверка завершена: найдено {gaps_found} пропусков")
        else:
            logger.info("✅ Проверка завершена: пропусков не найдено")
        
        self.status = SyncStatus.RUNNING
    
    async def _fill_gap(
        self, 
        symbol: str, 
        interval: str, 
        gap_start: Optional[datetime], 
        gap_end: datetime
    ):
        """
        Заполнение обнаруженного пропуска
        
        Args:
            symbol: Фьючерсный символ
            interval: Интервал свечей
            gap_start: Начало пропуска (может быть None если данных вообще нет)
            gap_end: Конец пропуска
        """
        self.status = SyncStatus.FILLING_GAP
        logger.info(f"🔧 Заполнение пропуска: {symbol} {interval}")
        
        try:
            # Если gap_start is None - загружаем максимум доступной истории
            if gap_start is None:
                max_history = self.YFINANCE_LIMITS.get(interval, timedelta(days=730))
                gap_start = gap_end - max_history
                logger.info(f"   • Загрузка полной истории: {max_history.days} дней")
            
            # Проверяем лимиты YFinance
            max_history = self.YFINANCE_LIMITS.get(interval, timedelta(days=730))
            min_allowed_start = gap_end - max_history
            
            if gap_start < min_allowed_start:
                logger.warning(f"⚠️ gap_start {gap_start.date()} старше лимита YFinance")
                gap_start = min_allowed_start
            
            # Загружаем данные
            candles = await self._fetch_yfinance_data(symbol, interval, gap_start, gap_end)
            
            if not candles:
                logger.warning(f"⚠️ Нет данных для заполнения пропуска {symbol} {interval}")
                return
            
            # Сохраняем в БД
            candle_objects = []
            
            for candle_dict in candles:
                try:
                    candle = MarketDataCandle.create_from_yfinance_data(
                        symbol=symbol,
                        interval=interval,
                        yf_data=candle_dict
                    )
                    candle_objects.append(candle)
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга свечи: {e}")
                    continue
            
            if candle_objects:
                inserted, updated = await self.repository.bulk_insert_candles(
                    candles=candle_objects,
                    batch_size=500
                )
                
                total_saved = inserted + updated
                self.stats["gaps_filled"] += 1
                logger.info(f"✅ Пропуск заполнен: {symbol} {interval}, {total_saved} свечей")
            
        except Exception as e:
            logger.error(f"❌ Ошибка заполнения пропуска {symbol} {interval}: {e}")
        
        finally:
            self.status = SyncStatus.RUNNING
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику работы"""
        uptime = None
        if self.start_time:
            uptime = datetime.now(timezone.utc) - self.start_time
        
        return {
            **self.stats,
            "uptime_seconds": uptime.total_seconds() if uptime else 0,
            "uptime_formatted": str(uptime).split('.')[0] if uptime else "0:00:00",
            "is_running": self.is_running,
            "status": self.status.value,
            "symbols": self.symbols,
            "intervals": [s.interval for s in self.schedule],
            "schedule_details": [
                {
                    "interval": s.interval,
                    "sync_period_minutes": s.sync_period_minutes,
                    "last_sync": s.last_sync.isoformat() if s.last_sync else None,
                    "next_sync": s.next_sync.isoformat() if s.next_sync else None,
                    "sync_count": s.sync_count,
                    "error_count": s.error_count,
                    "last_error": s.last_error
                }
                for s in self.schedule
            ]
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Проверка здоровья сервиса"""
        is_healthy = (
            self.is_running and
            self.status in [SyncStatus.RUNNING, SyncStatus.SYNCING] and
            self.stats["yfinance_errors"] < 10
        )
        
        return {
            "healthy": is_healthy,
            "status": self.status.value,
            "is_running": self.is_running,
            "total_syncs": self.stats["total_syncs"],
            "successful_syncs": self.stats["successful_syncs"],
            "failed_syncs": self.stats["failed_syncs"],
            "yfinance_errors": self.stats["yfinance_errors"],
            "last_sync": self.stats["last_sync"].isoformat() if self.stats["last_sync"] else None,
            "last_error": self.stats["last_error"]
        }
    
    def __repr__(self):
        return (f"SimpleFuturesSync(symbols={self.symbols}, "
                f"status={self.status.value}, "
                f"synced={self.stats['candles_synced']})")


# Export
__all__ = [
    "SimpleFuturesSync",
    "FuturesSyncSchedule",
    "SyncStatus"
]

logger.info("SimpleFuturesSync module loaded successfully")
