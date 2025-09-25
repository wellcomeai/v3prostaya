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
# from .momentum_strategy import MomentumStrategy
# from .technical_strategy import TechnicalStrategy
# from .sentiment_strategy import SentimentStrategy

__all__ = [
    "BaseStrategy",
    "TradingSignal",
    "SignalType", 
    "SignalStrength",
    # "MomentumStrategy",
    # "TechnicalStrategy", 
    # "SentimentStrategy"
]

__version__ = "1.0.0"

# Метаданные стратегий
AVAILABLE_STRATEGIES = {
    "momentum": {
        "name": "MomentumStrategy",
        "description": "Импульсная торговая стратегия на основе движений цены",
        "class": None,  # MomentumStrategy,  # Будет добавлено позже
        "enabled": True
    },
    "technical": {
        "name": "TechnicalStrategy", 
        "description": "Технический анализ с индикаторами RSI, MACD, Bollinger Bands",
        "class": None,  # TechnicalStrategy,
        "enabled": True
    },
    "sentiment": {
        "name": "SentimentStrategy",
        "description": "Анализ настроений рынка и социальных индикаторов",
        "class": None,  # SentimentStrategy,
        "enabled": False  # Пока отключена
    }
}

def get_available_strategies():
    """Возвращает список доступных стратегий"""
    return {k: v for k, v in AVAILABLE_STRATEGIES.items() if v["enabled"]}

def get_strategy_info(strategy_name: str):
    """Возвращает информацию о конкретной стратегии"""
    return AVAILABLE_STRATEGIES.get(strategy_name)
