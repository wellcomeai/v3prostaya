"""
Модуль торговых стратегий v3.0.0

Содержит различные торговые стратегии для анализа рыночных данных
и генерации торговых сигналов.

Изменения v3.0.0:
- ✅ Все стратегии обновлены под StrategyOrchestrator
- ✅ Метод analyze_with_data() реализован во всех стратегиях
- ✅ Убрана зависимость от MarketDataSnapshot
- ✅ Прямая работа с данными из Repository
- ❌ MomentumStrategy удалена (будет переработана позже)

Архитектура:
- BaseStrategy: Абстрактный базовый класс для всех стратегий
- BreakoutStrategy: Стратегия торговли пробоев уровней
- BounceStrategy: Стратегия торговли отбоев от уровней (БСУ-БПУ модель)
- FalseBreakoutStrategy: Стратегия торговли ложных пробоев
- StrategyOrchestrator: Координатор выполнения всех стратегий

Планируется:
- MomentumStrategy: Импульсная торговая стратегия (в разработке)
- TechnicalStrategy: Технический анализ (RSI, MACD, Bollinger Bands)
- SentimentStrategy: Анализ настроений рынка
- MLStrategy: Стратегии машинного обучения

Author: Trading Bot Team
Version: 3.0.0 - Orchestrator Integration
"""

import logging

# Базовые классы
from .base_strategy import BaseStrategy, TradingSignal, SignalType, SignalStrength

# Реализованные стратегии v3.0
from .breakout_strategy import BreakoutStrategy
from .bounce_strategy import BounceStrategy
from .false_breakout_strategy import FalseBreakoutStrategy

# Координатор стратегий
from .strategy_orchestrator import StrategyOrchestrator

# Будущие стратегии
# from .momentum_strategy import MomentumStrategy  # TODO: переработка под v3.0
# from .technical_strategy import TechnicalStrategy
# from .sentiment_strategy import SentimentStrategy

logger = logging.getLogger(__name__)

__all__ = [
    # Базовые классы
    "BaseStrategy",
    "TradingSignal",
    "SignalType", 
    "SignalStrength",
    
    # Стратегии v3.0
    "BreakoutStrategy",
    "BounceStrategy",
    "FalseBreakoutStrategy",
    
    # Координатор
    "StrategyOrchestrator",
    
    # Утилиты
    "get_available_strategies",
    "create_strategy",
    "get_strategy_info",
    "get_all_strategies_info",
    "list_strategies",
    "get_strategies_by_category",
    "print_strategies_info"
]

__version__ = "3.0.0"

# ==================== МЕТАДАННЫЕ СТРАТЕГИЙ ====================

