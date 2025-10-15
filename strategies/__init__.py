"""
Модуль торговых стратегий

Содержит различные торговые стратегии для анализа рыночных данных
и генерации торговых сигналов.

Архитектура:
- BaseStrategy: Абстрактный базовый класс для всех стратегий
- MomentumStrategy: Импульсная торговая стратегия на основе движений цены
- BreakoutStrategy: Стратегия торговли пробоев уровней
- BounceStrategy: Стратегия торговли отбоев от уровней (БСУ-БПУ модель)
- FalseBreakoutStrategy: Стратегия торговли ложных пробоев
- TechnicalStrategy: Технический анализ (RSI, MACD, Bollinger Bands) [TODO]
- SentimentStrategy: Анализ настроений рынка [TODO]
- MLStrategy: Стратегии машинного обучения [TODO]
"""

import logging

# Базовые классы
from .base_strategy import BaseStrategy, TradingSignal, SignalType, SignalStrength

# Реализованные стратегии
from .momentum_strategy import MomentumStrategy
from .breakout_strategy import BreakoutStrategy
from .bounce_strategy import BounceStrategy
from .false_breakout_strategy import FalseBreakoutStrategy

# Будущие стратегии
# from .technical_strategy import TechnicalStrategy
# from .sentiment_strategy import SentimentStrategy

logger = logging.getLogger(__name__)

__all__ = [
    # Базовые классы
    "BaseStrategy",
    "TradingSignal",
    "SignalType", 
    "SignalStrength",
    
    # Стратегии
    "MomentumStrategy",
    "BreakoutStrategy",
    "BounceStrategy",
    "FalseBreakoutStrategy",
    # "TechnicalStrategy", 
    # "SentimentStrategy",
    
    # Утилиты
    "get_available_strategies",
    "create_strategy",
    "get_strategy_info",
    "get_all_strategies_info"
]

__version__ = "2.0.0"

# ==================== МЕТАДАННЫЕ СТРАТЕГИЙ ====================

AVAILABLE_STRATEGIES = {
    "momentum": {
        "name": "MomentumStrategy",
        "class_name": "MomentumStrategy",
        "description": "Импульсная торговая стратегия на основе движений цены",
        "details": "Анализирует краткосрочные движения за 1м, 5м, 24ч. Генерирует сигналы при экстремальных движениях (>2%), импульсах и разворотах тренда.",
        "class": MomentumStrategy,
        "enabled": True,
        "category": "momentum",
        "timeframes": ["1m", "5m", "1h"],
        "min_data_required": "100 свечей M1",
        "avg_signals_per_day": "8-15",
        "suitable_for": ["скальпинг", "внутридневная торговля"],
        "risk_level": "средний-высокий"
    },
    
    "breakout": {
        "name": "BreakoutStrategy",
        "class_name": "BreakoutStrategy",
        "description": "Стратегия торговли пробоев ключевых уровней",
        "details": "Ловит импульсные движения после преодоления уровня. Требует поджатие, консолидацию и накопленную энергию. Не работает при исчерпанном ATR.",
        "class": BreakoutStrategy,
        "enabled": True,
        "category": "level_based",
        "timeframes": ["5m", "30m", "1h", "1d"],
        "min_data_required": "180 свечей D1 + 100 свечей M5",
        "avg_signals_per_day": "2-4",
        "suitable_for": ["свинг-трейдинг", "позиционная торговля"],
        "risk_level": "средний"
    },
    
    "bounce": {
        "name": "BounceStrategy",
        "class_name": "BounceStrategy",
        "description": "Стратегия торговли отбоев от уровней (БСУ-БПУ модель)",
        "details": "Торгует отскок от проверенного уровня. Использует модель БСУ-БПУ для подтверждения. Вход за 30 сек до закрытия БПУ-2. R:R минимум 3:1.",
        "class": BounceStrategy,
        "enabled": True,
        "category": "level_based",
        "timeframes": ["30m", "1h", "1d"],
        "min_data_required": "180 свечей D1 + 50 свечей M30",
        "avg_signals_per_day": "1-3",
        "suitable_for": ["свинг-трейдинг", "точечные входы"],
        "risk_level": "низкий-средний"
    },
    
    "false_breakout": {
        "name": "FalseBreakoutStrategy",
        "class_name": "FalseBreakoutStrategy",
        "description": "Стратегия торговли ложных пробоев (ловушек)",
        "details": "Ловит развороты после ложного пробоя уровня. Торгует ПРОТИВ направления пробоя. Быстрые сделки (1-4 часа). R:R 2-3:1.",
        "class": FalseBreakoutStrategy,
        "enabled": True,
        "category": "level_based",
        "timeframes": ["5m", "30m", "1h"],
        "min_data_required": "180 свечей D1 + 50 свечей M5",
        "avg_signals_per_day": "2-5",
        "suitable_for": ["контртрендовая торговля", "ловля разворотов"],
        "risk_level": "средний-высокий"
    },
    
    "technical": {
        "name": "TechnicalStrategy", 
        "class_name": "TechnicalStrategy",
        "description": "Технический анализ с индикаторами RSI, MACD, Bollinger Bands",
        "details": "Классический технический анализ с использованием популярных индикаторов. Дивергенции, перекупленность/перепроданность, пересечения MACD.",
        "class": None,  # TODO: будет добавлено позже
        "enabled": False,
        "category": "indicator_based",
        "timeframes": ["15m", "1h", "4h"],
        "min_data_required": "200 свечей",
        "avg_signals_per_day": "3-6",
        "suitable_for": ["свинг-трейдинг"],
        "risk_level": "средний"
    },
    
    "sentiment": {
        "name": "SentimentStrategy",
        "class_name": "SentimentStrategy",
        "description": "Анализ настроений рынка и социальных индикаторов",
        "details": "Анализирует социальные сети, новости, страх/жадность. Комбинирует с техническим анализом для подтверждения сигналов.",
        "class": None,  # TODO: будет добавлено позже
        "enabled": False,
        "category": "sentiment_based",
        "timeframes": ["1h", "4h", "1d"],
        "min_data_required": "Внешние данные + 100 свечей",
        "avg_signals_per_day": "1-3",
        "suitable_for": ["позиционная торговля"],
        "risk_level": "средний"
    }
}

