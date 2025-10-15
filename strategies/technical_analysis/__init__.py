"""
Technical Analysis Module

Модуль технического анализа для торговых стратегий.
Предоставляет инструменты для анализа уровней, ATR, паттернов и рыночных условий.

Components:
- TechnicalAnalysisContext: Кэшированный контекст технического анализа
- TechnicalAnalysisContextManager: Менеджер автоматического обновления контекстов
- LevelAnalyzer: Анализатор уровней поддержки/сопротивления
- ATRCalculator: Калькулятор ATR (Average True Range)
- PatternDetector: Детектор паттернов БСУ-БПУ
- BreakoutAnalyzer: Анализатор пробоев (истинных и ложных)
- MarketConditionsAnalyzer: Анализатор рыночных условий

Author: Trading Bot Team
Version: 2.0.0
"""

import logging

# ==================== CONTEXT ====================
from .context import (
    TechnicalAnalysisContext,
    SupportResistanceLevel,
    ATRData,
    MarketCondition,
    TrendDirection
)

from .context_manager import TechnicalAnalysisContextManager

# ==================== ANALYZERS ====================
from .level_analyzer import LevelAnalyzer, LevelCandidate

from .atr_calculator import ATRCalculator

from .pattern_detector import (
    PatternDetector,
    PatternMatch,
    BSUPattern,
    BPUPattern
)

from .breakout_analyzer import (
    BreakoutAnalyzer,
    BreakoutAnalysis,
    BreakoutType,
    BreakoutDirection
)

from .market_conditions import (
    MarketConditionsAnalyzer,
    MarketConditionsAnalysis,
    VolatilityLevel,
    EnergyLevel,
    TrendStrength
)

logger = logging.getLogger(__name__)

# ==================== EXPORTS ====================

__all__ = [
    # Context & Manager
    "TechnicalAnalysisContext",
    "TechnicalAnalysisContextManager",
    "SupportResistanceLevel",
    "ATRData",
    "MarketCondition",
    "TrendDirection",
    
    # Level Analyzer
    "LevelAnalyzer",
    "LevelCandidate",
    
    # ATR Calculator
    "ATRCalculator",
    
    # Pattern Detector
    "PatternDetector",
    "PatternMatch",
    "BSUPattern",
    "BPUPattern",
    
    # Breakout Analyzer
    "BreakoutAnalyzer",
    "BreakoutAnalysis",
    "BreakoutType",
    "BreakoutDirection",
    
    # Market Conditions Analyzer
    "MarketConditionsAnalyzer",
    "MarketConditionsAnalysis",
    "VolatilityLevel",
    "EnergyLevel",
    "TrendStrength",
    
    # Utilities
    "get_module_status",
    "is_fully_ready",
    "print_module_status"
]

__version__ = "2.0.0"

# ==================== MODULE STATUS ====================

MODULE_STATUS = {
    "context": "✅ Ready",
    "context_manager": "✅ Ready",
    "level_analyzer": "✅ Ready",
    "atr_calculator": "✅ Ready",
    "pattern_detector": "✅ Ready",
    "breakout_analyzer": "✅ Ready",
    "market_conditions": "✅ Ready"
}

# ==================== UTILITIES ====================

def get_module_status():
    """
    Возвращает статус всех модулей
    
    Returns:
        Dict[str, str]: Словарь модуль -> статус
    """
    return MODULE_STATUS.copy()


def is_fully_ready():
    """
    Проверяет готовность всех модулей
    
    Returns:
        bool: True если все модули готовы
    """
    return all(status == "✅ Ready" for status in MODULE_STATUS.values())


def print_module_status():
    """Красиво выводит статус всех модулей"""
    logger.info("=" * 70)
    logger.info("📊 TECHNICAL ANALYSIS MODULE STATUS")
    logger.info("=" * 70)
    
    for module, status in MODULE_STATUS.items():
        logger.info(f"  {status} {module}")
    
    if is_fully_ready():
        logger.info("\n✅ All technical analysis modules are ready and operational!")
    else:
        ready_count = sum(1 for s in MODULE_STATUS.values() if s == "✅ Ready")
        total_count = len(MODULE_STATUS)
        logger.info(f"\n⏳ {ready_count}/{total_count} modules ready")
    
    logger.info("=" * 70)


def get_available_analyzers():
    """
    Возвращает список доступных анализаторов
    
    Returns:
        Dict[str, type]: Словарь название -> класс анализатора
    """
    return {
        "level": LevelAnalyzer,
        "atr": ATRCalculator,
        "pattern": PatternDetector,
        "breakout": BreakoutAnalyzer,
        "market_conditions": MarketConditionsAnalyzer
    }


def create_full_analyzer_suite():
    """
    Создает полный набор анализаторов для использования в стратегиях
    
    Returns:
        Dict[str, object]: Словарь с инициализированными анализаторами
        
    Example:
        >>> analyzers = create_full_analyzer_suite()
        >>> level_analyzer = analyzers['level']
        >>> atr_calculator = analyzers['atr']
    """
    try:
        suite = {
            "level": LevelAnalyzer(),
            "atr": ATRCalculator(),
            "pattern": PatternDetector(),
            "breakout": BreakoutAnalyzer(),
            "market_conditions": MarketConditionsAnalyzer()
        }
        
        logger.info("✅ Создан полный набор анализаторов")
        return suite
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания набора анализаторов: {e}")
        raise


# ==================== INITIALIZATION ====================

# Выводим информацию при импорте
logger.info("=" * 70)
logger.info("📊 Technical Analysis Module Loading...")
logger.info(f"   Version: {__version__}")
logger.info("=" * 70)

for module, status in MODULE_STATUS.items():
    logger.info(f"  {status} {module}")

if is_fully_ready():
    logger.info("\n✅ All technical analysis modules ready and operational!")
    logger.info("\nAvailable components:")
    logger.info("  • TechnicalAnalysisContext - кэшированный контекст анализа")
    logger.info("  • TechnicalAnalysisContextManager - менеджер автообновления")
    logger.info("  • LevelAnalyzer - анализ уровней S/R")
    logger.info("  • ATRCalculator - расчет запаса хода")
    logger.info("  • PatternDetector - детекция паттернов (БСУ-БПУ, поджатие)")
    logger.info("  • BreakoutAnalyzer - анализ пробоев (истинные/ложные)")
    logger.info("  • MarketConditionsAnalyzer - анализ рыночных условий")
else:
    ready_count = sum(1 for s in MODULE_STATUS.values() if s == "✅ Ready")
    total_count = len(MODULE_STATUS)
    logger.info(f"\n⏳ {ready_count}/{total_count} modules ready")

logger.info("=" * 70)