AVAILABLE_STRATEGIES = {
    "breakout": {
        "name": "BreakoutStrategy",
        "class_name": "BreakoutStrategy",
        "description": "Стратегия торговли пробоев ключевых уровней",
        "details": "Ловит импульсные движения после преодоления уровня. Требует поджатие, консолидацию и накопленную энергию. Не работает при исчерпанном ATR. Entry: Buy/Sell Stop за уровнем. R:R минимум 3:1.",
        "class": BreakoutStrategy,
        "enabled": True,
        "version": "3.0.0",
        "category": "level_based",
        "timeframes": ["5m", "1h", "1d"],
        "min_data_required": "180 свечей D1 + 50 свечей M5 + 24 свечей H1",
        "avg_signals_per_day": "2-4",
        "suitable_for": ["свинг-трейдинг", "позиционная торговля"],
        "risk_level": "средний",
        "api_version": "analyze_with_data"
    },
    
    "bounce": {
        "name": "BounceStrategy",
        "class_name": "BounceStrategy",
        "description": "Стратегия торговли отбоев от уровней (БСУ-БПУ модель)",
        "details": "Торгует отскок от проверенного уровня. Использует модель БСУ-БПУ для подтверждения. Вход: Limit ордер с люфтом 20% от SL. R:R минимум 3:1. Работает при исчерпанном ATR.",
        "class": BounceStrategy,
        "enabled": True,
        "version": "3.0.0",
        "category": "level_based",
        "timeframes": ["1h", "1d"],
        "min_data_required": "180 свечей D1 + 24 свечей H1",
        "avg_signals_per_day": "1-3",
        "suitable_for": ["свинг-трейдинг", "точечные входы"],
        "risk_level": "низкий-средний",
        "api_version": "analyze_with_data"
    },
    
    "false_breakout": {
        "name": "FalseBreakoutStrategy",
        "class_name": "FalseBreakoutStrategy",
        "description": "Стратегия торговли ложных пробоев (ловушек)",
        "details": "Ловит развороты после ложного пробоя уровня. Торгует ПРОТИВ направления пробоя. Entry: Market или Limit. Быстрые сделки (1-4 часа). R:R 2.5:1. Требует подтверждения разворота.",
        "class": FalseBreakoutStrategy,
        "enabled": True,
        "version": "3.0.0",
        "category": "level_based",
        "timeframes": ["5m", "1h"],
        "min_data_required": "180 свечей D1 + 50 свечей M5",
        "avg_signals_per_day": "2-5",
        "suitable_for": ["контртрендовая торговля", "ловля разворотов"],
        "risk_level": "средний-высокий",
        "api_version": "analyze_with_data"
    },
    
    # ==================== В РАЗРАБОТКЕ ====================
    
    "momentum": {
        "name": "MomentumStrategy",
        "class_name": "MomentumStrategy",
        "description": "Импульсная торговая стратегия на основе движений цены",
        "details": "Анализирует краткосрочные движения за 1м, 5м, 1ч. Генерирует сигналы при экстремальных движениях (>2%), импульсах и разворотах тренда. В процессе переработки под v3.0.",
        "class": None,  # TODO: переработка под analyze_with_data
        "enabled": False,
        "version": "2.0.0",
        "category": "momentum",
        "timeframes": ["1m", "5m", "1h"],
        "min_data_required": "100 свечей M1 + 50 свечей M5 + 24 свечей H1",
        "avg_signals_per_day": "8-15",
        "suitable_for": ["скальпинг", "внутридневная торговля"],
        "risk_level": "средний-высокий",
        "api_version": "legacy"
    },
    
    "technical": {
        "name": "TechnicalStrategy", 
        "class_name": "TechnicalStrategy",
        "description": "Технический анализ с индикаторами RSI, MACD, Bollinger Bands",
        "details": "Классический технический анализ с использованием популярных индикаторов. Дивергенции, перекупленность/перепроданность, пересечения MACD.",
        "class": None,  # TODO: будет добавлено позже
        "enabled": False,
        "version": "1.0.0",
        "category": "indicator_based",
        "timeframes": ["15m", "1h", "4h"],
        "min_data_required": "200 свечей",
        "avg_signals_per_day": "3-6",
        "suitable_for": ["свинг-трейдинг"],
        "risk_level": "средний",
        "api_version": "future"
    },
    
    "sentiment": {
        "name": "SentimentStrategy",
        "class_name": "SentimentStrategy",
        "description": "Анализ настроений рынка и социальных индикаторов",
        "details": "Анализирует социальные сети, новости, страх/жадность. Комбинирует с техническим анализом для подтверждения сигналов.",
        "class": None,  # TODO: будет добавлено позже
        "enabled": False,
        "version": "1.0.0",
        "category": "sentiment_based",
        "timeframes": ["1h", "4h", "1d"],
        "min_data_required": "Внешние данные + 100 свечей",
        "avg_signals_per_day": "1-3",
        "suitable_for": ["позиционная торговля"],
        "risk_level": "средний",
        "api_version": "future"
    }
}

# ==================== УТИЛИТЫ ====================

def get_available_strategies():
    """
    Возвращает словарь доступных стратегий (только активные v3.0)
    
    Returns:
        Dict[str, dict]: Словарь с метаданными доступных стратегий
    """
    available = {
        k: v for k, v in AVAILABLE_STRATEGIES.items() 
        if v["enabled"] and v["class"] is not None
    }
    
    logger.debug(f"📋 Доступно стратегий: {len(available)}/{len(AVAILABLE_STRATEGIES)}")
    
    return available


