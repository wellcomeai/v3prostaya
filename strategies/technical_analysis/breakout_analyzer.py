"""
Breakout Analyzer - Анализатор пробоев уровней

Определяет тип пробоя (настоящий vs ложный) для торговых стратегий.

Типы пробоев:
1. Настоящий пробой (True Breakout) - импульсное движение после преодоления уровня
2. Ложный пробой (False Breakout) - обманный пробой с последующим разворотом
   - Простой ЛП (1 бар)
   - Сильный ЛП (2 бара)
   - Сложный ЛП (3+ бара)

Критерии из стратегии:
- Глубина пробоя ≤ 1/3 ATR для ложного пробоя
- Поджатие перед настоящим пробоем
- Ближний/дальний ретест
- Закрытие у уровня
- Реакция на ЛП

Author: Trading Bot Team
Version: 1.0.0
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum

from .context import SupportResistanceLevel

logger = logging.getLogger(__name__)


class BreakoutType(Enum):
    """Типы пробоев"""
    TRUE_BREAKOUT = "true_breakout"          # Настоящий пробой
    FALSE_BREAKOUT_SIMPLE = "false_simple"   # Простой ЛП (1 бар)
    FALSE_BREAKOUT_STRONG = "false_strong"   # Сильный ЛП (2 бара)
    FALSE_BREAKOUT_COMPLEX = "false_complex" # Сложный ЛП (3+ бара)
    NO_BREAKOUT = "no_breakout"              # Пробоя нет
    UNKNOWN = "unknown"                      # Неопределенный


class BreakoutDirection(Enum):
    """Направление пробоя"""
    UPWARD = "upward"      # Пробой вверх (через сопротивление)
    DOWNWARD = "downward"  # Пробой вниз (через поддержку)
    NONE = "none"


@dataclass
class BreakoutAnalysis:
    """
    Результат анализа пробоя
    
    Attributes:
        breakout_type: Тип пробоя
        direction: Направление пробоя
        strength: Сила пробоя (0.0-1.0)
        confidence: Уверенность в классификации (0.0-1.0)
        level: Уровень который был пробит
        breakout_candle: Свеча пробоя
        breakout_depth: Глубина пробоя в пунктах
        breakout_depth_atr_ratio: Глубина / ATR
        has_compression: Было ли поджатие перед пробоем
        retest_type: Тип ретеста (near/far)
        close_near_level: Закрытие вблизи уровня
        metadata: Дополнительная информация
    """
    breakout_type: BreakoutType
    direction: BreakoutDirection
    strength: float
    confidence: float
    level: Optional[SupportResistanceLevel] = None
    breakout_candle: Any = None
    breakout_depth: float = 0.0
    breakout_depth_atr_ratio: float = 0.0
    has_compression: bool = False
    retest_type: str = "unknown"  # near, far, first
    close_near_level: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_true_breakout(self) -> bool:
        """Является ли настоящим пробоем"""
        return self.breakout_type == BreakoutType.TRUE_BREAKOUT
    
    @property
    def is_false_breakout(self) -> bool:
        """Является ли ложным пробоем"""
        return self.breakout_type in [
            BreakoutType.FALSE_BREAKOUT_SIMPLE,
            BreakoutType.FALSE_BREAKOUT_STRONG,
            BreakoutType.FALSE_BREAKOUT_COMPLEX
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация"""
        return {
            "breakout_type": self.breakout_type.value,
            "direction": self.direction.value,
            "strength": self.strength,
            "confidence": self.confidence,
            "breakout_depth": self.breakout_depth,
            "breakout_depth_atr_ratio": self.breakout_depth_atr_ratio,
            "has_compression": self.has_compression,
            "retest_type": self.retest_type,
            "close_near_level": self.close_near_level,
            "is_true_breakout": self.is_true_breakout,
            "is_false_breakout": self.is_false_breakout,
            "metadata": self.metadata
        }


