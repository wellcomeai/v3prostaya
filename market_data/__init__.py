"""
Модуль для работы с рыночными данными

Предоставляет провайдеры для получения данных из различных источников:
- Bybit WebSocket для криптовалют в реальном времени
- YFinance WebSocket для фьючерсов CME в реальном времени
- REST API для исторических данных
- Менеджер для управления всеми источниками данных
"""

# ========== BYBIT ПРОВАЙДЕРЫ ==========
from .websocket_provider import WebSocketProvider, RealtimeMarketData
from .rest_api_provider import RestApiProvider

# ========== 🆕 YFINANCE ПРОВАЙДЕРЫ ==========
from .yfinance_websocket_provider import (
    YFinanceWebSocketProvider,
    RealtimeFuturesData
)

# ========== МЕНЕДЖЕР И МОДЕЛИ ДАННЫХ ==========
from .market_data_manager import (
    MarketDataManager,
    MarketDataSnapshot,
    FuturesSnapshot,  # 🆕 Снимок данных фьючерса
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
    
    # Менеджер и снимки данных
    "MarketDataManager",
    "MarketDataSnapshot",
    "FuturesSnapshot",  # 🆕 Снимок фьючерса
    
    # Типы и перечисления
    "DataSourceType",
    "HealthStatus",
    
    # Бэктестинг (будущее)
    "CandleData"
]


# ========== ИНФОРМАЦИЯ О МОДУЛЕ ==========
__version__ = "2.0.0"  # 🆕 Версия 2.0 с поддержкой YFinance
__author__ = "Trading Bot Team"
__description__ = "Market data providers for crypto (Bybit) and futures (YFinance)"


# ========== УДОБНЫЕ АЛИАСЫ ==========
# Для обратной совместимости и удобства
BybitWebSocket = WebSocketProvider
YFinanceWebSocket = YFinanceWebSocketProvider
CryptoData = RealtimeMarketData
FuturesData = RealtimeFuturesData