def get_all_strategies_info():
    """
    Возвращает информацию о всех стратегиях (включая неактивные)
    
    Returns:
        Dict[str, dict]: Полный словарь метаданных всех стратегий
    """
    return AVAILABLE_STRATEGIES.copy()


def get_strategy_info(strategy_name: str):
    """
    Возвращает информацию о конкретной стратегии
    
    Args:
        strategy_name: Имя стратегии ("breakout", "bounce", "false_breakout", etc.)
        
    Returns:
        dict или None: Метаданные стратегии или None если не найдена
    """
    return AVAILABLE_STRATEGIES.get(strategy_name)


def create_strategy(strategy_type: str, **kwargs) -> BaseStrategy:
    """
    Фабрика для создания экземпляров стратегий
    
    Args:
        strategy_type: Тип стратегии ("breakout", "bounce", "false_breakout")
        **kwargs: Параметры для инициализации стратегии
            - symbol: str (обязательно)
            - repository: MarketDataRepository (опционально)
            - ta_context_manager: TechnicalAnalysisContextManager (опционально)
            - другие параметры специфичные для стратегии
        
    Returns:
        BaseStrategy: Экземпляр стратегии
        
    Raises:
        ValueError: Если тип стратегии неизвестен, отключен или не реализован
        
    Examples:
        >>> breakout = create_strategy(
        ...     "breakout", 
        ...     symbol="BTCUSDT",
        ...     repository=repo,
        ...     ta_context_manager=ta_manager
        ... )
        >>> 
        >>> bounce = create_strategy(
        ...     "bounce",
        ...     symbol="ETHUSDT",
        ...     repository=repo,
        ...     ta_context_manager=ta_manager
        ... )
    """
    strategy_type = strategy_type.lower()
    
    # Проверка существования
    if strategy_type not in AVAILABLE_STRATEGIES:
        available = list(AVAILABLE_STRATEGIES.keys())
        raise ValueError(
            f"Unknown strategy type: '{strategy_type}'. "
            f"Available strategies: {', '.join(available)}"
        )
    
    strategy_info = AVAILABLE_STRATEGIES[strategy_type]
    
    # Проверка что стратегия включена
    if not strategy_info["enabled"]:
        raise ValueError(
            f"Strategy '{strategy_type}' is disabled. "
            f"Status: {strategy_info.get('version', 'unknown')} - {strategy_info.get('api_version', 'unknown')}"
        )
    
    # Проверка что стратегия реализована
    if strategy_info["class"] is None:
        raise ValueError(
            f"Strategy '{strategy_type}' is not implemented yet. "
            f"Coming soon!"
        )
    
    # Создаем экземпляр
    strategy_class = strategy_info["class"]
    
    try:
        instance = strategy_class(**kwargs)
        logger.info(f"✅ Создана стратегия: {strategy_info['name']} v{strategy_info['version']}")
        return instance
    
    except Exception as e:
        logger.error(f"❌ Ошибка создания стратегии '{strategy_type}': {e}")
        raise


def list_strategies(category: str = None, enabled_only: bool = True):
    """
    Список стратегий с фильтрацией
    
    Args:
        category: Фильтр по категории ("momentum", "level_based", "indicator_based", "sentiment_based")
        enabled_only: Показывать только включенные стратегии
        
    Returns:
        List[str]: Список названий стратегий
        
    Examples:
        >>> list_strategies()  # Все активные
        ['breakout', 'bounce', 'false_breakout']
        >>> 
        >>> list_strategies(category="level_based")
        ['breakout', 'bounce', 'false_breakout']
        >>> 
        >>> list_strategies(enabled_only=False)  # Все стратегии
        ['breakout', 'bounce', 'false_breakout', 'momentum', 'technical', 'sentiment']
    """
    strategies = AVAILABLE_STRATEGIES
    
    # Фильтр по категории
    if category:
        strategies = {
            k: v for k, v in strategies.items()
            if v.get("category") == category
        }
    
    # Фильтр по enabled
    if enabled_only:
        strategies = {
            k: v for k, v in strategies.items()
            if v["enabled"] and v["class"] is not None
        }
    
    return list(strategies.keys())


