"""
Breakout Strategy v3.0 - Стратегия торговли пробоя с analyze_with_data()

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
Version: 3.0.1 - FIXED: KeyError 'close' -> 'close_price'
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from .base_strategy import BaseStrategy, TradingSignal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class BreakoutStrategy(BaseStrategy):
    """
    💥 Стратегия торговли пробоя уровней v3.0
    
    Ставка на импульсное движение после преодоления ключевого уровня.
    Требует накопления энергии (консолидации) перед пробоем.
    
    Изменения v3.0.1:
    - ✅ ИСПРАВЛЕНО: KeyError 'close' -> используем 'close_price'
    - ✅ ИСПРАВЛЕНО: KeyError 'high' -> используем 'high_price'
    - ✅ ИСПРАВЛЕНО: KeyError 'low' -> используем 'low_price'
    - ✅ ИСПРАВЛЕНО: KeyError 'open' -> используем 'open_price'
    
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
        min_level_strength: float = 0.5,
        max_distance_to_level_percent: float = 2.0,
        
        # Параметры поджатия
        require_compression: bool = False,
        compression_min_bars: int = 3,
        
        # Параметры ретеста
        near_retest_max_days: int = 7,
        ideal_retest_touches: int = 3,
        
        # Параметры закрытия
        close_near_level_tolerance: float = 0.5,
        close_near_extreme_max_pullback: float = 10.0,
        
        # Параметры энергии
        require_consolidation: bool = True,
        min_energy_level: str = "moderate",
        
        # Параметры ATR
        atr_exhaustion_threshold: float = 0.75,
        
        # Параметры ордеров
        entry_offset_points: float = 2.0,
        stop_loss_multiplier: float = 1.0,
        take_profit_ratio: float = 3.0,
        order_cancel_atr_distance: float = 1.0,
        
        # Настройки стратегии
        min_signal_strength: float = 0.6,
        signal_cooldown_minutes: int = 30,
        max_signals_per_hour: int = 2,
    ):
        """
        Инициализация стратегии пробоя
        
        Args:
            symbol: Торговый символ
            repository: MarketDataRepository
            ta_context_manager: Менеджер технического анализа
            [остальные параметры см. выше]
        """
        super().__init__(
            name="BreakoutStrategy",
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
        
        logger.info("💥 BreakoutStrategy v3.0.1 инициализирована (FIXED)")
        logger.info(f"   • Symbol: {symbol}")
        logger.info(f"   • Require compression: {require_compression}")
        logger.info(f"   • Require consolidation: {require_consolidation}")
        logger.info(f"   • Min energy: {min_energy_level}")
        logger.info(f"   • ATR exhaustion: {atr_exhaustion_threshold*100}%")
    
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
        2. Анализ рыночных условий
        3. Поиск подходящих уровней
        4. Проверка всех условий входа
        5. Расчет параметров ордера
        6. Генерация сигнала
        
        Args:
            symbol: Торговый символ
            candles_1m: Минутные свечи (последние 100)
            candles_5m: 5-минутные свечи (последние 50)
            candles_1h: Часовые свечи (последние 24)
            candles_1d: Дневные свечи (последние 180)
            ta_context: Технический контекст (уровни, ATR)
            
        Returns:
            TradingSignal или None
        """
        try:
            # Обновляем symbol (если был PLACEHOLDER)
            self.symbol = symbol
            
            # Проверка минимальных данных
            if not candles_5m or len(candles_5m) < 20:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: недостаточно M5 свечей")
                return None
            
            if not candles_1d or len(candles_1d) < 30:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: недостаточно D1 свечей")
                return None
            
            # ✅ ИСПРАВЛЕНО: используем 'close_price' вместо 'close'
            current_price = float(candles_5m[-1]['close_price'])
            
            # Шаг 1: Проверка технического контекста
            if ta_context is None:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: технический контекст недоступен")
                return None
            
            # Проверяем что контекст инициализирован
            if not hasattr(ta_context, 'levels_d1') or not ta_context.levels_d1:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: нет уровней D1 в контексте")
                return None
            
            # Шаг 2: Проверка ATR (не должен быть исчерпан)
            if hasattr(ta_context, 'atr_data') and ta_context.atr_data:
                atr_used = ta_context.atr_data.current_range_used if hasattr(ta_context.atr_data, 'current_range_used') else 0
                if atr_used > self.atr_exhaustion_threshold:
                    self.strategy_stats["setups_filtered_by_atr"] += 1
                    if self.debug_mode:
                        logger.debug(f"⚠️ {symbol}: ATR исчерпан: {atr_used*100:.1f}%")
                    return None
            
            # Шаг 3: Поиск ближайшего уровня
            nearest_level, direction = self._find_nearest_level_for_breakout(
                ta_context=ta_context,
                current_price=current_price
            )
            
            if not nearest_level:
                return None
            
            self.strategy_stats["levels_analyzed"] += 1
            
            # Шаг 4: Проверка всех условий входа
            setup_valid, setup_details = self._validate_breakout_setup(
                level=nearest_level,
                direction=direction,
                ta_context=ta_context,
                candles_5m=candles_5m,
                candles_1h=candles_1h,
                candles_1d=candles_1d,
                current_price=current_price
            )
            
            if not setup_valid:
                return None
            
            self.strategy_stats["setups_found"] += 1
            
            # Шаг 5: Расчет параметров ордера
            order_params = self._calculate_order_parameters(
                level=nearest_level,
                direction=direction,
                ta_context=ta_context,
                current_price=current_price
            )
            
            # Шаг 6: Проверка что цена не ушла слишком далеко
            if not self._check_order_validity(order_params, current_price, ta_context):
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: цена слишком далеко от точки входа")
                return None
            
            # Шаг 7: Генерация сигнала
            signal = self._create_breakout_signal(
                level=nearest_level,
                direction=direction,
                order_params=order_params,
                setup_details=setup_details,
                current_price=current_price
            )
            
            self.strategy_stats["signals_generated"] += 1
            
            logger.info(f"✅ {symbol}: Сигнал пробоя создан: {direction} через {nearest_level.price:.2f}")
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ {symbol}: Ошибка в analyze_with_data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    # ==================== ПОИСК УРОВНЕЙ ====================
    
    def _find_nearest_level_for_breakout(
        self,
        ta_context: Any,
        current_price: float
    ) -> Tuple[Optional[Any], str]:
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
            candidates = []
            
            if resistances:
                nearest_resistance = min(resistances, key=lambda l: abs(l.price - current_price))
                distance = abs(nearest_resistance.price - current_price) / current_price
                if distance <= self.max_distance_to_level:
                    candidates.append((nearest_resistance, "up", distance))
            
            if supports:
                nearest_support = min(supports, key=lambda l: abs(l.price - current_price))
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
    
    def _validate_breakout_setup(
        self,
        level: Any,
        direction: str,
        ta_context: Any,
        candles_5m: List[Dict],
        candles_1h: List[Dict],
        candles_1d: List[Dict],
        current_price: float
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Валидация всех условий для пробоя
        
        Проверяет 6 основных условий из документа:
        1. ✅ Поджатие (маленькие бары)
        2. ✅ Ближний ретест
        3. ✅ Закрытие у уровня
        4. ✅ Консолидация (энергия)
        5. ✅ Закрытие под Hi/Low без отката
        6. ✅ ATR не исчерпан (проверено выше)
        
        Args:
            level: Уровень для пробоя
            direction: Направление пробоя
            ta_context: Технический контекст
            candles_5m: 5-минутные свечи
            candles_1h: Часовые свечи
            candles_1d: Дневные свечи
            current_price: Текущая цена
            
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
            
            score = 0
            max_score = 5  # 5 основных условий (ATR проверен выше)
            
            # УСЛОВИЕ 1: Поджатие (проверка по M5)
            has_compression = False
            if self.require_compression and len(candles_5m) >= 20:
                recent_m5 = candles_5m[-20:]
                
                # ✅ ИСПРАВЛЕНО: используем 'high_price' и 'low_price'
                avg_size = sum(abs(float(c['high_price']) - float(c['low_price'])) for c in recent_m5) / len(recent_m5)
                
                # Последние 3 свечи должны быть меньше среднего
                last_3_sizes = [abs(float(c['high_price']) - float(c['low_price'])) for c in recent_m5[-3:]]
                avg_last_3 = sum(last_3_sizes) / len(last_3_sizes)
                
                has_compression = avg_last_3 < avg_size * 0.8  # На 20% меньше среднего
                
                if has_compression:
                    score += 1
                    self.strategy_stats["compressions_found"] += 1
                    logger.debug("✅ Поджатие обнаружено")
                elif self.require_compression:
                    self.strategy_stats["setups_filtered_by_compression"] += 1
                    logger.debug("❌ Нет поджатия")
                    return False, details
            
            details["has_compression"] = has_compression
            
            # УСЛОВИЕ 2: Ближний ретест
            is_near_retest = False
            if hasattr(level, 'last_touch') and level.last_touch:
                days_since_touch = (datetime.now() - level.last_touch).days
                is_near_retest = days_since_touch <= self.near_retest_max_days
                
                if is_near_retest:
                    score += 1
                    logger.debug(f"✅ Ближний ретест: {days_since_touch} дней")
                
                details["days_since_touch"] = days_since_touch
            
            details["is_near_retest"] = is_near_retest
            
            # УСЛОВИЕ 3: Закрытие вблизи уровня
            close_near_level = False
            if candles_5m:
                # ✅ ИСПРАВЛЕНО: используем 'close_price'
                last_close = float(candles_5m[-1]['close_price'])
                distance = abs(last_close - level.price) / level.price * 100
                
                close_near_level = distance <= self.close_near_level_tolerance
                
                if close_near_level:
                    score += 1
                    logger.debug("✅ Закрытие у уровня")
                
                details["close_distance_percent"] = distance
            
            details["close_near_level"] = close_near_level
            
            # УСЛОВИЕ 4: Консолидация (по H1)
            has_consolidation = False
            if self.require_consolidation and len(candles_1h) >= 10:
                # Простая проверка: последние 10 часов цена в узком диапазоне
                recent_h1 = candles_1h[-10:]
                
                # ✅ ИСПРАВЛЕНО: используем 'high_price' и 'low_price'
                highs = [float(c['high_price']) for c in recent_h1]
                lows = [float(c['low_price']) for c in recent_h1]
                
                price_range = max(highs) - min(lows)
                avg_price = (max(highs) + min(lows)) / 2
                
                # Диапазон меньше 2% от средней цены = консолидация
                range_percent = price_range / avg_price * 100
                has_consolidation = range_percent < 2.0
                
                if has_consolidation:
                    score += 1
                    self.strategy_stats["consolidations_found"] += 1
                    logger.debug(f"✅ Консолидация: диапазон {range_percent:.2f}%")
                elif self.require_consolidation:
                    self.strategy_stats["setups_filtered_by_energy"] += 1
                    logger.debug(f"❌ Нет консолидации: диапазон {range_percent:.2f}%")
                    return False, details
                
                details["consolidation_range_percent"] = range_percent
            
            details["has_consolidation"] = has_consolidation
            
            # УСЛОВИЕ 5: Закрытие под Hi/Low без отката
            close_near_extreme = False
            if candles_5m:
                last_candle = candles_5m[-1]
                
                # ✅ ИСПРАВЛЕНО: используем 'high_price', 'low_price', 'close_price'
                high = float(last_candle['high_price'])
                low = float(last_candle['low_price'])
                close = float(last_candle['close_price'])
                
                candle_size = high - low
                
                if direction == "up":
                    # Для пробоя вверх: закрытие должно быть у High
                    distance_from_high = high - close
                    pullback_percent = (distance_from_high / candle_size * 100) if candle_size > 0 else 100
                    close_near_extreme = pullback_percent <= self.close_near_extreme_max_pullback
                else:
                    # Для пробоя вниз: закрытие должно быть у Low
                    distance_from_low = close - low
                    pullback_percent = (distance_from_low / candle_size * 100) if candle_size > 0 else 100
                    close_near_extreme = pullback_percent <= self.close_near_extreme_max_pullback
                
                if close_near_extreme:
                    score += 1
                    logger.debug(f"✅ Закрытие у экстремума (откат {pullback_percent:.1f}%)")
                
                details["pullback_percent"] = pullback_percent
            
            details["close_near_extreme"] = close_near_extreme
            
            # Итоговая оценка
            details["setup_score"] = score
            details["setup_score_max"] = max_score
            details["setup_quality"] = score / max_score
            
            # Минимальный score для входа
            min_score = 3  # Минимум 3 из 5 условий
            
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
        level: Any,
        direction: str,
        ta_context: Any,
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
            atr = current_price * 0.02  # 2% по умолчанию
            if hasattr(ta_context, 'atr_data') and ta_context.atr_data:
                if hasattr(ta_context.atr_data, 'calculated_atr'):
                    atr = ta_context.atr_data.calculated_atr
            
            # Люфт (фиксированный offset)
            entry_offset = self.entry_offset
            
            if direction == "up":
                # Пробой вверх (через сопротивление)
                entry_price = level_price + entry_offset  # Buy Stop
                
                # Stop Loss за уровнем (10% от ATR)
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
        ta_context: Any
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
            atr = current_price * 0.02
            if hasattr(ta_context, 'atr_data') and ta_context.atr_data:
                if hasattr(ta_context.atr_data, 'calculated_atr'):
                    atr = ta_context.atr_data.calculated_atr
            
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
        level: Any,
        direction: str,
        order_params: Dict[str, float],
        setup_details: Dict[str, Any],
        current_price: float
    ) -> TradingSignal:
        """
        Создание торгового сигнала пробоя
        
        Args:
            level: Уровень пробоя
            direction: Направление
            order_params: Параметры ордера
            setup_details: Детали setup
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
                level=level
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
        level: Any
    ) -> float:
        """Расчет силы сигнала"""
        strength = 0.5  # Базовая
        
        # Бонус за качество setup
        setup_quality = setup_details.get("setup_quality", 0)
        strength += setup_quality * 0.3
        
        # Бонус за сильный уровень
        if hasattr(level, 'is_strong') and level.is_strong:
            strength += 0.1
        
        return min(1.0, strength)
    
    def _calculate_signal_confidence(
        self,
        setup_details: Dict[str, Any],
        level: Any
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
        if hasattr(level, 'strength') and level.strength >= 0.8:
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def _build_signal_reasons(
        self,
        setup_details: Dict[str, Any],
        level: Any,
        direction: str
    ) -> List[str]:
        """Построение списка причин сигнала"""
        reasons = []
        
        direction_text = "вверх" if direction == "up" else "вниз"
        reasons.append(f"Пробой {direction_text} через {level.level_type} @ {level.price:.2f}")
        
        if setup_details.get("has_compression"):
            reasons.append("Поджатие у уровня обнаружено")
        
        if setup_details.get("has_consolidation"):
            range_pct = setup_details.get("consolidation_range_percent", 0)
            reasons.append(f"Консолидация (диапазон {range_pct:.1f}%)")
        
        if setup_details.get("is_near_retest"):
            days = setup_details.get("days_since_touch", 0)
            reasons.append(f"Ближний ретест ({days} дней)")
        
        if setup_details.get("close_near_level"):
            reasons.append("Закрытие вблизи уровня")
        
        if setup_details.get("close_near_extreme"):
            reasons.append(f"Закрытие у экстремума")
        
        if hasattr(level, 'is_strong') and level.is_strong:
            reasons.append(f"Сильный уровень (strength={level.strength:.2f})")
        
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

logger.info("✅ Breakout Strategy v3.0.1 loaded (FIXED: KeyError resolved)")
