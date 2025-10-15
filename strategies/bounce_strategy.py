"""
Bounce Strategy - Стратегия торговли отбоя (БСУ-БПУ модель)

Торгует отбой от сильного уровня при подтверждении его значимости.

Ключевые элементы:
1. БСУ (Бар Создавший Уровень) - исторический бар, создавший уровень
2. БПУ-1 (Бар Подтвердивший Уровень) - первое касание "точка в точку"
3. БПУ-2 - второе касание, должно быть пучком с БПУ-1

Механика входа:
- За 30 сек до закрытия БПУ-2 → Limit ордер от уровня ± люфт
- Stop Loss → сразу при выставлении (технический, за уровень)
- Люфт = 20% от Stop Loss
- ТВХ (Точка Входа) = уровень ± люфт
- Take Profit = Stop × 3 (минимум 3:1)

Условия отбоя (предпосылки):
- Подход паранормальными барами
- Пройдено 75-80% ATR (запас хода исчерпан)
- Дальний ретест (>1 месяца)
- Подход большими барами
- Закрытие далеко от уровня
- Было сильное движение (>10-15%)

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
    SupportResistanceLevel,
    BSUPattern,
    BPUPattern
)

logger = logging.getLogger(__name__)


class BounceStrategy(BaseStrategy):
    """
    🎯 Стратегия торговли отбоя от уровня (БСУ-БПУ модель)
    
    Ловит отскок цены от сильного уровня поддержки/сопротивления.
    Использует модель БСУ-БПУ для подтверждения валидности уровня.
    
    Сильные стороны:
    - Высокая точность (уровень подтвержден касаниями)
    - Четкая точка входа (за 30 сек до закрытия БПУ-2)
    - Хороший R:R (минимум 3:1)
    - Работает при исчерпанном ATR
    
    Слабые стороны:
    - Требует точного тайминга (30 сек до закрытия)
    - Нужны БСУ и минимум 2 БПУ
    - Не работает в сильном тренде
    
    Usage:
        strategy = BounceStrategy(
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
        min_level_strength: float = 0.6,        # Минимальная сила уровня (выше чем у пробоя)
        min_level_touches: int = 2,             # Минимум касаний
        max_distance_to_level_percent: float = 1.0,  # Максимальное расстояние до уровня
        
        # Параметры БСУ
        bsu_max_age_days: int = 180,            # Максимальный возраст БСУ
        
        # Параметры БПУ
        require_bpu1: bool = True,              # Требовать БПУ-1
        require_bpu2: bool = True,              # Требовать БПУ-2
        bpu_touch_tolerance: float = 0.2,       # Допуск касания БПУ (%)
        bpu2_cluster_tolerance: float = 0.3,    # Допуск пучка БПУ-2 с БПУ-1
        
        # Параметры тайминга
        seconds_before_close: int = 30,         # Секунд до закрытия БПУ-2 для входа
        
        # Предпосылки для отбоя
        prefer_far_retest: bool = True,         # Предпочитать дальний ретест (>1 мес)
        far_retest_min_days: int = 30,          # Минимум дней для дальнего ретеста
        prefer_atr_exhausted: bool = True,      # Предпочитать исчерпанный ATR
        atr_exhaustion_min: float = 0.75,       # Минимум 75% ATR для отбоя
        
        # Параметры ордеров
        stop_loss_percent_of_atr: float = 0.05,  # 5% ATR для контртренда
        gap_percent_of_stop: float = 0.20,      # Люфт = 20% от Stop Loss
        take_profit_ratio: float = 3.0,         # TP:SL = 3:1
        order_cancel_distance_stops: float = 2.0,  # Отмена если цена > 2 стопов
        
        # Настройки стратегии
        min_signal_strength: float = 0.6,
        signal_cooldown_minutes: int = 15,
        max_signals_per_hour: int = 4,
    ):
        """
        Инициализация стратегии отбоя
        
        Args:
            symbol: Торговый символ
            ta_context_manager: Менеджер технического анализа
            [остальные параметры см. выше]
        """
        super().__init__(
            name="BounceStrategy",
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
        
        # Параметры БСУ
        self.bsu_max_age_days = bsu_max_age_days
        
        # Параметры БПУ
        self.require_bpu1 = require_bpu1
        self.require_bpu2 = require_bpu2
        self.bpu_touch_tolerance = bpu_touch_tolerance / 100.0
        self.bpu2_cluster_tolerance = bpu2_cluster_tolerance / 100.0
        
        # Параметры тайминга
        self.seconds_before_close = seconds_before_close
        
        # Предпосылки
        self.prefer_far_retest = prefer_far_retest
        self.far_retest_min_days = far_retest_min_days
        self.prefer_atr_exhausted = prefer_atr_exhausted
        self.atr_exhaustion_min = atr_exhaustion_min
        
        # Параметры ордеров
        self.stop_loss_percent = stop_loss_percent_of_atr
        self.gap_percent = gap_percent_of_stop
        self.take_profit_ratio = take_profit_ratio
        self.order_cancel_distance = order_cancel_distance_stops
        
        # Инициализируем анализаторы
        self.pattern_detector = PatternDetector(
            bpu_touch_tolerance_percent=bpu_touch_tolerance,
            bpu_max_gap_percent=bpu2_cluster_tolerance
        )
        
        self.market_analyzer = MarketConditionsAnalyzer()
        
        # Статистика стратегии
        self.strategy_stats = {
            "levels_analyzed": 0,
            "bsu_found": 0,
            "bpu1_found": 0,
            "bpu2_found": 0,
            "bpu2_clusters_found": 0,
            "setups_found": 0,
            "signals_generated": 0,
            "timing_missed": 0,
            "far_retests": 0,
            "atr_exhausted_entries": 0
        }
        
        logger.info("🎯 BounceStrategy инициализирована")
        logger.info(f"   • Symbol: {symbol}")
        logger.info(f"   • Require BPU-1: {require_bpu1}, BPU-2: {require_bpu2}")
        logger.info(f"   • Entry timing: {seconds_before_close}s before close")
        logger.info(f"   • Prefer far retest: {prefer_far_retest}")
        logger.info(f"   • Prefer ATR exhausted: {prefer_atr_exhausted}")
    
    # ==================== ОСНОВНОЙ АНАЛИЗ ====================
    
    async def analyze_market_data(
        self,
        market_data: MarketDataSnapshot,
        ta_context: Optional[TechnicalAnalysisContext] = None
    ) -> Optional[TradingSignal]:
        """
        🎯 Основной метод анализа для стратегии отбоя
        
        Алгоритм:
        1. Проверка технического контекста
        2. Поиск подходящих уровней (сильные, близкие)
        3. Поиск БСУ для уровня
        4. Поиск БПУ-1 и БПУ-2
        5. Проверка пучка БПУ-2 с БПУ-1
        6. Проверка тайминга (30 сек до закрытия)
        7. Проверка предпосылок для отбоя
        8. Расчет параметров ордера
        9. Генерация сигнала
        
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
            
            # Шаг 2: Поиск ближайшего сильного уровня
            nearest_level, direction = self._find_nearest_level_for_bounce(
                ta_context=ta_context,
                current_price=current_price
            )
            
            if not nearest_level:
                return None
            
            self.strategy_stats["levels_analyzed"] += 1
            
            # Шаг 3: Поиск БСУ для уровня
            bsu = self.pattern_detector.find_bsu(
                candles=ta_context.recent_candles_d1,
                level=nearest_level,
                max_age_days=self.bsu_max_age_days
            )
            
            if not bsu:
                if self.debug_mode:
                    logger.debug(f"⚠️ БСУ не найден для уровня {nearest_level.price:.2f}")
                return None
            
            self.strategy_stats["bsu_found"] += 1
            logger.debug(f"✅ БСУ найден: возраст {bsu.age_days} дней")
            
            # Шаг 4: Поиск БПУ (на M30 или H1)
            candles_for_bpu = ta_context.recent_candles_m30 or ta_context.recent_candles_h1
            
            if not candles_for_bpu or len(candles_for_bpu) < 2:
                if self.debug_mode:
                    logger.debug("⚠️ Недостаточно свечей для поиска БПУ")
                return None
            
            bpu_list = self.pattern_detector.find_bpu(
                candles=candles_for_bpu,
                level=nearest_level,
                lookback=50
            )
            
            if not bpu_list:
                if self.debug_mode:
                    logger.debug("⚠️ БПУ не найдены")
                return None
            
            # Шаг 5: Проверка наличия БПУ-1 и БПУ-2
            bpu1 = None
            bpu2 = None
            
            for bpu in bpu_list:
                if bpu.is_bpu1:
                    bpu1 = bpu
                    self.strategy_stats["bpu1_found"] += 1
                if bpu.is_bpu2:
                    bpu2 = bpu
                    self.strategy_stats["bpu2_found"] += 1
            
            # Проверка требований
            if self.require_bpu1 and not bpu1:
                if self.debug_mode:
                    logger.debug("⚠️ БПУ-1 не найден (требуется)")
                return None
            
            if self.require_bpu2 and not bpu2:
                if self.debug_mode:
                    logger.debug("⚠️ БПУ-2 не найден (требуется)")
                return None
            
            # Проверка пучка БПУ-2 с БПУ-1
            if bpu2 and not bpu2.forms_cluster_with:
                if self.debug_mode:
                    logger.debug("⚠️ БПУ-2 не формирует пучок с БПУ-1")
                return None
            
            self.strategy_stats["bpu2_clusters_found"] += 1
            logger.info("✅ БПУ-2 формирует пучок с БПУ-1")
            
            # Шаг 6: Проверка тайминга (за 30 сек до закрытия БПУ-2)
            if not self._check_timing(bpu2, current_time):
                self.strategy_stats["timing_missed"] += 1
                if self.debug_mode:
                    logger.debug("⚠️ Неправильный тайминг (не за 30 сек до закрытия)")
                return None
            
            logger.info("✅ Тайминг корректен (за 30 сек до закрытия БПУ-2)")
            
            # Шаг 7: Проверка предпосылок для отбоя
            bounce_score, bounce_details = self._check_bounce_preconditions(
                level=nearest_level,
                ta_context=ta_context,
                market_data=market_data
            )
            
            if bounce_score < 2:  # Минимум 2 предпосылки
                if self.debug_mode:
                    logger.debug(f"⚠️ Недостаточно предпосылок: {bounce_score}/5")
                return None
            
            self.strategy_stats["setups_found"] += 1
            logger.info(f"✅ Предпосылки для отбоя: {bounce_score}/5")
            
            # Шаг 8: Расчет параметров ордера
            order_params = self._calculate_order_parameters(
                level=nearest_level,
                direction=direction,
                ta_context=ta_context,
                current_price=current_price
            )
            
            # Шаг 9: Проверка валидности ордера
            if not self._check_order_validity(order_params, current_price):
                if self.debug_mode:
                    logger.debug("⚠️ Ордер невалиден (цена слишком далеко)")
                return None
            
            # Шаг 10: Генерация сигнала
            signal = self._create_bounce_signal(
                level=nearest_level,
                direction=direction,
                bsu=bsu,
                bpu1=bpu1,
                bpu2=bpu2,
                order_params=order_params,
                bounce_details=bounce_details,
                current_price=current_price
            )
            
            self.strategy_stats["signals_generated"] += 1
            
            logger.info(f"✅ Сигнал отбоя создан: {direction} от {nearest_level.price:.2f}")
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ Ошибка в analyze_market_data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    # ==================== ПОИСК УРОВНЕЙ ====================
    
    def _find_nearest_level_for_bounce(
        self,
        ta_context: TechnicalAnalysisContext,
        current_price: float
    ) -> Tuple[Optional[SupportResistanceLevel], str]:
        """
        Поиск ближайшего сильного уровня для отбоя
        
        Критерии:
        - Сильный уровень (strength >= 0.6)
        - Минимум 2 касания
        - Близко к текущей цене (< 1%)
        
        Args:
            ta_context: Технический контекст
            current_price: Текущая цена
            
        Returns:
            Tuple[уровень, направление ("up"/"down")]
        """
        try:
            # Фильтруем по силе и касаниям
            suitable_levels = [
                level for level in ta_context.levels_d1
                if level.strength >= self.min_level_strength and
                   level.touches >= self.min_level_touches
            ]
            
            if not suitable_levels:
                return None, None
            
            # Ищем поддержку ниже цены (отбой вверх)
            supports = [
                level for level in suitable_levels
                if level.level_type == "support" and level.price < current_price
            ]
            
            # Ищем сопротивление выше цены (отбой вниз)
            resistances = [
                level for level in suitable_levels
                if level.level_type == "resistance" and level.price > current_price
            ]
            
            # Определяем ближайший
            candidates = []
            
            if supports:
                nearest_support = min(supports, key=lambda l: abs(l.price - current_price))
                distance = abs(nearest_support.price - current_price) / current_price
                if distance <= self.max_distance_to_level:
                    candidates.append((nearest_support, "up", distance))
            
            if resistances:
                nearest_resistance = min(resistances, key=lambda l: abs(l.price - current_price))
                distance = abs(nearest_resistance.price - current_price) / current_price
                if distance <= self.max_distance_to_level:
                    candidates.append((nearest_resistance, "down", distance))
            
            if not candidates:
                return None, None
            
            # Выбираем ближайший
            best = min(candidates, key=lambda x: x[2])
            level, direction, distance = best
            
            logger.debug(f"🎯 Найден уровень для отбоя: {level.level_type} @ {level.price:.2f}, "
                        f"distance={distance*100:.2f}%, strength={level.strength:.2f}, "
                        f"touches={level.touches}")
            
            return level, direction
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска уровня: {e}")
            return None, None
    
    # ==================== ПРОВЕРКА ТАЙМИНГА ====================
    
    def _check_timing(self, bpu2: BPUPattern, current_time: datetime) -> bool:
        """
        Проверка тайминга входа (за 30 сек до закрытия БПУ-2)
        
        Args:
            bpu2: Паттерн БПУ-2
            current_time: Текущее время
            
        Returns:
            True если время подходит
        """
        try:
            if not bpu2 or not bpu2.candle:
                return False
            
            # Время закрытия свечи БПУ-2
            candle_close_time = bpu2.candle.close_time
            
            # Время входа: за 30 секунд до закрытия
            entry_time_start = candle_close_time - timedelta(seconds=self.seconds_before_close)
            entry_time_end = candle_close_time
            
            # Проверяем что текущее время в окне
            is_valid = entry_time_start <= current_time <= entry_time_end
            
            if is_valid:
                seconds_until_close = (entry_time_end - current_time).total_seconds()
                logger.debug(f"✅ Тайминг OK: {seconds_until_close:.0f}s до закрытия БПУ-2")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки тайминга: {e}")
            return False
    
    # ==================== ПРЕДПОСЫЛКИ ДЛЯ ОТБОЯ ====================
    
    def _check_bounce_preconditions(
        self,
        level: SupportResistanceLevel,
        ta_context: TechnicalAnalysisContext,
        market_data: MarketDataSnapshot
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Проверка предпосылок для отбоя
        
        Из документа:
        1. ✅ Подход паранормальными барами
        2. ✅ Пройдено 75-80% ATR
        3. ✅ Дальний ретест (>1 месяца)
        4. ✅ Подход большими барами (>3)
        5. ✅ Закрытие далеко от уровня
        6. Было сильное движение (>10-15%)
        
        Args:
            level: Уровень
            ta_context: Технический контекст
            market_data: Рыночные данные
            
        Returns:
            Tuple[score (0-5), детали]
        """
        try:
            score = 0
            details = {}
            
            # 1. ATR исчерпан (75-80%)
            atr_exhausted = False
            if ta_context.atr_data:
                atr_exhausted = ta_context.is_atr_exhausted(self.atr_exhaustion_min)
                details["atr_exhausted"] = atr_exhausted
                details["atr_used_percent"] = ta_context.atr_data.current_range_used
                
                if atr_exhausted:
                    score += 1
                    self.strategy_stats["atr_exhausted_entries"] += 1
                    logger.debug(f"✅ ATR исчерпан: {ta_context.atr_data.current_range_used:.1f}%")
            
            # 2. Дальний ретест (>1 месяца)
            far_retest = False
            if level.last_touch:
                days_since = (datetime.now() - level.last_touch).days
                far_retest = days_since >= self.far_retest_min_days
                details["days_since_touch"] = days_since
                details["far_retest"] = far_retest
                
                if far_retest:
                    score += 1
                    self.strategy_stats["far_retests"] += 1
                    logger.debug(f"✅ Дальний ретест: {days_since} дней")
            
            # 3. Подход большими барами
            big_bars_approach = False
            if ta_context.recent_candles_h1 and len(ta_context.recent_candles_h1) >= 5:
                recent = ta_context.recent_candles_h1[-5:]
                
                # ATR для сравнения
                atr = ta_context.atr_data.calculated_atr if ta_context.atr_data else None
                
                if atr:
                    ranges = [float(c.high_price - c.low_price) for c in recent]
                    avg_range = sum(ranges) / len(ranges)
                    
                    # Большие бары если avg_range > 0.8×ATR
                    big_bars_approach = avg_range > (atr * 0.8)
                    details["big_bars_approach"] = big_bars_approach
                    details["avg_bar_range"] = avg_range
                    
                    if big_bars_approach:
                        score += 1
                        logger.debug("✅ Подход большими барами")
            
            # 4. Закрытие далеко от уровня
            close_far_from_level = False
            if ta_context.recent_candles_m30:
                last_candle = ta_context.recent_candles_m30[-1]
                close = float(last_candle['close_price'])
                
                distance = abs(close - level.price)
                distance_percent = distance / level.price * 100
                
                # Далеко если > 0.5%
                close_far_from_level = distance_percent > 0.5
                details["close_distance_percent"] = distance_percent
                details["close_far_from_level"] = close_far_from_level
                
                if close_far_from_level:
                    score += 1
                    logger.debug(f"✅ Закрытие далеко: {distance_percent:.2f}%")
            
            # 5. Сильное предшествующее движение
            strong_move = False
            change_24h = abs(market_data.price_change_24h)
            
            if change_24h > 10.0:  # > 10%
                strong_move = True
                score += 1
                details["strong_move"] = strong_move
                details["move_percent"] = change_24h
                logger.debug(f"✅ Сильное движение: {change_24h:.1f}%")
            
            details["preconditions_score"] = score
            
            logger.info(f"📊 Предпосылки для отбоя: {score}/5")
            
            return score, details
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки предпосылок: {e}")
            return 0, {}
    
    # ==================== РАСЧЕТ ПАРАМЕТРОВ ОРДЕРА ====================
    
    def _calculate_order_parameters(
        self,
        level: SupportResistanceLevel,
        direction: str,
        ta_context: TechnicalAnalysisContext,
        current_price: float
    ) -> Dict[str, float]:
        """
        Расчет параметров Limit ордера
        
        Механика из документа:
        1. Люфт = 20% от Stop Loss
        2. ТВХ (Точка Входа) = уровень ± люфт
        3. Stop = ТВХ ± размер стопа
        4. Take Profit = Stop × 3
        
        Args:
            level: Уровень отбоя
            direction: Направление
            ta_context: Технический контекст
            current_price: Текущая цена
            
        Returns:
            Словарь с параметрами
        """
        try:
            level_price = level.price
            
            # ATR для расчетов
            atr = ta_context.atr_data.calculated_atr if ta_context.atr_data else level_price * 0.02
            
            # Stop Loss = 5% ATR (контртренд)
            stop_distance = atr * self.stop_loss_percent
            
            # Люфт = 20% от Stop Loss
            gap = stop_distance * self.gap_percent
            
            if direction == "up":
                # Отбой от поддержки (вверх)
                entry_price = level_price + gap  # ТВХ выше уровня
                stop_loss = entry_price - stop_distance  # Stop ниже ТВХ
                take_profit = entry_price + (stop_distance * self.take_profit_ratio)
                
            else:
                # Отбой от сопротивления (вниз)
                entry_price = level_price - gap  # ТВХ ниже уровня
                stop_loss = entry_price + stop_distance  # Stop выше ТВХ
                take_profit = entry_price - (stop_distance * self.take_profit_ratio)
            
            params = {
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "stop_distance": stop_distance,
                "gap": gap,
                "gap_percent": self.gap_percent * 100,
                "risk_reward_ratio": self.take_profit_ratio,
                "level_price": level_price,
                "atr_used": atr
            }
            
            logger.debug(f"📊 Параметры Limit ордера: Entry={entry_price:.2f}, "
                        f"SL={stop_loss:.2f}, TP={take_profit:.2f}, "
                        f"Gap={gap:.2f} ({self.gap_percent*100}%)")
            
            return params
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета параметров: {e}")
            return {}
    
    def _check_order_validity(
        self,
        order_params: Dict[str, float],
        current_price: float
    ) -> bool:
        """
        Проверка валидности ордера
        
        Отменяем если цена на расстоянии > 2 стопов от лимитной заявки
        
        Args:
            order_params: Параметры ордера
            current_price: Текущая цена
            
        Returns:
            True если ордер валиден
        """
        try:
            entry_price = order_params.get("entry_price")
            stop_distance = order_params.get("stop_distance")
            
            if not entry_price or not stop_distance:
                return False
            
            # Расстояние до entry
            distance = abs(current_price - entry_price)
            
            # Максимум: 2 стопа
            max_distance = stop_distance * self.order_cancel_distance
            
            if distance > max_distance:
                logger.debug(f"⚠️ Цена слишком далеко: {distance:.2f} > {max_distance:.2f} (2 stops)")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки ордера: {e}")
            return False
    
    # ==================== СОЗДАНИЕ СИГНАЛА ====================
    
    def _create_bounce_signal(
        self,
        level: SupportResistanceLevel,
        direction: str,
        bsu: BSUPattern,
        bpu1: Optional[BPUPattern],
        bpu2: Optional[BPUPattern],
        order_params: Dict[str, float],
        bounce_details: Dict[str, Any],
        current_price: float
    ) -> TradingSignal:
        """
        Создание торгового сигнала отбоя
        
        Args:
            level: Уровень отбоя
            direction: Направление
            bsu: Паттерн БСУ
            bpu1: Паттерн БПУ-1
            bpu2: Паттерн БПУ-2
            order_params: Параметры ордера
            bounce_details: Детали предпосылок
            current_price: Текущая цена
            
        Returns:
            TradingSignal
        """
        try:
            # Тип сигнала
            signal_type = SignalType.BUY if direction == "up" else SignalType.SELL
            
            # Если все условия идеальны - STRONG
            preconditions_score = bounce_details.get("preconditions_score", 0)
            
            if preconditions_score >= 4:
                signal_type = SignalType.STRONG_BUY if direction == "up" else SignalType.STRONG_SELL
            
            # Расчет силы
            strength = self._calculate_signal_strength(
                preconditions_score=preconditions_score,
                level=level,
                bsu=bsu
            )
            
            # Расчет уверенности
            confidence = self._calculate_signal_confidence(
                preconditions_score=preconditions_score,
                level=level,
                has_bpu2=bpu2 is not None
            )
            
            # Причины
            reasons = self._build_signal_reasons(
                level=level,
                direction=direction,
                bsu=bsu,
                bpu1=bpu1,
                bpu2=bpu2,
                bounce_details=bounce_details
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
                0.025 * confidence,  # До 2.5% при макс уверенности
                0.04  # Но не более 4%
            )
            
            # Технические индикаторы
            signal.add_technical_indicator(
                "bounce_level",
                level.price,
                f"{level.level_type} @ {level.price:.2f}"
            )
            
            signal.add_technical_indicator(
                "entry_price",
                order_params.get("entry_price"),
                f"Limit Entry: {order_params.get('entry_price'):.2f}"
            )
            
            signal.add_technical_indicator(
                "bsu_age_days",
                bsu.age_days,
                f"БСУ возраст: {bsu.age_days} дней"
            )
            
            if bpu2:
                signal.add_technical_indicator(
                    "bpu_pattern",
                    "БПУ-2 (пучок с БПУ-1)",
                    "БСУ-БПУ модель подтверждена"
                )
            
            signal.add_technical_indicator(
                "gap",
                order_params.get("gap"),
                f"Люфт: {order_params.get('gap_percent'):.0f}%"
            )
            
            # Метаданные
            signal.technical_indicators["bounce_details"] = bounce_details
            signal.technical_indicators["order_params"] = order_params
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания сигнала: {e}")
            return self.create_signal(
                signal_type=SignalType.BUY if direction == "up" else SignalType.SELL,
                strength=0.5,
                confidence=0.5,
                current_price=current_price,
                reasons=["Отбой от уровня"]
            )
    
    def _calculate_signal_strength(
        self,
        preconditions_score: int,
        level: SupportResistanceLevel,
        bsu: BSUPattern
    ) -> float:
        """Расчет силы сигнала"""
        strength = 0.5  # Базовая
        
        # Бонус за предпосылки (каждая дает +0.08)
        strength += preconditions_score * 0.08
        
        # Бонус за сильный уровень
        if level.is_strong:
            strength += 0.1
        
        # Бонус за свежий БСУ
        if bsu.age_days < 90:
            strength += 0.05
        
        return min(1.0, strength)
    
    def _calculate_signal_confidence(
        self,
        preconditions_score: int,
        level: SupportResistanceLevel,
        has_bpu2: bool
    ) -> float:
        """Расчет уверенности"""
        confidence = 0.6  # Базовая
        
        # Бонус за предпосылки
        confidence += preconditions_score * 0.06
        
        # Бонус за БПУ-2
        if has_bpu2:
            confidence += 0.15
        
        # Бонус за сильный уровень
        if level.strength >= 0.8:
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def _build_signal_reasons(
        self,
        level: SupportResistanceLevel,
        direction: str,
        bsu: BSUPattern,
        bpu1: Optional[BPUPattern],
        bpu2: Optional[BPUPattern],
        bounce_details: Dict[str, Any]
    ) -> List[str]:
        """Построение списка причин"""
        reasons = []
        
        direction_text = "вверх" if direction == "up" else "вниз"
        reasons.append(f"Отбой {direction_text} от {level.level_type} @ {level.price:.2f}")
        
        reasons.append(f"БСУ найден (возраст {bsu.age_days} дней)")
        
        if bpu1:
            reasons.append("БПУ-1: касание точка в точку")
        
        if bpu2:
            reasons.append("БПУ-2: пучок с БПУ-1 (модель подтверждена)")
        
        # Предпосылки
        if bounce_details.get("atr_exhausted"):
            reasons.append(f"ATR исчерпан: {bounce_details.get('atr_used_percent', 0):.1f}%")
        
        if bounce_details.get("far_retest"):
            days = bounce_details.get("days_since_touch", 0)
            reasons.append(f"Дальний ретест: {days} дней")
        
        if bounce_details.get("big_bars_approach"):
            reasons.append("Подход большими барами")
        
        if bounce_details.get("strong_move"):
            move = bounce_details.get("move_percent", 0)
            reasons.append(f"Сильное движение: {move:.1f}%")
        
        if level.is_strong:
            reasons.append(f"Сильный уровень: strength={level.strength:.2f}, touches={level.touches}")
        
        return reasons
    
    # ==================== СТАТИСТИКА ====================
    
    def get_strategy_stats(self) -> Dict[str, Any]:
        """Получить статистику стратегии"""
        base_stats = self.get_stats()
        
        return {
            **base_stats,
            "strategy_type": "BounceStrategy",
            "strategy_stats": self.strategy_stats.copy(),
            "config": {
                "require_bpu1": self.require_bpu1,
                "require_bpu2": self.require_bpu2,
                "seconds_before_close": self.seconds_before_close,
                "prefer_far_retest": self.prefer_far_retest,
                "prefer_atr_exhausted": self.prefer_atr_exhausted,
                "take_profit_ratio": self.take_profit_ratio,
                "gap_percent": self.gap_percent * 100
            }
        }
    
    def __str__(self):
        stats = self.get_strategy_stats()
        return (f"BounceStrategy(symbol={self.symbol}, "
                f"bsu_found={stats['strategy_stats']['bsu_found']}, "
                f"bpu2_clusters={stats['strategy_stats']['bpu2_clusters_found']}, "
                f"signals={stats['signals_sent']}, "
                f"success_rate={stats['analysis_success_rate']:.1f}%)")


# Export
__all__ = ["BounceStrategy"]

logger.info("✅ Bounce Strategy module loaded")
