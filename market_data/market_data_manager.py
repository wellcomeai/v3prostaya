import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
from dataclasses import dataclass, field
import traceback

from .websocket_provider import WebSocketProvider, RealtimeMarketData
from .rest_api_provider import RestApiProvider
from config import Config

logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    """Типы источников данных"""
    WEBSOCKET = "websocket"
    REST_API = "rest_api" 
    COMBINED = "combined"
    CACHE = "cache"


class HealthStatus(Enum):
    """Статус здоровья системы"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  
    CRITICAL = "critical"
    INITIALIZING = "initializing"


@dataclass
class MarketDataSnapshot:
    """Снимок рыночных данных"""
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


class MarketDataManager:
    """
    Центральный менеджер для управления всеми источниками рыночных данных
    
    Особенности Production версии:
    - Автоматическое переподключение WebSocket
    - Интеллектуальное кэширование 
    - Детальный мониторинг производительности
    - Graceful shutdown
    - Error recovery
    """
    
    def __init__(self, symbol: str = None, testnet: bool = None, 
                 enable_websocket: bool = True, enable_rest_api: bool = True,
                 rest_cache_minutes: int = 1, websocket_reconnect: bool = True):
        """
        Инициализация менеджера данных
        
        Args:
            symbol: Торговый символ
            testnet: Использовать testnet
            enable_websocket: Включить WebSocket провайдер
            enable_rest_api: Включить REST API провайдер
            rest_cache_minutes: Время кэширования REST данных в минутах
            websocket_reconnect: Включить автоматическое переподключение WebSocket
        """
        self.symbol = symbol or Config.SYMBOL
        self.testnet = testnet if testnet is not None else Config.BYBIT_TESTNET
        
        # Провайдеры данных
        self.websocket_provider: Optional[WebSocketProvider] = None
        self.rest_api_provider: Optional[RestApiProvider] = None
        
        # Настройки
        self.enable_websocket = enable_websocket
        self.enable_rest_api = enable_rest_api
        self.websocket_reconnect = websocket_reconnect
        self.rest_cache_duration = timedelta(minutes=rest_cache_minutes)
        
        # Кэш и состояние данных
        self.last_rest_update: Optional[datetime] = None
        self.cached_rest_data: Optional[Dict[str, Any]] = None
        self.last_snapshot: Optional[MarketDataSnapshot] = None
        
        # Подписчики на обновления данных
        self.data_subscribers: List[Callable[[MarketDataSnapshot], None]] = []
        
        # Управление жизненным циклом
        self.is_running = False
        self.initialization_complete = False
        self.shutdown_event = asyncio.Event()
        
        # Задачи фонового выполнения
        self.background_tasks: List[asyncio.Task] = []
        
        # Статистика и мониторинг
        self.stats = {
            "websocket_updates": 0,
            "rest_api_calls": 0,
            "data_snapshots_created": 0,
            "errors": 0,
            "websocket_reconnects": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "subscriber_notifications": 0,
            "start_time": datetime.now(),
            "last_error": None,
            "last_websocket_data": None,
            "last_rest_data": None
        }
        
        # Конфигурация переподключения
        self.reconnect_delay = 5  # секунд
        self.max_reconnect_attempts = 10
        self.current_reconnect_attempts = 0
        
        logger.info(f"🏗️ MarketDataManager инициализирован для {self.symbol}")
    
    async def start(self) -> bool:
        """
        Запуск всех провайдеров данных
        
        Returns:
            True если хотя бы один провайдер запущен успешно
        """
        try:
            logger.info(f"🚀 Запуск MarketDataManager для {self.symbol}")
            self.stats["start_time"] = datetime.now()
            
            providers_started = 0
            initialization_errors = []
            
            # Инициализируем REST API провайдер
            if self.enable_rest_api:
                try:
                    logger.info("📡 Инициализация REST API провайдера...")
                    self.rest_api_provider = RestApiProvider(testnet=self.testnet)
                    
                    # Проверяем подключение с таймаутом
                    connection_task = asyncio.create_task(self.rest_api_provider.check_connection())
                    connection_ok = await asyncio.wait_for(connection_task, timeout=10)
                    
                    if connection_ok:
                        providers_started += 1
                        logger.info("✅ REST API провайдер готов")
                        
                        # Получаем начальные данные
                        await self._initialize_rest_data()
                    else:
                        initialization_errors.append("REST API connection failed")
                        logger.warning("⚠️ REST API провайдер недоступен")
                        
                except asyncio.TimeoutError:
                    initialization_errors.append("REST API connection timeout")
                    logger.error("❌ Таймаут подключения к REST API")
                except Exception as e:
                    initialization_errors.append(f"REST API error: {str(e)}")
                    logger.error(f"❌ Ошибка инициализации REST API провайдера: {e}")
                    self.stats["errors"] += 1
                    self.stats["last_error"] = str(e)
            
            # Инициализируем WebSocket провайдер
            if self.enable_websocket:
                websocket_started = await self._initialize_websocket()
                if websocket_started:
                    providers_started += 1
                else:
                    initialization_errors.append("WebSocket initialization failed")
            
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
            initial_snapshot = await self.get_market_snapshot()
            if initial_snapshot:
                logger.info(f"📊 Начальные данные получены: ${initial_snapshot.current_price:,.2f}")
                self.last_snapshot = initial_snapshot
            
            logger.info(f"✅ MarketDataManager запущен успешно!")
            logger.info(f"📈 Провайдеров активно: {providers_started}")
            logger.info(f"🔌 WebSocket: {'✅' if self.websocket_provider and self.websocket_provider.is_running() else '❌'}")
            logger.info(f"📡 REST API: {'✅' if self.rest_api_provider else '❌'}")
            
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
            logger.info("📥 Получение начальных REST данных...")
            self.cached_rest_data = await self.rest_api_provider.get_comprehensive_market_data(self.symbol)
            self.last_rest_update = datetime.now()
            self.stats["rest_api_calls"] += 1
            self.stats["last_rest_data"] = datetime.now()
            logger.info("✅ Начальные REST данные получены")
        except Exception as e:
            logger.error(f"❌ Ошибка получения начальных REST данных: {e}")
            raise
    
    async def _initialize_websocket(self) -> bool:
        """Инициализация WebSocket провайдера"""
        try:
            logger.info("🔌 Инициализация WebSocket провайдера...")
            self.websocket_provider = WebSocketProvider(
                symbol=self.symbol, 
                testnet=self.testnet
            )
            
            # Подписываемся на обновления
            self.websocket_provider.add_ticker_callback(self._on_websocket_ticker_update)
            self.websocket_provider.add_orderbook_callback(self._on_websocket_orderbook_update)
            self.websocket_provider.add_trades_callback(self._on_websocket_trades_update)
            
            # Запускаем WebSocket с таймаутом
            start_task = asyncio.create_task(self.websocket_provider.start())
            await asyncio.wait_for(start_task, timeout=15)
            
            # Ждем получения данных
            logger.info("⏳ Ожидание WebSocket данных...")
            data_received = await self.websocket_provider.wait_for_data(timeout=20)
            
            if data_received:
                self.current_reconnect_attempts = 0  # Сбрасываем счетчик попыток
                logger.info("✅ WebSocket провайдер готов")
                return True
            else:
                logger.warning("⚠️ WebSocket данные не получены в течение таймаута")
                return False
                
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут инициализации WebSocket")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации WebSocket провайдера: {e}")
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return False
    
    async def _start_background_tasks(self):
        """Запуск фоновых задач"""
        try:
            # Задача мониторинга WebSocket соединения
            if self.websocket_reconnect and self.websocket_provider:
                monitor_task = asyncio.create_task(self._websocket_monitor_task())
                self.background_tasks.append(monitor_task)
                logger.info("🔍 Запущен мониторинг WebSocket соединения")
            
            # Задача периодической очистки статистики (каждый час)
            cleanup_task = asyncio.create_task(self._periodic_cleanup_task())
            self.background_tasks.append(cleanup_task)
            logger.info("🧹 Запущена задача очистки статистики")
            
            logger.info(f"🔄 Запущено {len(self.background_tasks)} фоновых задач")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска фоновых задач: {e}")
    
    async def _websocket_monitor_task(self):
        """Фоновая задача мониторинга WebSocket соединения"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(30)  # Проверяем каждые 30 секунд
                
                if not self.websocket_provider or not self.websocket_provider.is_running():
                    logger.warning("⚠️ WebSocket соединение потеряно, попытка переподключения...")
                    
                    if self.current_reconnect_attempts < self.max_reconnect_attempts:
                        success = await self._attempt_websocket_reconnect()
                        if success:
                            logger.info("✅ WebSocket переподключен успешно")
                            self.current_reconnect_attempts = 0
                        else:
                            self.current_reconnect_attempts += 1
                            logger.warning(f"⚠️ Попытка переподключения {self.current_reconnect_attempts}/{self.max_reconnect_attempts} неуспешна")
                    else:
                        logger.error("💥 Превышено максимальное количество попыток переподключения WebSocket")
                        
            except asyncio.CancelledError:
                logger.info("🔄 Задача мониторинга WebSocket отменена")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в задаче мониторинга WebSocket: {e}")
                self.stats["errors"] += 1
    
    async def _attempt_websocket_reconnect(self) -> bool:
        """Попытка переподключения WebSocket"""
        try:
            # Останавливаем старое соединение
            if self.websocket_provider:
                await self.websocket_provider.stop()
            
            # Ждем перед переподключением
            await asyncio.sleep(self.reconnect_delay)
            
            # Пытаемся переподключиться
            success = await self._initialize_websocket()
            
            if success:
                self.stats["websocket_reconnects"] += 1
                logger.info("🔄 WebSocket переподключение успешно")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Ошибка переподключения WebSocket: {e}")
            return False
    
    async def _periodic_cleanup_task(self):
        """Периодическая очистка и оптимизация"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(3600)  # Каждый час
                
                # Логируем статистику
                stats = self.get_stats()
                logger.info(f"📊 Hourly stats: {stats['websocket_updates']} WS updates, "
                           f"{stats['rest_api_calls']} REST calls, {stats['errors']} errors")
                
                # Очищаем старые ошибки (оставляем только последние 10)
                if self.stats["errors"] > 100:
                    logger.info("🧹 Сброс счетчика ошибок для оптимизации памяти")
                    self.stats["errors"] = 10
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в задаче очистки: {e}")
    
    def _on_websocket_ticker_update(self, ticker_data: dict):
        """Callback для обновлений тикера от WebSocket"""
        try:
            self.stats["websocket_updates"] += 1
            self.stats["last_websocket_data"] = datetime.now()
            
            # Создаем снимок данных для подписчиков (асинхронно)
            if self.data_subscribers:
                asyncio.create_task(self._notify_subscribers_async())
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки WebSocket ticker: {e}")
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
    
    def _on_websocket_orderbook_update(self, orderbook_data: dict):
        """Callback для обновлений ордербука от WebSocket"""
        try:
            # При необходимости можно добавить специфичную логику
            pass
        except Exception as e:
            logger.error(f"❌ Ошибка обработки WebSocket orderbook: {e}")
            self.stats["errors"] += 1
    
    def _on_websocket_trades_update(self, trades_data: list):
        """Callback для обновлений трейдов от WebSocket"""
        try:
            # При необходимости можно добавить специфичную логику
            pass
        except Exception as e:
            logger.error(f"❌ Ошибка обработки WebSocket trades: {e}")
            self.stats["errors"] += 1
    
    async def _notify_subscribers_async(self):
        """Асинхронное уведомление подписчиков о новых данных"""
        try:
            snapshot = await self.get_market_snapshot()
            if snapshot:
                self.last_snapshot = snapshot
                
                # Уведомляем подписчиков
                for subscriber in self.data_subscribers.copy():  # Копируем для безопасности
                    try:
                        subscriber(snapshot)
                        self.stats["subscriber_notifications"] += 1
                    except Exception as e:
                        logger.error(f"❌ Ошибка в подписчике данных: {e}")
                        self.stats["errors"] += 1
                        
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления подписчиков: {e}")
            self.stats["errors"] += 1
    
    def add_data_subscriber(self, callback: Callable[[MarketDataSnapshot], None]):
        """
        Добавляет подписчика на обновления данных
        
        Args:
            callback: Функция для обработки обновлений данных
        """
        if callback not in self.data_subscribers:
            self.data_subscribers.append(callback)
            logger.info(f"📝 Добавлен подписчик данных ({len(self.data_subscribers)} всего)")
        else:
            logger.warning("⚠️ Подписчик уже существует")
    
    def remove_data_subscriber(self, callback: Callable[[MarketDataSnapshot], None]):
        """Удаляет подписчика на обновления данных"""
        if callback in self.data_subscribers:
            self.data_subscribers.remove(callback)
            logger.info(f"🗑️ Удален подписчик данных ({len(self.data_subscribers)} осталось)")
        else:
            logger.warning("⚠️ Подписчик не найден для удаления")
    
    async def get_market_snapshot(self, force_refresh: bool = False) -> Optional[MarketDataSnapshot]:
        """
        Получает текущий снимок рыночных данных
        
        Args:
            force_refresh: Принудительно обновить данные из REST API
            
        Returns:
            Снимок рыночных данных или None при ошибке
        """
        try:
            websocket_data = None
            rest_data = None
            
            # Получаем данные из WebSocket (приоритетные для реального времени)
            if self.websocket_provider and self.websocket_provider.is_running():
                websocket_stats = self.websocket_provider.get_current_stats()
                if websocket_stats["has_sufficient_data"]:
                    websocket_data = websocket_stats
            
            # Получаем данные из REST API (для дополнения или fallback)
            if self.rest_api_provider:
                if force_refresh or self._should_refresh_rest_data():
                    try:
                        rest_data = await self.rest_api_provider.get_comprehensive_market_data(self.symbol)
                        self.cached_rest_data = rest_data
                        self.last_rest_update = datetime.now()
                        self.stats["rest_api_calls"] += 1
                        self.stats["last_rest_data"] = datetime.now()
                        self.stats["cache_misses"] += 1
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка получения REST данных: {e}")
                        # Используем кэшированные данные если есть
                        if self.cached_rest_data:
                            rest_data = self.cached_rest_data
                            self.stats["cache_hits"] += 1
                elif self.cached_rest_data:
                    rest_data = self.cached_rest_data
                    self.stats["cache_hits"] += 1
            
            # Создаем комбинированный снимок
            snapshot = self._create_market_snapshot(websocket_data, rest_data)
            
            if snapshot:
                self.stats["data_snapshots_created"] += 1
                
            return snapshot
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания снимка рыночных данных: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return None
    
    def _should_refresh_rest_data(self) -> bool:
        """Проверяет, нужно ли обновить REST данные"""
        if not self.last_rest_update:
            return True
        return datetime.now() - self.last_rest_update > self.rest_cache_duration
    
    def _create_market_snapshot(self, websocket_data: Optional[Dict], rest_data: Optional[Dict]) -> Optional[MarketDataSnapshot]:
        """
        Создает снимок рыночных данных из доступных источников
        
        Args:
            websocket_data: Данные от WebSocket провайдера
            rest_data: Данные от REST API провайдера
            
        Returns:
            Снимок рыночных данных
        """
        try:
            if not websocket_data and not rest_data:
                logger.warning("⚠️ Нет данных для создания снимка")
                return None
            
            # Определяем приоритетный источник данных
            current_price = 0
            price_change_1m = 0
            price_change_5m = 0
            data_source = DataSourceType.REST_API
            has_realtime_data = False
            has_historical_data = bool(rest_data)
            
            # WebSocket данные имеют приоритет для реального времени
            if websocket_data and websocket_data.get("has_sufficient_data"):
                current_price = websocket_data.get("current_price", 0)
                price_change_1m = websocket_data.get("price_change_1m", 0)
                price_change_5m = websocket_data.get("price_change_5m", 0)
                data_source = DataSourceType.WEBSOCKET if not rest_data else DataSourceType.COMBINED
                has_realtime_data = True
            elif rest_data:
                # Fallback на REST данные
                current_price = rest_data.get("current_price", 0)
                # REST API не предоставляет изменения за короткие периоды
                price_change_1m = 0
                price_change_5m = 0
                data_source = DataSourceType.CACHE if self.cached_rest_data == rest_data else DataSourceType.REST_API
            
            # Создаем снимок на основе доступных данных
            if rest_data:
                # Полный снимок с REST данными
                snapshot = MarketDataSnapshot(
                    symbol=self.symbol,
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
                # Снимок только из WebSocket данных (ограниченные данные)
                snapshot = MarketDataSnapshot(
                    symbol=self.symbol,
                    timestamp=datetime.now(),
                    current_price=current_price,
                    price_change_1m=price_change_1m,
                    price_change_5m=price_change_5m,
                    price_change_24h=websocket_data.get("price_change_24h", 0),
                    volume_24h=websocket_data.get("volume_24h", 0),
                    high_24h=0,  # WebSocket не предоставляет детальные исторические данные
                    low_24h=0,
                    bid_price=0,  # Можно добавить из ордербука в будущем
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
            
            # Дополняем WebSocket данными если они доступны и мы используем комбинированный источник
            if websocket_data and rest_data and has_realtime_data:
                # Обновляем анализы более свежими данными из WebSocket
                ws_volume_analysis = websocket_data.get("volume_analysis", {})
                ws_orderbook_pressure = websocket_data.get("orderbook_pressure", {})
                
                if ws_volume_analysis:
                    snapshot.volume_analysis.update(ws_volume_analysis)
                if ws_orderbook_pressure:
                    snapshot.orderbook_pressure.update(ws_orderbook_pressure)
            
            return snapshot
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания снимка данных: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return None
    
    async def get_price_change(self, minutes: int) -> float:
        """
        Получает изменение цены за указанный период
        
        Args:
            minutes: Период в минутах
            
        Returns:
            Изменение цены в процентах
        """
        try:
            if self.websocket_provider and self.websocket_provider.is_running():
                return self.websocket_provider.get_market_data().get_price_change(minutes)
            return 0.0
        except Exception as e:
            logger.error(f"❌ Ошибка получения изменения цены: {e}")
            self.stats["errors"] += 1
            return 0.0
    
    def get_current_price(self) -> float:
        """Получает текущую цену"""
        try:
            if self.websocket_provider and self.websocket_provider.is_running():
                return self.websocket_provider.get_market_data().get_current_price()
            elif self.cached_rest_data:
                return self.cached_rest_data.get("current_price", 0)
            return 0.0
        except Exception as e:
            logger.error(f"❌ Ошибка получения текущей цены: {e}")
            self.stats["errors"] += 1
            return 0.0
    
    def get_realtime_data(self) -> Optional[RealtimeMarketData]:
        """Получает объект с данными реального времени"""
        if self.websocket_provider and self.websocket_provider.is_running():
            return self.websocket_provider.get_market_data()
        return None
    
    def get_last_snapshot(self) -> Optional[MarketDataSnapshot]:
        """Получает последний созданный снимок данных"""
        return self.last_snapshot
    
    async def refresh_rest_data(self) -> bool:
        """
        Принудительно обновляет данные из REST API
        
        Returns:
            True если данные обновлены успешно
        """
        try:
            if not self.rest_api_provider:
                logger.warning("⚠️ REST API провайдер недоступен")
                return False
            
            logger.info("🔄 Принудительное обновление REST данных...")
            self.cached_rest_data = await self.rest_api_provider.get_comprehensive_market_data(self.symbol)
            self.last_rest_update = datetime.now()
            self.stats["rest_api_calls"] += 1
            self.stats["last_rest_data"] = datetime.now()
            
            logger.info("✅ REST данные принудительно обновлены")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления REST данных: {e}")
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает детальную статистику работы менеджера"""
        uptime = datetime.now() - self.stats["start_time"]
        
        # Вычисляем производительность
        uptime_hours = uptime.total_seconds() / 3600
        updates_per_hour = self.stats["websocket_updates"] / uptime_hours if uptime_hours > 0 else 0
        api_calls_per_hour = self.stats["rest_api_calls"] / uptime_hours if uptime_hours > 0 else 0
        
        # Коэффициент успеха
        total_operations = self.stats["websocket_updates"] + self.stats["rest_api_calls"] + self.stats["data_snapshots_created"]
        success_rate = ((total_operations - self.stats["errors"]) / total_operations * 100) if total_operations > 0 else 100
        
        return {
            # Базовая статистика
            **self.stats,
            
            # Время работы
            "uptime_seconds": uptime.total_seconds(),
            "uptime_formatted": str(uptime).split('.')[0],
            "uptime_hours": uptime_hours,
            
            # Статус компонентов
            "is_running": self.is_running,
            "initialization_complete": self.initialization_complete,
            "websocket_active": self.websocket_provider.is_running() if self.websocket_provider else False,
            "rest_api_active": bool(self.rest_api_provider),
            
            # Подписчики
            "data_subscribers_count": len(self.data_subscribers),
            
            # Кэш
            "cached_data_available": bool(self.cached_rest_data),
            "cached_data_age_seconds": (datetime.now() - self.last_rest_update).total_seconds() if self.last_rest_update else None,
            "cache_hit_rate": (self.stats["cache_hits"] / (self.stats["cache_hits"] + self.stats["cache_misses"]) * 100) if (self.stats["cache_hits"] + self.stats["cache_misses"]) > 0 else 0,
            
            # Производительность
            "updates_per_hour": round(updates_per_hour, 2),
            "api_calls_per_hour": round(api_calls_per_hour, 2),
            "success_rate_percent": round(success_rate, 2),
            
            # Фоновые задачи
            "background_tasks_count": len(self.background_tasks),
            "background_tasks_active": sum(1 for task in self.background_tasks if not task.done()),
            
            # Переподключения
            "reconnect_attempts_current": self.current_reconnect_attempts,
            "reconnect_attempts_max": self.max_reconnect_attempts
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Возвращает детальный статус здоровья системы"""
        websocket_status = "active" if (self.websocket_provider and self.websocket_provider.is_running()) else "inactive"
        rest_api_status = "active" if self.rest_api_provider else "inactive"
        
        # Определяем общий статус здоровья
        if not self.initialization_complete:
            overall_status = HealthStatus.INITIALIZING
        elif websocket_status == "inactive" and rest_api_status == "inactive":
            overall_status = HealthStatus.CRITICAL
        elif websocket_status == "inactive" or rest_api_status == "inactive":
            overall_status = HealthStatus.DEGRADED
        elif self.stats["errors"] > 50:  # Много ошибок
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY
        
        # Проверяем свежесть данных
        data_freshness = "unknown"
        if self.stats.get("last_websocket_data"):
            ws_age = (datetime.now() - self.stats["last_websocket_data"]).total_seconds()
            if ws_age < 60:
                data_freshness = "fresh"
            elif ws_age < 300:
                data_freshness = "stale"
            else:
                data_freshness = "very_stale"
        
        return {
            "overall_status": overall_status.value,
            "components": {
                "websocket_provider": websocket_status,
                "rest_api_provider": rest_api_status,
                "background_tasks": "active" if any(not task.done() for task in self.background_tasks) else "inactive"
            },
            "data_status": {
                "has_realtime_data": bool(self.websocket_provider and self.websocket_provider.is_running()),
                "has_historical_data": bool(self.cached_rest_data),
                "data_freshness": data_freshness,
                "current_price": self.get_current_price(),
                "last_snapshot_time": self.last_snapshot.timestamp.isoformat() if self.last_snapshot else None
            },
            "performance": {
                "error_count": self.stats["errors"],
                "reconnect_attempts": self.current_reconnect_attempts,
                "cache_hit_rate": round((self.stats["cache_hits"] / (self.stats["cache_hits"] + self.stats["cache_misses"]) * 100), 2) if (self.stats["cache_hits"] + self.stats["cache_misses"]) > 0 else 0
            },
            "timestamp": datetime.now().isoformat()
        }
    
    async def stop(self):
        """Graceful shutdown всех провайдеров данных"""
        try:
            logger.info("🔄 Начинаю graceful shutdown MarketDataManager...")
            
            # Устанавливаем флаг остановки
            self.is_running = False
            self.shutdown_event.set()
            
            # Останавливаем фоновые задачи
            if self.background_tasks:
                logger.info(f"⏹️ Останавливаю {len(self.background_tasks)} фоновых задач...")
                for task in self.background_tasks:
                    if not task.done():
                        task.cancel()
                
                # Ждем завершения задач
                if self.background_tasks:
                    await asyncio.gather(*self.background_tasks, return_exceptions=True)
                    logger.info("✅ Фоновые задачи остановлены")
            
            # Останавливаем WebSocket провайдер
            if self.websocket_provider:
                logger.info("🔌 Останавливаю WebSocket провайдер...")
                await self.websocket_provider.stop()
                logger.info("✅ WebSocket провайдер остановлен")
            
            # Закрываем REST API провайдер
            if self.rest_api_provider:
                logger.info("📡 Закрываю REST API провайдер...")
                await self.rest_api_provider.close()
                logger.info("✅ REST API провайдер закрыт")
            
            # Очищаем подписчиков
            subscribers_count = len(self.data_subscribers)
            self.data_subscribers.clear()
            if subscribers_count > 0:
                logger.info(f"🧹 Очищено {subscribers_count} подписчиков")
            
            # Очищаем кэш
            self.cached_rest_data = None
            self.last_snapshot = None
            
            # Логируем финальную статистику
            final_stats = self.get_stats()
            logger.info(f"📊 Финальная статистика:")
            logger.info(f"   • Время работы: {final_stats['uptime_formatted']}")
            logger.info(f"   • WebSocket обновлений: {final_stats['websocket_updates']}")
            logger.info(f"   • REST API вызовов: {final_stats['rest_api_calls']}")
            logger.info(f"   • Снимков данных создано: {final_stats['data_snapshots_created']}")
            logger.info(f"   • Ошибок: {final_stats['errors']}")
            logger.info(f"   • Успешность: {final_stats['success_rate_percent']:.1f}%")
            
            logger.info("🛑 MarketDataManager успешно остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при остановке MarketDataManager: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
    
    def __str__(self):
        """Строковое представление менеджера"""
        status = "Running" if self.is_running else "Stopped"
        
        providers = []
        if self.websocket_provider and self.websocket_provider.is_running():
            providers.append("WebSocket")
        if self.rest_api_provider:
            providers.append("REST")
        
        providers_str = "+".join(providers) if providers else "None"
        health = self.get_health_status()["overall_status"]
        
        return f"MarketDataManager(symbol={self.symbol}, status={status}, providers=[{providers_str}], health={health})"
    
    def __repr__(self):
        """Подробное представление для отладки"""
        stats = self.get_stats()
        return (f"MarketDataManager(symbol='{self.symbol}', testnet={self.testnet}, "
                f"running={self.is_running}, ws_updates={stats['websocket_updates']}, "
                f"rest_calls={stats['rest_api_calls']}, errors={stats['errors']})")
