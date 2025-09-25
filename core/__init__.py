"""
Ядро торговой системы

Содержит основные компоненты для управления торговыми сигналами,
стратегиями и обработкой рыночных данных.

Компоненты:
- SignalManager: Центральный менеджер для обработки и комбинирования сигналов
- StrategyOrchestrator: Управляет всеми торговыми стратегиями
- Модели данных: Базовые структуры данных для системы
"""

from .signal_manager import SignalManager, SignalProcessor, SignalFilter
from .data_models import (
    SystemConfig, 
    StrategyConfig, 
    SignalMetrics,
    MarketCondition,
    RiskParameters,
    NotificationSettings
)
# from .strategy_orchestrator import StrategyOrchestrator  # Будет добавлен позже

__all__ = [
    # Signal Management
    "SignalManager",
    "SignalProcessor", 
    "SignalFilter",
    
    # Data Models
    "SystemConfig",
    "StrategyConfig",
    "SignalMetrics", 
    "MarketCondition",
    "RiskParameters",
    "NotificationSettings",
    
    # Strategy Management (будущее)
    # "StrategyOrchestrator"
]

__version__ = "1.0.0"

# Константы ядра системы
CORE_CONFIG = {
    "max_concurrent_strategies": 10,
    "signal_processing_timeout": 30.0,  # секунд
    "default_signal_expiry": 300,       # 5 минут
    "max_signal_queue_size": 1000,
    "metrics_retention_hours": 24
}

def get_core_config():
    """Возвращает конфигурацию ядра системы"""
    return CORE_CONFIG.copy()

def validate_core_dependencies():
    """
    Проверяет доступность всех зависимостей ядра
    
    Returns:
        Dict с результатами проверки
    """
    try:
        from market_data import MarketDataManager
        from strategies import BaseStrategy
        
        return {
            "status": "ok",
            "market_data_available": True,
            "strategies_available": True,
            "all_dependencies_ok": True
        }
    except ImportError as e:
        return {
            "status": "error", 
            "error": str(e),
            "all_dependencies_ok": False
        }