# ==================== УТИЛИТЫ ====================

def get_available_strategies():
    """
    Возвращает словарь доступных стратегий
    
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
        strategy_name: Имя стратегии ("momentum", "breakout", etc.)
        
    Returns:
        dict или None: Метаданные стратегии или None если не найдена
    """
    return AVAILABLE_STRATEGIES.get(strategy_name)


def create_strategy(strategy_type: str, **kwargs) -> BaseStrategy:
    """
    Фабрика для создания экземпляров стратегий
    
    Args:
        strategy_type: Тип стратегии ("momentum", "breakout", "bounce", "false_breakout")
        **kwargs: Параметры для инициализации стратегии
        
    Returns:
        BaseStrategy: Экземпляр стратегии
        
    Raises:
        ValueError: Если тип стратегии неизвестен, отключен или не реализован
        
    Examples:
        >>> momentum = create_strategy("momentum", symbol="BTCUSDT")
        >>> breakout = create_strategy("breakout", symbol="ETHUSDT", ta_context_manager=manager)
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
            f"Enable it in AVAILABLE_STRATEGIES to use."
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
        logger.info(f"✅ Создана стратегия: {strategy_info['name']}")
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
    logger.info("📊 ДОСТУПНЫЕ ТОРГОВЫЕ СТРАТЕГИИ")
    logger.info("=" * 80)
    
    available = get_available_strategies()
    disabled = {k: v for k, v in AVAILABLE_STRATEGIES.items() if not v["enabled"] or v["class"] is None}
    
    logger.info(f"\n✅ Активные стратегии: {len(available)}")
    
    for name, info in available.items():
        logger.info(f"\n🔹 {info['name']}")
        logger.info(f"   Описание: {info['description']}")
        logger.info(f"   Категория: {info['category']}")
        logger.info(f"   Таймфреймы: {', '.join(info['timeframes'])}")
        logger.info(f"   Сигналов/день: {info['avg_signals_per_day']}")
        logger.info(f"   Риск: {info['risk_level']}")
    
    if disabled:
        logger.info(f"\n⏳ В разработке: {len(disabled)}")
        for name, info in disabled.items():
            logger.info(f"   • {info['name']}")
    
    logger.info("\n" + "=" * 80)


# ==================== ИНИЦИАЛИЗАЦИЯ МОДУЛЯ ====================

# Выводим информацию при импорте
logger.info("=" * 60)
logger.info("📦 Модуль стратегий загружен")
logger.info(f"   Версия: {__version__}")
logger.info(f"   Активных стратегий: {len(get_available_strategies())}")
logger.info(f"   Всего стратегий: {len(AVAILABLE_STRATEGIES)}")
logger.info("=" * 60)

# Список активных стратегий
active_strategies = [info['name'] for info in get_available_strategies().values()]
if active_strategies:
    logger.info(f"✅ Активные: {', '.join(active_strategies)}")

# Список в разработке
pending_strategies = [
    info['name'] for name, info in AVAILABLE_STRATEGIES.items() 
    if not info['enabled'] or info['class'] is None
]
if pending_strategies:
    logger.info(f"⏳ В разработке: {', '.join(pending_strategies)}")

logger.info("=" * 60)
