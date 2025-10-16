# ==================================================
# ОБНОВЛЕННЫЙ core/__init__.py
# ==================================================

from .signal_manager import SignalManager, SignalProcessor, SignalFilter
from .data_models import (
    SystemConfig, 
    StrategyConfig, 
    SignalMetrics,
    MarketCondition,
    RiskParameters,
    NotificationSettings
)
from .strategy_orchestrator import StrategyOrchestrator
from .data_source_adapter import DataSourceAdapter
from .market_analyzer import MarketAnalyzer, MarketAnalysisReport, StrategyOpinion  # ✅ ДОБАВЛЕНО

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
    
    # Strategy Management
    "StrategyOrchestrator",
    "DataSourceAdapter",
    
    # Market Analysis  # ✅ ДОБАВЛЕНО
    "MarketAnalyzer",
    "MarketAnalysisReport",
    "StrategyOpinion"
]
