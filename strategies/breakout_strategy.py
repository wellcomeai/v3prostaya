"""
Breakout Strategy - Стратегия торговли пробоя

Торгует импульсные движения после преодоления ключевых уровней.

Условия входа (из документа):
1. ✅ Уровень с D1 идентифицирован
2. ✅ Подход к уровню маленькими барами (поджатие)
3. ✅ Ближний ретест (до 1 недели, идеально 3 свечи)
4. ✅ Закрытие инструмента вблизи уровня
5. ✅ Долгая консолидация (энергия накоплена)
6. ✅ Закрытие бара под самый Hi/Low без отката (макс 10%)
7. ✅ ATR не исчерпан (< 75%)

Механика входа:
- Buy Stop / Sell Stop → за уровнем (+1-2 пункта)
- Stop Loss → технический (за уровень)
- Take Profit → минимум 3:1
- Отмена ордера если цена отошла на 1 ATR от заявки

Author: Trading Bot Team
Version: 1.0.0
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from .base_strategy import BaseStrategy, TradingSignal, SignalType, SignalStrength
from market_data import MarketDataSnapshot
from strategies.technical_analysis import (
    TechnicalAnalysisContext,
    PatternDetector,
    MarketConditionsAnalyzer,
    BreakoutAnalyzer,
    SupportResistanceLevel,
    MarketCondition,
    EnergyLevel
)

logger = logging.getLogger(__name__)


class BreakoutStrategy(BaseStrategy):
    """
    💥 Стратегия торговли пробоя уровней
    
    Ставка на импульсное движение после преодоления ключевого уровня.
    Требует накопления энергии (консолидации) перед пробоем.
    
    Сильные стороны:
    - Ловит крупные импульсные движения
    - Высокий R:R (минимум 3:1)
    - Четкие условия входа
    
    Слабые стороны:
    - Требует терпения (ждем все условия)
    - Ложные пробои могут срабатывать стоп
    - Не работает при исчерпанном ATR
    
    Usage:
        strategy = BreakoutStrategy(
            symbol="BTCUSDT",
            ta_context_manager=ta_manager
        )
        
        signal = await strategy.process_market_data(
            market_data=snapshot,
            ta_context=context
        )
    """
    
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        ta_context_manager = None,
        
        # Параметры уровней
        min_level_strength: float = 0.5,        # Минимальная сила уровня
        max_distance_to_level_percent: float = 2.0,  # Максимальное расстояние до уровня
        
        # Параметры поджатия
        require_compression: bool = True,        # Требовать поджатие
        compression_min_bars: int = 3,          # Минимум баров поджатия
        
        # Параметры ретеста
        near_retest_max_days: int = 7,          # Ближний ретест < 7 дней
        ideal_retest_touches: int = 3,          # Идеальное кол-во касаний
        
        # Параметры закрытия
        close_near_level_tolerance: float = 0.5,  # Допуск закрытия у уровня (%)
        close_near_extreme_max_pullback: float = 10.0,  # Макс откат от Hi/Low (%)
        
        # Параметры энергии
        require_consolidation: bool = True,      # Требовать консолидацию
        min_energy_level: str = "moderate",     # moderate, high, explosive
        
        # Параметры ATR
        atr_exhaustion_threshold: float = 0.75,  # 75% = исчерпан
        
        # Параметры ордеров
        entry_offset_points: float = 2.0,       # Отступ от уровня для ордера
        stop_loss_multiplier: float = 1.0,      # Множитель для SL
        take_profit_ratio: float = 3.0,         # TP:SL ratio (минимум 3:1)
        order_cancel_atr_distance: float = 1.0,  # Отмена если цена ушла на 1 ATR
        
        # Настройки стратегии
        min_signal_strength: float = 0.6,
        signal_cooldown_minutes: int = 30,      # Долгий cooldown для пробоев
        max_signals_per_hour: int = 2,          # Мало сигналов (качество > количество)
    ):
        """
        Инициализация стратегии пробоя
        
        Args:
            symbol: Торговый символ
            ta_context_manager: Менеджер технического анализа
            [остальные параметры см. выше]
        """
        super().__init__(
            name="BreakoutStrategy",
            symbol=symbol,
            min_signal_strength=min_signal_strength,
            signal_cooldown_minutes=signal_cooldown_minutes,
            max_signals_per_hour=max_signals_per_hour,
            enable_risk_management=True
        )
        
        # Менеджер технического анализа
        self.ta_context_manager = ta_context_manager
        
        # Параметры уровней
        self.min_level_strength = min_level_strength
        self.max_distance_to_level = max_distance_to_level_percent / 100.0
        
        # Параметры поджатия
        self.require_compression = require_compression
        self.compression_min_bars = compression_min_bars
        
        # Параметры ретеста
        self.near_retest_max_days = near_retest_max_days
        self.ideal_retest_touches = ideal_retest_touches
        
        # Параметры закрытия
        self.close_near_level_tolerance = close_near_level_tolerance
        self.close_near_extreme_max_pullback = close_near_extreme_max_pullback
        
        # Параметры энергии
        self.require_consolidation = require_consolidation
        self.min_energy_level = min_energy_level
        
        # Параметры ATR
        self.atr_exhaustion_threshold = atr_exhaustion_threshold
        
        # Параметры ордеров
        self.entry_offset = entry_offset_points
        self.stop_loss_multiplier = stop_loss_multiplier
        self.take_profit_ratio = take_profit_ratio
        self.order_cancel_distance = order_cancel_atr_distance
        
        # Инициализируем анализаторы
        self.pattern_detector = PatternDetector(
            compression_min_bars=compression_min_bars
        )
        
        self.market_analyzer = MarketConditionsAnalyzer()
        self.breakout_analyzer = BreakoutAnalyzer()
        
        # Статистика стратегии
        self.strategy_stats = {
            "levels_analyzed": 0,
            "compressions_found": 0,
            "consolidations_found": 0,
            "setups_found": 0,
            "signals_generated": 0,
            "setups_filtered_by_atr": 0,
            "setups_filtered_by_energy": 0,
            "setups_filtered_by_compression": 0
        }
        
        logger.info("💥 BreakoutStrategy инициализирована")
        logger.info(f"   • Symbol: {symbol}")
        logger.info(f"   • Require compression: {require_compression}")
        logger.info(f"   • Require consolidation: {require_consolidation}")
        logger.info(f"   • Min energy: {min_energy_level}")
        logger.info(f"   • ATR exhaustion: {atr_exhaustion_threshold*100}%")
    
    # ==================== ОСНОВНОЙ АНАЛИЗ ====================
    
    async def analyze_market_data(
        self,
        market_data: MarketDataSnapshot,
        ta_context: Optional[TechnicalAnalysisContext] = None
    ) -> Optional[TradingSignal]:
        """
        🎯 Основной метод анализа для стратегии пробоя
        
        Алгоритм:
        1. Проверка технического контекста
        2. Анализ рыночных условий
        3. Поиск подходящих уровней
        4. Проверка всех условий входа
        5. Расчет параметров ордера
        6. Генерация сигнала
        
        Args:
            market_data: Снимок рыночных данных
            ta_context: Технический контекст (уровни, ATR, свечи)
            
        Returns:
            TradingSignal или None
        """
        try:
            # Шаг 1: Проверка технического контекста
            if ta_context is None or not ta_context.is_fully_initialized():
                if self.debug_mode:
                    logger.debug("⚠️ Технический контекст не инициализирован")
                return None
            
            current_price = market_data.current_price
            
            # Шаг 2: Анализ рыночных условий
            market_conditions = self.market_analyzer.analyze_conditions(
                candles_h1=ta_context.recent_candles_h1,
                candles_d1=ta_context.recent_candles_d1,
                atr=ta_context.atr_data.calculated_atr if ta_context.atr_data else None,
                current_price=current_price
            )
            
            # Проверка пригодности для пробоя
            if not market_conditions.is_suitable_for_breakout:
                if self.debug_mode:
                    logger.debug(f"⚠️ Условия не подходят для пробоя: "
                               f"{market_conditions.market_condition.value}")
                return None
            
            # Шаг 3: Проверка ATR (не должен быть исчерпан)
            if ta_context.atr_data and ta_context.is_atr_exhausted(self.atr_exhaustion_threshold):
                self.strategy_stats["setups_filtered_by_atr"] += 1
                if self.debug_mode:
                    logger.debug(f"⚠️ ATR исчерпан: {ta_context.atr_data.current_range_used:.1f}%")
                return None
            
            # Шаг 4: Поиск ближайшего уровня
            nearest_level, direction = self._find_nearest_level_for_breakout(
                ta_context=ta_context,
                current_price=current_price
            )
            
            if not nearest_level:
                return None
            
            self.strategy_stats["levels_analyzed"] += 1
            
            # Шаг 5: Проверка всех условий входа
            setup_valid, setup_details = await self._validate_breakout_setup(
                level=nearest_level,
                direction=direction,
                ta_context=ta_context,
                market_data=market_data,
                market_conditions=market_conditions
            )
            
            if not setup_valid:
                return None
            
            self.strategy_stats["setups_found"] += 1
            
            # Шаг 6: Расчет параметров ордера
            order_params = self._calculate_order_parameters(
                level=nearest_level,
                direction=direction,
                ta_context=ta_context,
                current_price=current_price
            )
            
            # Шаг 7: Проверка что цена не ушла слишком далеко
            if not self._check_order_validity(order_params, current_price, ta_context):
                if self.debug_mode:
                    logger.debug("⚠️ Цена слишком далеко от точки входа")
                return None
            
            # Шаг 8: Генерация сигнала
            signal = self._create_breakout_signal(
                level=nearest_level,
                direction=direction,
                order_params=order_params,
                setup_details=setup_details,
                market_conditions=market_conditions,
                current_price=current_price
            )
            
            self.strategy_stats["signals_generated"] += 1
            
            logger.info(f"✅ Сигнал пробоя создан: {direction} через {nearest_level.price:.2f}")
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ Ошибка в analyze_market_data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    # ==================== ПОИСК УРОВНЕЙ ====================
    
    def _find_nearest_level_for_breakout(
        self,
        ta_context: TechnicalAnalysisContext,
        current_price: float
    ) -> Tuple[Optional[SupportResistanceLevel], str]:
        """
        Поиск ближайшего уровня для потенциального пробоя
        
        Args:
            ta_context: Технический контекст
            current_price: Текущая цена
            
        Returns:
            Tuple[уровень, направление ("up"/"down")]
        """
        try:
            # Фильтруем уровни по силе
            strong_levels = [
                level for level in ta_context.levels_d1
                if level.strength >= self.min_level_strength
            ]
            
            if not strong_levels:
                return None, None
            
            # Ищем ближайшее сопротивление (для пробоя вверх)
            resistances = [
                level for level in strong_levels
                if level.level_type == "resistance" and level.price > current_price
            ]
            
            # Ищем ближайшую поддержку (для пробоя вниз)
            supports = [
                level for level in strong_levels
                if level.level_type == "support" and level.price < current_price
            ]
            
            # Выбираем ближайший уровень
            nearest_resistance = None
            nearest_support = None
            
            if resistances:
                nearest_resistance = min(resistances, key=lambda l: abs(l.price - current_price))
            
            if supports:
                nearest_support = min(supports, key=lambda l: abs(l.price - current_price))
            
            # Определяем какой уровень ближе
            candidates = []
            
            if nearest_resistance:
                distance = abs(nearest_resistance.price - current_price) / current_price
                if distance <= self.max_distance_to_level:
                    candidates.append((nearest_resistance, "up", distance))
            
            if nearest_support:
                distance = abs(nearest_support.price - current_price) / current_price
                if distance <= self.max_distance_to_level:
                    candidates.append((nearest_support, "down", distance))
            
            if not candidates:
                return None, None
            
            # Выбираем ближайший
            best_candidate = min(candidates, key=lambda x: x[2])
            level, direction, distance = best_candidate
            
            logger.debug(f"🎯 Найден уровень: {level.level_type} @ {level.price:.2f}, "
                        f"distance={distance*100:.2f}%, strength={level.strength:.2f}")
            
            return level, direction
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска уровня: {e}")
            return None, None
    
    # ==================== ВАЛИДАЦИЯ УСЛОВИЙ ====================
    
    async def _validate_breakout_setup(
        self,
        level: SupportResistanceLevel,
        direction: str,
        ta_context: TechnicalAnalysisContext,
        market_data: MarketDataSnapshot,
        market_conditions: Any
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Валидация всех условий для пробоя
        
        Проверяет 6 основных условий из документа:
        1. ✅ Поджатие (маленькие бары)
        2. ✅ Ближний ретест
        3. ✅ Закрытие у уровня
        4. ✅ Консолидация (энергия)
        5. ✅ Закрытие под Hi/Low без отката
        6. ✅ ATR не исчерпан
        
        Args:
            level: Уровень для пробоя
            direction: Направление пробоя
            ta_context: Технический контекст
            market_data: Рыночные данные
            market_conditions: Условия рынка
            
        Returns:
            Tuple[валидный setup?, детали]
        """
        try:
            details = {
                "level_price": level.price,
                "level_strength": level.strength,
                "level_touches": level.touches,
                "direction": direction
            }
            
            # УСЛОВИЕ 1: Поджатие
            has_compression = False
            
            if self.require_compression:
                candles_m5 = ta_context.recent_candles_m5[-20:] if ta_context.recent_candles_m5 else []
                
                if candles_m5:
                    atr = ta_context.atr_data.calculated_atr if ta_context.atr_data else None
                    
                    has_compression, compression_details = self.pattern_detector.detect_compression(
                        candles=candles_m5,
                        level=level,
                        atr=atr
                    )
                    
                    details["compression"] = compression_details
                    
                    if not has_compression:
                        self.strategy_stats["setups_filtered_by_compression"] += 1
                        if self.debug_mode:
                            logger.debug("❌ Нет поджатия")
                        return False, details
                    
                    self.strategy_stats["compressions_found"] += 1
            
            details["has_compression"] = has_compression
            
            # УСЛОВИЕ 2: Ближний ретест
            is_near_retest = False
            
            if level.last_touch:
                days_since_touch = (datetime.now() - level.last_touch).days
                is_near_retest = days_since_touch <= self.near_retest_max_days
                
                details["days_since_touch"] = days_since_touch
                details["is_near_retest"] = is_near_retest
                
                if self.debug_mode:
                    if is_near_retest:
                        logger.debug(f"✅ Ближний ретест: {days_since_touch} дней")
                    else:
                        logger.debug(f"⚠️ Дальний ретест: {days_since_touch} дней")
            
            # УСЛОВИЕ 3: Закрытие вблизи уровня
            close_near_level = False
            
            if ta_context.recent_candles_m5:
                last_candle = ta_context.recent_candles_m5[-1]
                close_near_level = self.pattern_detector.check_close_near_level(
                    candle=last_candle,
                    level=level,
                    tolerance_percent=self.close_near_level_tolerance
                )
                
                details["close_near_level"] = close_near_level
                
                if close_near_level:
                    logger.debug("✅ Закрытие у уровня")
            
            # УСЛОВИЕ 4: Консолидация и энергия
            has_enough_energy = False
            
            if self.require_consolidation:
                if not market_conditions.has_consolidation:
                    self.strategy_stats["setups_filtered_by_energy"] += 1
                    if self.debug_mode:
                        logger.debug("❌ Нет консолидации")
                    return False, details
                
                # Проверяем уровень энергии
                energy_map = {
                    "moderate": [EnergyLevel.MODERATE, EnergyLevel.HIGH, EnergyLevel.EXPLOSIVE],
                    "high": [EnergyLevel.HIGH, EnergyLevel.EXPLOSIVE],
                    "explosive": [EnergyLevel.EXPLOSIVE]
                }
                
                required_levels = energy_map.get(self.min_energy_level, [EnergyLevel.MODERATE])
                has_enough_energy = market_conditions.energy_level in required_levels
                
                details["consolidation_bars"] = market_conditions.consolidation_bars
                details["energy_level"] = market_conditions.energy_level.value
                details["has_enough_energy"] = has_enough_energy
                
                if not has_enough_energy:
                    self.strategy_stats["setups_filtered_by_energy"] += 1
                    if self.debug_mode:
                        logger.debug(f"❌ Недостаточно энергии: {market_conditions.energy_level.value}")
                    return False, details
                
                self.strategy_stats["consolidations_found"] += 1
            
            # УСЛОВИЕ 5: Закрытие под Hi/Low без отката
            close_near_extreme = False
            extreme_type = None
            
            if ta_context.recent_candles_m5:
                last_candle = ta_context.recent_candles_m5[-1]
                close_near_extreme, extreme_type = self.pattern_detector.check_close_near_extreme(
                    candle=last_candle,
                    max_pullback_percent=self.close_near_extreme_max_pullback
                )
                
                details["close_near_extreme"] = close_near_extreme
                details["extreme_type"] = extreme_type
                
                if close_near_extreme:
                    logger.debug(f"✅ Закрытие у {extreme_type}")
            
            # УСЛОВИЕ 6: ATR не исчерпан (уже проверено в основном методе)
            
            # Итоговая оценка setup
            score = 0
            max_score = 6
            
            if has_compression:
                score += 1
            if is_near_retest:
                score += 1
            if close_near_level:
                score += 1
            if has_enough_energy:
                score += 1
            if close_near_extreme:
                score += 1
            if not ta_context.is_atr_exhausted(self.atr_exhaustion_threshold):
                score += 1
            
            details["setup_score"] = score
            details["setup_score_max"] = max_score
            details["setup_quality"] = score / max_score
            
            # Минимальный score для входа
            min_score = 4 if self.require_compression and self.require_consolidation else 3
            
            is_valid = score >= min_score
            
            if is_valid:
                logger.info(f"✅ Setup валиден: {score}/{max_score} условий выполнено")
            else:
                logger.debug(f"❌ Setup невалиден: {score}/{max_score} < {min_score}")
            
            return is_valid, details
            
        except Exception as e:
            logger.error(f"❌ Ошибка валидации setup: {e}")
            return False, {}
    
    # ==================== РАСЧЕТ ПАРАМЕТРОВ ОРДЕРА ====================
    
    def _calculate_order_parameters(
        self,
        level: SupportResistanceLevel,
        direction: str,
        ta_context: TechnicalAnalysisContext,
        current_price: float
    ) -> Dict[str, float]:
        """
        Расчет параметров ордера (ТВХ, Stop Loss, Take Profit)
        
        Механика из документа:
        - Entry: уровень ± offset (1-2 пункта)
        - Stop Loss: технический (за уровень)
        - Take Profit: минимум 3:1
        
        Args:
            level: Уровень пробоя
            direction: Направление
            ta_context: Технический контекст
            current_price: Текущая цена
            
        Returns:
            Словарь с параметрами ордера
        """
        try:
            level_price = level.price
            
            # ATR для расчетов
            atr = ta_context.atr_data.calculated_atr if ta_context.atr_data else level_price * 0.02
            
            # Люфт (20% от Stop Loss, но пока используем фиксированный offset)
            entry_offset = self.entry_offset
            
            if direction == "up":
                # Пробой вверх (через сопротивление)
                entry_price = level_price + entry_offset  # Buy Stop
                
                # Stop Loss за уровнем (технический)
                # Используем расчетный stop = 10% от ATR для тренда
                stop_distance = atr * 0.10 * self.stop_loss_multiplier
                stop_loss = entry_price - stop_distance
                
                # Take Profit: минимум 3:1
                take_profit = entry_price + (stop_distance * self.take_profit_ratio)
                
            else:
                # Пробой вниз (через поддержку)
                entry_price = level_price - entry_offset  # Sell Stop
                
                # Stop Loss за уровнем
                stop_distance = atr * 0.10 * self.stop_loss_multiplier
                stop_loss = entry_price + stop_distance
                
                # Take Profit: минимум 3:1
                take_profit = entry_price - (stop_distance * self.take_profit_ratio)
            
            params = {
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "stop_distance": stop_distance,
                "risk_reward_ratio": self.take_profit_ratio,
                "level_price": level_price,
                "atr_used": atr
            }
            
            logger.debug(f"📊 Параметры ордера: Entry={entry_price:.2f}, "
                        f"SL={stop_loss:.2f}, TP={take_profit:.2f}, R:R={self.take_profit_ratio}:1")
            
            return params
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета параметров: {e}")
            return {}
    
    def _check_order_validity(
        self,
        order_params: Dict[str, float],
        current_price: float,
        ta_context: TechnicalAnalysisContext
    ) -> bool:
        """
        Проверка валидности ордера
        
        Отменяем если цена ушла слишком далеко (> 1 ATR от entry)
        
        Args:
            order_params: Параметры ордера
            current_price: Текущая цена
            ta_context: Технический контекст
            
        Returns:
            True если ордер валиден
        """
        try:
            entry_price = order_params.get("entry_price")
            if not entry_price:
                return False
            
            # Проверяем расстояние до entry
            distance = abs(current_price - entry_price)
            
            # ATR для сравнения
            atr = ta_context.atr_data.calculated_atr if ta_context.atr_data else current_price * 0.02
            
            max_distance = atr * self.order_cancel_distance
            
            if distance > max_distance:
                logger.debug(f"⚠️ Цена слишком далеко: {distance:.2f} > {max_distance:.2f} (1 ATR)")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки ордера: {e}")
            return False
    
    # ==================== СОЗДАНИЕ СИГНАЛА ====================
    
    def _create_breakout_signal(
        self,
        level: SupportResistanceLevel,
        direction: str,
        order_params: Dict[str, float],
        setup_details: Dict[str, Any],
        market_conditions: Any,
        current_price: float
    ) -> TradingSignal:
        """
        Создание торгового сигнала пробоя
        
        Args:
            level: Уровень пробоя
            direction: Направление
            order_params: Параметры ордера
            setup_details: Детали setup
            market_conditions: Условия рынка
            current_price: Текущая цена
            
        Returns:
            TradingSignal
        """
        try:
            # Определяем тип сигнала
            signal_type = SignalType.BUY if direction == "up" else SignalType.SELL
            
            # Если все условия идеальны - STRONG сигнал
            setup_quality = setup_details.get("setup_quality", 0.5)
            
            if setup_quality >= 0.9:
                signal_type = SignalType.STRONG_BUY if direction == "up" else SignalType.STRONG_SELL
            
            # Расчет силы сигнала
            strength = self._calculate_signal_strength(
                setup_details=setup_details,
                level=level,
                market_conditions=market_conditions
            )
            
            # Расчет уверенности
            confidence = self._calculate_signal_confidence(
                setup_details=setup_details,
                level=level
            )
            
            # Причины
            reasons = self._build_signal_reasons(
                setup_details=setup_details,
                level=level,
                direction=direction
            )
            
            # Создаем сигнал
            signal = self.create_signal(
                signal_type=signal_type,
                strength=strength,
                confidence=confidence,
                current_price=current_price,
                reasons=reasons
            )
            
            # Добавляем параметры ордера
            signal.stop_loss = order_params.get("stop_loss")
            signal.take_profit = order_params.get("take_profit")
            
            # Размер позиции (из risk management)
            signal.position_size_recommendation = min(
                0.03 * confidence,  # До 3% при макс уверенности
                0.05  # Но не более 5%
            )
            
            # Технические индикаторы
            signal.add_technical_indicator(
                "breakout_level",
                level.price,
                f"{level.level_type} @ {level.price:.2f}"
            )
            
            signal.add_technical_indicator(
                "entry_price",
                order_params.get("entry_price"),
                f"Entry: {order_params.get('entry_price'):.2f}"
            )
            
            signal.add_technical_indicator(
                "risk_reward_ratio",
                order_params.get("risk_reward_ratio"),
                f"R:R = {order_params.get('risk_reward_ratio')}:1"
            )
            
            # Условия рынка
            signal.market_conditions = {
                "market_condition": market_conditions.market_condition.value,
                "energy_level": market_conditions.energy_level.value,
                "consolidation_bars": market_conditions.consolidation_bars,
                "setup_quality": setup_quality
            }
            
            # Метаданные
            signal.technical_indicators["setup_details"] = setup_details
            signal.technical_indicators["order_params"] = order_params
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания сигнала: {e}")
            # Создаем базовый сигнал
            return self.create_signal(
                signal_type=SignalType.BUY if direction == "up" else SignalType.SELL,
                strength=0.5,
                confidence=0.5,
                current_price=current_price,
                reasons=["Пробой уровня"]
            )
    
    def _calculate_signal_strength(
        self,
        setup_details: Dict[str, Any],
        level: SupportResistanceLevel,
        market_conditions: Any
    ) -> float:
        """Расчет силы сигнала"""
        strength = 0.5  # Базовая
        
        # Бонус за качество setup
        setup_quality = setup_details.get("setup_quality", 0)
        strength += setup_quality * 0.3
        
        # Бонус за сильный уровень
        if level.is_strong:
            strength += 0.1
        
        # Бонус за высокую энергию
        if market_conditions.energy_level in [EnergyLevel.HIGH, EnergyLevel.EXPLOSIVE]:
            strength += 0.1
        
        return min(1.0, strength)
    
    def _calculate_signal_confidence(
        self,
        setup_details: Dict[str, Any],
        level: SupportResistanceLevel
    ) -> float:
        """Расчет уверенности в сигнале"""
        confidence = 0.6  # Базовая
        
        # Бонус за поджатие
        if setup_details.get("has_compression"):
            confidence += 0.15
        
        # Бонус за ближний ретест
        if setup_details.get("is_near_retest"):
            confidence += 0.1
        
        # Бонус за сильный уровень
        if level.strength >= 0.8:
            confidence += 0.1
        
        # Бонус за множественные касания
        if level.touches >= 3:
            confidence += 0.05
        
        return min(1.0, confidence)
    
    def _build_signal_reasons(
        self,
        setup_details: Dict[str, Any],
        level: SupportResistanceLevel,
        direction: str
    ) -> List[str]:
        """Построение списка причин сигнала"""
        reasons = []
        
        direction_text = "вверх" if direction == "up" else "вниз"
        reasons.append(f"Пробой {direction_text} через {level.level_type} @ {level.price:.2f}")
        
        if setup_details.get("has_compression"):
            reasons.append("Поджатие у уровня обнаружено")
        
        if setup_details.get("has_enough_energy"):
            energy = setup_details.get("energy_level", "unknown")
            consol_bars = setup_details.get("consolidation_bars", 0)
            reasons.append(f"Энергия накоплена: {energy} ({consol_bars} баров консолидации)")
        
        if setup_details.get("is_near_retest"):
            days = setup_details.get("days_since_touch", 0)
            reasons.append(f"Ближний ретест ({days} дней)")
        
        if setup_details.get("close_near_level"):
            reasons.append("Закрытие вблизи уровня")
        
        if setup_details.get("close_near_extreme"):
            reasons.append(f"Закрытие под {setup_details.get('extreme_type')}")
        
        if level.is_strong:
            reasons.append(f"Сильный уровень (strength={level.strength:.2f}, touches={level.touches})")
        
        return reasons
    
    # ==================== СТАТИСТИКА ====================
    
    def get_strategy_stats(self) -> Dict[str, Any]:
        """Получить статистику стратегии"""
        base_stats = self.get_stats()
        
        return {
            **base_stats,
            "strategy_type": "BreakoutStrategy",
            "strategy_stats": self.strategy_stats.copy(),
            "config": {
                "require_compression": self.require_compression,
                "require_consolidation": self.require_consolidation,
                "min_energy_level": self.min_energy_level,
                "atr_exhaustion_threshold": self.atr_exhaustion_threshold,
                "take_profit_ratio": self.take_profit_ratio
            }
        }
    
    def __str__(self):
        stats = self.get_strategy_stats()
        return (f"BreakoutStrategy(symbol={self.symbol}, "
                f"setups={stats['strategy_stats']['setups_found']}, "
                f"signals={stats['signals_sent']}, "
                f"success_rate={stats['analysis_success_rate']:.1f}%)")


# Export
__all__ = ["BreakoutStrategy"]

logger.info("✅ Breakout Strategy module loaded")
