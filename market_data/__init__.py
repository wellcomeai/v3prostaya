"""
Модуль для работы с рыночными данными

Предоставляет надежную синхронизацию свечей через REST API:
- SimpleCandleSync: Синхронизация криптовалютных свечей (Bybit REST)
- SimpleFuturesSync: Синхронизация фьючерсных свечей (YFinance REST)
- MarketDataManager: Опциональный WebSocket ticker для real-time цен
- RestApiProvider: Для получения рыночных данных (legacy support)
- DataQuality: Оценка качества рыночных данных

Version 3.0.0 - SimpleCandleSync + SimpleFuturesSync Architecture
"""

from dataclasses import dataclass
from datetime import datetime

# ========== 🆕 DATA QUALITY ==========
@dataclass
class DataQuality:
    """
    Оценка качества рыночных данных
    
    Attributes:
        bybit_rest_api: REST API доступен и данные свежие
        bybit_websocket: WebSocket подключен
        yfinance_websocket: YFinance WebSocket подключен
        overall_quality: Общая оценка (excellent/good/fair/poor)
        data_completeness: Полнота данных 0.0-1.0
        last_update: Время последнего обновления
    """
    bybit_rest_api: bool = False
    bybit_websocket: bool = False
    yfinance_websocket: bool = False
    overall_quality: str = "poor"  # excellent | good | fair | poor
    data_completeness: float = 0.0  # 0.0 - 1.0
    last_update: datetime = None
    
    def is_good_quality(self) -> bool:
        """Данные хорошего качества?"""
        return self.overall_quality in ["excellent", "good"]
    
    def is_realtime(self) -> bool:
        """Есть real-time данные?"""
        return self.bybit_websocket or self.yfinance_websocket


# ========== 🚀 ОСНОВНЫЕ СИНХРОНИЗАТОРЫ ==========
from .simple_candle_sync import SimpleCandleSync
from .simple_futures_sync import SimpleFuturesSync

# ========== 📊 REST API ПРОВАЙДЕР (для telegram_bot) ==========
try:
    from .rest_api_provider import RestApiProvider
except ImportError:
    RestApiProvider = None

# ========== 📊 ОПЦИОНАЛЬНЫЙ WEBSOCKET (только ticker) ==========
try:
    from .market_data_manager import (
        MarketDataManager,
        MarketDataSnapshot,
        FuturesSnapshot,
        DataSourceType,
        HealthStatus
    )
except ImportError:
    MarketDataManager = None
    MarketDataSnapshot = None
    FuturesSnapshot = None
    DataSourceType = None
    HealthStatus = None

# ========== ТИПЫ ДЛЯ БЭКТЕСТИНГА (ЗАГЛУШКИ) ==========
try:
    from .data_models import CandleData
except ImportError:
    class CandleData:
        """Заглушка для CandleData (для будущего бэктестинга)"""
        pass


__all__ = [
    # 🚀 Основные синхронизаторы (REST API)
    "SimpleCandleSync",      # Криптовалюты (Bybit)
    "SimpleFuturesSync",     # Фьючерсы (YFinance)
    
    # 📡 REST API провайдер (legacy support для telegram_bot)
    "RestApiProvider",
    
    # 📊 Опциональный WebSocket ticker
    "MarketDataManager",
    "MarketDataSnapshot",
    "FuturesSnapshot",
    "DataSourceType",
    "HealthStatus",
    
    # 📈 Качество данных
    "DataQuality",  # 🆕 ДОБАВЛЕНО
    
    # Бэктестинг (будущее)
    "CandleData"
]


# ========== ИНФОРМАЦИЯ О МОДУЛЕ ==========
__version__ = "3.0.0"
__author__ = "Trading Bot Team"
__description__ = "Reliable candle synchronization via REST API for crypto and futures"


# ========== УДОБНЫЕ АЛИАСЫ ==========
CryptoSync = SimpleCandleSync
FuturesSync = SimpleFuturesSync
