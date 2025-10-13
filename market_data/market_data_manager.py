import asyncio
import logging
import queue  # Thread-safe очередь для WebSocket событий
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
from dataclasses import dataclass, field
import traceback

from .websocket_provider import WebSocketProvider, RealtimeMarketData
from .rest_api_provider import RestApiProvider
from .yfinance_websocket_provider import YFinanceWebSocketProvider, RealtimeFuturesData
from .candle_sync_service import CandleSyncService, SyncConfig
from .candle_aggregator import CandleAggregator  # 🆕 ДОБАВЛЕНО
from config import Config

logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    """Типы источников данных"""
    WEBSOCKET = "websocket"
    REST_API = "rest_api" 
    COMBINED = "combined"
    CACHE = "cache"
    YFINANCE = "yfinance"


class HealthStatus(Enum):
    """Статус здоровья системы"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  
    CRITICAL = "critical"
    INITIALIZING = "initializing"


@dataclass
class MarketDataSnapshot:
    """Снимок рыночных данных (криптовалюты)"""
    symbol: str
    timestamp: datetime
    current_price: float
    price_change_1m: float
    price_change_5m: float
    price_change_24h: float
    volume_24h: float
    high_24h: float
    low_24h: float
    bid_price: float
    ask_price: float
    spread: float
    open_interest: float
    
    # Дополнительные данные
    volume_analysis: Dict[str, Any] = field(default_factory=dict)
    orderbook_pressure: Dict[str, Any] = field(default_factory=dict)
    trades_analysis: Dict[str, Any] = field(default_factory=dict)
    hourly_stats: Dict[str, Any] = field(default_factory=dict)
    
    # Метаданные
    data_source: DataSourceType = DataSourceType.COMBINED
    data_quality: Dict[str, Any] = field(default_factory=dict)
    has_realtime_data: bool = False
    has_historical_data: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь для сериализации"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'current_price': self.current_price,
            'price_change_1m': self.price_change_1m,
            'price_change_5m': self.price_change_5m,
            'price_change_24h': self.price_change_24h,
            'volume_24h': self.volume_24h,
            'high_24h': self.high_24h,
            'low_24h': self.low_24h,
            'bid_price': self.bid_price,
            'ask_price': self.ask_price,
            'spread': self.spread,
            'open_interest': self.open_interest,
            'volume_analysis': self.volume_analysis,
            'orderbook_pressure': self.orderbook_pressure,
            'trades_analysis': self.trades_analysis,
            'hourly_stats': self.hourly_stats,
            'data_source': self.data_source.value,
            'data_quality': self.data_quality,
            'has_realtime_data': self.has_realtime_data,
            'has_historical_data': self.has_historical_data
        }


@dataclass
class FuturesSnapshot:
    """Снимок данных фьючерса"""
    symbol: str
    timestamp: datetime
    current_price: float
    price_change_1m: float
    price_change_5m: float
    volume: float
    data_points: int
    
    # Метаданные
    data_source: DataSourceType = DataSourceType.YFINANCE
    has_sufficient_data: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь для сериализации"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'current_price': self.current_price,
            'price_change_1m': self.price_change_1m,
            'price_change_5m': self.price_change_5m,
            'volume': self.volume,
            'data_points': self.data_points,
            'data_source': self.data_source.value,
            'has_sufficient_data': self.has_sufficient_data
        }


class MarketDataManager:
    """
    🚀 Центральный менеджер для управления всеми источниками рыночных данных
    
    Поддерживает:
    ✅ Bybit WebSocket + REST API (криптовалюты) - МНОЖЕСТВЕННЫЕ СИМВОЛЫ
    ✅ YFinance WebSocket (фьючерсы CME)
    ✅ CandleAggregator - сохранение WebSocket данных в БД
    ✅ Синхронизация исторических свечей для МНОЖЕСТВЕННЫХ символов
    ✅ Thread-safe обработка сообщений
    ✅ Автоматическое переподключение
    ✅ Интеллектуальное кэширование 
    ✅ Детальный мониторинг производительности
    ✅ Graceful shutdown и error recovery
    """
    
    def __init__(self, 
                 symbols_crypto: List[str] = None,
                 symbols_futures: List[str] = None,
                 testnet: bool = None, 
                 enable_bybit_websocket: bool = True,
                 enable_yfinance_websocket: bool = False,
                 enable_rest_api: bool = True,
                 enable_candle_sync: bool = True,
                 enable_candle_aggregation: bool = True,  # 🆕 ДОБАВЛЕНО
                 rest_cache_minutes: int = 1, 
                 websocket_reconnect: bool = True):
        """
        Инициализация менеджера данных
        
        Args:
            symbols_crypto: Список крипто символов (BTCUSDT, ETHUSDT)
            symbols_futures: Список фьючерсов CME (MCL, MGC, MES, MNQ)
            testnet: Использовать testnet для Bybit
            enable_bybit_websocket: Включить Bybit WebSocket
            enable_yfinance_websocket: Включить YFinance WebSocket
            enable_rest_api: Включить REST API провайдер
            enable_candle_sync: Включить синхронизацию исторических свечей
            enable_candle_aggregation: Включить агрегацию и сохранение WebSocket данных в БД
            rest_cache_minutes: Время кэширования REST данных в минутах
            websocket_reconnect: Включить автоматическое переподключение
        """
        # Символы криптовалют и фьючерсов
        self.symbols_crypto = symbols_crypto or [Config.SYMBOL]
        self.symbols_futures = symbols_futures or ["MCL", "MGC", "MES", "MNQ"]
        self.testnet = testnet if testnet is not None else Config.BYBIT_TESTNET
        
        # Провайдеры данных
        self.bybit_websocket_provider: Optional[WebSocketProvider] = None
        self.yfinance_websocket_provider: Optional[YFinanceWebSocketProvider] = None
        self.rest_api_provider: Optional[RestApiProvider] = None
        self.candle_sync_service: Optional[CandleSyncService] = None
        self.candle_aggregator: Optional[CandleAggregator] = None  # 🆕 ДОБАВЛЕНО
        
        # Настройки
        self.enable_bybit_websocket = enable_bybit_websocket
        self.enable_yfinance_websocket = enable_yfinance_websocket
        self.enable_rest_api = enable_rest_api
        self.enable_candle_sync = enable_candle_sync
        self.enable_candle_aggregation = enable_candle_aggregation  # 🆕 ДОБАВЛЕНО
        self.websocket_reconnect = websocket_reconnect
        self.rest_cache_duration = timedelta(minutes=rest_cache_minutes)
        
        # Кэш и состояние данных
        self.last_rest_update: Optional[datetime] = None
        self.cached_rest_data: Optional[Dict[str, Any]] = None
        self.last_snapshot: Optional[MarketDataSnapshot] = None
        self.last_futures_snapshots: Dict[str, FuturesSnapshot] = {}
        
        # Подписчики на обновления данных
        self.data_subscribers: List[Callable[[MarketDataSnapshot], None]] = []
        self.futures_subscribers: List[Callable[[str, FuturesSnapshot], None]] = []
        
        # Управление жизненным циклом
        self.is_running = False
        self.initialization_complete = False
        self.shutdown_event = asyncio.Event()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Задачи фонового выполнения
        self.background_tasks: List[asyncio.Task] = []
        
        # Thread-safe очереди для WebSocket событий
        self._bybit_event_queue: Optional[queue.Queue] = None
        self._yfinance_event_queue: Optional[queue.Queue] = None
        
        # Статистика и мониторинг
        self.stats = {
            # Bybit статистика
            "bybit_websocket_updates": 0,
            "bybit_rest_api_calls": 0,
            "bybit_websocket_reconnects": 0,
            "bybit_callback_errors": 0,
            "last_bybit_websocket_data": None,
            "last_bybit_rest_data": None,
            
            # YFinance статистика
            "yfinance_websocket_updates": 0,
            "yfinance_reconnects": 0,
            "yfinance_callback_errors": 0,
            "last_yfinance_data": None,
            
            # Общая статистика
            "data_snapshots_created": 0,
            "futures_snapshots_created": 0,
            "errors": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "subscriber_notifications": 0,
            "futures_subscriber_notifications": 0,
            "start_time": datetime.now(),
            "last_error": None
        }
        
        # Конфигурация переподключения
        self.reconnect_delay = 5  # секунд
        self.max_reconnect_attempts = 10
        self.current_bybit_reconnect_attempts = 0
        self.current_yfinance_reconnect_attempts = 0
        
        logger.info(f"🏗️ MarketDataManager инициализирован")
        logger.info(f"   • Crypto symbols: {', '.join(self.symbols_crypto)}")
        logger.info(f"   • Futures symbols: {', '.join(self.symbols_futures)}")
        logger.info(f"   • Bybit WS: {enable_bybit_websocket}, YFinance WS: {enable_yfinance_websocket}")
        logger.info(f"   • Candle Sync: {enable_candle_sync} (для {len(self.symbols_crypto)} символов)")
        logger.info(f"   • Candle Aggregation: {enable_candle_aggregation}")  # 🆕 ДОБАВЛЕНО
    
    async def start(self) -> bool:
        """
        🚀 Запуск всех провайдеров данных
        
        Returns:
            True если хотя бы один провайдер запущен успешно
        """
        try:
            logger.info(f"🚀 Запуск MarketDataManager...")
            self.stats["start_time"] = datetime.now()
            
            # Сохраняем ссылку на основной event loop
            self._main_loop = asyncio.get_running_loop()
            
            # Создаем thread-safe очереди
            self._bybit_event_queue = queue.Queue(maxsize=5000)
            self._yfinance_event_queue = queue.Queue(maxsize=1000)
            
            providers_started = 0
            initialization_errors = []
            
            # ========== ИНИЦИАЛИЗАЦИЯ BYBIT REST API ==========
            if self.enable_rest_api:
                try:
                    logger.info("📡 Инициализация Bybit REST API провайдера...")
                    self.rest_api_provider = RestApiProvider(testnet=self.testnet)
                    
                    connection_task = asyncio.create_task(self.rest_api_provider.check_connection())
                    connection_ok = await asyncio.wait_for(connection_task, timeout=10)
                    
                    if connection_ok:
                        providers_started += 1
                        logger.info("✅ Bybit REST API провайдер готов")
                        await self._initialize_rest_data()
                    else:
                        initialization_errors.append("Bybit REST API connection failed")
                        logger.warning("⚠️ Bybit REST API провайдер недоступен")
                        
                except asyncio.TimeoutError:
                    initialization_errors.append("Bybit REST API connection timeout")
                    logger.error("❌ Таймаут подключения к Bybit REST API")
                except Exception as e:
                    initialization_errors.append(f"Bybit REST API error: {str(e)}")
                    logger.error(f"❌ Ошибка инициализации Bybit REST API: {e}")
                    self.stats["errors"] += 1
                    self.stats["last_error"] = str(e)
            
            # ========== ИНИЦИАЛИЗАЦИЯ СИНХРОНИЗАЦИИ СВЕЧЕЙ ДЛЯ ВСЕХ СИМВОЛОВ ==========
            if self.enable_rest_api and self.enable_candle_sync:
                try:
                    logger.info(f"🔄 Инициализация сервиса синхронизации свечей для {len(self.symbols_crypto)} символов...")
                    
                    # Получаем репозиторий
                    from database.repositories import get_market_data_repository
                    repository = await get_market_data_repository()
                    
                    # Создаем конфигурацию
                    sync_config = SyncConfig(
                        intervals_to_sync=["1m", "5m", "15m", "1h", "1d"],
                        check_gaps_on_start=True,
                        max_gap_days=30
                    )
                    
                    # Создаем сервис
                    self.candle_sync_service = CandleSyncService(
                        repository=repository,
                        rest_api_provider=self.rest_api_provider,
                        historical_loader=None,
                        config=sync_config
                    )
                    
                    # Запускаем синхронизацию для ВСЕХ крипто символов
                    logger.info(f"🎯 Запуск синхронизации для символов: {', '.join(self.symbols_crypto)}")
                    sync_started = await self.candle_sync_service.start(self.symbols_crypto)
                    
                    if sync_started:
                        providers_started += 1
                        total_tasks = len(self.symbols_crypto) * len(sync_config.intervals_to_sync)
                        logger.info(f"✅ Сервис синхронизации запущен для {len(self.symbols_crypto)} символов ({total_tasks} задач)")
                    else:
                        logger.warning("⚠️ Не удалось запустить синхронизацию свечей")
                        initialization_errors.append("Candle sync startup failed")
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка инициализации синхронизации: {e}")
                    logger.error(f"Stack trace: {traceback.format_exc()}")
                    initialization_errors.append(f"Candle sync error: {str(e)}")
                    self.stats["errors"] += 1
                    self.stats["last_error"] = str(e)
            
            # ========== ИНИЦИАЛИЗАЦИЯ BYBIT WEBSOCKET ==========
            if self.enable_bybit_websocket:
                bybit_ws_started = await self._initialize_bybit_websocket()
                if bybit_ws_started:
                    providers_started += 1
                else:
                    initialization_errors.append("Bybit WebSocket initialization failed")
            
            # ========== 🆕 ИНИЦИАЛИЗАЦИЯ CANDLE AGGREGATOR ==========
            if self.enable_candle_aggregation and self.enable_bybit_websocket and self.bybit_websocket_provider:
                try:
                    logger.info(f"🏗️ Инициализация CandleAggregator для {len(self.symbols_crypto)} символов...")
                    
                    self.candle_aggregator = CandleAggregator(
                        symbols=self.symbols_crypto,
                        intervals=["1m", "5m", "15m", "1h", "1d"],
                        batch_save=True,  # Батчевое сохранение для производительности
                        batch_size=50
                    )
                    
                    # Запускаем агрегатор
                    await self.candle_aggregator.start()
                    
                    # Подписываем агрегатор на WebSocket обновления
                    self.bybit_websocket_provider.add_ticker_callback(
                        lambda symbol, ticker_data: asyncio.create_task(
                            self._handle_ticker_for_aggregator(symbol, ticker_data)
                        )
                    )
                    logger.info("✅ CandleAggregator подписан на WebSocket обновления")
                    
                    providers_started += 1
                    logger.info("✅ CandleAggregator инициализирован и запущен")
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка инициализации CandleAggregator: {e}")
                    logger.error(traceback.format_exc())
                    initialization_errors.append(f"CandleAggregator error: {str(e)}")
                    self.stats["errors"] += 1
                    self.stats["last_error"] = str(e)
            
            # ========== ИНИЦИАЛИЗАЦИЯ YFINANCE WEBSOCKET ==========
            if self.enable_yfinance_websocket:
                yfinance_ws_started = await self._initialize_yfinance_websocket()
                if yfinance_ws_started:
                    providers_started += 1
                else:
                    initialization_errors.append("YFinance WebSocket initialization failed")
            
            # Проверяем результат инициализации
            if providers_started == 0:
                logger.error(f"💥 Ни один провайдер не был запущен успешно. Ошибки: {initialization_errors}")
                return False
            
            # Устанавливаем флаги состояния
            self.is_running = True
            self.initialization_complete = True
            
            # Запускаем фоновые задачи
            await self._start_background_tasks()
            
            # Создаем начальный снимок данных
            if self.enable_bybit_websocket or self.enable_rest_api:
                initial_snapshot = await self.get_market_snapshot()
                if initial_snapshot:
                    logger.info(f"📊 Начальные крипто данные: ${initial_snapshot.current_price:,.2f}")
                    self.last_snapshot = initial_snapshot
            
            # Создаем начальные снимки фьючерсов
            if self.enable_yfinance_websocket:
                for symbol in self.symbols_futures:
                    futures_snapshot = await self.get_futures_snapshot(symbol)
                    if futures_snapshot:
                        logger.info(f"📊 Начальные данные {symbol}: ${futures_snapshot.current_price:,.2f}")
                        self.last_futures_snapshots[symbol] = futures_snapshot
            
            logger.info(f"✅ MarketDataManager запущен успешно!")
            logger.info(f"📈 Провайдеров активно: {providers_started}")
            logger.info(f"🔌 Bybit WS: {'✅' if self.bybit_websocket_provider and self.bybit_websocket_provider.is_running() else '❌'}")
            logger.info(f"🔌 YFinance WS: {'✅' if self.yfinance_websocket_provider and self.yfinance_websocket_provider.is_running() else '❌'}")
            logger.info(f"📡 REST API: {'✅' if self.rest_api_provider else '❌'}")
            
            # Улучшенное логирование синхронизации
            if self.candle_sync_service and self.candle_sync_service.is_running:
                sync_stats = self.candle_sync_service.get_stats()
                active_tasks = sync_stats.get('active_tasks', 0)
                symbols_syncing = sync_stats.get('symbols_syncing', [])
                logger.info(f"🔄 Candle Sync: ✅ ({len(symbols_syncing)} символов, {active_tasks} активных задач)")
                logger.info(f"   Символы: {', '.join(symbols_syncing)}")
            else:
                logger.info(f"🔄 Candle Sync: ❌")
            
            # 🆕 Логирование CandleAggregator
            if self.candle_aggregator and self.candle_aggregator.is_running:
                agg_stats = self.candle_aggregator.get_stats()
                logger.info(f"🏗️ Candle Aggregator: ✅ ({len(self.symbols_crypto)} символов, {len(agg_stats['intervals'])} интервалов)")
                logger.info(f"   Интервалы: {', '.join(agg_stats['intervals'])}")
            else:
                logger.info(f"🏗️ Candle Aggregator: ❌")
            
            return True
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка запуска MarketDataManager: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return False
    
    async def _initialize_rest_data(self):
        """Получает начальные данные через REST API"""
        try:
            logger.info("📥 Получение начальных Bybit REST данных...")
            # Берем первый крипто символ для начальных данных
            symbol = self.symbols_crypto[0]
            self.cached_rest_data = await self.rest_api_provider.get_comprehensive_market_data(symbol)
            self.last_rest_update = datetime.now()
            self.stats["bybit_rest_api_calls"] += 1
            self.stats["last_bybit_rest_data"] = datetime.now()
            logger.info("✅ Начальные Bybit REST данные получены")
        except Exception as e:
            logger.error(f"❌ Ошибка получения начальных REST данных: {e}")
            raise
    
    async def _initialize_bybit_websocket(self) -> bool:
        """🆕 ИЗМЕНЕНО: Инициализация Bybit WebSocket провайдера с множественными символами"""
        try:
            logger.info("🔌 Инициализация Bybit WebSocket провайдера...")
            
            # 🆕 ИЗМЕНЕНО: Передаем ВСЕ крипто символы
            self.bybit_websocket_provider = WebSocketProvider(
                symbols=self.symbols_crypto,  # ✅ ВСЕ 15 символов!
                testnet=self.testnet
            )
            
            # Подписываемся на обновления с thread-safe callback'ами
            # 🆕 ИЗМЕНЕНО: Callbacks теперь принимают (symbol, data)
            self.bybit_websocket_provider.add_ticker_callback(self._on_bybit_ticker_update)
            self.bybit_websocket_provider.add_orderbook_callback(self._on_bybit_orderbook_update)
            self.bybit_websocket_provider.add_trades_callback(self._on_bybit_trades_update)
            
            # Запускаем WebSocket с таймаутом
            start_task = asyncio.create_task(self.bybit_websocket_provider.start())
            await asyncio.wait_for(start_task, timeout=15)
            
            # Ждем получения данных для всех символов
            logger.info(f"⏳ Ожидание Bybit WebSocket данных для {len(self.symbols_crypto)} символов...")
            data_received = await self.bybit_websocket_provider.wait_for_data(
                timeout=30,
                min_symbols=max(1, len(self.symbols_crypto) // 2)  # Хотя бы половина символов
            )
            
            if data_received:
                self.current_bybit_reconnect_attempts = 0
                logger.info("✅ Bybit WebSocket провайдер готов")
                return True
            else:
                logger.warning("⚠️ Bybit WebSocket данные не получены в течение таймаута")
                return False
                
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут инициализации Bybit WebSocket")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Bybit WebSocket: {e}")
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return False
    
    async def _initialize_yfinance_websocket(self) -> bool:
        """Инициализация YFinance WebSocket провайдера"""
        try:
            logger.info("🔌 Инициализация YFinance WebSocket провайдера...")
            self.yfinance_websocket_provider = YFinanceWebSocketProvider(
                symbols=self.symbols_futures,
                verbose=False
            )
            
            # Подписываемся на обновления
            self.yfinance_websocket_provider.add_data_callback(self._on_yfinance_data_update)
            
            # Запускаем WebSocket с таймаутом
            start_task = asyncio.create_task(self.yfinance_websocket_provider.start())
            await asyncio.wait_for(start_task, timeout=20)
            
            # Ждем получения данных для всех фьючерсов
            logger.info(f"⏳ Ожидание YFinance WebSocket данных для {len(self.symbols_futures)} символов...")
            data_received = await self.yfinance_websocket_provider.wait_for_data(timeout=60)
            
            if data_received:
                self.current_yfinance_reconnect_attempts = 0
                logger.info("✅ YFinance WebSocket провайдер готов")
                return True
            else:
                logger.warning("⚠️ YFinance WebSocket данные не получены в течение таймаута")
                return False
                
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут инициализации YFinance WebSocket")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации YFinance WebSocket: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return False
    
    async def _start_background_tasks(self):
        """Запуск фоновых задач"""
        try:
            # Задача обработки Bybit WebSocket событий
            if self.bybit_websocket_provider:
                bybit_processor = asyncio.create_task(self._bybit_event_processor())
                self.background_tasks.append(bybit_processor)
                logger.info("🔄 Запущен процессор Bybit WebSocket событий")
            
            # Задача обработки YFinance WebSocket событий
            if self.yfinance_websocket_provider:
                yfinance_processor = asyncio.create_task(self._yfinance_event_processor())
                self.background_tasks.append(yfinance_processor)
                logger.info("🔄 Запущен процессор YFinance WebSocket событий")
            
            # Задача мониторинга Bybit WebSocket
            if self.websocket_reconnect and self.bybit_websocket_provider:
                bybit_monitor = asyncio.create_task(self._bybit_monitor_task())
                self.background_tasks.append(bybit_monitor)
                logger.info("🔍 Запущен мониторинг Bybit WebSocket")
            
            # Задача мониторинга YFinance WebSocket
            if self.websocket_reconnect and self.yfinance_websocket_provider:
                yfinance_monitor = asyncio.create_task(self._yfinance_monitor_task())
                self.background_tasks.append(yfinance_monitor)
                logger.info("🔍 Запущен мониторинг YFinance WebSocket")
            
            # Задача периодической очистки
            cleanup_task = asyncio.create_task(self._periodic_cleanup_task())
            self.background_tasks.append(cleanup_task)
            logger.info("🧹 Запущена задача очистки статистики")
            
            logger.info(f"🔄 Запущено {len(self.background_tasks)} фоновых задач")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска фоновых задач: {e}")
    
    # ========== BYBIT WEBSOCKET ОБРАБОТЧИКИ ==========
    
    async def _bybit_event_processor(self):
        """Фоновая задача для обработки Bybit WebSocket событий"""
        logger.info("🔄 Запущен цикл обработки Bybit WebSocket событий")
        
        while self.is_running and not self.shutdown_event.is_set():
            try:
                if not self._bybit_event_queue:
                    await asyncio.sleep(1)
                    continue
                
                try:
                    event = self._bybit_event_queue.get_nowait()
                    await self._process_bybit_event(event)
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    continue
                    
            except asyncio.CancelledError:
                logger.info("🔄 Процессор Bybit WebSocket событий отменен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в процессоре Bybit WebSocket: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(1)
        
        logger.info("🛑 Цикл обработки Bybit WebSocket остановлен")
    
    async def _process_bybit_event(self, event: Dict[str, Any]):
        """Обрабатывает событие от Bybit WebSocket"""
        try:
            event_type = event.get("type")
            
            if event_type == "ticker":
                if self.data_subscribers:
                    await self._notify_subscribers_async()
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки Bybit события: {e}")
            self.stats["errors"] += 1
    
    def _on_bybit_ticker_update(self, symbol: str, ticker_data: dict):  # 🆕 ИЗМЕНЕНО
        """Thread-safe callback для Bybit тикера"""
        try:
            self.stats["bybit_websocket_updates"] += 1
            self.stats["last_bybit_websocket_data"] = datetime.now()
            
            if self._bybit_event_queue:
                try:
                    self._bybit_event_queue.put_nowait({
                        "type": "ticker",
                        "symbol": symbol,  # 🆕 ДОБАВЛЕНО
                        "data": ticker_data
                    })
                except queue.Full:
                    logger.warning("⚠️ Очередь Bybit событий переполнена")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки Bybit ticker для {symbol}: {e}")
            self.stats["bybit_callback_errors"] += 1
            self.stats["errors"] += 1
    
    def _on_bybit_orderbook_update(self, symbol: str, orderbook_data: dict):  # 🆕 ИЗМЕНЕНО
        """Thread-safe callback для Bybit ордербука"""
        try:
            if self._bybit_event_queue:
                try:
                    self._bybit_event_queue.put_nowait({
                        "type": "orderbook",
                        "symbol": symbol,  # 🆕 ДОБАВЛЕНО
                        "data": orderbook_data
                    })
                except queue.Full:
                    logger.warning("⚠️ Очередь Bybit событий переполнена")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки Bybit orderbook для {symbol}: {e}")
            self.stats["bybit_callback_errors"] += 1
    
    def _on_bybit_trades_update(self, symbol: str, trades_data: list):  # 🆕 ИЗМЕНЕНО
        """Thread-safe callback для Bybit трейдов"""
        try:
            if self._bybit_event_queue:
                try:
                    self._bybit_event_queue.put_nowait({
                        "type": "trades",
                        "symbol": symbol,  # 🆕 ДОБАВЛЕНО
                        "data": trades_data
                    })
                except queue.Full:
                    logger.warning("⚠️ Очередь Bybit событий переполнена")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки Bybit trades для {symbol}: {e}")
            self.stats["bybit_callback_errors"] += 1
    
    async def _bybit_monitor_task(self):
        """Мониторинг Bybit WebSocket соединения"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(30)
                
                if not self.bybit_websocket_provider or not self.bybit_websocket_provider.is_running():
                    logger.warning("⚠️ Bybit WebSocket потеряно, попытка переподключения...")
                    
                    if self.current_bybit_reconnect_attempts < self.max_reconnect_attempts:
                        success = await self._attempt_bybit_reconnect()
                        if success:
                            logger.info("✅ Bybit WebSocket переподключен")
                            self.current_bybit_reconnect_attempts = 0
                        else:
                            self.current_bybit_reconnect_attempts += 1
                    else:
                        logger.error("💥 Превышено максимум попыток переподключения Bybit")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка мониторинга Bybit: {e}")
    
    async def _attempt_bybit_reconnect(self) -> bool:
        """Попытка переподключения Bybit WebSocket"""
        try:
            if self.bybit_websocket_provider:
                await self.bybit_websocket_provider.stop()
            
            await asyncio.sleep(self.reconnect_delay)
            success = await self._initialize_bybit_websocket()
            
            if success:
                self.stats["bybit_websocket_reconnects"] += 1
                
                # 🆕 Переподписываем CandleAggregator если есть
                if self.candle_aggregator and self.candle_aggregator.is_running:
                    self.bybit_websocket_provider.add_ticker_callback(
                        lambda symbol, ticker_data: asyncio.create_task(
                            self._handle_ticker_for_aggregator(symbol, ticker_data)
                        )
                    )
                    logger.info("✅ CandleAggregator переподписан после переподключения")
            
            return success
        except Exception as e:
            logger.error(f"❌ Ошибка переподключения Bybit: {e}")
            return False
    
    # ========== 🆕 CANDLE AGGREGATOR ОБРАБОТЧИК ==========
    
    async def _handle_ticker_for_aggregator(self, symbol: str, ticker_data: dict):
        """
        🆕 Обработчик ticker updates для CandleAggregator
        
        Args:
            symbol: Символ (передается от WebSocket callback)
            ticker_data: Данные тикера от WebSocket
        """
        try:
            if not self.candle_aggregator or not self.candle_aggregator.is_running:
                return
            
            # Передаем в агрегатор
            await self.candle_aggregator.process_ticker_update(symbol, ticker_data)
            
        except Exception as e:
            logger.error(f"❌ Ошибка передачи тика {symbol} в агрегатор: {e}")
    
    # ========== YFINANCE WEBSOCKET ОБРАБОТЧИКИ ==========
    
    async def _yfinance_event_processor(self):
        """Фоновая задача для обработки YFinance WebSocket событий"""
        logger.info("🔄 Запущен цикл обработки YFinance WebSocket событий")
        
        while self.is_running and not self.shutdown_event.is_set():
            try:
                if not self._yfinance_event_queue:
                    await asyncio.sleep(1)
                    continue
                
                try:
                    event = self._yfinance_event_queue.get_nowait()
                    await self._process_yfinance_event(event)
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    continue
                    
            except asyncio.CancelledError:
                logger.info("🔄 Процессор YFinance WebSocket отменен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в процессоре YFinance WebSocket: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(1)
        
        logger.info("🛑 Цикл обработки YFinance WebSocket остановлен")
    
    async def _process_yfinance_event(self, event: Dict[str, Any]):
        """Обрабатывает событие от YFinance WebSocket"""
        try:
            symbol = event.get("symbol")
            data = event.get("data")
            
            if symbol and data:
                # Уведомляем подписчиков
                if self.futures_subscribers:
                    await self._notify_futures_subscribers_async(symbol)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки YFinance события: {e}")
            self.stats["errors"] += 1
    
    def _on_yfinance_data_update(self, symbol: str, data: dict):
        """Thread-safe callback для YFinance данных"""
        try:
            self.stats["yfinance_websocket_updates"] += 1
            self.stats["last_yfinance_data"] = datetime.now()
            
            if self._yfinance_event_queue:
                try:
                    self._yfinance_event_queue.put_nowait({
                        "symbol": symbol,
                        "data": data
                    })
                except queue.Full:
                    logger.warning(f"⚠️ Очередь YFinance событий переполнена для {symbol}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки YFinance данных {symbol}: {e}")
            self.stats["yfinance_callback_errors"] += 1
            self.stats["errors"] += 1
    
    async def _yfinance_monitor_task(self):
        """Мониторинг YFinance WebSocket соединения"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(90)
                
                is_healthy = (self.yfinance_websocket_provider and 
                             self.yfinance_websocket_provider.is_connection_healthy())
                
                if not is_healthy:
                    if self.yfinance_websocket_provider:
                        stats = self.yfinance_websocket_provider.get_connection_stats()
                        logger.warning(f"⚠️ YFinance WebSocket нездоров")
                        logger.warning(f"📊 Сообщений получено: {stats['messages_received']}")
                    
                    if self.current_yfinance_reconnect_attempts < self.max_reconnect_attempts:
                        logger.info(f"🔄 Попытка переподключения {self.current_yfinance_reconnect_attempts + 1}/{self.max_reconnect_attempts}")
                        success = await self._attempt_yfinance_reconnect()
                        
                        if success:
                            logger.info("✅ YFinance WebSocket успешно переподключен")
                            self.current_yfinance_reconnect_attempts = 0
                        else:
                            self.current_yfinance_reconnect_attempts += 1
                    else:
                        logger.error(f"💥 Превышено максимум попыток переподключения YFinance")
                        await asyncio.sleep(600)
                        self.current_yfinance_reconnect_attempts = 0
                else:
                    if self.current_yfinance_reconnect_attempts > 0:
                        self.current_yfinance_reconnect_attempts = 0
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка мониторинга YFinance: {e}")
    
    async def _attempt_yfinance_reconnect(self) -> bool:
        """Попытка переподключения YFinance WebSocket"""
        try:
            if self.yfinance_websocket_provider:
                await self.yfinance_websocket_provider.stop()
            
            await asyncio.sleep(self.reconnect_delay)
            success = await self._initialize_yfinance_websocket()
            
            if success:
                self.stats["yfinance_reconnects"] += 1
            
            return success
        except Exception as e:
            logger.error(f"❌ Ошибка переподключения YFinance: {e}")
            return False
    
    # ========== ОЧИСТКА И ПЕРИОДИЧЕСКИЕ ЗАДАЧИ ==========
    
    async def _periodic_cleanup_task(self):
        """Периодическая очистка и оптимизация"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(3600)  # Каждый час
                
                stats = self.get_stats()
                logger.info(f"📊 Hourly stats:")
                logger.info(f"   • Bybit WS: {stats['bybit_websocket_updates']}, REST: {stats['bybit_rest_api_calls']}")
                logger.info(f"   • YFinance WS: {stats['yfinance_websocket_updates']}")
                logger.info(f"   • Errors: {stats['errors']}")
                
                # Логируем статистику синхронизации
                if self.candle_sync_service:
                    sync_stats = stats.get('candle_sync', {})
                    logger.info(f"   • Candle Sync: {sync_stats.get('candles_synced', 0)} свечей")
                
                # 🆕 Логируем статистику агрегации
                if self.candle_aggregator:
                    agg_stats = stats.get('candle_aggregator', {})
                    logger.info(f"   • Candle Aggregator: {agg_stats.get('ticks_received', 0)} тиков, "
                              f"{agg_stats.get('candles_created', 0)} свечей создано, "
                              f"{agg_stats.get('candles_saved', 0)} сохранено")
                
                # Очищаем счетчики ошибок
                if self.stats["errors"] > 100:
                    self.stats["errors"] = 10
                
                # Очищаем очереди если переполнены
                for queue_name, queue_obj in [
                    ("Bybit", self._bybit_event_queue),
                    ("YFinance", self._yfinance_event_queue)
                ]:
                    if queue_obj and queue_obj.qsize() > 500:
                        logger.warning(f"🧹 Очищаю переполненную очередь {queue_name}")
                        while not queue_obj.empty():
                            try:
                                queue_obj.get_nowait()
                            except queue.Empty:
                                break
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в задаче очистки: {e}")
    
    # ========== ПОДПИСЧИКИ ==========
    
    def add_data_subscriber(self, callback: Callable[[MarketDataSnapshot], None]):
        """Добавляет подписчика на обновления крипто данных"""
        if callback not in self.data_subscribers:
            self.data_subscribers.append(callback)
            logger.info(f"📝 Добавлен подписчик крипто данных ({len(self.data_subscribers)} всего)")
    
    def remove_data_subscriber(self, callback: Callable[[MarketDataSnapshot], None]):
        """Удаляет подписчика крипто данных"""
        if callback in self.data_subscribers:
            self.data_subscribers.remove(callback)
            logger.info(f"🗑️ Удален подписчик крипто данных")
    
    def add_futures_subscriber(self, callback: Callable[[str, FuturesSnapshot], None]):
        """Добавляет подписчика на обновления фьючерсов"""
        if callback not in self.futures_subscribers:
            self.futures_subscribers.append(callback)
            logger.info(f"📝 Добавлен подписчик фьючерсов ({len(self.futures_subscribers)} всего)")
    
    def remove_futures_subscriber(self, callback: Callable[[str, FuturesSnapshot], None]):
        """Удаляет подписчика фьючерсов"""
        if callback in self.futures_subscribers:
            self.futures_subscribers.remove(callback)
            logger.info(f"🗑️ Удален подписчик фьючерсов")
    
    async def _notify_subscribers_async(self):
        """Уведомление подписчиков крипто данных"""
        try:
            snapshot = await self.get_market_snapshot()
            if snapshot:
                self.last_snapshot = snapshot
                
                for subscriber in self.data_subscribers.copy():
                    try:
                        subscriber(snapshot)
                        self.stats["subscriber_notifications"] += 1
                    except Exception as e:
                        logger.error(f"❌ Ошибка в подписчике крипто: {e}")
                        self.stats["errors"] += 1
                        
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления подписчиков крипто: {e}")
    
    async def _notify_futures_subscribers_async(self, symbol: str):
        """Уведомление подписчиков фьючерсов"""
        try:
            snapshot = await self.get_futures_snapshot(symbol)
            if snapshot:
                self.last_futures_snapshots[symbol] = snapshot
                
                for subscriber in self.futures_subscribers.copy():
                    try:
                        subscriber(symbol, snapshot)
                        self.stats["futures_subscriber_notifications"] += 1
                    except Exception as e:
                        logger.error(f"❌ Ошибка в подписчике фьючерсов {symbol}: {e}")
                        self.stats["errors"] += 1
                        
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления подписчиков фьючерсов {symbol}: {e}")
    
    # ========== ПОЛУЧЕНИЕ ДАННЫХ ==========
    
    async def get_market_snapshot(self, symbol: str = None, force_refresh: bool = False) -> Optional[MarketDataSnapshot]:
        """
        Получает снимок крипто рыночных данных
        
        Args:
            symbol: Крипто символ (по умолчанию первый из списка)
            force_refresh: Принудительно обновить данные из REST API
            
        Returns:
            Снимок рыночных данных или None
        """
        try:
            symbol = symbol or self.symbols_crypto[0]
            websocket_data = None
            rest_data = None
            
            # Получаем данные из Bybit WebSocket
            if self.bybit_websocket_provider and self.bybit_websocket_provider.is_running():
                websocket_stats = self.bybit_websocket_provider.get_current_stats(symbol)
                if websocket_stats.get("has_sufficient_data"):
                    websocket_data = websocket_stats
            
            # Получаем данные из REST API
            if self.rest_api_provider:
                if force_refresh or self._should_refresh_rest_data():
                    try:
                        rest_data = await self.rest_api_provider.get_comprehensive_market_data(symbol)
                        self.cached_rest_data = rest_data
                        self.last_rest_update = datetime.now()
                        self.stats["bybit_rest_api_calls"] += 1
                        self.stats["last_bybit_rest_data"] = datetime.now()
                        self.stats["cache_misses"] += 1
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка REST данных: {e}")
                        if self.cached_rest_data:
                            rest_data = self.cached_rest_data
                            self.stats["cache_hits"] += 1
                elif self.cached_rest_data:
                    rest_data = self.cached_rest_data
                    self.stats["cache_hits"] += 1
            
            # Создаем комбинированный снимок
            snapshot = self._create_market_snapshot(symbol, websocket_data, rest_data)
            
            if snapshot:
                self.stats["data_snapshots_created"] += 1
                
            return snapshot
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания снимка крипто: {e}")
            self.stats["errors"] += 1
            return None
    
    async def get_futures_snapshot(self, symbol: str) -> Optional[FuturesSnapshot]:
        """
        Получает снимок данных фьючерса
        
        Args:
            symbol: Символ фьючерса (MCL, MGC, MES, MNQ)
            
        Returns:
            Снимок данных фьючерса или None
        """
        try:
            if not self.yfinance_websocket_provider or not self.yfinance_websocket_provider.is_running():
                logger.warning(f"⚠️ YFinance WebSocket недоступен для {symbol}")
                return None
            
            futures_data = self.yfinance_websocket_provider.get_futures_data(symbol)
            if not futures_data:
                logger.warning(f"⚠️ Нет данных фьючерса {symbol}")
                return None
            
            snapshot = FuturesSnapshot(
                symbol=symbol,
                timestamp=datetime.now(),
                current_price=futures_data.get_current_price(),
                price_change_1m=futures_data.get_price_change(1),
                price_change_5m=futures_data.get_price_change(5),
                volume=futures_data.get_volume(),
                data_points=len(futures_data.prices),
                data_source=DataSourceType.YFINANCE,
                has_sufficient_data=futures_data.has_sufficient_data()
            )
            
            self.stats["futures_snapshots_created"] += 1
            return snapshot
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания снимка фьючерса {symbol}: {e}")
            self.stats["errors"] += 1
            return None
    
    async def get_all_futures_snapshots(self) -> Dict[str, FuturesSnapshot]:
        """Получает снимки всех фьючерсов"""
        snapshots = {}
        for symbol in self.symbols_futures:
            snapshot = await self.get_futures_snapshot(symbol)
            if snapshot:
                snapshots[symbol] = snapshot
        return snapshots
    
    def _should_refresh_rest_data(self) -> bool:
        """Проверяет, нужно ли обновить REST данные"""
        if not self.last_rest_update:
            return True
        return datetime.now() - self.last_rest_update > self.rest_cache_duration
    
    def _create_market_snapshot(self, symbol: str, websocket_data: Optional[Dict], rest_data: Optional[Dict]) -> Optional[MarketDataSnapshot]:
        """Создает снимок крипто данных"""
        try:
            if not websocket_data and not rest_data:
                return None
            
            current_price = 0
            price_change_1m = 0
            price_change_5m = 0
            data_source = DataSourceType.REST_API
            has_realtime_data = False
            has_historical_data = bool(rest_data)
            
            if websocket_data and websocket_data.get("has_sufficient_data"):
                current_price = websocket_data.get("current_price", 0)
                price_change_1m = websocket_data.get("price_change_1m", 0)
                price_change_5m = websocket_data.get("price_change_5m", 0)
                data_source = DataSourceType.WEBSOCKET if not rest_data else DataSourceType.COMBINED
                has_realtime_data = True
            elif rest_data:
                current_price = rest_data.get("current_price", 0)
                price_change_1m = 0
                price_change_5m = 0
                data_source = DataSourceType.CACHE if self.cached_rest_data == rest_data else DataSourceType.REST_API
            
            if rest_data:
                snapshot = MarketDataSnapshot(
                    symbol=symbol,
                    timestamp=datetime.now(),
                    current_price=current_price,
                    price_change_1m=price_change_1m,
                    price_change_5m=price_change_5m,
                    price_change_24h=rest_data.get("price_change_24h", 0),
                    volume_24h=rest_data.get("volume_24h", 0),
                    high_24h=rest_data.get("high_24h", 0),
                    low_24h=rest_data.get("low_24h", 0),
                    bid_price=rest_data.get("bid_price", 0),
                    ask_price=rest_data.get("ask_price", 0),
                    spread=rest_data.get("spread", 0),
                    open_interest=rest_data.get("open_interest", 0),
                    volume_analysis=rest_data.get("trades_analysis", {}),
                    orderbook_pressure=rest_data.get("orderbook_analysis", {}),
                    trades_analysis=rest_data.get("trades_analysis", {}),
                    hourly_stats=rest_data.get("hourly_stats", {}),
                    data_source=data_source,
                    data_quality=rest_data.get("data_quality", {}),
                    has_realtime_data=has_realtime_data,
                    has_historical_data=has_historical_data
                )
            elif websocket_data:
                snapshot = MarketDataSnapshot(
                    symbol=symbol,
                    timestamp=datetime.now(),
                    current_price=current_price,
                    price_change_1m=price_change_1m,
                    price_change_5m=price_change_5m,
                    price_change_24h=websocket_data.get("price_change_24h", 0),
                    volume_24h=websocket_data.get("volume_24h", 0),
                    high_24h=0,
                    low_24h=0,
                    bid_price=0,
                    ask_price=0,
                    spread=0,
                    open_interest=0,
                    volume_analysis=websocket_data.get("volume_analysis", {}),
                    orderbook_pressure=websocket_data.get("orderbook_pressure", {}),
                    data_source=DataSourceType.WEBSOCKET,
                    has_realtime_data=has_realtime_data,
                    has_historical_data=has_historical_data
                )
            else:
                return None
            
            if websocket_data and rest_data and has_realtime_data:
                ws_volume = websocket_data.get("volume_analysis", {})
                ws_orderbook = websocket_data.get("orderbook_pressure", {})
                
                if ws_volume:
                    snapshot.volume_analysis.update(ws_volume)
                if ws_orderbook:
                    snapshot.orderbook_pressure.update(ws_orderbook)
            
            return snapshot
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания снимка: {e}")
            self.stats["errors"] += 1
            return None
    
    # ========== ДОПОЛНИТЕЛЬНЫЕ МЕТОДЫ ==========
    
    def get_current_price(self, symbol: str = None) -> float:
        """Получает текущую цену крипты"""
        try:
            symbol = symbol or self.symbols_crypto[0]
            if self.bybit_websocket_provider and self.bybit_websocket_provider.is_running():
                return self.bybit_websocket_provider.get_market_data(symbol).get_current_price()
            elif self.cached_rest_data:
                return self.cached_rest_data.get("current_price", 0)
            return 0.0
        except Exception as e:
            logger.error(f"❌ Ошибка получения цены {symbol}: {e}")
            return 0.0
    
    def get_futures_price(self, symbol: str) -> float:
        """Получает текущую цену фьючерса"""
        try:
            if self.yfinance_websocket_provider:
                futures_data = self.yfinance_websocket_provider.get_futures_data(symbol)
                if futures_data:
                    return futures_data.get_current_price()
            return 0.0
        except Exception as e:
            logger.error(f"❌ Ошибка получения цены {symbol}: {e}")
            return 0.0
    
    def get_last_snapshot(self) -> Optional[MarketDataSnapshot]:
        """Получает последний снимок крипто данных"""
        return self.last_snapshot
    
    def get_last_futures_snapshot(self, symbol: str) -> Optional[FuturesSnapshot]:
        """Получает последний снимок фьючерса"""
        return self.last_futures_snapshots.get(symbol)
    
    # ========== СТАТИСТИКА И МОНИТОРИНГ ==========
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает детальную статистику"""
        uptime = datetime.now() - self.stats["start_time"]
        uptime_hours = uptime.total_seconds() / 3600
        
        # Производительность
        bybit_updates_per_hour = self.stats["bybit_websocket_updates"] / uptime_hours if uptime_hours > 0 else 0
        bybit_calls_per_hour = self.stats["bybit_rest_api_calls"] / uptime_hours if uptime_hours > 0 else 0
        yfinance_updates_per_hour = self.stats["yfinance_websocket_updates"] / uptime_hours if uptime_hours > 0 else 0
        
        # Коэффициент успеха
        total_ops = (self.stats["bybit_websocket_updates"] + self.stats["bybit_rest_api_calls"] + 
                    self.stats["yfinance_websocket_updates"] + self.stats["data_snapshots_created"] +
                    self.stats["futures_snapshots_created"])
        success_rate = ((total_ops - self.stats["errors"]) / total_ops * 100) if total_ops > 0 else 100
        
        stats_dict = {
            **self.stats,
            
            # Время работы
            "uptime_seconds": uptime.total_seconds(),
            "uptime_formatted": str(uptime).split('.')[0],
            "uptime_hours": uptime_hours,
            
            # Статус компонентов
            "is_running": self.is_running,
            "initialization_complete": self.initialization_complete,
            "bybit_websocket_active": self.bybit_websocket_provider.is_running() if self.bybit_websocket_provider else False,
            "yfinance_websocket_active": self.yfinance_websocket_provider.is_running() if self.yfinance_websocket_provider else False,
            "rest_api_active": bool(self.rest_api_provider),
            "candle_sync_active": self.candle_sync_service.is_running if self.candle_sync_service else False,
            "candle_aggregator_active": self.candle_aggregator.is_running if self.candle_aggregator else False,  # 🆕
            
            # Подписчики
            "data_subscribers_count": len(self.data_subscribers),
            "futures_subscribers_count": len(self.futures_subscribers),
            
            # Кэш
            "cached_data_available": bool(self.cached_rest_data),
            "cached_data_age_seconds": (datetime.now() - self.last_rest_update).total_seconds() if self.last_rest_update else None,
            "cache_hit_rate": (self.stats["cache_hits"] / (self.stats["cache_hits"] + self.stats["cache_misses"]) * 100) if (self.stats["cache_hits"] + self.stats["cache_misses"]) > 0 else 0,
            
            # Производительность
            "bybit_updates_per_hour": round(bybit_updates_per_hour, 2),
            "bybit_api_calls_per_hour": round(bybit_calls_per_hour, 2),
            "yfinance_updates_per_hour": round(yfinance_updates_per_hour, 2),
            "success_rate_percent": round(success_rate, 2),
            
            # Фоновые задачи
            "background_tasks_count": len(self.background_tasks),
            "background_tasks_active": sum(1 for task in self.background_tasks if not task.done()),
            
            # Очереди
            "bybit_queue_size": self._bybit_event_queue.qsize() if self._bybit_event_queue else 0,
            "yfinance_queue_size": self._yfinance_event_queue.qsize() if self._yfinance_event_queue else 0,
            
            # Переподключения
            "bybit_reconnect_attempts": self.current_bybit_reconnect_attempts,
            "yfinance_reconnect_attempts": self.current_yfinance_reconnect_attempts,
            "max_reconnect_attempts": self.max_reconnect_attempts
        }
        
        # Добавляем статистику синхронизации свечей
        if self.candle_sync_service:
            stats_dict["candle_sync"] = self.candle_sync_service.get_stats()
        
        # 🆕 Добавляем статистику агрегации свечей
        if self.candle_aggregator:
            stats_dict["candle_aggregator"] = self.candle_aggregator.get_stats()
        
        return stats_dict
    
    def get_health_status(self) -> Dict[str, Any]:
        """Возвращает детальный статус здоровья"""
        bybit_ws_status = "active" if (self.bybit_websocket_provider and self.bybit_websocket_provider.is_running()) else "inactive"
        yfinance_ws_status = "active" if (self.yfinance_websocket_provider and self.yfinance_websocket_provider.is_running()) else "inactive"
        rest_api_status = "active" if self.rest_api_provider else "inactive"
        candle_sync_status = "active" if (self.candle_sync_service and self.candle_sync_service.is_running) else "inactive"
        candle_aggregator_status = "active" if (self.candle_aggregator and self.candle_aggregator.is_running) else "inactive"  # 🆕
        
        # Определяем общий статус
        if not self.initialization_complete:
            overall_status = HealthStatus.INITIALIZING
        elif all(status == "inactive" for status in [bybit_ws_status, yfinance_ws_status, rest_api_status]):
            overall_status = HealthStatus.CRITICAL
        elif bybit_ws_status == "inactive" and rest_api_status == "inactive":
            overall_status = HealthStatus.DEGRADED
        elif self.stats["errors"] > 50:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY
        
        # Свежесть данных
        data_freshness = "unknown"
        if self.stats.get("last_bybit_websocket_data"):
            ws_age = (datetime.now() - self.stats["last_bybit_websocket_data"]).total_seconds()
            if ws_age < 60:
                data_freshness = "fresh"
            elif ws_age < 300:
                data_freshness = "stale"
            else:
                data_freshness = "very_stale"
        
        # Свежесть данных YFinance
        yfinance_freshness = "unknown"
        if self.stats.get("last_yfinance_data"):
            yf_age = (datetime.now() - self.stats["last_yfinance_data"]).total_seconds()
            if yf_age < 300:
                yfinance_freshness = "fresh"
            elif yf_age < 600:
                yfinance_freshness = "stale"
            else:
                yfinance_freshness = "very_stale"
        
        return {
            "overall_status": overall_status.value,
            "components": {
                "bybit_websocket": bybit_ws_status,
                "yfinance_websocket": yfinance_ws_status,
                "rest_api": rest_api_status,
                "candle_sync": candle_sync_status,
                "candle_aggregator": candle_aggregator_status,  # 🆕
                "bybit_event_queue": "healthy" if self._bybit_event_queue and self._bybit_event_queue.qsize() < 800 else "degraded",
                "yfinance_event_queue": "healthy" if self._yfinance_event_queue and self._yfinance_event_queue.qsize() < 800 else "degraded",
                "background_tasks": "active" if any(not task.done() for task in self.background_tasks) else "inactive"
            },
            "data_status": {
                "has_crypto_realtime": bool(self.bybit_websocket_provider and self.bybit_websocket_provider.is_running()),
                "has_futures_realtime": bool(self.yfinance_websocket_provider and self.yfinance_websocket_provider.is_running()),
                "has_historical_data": bool(self.cached_rest_data),
                "crypto_freshness": data_freshness,
                "futures_freshness": yfinance_freshness,
                "current_crypto_price": self.get_current_price(),
                "futures_prices": {symbol: self.get_futures_price(symbol) for symbol in self.symbols_futures},
                "last_snapshot_time": self.last_snapshot.timestamp.isoformat() if self.last_snapshot else None
            },
            "performance": {
                "error_count": self.stats["errors"],
                "bybit_callback_errors": self.stats["bybit_callback_errors"],
                "yfinance_callback_errors": self.stats["yfinance_callback_errors"],
                "bybit_reconnect_attempts": self.current_bybit_reconnect_attempts,
                "yfinance_reconnect_attempts": self.current_yfinance_reconnect_attempts,
                "cache_hit_rate": round((self.stats["cache_hits"] / (self.stats["cache_hits"] + self.stats["cache_misses"]) * 100), 2) if (self.stats["cache_hits"] + self.stats["cache_misses"]) > 0 else 0
            },
            "timestamp": datetime.now().isoformat()
        }
    
    # ========== GRACEFUL SHUTDOWN ==========
    
    async def stop(self):
        """Graceful shutdown всех провайдеров"""
        try:
            logger.info("🔄 Начинаю graceful shutdown MarketDataManager...")
            
            self.is_running = False
            self.shutdown_event.set()
            
            # Останавливаем фоновые задачи
            if self.background_tasks:
                logger.info(f"⏹️ Останавливаю {len(self.background_tasks)} фоновых задач...")
                for task in self.background_tasks:
                    if not task.done():
                        task.cancel()
                
                if self.background_tasks:
                    await asyncio.gather(*self.background_tasks, return_exceptions=True)
                    logger.info("✅ Фоновые задачи остановлены")
            
            # 🆕 Останавливаем CandleAggregator
            if self.candle_aggregator:
                logger.info("🏗️ Останавливаю CandleAggregator...")
                try:
                    await self.candle_aggregator.stop()
                    logger.info("✅ CandleAggregator остановлен")
                except Exception as e:
                    logger.error(f"❌ Ошибка остановки CandleAggregator: {e}")
            
            # Останавливаем Bybit WebSocket
            if self.bybit_websocket_provider:
                logger.info("🔌 Останавливаю Bybit WebSocket...")
                await self.bybit_websocket_provider.stop()
                logger.info("✅ Bybit WebSocket остановлен")
            
            # Останавливаем YFinance WebSocket
            if self.yfinance_websocket_provider:
                logger.info("🔌 Останавливаю YFinance WebSocket...")
                await self.yfinance_websocket_provider.stop()
                logger.info("✅ YFinance WebSocket остановлен")
            
            # Останавливаем синхронизацию свечей
            if self.candle_sync_service:
                logger.info("🔄 Останавливаю синхронизацию свечей...")
                await self.candle_sync_service.stop()
                logger.info("✅ Синхронизация свечей остановлена")
            
            # Закрываем REST API
            if self.rest_api_provider:
                logger.info("📡 Закрываю REST API...")
                await self.rest_api_provider.close()
                logger.info("✅ REST API закрыт")
            
            # Очищаем подписчиков
            self.data_subscribers.clear()
            self.futures_subscribers.clear()
            
            # Очищаем очереди
            for queue_name, queue_obj in [
                ("Bybit", self._bybit_event_queue),
                ("YFinance", self._yfinance_event_queue)
            ]:
                if queue_obj:
                    events_cleared = 0
                    while not queue_obj.empty():
                        try:
                            queue_obj.get_nowait()
                            events_cleared += 1
                        except queue.Empty:
                            break
                    if events_cleared > 0:
                        logger.info(f"🧹 Очищено {events_cleared} событий из очереди {queue_name}")
            
            # Очищаем кэш
            self.cached_rest_data = None
            self.last_snapshot = None
            self.last_futures_snapshots.clear()
            self._main_loop = None
            
            # Логируем финальную статистику
            final_stats = self.get_stats()
            logger.info(f"📊 Финальная статистика:")
            logger.info(f"   • Время работы: {final_stats['uptime_formatted']}")
            logger.info(f"   • Bybit WS обновлений: {final_stats['bybit_websocket_updates']}")
            logger.info(f"   • YFinance WS обновлений: {final_stats['yfinance_websocket_updates']}")
            logger.info(f"   • REST API вызовов: {final_stats['bybit_rest_api_calls']}")
            logger.info(f"   • Крипто снимков: {final_stats['data_snapshots_created']}")
            logger.info(f"   • Фьючерс снимков: {final_stats['futures_snapshots_created']}")
            logger.info(f"   • Ошибок: {final_stats['errors']}")
            logger.info(f"   • Успешность: {final_stats['success_rate_percent']:.1f}%")
            
            # Логируем статистику синхронизации
            if 'candle_sync' in final_stats:
                sync_stats = final_stats['candle_sync']
                logger.info(f"   • Пропусков найдено: {sync_stats.get('gaps_found', 0)}")
                logger.info(f"   • Пропусков заполнено: {sync_stats.get('gaps_filled', 0)}")
                logger.info(f"   • Свечей синхронизировано: {sync_stats.get('candles_synced', 0)}")
            
            # 🆕 Логируем статистику агрегации
            if 'candle_aggregator' in final_stats:
                agg_stats = final_stats['candle_aggregator']
                logger.info(f"   • Тиков обработано: {agg_stats.get('ticks_received', 0)}")
                logger.info(f"   • Свечей создано: {agg_stats.get('candles_created', 0)}")
                logger.info(f"   • Свечей сохранено в БД: {agg_stats.get('candles_saved', 0)}")
            
            logger.info("🛑 MarketDataManager успешно остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при остановке MarketDataManager: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
    
    def __str__(self):
        """Строковое представление"""
        status = "Running" if self.is_running else "Stopped"
        
        providers = []
        if self.bybit_websocket_provider and self.bybit_websocket_provider.is_running():
            providers.append("Bybit-WS")
        if self.yfinance_websocket_provider and self.yfinance_websocket_provider.is_running():
            providers.append("YFinance-WS")
        if self.rest_api_provider:
            providers.append("REST")
        if self.candle_sync_service and self.candle_sync_service.is_running:
            providers.append(f"Sync({len(self.symbols_crypto)})")
        if self.candle_aggregator and self.candle_aggregator.is_running:  # 🆕
            providers.append(f"Aggregator({len(self.symbols_crypto)})")
        
        providers_str = "+".join(providers) if providers else "None"
        health = self.get_health_status()["overall_status"]
        
        return f"MarketDataManager(crypto={len(self.symbols_crypto)}, futures={len(self.symbols_futures)}, status={status}, providers=[{providers_str}], health={health})"
    
    def __repr__(self):
        """Подробное представление"""
        stats = self.get_stats()
        return (f"MarketDataManager(crypto_symbols={self.symbols_crypto}, futures_symbols={self.symbols_futures}, "
                f"running={self.is_running}, bybit_ws={stats['bybit_websocket_updates']}, "
                f"yfinance_ws={stats['yfinance_websocket_updates']}, rest={stats['bybit_rest_api_calls']}, "
                f"errors={stats['errors']})")


# Export main components
__all__ = [
    "MarketDataManager",
    "MarketDataSnapshot",
    "FuturesSnapshot",
    "DataSourceType",
    "HealthStatus"
]

logger.info("✅ Market Data Manager module loaded successfully with Multi-Symbol WebSocket + CandleAggregator support")
