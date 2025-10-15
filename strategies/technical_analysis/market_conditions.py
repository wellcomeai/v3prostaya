"""
Market Conditions Analyzer - Анализатор рыночных условий

Определяет текущее состояние рынка для выбора торговой стратегии:
1. Консолидация - накопление энергии для пробоя
2. Волатильность - уровень колебаний цены
3. Тренд - направление и сила движения
4. Энергия - накоплена ли энергия для пробоя
5. V-формация - резкий разворот без консолидации
6. Рыночный режим - trending/consolidation/volatile

Используется для:
- Выбора подходящей стратегии (пробой vs отбой)
- Фильтрации сигналов по условиям рынка
- Адаптации параметров под текущие условия

Author: Trading Bot Team
Version: 1.0.0
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
from statistics import mean, stdev

from .context import MarketCondition, TrendDirection

logger = logging.getLogger(__name__)


class VolatilityLevel(Enum):
    """Уровень волатильности"""
    VERY_LOW = "very_low"      # < 0.5% диапазон
    LOW = "low"                # 0.5% - 1%
    NORMAL = "normal"          # 1% - 2%
    HIGH = "high"              # 2% - 4%
    EXTREME = "extreme"        # > 4%


class EnergyLevel(Enum):
    """Уровень накопленной энергии"""
    DEPLETED = "depleted"      # Энергия исчерпана
    LOW = "low"                # Низкая энергия
    MODERATE = "moderate"      # Умеренная энергия
    HIGH = "high"              # Высокая энергия (готов к пробою)
    EXPLOSIVE = "explosive"    # Взрывная энергия


class TrendStrength(Enum):
    """Сила тренда"""
    VERY_WEAK = "very_weak"    # < 0.5%
    WEAK = "weak"              # 0.5% - 1%
    MODERATE = "moderate"      # 1% - 2%
    STRONG = "strong"          # 2% - 5%
    VERY_STRONG = "very_strong"  # > 5%


@dataclass
class MarketConditionsAnalysis:
    """
    Результат анализа рыночных условий
    
    Attributes:
        market_condition: Общее состояние рынка
        trend_direction: Направление тренда
        trend_strength: Сила тренда
        volatility_level: Уровень волатильности
        energy_level: Уровень накопленной энергии
        has_consolidation: Наличие консолидации
        consolidation_bars: Количество баров в консолидации
        has_v_formation: Наличие V-формации
        is_suitable_for_breakout: Подходит для стратегии пробоя
        is_suitable_for_bounce: Подходит для стратегии отбоя
        is_suitable_for_false_breakout: Подходит для ЛП стратегии
        metadata: Дополнительная информация
    """
    market_condition: MarketCondition
    trend_direction: TrendDirection
    trend_strength: TrendStrength
    volatility_level: VolatilityLevel
    energy_level: EnergyLevel
    
    has_consolidation: bool = False
    consolidation_bars: int = 0
    consolidation_range_percent: float = 0.0
    
    has_v_formation: bool = False
    v_formation_type: Optional[str] = None
    
    is_suitable_for_breakout: bool = False
    is_suitable_for_bounce: bool = False
    is_suitable_for_false_breakout: bool = False
    
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация"""
        return {
            "market_condition": self.market_condition.value,
            "trend_direction": self.trend_direction.value,
            "trend_strength": self.trend_strength.value,
            "volatility_level": self.volatility_level.value,
            "energy_level": self.energy_level.value,
            "has_consolidation": self.has_consolidation,
            "consolidation_bars": self.consolidation_bars,
            "consolidation_range_percent": self.consolidation_range_percent,
            "has_v_formation": self.has_v_formation,
            "v_formation_type": self.v_formation_type,
            "is_suitable_for_breakout": self.is_suitable_for_breakout,
            "is_suitable_for_bounce": self.is_suitable_for_bounce,
            "is_suitable_for_false_breakout": self.is_suitable_for_false_breakout,
            "confidence": self.confidence,
            "metadata": self.metadata
        }


