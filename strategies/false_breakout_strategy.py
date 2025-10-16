"""
False Breakout Strategy v3.0 - Стратегия торговли ложных пробоев с analyze_with_data()

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
1. ✅ Обнаружен ложный пробой
2. ✅ Цена подтвердила разворот (вернулась за уровень)
3. ✅ Не прошло много времени (< 4 часов)
4. ✅ Сильный уровень (strength >= 0.5)
5. ✅ Подходящие рыночные условия

Author: Trading Bot Team
Version: 3.0.1 - FIXED: KeyError 'close' -> 'close_price'
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from .base_strategy import BaseStrategy, TradingSignal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class FalseBreakoutStrategy(BaseStrategy):
    """
    🎣 Стратегия торговли ложных пробоев (ловушек) v3.0
    
    Ловит развороты после того как крупный игрок "поймал стопы" мелких трейдеров.
    Торгует ПРОТИВ направления ложного пробоя.
    
    Изменения v3.0.1:
    - ✅ ИСПРАВЛЕНО: KeyError 'close' -> используем 'close_price'
    - ✅ ИСПРАВЛЕНО: KeyError 'high' -> используем 'high_price'
    - ✅ ИСПРАВЛЕНО: KeyError 'low' -> используем 'low_price'
    
    Сильные стороны:
    - Высокая точность (уровень проверен ЛП)
    - Хороший R:R (2-3:1)
    - Четкая точка входа (после подтверждения)
    - Быстрые сделки (часто закрываются за 1-4 часа)
    
    Слабые стороны:
    - Требует быстрой реакции (4 часа после ЛП)
    - Нужно подтверждение разворота
    - Не работает при высокой волатильности
    - Ложные ЛП (может быть истинным пробоем)
    
    Usage:
        strategy = FalseBreakoutStrategy(
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
        min_level_touches: int = 2,
        max_distance_to_level_percent: float = 2.0,
        
        # Параметры ложного пробоя
        min_false_breakout_depth_percent: float = 0.1,  # Мин глубина ЛП (0.1%)
        max_false_breakout_depth_percent: float = 1.0,  # Макс глубина ЛП (1%)
        prefer_simple_false_breakouts: bool = True,     # Предпочитать простые ЛП
        
        # Параметры подтверждения
        confirmation_required: bool = True,             # Требовать подтверждение
        confirmation_distance_percent: float = 0.3,     # Расстояние подтверждения от уровня
        max_time_since_breakout_hours: int = 4,         # Макс время после ЛП (часы)
        
        # Параметры рыночных условий
        prefer_strong_levels: bool = True,              # Предпочитать сильные уровни
        avoid_extreme_volatility: bool = True,          # Избегать экстремальной волатильности
        
        # Параметры ордеров
        entry_type: str = "market",                     # market или limit
        limit_offset_percent: float = 0.2,              # Отступ для лимит ордера
        stop_loss_beyond_extreme: float = 1.1,          # SL за экстремум ЛП × 1.1
        take_profit_ratio: float = 2.5,                 # TP:SL = 2.5:1
        
        # Настройки стратегии
        min_signal_strength: float = 0.6,
        signal_cooldown_minutes: int = 15,
        max_signals_per_hour: int = 4,
    ):
        """
        Инициализация стратегии ложных пробоев
        
        Args:
            symbol: Торговый символ
            repository: MarketDataRepository
            ta_context_manager: Менеджер технического анализа
            [остальные параметры см. выше]
        """
        super().__init__(
            name="FalseBreakoutStrategy",
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
        
        # Параметры ЛП
        self.min_fb_depth = min_false_breakout_depth_percent / 100.0
        self.max_fb_depth = max_false_breakout_depth_percent / 100.0
        self.prefer_simple_fb = prefer_simple_false_breakouts
        
        # Параметры подтверждения
        self.confirmation_required = confirmation_required
        self.confirmation_distance = confirmation_distance_percent / 100.0
        self.max_time_since_breakout = timedelta(hours=max_time_since_breakout_hours)
        
        # Параметры рыночных условий
        self.prefer_strong_levels = prefer_strong_levels
        self.avoid_extreme_volatility = avoid_extreme_volatility
        
        # Параметры ордеров
        self.entry_type = entry_type
        self.limit_offset = limit_offset_percent / 100.0
        self.stop_beyond_extreme = stop_loss_beyond_extreme
        self.take_profit_ratio = take_profit_ratio
        
        # Статистика стратегии
        self.strategy_stats = {
            "levels_analyzed": 0,
            "false_breakouts_detected": 0,
            "false_breakouts_simple": 0,
            "false_breakouts_strong": 0,
            "confirmations_passed": 0,
            "signals_generated": 0,
            "filtered_by_time": 0,
            "filtered_by_confirmation": 0,
            "filtered_by_level_strength": 0
        }
        
        logger.info("🎣 FalseBreakoutStrategy v3.0.1 инициализирована (FIXED)")
        logger.info(f"   • Symbol: {symbol}")
        logger.info(f"   • Min level strength: {min_level_strength}")
        logger.info(f"   • FB depth: {min_false_breakout_depth_percent}-{max_false_breakout_depth_percent}%")
        logger.info(f"   • Max time after FB: {max_time_since_breakout_hours} hours")
        logger.info(f"   • Entry type: {entry_type}")
    
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
        2. Поиск ближайших уровней
        3. Анализ пробоев (ищем ложные)
        4. Проверка подтверждения разворота
        5. Проверка времени после пробоя
        6. Расчет параметров ордера
        7. Генерация сигнала ПРОТИВ пробоя
        
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
            if not candles_5m or len(candles_5m) < 10:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: недостаточно M5 свечей")
                return None
            
            if not candles_1d or len(candles_1d) < 30:
                if self.debug_mode:
                    logger.debug(f"⚠️ {symbol}: недостаточно D1 свечей")
                return None
            
            # ✅ ИСПРАВЛЕНО: используем 'close_price' вместо 'close'
            current_price = float(candles_5m[-1]['close_price'])
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
            
            # Шаг 2: Поиск ближайших уровней
            nearest_levels = self._find_nearest_levels(
                ta_context=ta_context,
                current_price=current_price
            )
            
            if not nearest_levels:
                return None
            
            # Шаг 3: Анализ каждого уровня на наличие ЛП
            for level in nearest_levels:
                self.strategy_stats["levels_analyzed"] += 1
                
                # Анализируем пробой
                is_false_breakout, fb_details = self._detect_false_breakout_simple(
                    level=level,
                    candles_5m=candles_5m,
                    current_price=current_price,
                    current_time=current_time
                )
                
                # Шаг 4: Проверка что это ложный пробой
                if not is_false_breakout:
                    continue
                
                self.strategy_stats["false_breakouts_detected"] += 1
                
                # Определяем тип ЛП
                fb_type = fb_details.get("type", "simple")
                if fb_type == "simple":
                    self.strategy_stats["false_breakouts_simple"] += 1
                else:
                    self.strategy_stats["false_breakouts_strong"] += 1
                
                direction = fb_details.get("direction", "unknown")
                
                logger.info(f"💥 {symbol}: Ложный пробой обнаружен: {fb_type} "
                           f"@ {level.price:.2f}, direction={direction}")
                
                # Фильтр: Предпочитаем простые ЛП
                if self.prefer_simple_fb and fb_type != "simple":
                    if self.debug_mode:
                        logger.debug(f"⚠️ {symbol}: пропускаем {fb_type} ЛП")
                    continue
                
                # Шаг 5: Проверка подтверждения разворота
                if self.confirmation_required:
                    confirmed, confirmation_details = self._check_reversal_confirmation(
                        level=level,
                        fb_details=fb_details,
                        current_price=current_price
                    )
                    
                    if not confirmed:
                        self.strategy_stats["filtered_by_confirmation"] += 1
                        if self.debug_mode:
                            logger.debug(f"⚠️ {symbol}: нет подтверждения разворота")
                        continue
                    
                    self.strategy_stats["confirmations_passed"] += 1
                
                # Шаг 6: Проверка времени после пробоя
                if not self._check_timing(fb_details, current_time):
                    self.strategy_stats["filtered_by_time"] += 1
                    if self.debug_mode:
                        logger.debug(f"⚠️ {symbol}: слишком много времени прошло после ЛП")
                    continue
                
                # Шаг 7: Проверка силы уровня
                if self.prefer_strong_levels:
                    if level.strength < self.min_level_strength:
                        self.strategy_stats["filtered_by_level_strength"] += 1
                        if self.debug_mode:
                            logger.debug(f"⚠️ {symbol}: слабый уровень: {level.strength:.2f}")
                        continue
                
                # Шаг 8: Расчет параметров ордера
                order_params = self._calculate_order_parameters(
                    level=level,
                    fb_details=fb_details,
                    ta_context=ta_context,
                    current_price=current_price
                )
                
                # Шаг 9: Генерация сигнала
                signal = self._create_false_breakout_signal(
                    level=level,
                    fb_details=fb_details,
                    order_params=order_params,
                    current_price=current_price
                )
                
                self.strategy_stats["signals_generated"] += 1
                
                logger.info(f"✅ {symbol}: Сигнал ЛП создан: {signal.signal_type.value} @ {current_price:.2f}")
                
                return signal
            
            # Если не нашли подходящих ЛП
            return None
            
        except Exception as e:
            logger.error(f"❌ {symbol}: Ошибка в analyze_with_data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    # ==================== ПОИСК УРОВНЕЙ ====================
    
    def _find_nearest_levels(
        self,
        ta_context: Any,
        current_price: float
    ) -> List[Any]:
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
    
    # ==================== ОБНАРУЖЕНИЕ ЛОЖНОГО ПРОБОЯ ====================
    
    def _detect_false_breakout_simple(
        self,
        level: Any,
        candles_5m: List[Dict],
        current_price: float,
        current_time: datetime
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Упрощенная проверка ложного пробоя
        
        Ложный пробой = цена пробила уровень, но вернулась обратно
        
        Типы:
        1. Простой ЛП - пробил и сразу закрылся назад (1-2 свечи)
        2. Сильный ЛП - пробил, немного постоял, затем вернулся (3-5 свечей)
        
        Args:
            level: Уровень
            candles_5m: 5-минутные свечи
            current_price: Текущая цена
            current_time: Текущее время
            
        Returns:
            Tuple[найден ли ЛП?, детали]
        """
        try:
            level_price = level.price
            level_type = level.level_type  # "support" или "resistance"
            
            details = {
                "found": False,
                "type": "simple",
                "direction": "unknown",
                "breakout_time": None,
                "breakout_high": None,
                "breakout_low": None,
                "depth": 0
            }
            
            # Ищем пробой в последних 20 свечах (около 2 часов)
            lookback = min(20, len(candles_5m))
            recent_candles = candles_5m[-lookback:]
            
            for i in range(len(recent_candles) - 1, 0, -1):  # С конца к началу
                candle = recent_candles[i]
                
                # ✅ ИСПРАВЛЕНО: используем 'high_price', 'low_price', 'close_price'
                high = float(candle['high_price'])
                low = float(candle['low_price'])
                close = float(candle['close_price'])
                
                # Проверяем пробой сопротивления (вверх)
                if level_type == "resistance":
                    # Пробой = High выше уровня
                    if high > level_price:
                        depth = (high - level_price) / level_price
                        
                        # Проверяем глубину пробоя
                        if self.min_fb_depth <= depth <= self.max_fb_depth:
                            # Проверяем что цена вернулась под уровень
                            if current_price < level_price * (1 - self.confirmation_distance):
                                details["found"] = True
                                details["direction"] = "upward"
                                details["breakout_high"] = high
                                details["breakout_low"] = low
                                details["depth"] = depth * 100
                                
                                # Время пробоя
                                if 'close_time' in candle:
                                    details["breakout_time"] = candle['close_time']
                                
                                # Определяем тип ЛП
                                bars_since = len(recent_candles) - i - 1
                                if bars_since <= 2:
                                    details["type"] = "simple"
                                else:
                                    details["type"] = "strong"
                                
                                logger.debug(f"✅ ЛП вверх найден: глубина {depth*100:.2f}%, "
                                           f"тип {details['type']}, {bars_since} баров назад")
                                return True, details
                
                # Проверяем пробой поддержки (вниз)
                elif level_type == "support":
                    # Пробой = Low ниже уровня
                    if low < level_price:
                        depth = (level_price - low) / level_price
                        
                        # Проверяем глубину пробоя
                        if self.min_fb_depth <= depth <= self.max_fb_depth:
                            # Проверяем что цена вернулась над уровень
                            if current_price > level_price * (1 + self.confirmation_distance):
                                details["found"] = True
                                details["direction"] = "downward"
                                details["breakout_high"] = high
                                details["breakout_low"] = low
                                details["depth"] = depth * 100
                                
                                # Время пробоя
                                if 'close_time' in candle:
                                    details["breakout_time"] = candle['close_time']
                                
                                # Определяем тип ЛП
                                bars_since = len(recent_candles) - i - 1
                                if bars_since <= 2:
                                    details["type"] = "simple"
                                else:
                                    details["type"] = "strong"
                                
                                logger.debug(f"✅ ЛП вниз найден: глубина {depth*100:.2f}%, "
                                           f"тип {details['type']}, {bars_since} баров назад")
                                return True, details
            
            return False, details
            
        except Exception as e:
            logger.error(f"❌ Ошибка обнаружения ЛП: {e}")
            return False, {}
    
    # ==================== ПОДТВЕРЖДЕНИЕ РАЗВОРОТА ====================
    
    def _check_reversal_confirmation(
        self,
        level: Any,
        fb_details: Dict[str, Any],
        current_price: float
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Проверка подтверждения разворота после ЛП
        
        Подтверждение = цена вернулась за уровень и закрепилась
        
        Args:
            level: Уровень
            fb_details: Детали ЛП
            current_price: Текущая цена
            
        Returns:
            Tuple[подтверждено?, детали]
        """
        try:
            details = {}
            
            level_price = level.price
            direction = fb_details.get("direction", "unknown")
            
            # Определяем куда должна вернуться цена
            if direction == "upward":
                # ЛП вверх → цена должна быть ниже уровня
                target_zone = level_price * (1 - self.confirmation_distance)
                confirmed = current_price < target_zone
                
                details["direction"] = "below"
                details["target_zone"] = target_zone
                details["current_price"] = current_price
                details["confirmed"] = confirmed
                
                if confirmed:
                    logger.info(f"✅ Подтверждение разворота: цена {current_price:.2f} < {target_zone:.2f}")
                else:
                    logger.debug(f"⚠️ Нет подтверждения: цена {current_price:.2f} >= {target_zone:.2f}")
            
            elif direction == "downward":
                # ЛП вниз → цена должна быть выше уровня
                target_zone = level_price * (1 + self.confirmation_distance)
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
            
            return confirmed, details
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки подтверждения: {e}")
            return False, {}
    
    # ==================== ПРОВЕРКА ТАЙМИНГА ====================
    
    def _check_timing(
        self,
        fb_details: Dict[str, Any],
        current_time: datetime
    ) -> bool:
        """
        Проверка времени после ложного пробоя
        
        Не торгуем старые ЛП (> 4 часов)
        
        Args:
            fb_details: Детали ЛП
            current_time: Текущее время
            
        Returns:
            True если время подходит
        """
        try:
            breakout_time = fb_details.get("breakout_time")
            
            if not breakout_time:
                # Если нет времени, считаем что недавнее
                return True
            
            # Прошедшее время
            time_since = current_time - breakout_time
            
            is_valid = time_since <= self.max_time_since_breakout
            
            if is_valid:
                hours_since = time_since.total_seconds() / 3600
                logger.debug(f"✅ Тайминг OK: {hours_since:.1f}h после ЛП")
            else:
                hours_since = time_since.total_seconds() / 3600
                logger.debug(f"⚠️ Слишком поздно: {hours_since:.1f}h после ЛП")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки тайминга: {e}")
            return False
    
    # ==================== РАСЧЕТ ПАРАМЕТРОВ ОРДЕРА ====================
    
    def _calculate_order_parameters(
        self,
        level: Any,
        fb_details: Dict[str, Any],
        ta_context: Any,
        current_price: float
    ) -> Dict[str, float]:
        """
        Расчет параметров ордера для торговли ЛП
        
        Механика:
        - Entry: Market или Limit от уровня
        - Stop Loss: за зону ЛП (High/Low пробоя × 1.1)
        - Take Profit: 2-3 стопа
        
        Args:
            level: Уровень ЛП
            fb_details: Детали ЛП
            ta_context: Технический контекст
            current_price: Текущая цена
            
        Returns:
            Словарь с параметрами ордера
        """
        try:
            direction = fb_details.get("direction", "unknown")
            
            # Определяем зону ЛП (High/Low свечи пробоя)
            fb_high = fb_details.get("breakout_high", level.price * 1.01)
            fb_low = fb_details.get("breakout_low", level.price * 0.99)
            
            # ENTRY PRICE
            if self.entry_type == "market":
                entry_price = current_price
            else:
                # Limit ордер от уровня
                offset = level.price * self.limit_offset
                
                if direction == "upward":
                    # ЛП вверх → входим в SHORT → лимит выше
                    entry_price = level.price + offset
                else:
                    # ЛП вниз → входим в LONG → лимит ниже
                    entry_price = level.price - offset
            
            # STOP LOSS (за зону ЛП)
            if direction == "upward":
                # ЛП вверх → SHORT → стоп выше High ЛП
                stop_loss = fb_high * self.stop_beyond_extreme
                stop_distance = abs(entry_price - stop_loss)
            else:
                # ЛП вниз → LONG → стоп ниже Low ЛП
                stop_loss = fb_low / self.stop_beyond_extreme
                stop_distance = abs(stop_loss - entry_price)
            
            # TAKE PROFIT
            basic_tp_distance = stop_distance * self.take_profit_ratio
            
            if direction == "upward":
                # SHORT
                take_profit = entry_price - basic_tp_distance
            else:
                # LONG
                take_profit = entry_price + basic_tp_distance
            
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
                "fb_low": fb_low
            }
            
            logger.debug(f"📊 Параметры ордера ЛП: Entry={entry_price:.2f} ({self.entry_type}), "
                        f"SL={stop_loss:.2f}, TP={take_profit:.2f}, R:R={actual_rr_ratio:.1f}:1")
            
            return params
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета параметров: {e}")
            return {}
    
    # ==================== СОЗДАНИЕ СИГНАЛА ====================
    
    def _create_false_breakout_signal(
        self,
        level: Any,
        fb_details: Dict[str, Any],
        order_params: Dict[str, float],
        current_price: float
    ) -> TradingSignal:
        """
        Создание торгового сигнала после ЛП
        
        Торгуем ПРОТИВ направления пробоя:
        - ЛП вверх → SELL
        - ЛП вниз → BUY
        
        Args:
            level: Уровень ЛП
            fb_details: Детали ЛП
            order_params: Параметры ордера
            current_price: Текущая цена
            
        Returns:
            TradingSignal
        """
        try:
            direction = fb_details.get("direction", "unknown")
            
            # Определяем тип сигнала (ПРОТИВ пробоя)
            if direction == "upward":
                # ЛП вверх → входим в SHORT
                signal_type = SignalType.SELL
                
                # Если простой ЛП → STRONG
                if fb_details.get("type") == "simple":
                    signal_type = SignalType.STRONG_SELL
            
            else:
                # ЛП вниз → входим в LONG
                signal_type = SignalType.BUY
                
                # Если простой ЛП → STRONG
                if fb_details.get("type") == "simple":
                    signal_type = SignalType.STRONG_BUY
            
            # Расчет силы сигнала
            strength = self._calculate_signal_strength(
                fb_details=fb_details,
                level=level
            )
            
            # Расчет уверенности
            confidence = self._calculate_signal_confidence(
                fb_details=fb_details,
                level=level,
                order_params=order_params
            )
            
            # Причины
            reasons = self._build_signal_reasons(
                level=level,
                fb_details=fb_details,
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
                fb_details.get("type", "simple"),
                f"Тип ЛП: {fb_details.get('type', 'simple')}"
            )
            
            signal.add_technical_indicator(
                "level_price",
                level.price,
                f"{level.level_type} @ {level.price:.2f}"
            )
            
            signal.add_technical_indicator(
                "breakout_depth",
                fb_details.get("depth", 0),
                f"Глубина: {fb_details.get('depth', 0):.2f}%"
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
            signal.technical_indicators["fb_details"] = fb_details
            signal.technical_indicators["order_params"] = order_params
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания сигнала: {e}")
            # Создаем базовый сигнал
            direction = fb_details.get("direction", "unknown")
            return self.create_signal(
                signal_type=SignalType.SELL if direction == "upward" else SignalType.BUY,
                strength=0.5,
                confidence=0.5,
                current_price=current_price,
                reasons=["Ложный пробой уровня"]
            )
    
    def _calculate_signal_strength(
        self,
        fb_details: Dict[str, Any],
        level: Any
    ) -> float:
        """Расчет силы сигнала"""
        strength = 0.5  # Базовая
        
        # Бонус за тип ЛП
        if fb_details.get("type") == "simple":
            strength += 0.2  # Простой ЛП = самый надежный
        else:
            strength += 0.1
        
        # Бонус за сильный уровень
        if hasattr(level, 'is_strong') and level.is_strong:
            strength += 0.1
        
        # Бонус за небольшую глубину пробоя (меньше = лучше)
        depth = fb_details.get("depth", 0)
        if depth < 0.5:  # < 0.5%
            strength += 0.1
        
        return min(1.0, strength)
    
    def _calculate_signal_confidence(
        self,
        fb_details: Dict[str, Any],
        level: Any,
        order_params: Dict[str, float]
    ) -> float:
        """Расчет уверенности в сигнале"""
        confidence = 0.6  # Базовая
        
        # Бонус за простой ЛП
        if fb_details.get("type") == "simple":
            confidence += 0.15
        
        # Бонус за сильный уровень
        if hasattr(level, 'strength') and level.strength >= 0.8:
            confidence += 0.1
        
        # Бонус за хороший R:R
        rr_ratio = order_params.get("risk_reward_ratio", 0)
        if rr_ratio >= 2.5:
            confidence += 0.05
        
        return min(1.0, confidence)
    
    def _build_signal_reasons(
        self,
        level: Any,
        fb_details: Dict[str, Any],
        order_params: Dict[str, float]
    ) -> List[str]:
        """Построение списка причин сигнала"""
        reasons = []
        
        # Тип ЛП
        fb_type = fb_details.get("type", "simple")
        fb_type_names = {
            "simple": "Простой ЛП (1-2 бара)",
            "strong": "Сильный ЛП (3+ бара)"
        }
        
        fb_name = fb_type_names.get(fb_type, "Ложный пробой")
        
        direction = fb_details.get("direction", "unknown")
        direction_text = "вверх" if direction == "upward" else "вниз"
        
        reasons.append(f"{fb_name} {direction_text} через {level.level_type} @ {level.price:.2f}")
        
        # Глубина пробоя
        depth = fb_details.get("depth", 0)
        if depth > 0:
            reasons.append(f"Глубина пробоя: {depth:.2f}%")
        
        # Подтверждение разворота
        reasons.append("Цена подтвердила разворот за уровень")
        
        # Сила уровня
        if hasattr(level, 'is_strong') and level.is_strong:
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
                "fb_depth_range": f"{self.min_fb_depth*100}-{self.max_fb_depth*100}%",
                "prefer_simple_fb": self.prefer_simple_fb,
                "confirmation_required": self.confirmation_required,
                "max_time_after_fb_hours": self.max_time_since_breakout.total_seconds() / 3600,
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

logger.info("✅ False Breakout Strategy v3.0.1 loaded (FIXED: KeyError resolved)")
