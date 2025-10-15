"""
Technical Analysis Context

Структуры данных для кэширования технического анализа.
Хранит уровни, ATR, свечи и индикаторы с автоматической валидацией кэша.

Author: Trading Bot Team
Version: 1.0.0
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class MarketCondition(Enum):
    """Состояние рынка"""
    CONSOLIDATION = "consolidation"  # Консолидация
    TRENDING = "trending"            # Трендовое движение
    VOLATILE = "volatile"            # Волатильный
    NEUTRAL = "neutral"              # Нейтральный
    UNKNOWN = "unknown"              # Неизвестно


class TrendDirection(Enum):
    """Направление тренда"""
    BULLISH = "bullish"    # Бычий
    BEARISH = "bearish"    # Медвежий
    NEUTRAL = "neutral"    # Боковик
    UNKNOWN = "unknown"    # Неизвестно


@dataclass
class SupportResistanceLevel:
    """
    Уровень поддержки/сопротивления
    
    Attributes:
        price: Цена уровня
        level_type: Тип уровня (support/resistance)
        strength: Сила уровня (0.0-1.0)
        touches: Количество касаний
        last_touch: Время последнего касания
        created_at: Время создания уровня (БСУ)
        distance_from_current: Расстояние от текущей цены (%)
        metadata: Дополнительная информация
    """
    price: float
    level_type: str  # "support" или "resistance"
    strength: float  # 0.0 - 1.0
    touches: int = 0
    last_touch: Optional[datetime] = None
    created_at: Optional[datetime] = None
    distance_from_current: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Валидация данных"""
        if self.price <= 0:
            raise ValueError(f"Invalid price: {self.price}")
        if not 0 <= self.strength <= 1:
            raise ValueError(f"Invalid strength: {self.strength}")
        if self.level_type not in ["support", "resistance"]:
            raise ValueError(f"Invalid level_type: {self.level_type}")
    
    @property
    def is_strong(self) -> bool:
        """Является ли уровень сильным (>0.7)"""
        return self.strength >= 0.7
    
    @property
    def is_recent(self, hours: int = 168) -> bool:
        """Было ли касание недавно (по умолчанию 1 неделя)"""
        if not self.last_touch:
            return False
        age = datetime.now(timezone.utc) - self.last_touch
        return age < timedelta(hours=hours)
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь"""
        return {
            "price": self.price,
            "level_type": self.level_type,
            "strength": self.strength,
            "touches": self.touches,
            "last_touch": self.last_touch.isoformat() if self.last_touch else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "distance_from_current": self.distance_from_current,
            "is_strong": self.is_strong,
            "is_recent": self.is_recent,
            "metadata": self.metadata
        }


@dataclass
class ATRData:
    """
    Данные Average True Range
    
    Attributes:
        calculated_atr: Расчетный ATR (среднее High-Low)
        technical_atr: Технический ATR (расстояние между уровнями)
        atr_percent: ATR в процентах от цены
        current_range_used: Использовано диапазона сегодня (%)
        is_exhausted: Исчерпан ли запас хода (>75%)
        last_5_ranges: Диапазоны последних 5 дней
        updated_at: Время обновления
    """
    calculated_atr: float
    technical_atr: float
    atr_percent: float
    current_range_used: float = 0.0
    is_exhausted: bool = False
    last_5_ranges: List[float] = field(default_factory=list)
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Валидация"""
        if self.calculated_atr < 0:
            raise ValueError(f"Invalid calculated_atr: {self.calculated_atr}")
        if self.technical_atr < 0:
            raise ValueError(f"Invalid technical_atr: {self.technical_atr}")
    
    @property
    def is_valid(self) -> bool:
        """Проверка валидности данных"""
        return self.calculated_atr > 0 and self.technical_atr > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация"""
        return {
            "calculated_atr": self.calculated_atr,
            "technical_atr": self.technical_atr,
            "atr_percent": self.atr_percent,
            "current_range_used": self.current_range_used,
            "is_exhausted": self.is_exhausted,
            "last_5_ranges": self.last_5_ranges,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


@dataclass
class TechnicalAnalysisContext:
    """
    🧠 Контекст технического анализа с кэшированием
    
    Централизованное хранилище всех данных технического анализа:
    - Уровни поддержки/сопротивления (D1)
    - ATR и запас хода
    - Последние свечи всех таймфреймов
    - Предрасчитанные индикаторы
    - Рыночные условия
    
    Кэширование:
    - levels_d1: обновление раз в 24 часа
    - atr_data: обновление раз в час
    - candles: обновление каждую минуту
    
    Usage:
        context = await ta_manager.get_context("BTCUSDT")
        levels = context.levels_d1
        atr = context.atr_data.calculated_atr
        candles = context.recent_candles_m5
    """
    
    # Основные данные
    symbol: str
    data_source: str = "bybit"  # bybit, yfinance, etc.
    
    # ==================== УРОВНИ D1 ====================
    levels_d1: List[SupportResistanceLevel] = field(default_factory=list)
    levels_updated_at: Optional[datetime] = None
    levels_cache_ttl_hours: int = 24
    
    # ==================== ATR ====================
    atr_data: Optional[ATRData] = None
    atr_cache_ttl_hours: int = 1
    
    # ==================== СВЕЧИ ====================
    recent_candles_m5: List = field(default_factory=list)   # 100 свечей (8 часов)
    recent_candles_m30: List = field(default_factory=list)  # 50 свечей (25 часов)
    recent_candles_h1: List = field(default_factory=list)   # 24 свечи (1 день)
    recent_candles_h4: List = field(default_factory=list)   # 24 свечи (4 дня)
    recent_candles_d1: List = field(default_factory=list)   # 180 свечей (6 месяцев)
    candles_updated_at: Optional[datetime] = None
    candles_cache_ttl_minutes: int = 1
    
    # ==================== ПРЕДРАСЧИТАННЫЕ ИНДИКАТОРЫ ====================
    market_condition: MarketCondition = MarketCondition.UNKNOWN
    dominant_trend_h1: TrendDirection = TrendDirection.UNKNOWN
    dominant_trend_d1: TrendDirection = TrendDirection.UNKNOWN
    
    volatility_level: str = "normal"  # low, normal, high, extreme
    consolidation_detected: bool = False
    consolidation_bars_count: int = 0
    
    # Дополнительные флаги
    has_recent_breakout: bool = False
    has_compression: bool = False  # Поджатие
    has_v_formation: bool = False  # V-образная формация
    
    # ==================== МЕТАДАННЫЕ ====================
    context_created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_full_update: Optional[datetime] = None
    update_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    
    # ==================== КЭШИРОВАНИЕ ====================
    
    def is_levels_cache_valid(self) -> bool:
        """Проверка валидности кэша уровней"""
        if not self.levels_updated_at:
            return False
        age = datetime.now(timezone.utc) - self.levels_updated_at
        return age < timedelta(hours=self.levels_cache_ttl_hours)
    
    def is_atr_cache_valid(self) -> bool:
        """Проверка валидности кэша ATR"""
        if not self.atr_data or not self.atr_data.updated_at:
            return False
        age = datetime.now(timezone.utc) - self.atr_data.updated_at
        return age < timedelta(hours=self.atr_cache_ttl_hours)
    
    def is_candles_cache_valid(self) -> bool:
        """Проверка валидности кэша свечей"""
        if not self.candles_updated_at:
            return False
        age = datetime.now(timezone.utc) - self.candles_updated_at
        return age < timedelta(minutes=self.candles_cache_ttl_minutes)
    
    def is_fully_initialized(self) -> bool:
        """Проверка полной инициализации контекста"""
        return (
            len(self.levels_d1) > 0 and
            self.atr_data is not None and
            len(self.recent_candles_d1) > 0 and
            len(self.recent_candles_h1) > 0 and
            len(self.recent_candles_m5) > 0
        )
    
    # ==================== ПОИСК УРОВНЕЙ ====================
    
    def get_nearest_support(self, current_price: float, max_distance_percent: float = 5.0) -> Optional[SupportResistanceLevel]:
        """
        Найти ближайший уровень поддержки ниже текущей цены
        
        Args:
            current_price: Текущая цена
            max_distance_percent: Максимальное расстояние в %
            
        Returns:
            Ближайший уровень поддержки или None
        """
        supports = [
            level for level in self.levels_d1
            if level.level_type == "support" and level.price < current_price
        ]
        
        if not supports:
            return None
        
        # Сортируем по расстоянию от текущей цены
        supports.sort(key=lambda l: abs(l.price - current_price))
        
        nearest = supports[0]
        distance_percent = abs(nearest.price - current_price) / current_price * 100
        
        if distance_percent <= max_distance_percent:
            return nearest
        
        return None
    
    def get_nearest_resistance(self, current_price: float, max_distance_percent: float = 5.0) -> Optional[SupportResistanceLevel]:
        """
        Найти ближайший уровень сопротивления выше текущей цены
        
        Args:
            current_price: Текущая цена
            max_distance_percent: Максимальное расстояние в %
            
        Returns:
            Ближайший уровень сопротивления или None
        """
        resistances = [
            level for level in self.levels_d1
            if level.level_type == "resistance" and level.price > current_price
        ]
        
        if not resistances:
            return None
        
        # Сортируем по расстоянию
        resistances.sort(key=lambda l: abs(l.price - current_price))
        
        nearest = resistances[0]
        distance_percent = abs(nearest.price - current_price) / current_price * 100
        
        if distance_percent <= max_distance_percent:
            return nearest
        
        return None
    
    def get_strong_levels(self, min_strength: float = 0.7) -> List[SupportResistanceLevel]:
        """Получить все сильные уровни"""
        return [level for level in self.levels_d1 if level.strength >= min_strength]
    
    def is_near_level(self, current_price: float, tolerance_percent: float = 0.5) -> Optional[SupportResistanceLevel]:
        """
        Проверить, находится ли цена рядом с каким-либо уровнем
        
        Args:
            current_price: Текущая цена
            tolerance_percent: Допуск в процентах (0.5% по умолчанию)
            
        Returns:
            Уровень если рядом, иначе None
        """
        for level in self.levels_d1:
            distance_percent = abs(level.price - current_price) / current_price * 100
            if distance_percent <= tolerance_percent:
                return level
        return None
    
    # ==================== ATR ПРОВЕРКИ ====================
    
    def is_atr_exhausted(self, threshold: float = 0.75) -> bool:
        """
        Проверить, исчерпан ли запас хода (>75% ATR)
        
        Args:
            threshold: Порог в долях (0.75 = 75%)
        """
        if not self.atr_data:
            return False
        return self.atr_data.current_range_used >= threshold
    
    def get_remaining_atr_percent(self) -> float:
        """Получить оставшийся процент ATR"""
        if not self.atr_data:
            return 0.0
        return max(0.0, 100.0 - self.atr_data.current_range_used)
    
    # ==================== СТАТИСТИКА ====================
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Получить статус всех кэшей"""
        return {
            "levels_valid": self.is_levels_cache_valid(),
            "levels_age_hours": (datetime.now(timezone.utc) - self.levels_updated_at).total_seconds() / 3600 if self.levels_updated_at else None,
            "atr_valid": self.is_atr_cache_valid(),
            "atr_age_hours": (datetime.now(timezone.utc) - self.atr_data.updated_at).total_seconds() / 3600 if self.atr_data and self.atr_data.updated_at else None,
            "candles_valid": self.is_candles_cache_valid(),
            "candles_age_minutes": (datetime.now(timezone.utc) - self.candles_updated_at).total_seconds() / 60 if self.candles_updated_at else None,
            "fully_initialized": self.is_fully_initialized()
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Получить краткую сводку контекста"""
        return {
            "symbol": self.symbol,
            "data_source": self.data_source,
            "levels_count": len(self.levels_d1),
            "strong_levels_count": len(self.get_strong_levels()),
            "atr_calculated": self.atr_data.calculated_atr if self.atr_data else 0.0,
            "atr_exhausted": self.is_atr_exhausted(),
            "market_condition": self.market_condition.value,
            "trend_h1": self.dominant_trend_h1.value,
            "trend_d1": self.dominant_trend_d1.value,
            "has_compression": self.has_compression,
            "consolidation_detected": self.consolidation_detected,
            "update_count": self.update_count,
            "error_count": self.error_count,
            "cache_status": self.get_cache_status()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Полная сериализация в словарь"""
        return {
            "symbol": self.symbol,
            "data_source": self.data_source,
            "levels_d1": [level.to_dict() for level in self.levels_d1],
            "levels_updated_at": self.levels_updated_at.isoformat() if self.levels_updated_at else None,
            "atr_data": self.atr_data.to_dict() if self.atr_data else None,
            "candles_count": {
                "m5": len(self.recent_candles_m5),
                "m30": len(self.recent_candles_m30),
                "h1": len(self.recent_candles_h1),
                "h4": len(self.recent_candles_h4),
                "d1": len(self.recent_candles_d1)
            },
            "candles_updated_at": self.candles_updated_at.isoformat() if self.candles_updated_at else None,
            "market_condition": self.market_condition.value,
            "dominant_trend_h1": self.dominant_trend_h1.value,
            "dominant_trend_d1": self.dominant_trend_d1.value,
            "volatility_level": self.volatility_level,
            "consolidation_detected": self.consolidation_detected,
            "has_compression": self.has_compression,
            "has_v_formation": self.has_v_formation,
            "context_created_at": self.context_created_at.isoformat(),
            "last_full_update": self.last_full_update.isoformat() if self.last_full_update else None,
            "update_count": self.update_count,
            "error_count": self.error_count,
            "cache_status": self.get_cache_status()
        }
    
    def __repr__(self) -> str:
        """Строковое представление для отладки"""
        status = "✅ initialized" if self.is_fully_initialized() else "⚠️ partial"
        return (f"TechnicalAnalysisContext(symbol='{self.symbol}', "
                f"levels={len(self.levels_d1)}, "
                f"atr={self.atr_data.calculated_atr if self.atr_data else 0:.2f}, "
                f"status={status})")
    
    def __str__(self) -> str:
        """Человекочитаемое представление"""
        summary = self.get_summary()
        return (f"Technical Analysis Context for {self.symbol}:\n"
                f"  Levels: {summary['levels_count']} total, {summary['strong_levels_count']} strong\n"
                f"  ATR: {summary['atr_calculated']:.2f} (exhausted: {summary['atr_exhausted']})\n"
                f"  Market: {summary['market_condition']}\n"
                f"  Trend H1: {summary['trend_h1']}, D1: {summary['trend_d1']}\n"
                f"  Updates: {summary['update_count']}, Errors: {summary['error_count']}")


# Export
__all__ = [
    "TechnicalAnalysisContext",
    "SupportResistanceLevel",
    "ATRData",
    "MarketCondition",
    "TrendDirection"
]

logger.info("✅ Technical Analysis Context module loaded")