class MarketConditionsAnalyzer:
    """
    🌡️ Анализатор рыночных условий
    
    Определяет текущее состояние рынка для выбора торговой стратегии:
    - Консолидация vs Тренд
    - Волатильность
    - Накопленная энергия
    - Подходящие стратегии
    
    Usage:
        analyzer = MarketConditionsAnalyzer()
        
        # Анализ условий на H1 и D1
        conditions = analyzer.analyze_conditions(
            candles_h1=candles_h1,
            candles_d1=candles_d1,
            atr=atr_data.calculated_atr
        )
        
        # Выбор стратегии
        if conditions.is_suitable_for_breakout:
            strategy = BreakoutStrategy()
        elif conditions.is_suitable_for_bounce:
            strategy = BounceStrategy()
    """
    
    def __init__(
        self,
        # Параметры консолидации
        consolidation_min_bars: int = 10,
        consolidation_max_range_percent: float = 2.0,
        consolidation_energy_threshold: int = 15,  # Баров для высокой энергии
        
        # Параметры волатильности
        volatility_very_low: float = 0.5,
        volatility_low: float = 1.0,
        volatility_normal: float = 2.0,
        volatility_high: float = 4.0,
        
        # Параметры тренда
        trend_weak: float = 0.5,
        trend_moderate: float = 1.0,
        trend_strong: float = 2.0,
        trend_very_strong: float = 5.0,
        
        # V-формация
        v_formation_min_move: float = 3.0,
    ):
        """
        Инициализация анализатора рыночных условий
        
        Args:
            consolidation_min_bars: Минимум баров для консолидации
            consolidation_max_range_percent: Максимальный диапазон консолидации
            consolidation_energy_threshold: Баров для высокой энергии
            volatility_very_low: Порог очень низкой волатильности
            volatility_low: Порог низкой волатильности
            volatility_normal: Порог нормальной волатильности
            volatility_high: Порог высокой волатильности
            trend_weak: Порог слабого тренда
            trend_moderate: Порог умеренного тренда
            trend_strong: Порог сильного тренда
            trend_very_strong: Порог очень сильного тренда
            v_formation_min_move: Минимальное движение для V-формации
        """
        self.consolidation_min_bars = consolidation_min_bars
        self.consolidation_max_range = consolidation_max_range_percent / 100.0
        self.consolidation_energy_threshold = consolidation_energy_threshold
        
        self.vol_very_low = volatility_very_low / 100.0
        self.vol_low = volatility_low / 100.0
        self.vol_normal = volatility_normal / 100.0
        self.vol_high = volatility_high / 100.0
        
        self.trend_weak = trend_weak / 100.0
        self.trend_moderate = trend_moderate / 100.0
        self.trend_strong = trend_strong / 100.0
        self.trend_very_strong = trend_very_strong / 100.0
        
        self.v_min_move = v_formation_min_move / 100.0
        
        # Статистика
        self.stats = {
            "analyses_count": 0,
            "consolidations_detected": 0,
            "trends_detected": 0,
            "v_formations_detected": 0,
            "high_energy_detected": 0,
            "high_volatility_detected": 0
        }
        
        logger.info("🌡️ MarketConditionsAnalyzer инициализирован")
        logger.info(f"   • Consolidation: min_bars={consolidation_min_bars}, "
                   f"max_range={consolidation_max_range_percent}%")
        logger.info(f"   • Energy threshold: {consolidation_energy_threshold} bars")
    
    # ==================== ОСНОВНОЙ АНАЛИЗ ====================
    
    def analyze_conditions(
        self,
        candles_h1: Optional[List] = None,
        candles_d1: Optional[List] = None,
        atr: Optional[float] = None,
        current_price: Optional[float] = None
    ) -> MarketConditionsAnalysis:
        """
        🎯 Основной метод анализа рыночных условий
        
        Анализирует:
        1. Тренд (направление и сила)
        2. Волатильность
        3. Консолидацию
        4. Энергию
        5. V-формацию
        6. Подходящие стратегии
        
        Args:
            candles_h1: Свечи H1 для краткосрочного анализа
            candles_d1: Свечи D1 для долгосрочного анализа
            atr: ATR для расчетов
            current_price: Текущая цена
            
        Returns:
            MarketConditionsAnalysis с результатами
        """
        try:
            self.stats["analyses_count"] += 1
            
            # Используем H1 как основной таймфрейм
            primary_candles = candles_h1 or candles_d1
            
            if not primary_candles or len(primary_candles) < 10:
                return self._create_default_analysis()
            
            # Определяем текущую цену
            if current_price is None:
                current_price = float(primary_candles[-1]['close_price'])
            
            # 1. ТРЕНД (направление и сила)
            trend_direction, trend_strength = self._analyze_trend(primary_candles)
            
            # 2. ВОЛАТИЛЬНОСТЬ
            volatility_level = self._analyze_volatility(primary_candles, atr)
            
            # 3. КОНСОЛИДАЦИЯ
            has_consolidation, consol_bars, consol_range = self._analyze_consolidation(primary_candles)
            
            # 4. ЭНЕРГИЯ (накоплена ли для пробоя)
            energy_level = self._analyze_energy(
                candles=primary_candles,
                has_consolidation=has_consolidation,
                consolidation_bars=consol_bars
            )
            
            # 5. V-ФОРМАЦИЯ
            has_v, v_type = self._analyze_v_formation(primary_candles)
            
            # 6. ОБЩЕЕ СОСТОЯНИЕ РЫНКА
            market_condition = self._determine_market_condition(
                has_consolidation=has_consolidation,
                trend_strength=trend_strength,
                volatility_level=volatility_level
            )
            
            # 7. ПОДХОДЯЩИЕ СТРАТЕГИИ
            suitable_breakout = self._is_suitable_for_breakout(
                has_consolidation=has_consolidation,
                energy_level=energy_level,
                trend_strength=trend_strength
            )
            
            suitable_bounce = self._is_suitable_for_bounce(
                has_consolidation=has_consolidation,
                volatility_level=volatility_level,
                trend_strength=trend_strength
            )
            
            suitable_false_breakout = self._is_suitable_for_false_breakout(
                volatility_level=volatility_level,
                trend_strength=trend_strength,
                has_v=has_v
            )
            
            # 8. УВЕРЕННОСТЬ
            confidence = self._calculate_confidence(
                market_condition=market_condition,
                data_quality=len(primary_candles)
            )
            
            # Метаданные
            metadata = {
                "candles_h1_count": len(candles_h1) if candles_h1 else 0,
                "candles_d1_count": len(candles_d1) if candles_d1 else 0,
                "atr": atr,
                "current_price": current_price,
                "analyzed_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Создаем результат
            analysis = MarketConditionsAnalysis(
                market_condition=market_condition,
                trend_direction=trend_direction,
                trend_strength=trend_strength,
                volatility_level=volatility_level,
                energy_level=energy_level,
                has_consolidation=has_consolidation,
                consolidation_bars=consol_bars,
                consolidation_range_percent=consol_range * 100,
                has_v_formation=has_v,
                v_formation_type=v_type,
                is_suitable_for_breakout=suitable_breakout,
                is_suitable_for_bounce=suitable_bounce,
                is_suitable_for_false_breakout=suitable_false_breakout,
                confidence=confidence,
                metadata=metadata
            )
            
            # Обновляем статистику
            self._update_stats(analysis)
            
            logger.info(f"✅ Анализ условий завершен: {market_condition.value}, "
                       f"trend={trend_direction.value}/{trend_strength.value}, "
                       f"energy={energy_level.value}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа условий: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_default_analysis()
    
    # ==================== АНАЛИЗ ТРЕНДА ====================
    
    def _analyze_trend(self, candles: List) -> Tuple[TrendDirection, TrendStrength]:
        """
        Анализ тренда (направление и сила)
        
        Методика:
        1. Сравниваем первую и вторую половину свечей
        2. Рассчитываем процент изменения
        3. Определяем направление и силу
        
        Args:
            candles: Список свечей
            
        Returns:
            Tuple[направление, сила тренда]
        """
        try:
            if len(candles) < 10:
                return TrendDirection.NEUTRAL, TrendStrength.VERY_WEAK
            
            # Делим на две половины
            mid = len(candles) // 2
            first_half = candles[:mid]
            second_half = candles[mid:]
            
            # Средние цены
            first_avg = mean([float(c['close_price']) for c in first_half])
            second_avg = mean([float(c['close_price']) for c in second_half])
            
            # Процент изменения
            change_percent = (second_avg - first_avg) / first_avg
            
            # Определяем направление
            if change_percent > 0.005:  # > 0.5%
                direction = TrendDirection.BULLISH
            elif change_percent < -0.005:  # < -0.5%
                direction = TrendDirection.BEARISH
            else:
                direction = TrendDirection.NEUTRAL
            
            # Определяем силу
            abs_change = abs(change_percent)
            
            if abs_change >= self.trend_very_strong:
                strength = TrendStrength.VERY_STRONG
            elif abs_change >= self.trend_strong:
                strength = TrendStrength.STRONG
            elif abs_change >= self.trend_moderate:
                strength = TrendStrength.MODERATE
            elif abs_change >= self.trend_weak:
                strength = TrendStrength.WEAK
            else:
                strength = TrendStrength.VERY_WEAK
            
            logger.debug(f"📈 Тренд: {direction.value}, сила: {strength.value} ({change_percent*100:.2f}%)")
            
            return direction, strength
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа тренда: {e}")
            return TrendDirection.UNKNOWN, TrendStrength.VERY_WEAK
    
    # ==================== АНАЛИЗ ВОЛАТИЛЬНОСТИ ====================
    
    def _analyze_volatility(self, candles: List, atr: Optional[float] = None) -> VolatilityLevel:
        """
        Анализ уровня волатильности
        
        Использует:
        1. Стандартное отклонение цен закрытия
        2. Средний диапазон High-Low
        3. ATR (если доступен)
        
        Args:
            candles: Список свечей
            atr: ATR (опционально)
            
        Returns:
            Уровень волатильности
        """
        try:
            if len(candles) < 5:
                return VolatilityLevel.NORMAL
            
            # Берем последние 20 свечей
            recent = candles[-20:] if len(candles) > 20 else candles
            
            closes = [float(c['close_price']) for c in recent]
            avg_close = mean(closes)
            
            # Метод 1: Стандартное отклонение
            if len(closes) >= 5:
                std_dev = stdev(closes)
                volatility_percent = (std_dev / avg_close) if avg_close > 0 else 0
            else:
                volatility_percent = 0
            
            # Метод 2: Средний диапазон
            ranges = [float(c['high_price'] - c['low_price']) for c in recent]
            avg_range = mean(ranges)
            range_percent = (avg_range / avg_close) if avg_close > 0 else 0
            
            # Комбинируем оба метода
            combined_volatility = (volatility_percent + range_percent) / 2
            
            # Определяем уровень
            if combined_volatility < self.vol_very_low:
                level = VolatilityLevel.VERY_LOW
            elif combined_volatility < self.vol_low:
                level = VolatilityLevel.LOW
            elif combined_volatility < self.vol_normal:
                level = VolatilityLevel.NORMAL
            elif combined_volatility < self.vol_high:
                level = VolatilityLevel.HIGH
            else:
                level = VolatilityLevel.EXTREME
            
            logger.debug(f"📊 Волатильность: {level.value} ({combined_volatility*100:.2f}%)")
            
            return level
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа волатильности: {e}")
            return VolatilityLevel.NORMAL
    
    # ==================== АНАЛИЗ КОНСОЛИДАЦИИ ====================
    
    def _analyze_consolidation(self, candles: List) -> Tuple[bool, int, float]:
        """
        Анализ консолидации (боковое движение)
        
        Консолидация = длительное движение в узком диапазоне
        
        Args:
            candles: Список свечей
            
        Returns:
            Tuple[есть консолидация?, кол-во баров, диапазон в %]
        """
        try:
            if len(candles) < self.consolidation_min_bars:
                return False, 0, 0.0
            
            # Анализируем последние N свечей
            lookback = min(30, len(candles))
            recent = candles[-lookback:]
            
            # Находим максимальную последовательность консолидации
            max_consol_bars = 0
            max_consol_range = 0.0
            
            for start_idx in range(len(recent) - self.consolidation_min_bars + 1):
                for end_idx in range(start_idx + self.consolidation_min_bars, len(recent) + 1):
                    subset = recent[start_idx:end_idx]
                    
                    # Проверяем диапазон
                    highs = [float(c['high_price']) for c in subset]
                    lows = [float(c['low_price']) for c in subset]
                    closes = [float(c['close_price']) for c in subset]
                    
                    max_high = max(highs)
                    min_low = min(lows)
                    avg_close = mean(closes)
                    
                    range_percent = (max_high - min_low) / avg_close if avg_close > 0 else 0
                    
                    # Проверяем что диапазон в пределах лимита
                    if range_percent <= self.consolidation_max_range:
                        # Проверяем что нет явного тренда
                        first_half_avg = mean(closes[:len(closes)//2])
                        second_half_avg = mean(closes[len(closes)//2:])
                        trend = abs(second_half_avg - first_half_avg) / first_half_avg
                        
                        if trend < 0.015:  # Тренд < 1.5%
                            bars_count = end_idx - start_idx
                            if bars_count > max_consol_bars:
                                max_consol_bars = bars_count
                                max_consol_range = range_percent
            
            has_consolidation = max_consol_bars >= self.consolidation_min_bars
            
            if has_consolidation:
                logger.info(f"✅ Консолидация обнаружена: {max_consol_bars} баров, "
                          f"диапазон {max_consol_range*100:.2f}%")
            
            return has_consolidation, max_consol_bars, max_consol_range
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа консолидации: {e}")
            return False, 0, 0.0
    
    # ==================== АНАЛИЗ ЭНЕРГИИ ====================
    
    def _analyze_energy(
        self,
        candles: List,
        has_consolidation: bool,
        consolidation_bars: int
    ) -> EnergyLevel:
        """
        Анализ накопленной энергии для пробоя
        
        Энергия накапливается во время консолидации.
        Чем дольше консолидация - тем больше энергии.
        
        Args:
            candles: Список свечей
            has_consolidation: Есть ли консолидация
            consolidation_bars: Количество баров в консолидации
            
        Returns:
            Уровень энергии
        """
        try:
            if not has_consolidation:
                return EnergyLevel.LOW
            
            # Энергия зависит от длительности консолидации
            if consolidation_bars >= self.consolidation_energy_threshold * 2:
                level = EnergyLevel.EXPLOSIVE
            elif consolidation_bars >= self.consolidation_energy_threshold:
                level = EnergyLevel.HIGH
            elif consolidation_bars >= self.consolidation_min_bars * 1.5:
                level = EnergyLevel.MODERATE
            else:
                level = EnergyLevel.LOW
            
            # Дополнительная проверка - сжатие диапазона
            if len(candles) >= 20:
                recent = candles[-20:]
                ranges = [float(c['high_price'] - c['low_price']) for c in recent]
                
                # Если диапазоны уменьшаются - энергия растет
                first_half_avg = mean(ranges[:10])
                second_half_avg = mean(ranges[10:])
                
                if second_half_avg < first_half_avg * 0.8:  # Сжатие на 20%+
                    # Повышаем уровень энергии
                    if level == EnergyLevel.MODERATE:
                        level = EnergyLevel.HIGH
                    elif level == EnergyLevel.LOW:
                        level = EnergyLevel.MODERATE
            
            logger.debug(f"⚡ Энергия: {level.value} (консолидация {consolidation_bars} баров)")
            
            return level
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа энергии: {e}")
            return EnergyLevel.LOW
    
    # ==================== АНАЛИЗ V-ФОРМАЦИИ ====================
    
    def _analyze_v_formation(self, candles: List) -> Tuple[bool, Optional[str]]:
        """
        Анализ V-формации (резкий разворот без консолидации)
        
        Args:
            candles: Список свечей
            
        Returns:
            Tuple[есть V-формация?, тип (bullish/bearish)]
        """
        try:
            if len(candles) < 5:
                return False, None
            
            # Берем последние 10 свечей
            recent = candles[-10:] if len(candles) > 10 else candles
            
            closes = [float(c['close_price']) for c in recent]
            highs = [float(c['high_price']) for c in recent]
            lows = [float(c['low_price']) for c in recent]
            
            # Ищем экстремум (дно или вершину V)
            max_high = max(highs)
            min_low = min(lows)
            max_idx = highs.index(max_high)
            min_idx = lows.index(min_low)
            
            # V-формация вниз-вверх (бычья)
            if min_idx > 0 and min_idx < len(recent) - 2:
                before = closes[:min_idx+1]
                after = closes[min_idx:]
                
                if before and after and len(after) >= 2:
                    down_move = (before[0] - min_low) / before[0]
                    up_move = (after[-1] - min_low) / min_low
                    
                    if down_move >= self.v_min_move and up_move >= self.v_min_move * 0.7:
                        logger.info(f"✅ V-формация (бычья): down={down_move*100:.1f}%, up={up_move*100:.1f}%")
                        return True, "bullish"
            
            # V-формация вверх-вниз (медвежья)
            if max_idx > 0 and max_idx < len(recent) - 2:
                before = closes[:max_idx+1]
                after = closes[max_idx:]
                
                if before and after and len(after) >= 2:
                    up_move = (max_high - before[0]) / before[0]
                    down_move = (max_high - after[-1]) / max_high
                    
                    if up_move >= self.v_min_move and down_move >= self.v_min_move * 0.7:
                        logger.info(f"✅ V-формация (медвежья): up={up_move*100:.1f}%, down={down_move*100:.1f}%")
                        return True, "bearish"
            
            return False, None
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа V-формации: {e}")
            return False, None
    
    # ==================== ОПРЕДЕЛЕНИЕ СОСТОЯНИЯ РЫНКА ====================
    
    def _determine_market_condition(
        self,
        has_consolidation: bool,
        trend_strength: TrendStrength,
        volatility_level: VolatilityLevel
    ) -> MarketCondition:
        """
        Определение общего состояния рынка
        
        Args:
            has_consolidation: Есть ли консолидация
            trend_strength: Сила тренда
            volatility_level: Уровень волатильности
            
        Returns:
            Состояние рынка
        """
        try:
            # Консолидация (боковик)
            if has_consolidation:
                return MarketCondition.CONSOLIDATION
            
            # Волатильный рынок
            if volatility_level in [VolatilityLevel.HIGH, VolatilityLevel.EXTREME]:
                return MarketCondition.VOLATILE
            
            # Трендовый рынок
            if trend_strength in [TrendStrength.STRONG, TrendStrength.VERY_STRONG]:
                return MarketCondition.TRENDING
            
            # Нейтральный рынок
            return MarketCondition.NEUTRAL
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения состояния: {e}")
            return MarketCondition.UNKNOWN
    
    # ==================== ПОДХОДЯЩИЕ СТРАТЕГИИ ====================
    
    def _is_suitable_for_breakout(
        self,
        has_consolidation: bool,
        energy_level: EnergyLevel,
        trend_strength: TrendStrength
    ) -> bool:
        """
        Проверка пригодности для стратегии пробоя
        
        Подходит если:
        - Есть консолидация (энергия накоплена)
        - Высокая энергия
        - Не очень сильный тренд
        """
        return (
            has_consolidation and
            energy_level in [EnergyLevel.HIGH, EnergyLevel.EXPLOSIVE] and
            trend_strength not in [TrendStrength.VERY_STRONG]
        )
    
    def _is_suitable_for_bounce(
        self,
        has_consolidation: bool,
        volatility_level: VolatilityLevel,
        trend_strength: TrendStrength
    ) -> bool:
        """
        Проверка пригодности для стратегии отбоя
        
        Подходит если:
        - НЕТ консолидации (уровни работают)
        - Нормальная или низкая волатильность
        - Есть тренд
        """
        return (
            not has_consolidation and
            volatility_level not in [VolatilityLevel.EXTREME] and
            trend_strength in [TrendStrength.MODERATE, TrendStrength.STRONG]
        )
    
    def _is_suitable_for_false_breakout(
        self,
        volatility_level: VolatilityLevel,
        trend_strength: TrendStrength,
        has_v: bool
    ) -> bool:
        """
        Проверка пригодности для стратегии ложного пробоя
        
        Подходит если:
        - Высокая волатильность (ловушки крупного игрока)
        - Сильный тренд (откаты и ложные пробои)
        - V-формация
        """
        return (
            volatility_level in [VolatilityLevel.HIGH, VolatilityLevel.EXTREME] or
            trend_strength in [TrendStrength.STRONG, TrendStrength.VERY_STRONG] or
            has_v
        )
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================
    
    def _calculate_confidence(
        self,
        market_condition: MarketCondition,
        data_quality: int
    ) -> float:
        """Расчет уверенности в анализе"""
        confidence = 0.5
        
        # Бонус за качество данных
        if data_quality >= 50:
            confidence += 0.3
        elif data_quality >= 20:
            confidence += 0.2
        elif data_quality >= 10:
            confidence += 0.1
        
        # Бонус за определенное состояние
        if market_condition not in [MarketCondition.UNKNOWN, MarketCondition.NEUTRAL]:
            confidence += 0.2
        
        return min(1.0, confidence)
    
    def _create_default_analysis(self) -> MarketConditionsAnalysis:
        """Создание дефолтного результата"""
        return MarketConditionsAnalysis(
            market_condition=MarketCondition.UNKNOWN,
            trend_direction=TrendDirection.UNKNOWN,
            trend_strength=TrendStrength.VERY_WEAK,
            volatility_level=VolatilityLevel.NORMAL,
            energy_level=EnergyLevel.LOW,
            confidence=0.0
        )
    
    # ==================== СТАТИСТИКА ====================
    
    def _update_stats(self, analysis: MarketConditionsAnalysis):
        """Обновление статистики"""
        if analysis.has_consolidation:
            self.stats["consolidations_detected"] += 1
        
        if analysis.trend_strength in [TrendStrength.STRONG, TrendStrength.VERY_STRONG]:
            self.stats["trends_detected"] += 1
        
        if analysis.has_v_formation:
            self.stats["v_formations_detected"] += 1
        
        if analysis.energy_level in [EnergyLevel.HIGH, EnergyLevel.EXPLOSIVE]:
            self.stats["high_energy_detected"] += 1
        
        if analysis.volatility_level in [VolatilityLevel.HIGH, VolatilityLevel.EXTREME]:
            self.stats["high_volatility_detected"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику"""
        return {
            **self.stats,
            "config": {
                "consolidation_min_bars": self.consolidation_min_bars,
                "consolidation_energy_threshold": self.consolidation_energy_threshold,
                "volatility_thresholds": {
                    "very_low": self.vol_very_low * 100,
                    "low": self.vol_low * 100,
                    "normal": self.vol_normal * 100,
                    "high": self.vol_high * 100
                },
                "trend_thresholds": {
                    "weak": self.trend_weak * 100,
                    "moderate": self.trend_moderate * 100,
                    "strong": self.trend_strong * 100,
                    "very_strong": self.trend_very_strong * 100
                }
            }
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.stats = {
            "analyses_count": 0,
            "consolidations_detected": 0,
            "trends_detected": 0,
            "v_formations_detected": 0,
            "high_energy_detected": 0,
            "high_volatility_detected": 0
        }
        logger.info("🔄 Статистика MarketConditionsAnalyzer сброшена")
    
    def __repr__(self) -> str:
        return (f"MarketConditionsAnalyzer(analyses={self.stats['analyses_count']}, "
                f"consolidations={self.stats['consolidations_detected']}, "
                f"trends={self.stats['trends_detected']})")
    
    def __str__(self) -> str:
        stats = self.get_stats()
        return (f"Market Conditions Analyzer:\n"
                f"  Analyses: {stats['analyses_count']}\n"
                f"  Consolidations: {stats['consolidations_detected']}\n"
                f"  Trends: {stats['trends_detected']}\n"
                f"  V-formations: {stats['v_formations_detected']}\n"
                f"  High energy: {stats['high_energy_detected']}\n"
                f"  High volatility: {stats['high_volatility_detected']}")


# Export
__all__ = [
    "MarketConditionsAnalyzer",
    "MarketConditionsAnalysis",
    "VolatilityLevel",
    "EnergyLevel",
    "TrendStrength"
]

logger.info("✅ Market Conditions Analyzer module loaded")
