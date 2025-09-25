"""
Модуль для работы с рыночными данными

Предоставляет провайдеры для получения данных из различных источников:
- WebSocket для данных в реальном времени
- REST API для исторических данных
- Менеджер для управления всеми источниками данных
"""

from .websocket_provider import WebSocketProvider, RealtimeMarketData
from .rest_api_provider import RestApiProvider
from .market_data_manager import MarketDataManager

__all__ = [
    "WebSocketProvider",
    "RealtimeMarketData", 
    "RestApiProvider",
    "MarketDataManager"
]

__version__ = "1.0.0"
