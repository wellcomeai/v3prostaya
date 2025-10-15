"""
Technical Analysis Module

Модуль технического анализа для торговых стратегий.
Предоставляет инструменты для анализа уровней, ATR, паттернов и рыночных условий.

Components:
- TechnicalAnalysisContext: Кэшированный контекст технического анализа
- TechnicalAnalysisContextManager: Менеджер автоматического обновления контекстов
- LevelAnalyzer: Анализатор уровней поддержки/сопротивления (TODO)
- ATRCalculator: Калькулятор ATR (TODO)
- PatternDetector: Детектор паттернов БСУ-БПУ (TODO)
- BreakoutAnalyzer: Анализатор пробоев (TODO)
- MarketConditions: Анализатор рыночных условий (TODO)

Author: Trading Bot Team
Version: 1.0.0
"""

import logging

# Context и Manager (готовы)
from .context import (
    TechnicalAnalysisContext,
    SupportResistanceLevel,
    ATRData,
    MarketCondition,
    TrendDirection
)

from .context_manager import TechnicalAnalysisContextManager

# Аналитические модули (будут добавлены)
# from .level_analyzer import LevelAnalyzer
# from .atr_calculator import ATRCalculator
# from .pattern_detector import PatternDetector
# from .breakout_analyzer import BreakoutAnalyzer
# from .market_conditions import MarketConditionsAnalyzer

logger = logging.getLogger(__name__)

__all__ = [
    # Context
    "TechnicalAnalysisContext",
    "SupportResistanceLevel",
    "ATRData",
    "MarketCondition",
    "TrendDirection",
    
    # Manager
    "TechnicalAnalysisContextManager",
    
    # Analyzers (TODO)
    # "LevelAnalyzer",
    # "ATRCalculator",
    # "PatternDetector",
    # "BreakoutAnalyzer",
    # "MarketConditionsAnalyzer",
]

__version__ = "1.0.0"

# Статус модулей
MODULE_STATUS = {
    "context": "✅ Ready",
    "context_manager": "✅ Ready",
    "level_analyzer": "⏳ Pending",
    "atr_calculator": "⏳ Pending",
    "pattern_detector": "⏳ Pending",
    "breakout_analyzer": "⏳ Pending",
    "market_conditions": "⏳ Pending"
}

def get_module_status():
    """Возвращает статус всех модулей"""
    return MODULE_STATUS.copy()

def is_fully_ready():
    """Проверяет готовность всех модулей"""
    return all(status == "✅ Ready" for status in MODULE_STATUS.values())

# Логируем статус при импорте
logger.info("=" * 60)
logger.info("📊 Technical Analysis Module Loading...")
logger.info("=" * 60)

for module, status in MODULE_STATUS.items():
    logger.info(f"  {status} {module}")

if is_fully_ready():
    logger.info("✅ All technical analysis modules ready!")
else:
    ready_count = sum(1 for s in MODULE_STATUS.values() if s == "✅ Ready")
    total_count = len(MODULE_STATUS)
    logger.info(f"⏳ {ready_count}/{total_count} modules ready")

logger.info("=" * 60)
