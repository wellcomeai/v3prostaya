"""
False Breakout Strategy - Стратегия торговли ложных пробоев

Торгует РЕАКЦИЮ на ложный пробой (False Breakout) - когда крупный игрок 
"ловит стопы" и цена резко разворачивается обратно за уровень.

Типы ложных пробоев:
1. Простой ЛП (1 бар) - пробил, но закрылся назад за уровень
2. Сильный ЛП (2 бара) - пробил, закрылся в зоне, затем развернулся
3. Сложный ЛП (3+ бара) - консолидация в зоне пробоя, потом разворот

Механика входа:
- После ЛП вверх → SELL (цена вернулась под уровень)
- После ЛП вниз → BUY (цена вернулась над уровень)
- Entry: текущая цена (Market) или Limit от уровня
- Stop Loss: за зону ЛП (High/Low пробоя × 1.1)
- Take Profit: 2-3 стопа (противоположный уровень)

Условия входа:
1. ✅ Обнаружен ложный пробой (BreakoutAnalyzer)
2. ✅ Цена подтвердила разворот (вернулась за уровень)
3. ✅ Не прошло много времени (< 30 минут)
4. ✅ Сильный уровень (strength >= 0.5)
5. ✅ Подходящие рыночные условия

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
    BreakoutType,
    BreakoutDirection,
    MarketCondition,
    VolatilityLevel
)

logger = logging.getLogger(__name__)


class FalseBreakoutStrategy(BaseStrategy):
    """
    🎣 Стратегия торговли ложных пробоев (ловушек)
    
    Ловит развороты после того как крупный игрок "поймал стопы" мелких трейдеров.
    Торгует ПРОТИВ направления ложного пробоя.
    
    Сильные стороны:
    - Высокая точность (уровень проверен ЛП)
    - Хороший R:R (2-3:1)
    - Четкая точка входа (после подтверждения)
    - Быстрые сделки (часто закрываются за 1-4 часа)
    
    Слабые стороны:
    - Требует быстрой реакции (30 минут после ЛП)
    - Нужно подтверждение разворота
    - Не работает при высокой волатильности
    - Ложные ЛП (может быть истинным пробоем)
    
    Usage:
        strategy = FalseBreakoutStrategy(
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
        min_level_touches: int = 2,             # Минимум касаний
        max_distance_to_level_percent: float = 2.0,  # Максимальное расстояние до уровня
        
        # Параметры ложного пробоя
        min_false_breakout_depth_atr: float = 0.05,  # Мин глубина ЛП (5% ATR)
        max_false_breakout_depth_atr: float = 0.33,  # Макс глубина ЛП (1/3 ATR)
        prefer_simple_false_breakouts: bool = True,  # Предпочитать простые ЛП
        
        # Параметры подтверждения
        confirmation_required: bool = True,          # Требовать подтверждение
        confirmation_distance_percent: float = 0.3,  # Расстояние подтверждения от уровня
        max_time_since_breakout_minutes: int = 30,   # Макс время после ЛП
        
        # Параметры рыночных условий
        prefer_strong_levels: bool = True,           # Предпочитать сильные уровни
        avoid_extreme_volatility: bool = True,       # Избегать экстремальной волатильности
        require_clear_reversal: bool = True,         # Требовать четкий разворот
        
        # Параметры ордеров
        entry_type: str = "market",                  # market или limit
        limit_offset_percent: float = 0.2,           # Отступ для лимит ордера
        stop_loss_beyond_extreme: float = 1.1,       # SL за экстремум ЛП × 1.1
        take_profit_ratio: float = 2.5,              # TP:SL = 2.5:1
        use_opposite_level_for_tp: bool = True,      # Использовать противоположный уровень для TP
        
        # Настройки стратегии
        min_signal_strength: float = 0.6,
        signal_cooldown_minutes: int = 15,
        max_signals_per_hour: int = 4,
    ):
        """
        Инициализация стратегии ложных пробоев
        
        Args:
            symbol: Торговый символ
            ta_context_manager: Менеджер технического анализа
            [остальные параметры см. выше]
        """
        super().__init__(
            name="FalseBreakoutStrategy",
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
        self.min_level_touches = min_level_touches
        self.max_distance_to_level = max_distance_to_level_percent / 100.0
        
        # Параметры ЛП
        self.min_fb_depth_atr = min_false_breakout_depth_atr
        self.max_fb_depth_atr = max_false_breakout_depth_atr
        self.prefer_simple_fb = prefer_simple_false_breakouts
        
        # Параметры подтверждения
        self.confirmation_required = confirmation_required
        self.confirmation_distance = confirmation_distance_percent / 100.0
        self.max_time_since_breakout = timedelta(minutes=max_time_since_breakout_minutes)
        
        # Параметры рыночных условий
        self.prefer_strong_levels = prefer_strong_levels
        self.avoid_extreme_volatility = avoid_extreme_volatility
        self.require_clear_reversal = require_clear_reversal
        
        # Параметры ордеров
        self.entry_type = entry_type
        self.limit_offset = limit_offset_percent / 100.0
        self.stop_beyond_extreme = stop_loss_beyond_extreme
        self.take_profit_ratio = take_profit_ratio
        self.use_opposite_level_tp = use_opposite_level_for_tp
        
        # Инициализируем анализаторы
        self.breakout_analyzer = BreakoutAnalyzer(
            false_breakout_max_depth_atr=max_false_breakout_depth_atr,
            true_breakout_min_depth_atr=min_false_breakout_depth_atr
        )
        
        self.pattern_detector = PatternDetector()
        self.market_analyzer = MarketConditionsAnalyzer()
        
        # Статистика стратегии
        self.strategy_stats = {
            "levels_analyzed": 0,
            "false_breakouts_detected": 0,
            "false_breakouts_simple": 0,
            "false_breakouts_strong": 0,
            "false_breakouts_complex": 0,
            "confirmations_passed": 0,
            "signals_generated": 0,
            "filtered_by_time": 0,
            "filtered_by_confirmation": 0,
            "filtered_by_volatility": 0,
            "filtered_by_level_strength": 0
        }
        
        logger.info("🎣 FalseBreakoutStrategy инициализирована")
        logger.info(f"   • Symbol: {symbol}")
        logger.info(f"   • Min level strength: {min_level_strength}")
        logger.info(f"   • FB depth: {min_false_breakout_depth_atr}-{max_false_breakout_depth_atr} ATR")
        logger.info(f"   • Max time after FB: {max_time_since_breakout_minutes} min")
        logger.info(f"   • Entry type: {entry_type}")
    
    # ==================== ОСНОВНОЙ АНАЛИЗ ====================
    
    async def analyze_market_data(
        self,
        market_data: MarketDataSnapshot,
        ta_context: Optional[TechnicalAnalysisContext] = None
    ) -> Optional[TradingSignal]:
        """
        🎯 Основной метод анализа для стратегии ложных пробоев
        
        Алгоритм:
        1. Проверка технического контекста
        2. Анализ рыночных условий
        3. Поиск ближайших уровней
        4. Анализ пробоев через BreakoutAnalyzer
        5. Проверка что это ложный пробой
        6. Проверка подтверждения разворота
        7. Проверка времени после пробоя
        8. Расчет параметров ордера
        9. Генерация сигнала ПРОТИВ пробоя
        
        Args:
            market_data: Снимок рыночных данных
            ta_context: Технический контекст
            
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
            current_time = datetime.now()
            
            # Шаг 2: Анализ рыночных условий
            market_conditions = self.market_analyzer.analyze_conditions(
                candles_h1=ta_context.recent_candles_h1,
                candles_d1=ta_context.recent_candles_d1,
                atr=ta_context.atr_data.calculated_atr if ta_context.atr_data else None,
                current_price=current_price
            )
            
            # Фильтр: Избегаем экстремальной волатильности
            if self.avoid_extreme_volatility:
                if market_conditions.volatility_level == VolatilityLevel.EXTREME:
                    self.strategy_stats["filtered_by_volatility"] += 1
                    if self.debug_mode:
                        logger.debug("⚠️ Экстремальная волатильность")
                    return None
            
            # Шаг 3: Поиск ближайших уровней
            nearest_levels = self._find_nearest_levels(
                ta_context=ta_context,
                current_price=current_price
            )
            
            if not nearest_levels:
                return None
            
            # Шаг 4: Анализ каждого уровня на наличие ЛП
            for level in nearest_levels:
                self.strategy_stats["levels_analyzed"] += 1
                
                # Анализируем пробой через BreakoutAnalyzer
                candles_for_analysis = ta_context.recent_candles_m5 or ta_context.recent_candles_m30
                
                if not candles_for_analysis or len(candles_for_analysis) < 5:
                    continue
                
                breakout_analysis = self.breakout_analyzer.analyze_breakout(
                    candles=candles_for_analysis,
                    level=level,
                    atr=ta_context.atr_data.calculated_atr if ta_context.atr_data else None,
                    current_price=current_price,
                    lookback=20
                )
                
                # Шаг 5: Проверка что это ложный пробой
                if not breakout_analysis.is_false_breakout:
                    continue
                
                self.strategy_stats["false_breakouts_detected"] += 1
                
                # Подсчет статистики по типам
                if breakout_analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_SIMPLE:
                    self.strategy_stats["false_breakouts_simple"] += 1
                elif breakout_analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_STRONG:
                    self.strategy_stats["false_breakouts_strong"] += 1
                elif breakout_analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_COMPLEX:
                    self.strategy_stats["false_breakouts_complex"] += 1
                
                logger.info(f"💥 Ложный пробой обнаружен: {breakout_analysis.breakout_type.value} "
                           f"@ {level.price:.2f}, direction={breakout_analysis.direction.value}")
                
                # Фильтр: Предпочитаем простые ЛП
                if self.prefer_simple_fb:
                    if breakout_analysis.breakout_type != BreakoutType.FALSE_BREAKOUT_SIMPLE:
                        if self.debug_mode:
                            logger.debug(f"⚠️ Пропускаем {breakout_analysis.breakout_type.value}")
                        continue
                
                # Шаг 6: Проверка подтверждения разворота
                if self.confirmation_required:
                    confirmed, confirmation_details = self._check_reversal_confirmation(
                        level=level,
                        breakout_analysis=breakout_analysis,
                        current_price=current_price,
                        ta_context=ta_context
                    )
                    
                    if not confirmed:
                        self.strategy_stats["filtered_by_confirmation"] += 1
                        if self.debug_mode:
                            logger.debug("⚠️ Нет подтверждения разворота")
                        continue
                    
                    self.strategy_stats["confirmations_passed"] += 1
                
                # Шаг 7: Проверка времени после пробоя
                if not self._check_timing(breakout_analysis, current_time):
                    self.strategy_stats["filtered_by_time"] += 1
                    if self.debug_mode:
                        logger.debug("⚠️ Слишком много времени прошло после ЛП")
                    continue
                
                # Шаг 8: Проверка силы уровня
                if self.prefer_strong_levels:
                    if level.strength < self.min_level_strength:
                        self.strategy_stats["filtered_by_level_strength"] += 1
                        if self.debug_mode:
                            logger.debug(f"⚠️ Слабый уровень: {level.strength:.2f}")
                        continue
                
                # Шаг 9: Расчет параметров ордера
                order_params = self._calculate_order_parameters(
                    level=level,
                    breakout_analysis=breakout_analysis,
                    ta_context=ta_context,
                    current_price=current_price
                )
                
                # Шаг 10: Генерация сигнала
                signal = self._create_false_breakout_signal(
                    level=level,
                    breakout_analysis=breakout_analysis,
                    order_params=order_params,
                    market_conditions=market_conditions,
                    current_price=current_price
                )
                
                self.strategy_stats["signals_generated"] += 1
                
                logger.info(f"✅ Сигнал ЛП создан: {signal.signal_type.value} @ {current_price:.2f}")
                
                return signal
            
            # Если не нашли подходящих ЛП
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка в analyze_market_data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    # ==================== ПОИСК УРОВНЕЙ ====================
    
    def _find_nearest_levels(
        self,
        ta_context: TechnicalAnalysisContext,
        current_price: float
    ) -> List[SupportResistanceLevel]:
        """
        Поиск ближайших уровней для анализа ЛП
        
        Ищем уровни в обе стороны от цены (support и resistance)
        
        Args:
            ta_context: Технический контекст
            current_price: Текущая цена
            
        Returns:
            Список подходящих уровней
        """
        try:
            # Фильтруем по силе и касаниям
            suitable_levels = [
                level for level in ta_context.levels_d1
                if level.strength >= self.min_level_strength and
                   level.touches >= self.min_level_touches
            ]
            
            if not suitable_levels:
                return []
            
            # Ищем ближайшие уровни в обе стороны
            candidates = []
            
            for level in suitable_levels:
                distance = abs(level.price - current_price)
                distance_percent = distance / current_price
                
                if distance_percent <= self.max_distance_to_level:
                    candidates.append(level)
            
            # Сортируем по расстоянию
            candidates.sort(key=lambda l: abs(l.price - current_price))
            
            # Берем 2-3 ближайших
            nearest = candidates[:3]
            
            if nearest:
                logger.debug(f"🎯 Найдено {len(nearest)} ближайших уровней для анализа ЛП")
            
            return nearest
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска уровней: {e}")
            return []
    
    # ==================== ПОДТВЕРЖДЕНИЕ РАЗВОРОТА ====================
    
    def _check_reversal_confirmation(
        self,
        level: SupportResistanceLevel,
        breakout_analysis: Any,
        current_price: float,
        ta_context: TechnicalAnalysisContext
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Проверка подтверждения разворота после ЛП
        
        Подтверждение = цена вернулась за уровень и закрепилась
        
        Args:
            level: Уровень
            breakout_analysis: Результат анализа пробоя
            current_price: Текущая цена
            ta_context: Технический контекст
            
        Returns:
            Tuple[подтверждено?, детали]
        """
        try:
            details = {}
            
            # Определяем куда должна вернуться цена
            if breakout_analysis.direction == BreakoutDirection.UPWARD:
                # ЛП вверх → цена должна быть ниже уровня
                must_be_below = True
                target_zone = level.price - (level.price * self.confirmation_distance)
                
                confirmed = current_price < target_zone
                
                details["direction"] = "below"
                details["target_zone"] = target_zone
                details["current_price"] = current_price
                details["confirmed"] = confirmed
                
                if confirmed:
                    logger.info(f"✅ Подтверждение разворота: цена {current_price:.2f} < {target_zone:.2f}")
                else:
                    logger.debug(f"⚠️ Нет подтверждения: цена {current_price:.2f} >= {target_zone:.2f}")
            
            elif breakout_analysis.direction == BreakoutDirection.DOWNWARD:
                # ЛП вниз → цена должна быть выше уровня
                must_be_above = True
                target_zone = level.price + (level.price * self.confirmation_distance)
                
                confirmed = current_price > target_zone
                
                details["direction"] = "above"
                details["target_zone"] = target_zone
                details["current_price"] = current_price
                details["confirmed"] = confirmed
                
                if confirmed:
                    logger.info(f"✅ Подтверждение разворота: цена {current_price:.2f} > {target_zone:.2f}")
                else:
                    logger.debug(f"⚠️ Нет подтверждения: цена {current_price:.2f} <= {target_zone:.2f}")
            
            else:
                return False, details
            
            # Дополнительная проверка - импульс разворота
            if confirmed and self.require_clear_reversal:
                if ta_context.recent_candles_m5:
                    last_candles = ta_context.recent_candles_m5[-3:]
                    
                    if len(last_candles) >= 2:
                        # Проверяем что последние свечи идут в направлении разворота
                        closes = [float(c.close_price) for c in last_candles]
                        
                        if breakout_analysis.direction == BreakoutDirection.UPWARD:
                            # Должны идти вниз
                            reversal_confirmed = closes[-1] < closes[0]
                        else:
                            # Должны идти вверх
                            reversal_confirmed = closes[-1] > closes[0]
                        
                        details["clear_reversal"] = reversal_confirmed
                        
                        if not reversal_confirmed:
                            logger.debug("⚠️ Нет четкого импульса разворота")
                            return False, details
            
            return confirmed, details
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки подтверждения: {e}")
            return False, {}
    
    # ==================== ПРОВЕРКА ТАЙМИНГА ====================
    
    def _check_timing(
        self,
        breakout_analysis: Any,
        current_time: datetime
    ) -> bool:
        """
        Проверка времени после ложного пробоя
        
        Не торгуем старые ЛП (> 30 минут)
        
        Args:
            breakout_analysis: Результат анализа пробоя
            current_time: Текущее время
            
        Returns:
            True если время подходит
        """
        try:
            if not breakout_analysis.breakout_candle:
                return False
            
            # Время свечи пробоя
            breakout_time = breakout_analysis.breakout_candle.close_time
            
            # Прошедшее время
            time_since = current_time - breakout_time
            
            is_valid = time_since <= self.max_time_since_breakout
            
            if is_valid:
                minutes_since = time_since.total_seconds() / 60
                logger.debug(f"✅ Тайминг OK: {minutes_since:.0f} минут после ЛП")
            else:
                minutes_since = time_since.total_seconds() / 60
                logger.debug(f"⚠️ Слишком поздно: {minutes_since:.0f} минут после ЛП")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки тайминга: {e}")
            return False
    
    # ==================== РАСЧЕТ ПАРАМЕТРОВ ОРДЕРА ====================
    
    def _calculate_order_parameters(
        self,
        level: SupportResistanceLevel,
        breakout_analysis: Any,
        ta_context: TechnicalAnalysisContext,
        current_price: float
    ) -> Dict[str, float]:
        """
        Расчет параметров ордера для торговли ЛП
        
        Механика:
        - Entry: Market или Limit от уровня
        - Stop Loss: за зону ЛП (High/Low пробоя × 1.1)
        - Take Profit: 2-3 стопа или до противоположного уровня
        
        Args:
            level: Уровень ЛП
            breakout_analysis: Результат анализа пробоя
            ta_context: Технический контекст
            current_price: Текущая цена
            
        Returns:
            Словарь с параметрами ордера
        """
        try:
            direction = breakout_analysis.direction
            
            # ATR для расчетов
            atr = ta_context.atr_data.calculated_atr if ta_context.atr_data else current_price * 0.02
            
            # Определяем зону ЛП (High/Low свечи пробоя)
            if breakout_analysis.breakout_candle:
                fb_candle = breakout_analysis.breakout_candle
                fb_high = float(fb_candle.high_price)
                fb_low = float(fb_candle.low_price)
            else:
                fb_high = level.price * 1.01
                fb_low = level.price * 0.99
            
            # ENTRY PRICE
            if self.entry_type == "market":
                entry_price = current_price
            else:
                # Limit ордер от уровня
                offset = level.price * self.limit_offset
                
                if direction == BreakoutDirection.UPWARD:
                    # ЛП вверх → входим в SHORT → лимит выше
                    entry_price = level.price + offset
                else:
                    # ЛП вниз → входим в LONG → лимит ниже
                    entry_price = level.price - offset
            
            # STOP LOSS (за зону ЛП)
            if direction == BreakoutDirection.UPWARD:
                # ЛП вверх → SHORT → стоп выше High ЛП
                stop_loss = fb_high * self.stop_beyond_extreme
                stop_distance = abs(entry_price - stop_loss)
            else:
                # ЛП вниз → LONG → стоп ниже Low ЛП
                stop_loss = fb_low / self.stop_beyond_extreme
                stop_distance = abs(stop_loss - entry_price)
            
            # TAKE PROFIT
            # Вариант 1: По соотношению к стопу
            basic_tp_distance = stop_distance * self.take_profit_ratio
            
            if direction == BreakoutDirection.UPWARD:
                # SHORT
                basic_tp = entry_price - basic_tp_distance
            else:
                # LONG
                basic_tp = entry_price + basic_tp_distance
            
            # Вариант 2: До противоположного уровня
            if self.use_opposite_level_tp:
                opposite_level = self._find_opposite_level(
                    ta_context=ta_context,
                    current_price=current_price,
                    direction=direction
                )
                
                if opposite_level:
                    # Используем ближайшее: либо расчетный TP, либо уровень
                    if direction == BreakoutDirection.UPWARD:
                        # SHORT → берем максимум из двух (ближайший вниз)
                        take_profit = max(basic_tp, opposite_level.price)
                    else:
                        # LONG → берем минимум из двух (ближайший вверх)
                        take_profit = min(basic_tp, opposite_level.price)
                    
                    logger.debug(f"📊 TP скорректирован до уровня: {take_profit:.2f}")
                else:
                    take_profit = basic_tp
            else:
                take_profit = basic_tp
            
            # Итоговое соотношение R:R
            actual_tp_distance = abs(take_profit - entry_price)
            actual_rr_ratio = actual_tp_distance / stop_distance if stop_distance > 0 else 0
            
            params = {
                "entry_price": entry_price,
                "entry_type": self.entry_type,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "stop_distance": stop_distance,
                "tp_distance": actual_tp_distance,
                "risk_reward_ratio": actual_rr_ratio,
                "level_price": level.price,
                "fb_high": fb_high,
                "fb_low": fb_low,
                "atr_used": atr
            }
            
            logger.debug(f"📊 Параметры ордера ЛП: Entry={entry_price:.2f} ({self.entry_type}), "
                        f"SL={stop_loss:.2f}, TP={take_profit:.2f}, R:R={actual_rr_ratio:.1f}:1")
            
            return params
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета параметров: {e}")
            return {}
    
    def _find_opposite_level(
        self,
        ta_context: TechnicalAnalysisContext,
        current_price: float,
        direction: BreakoutDirection
    ) -> Optional[SupportResistanceLevel]:
        """
        Найти противоположный уровень для Take Profit
        
        Args:
            ta_context: Технический контекст
            current_price: Текущая цена
            direction: Направление ЛП
            
        Returns:
            Противоположный уровень или None
        """
        try:
            if direction == BreakoutDirection.UPWARD:
                # ЛП вверх → SHORT → ищем поддержку ниже
                return ta_context.get_nearest_support(current_price, max_distance_percent=5.0)
            else:
                # ЛП вниз → LONG → ищем сопротивление выше
                return ta_context.get_nearest_resistance(current_price, max_distance_percent=5.0)
        except:
            return None
    
    # ==================== СОЗДАНИЕ СИГНАЛА ====================
    
    def _create_false_breakout_signal(
        self,
        level: SupportResistanceLevel,
        breakout_analysis: Any,
        order_params: Dict[str, float],
        market_conditions: Any,
        current_price: float
    ) -> TradingSignal:
        """
        Создание торгового сигнала после ЛП
        
        Торгуем ПРОТИВ направления пробоя:
        - ЛП вверх → SELL
        - ЛП вниз → BUY
        
        Args:
            level: Уровень ЛП
            breakout_analysis: Анализ пробоя
            order_params: Параметры ордера
            market_conditions: Условия рынка
            current_price: Текущая цена
            
        Returns:
            TradingSignal
        """
        try:
            # Определяем тип сигнала (ПРОТИВ пробоя)
            if breakout_analysis.direction == BreakoutDirection.UPWARD:
                # ЛП вверх → входим в SHORT
                signal_type = SignalType.SELL
                
                # Если простой ЛП и высокая уверенность → STRONG
                if (breakout_analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_SIMPLE and
                    breakout_analysis.confidence >= 0.8):
                    signal_type = SignalType.STRONG_SELL
            
            else:
                # ЛП вниз → входим в LONG
                signal_type = SignalType.BUY
                
                # Если простой ЛП и высокая уверенность → STRONG
                if (breakout_analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_SIMPLE and
                    breakout_analysis.confidence >= 0.8):
                    signal_type = SignalType.STRONG_BUY
            
            # Расчет силы сигнала
            strength = self._calculate_signal_strength(
                breakout_analysis=breakout_analysis,
                level=level,
                market_conditions=market_conditions
            )
            
            # Расчет уверенности
            confidence = self._calculate_signal_confidence(
                breakout_analysis=breakout_analysis,
                level=level,
                order_params=order_params
            )
            
            # Причины
            reasons = self._build_signal_reasons(
                level=level,
                breakout_analysis=breakout_analysis,
                order_params=order_params
            )
            
            # Создаем сигнал
            signal = self.create_signal(
                signal_type=signal_type,
                strength=strength,
                confidence=confidence,
                current_price=current_price,
                reasons=reasons
            )
            
            # Параметры ордера
            signal.stop_loss = order_params.get("stop_loss")
            signal.take_profit = order_params.get("take_profit")
            
            # Размер позиции
            signal.position_size_recommendation = min(
                0.02 * confidence,  # До 2% при макс уверенности
                0.04  # Но не более 4%
            )
            
            # Технические индикаторы
            signal.add_technical_indicator(
                "false_breakout_type",
                breakout_analysis.breakout_type.value,
                f"Тип ЛП: {breakout_analysis.breakout_type.value}"
            )
            
            signal.add_technical_indicator(
                "level_price",
                level.price,
                f"{level.level_type} @ {level.price:.2f}"
            )
            
            signal.add_technical_indicator(
                "breakout_depth_atr",
                breakout_analysis.breakout_depth_atr_ratio,
                f"Глубина: {breakout_analysis.breakout_depth_atr_ratio:.2f} ATR"
            )
            
            signal.add_technical_indicator(
                "entry_type",
                order_params.get("entry_type"),
                f"Вход: {order_params.get('entry_type')}"
            )
            
            signal.add_technical_indicator(
                "risk_reward",
                order_params.get("risk_reward_ratio"),
                f"R:R = {order_params.get('risk_reward_ratio'):.1f}:1"
            )
            
            # Метаданные
            signal.technical_indicators["breakout_analysis"] = breakout_analysis.to_dict()
            signal.technical_indicators["order_params"] = order_params
            signal.market_conditions = {
                "market_condition": market_conditions.market_condition.value,
                "volatility": market_conditions.volatility_level.value,
                "trend_direction": market_conditions.trend_direction.value
            }
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания сигнала: {e}")
            # Создаем базовый сигнал
            return self.create_signal(
                signal_type=SignalType.SELL if breakout_analysis.direction == BreakoutDirection.UPWARD else SignalType.BUY,
                strength=0.5,
                confidence=0.5,
                current_price=current_price,
                reasons=["Ложный пробой уровня"]
            )
    
    def _calculate_signal_strength(
        self,
        breakout_analysis: Any,
        level: SupportResistanceLevel,
        market_conditions: Any
    ) -> float:
        """Расчет силы сигнала"""
        strength = 0.5  # Базовая
        
        # Бонус за тип ЛП
        if breakout_analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_SIMPLE:
            strength += 0.2  # Простой ЛП = самый надежный
        elif breakout_analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_STRONG:
            strength += 0.15
        elif breakout_analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_COMPLEX:
            strength += 0.1
        
        # Бонус за силу BreakoutAnalysis
        strength += breakout_analysis.strength * 0.2
        
        # Бонус за сильный уровень
        if level.is_strong:
            strength += 0.1
        
        # Штраф за высокую волатильность
        if market_conditions.volatility_level == VolatilityLevel.HIGH:
            strength -= 0.1
        
        return min(1.0, max(0.1, strength))
    
    def _calculate_signal_confidence(
        self,
        breakout_analysis: Any,
        level: SupportResistanceLevel,
        order_params: Dict[str, float]
    ) -> float:
        """Расчет уверенности в сигнале"""
        confidence = 0.6  # Базовая
        
        # Бонус за уверенность в ЛП
        confidence += breakout_analysis.confidence * 0.2
        
        # Бонус за простой ЛП
        if breakout_analysis.breakout_type == BreakoutType.FALSE_BREAKOUT_SIMPLE:
            confidence += 0.1
        
        # Бонус за сильный уровень
        if level.strength >= 0.8:
            confidence += 0.1
        
        # Бонус за хороший R:R
        rr_ratio = order_params.get("risk_reward_ratio", 0)
        if rr_ratio >= 3.0:
            confidence += 0.05
        
        return min(1.0, confidence)
    
    def _build_signal_reasons(
        self,
        level: SupportResistanceLevel,
        breakout_analysis: Any,
        order_params: Dict[str, float]
    ) -> List[str]:
        """Построение списка причин сигнала"""
        reasons = []
        
        # Тип ЛП
        fb_type_names = {
            BreakoutType.FALSE_BREAKOUT_SIMPLE: "Простой ЛП (1 бар)",
            BreakoutType.FALSE_BREAKOUT_STRONG: "Сильный ЛП (2 бара)",
            BreakoutType.FALSE_BREAKOUT_COMPLEX: "Сложный ЛП (3+ бара)"
        }
        
        fb_name = fb_type_names.get(breakout_analysis.breakout_type, "Ложный пробой")
        
        direction_text = "вверх" if breakout_analysis.direction == BreakoutDirection.UPWARD else "вниз"
        reasons.append(f"{fb_name} {direction_text} через {level.level_type} @ {level.price:.2f}")
        
        # Глубина пробоя
        if breakout_analysis.breakout_depth_atr_ratio > 0:
            reasons.append(f"Глубина пробоя: {breakout_analysis.breakout_depth_atr_ratio:.2f} ATR")
        
        # Подтверждение разворота
        reasons.append("Цена подтвердила разворот за уровень")
        
        # Сила уровня
        if level.is_strong:
            reasons.append(f"Сильный уровень: strength={level.strength:.2f}, touches={level.touches}")
        
        # R:R
        rr_ratio = order_params.get("risk_reward_ratio", 0)
        if rr_ratio > 0:
            reasons.append(f"Соотношение R:R = {rr_ratio:.1f}:1")
        
        # Тип входа
        entry_type = order_params.get("entry_type", "market")
        if entry_type == "limit":
            reasons.append(f"Лимит ордер от {order_params.get('entry_price'):.2f}")
        
        return reasons
    
    # ==================== СТАТИСТИКА ====================
    
    def get_strategy_stats(self) -> Dict[str, Any]:
        """Получить статистику стратегии"""
        base_stats = self.get_stats()
        
        return {
            **base_stats,
            "strategy_type": "FalseBreakoutStrategy",
            "strategy_stats": self.strategy_stats.copy(),
            "config": {
                "min_level_strength": self.min_level_strength,
                "fb_depth_range_atr": f"{self.min_fb_depth_atr}-{self.max_fb_depth_atr}",
                "prefer_simple_fb": self.prefer_simple_fb,
                "confirmation_required": self.confirmation_required,
                "max_time_after_fb_minutes": self.max_time_since_breakout.total_seconds() / 60,
                "entry_type": self.entry_type,
                "take_profit_ratio": self.take_profit_ratio
            }
        }
    
    def __str__(self):
        stats = self.get_strategy_stats()
        return (f"FalseBreakoutStrategy(symbol={self.symbol}, "
                f"fb_detected={stats['strategy_stats']['false_breakouts_detected']}, "
                f"signals={stats['signals_sent']}, "
                f"simple_fb={stats['strategy_stats']['false_breakouts_simple']}, "
                f"success_rate={stats['analysis_success_rate']:.1f}%)")


# Export
__all__ = ["FalseBreakoutStrategy"]

logger.info("✅ False Breakout Strategy module loaded")
