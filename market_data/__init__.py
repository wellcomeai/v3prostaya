"""
Модуль для работы с рыночными данными

Предоставляет надежную синхронизацию свечей через REST API:
- SimpleCandleSync: Синхронизация криптовалютных свечей (Bybit REST)
- SimpleFuturesSync: Синхронизация фьючерсных свечей (YFinance REST)
- MarketDataManager: Опциональный WebSocket ticker для real-time цен

Version 3.0.0 - SimpleCandleSync + SimpleFuturesSync Architecture
"""

# ========== 🚀 ОСНОВНЫЕ СИНХРОНИЗАТОРЫ ==========
from .simple_candle_sync import SimpleCandleSync
from .simple_futures_sync import SimpleFuturesSync  # 🆕 ДОБАВЛЕНО

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
    # Если MarketDataManager не нужен, создаем заглушки
    MarketDataManager = None
    MarketDataSnapshot = None
    FuturesSnapshot = None
    DataSourceType = None
    HealthStatus = None

# ========== ТИПЫ ДЛЯ БЭКТЕСТИНГА (ЗАГЛУШКИ) ==========
try:
    from .data_models import CandleData
except ImportError:
    # Если data_models не существует, создаем заглушку
    class CandleData:
        """Заглушка для CandleData (для будущего бэктестинга)"""
        pass


__all__ = [
    # 🚀 Основные синхронизаторы (REST API)
    "SimpleCandleSync",      # Криптовалюты (Bybit)
    "SimpleFuturesSync",     # Фьючерсы (YFinance) 🆕
    
    # 📊 Опциональный WebSocket ticker
    "MarketDataManager",     # Только для real-time цен (опционально)
    "MarketDataSnapshot",
    "FuturesSnapshot",
    "DataSourceType",
    "HealthStatus",
    
    # Бэктестинг (будущее)
    "CandleData"
]


# ========== ИНФОРМАЦИЯ О МОДУЛЕ ==========
__version__ = "3.0.0"  # 🆕 Версия 3.0 - SimpleCandleSync + SimpleFuturesSync
__author__ = "Trading Bot Team"
__description__ = "Reliable candle synchronization via REST API for crypto and futures"


# ========== УДОБНЫЕ АЛИАСЫ ==========
# Для обратной совместимости
CryptoSync = SimpleCandleSync
FuturesSync = SimpleFuturesSync
