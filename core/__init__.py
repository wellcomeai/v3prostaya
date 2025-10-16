"""
Core Trading System Module

Provides core components for the trading system:
- Signal Management with AI enrichment
- Strategy Orchestration (simplified v2.0)
- System configuration and data models
"""

import logging
from typing import List, Type

from .signal_manager import SignalManager
from .strategy_orchestrator import StrategyOrchestrator
from .data_models import (
    SystemConfig,
    StrategyConfig,
    create_default_system_config,
    TradingSignal,
    SignalType,
    SignalConfidence
)

# ❌ УДАЛЕНА СТРОКА: from .data_source_adapter import DataSourceAdapter

logger = logging.getLogger(__name__)

__all__ = [
    "SignalManager",
    "StrategyOrchestrator",
    "SystemConfig",
    "StrategyConfig", 
    "create_default_system_config",
    "TradingSignal",
    "SignalType",
    "SignalConfidence",
    # ❌ УДАЛЕНО: "DataSourceAdapter"
]

logger.info("✅ Core module loaded successfully (Simplified v2.0)")
