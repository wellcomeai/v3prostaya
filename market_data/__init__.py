"""
Модуль для работы с рыночными данными

Предоставляет провайдеры для получения данных из различных источников:
- Bybit WebSocket для криптовалют в реальном времени
- YFinance WebSocket для фьючерсов CME в реальном времени
- REST API для исторических данных
- Менеджер для управления всеми источниками данных
- Агрегатор свечей для сохранения WebSocket данных в БД
- Сервис синхронизации исторических свечей
"""

# ========== BYBIT ПРОВАЙДЕРЫ ==========
from .websocket_provider import WebSocketProvider, RealtimeMarketData
from .rest_api_provider import RestApiProvider

# ========== 🆕 YFINANCE ПРОВАЙДЕРЫ ==========
from .yfinance_websocket_provider import (
    YFinanceWebSocketProvider,
    RealtimeFuturesData
)

# ========== 🆕 CANDLE ОБРАБОТКА ==========
from .candle_aggregator import CandleAggregator, CandleBuilder
from .candle_sync_service import CandleSyncService, SyncConfig

# ========== МЕНЕДЖЕР И МОДЕЛИ ДАННЫХ ==========
from .market_data_manager import (
    MarketDataManager,
    MarketDataSnapshot,
    FuturesSnapshot,
    DataSourceType,
    HealthStatus
)

# ========== ТИПЫ ДЛЯ БЭКТЕСТИНГА (ЗАГЛУШКИ) ==========
try:
    from .data_models import CandleData
except ImportError:
    # Если data_models не существует, создаем заглушку
    class CandleData:
        """Заглушка для CandleData (для будущего бэктестинга)"""
        pass


__all__ = [
    # Bybit провайдеры
    "WebSocketProvider",
    "RealtimeMarketData",
    "RestApiProvider",
    
    # 🆕 YFinance провайдеры
    "YFinanceWebSocketProvider",
    "RealtimeFuturesData",
    
    # 🆕 Candle обработка
    "CandleAggregator",
    "CandleBuilder",
    "CandleSyncService", 
    "SyncConfig",
    
    # Менеджер и снимки данных
    "MarketDataManager",
    "MarketDataSnapshot",
    "FuturesSnapshot",
    
    # Типы и перечисления
    "DataSourceType",
    "HealthStatus",
    
    # Бэктестинг (будущее)
    "CandleData"
]


# ========== ИНФОРМАЦИЯ О МОДУЛЕ ==========
__version__ = "2.1.0"  # 🆕 Версия 2.1 с CandleAggregator + CandleSync
__author__ = "Trading Bot Team"
__description__ = "Market data providers with real-time aggregation and historical sync"


# ========== УДОБНЫЕ АЛИАСЫ ==========
# Для обратной совместимости и удобства
BybitWebSocket = WebSocketProvider
YFinanceWebSocket = YFinanceWebSocketProvider
CryptoData = RealtimeMarketData
FuturesData = RealtimeFuturesData
