"""
Модуль торговых стратегий

Содержит различные торговые стратегии для анализа рыночных данных
и генерации торговых сигналов.

Архитектура:
- BaseStrategy: Абстрактный базовый класс для всех стратегий
- MomentumStrategy: Импульсная торговая стратегия
- TechnicalStrategy: Технический анализ (RSI, MACD, Bollinger Bands)
- SentimentStrategy: Анализ настроений рынка
- MLStrategy: Стратегии машинного обучения (будущая функциональность)
"""

from .base_strategy import BaseStrategy, TradingSignal, SignalType, SignalStrength
from .momentum_strategy import MomentumStrategy
# from .technical_strategy import TechnicalStrategy
# from .sentiment_strategy import SentimentStrategy

__all__ = [
    "BaseStrategy",
    "TradingSignal",
    "SignalType", 
    "SignalStrength",
    "MomentumStrategy",
    # "TechnicalStrategy", 
    # "SentimentStrategy",
    "get_available_strategies",
    "create_strategy"
]

__version__ = "1.0.0"

# Метаданные стратегий
AVAILABLE_STRATEGIES = {
    "momentum": {
        "name": "MomentumStrategy",
        "description": "Импульсная торговая стратегия на основе движений цены",
        "class": MomentumStrategy,
        "enabled": True
    },
    "technical": {
        "name": "TechnicalStrategy", 
        "description": "Технический анализ с индикаторами RSI, MACD, Bollinger Bands",
        "class": None,  # TechnicalStrategy - будет добавлено позже
        "enabled": False
    },
    "sentiment": {
        "name": "SentimentStrategy",
        "description": "Анализ настроений рынка и социальных индикаторов",
        "class": None,  # SentimentStrategy - будет добавлено позже
        "enabled": False
    }
}

def get_available_strategies():
    """Возвращает список доступных стратегий"""
    return {k: v for k, v in AVAILABLE_STRATEGIES.items() if v["enabled"] and v["class"] is not None}

def create_strategy(strategy_type: str, **kwargs) -> BaseStrategy:
    """
    Фабрика для создания стратегий
    
    Args:
        strategy_type: Тип стратегии ("momentum", "technical", "sentiment")
        **kwargs: Параметры для инициализации стратегии
        
    Returns:
        Экземпляр стратегии
        
    Raises:
        ValueError: Если тип стратегии неизвестен или недоступен
    """
    strategy_type = strategy_type.lower()
    
    if strategy_type not in AVAILABLE_STRATEGIES:
        raise ValueError(f"Unknown strategy type: {strategy_type}")
    
    strategy_info = AVAILABLE_STRATEGIES[strategy_type]
    
    if not strategy_info["enabled"]:
        raise ValueError(f"Strategy {strategy_type} is disabled")
        
    if strategy_info["class"] is None:
        raise ValueError(f"Strategy {strategy_type} is not implemented yet")
    
    strategy_class = strategy_info["class"]
    return strategy_class(**kwargs)

def get_strategy_info(strategy_name: str):
    """Возвращает информацию о конкретной стратегии"""
    return AVAILABLE_STRATEGIES.get(strategy_name)