class BreakoutAnalyzer:
    """
    💥 Анализатор пробоев уровней
    
    Определяет тип пробоя (настоящий vs ложный) на основе:
    - Глубины пробоя
    - Поведения цены после пробоя
    - Предшествующих условий (поджатие, ретест)
    - Реакции на ложный пробой
    
    Usage:
        analyzer = BreakoutAnalyzer()
        
        # Анализ текущего состояния
        analysis = analyzer.analyze_breakout(
            candles=candles_m5,
            level=resistance,
            atr=atr_data.calculated_atr
        )
        
        if analysis.is_true_breakout:
            print(f"Настоящий пробой! Strength: {analysis.strength}")
        elif analysis.is_false_breakout:
            print(f"Ложный пробой: {analysis.breakout_type.value}")
    """
    
    def __init__(
        self,
        # Параметры ложного пробоя
        false_breakout_max_depth_atr: float = 0.33,  # Максимум 1/3 ATR
        false_breakout_tolerance_percent: float = 0.5,  # Допуск для зоны пробоя
        
        # Параметры настоящего пробоя
        true_breakout_min_depth_atr: float = 0.1,    # Минимум 10% ATR
        true_breakout_impulse_threshold: float = 0.5,  # Импульсное движение >0.5% ATR
        
        # Ретест
        near_retest_days: int = 7,                   # Ближний ретест < 7 дней
        far_retest_days: int = 30,                   # Дальний ретест > 30 дней
        
        # Поджатие
        compression_required: bool = True,            # Требовать поджатие для true breakout
    ):
        """
        Инициализация анализатора пробоев
        
        Args:
            false_breakout_max_depth_atr: Макс глубина ЛП (доли ATR)
            false_breakout_tolerance_percent: Допуск зоны пробоя
            true_breakout_min_depth_atr: Мин глубина настоящего пробоя
            true_breakout_impulse_threshold: Порог импульса
            near_retest_days: Дни для ближнего ретеста
            far_retest_days: Дни для дальнего ретеста
            compression_required: Требовать поджатие
        """
        self.false_max_depth_atr = false_breakout_max_depth_atr
        self.false_tolerance = false_breakout_tolerance_percent / 100.0
        
        self.true_min_depth_atr = true_breakout_min_depth_atr
        self.true_impulse = true_breakout_impulse_threshold
        
        self.near_retest_days = near_retest_days
        self.far_retest_days = far_retest_days
        
        self.compression_required = compression_required
        
        # Статистика
        self.stats = {
            "analyses_count": 0,
            "true_breakouts": 0,
            "false_breakouts_simple": 0,
            "false_breakouts_strong": 0,
            "false_breakouts_complex": 0,
            "no_breakouts": 0,
            "average_breakout_strength": 0.0
        }
        
        logger.info("💥 BreakoutAnalyzer инициализирован")
        logger.info(f"   • False breakout max depth: {false_breakout_max_depth_atr} ATR")
        logger.info(f"   • True breakout min depth: {true_breakout_min_depth_atr} ATR")
        logger.info(f"   • Compression required: {compression_required}")
    
    # ==================== ОСНОВНОЙ АНАЛИЗ ====================
    
    def analyze_breakout(
        self,
        candles: List,
        level: SupportResistanceLevel,
        atr: Optional[float] = None,
        current_price: Optional[float] = None,
        has_compression: bool = False,
        lookback: int = 10
    ) -> BreakoutAnalysis:
        """
        🎯 Основной метод анализа пробоя
        
        Анализирует последние свечи на наличие пробоя уровня и определяет его тип.
        
        Args:
            candles: Список свечей (M5, M30, H1)
            level: Уровень для проверки пробоя
            atr: ATR для расчета глубины пробоя
            current_price: Текущая цена
            has_compression: Было ли поджатие перед пробоем
            lookback: Сколько свечей анализировать
            
        Returns:
            BreakoutAnalysis с результатами
        """
        try:
            self.stats["analyses_count"] += 1
            
            if not candles or not level:
                return self._create_no_breakout_result()
            
            # Определяем текущую цену
            if current_price is None:
                current_price = float(candles[-1].close_price)
            
            # Берем последние N свечей
            recent_candles = candles[-lookback:] if len(candles) > lookback else candles
            
            # Проверяем наличие пробоя
            breakout_detected, direction = self._detect_breakout(recent_candles, level, current_price)
            
            if not breakout_detected:
                self.stats["no_breakouts"] += 1
                return self._create_no_breakout_result()
            
            logger.info(f"💥 Пробой обнаружен: {direction.value} через {level.price:.2f}")
            
            # Определяем тип пробоя
            breakout_type = self._classify_breakout_type(
                candles=recent_candles,
                level=level,
                direction=direction,
                atr=atr
            )
            
            # Рассчитываем параметры пробоя
            breakout_candle = self._find_breakout_candle(recent_candles, level, direction)
            breakout_depth = self._calculate_breakout_depth(breakout_candle, level, direction) if breakout_candle else 0.0
            
            depth_atr_ratio = 0.0
            if atr and atr > 0:
                depth_atr_ratio = breakout_depth / atr
            
            # Определяем тип ретеста
            retest_type = self._determine_retest_type(level)
            
            # Проверяем закрытие у уровня
            close_near_level = False
            if breakout_candle:
                close_near_level = self._check_close_near_level(breakout_candle, level)
            
            # Рассчитываем силу и уверенность
            strength = self._calculate_breakout_strength(
                breakout_type=breakout_type,
                depth_atr_ratio=depth_atr_ratio,
                has_compression=has_compression,
                retest_type=retest_type,
                close_near_level=close_near_level
            )
            
            confidence = self._calculate_confidence(
                breakout_type=breakout_type,
                candles=recent_candles,
                level=level,
                direction=direction
            )
            
            # Метаданные
            metadata = {
                "lookback_candles": len(recent_candles),
                "level_strength": level.strength,
                "level_touches": level.touches,
                "analyzed_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Создаем результат
            analysis = BreakoutAnalysis(
                breakout_type=breakout_type,
                direction=direction,
                strength=strength,
                confidence=confidence,
                level=level,
                breakout_candle=breakout_candle,
                breakout_depth=breakout_depth,
                breakout_depth_atr_ratio=depth_atr_ratio,
                has_compression=has_compression,
                retest_type=retest_type,
                close_near_level=close_near_level,
                metadata=metadata
            )
            
            # Обновляем статистику
            self._update_stats(analysis)
            
            logger.info(f"✅ Анализ пробоя завершен: type={breakout_type.value}, "
                       f"strength={strength:.2f}, confidence={confidence:.2f}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа пробоя: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_no_breakout_result()
    
    # ==================== ДЕТЕКЦИЯ ПРОБОЯ ====================
    
    def _detect_breakout(
        self,
        candles: List,
        level: SupportResistanceLevel,
        current_price: float
    ) -> Tuple[bool, BreakoutDirection]:
        """
        Проверка наличия пробоя уровня
        
        Args:
            candles: Список свечей
            level: Уровень
            current_price: Текущая цена
            
        Returns:
            Tuple[пробой обнаружен?, направление]
        """
        try:
            # Проверяем что хотя бы одна свеча пробила уровень
            for candle in candles:
                high = float(candle.high_price)
                low = float(candle.low_price)
                
                # Пробой вверх (через сопротивление)
                if level.level_type == "resistance" and high > level.price:
                    logger.debug(f"💥 Пробой вверх обнаружен: High={high:.2f} > Level={level.price:.2f}")
                    return True, BreakoutDirection.UPWARD
                
                # Пробой вниз (через поддержку)
                if level.level_type == "support" and low < level.price:
                    logger.debug(f"💥 Пробой вниз обнаружен: Low={low:.2f} < Level={level.price:.2f}")
                    return True, BreakoutDirection.DOWNWARD
            
            return False, BreakoutDirection.NONE
            
        except Exception as e:
            logger.error(f"❌ Ошибка детекции пробоя: {e}")
            return False, BreakoutDirection.NONE
    
    def _find_breakout_candle(
        self,
        candles: List,
        level: SupportResistanceLevel,
        direction: BreakoutDirection
    ) -> Optional[Any]:
        """
        Найти свечу пробоя
        
        Args:
            candles: Список свечей
            level: Уровень
            direction: Направление пробоя
            
        Returns:
            Свеча пробоя или None
        """
        try:
            for candle in reversed(candles):
                high = float(candle.high_price)
                low = float(candle.low_price)
                
                if direction == BreakoutDirection.UPWARD and high > level.price:
                    return candle
                
                if direction == BreakoutDirection.DOWNWARD and low < level.price:
                    return candle
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска свечи пробоя: {e}")
            return None
    
    # ==================== КЛАССИФИКАЦИЯ ТИПА ПРОБОЯ ====================
    
    def _classify_breakout_type(
        self,
        candles: List,
        level: SupportResistanceLevel,
        direction: BreakoutDirection,
        atr: Optional[float] = None
    ) -> BreakoutType:
        """
        Классификация типа пробоя
        
        Определяет: настоящий пробой или ложный (простой/сильный/сложный)
        
        Args:
            candles: Список свечей
            level: Уровень
            direction: Направление пробоя
            atr: ATR
            
        Returns:
            Тип пробоя
        """
        try:
            # Проверяем ложный пробой (приоритет)
            
            # 1. Простой ЛП (1 бар)
            simple_false = self._check_simple_false_breakout(candles, level, direction, atr)
            if simple_false:
                logger.info("🔴 Классифицирован как простой ЛП (1 бар)")
                return BreakoutType.FALSE_BREAKOUT_SIMPLE
            
            # 2. Сильный ЛП (2 бара)
            strong_false = self._check_strong_false_breakout(candles, level, direction, atr)
            if strong_false:
                logger.info("🔴 Классифицирован как сильный ЛП (2 бара)")
                return BreakoutType.FALSE_BREAKOUT_STRONG
            
            # 3. Сложный ЛП (3+ бара)
            complex_false = self._check_complex_false_breakout(candles, level, direction, atr)
            if complex_false:
                logger.info("🔴 Классифицирован как сложный ЛП (3+ бара)")
                return BreakoutType.FALSE_BREAKOUT_COMPLEX
            
            # 4. Если не ЛП - проверяем условия настоящего пробоя
            is_true = self._check_true_breakout(candles, level, direction, atr)
            if is_true:
                logger.info("🟢 Классифицирован как настоящий пробой")
                return BreakoutType.TRUE_BREAKOUT
            
            # Если не удалось классифицировать
            logger.warning("⚠️ Тип пробоя неопределен")
            return BreakoutType.UNKNOWN
            
        except Exception as e:
            logger.error(f"❌ Ошибка классификации пробоя: {e}")
            return BreakoutType.UNKNOWN
    
    def _check_simple_false_breakout(
        self,
        candles: List,
        level: SupportResistanceLevel,
        direction: BreakoutDirection,
        atr: Optional[float]
    ) -> bool:
        """
        Проверка простого ЛП (1 бар)
        
        Условия:
        1. Бар пробивает уровень
        2. Бар НЕ закрывается в зоне пробоя (возвращается обратно)
        3. Глубина пробоя ≤ 1/3 ATR
        
        Args:
            candles: Список свечей
            level: Уровень
            direction: Направление
            atr: ATR
            
        Returns:
            True если простой ЛП
        """
        try:
            if not candles:
                return False
            
            last_candle = candles[-1]
            high = float(last_candle.high_price)
            low = float(last_candle.low_price)
            close = float(last_candle.close_price)
            
            # Допуск для зоны пробоя
            tolerance = level.price * self.false_tolerance
            
            # Пробой вверх
            if direction == BreakoutDirection.UPWARD:
                # Проверяем что High пробил уровень
                if high <= level.price:
                    return False
                
                # Проверяем что Close вернулся под уровень
                if close >= (level.price - tolerance):
                    return False  # Закрылся в зоне пробоя
                
                # Проверяем глубину пробоя
                breakout_depth = high - level.price
                
                if atr and atr > 0:
                    depth_ratio = breakout_depth / atr
                    if depth_ratio > self.false_max_depth_atr:
                        return False  # Слишком глубокий пробой
                
                logger.debug(f"✅ Простой ЛП (вверх): пробой {breakout_depth:.2f}, close={close:.2f}")
                return True
            
            # Пробой вниз
            elif direction == BreakoutDirection.DOWNWARD:
                # Проверяем что Low пробил уровень
                if low >= level.price:
                    return False
                
                # Проверяем что Close вернулся над уровень
                if close <= (level.price + tolerance):
                    return False  # Закрылся в зоне пробоя
                
                # Проверяем глубину пробоя
                breakout_depth = level.price - low
                
                if atr and atr > 0:
                    depth_ratio = breakout_depth / atr
                    if depth_ratio > self.false_max_depth_atr:
                        return False  # Слишком глубокий пробой
                
                logger.debug(f"✅ Простой ЛП (вниз): пробой {breakout_depth:.2f}, close={close:.2f}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки простого ЛП: {e}")
            return False
    
    def _check_strong_false_breakout(
        self,
        candles: List,
        level: SupportResistanceLevel,
        direction: BreakoutDirection,
        atr: Optional[float]
    ) -> bool:
        """
        Проверка сильного ЛП (2 бара)
        
        Условия:
        1. Первый бар пробивает И закрывается в зоне пробоя
        2. Второй бар открывается в зоне пробоя
        3. Второй бар закрывается ЗА уровнем (разворот)
        
        Args:
            candles: Список свечей
            level: Уровень
            direction: Направление
            atr: ATR
            
        Returns:
            True если сильный ЛП
        """
        try:
            if len(candles) < 2:
                return False
            
            first_candle = candles[-2]
            second_candle = candles[-1]
            
            tolerance = level.price * self.false_tolerance
            
            # Пробой вверх
            if direction == BreakoutDirection.UPWARD:
                # Первый бар: пробил и закрылся в зоне пробоя
                first_high = float(first_candle.high_price)
                first_close = float(first_candle.close_price)
                
                if first_high <= level.price:
                    return False
                
                if first_close < level.price:
                    return False  # Не закрылся в зоне пробоя
                
                # Второй бар: открылся в зоне пробоя, закрылся под уровнем
                second_open = float(second_candle.open_price)
                second_close = float(second_candle.close_price)
                
                if second_open < level.price:
                    return False  # Не открылся в зоне пробоя
                
                if second_close >= (level.price - tolerance):
                    return False  # Не вернулся под уровень
                
                logger.debug(f"✅ Сильный ЛП (вверх): 2 бара с разворотом")
                return True
            
            # Пробой вниз
            elif direction == BreakoutDirection.DOWNWARD:
                # Первый бар: пробил и закрылся в зоне пробоя
                first_low = float(first_candle.low_price)
                first_close = float(first_candle.close_price)
                
                if first_low >= level.price:
                    return False
                
                if first_close > level.price:
                    return False  # Не закрылся в зоне пробоя
                
                # Второй бар: открылся в зоне пробоя, закрылся над уровнем
                second_open = float(second_candle.open_price)
                second_close = float(second_candle.close_price)
                
                if second_open > level.price:
                    return False  # Не открылся в зоне пробоя
                
                if second_close <= (level.price + tolerance):
                    return False  # Не вернулся над уровень
                
                logger.debug(f"✅ Сильный ЛП (вниз): 2 бара с разворотом")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки сильного ЛП: {e}")
            return False
    
    def _check_complex_false_breakout(
        self,
        candles: List,
        level: SupportResistanceLevel,
        direction: BreakoutDirection,
        atr: Optional[float]
    ) -> bool:
        """
        Проверка сложного ЛП (3+ бара)
        
        Условия:
        1. Первый бар пробивает И закрывается в зоне пробоя
        2. Минимум 3 следующих бара открываются/закрываются в зоне пробоя
        3. Последний бар закрывается ЗА уровнем (разворот)
        
        Args:
            candles: Список свечей
            level: Уровень
            direction: Направление
            atr: ATR
            
        Returns:
            True если сложный ЛП
        """
        try:
            if len(candles) < 4:
                return False
            
            tolerance = level.price * self.false_tolerance
            
            # Берем последние 4+ бара
            recent = candles[-4:]
            
            # Первый бар должен пробить и закрыться в зоне
            first = recent[0]
            
            if direction == BreakoutDirection.UPWARD:
                if float(first.high_price) <= level.price:
                    return False
                if float(first.close_price) < level.price:
                    return False
            elif direction == BreakoutDirection.DOWNWARD:
                if float(first.low_price) >= level.price:
                    return False
                if float(first.close_price) > level.price:
                    return False
            
            # Следующие 2+ бара в зоне пробоя
            middle_bars = recent[1:-1]
            
            for bar in middle_bars:
                bar_open = float(bar.open_price)
                bar_close = float(bar.close_price)
                
                if direction == BreakoutDirection.UPWARD:
                    # Должны быть в зоне пробоя (выше уровня)
                    if bar_open < level.price or bar_close < level.price:
                        return False
                elif direction == BreakoutDirection.DOWNWARD:
                    # Должны быть в зоне пробоя (ниже уровня)
                    if bar_open > level.price or bar_close > level.price:
                        return False
            
            # Последний бар - разворот
            last = recent[-1]
            last_close = float(last.close_price)
            
            if direction == BreakoutDirection.UPWARD:
                if last_close >= (level.price - tolerance):
                    return False  # Не вернулся
            elif direction == BreakoutDirection.DOWNWARD:
                if last_close <= (level.price + tolerance):
                    return False  # Не вернулся
            
            logger.debug(f"✅ Сложный ЛП: {len(middle_bars)+2} баров с консолидацией")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки сложного ЛП: {e}")
            return False
    
    def _check_true_breakout(
        self,
        candles: List,
        level: SupportResistanceLevel,
        direction: BreakoutDirection,
        atr: Optional[float]
    ) -> bool:
        """
        Проверка условий настоящего пробоя
        
        Признаки настоящего пробоя:
        1. Глубина пробоя достаточная (>10% ATR)
        2. Импульсное движение после пробоя
        3. Не возвращается к уровню
        
        Args:
            candles: Список свечей
            level: Уровень
            direction: Направление
            atr: ATR
            
        Returns:
            True если настоящий пробой
        """
        try:
            if not candles:
                return False
            
            # Находим свечу пробоя
            breakout_candle = None
            for candle in reversed(candles):
                high = float(candle.high_price)
                low = float(candle.low_price)
                
                if direction == BreakoutDirection.UPWARD and high > level.price:
                    breakout_candle = candle
                    break
                elif direction == BreakoutDirection.DOWNWARD and low < level.price:
                    breakout_candle = candle
                    break
            
            if not breakout_candle:
                return False
            
            # Рассчитываем глубину пробоя
            if direction == BreakoutDirection.UPWARD:
                depth = float(breakout_candle.high_price) - level.price
            else:
                depth = level.price - float(breakout_candle.low_price)
            
            # Проверяем минимальную глубину
            if atr and atr > 0:
                depth_ratio = depth / atr
                if depth_ratio < self.true_min_depth_atr:
                    logger.debug(f"⚠️ Недостаточная глубина пробоя: {depth_ratio:.2f} < {self.true_min_depth_atr}")
                    return False
            
            # Проверяем что цена не вернулась к уровню
            tolerance = level.price * 0.01  # 1%
            
            for candle in candles[candles.index(breakout_candle)+1:]:
                close = float(candle.close_price)
                
                if direction == BreakoutDirection.UPWARD:
                    if close < (level.price + tolerance):
                        logger.debug(f"⚠️ Цена вернулась к уровню после пробоя")
                        return False
                elif direction == BreakoutDirection.DOWNWARD:
                    if close > (level.price - tolerance):
                        logger.debug(f"⚠️ Цена вернулась к уровню после пробоя")
                        return False
            
            logger.debug(f"✅ Условия настоящего пробоя выполнены")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки настоящего пробоя: {e}")
            return False
    
    # ==================== РАСЧЕТЫ ====================
    
    def _calculate_breakout_depth(
        self,
        candle: Any,
        level: SupportResistanceLevel,
        direction: BreakoutDirection
    ) -> float:
        """Расчет глубины пробоя в пунктах"""
        try:
            if direction == BreakoutDirection.UPWARD:
                return float(candle.high_price) - level.price
            elif direction == BreakoutDirection.DOWNWARD:
                return level.price - float(candle.low_price)
            return 0.0
        except:
            return 0.0
    
    def _calculate_breakout_strength(
        self,
        breakout_type: BreakoutType,
        depth_atr_ratio: float,
        has_compression: bool,
        retest_type: str,
        close_near_level: bool
    ) -> float:
        """
        Расчет силы пробоя (0.0-1.0)
        
        Факторы:
        - Тип пробоя (настоящий = сильнее)
        - Глубина относительно ATR
        - Наличие поджатия
        - Тип ретеста
        - Закрытие у уровня
        """
        try:
            # Базовая сила по типу
            if breakout_type == BreakoutType.TRUE_BREAKOUT:
                base_strength = 0.7
            elif breakout_type in [BreakoutType.FALSE_BREAKOUT_STRONG, BreakoutType.FALSE_BREAKOUT_COMPLEX]:
                base_strength = 0.5
            elif breakout_type == BreakoutType.FALSE_BREAKOUT_SIMPLE:
                base_strength = 0.3
            else:
                base_strength = 0.1
            
            # Бонус за глубину (для настоящего пробоя)
            if breakout_type == BreakoutType.TRUE_BREAKOUT:
                if depth_atr_ratio > 0.5:
                    base_strength += 0.15
                elif depth_atr_ratio > 0.3:
                    base_strength += 0.10
            
            # Бонус за поджатие
            if has_compression:
                base_strength += 0.10
            
            # Бонус за ближний ретест
            if retest_type == "near":
                base_strength += 0.05
            
            # Бонус за закрытие у уровня
            if close_near_level and breakout_type == BreakoutType.TRUE_BREAKOUT:
                base_strength += 0.05
            
            return min(1.0, base_strength)
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета силы: {e}")
            return 0.5
    
    def _calculate_confidence(
        self,
        breakout_type: BreakoutType,
        candles: List,
        level: SupportResistanceLevel,
        direction: BreakoutDirection
    ) -> float:
        """Расчет уверенности в классификации"""
        try:
            # Базовая уверенность
            if breakout_type in [BreakoutType.TRUE_BREAKOUT, BreakoutType.FALSE_BREAKOUT_SIMPLE]:
                confidence = 0.8
            elif breakout_type in [BreakoutType.FALSE_BREAKOUT_STRONG, BreakoutType.FALSE_BREAKOUT_COMPLEX]:
                confidence = 0.7
            else:
                confidence = 0.5
            
            # Бонус за сильный уровень
            if level.is_strong:
                confidence += 0.1
            
            # Бонус за множественные касания
            if level.touches >= 3:
                confidence += 0.05
            
            return min(1.0, confidence)
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета уверенности: {e}")
            return 0.5
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================
    
    def _determine_retest_type(self, level: SupportResistanceLevel) -> str:
        """
        Определение типа ретеста
        
        Returns:
            "near" - ближний ретест (<7 дней)
            "far" - дальний ретест (>30 дней)
            "medium" - средний ретест
            "first" - первое касание
        """
        try:
            if not level.last_touch:
                return "first"
            
            days_since_touch = (datetime.now(timezone.utc) - level.last_touch).days
            
            if days_since_touch < self.near_retest_days:
                return "near"
            elif days_since_touch > self.far_retest_days:
                return "far"
            else:
                return "medium"
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения типа ретеста: {e}")
            return "unknown"
    
    def _check_close_near_level(
        self,
        candle: Any,
        level: SupportResistanceLevel,
        tolerance_percent: float = 0.5
    ) -> bool:
        """Проверка закрытия вблизи уровня"""
        try:
            close = float(candle.close_price)
            distance_percent = abs(close - level.price) / level.price * 100
            return distance_percent <= tolerance_percent
        except:
            return False
    
    def _create_no_breakout_result(self) -> BreakoutAnalysis:
        """Создание результата 'нет пробоя'"""
        return BreakoutAnalysis(
            breakout_type=BreakoutType.NO_BREAKOUT,
            direction=BreakoutDirection.NONE,
            strength=0.0,
            confidence=0.0
        )
    
    # ==================== СТАТИСТИКА ====================
    
    def _update_stats(self, analysis: BreakoutAnalysis):
        """Обновление статистики"""
        if analysis.breakout_type == BreakoutType.TRUE_BREAKOUT:
            self.stats["true_breakouts"] += 1
        elif analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_SIMPLE:
            self.stats["false_breakouts_simple"] += 1
        elif analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_STRONG:
            self.stats["false_breakouts_strong"] += 1
        elif analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_COMPLEX:
            self.stats["false_breakouts_complex"] += 1
        
        # Средняя сила
        count = self.stats["analyses_count"]
        prev_avg = self.stats["average_breakout_strength"]
        self.stats["average_breakout_strength"] = (prev_avg * (count - 1) + analysis.strength) / count
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику"""
        return {
            **self.stats,
            "config": {
                "false_max_depth_atr": self.false_max_depth_atr,
                "true_min_depth_atr": self.true_min_depth_atr,
                "near_retest_days": self.near_retest_days,
                "far_retest_days": self.far_retest_days,
                "compression_required": self.compression_required
            }
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.stats = {
            "analyses_count": 0,
            "true_breakouts": 0,
            "false_breakouts_simple": 0,
            "false_breakouts_strong": 0,
            "false_breakouts_complex": 0,
            "no_breakouts": 0,
            "average_breakout_strength": 0.0
        }
        logger.info("🔄 Статистика BreakoutAnalyzer сброшена")
    
    def __repr__(self) -> str:
        return (f"BreakoutAnalyzer(analyses={self.stats['analyses_count']}, "
                f"true={self.stats['true_breakouts']}, "
                f"false={self.stats['false_breakouts_simple']}/"
                f"{self.stats['false_breakouts_strong']}/"
                f"{self.stats['false_breakouts_complex']})")
    
    def __str__(self) -> str:
        stats = self.get_stats()
        return (f"Breakout Analyzer:\n"
                f"  Analyses: {stats['analyses_count']}\n"
                f"  True breakouts: {stats['true_breakouts']}\n"
                f"  False breakouts: simple={stats['false_breakouts_simple']}, "
                f"strong={stats['false_breakouts_strong']}, "
                f"complex={stats['false_breakouts_complex']}\n"
                f"  Average strength: {stats['average_breakout_strength']:.2f}")


# Export
__all__ = [
    "BreakoutAnalyzer",
    "BreakoutAnalysis",
    "BreakoutType",
    "BreakoutDirection"
]

logger.info("✅ Breakout Analyzer module loaded")
