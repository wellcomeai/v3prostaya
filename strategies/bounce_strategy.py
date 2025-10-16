"""
Bounce Strategy v3.0 - Стратегия торговли отбоя (БСУ-БПУ модель) с analyze_with_data()

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
Version: 3.0.0 - Orchestrator Integration
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from .base_strategy import BaseStrategy, TradingSignal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class BounceStrategy(BaseStrategy):
    """
    🎯 Стратегия торговли отбоя от уровня (БСУ-БПУ модель) v3.0
    
    Ловит отскок цены от сильного уровня поддержки/сопротивления.
    Использует модель БСУ-БПУ для подтверждения валидности уровня.
    
    Изменения v3.0:
    - ✅ Реализован analyze_with_data() - получает готовые данные
    - ✅ Убрана зависимость от MarketDataSnapshot
    - ✅ Работа напрямую со свечами из параметров
    - ✅ Упрощенная логика без PatternDetector (прямые проверки)
    
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
            repository=repository,
            ta_context_manager=ta_manager
        )
        
        signal = await strategy.analyze_with_data(
            symbol="BTCUSDT",
            candles_1m=candles_1m,
            candles_5m=candles_5m,
            candles_1h=candles_1h,
            candles_1d=candles_1d,
            ta_context=context
        )
    """
    
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        repository=None,
        ta_context_manager=None,
        
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
            repository: MarketDataRepository
            ta_context_manager: Менеджер технического анализа
            [остальные параметры см. выше]
        """
        super().__init__(
            name="BounceStrategy",
            symbol=symbol,
            repository=repository,
            ta_context_manager=ta_context_manager,
            min_signal_strength=min_signal_strength,
            signal_cooldown_minutes=signal_cooldown_minutes,
            max_signals_per_hour=max_signals_per_hour,
            enable_risk_management=True
        )
        
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
        
        # Статистика стратегии
        self.strategy_stats = {
            "levels_analyzed": 0,
            "bsu_found": 0,
            "bpu_patterns_found": 0,
            "setups_found": 0,
            "signals_generated": 0,
            "timing_missed": 0,
            "far_retests": 0,
            "atr_exhausted_entries": 0
        }
        
        logger.info("🎯 BounceStrategy v3.0 инициализирована")
        logger.info(f"   • Symbol: {symbol}")
        logger.info(f"   • Require BPU-1: {require_bpu1}, BPU-2: {require_bpu2}")
        logger.info(f"   • Entry timing: {seconds_before_close}s before close")
        logger.info(f"   • Prefer far retest: {prefer_far_retest}")
        logger.info(f"   • Prefer ATR exhausted: {prefer_atr_exhausted}")
    
    # ==================== НОВЫЙ API v3.0 ====================
    
    async def analyze_with_data(
        self,
        symbol: str,
        candles_1m: List[Dict],
        candles_5m: List[Dict],
        candles_1h: List[Dict],
        candles_1d: List[Dict],
        ta_context: Optional[Any] = None
    ) -> Optional[TradingSignal]:
        """
        🎯 Анализ с готовыми данными (v3.0)
        
        Алгоритм:
        1. Проверка технического контекста
        2. Поиск подходящих уровней (сильные, близкие)
        3. Проверка БСУ для уровня
        4. Поиск БПУ паттернов
        5. Проверка предпосылок для отбоя
        6. Расчет параметров ордера
        7. Генерация сигнала
        
        Args:
            symbol: Торговый символ
            candles_1m: Минутные свечи (последние 100)
            candles_5m: 5-минутные свечи (последние 50)
            candles_1h: Часовые свечи (последние 24)
            candles_1d: Дневные свечи (последние 180)
            ta_context: Технический контекст
            
        Returns:
            TradingSignal или None
        """
        try:
            # Обновляем symbol (если был PLACEHOLDER)
            self.symbol = symbol
            
            # Проверка минимальных данных
            if not candles_1h or len(candles_1h) < 10:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: недостаточно H1 свечей")
                return None
            
            if not candles_1d or len(candles_1d) < 30:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: недостаточно D1 свечей")
                return None
            
            # Текущая цена из последней H1 свечи
            current_price = float(candles_1h[-1]['close'])
            current_time = datetime.now()
            
            # Шаг 1: Проверка технического контекста
            if ta_context is None:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: технический контекст недоступен")
                return None
            
            # Проверяем что есть уровни
            if not hasattr(ta_context, 'levels_d1') or not ta_context.levels_d1:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: нет уровней D1")
                return None
            
            # Шаг 2: Поиск ближайшего сильного уровня
            nearest_level, direction = self._find_nearest_level_for_bounce(
                ta_context=ta_context,
                current_price=current_price
            )
            
            if not nearest_level:
                return None
            
            self.strategy_stats["levels_analyzed"] += 1
            
            # Шаг 3: Проверка БСУ для уровня (упрощенная версия)
            has_bsu = self._check_bsu_simple(
                level=nearest_level,
                candles_1d=candles_1d
            )
            
            if not has_bsu:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: БСУ не найден для уровня {nearest_level.price:.2f}")
                return None
            
            self.strategy_stats["bsu_found"] += 1
            
            # Шаг 4: Проверка БПУ паттернов (упрощенная версия)
            has_bpu_pattern = self._check_bpu_pattern_simple(
                level=nearest_level,
                candles_1h=candles_1h,
                current_price=current_price
            )
            
            if not has_bpu_pattern:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: БПУ паттерн не найден")
                return None
            
            self.strategy_stats["bpu_patterns_found"] += 1
            
            # Шаг 5: Проверка предпосылок для отбоя
            bounce_score, bounce_details = self._check_bounce_preconditions(
                level=nearest_level,
                ta_context=ta_context,
                candles_1h=candles_1h,
                candles_1d=candles_1d,
                current_price=current_price
            )
            
            if bounce_score < 2:  # Минимум 2 предпосылки
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: недостаточно предпосылок: {bounce_score}/5")
                return None
            
            self.strategy_stats["setups_found"] += 1
            logger.info(f"✅ {symbol}: Предпосылки для отбоя: {bounce_score}/5")
            
            # Шаг 6: Расчет параметров ордера
            order_params = self._calculate_order_parameters(
                level=nearest_level,
                direction=direction,
                ta_context=ta_context,
                current_price=current_price
            )
            
            # Шаг 7: Проверка валидности ордера
            if not self._check_order_validity(order_params, current_price):
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: ордер невалиден (цена слишком далеко)")
                return None
            
            # Шаг 8: Генерация сигнала
            signal = self._create_bounce_signal(
                level=nearest_level,
                direction=direction,
                order_params=order_params,
                bounce_details=bounce_details,
                current_price=current_price
            )
            
            self.strategy_stats["signals_generated"] += 1
            
            logger.info(f"✅ {symbol}: Сигнал отбоя создан: {direction} от {nearest_level.price:.2f}")
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ {symbol}: Ошибка в analyze_with_data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    # ==================== ПОИСК УРОВНЕЙ ====================
    
    def _find_nearest_level_for_bounce(
        self,
        ta_context: Any,
        current_price: float
    ) -> Tuple[Optional[Any], str]:
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
    
    # ==================== ПРОВЕРКА БСУ (УПРОЩЕННАЯ) ====================
    
    def _check_bsu_simple(
        self,
        level: Any,
        candles_1d: List[Dict]
    ) -> bool:
        """
        Упрощенная проверка наличия БСУ
        
        БСУ = исторический бар который создал уровень
        Проверяем что уровень не слишком старый
        
        Args:
            level: Уровень
            candles_1d: Дневные свечи
            
        Returns:
            True если БСУ валиден
        """
        try:
            # Проверяем возраст уровня
            if hasattr(level, 'first_touch') and level.first_touch:
                age_days = (datetime.now() - level.first_touch).days
                
                if age_days <= self.bsu_max_age_days:
                    logger.debug(f"✅ БСУ валиден: возраст {age_days} дней")
                    return True
                else:
                    logger.debug(f"⚠️ БСУ слишком старый: {age_days} дней")
                    return False
            
            # Если нет информации о first_touch, считаем валидным
            # если уровень сильный (т.е. проверен временем)
            if level.strength >= self.min_level_strength:
                logger.debug("✅ БСУ предполагается валидным (сильный уровень)")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки БСУ: {e}")
            return False
    
    # ==================== ПРОВЕРКА БПУ (УПРОЩЕННАЯ) ====================
    
    def _check_bpu_pattern_simple(
        self,
        level: Any,
        candles_1h: List[Dict],
        current_price: float
    ) -> bool:
        """
        Упрощенная проверка БПУ паттерна
        
        Проверяем что:
        1. Цена недавно касалась уровня (БПУ-1)
        2. Цена сейчас снова около уровня (БПУ-2)
        3. Касания были "точка в точку"
        
        Args:
            level: Уровень
            candles_1h: Часовые свечи
            current_price: Текущая цена
            
        Returns:
            True если паттерн найден
        """
        try:
            level_price = level.price
            
            # Ищем касания уровня в последних 50 часах
            touches = []
            
            for i, candle in enumerate(candles_1h[-50:]):
                high = float(candle['high'])
                low = float(candle['low'])
                close = float(candle['close'])
                
                # Проверяем касание уровня (допуск self.bpu_touch_tolerance)
                distance_high = abs(high - level_price) / level_price
                distance_low = abs(low - level_price) / level_price
                distance_close = abs(close - level_price) / level_price
                
                if min(distance_high, distance_low, distance_close) <= self.bpu_touch_tolerance:
                    touches.append({
                        'index': i,
                        'time': candle.get('close_time', datetime.now()),
                        'close': close
                    })
            
            # Нужно минимум 2 касания для БПУ-1 и БПУ-2
            if len(touches) < 2:
                logger.debug(f"⚠️ Недостаточно касаний: {len(touches)}")
                return False
            
            # Проверяем что последнее касание недавнее (БПУ-2)
            last_touch = touches[-1]
            if last_touch['index'] < len(candles_1h[-50:]) - 3:  # Не в последних 3 свечах
                logger.debug("⚠️ Последнее касание не недавнее")
                return False
            
            # Проверяем кластер (БПУ-2 рядом с БПУ-1)
            if len(touches) >= 2:
                prev_touch = touches[-2]
                
                # Расстояние между касаниями в барах
                bars_between = last_touch['index'] - prev_touch['index']
                
                # Должно быть не слишком далеко (в пределах 20 баров)
                if bars_between <= 20:
                    logger.debug(f"✅ БПУ паттерн найден: {len(touches)} касаний, "
                               f"последние 2 через {bars_between} баров")
                    return True
            
            logger.debug("⚠️ БПУ паттерн не подтвержден")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки БПУ: {e}")
            return False
    
    # ==================== ПРЕДПОСЫЛКИ ДЛЯ ОТБОЯ ====================
    
    def _check_bounce_preconditions(
        self,
        level: Any,
        ta_context: Any,
        candles_1h: List[Dict],
        candles_1d: List[Dict],
        current_price: float
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Проверка предпосылок для отбоя
        
        Из документа:
        1. ✅ ATR исчерпан (75-80%)
        2. ✅ Дальний ретест (>1 месяца)
        3. ✅ Подход большими барами
        4. ✅ Закрытие далеко от уровня
        5. ✅ Было сильное движение (>10%)
        
        Args:
            level: Уровень
            ta_context: Технический контекст
            candles_1h: Часовые свечи
            candles_1d: Дневные свечи
            current_price: Текущая цена
            
        Returns:
            Tuple[score (0-5), детали]
        """
        try:
            score = 0
            details = {}
            
            # 1. ATR исчерпан (75-80%)
            atr_exhausted = False
            if hasattr(ta_context, 'atr_data') and ta_context.atr_data:
                if hasattr(ta_context.atr_data, 'current_range_used'):
                    atr_used = ta_context.atr_data.current_range_used
                    atr_exhausted = atr_used >= self.atr_exhaustion_min
                    
                    details["atr_exhausted"] = atr_exhausted
                    details["atr_used_percent"] = atr_used * 100
                    
                    if atr_exhausted:
                        score += 1
                        self.strategy_stats["atr_exhausted_entries"] += 1
                        logger.debug(f"✅ ATR исчерпан: {atr_used*100:.1f}%")
            
            # 2. Дальний ретест (>1 месяца)
            far_retest = False
            if hasattr(level, 'last_touch') and level.last_touch:
                days_since = (datetime.now() - level.last_touch).days
                far_retest = days_since >= self.far_retest_min_days
                details["days_since_touch"] = days_since
                details["far_retest"] = far_retest
                
                if far_retest:
                    score += 1
                    self.strategy_stats["far_retests"] += 1
                    logger.debug(f"✅ Дальний ретест: {days_since} дней")
            
            # 3. Подход большими барами (проверка по H1)
            big_bars_approach = False
            if len(candles_1h) >= 5:
                recent = candles_1h[-5:]
                
                # Средний размер бара
                ranges = [float(c['high']) - float(c['low']) for c in recent]
                avg_range = sum(ranges) / len(ranges)
                
                # Получаем ATR для сравнения
                atr = current_price * 0.02  # По умолчанию 2%
                if hasattr(ta_context, 'atr_data') and ta_context.atr_data:
                    if hasattr(ta_context.atr_data, 'calculated_atr'):
                        atr = ta_context.atr_data.calculated_atr
                
                # Большие бары если avg_range > 0.5×ATR
                big_bars_approach = avg_range > (atr * 0.5)
                details["big_bars_approach"] = big_bars_approach
                details["avg_bar_range"] = avg_range
                
                if big_bars_approach:
                    score += 1
                    logger.debug("✅ Подход большими барами")
            
            # 4. Закрытие далеко от уровня
            close_far_from_level = False
            if candles_1h:
                last_close = float(candles_1h[-1]['close'])
                distance = abs(last_close - level.price)
                distance_percent = distance / level.price * 100
                
                # Далеко если > 0.3%
                close_far_from_level = distance_percent > 0.3
                details["close_distance_percent"] = distance_percent
                details["close_far_from_level"] = close_far_from_level
                
                if close_far_from_level:
                    score += 1
                    logger.debug(f"✅ Закрытие далеко: {distance_percent:.2f}%")
            
            # 5. Сильное предшествующее движение (проверка по D1)
            strong_move = False
            if len(candles_1d) >= 2:
                # Изменение за последний день
                current = float(candles_1d[-1]['close'])
                previous = float(candles_1d[-2]['close'])
                change = abs((current - previous) / previous * 100)
                
                if change > 5.0:  # > 5% за день
                    strong_move = True
                    score += 1
                    details["strong_move"] = strong_move
                    details["move_percent"] = change
                    logger.debug(f"✅ Сильное движение: {change:.1f}%")
            
            details["preconditions_score"] = score
            
            logger.info(f"📊 Предпосылки для отбоя: {score}/5")
            
            return score, details
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки предпосылок: {e}")
            return 0, {}
    
    # ==================== РАСЧЕТ ПАРАМЕТРОВ ОРДЕРА ====================
    
    def _calculate_order_parameters(
        self,
        level: Any,
        direction: str,
        ta_context: Any,
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
            atr = current_price * 0.02
            if hasattr(ta_context, 'atr_data') and ta_context.atr_data:
                if hasattr(ta_context.atr_data, 'calculated_atr'):
                    atr = ta_context.atr_data.calculated_atr
            
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
        level: Any,
        direction: str,
        order_params: Dict[str, float],
        bounce_details: Dict[str, Any],
        current_price: float
    ) -> TradingSignal:
        """
        Создание торгового сигнала отбоя
        
        Args:
            level: Уровень отбоя
            direction: Направление
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
                level=level
            )
            
            # Расчет уверенности
            confidence = self._calculate_signal_confidence(
                preconditions_score=preconditions_score,
                level=level
            )
            
            # Причины
            reasons = self._build_signal_reasons(
                level=level,
                direction=direction,
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
                "gap",
                order_params.get("gap"),
                f"Люфт: {order_params.get('gap_percent'):.0f}%"
            )
            
            signal.add_technical_indicator(
                "bsu_bpu_model",
                "confirmed",
                "БСУ-БПУ модель подтверждена"
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
        level: Any
    ) -> float:
        """Расчет силы сигнала"""
        strength = 0.5  # Базовая
        
        # Бонус за предпосылки (каждая дает +0.08)
        strength += preconditions_score * 0.08
        
        # Бонус за сильный уровень
        if hasattr(level, 'is_strong') and level.is_strong:
            strength += 0.1
        
        return min(1.0, strength)
    
    def _calculate_signal_confidence(
        self,
        preconditions_score: int,
        level: Any
    ) -> float:
        """Расчет уверенности"""
        confidence = 0.6  # Базовая
        
        # Бонус за предпосылки
        confidence += preconditions_score * 0.06
        
        # Бонус за сильный уровень
        if hasattr(level, 'strength') and level.strength >= 0.8:
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def _build_signal_reasons(
        self,
        level: Any,
        direction: str,
        bounce_details: Dict[str, Any]
    ) -> List[str]:
        """Построение списка причин"""
        reasons = []
        
        direction_text = "вверх" if direction == "up" else "вниз"
        reasons.append(f"Отбой {direction_text} от {level.level_type} @ {level.price:.2f}")
        
        reasons.append("БСУ-БПУ модель подтверждена")
        
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
        
        if hasattr(level, 'is_strong') and level.is_strong:
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
                f"bpu_patterns={stats['strategy_stats']['bpu_patterns_found']}, "
                f"signals={stats['signals_sent']}, "
                f"success_rate={stats['analysis_success_rate']:.1f}%)")


# Export
__all__ = ["BounceStrategy"]

logger.info("✅ Bounce Strategy v3.0 loaded - Orchestrator Integration Ready")