def get_strategies_by_category():
    """
    Группировка стратегий по категориям
    
    Returns:
        Dict[str, List[str]]: Словарь категория -> список стратегий
        
    Example:
        >>> get_strategies_by_category()
        {
            'level_based': ['breakout', 'bounce', 'false_breakout'],
            'momentum': ['momentum'],
            'indicator_based': ['technical'],
            'sentiment_based': ['sentiment']
        }
    """
    categorized = {}
    
    for strategy_name, info in AVAILABLE_STRATEGIES.items():
        category = info.get("category", "other")
        
        if category not in categorized:
            categorized[category] = []
        
        categorized[category].append(strategy_name)
    
    return categorized


def print_strategies_info():
    """
    Красиво выводит информацию о всех стратегиях в лог
    """
    logger.info("=" * 80)
    logger.info("📊 ДОСТУПНЫЕ ТОРГОВЫЕ СТРАТЕГИИ v3.0.0")
    logger.info("=" * 80)
    
    available = get_available_strategies()
    disabled = {
        k: v for k, v in AVAILABLE_STRATEGIES.items() 
        if not v["enabled"] or v["class"] is None
    }
    
    logger.info(f"\n✅ Активные стратегии: {len(available)}")
    
    for name, info in available.items():
        logger.info(f"\n🔹 {info['name']} v{info['version']}")
        logger.info(f"   Описание: {info['description']}")
        logger.info(f"   Категория: {info['category']}")
        logger.info(f"   Таймфреймы: {', '.join(info['timeframes'])}")
        logger.info(f"   Сигналов/день: {info['avg_signals_per_day']}")
        logger.info(f"   Риск: {info['risk_level']}")
        logger.info(f"   API: {info['api_version']}")
    
    if disabled:
        logger.info(f"\n⏳ В разработке / отключены: {len(disabled)}")
        for name, info in disabled.items():
            status = f"v{info['version']} - {info['api_version']}"
            logger.info(f"   • {info['name']} ({status})")
    
    logger.info("\n" + "=" * 80)


def get_orchestrator_compatible_strategies():
    """
    Возвращает только стратегии совместимые с StrategyOrchestrator
    
    Returns:
        Dict[str, dict]: Стратегии с api_version="analyze_with_data"
    """
    compatible = {
        k: v for k, v in AVAILABLE_STRATEGIES.items()
        if v.get("api_version") == "analyze_with_data" and 
           v["enabled"] and 
           v["class"] is not None
    }
    
    logger.debug(f"🎭 Совместимых с Orchestrator стратегий: {len(compatible)}")
    
    return compatible


# ==================== ИНИЦИАЛИЗАЦИЯ МОДУЛЯ ====================

# Выводим информацию при импорте
logger.info("=" * 70)
logger.info("📦 Модуль стратегий загружен")
logger.info(f"   Версия: {__version__}")
logger.info(f"   Активных стратегий: {len(get_available_strategies())}")
logger.info(f"   Всего стратегий: {len(AVAILABLE_STRATEGIES)}")
logger.info("=" * 70)

# Список активных стратегий v3.0
active_strategies = [
    f"{info['name']} v{info['version']}" 
    for info in get_available_strategies().values()
]
if active_strategies:
    logger.info(f"✅ Активные (v3.0): {', '.join(active_strategies)}")

# Список совместимых с Orchestrator
orchestrator_compatible = get_orchestrator_compatible_strategies()
if orchestrator_compatible:
    compatible_names = [info['name'] for info in orchestrator_compatible.values()]
    logger.info(f"🎭 Orchestrator-совместимые: {', '.join(compatible_names)}")

# Список в разработке
pending_strategies = [
    f"{info['name']} ({info.get('api_version', 'unknown')})"
    for name, info in AVAILABLE_STRATEGIES.items() 
    if not info['enabled'] or info['class'] is None
]
if pending_strategies:
    logger.info(f"⏳ В разработке: {', '.join(pending_strategies)}")

logger.info("=" * 70)

# Важное уведомление для разработчиков
logger.info("💡 Важно:")
logger.info("   • Все активные стратегии используют analyze_with_data()")
logger.info("   • Для запуска используйте StrategyOrchestrator")
logger.info("   • MomentumStrategy в процессе переработки под v3.0")
logger.info("=" * 70)
