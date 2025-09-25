import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from .base_strategy import BaseStrategy, TradingSignal, SignalType, SignalStrength
from market_data import MarketDataSnapshot

logger = logging.getLogger(__name__)


class MomentumStrategy(BaseStrategy):
    """
    Импульсная торговая стратегия
    
    Анализирует краткосрочные и среднесрочные движения цены для выявления 
    импульсных прорывов и разворотов тренда.
    
    Основные сигналы:
    1. Экстремальные движения (>2% за минуту) - мгновенные сигналы
    2. Импульсная торговля - устойчивые движения за 1м и 5м
    3. Развороты тренда - смена направления движения
    4. Объемный анализ - подтверждение сигналов объемами
    5. Анализ ордербука - давление покупателей/продавцов
    """
    
    def __init__(self, symbol: str = "BTCUSDT", 
                 # Пороги движений цены
                 extreme_movement_threshold: float = 2.0,      # % за 1 минуту для экстремальных сигналов
                 impulse_1m_threshold: float = 1.5,           # % за 1 минуту для импульсных сигналов
                 impulse_5m_threshold: float = 2.0,           # % за 5 минут для импульсных сигналов
                 reversal_1m_threshold: float = 0.8,          # % за 1 минуту для разворотов
                 reversal_5m_threshold: float = 1.0,          # % за 5 минут для разворотов
                 
                 # Объемы
                 high_volume_threshold: float = 20000,        # BTC для определения высокого объема
                 low_volume_threshold: float = 8000,          # BTC для определения низкого объема
                 
                 # Ордербук
                 strong_orderbook_pressure: float = 0.65,     # Сильное давление в ордербуке (65%+)
                 weak_orderbook_pressure: float = 0.35,       # Слабое давление в ордербуке (35%-)
                 
                 # Настройки стратегии
                 min_signal_strength: float = 0.5,
                 signal_cooldown_minutes: int = 5,
                 max_signals_per_hour: int = 12,
                 enable_extreme_signals: bool = True,         # Включить экстремальные сигналы
                 enable_impulse_signals: bool = True,         # Включить импульсные сигналы  
                 enable_reversal_signals: bool = True,        # Включить сигналы разворотов
                 enable_volume_analysis: bool = True,         # Включить объемный анализ
                 enable_orderbook_analysis: bool = True):     # Включить анализ ордербука
        
        super().__init__(
            name="MomentumStrategy",
            symbol=symbol,
            min_signal_strength=min_signal_strength,
            signal_cooldown_minutes=signal_cooldown_minutes,
            max_signals_per_hour=max_signals_per_hour,
            enable_risk_management=True
        )
        
        # Пороги движений
        self.extreme_movement_threshold = extreme_movement_threshold
        self.impulse_1m_threshold = impulse_1m_threshold
        self.impulse_5m_threshold = impulse_5m_threshold
        self.reversal_1m_threshold = reversal_1m_threshold
        self.reversal_5m_threshold = reversal_5m_threshold
        
        # Объемные пороги
        self.high_volume_threshold = high_volume_threshold
        self.low_volume_threshold = low_volume_threshold
        
        # Ордербук
        self.strong_orderbook_pressure = strong_orderbook_pressure
        self.weak_orderbook_pressure = weak_orderbook_pressure
        
        # Включение/выключение компонентов анализа
        self.enable_extreme_signals = enable_extreme_signals
        self.enable_impulse_signals = enable_impulse_signals
        self.enable_reversal_signals = enable_reversal_signals
        self.enable_volume_analysis = enable_volume_analysis
        self.enable_orderbook_analysis = enable_orderbook_analysis
        
        # Внутренние счетчики для статистики
        self.signal_type_stats = {
            "extreme_signals": 0,
            "impulse_signals": 0,
            "reversal_signals": 0,
            "volume_enhanced_signals": 0,
            "orderbook_enhanced_signals": 0
        }
        
        logger.info(f"🚀 MomentumStrategy инициализирована для {symbol}")
        logger.info(f"   • Экстремальные движения: ±{extreme_movement_threshold}% за 1м")
        logger.info(f"   • Импульсные сигналы: {impulse_1m_threshold}%/1м, {impulse_5m_threshold}%/5м")
        logger.info(f"   • Анализ объемов: {enable_volume_analysis}")
        logger.info(f"   • Анализ ордербука: {enable_orderbook_analysis}")
    
    async def analyze_market_data(self, market_data: MarketDataSnapshot) -> Optional[TradingSignal]:
        """
        Основной метод анализа для импульсной стратегии
        
        Последовательность анализа:
        1. Проверка экстремальных движений (приоритет 1)
        2. Анализ импульсных движений (приоритет 2)
        3. Анализ разворотов тренда (приоритет 3)
        4. Дополнение объемным анализом
        5. Дополнение анализом ордербука
        """
        try:
            current_price = market_data.current_price
            change_1m = market_data.price_change_1m
            change_5m = market_data.price_change_5m
            change_24h = market_data.price_change_24h
            volume_24h = market_data.volume_24h
            
            if self.debug_mode:
                logger.debug(f"📊 Анализ: цена=${current_price:,.2f}, 1м={change_1m:+.2f}%, "
                           f"5м={change_5m:+.2f}%, объем={volume_24h:,.0f}")
            
            # 1. ЭКСТРЕМАЛЬНЫЕ ДВИЖЕНИЯ (высший приоритет)
            if self.enable_extreme_signals:
                extreme_signal = await self._analyze_extreme_movements(market_data)
                if extreme_signal:
                    self.signal_type_stats["extreme_signals"] += 1
                    return extreme_signal
            
            # 2. ИМПУЛЬСНЫЕ ДВИЖЕНИЯ  
            if self.enable_impulse_signals:
                impulse_signal = await self._analyze_impulse_movements(market_data)
                if impulse_signal:
                    self.signal_type_stats["impulse_signals"] += 1
                    return impulse_signal
            
            # 3. РАЗВОРОТЫ ТРЕНДА
            if self.enable_reversal_signals:
                reversal_signal = await self._analyze_trend_reversals(market_data)
                if reversal_signal:
                    self.signal_type_stats["reversal_signals"] += 1 
                    return reversal_signal
            
            # Если нет основных сигналов, возвращаем None
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка в analyze_market_data: {e}")
            return None
    
    async def _analyze_extreme_movements(self, market_data: MarketDataSnapshot) -> Optional[TradingSignal]:
        """
        Анализ экстремальных движений цены (>2% за минуту)
        
        Создает сильные сигналы при резких движениях рынка
        """
        try:
            change_1m = market_data.price_change_1m
            current_price = market_data.current_price
            
            # Проверяем экстремальные движения
            if abs(change_1m) >= self.extreme_movement_threshold:
                
                signal_type = SignalType.STRONG_BUY if change_1m > 0 else SignalType.STRONG_SELL
                
                # Сила сигнала зависит от размера движения
                # 2% = 0.6, 3% = 0.8, 5%+ = 1.0
                strength = min(abs(change_1m) / 5.0 + 0.4, 1.0)
                
                # Высокая уверенность для экстремальных движений
                confidence = 0.9
                
                reasons = [f"🚨 ЭКСТРЕМАЛЬНОЕ ДВИЖЕНИЕ: {change_1m:+.2f}% за 1 минуту"]
                
                # Дополняем анализом 5-минутного тренда
                change_5m = market_data.price_change_5m
                if abs(change_5m) > 1.0:
                    if (change_1m > 0 and change_5m > 0) or (change_1m < 0 and change_5m < 0):
                        reasons.append(f"Подтверждение 5м трендом: {change_5m:+.2f}%")
                        confidence = min(confidence + 0.05, 1.0)
                    else:
                        reasons.append(f"Противоречие с 5м трендом: {change_5m:+.2f}%")
                        confidence = max(confidence - 0.1, 0.6)
                
                signal = self.create_signal(
                    signal_type=signal_type,
                    strength=strength,
                    confidence=confidence,
                    current_price=current_price,
                    reasons=reasons
                )
                
                # Добавляем технические индикаторы
                signal.add_technical_indicator("price_change_1m", change_1m, 
                                             f"Экстремальное движение {change_1m:+.2f}%")
                signal.add_technical_indicator("movement_magnitude", abs(change_1m), 
                                             f"Магнитуда движения: {abs(change_1m):.2f}%")
                
                # Дополняем объемным анализом
                if self.enable_volume_analysis:
                    self._enhance_signal_with_volume_analysis(signal, market_data)
                
                # Дополняем анализом ордербука
                if self.enable_orderbook_analysis:
                    self._enhance_signal_with_orderbook_analysis(signal, market_data)
                
                if self.debug_mode:
                    logger.debug(f"⚡ Экстремальный сигнал: {signal}")
                
                return signal
                
        except Exception as e:
            logger.error(f"❌ Ошибка анализа экстремальных движений: {e}")
            
        return None
    
    async def _analyze_impulse_movements(self, market_data: MarketDataSnapshot) -> Optional[TradingSignal]:
        """
        Анализ импульсных движений 
        
        Устойчивые движения в одном направлении за 1м и 5м периоды
        """
        try:
            change_1m = market_data.price_change_1m
            change_5m = market_data.price_change_5m
            current_price = market_data.current_price
            
            signal_type = None
            strength = 0.0
            reasons = []
            
            # ИМПУЛЬС ВВЕРХ
            if (change_1m > self.impulse_1m_threshold and change_5m > self.impulse_5m_threshold):
                signal_type = SignalType.BUY
                strength = 0.4  # Базовая сила
                reasons.append(f"Импульс вверх: 1м={change_1m:+.1f}%, 5м={change_5m:+.1f}%")
                
                # Усиливаем сигнал если движения согласованы
                if change_1m > 0 and change_5m > 0:
                    coherence_bonus = min(abs(change_1m - change_5m) / 10.0, 0.2)
                    strength += coherence_bonus
                
            # ИМПУЛЬС ВНИЗ
            elif (change_1m < -self.impulse_1m_threshold and change_5m < -self.impulse_5m_threshold):
                signal_type = SignalType.SELL
                strength = 0.4  # Базовая сила
                reasons.append(f"Импульс вниз: 1м={change_1m:+.1f}%, 5м={change_5m:+.1f}%")
                
                # Усиливаем сигнал если движения согласованы
                if change_1m < 0 and change_5m < 0:
                    coherence_bonus = min(abs(change_1m - change_5m) / 10.0, 0.2)
                    strength += coherence_bonus
            
            if signal_type is None:
                return None
            
            # Базовая уверенность для импульсных сигналов
            confidence = 0.7
            
            # Проверяем согласованность с 24ч трендом
            change_24h = market_data.price_change_24h
            if abs(change_24h) > 0.5:  # Если есть значимый 24ч тренд
                if ((signal_type == SignalType.BUY and change_24h > 0) or 
                    (signal_type == SignalType.SELL and change_24h < 0)):
                    reasons.append(f"Совпадение с 24ч трендом: {change_24h:+.1f}%")
                    confidence += 0.1
                    strength += 0.1
                else:
                    reasons.append(f"Противоречие с 24ч трендом: {change_24h:+.1f}%")
                    confidence -= 0.1
                    strength -= 0.05
            
            # Ограничиваем значения
            strength = max(0.1, min(1.0, strength))
            confidence = max(0.5, min(1.0, confidence))
            
            signal = self.create_signal(
                signal_type=signal_type,
                strength=strength,
                confidence=confidence,
                current_price=current_price,
                reasons=reasons
            )
            
            # Добавляем технические индикаторы
            signal.add_technical_indicator("impulse_1m", change_1m, f"1-минутный импульс")
            signal.add_technical_indicator("impulse_5m", change_5m, f"5-минутный импульс")
            signal.add_technical_indicator("trend_24h", change_24h, f"24-часовой тренд")
            
            # Дополнительные анализы
            if self.enable_volume_analysis:
                self._enhance_signal_with_volume_analysis(signal, market_data)
                
            if self.enable_orderbook_analysis:
                self._enhance_signal_with_orderbook_analysis(signal, market_data)
            
            if self.debug_mode:
                logger.debug(f"🎯 Импульсный сигнал: {signal}")
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа импульсных движений: {e}")
            
        return None
    
    async def _analyze_trend_reversals(self, market_data: MarketDataSnapshot) -> Optional[TradingSignal]:
        """
        Анализ разворотов тренда
        
        Противоположные движения за 1м и 5м периоды, указывающие на возможный разворот
        """
        try:
            change_1m = market_data.price_change_1m
            change_5m = market_data.price_change_5m
            current_price = market_data.current_price
            
            signal_type = None
            strength = 0.0
            reasons = []
            
            # РАЗВОРОТ ВВЕРХ (1м растет, 5м падал)
            if (change_1m > self.reversal_1m_threshold and change_5m < -self.reversal_5m_threshold):
                signal_type = SignalType.BUY
                strength = 0.3  # Более осторожная сила для разворотов
                reasons.append(f"Возможный разворот вверх: 1м={change_1m:+.1f}%, 5м={change_5m:+.1f}%")
                
            # РАЗВОРОТ ВНИЗ (1м падает, 5м рос)
            elif (change_1m < -self.reversal_1m_threshold and change_5m > self.reversal_5m_threshold):
                signal_type = SignalType.SELL
                strength = 0.3  # Более осторожная сила для разворотов
                reasons.append(f"Возможный разворот вниз: 1м={change_1m:+.1f}%, 5м={change_5m:+.1f}%")
            
            if signal_type is None:
                return None
            
            # Уверенность ниже чем у импульсных сигналов
            confidence = 0.6
            
            # Проверяем силу разворота
            reversal_magnitude = abs(change_1m) + abs(change_5m)
            if reversal_magnitude > 3.0:  # Сильный разворот
                strength += 0.2
                confidence += 0.1
                reasons.append(f"Сильный разворот (магнитуда: {reversal_magnitude:.1f}%)")
            
            # Проверяем подтверждение объемами
            volume_24h = market_data.volume_24h
            if volume_24h > self.high_volume_threshold:
                strength += 0.1
                confidence += 0.05
                reasons.append(f"Подтверждение высоким объемом: {volume_24h:,.0f} BTC")
            
            # Ограничиваем значения
            strength = max(0.1, min(0.8, strength))  # Развороты не должны быть слишком сильными
            confidence = max(0.5, min(0.8, confidence))
            
            signal = self.create_signal(
                signal_type=signal_type,
                strength=strength,
                confidence=confidence,
                current_price=current_price,
                reasons=reasons
            )
            
            # Добавляем технические индикаторы
            signal.add_technical_indicator("reversal_1m", change_1m, "1-минутное движение разворота")
            signal.add_technical_indicator("reversal_5m", change_5m, "5-минутное движение разворота") 
            signal.add_technical_indicator("reversal_magnitude", reversal_magnitude, "Магнитуда разворота")
            
            # Дополнительные анализы
            if self.enable_volume_analysis:
                self._enhance_signal_with_volume_analysis(signal, market_data)
                
            if self.enable_orderbook_analysis:
                self._enhance_signal_with_orderbook_analysis(signal, market_data)
            
            if self.debug_mode:
                logger.debug(f"🔄 Сигнал разворота: {signal}")
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа разворотов: {e}")
            
        return None
    
    def _enhance_signal_with_volume_analysis(self, signal: TradingSignal, market_data: MarketDataSnapshot):
        """Дополняет сигнал объемным анализом"""
        try:
            volume_24h = market_data.volume_24h
            volume_analysis = market_data.volume_analysis
            
            # Анализ объема торгов
            if volume_24h > self.high_volume_threshold:
                signal.strength = min(signal.strength + 0.15, 1.0)
                signal.confidence = min(signal.confidence + 0.1, 1.0)
                signal.add_reason(f"Высокий объем торгов: {volume_24h:,.0f} BTC")
                signal.add_technical_indicator("volume_24h", volume_24h, "Высокий объем подтверждает сигнал")
                self.signal_type_stats["volume_enhanced_signals"] += 1
                
            elif volume_24h < self.low_volume_threshold:
                signal.strength = max(signal.strength - 0.1, 0.1)
                signal.confidence = max(signal.confidence - 0.05, 0.3)
                signal.add_reason(f"Низкий объем торгов: {volume_24h:,.0f} BTC")
                signal.add_technical_indicator("volume_24h", volume_24h, "Низкий объем ослабляет сигнал")
            
            # Анализ соотношения покупок/продаж из трейдов
            if volume_analysis and "buy_sell_ratio" in volume_analysis:
                buy_sell_ratio = volume_analysis.get("buy_sell_ratio", 0)
                
                if ((signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY] and buy_sell_ratio > 0.6) or
                    (signal.signal_type in [SignalType.SELL, SignalType.STRONG_SELL] and buy_sell_ratio < 0.4)):
                    
                    signal.strength = min(signal.strength + 0.1, 1.0)
                    signal.add_reason(f"Объемы торгов подтверждают направление (B/S: {buy_sell_ratio:.2f})")
                    signal.add_technical_indicator("buy_sell_ratio", buy_sell_ratio, "Соотношение объемов покупок/продаж")
                
        except Exception as e:
            logger.error(f"❌ Ошибка объемного анализа: {e}")
    
    def _enhance_signal_with_orderbook_analysis(self, signal: TradingSignal, market_data: MarketDataSnapshot):
        """Дополняет сигнал анализом ордербука"""
        try:
            orderbook_pressure = market_data.orderbook_pressure
            
            if not orderbook_pressure or "pressure_ratio" not in orderbook_pressure:
                return
            
            pressure_ratio = orderbook_pressure.get("pressure_ratio", 0.5)  # 0.5 = равновесие
            
            # Сильное давление покупателей (>65%)
            if pressure_ratio > self.strong_orderbook_pressure:
                if signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]:
                    signal.strength = min(signal.strength + 0.15, 1.0)
                    signal.confidence = min(signal.confidence + 0.1, 1.0)
                    signal.add_reason(f"Давление покупателей в ордербуке: {pressure_ratio:.1%}")
                    self.signal_type_stats["orderbook_enhanced_signals"] += 1
                elif signal.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]:
                    # Противоречие - ослабляем сигнал продажи
                    signal.strength = max(signal.strength - 0.1, 0.1)
                    signal.add_reason(f"Противоречие: продажа при давлении покупателей ({pressure_ratio:.1%})")
            
            # Сильное давление продавцов (<35%)
            elif pressure_ratio < self.weak_orderbook_pressure:
                if signal.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]:
                    signal.strength = min(signal.strength + 0.15, 1.0)
                    signal.confidence = min(signal.confidence + 0.1, 1.0)
                    signal.add_reason(f"Давление продавцов в ордербуке: {(1-pressure_ratio):.1%}")
                    self.signal_type_stats["orderbook_enhanced_signals"] += 1
                elif signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]:
                    # Противоречие - ослабляем сигнал покупки
                    signal.strength = max(signal.strength - 0.1, 0.1)
                    signal.add_reason(f"Противоречие: покупка при давлении продавцов ({(1-pressure_ratio):.1%})")
            
            # Добавляем индикатор в любом случае
            signal.add_technical_indicator("orderbook_pressure", pressure_ratio, 
                                         f"Давление в ордербуке: {pressure_ratio:.1%} покупателей")
            
            # Дополнительная информация об объемах в ордербуке
            total_volume = orderbook_pressure.get("total_orderbook_volume", 0)
            if total_volume > 0:
                signal.add_technical_indicator("orderbook_volume", total_volume, 
                                             f"Общий объем в ордербуке: {total_volume:,.0f}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа ордербука: {e}")
    
    def get_strategy_stats(self) -> Dict[str, Any]:
        """Возвращает расширенную статистику стратегии"""
        base_stats = self.get_stats()
        
        # Добавляем специфичную статистику MomentumStrategy
        momentum_stats = {
            **base_stats,
            "strategy_type": "MomentumStrategy",
            "signal_types": self.signal_type_stats.copy(),
            "thresholds": {
                "extreme_movement": self.extreme_movement_threshold,
                "impulse_1m": self.impulse_1m_threshold,
                "impulse_5m": self.impulse_5m_threshold,
                "reversal_1m": self.reversal_1m_threshold,
                "reversal_5m": self.reversal_5m_threshold,
                "high_volume": self.high_volume_threshold,
                "low_volume": self.low_volume_threshold
            },
            "analysis_enabled": {
                "extreme_signals": self.enable_extreme_signals,
                "impulse_signals": self.enable_impulse_signals,
                "reversal_signals": self.enable_reversal_signals,
                "volume_analysis": self.enable_volume_analysis,
                "orderbook_analysis": self.enable_orderbook_analysis
            }
        }
        
        # Добавляем распределение типов сигналов в процентах
        total_signals = sum(self.signal_type_stats.values())
        if total_signals > 0:
            momentum_stats["signal_type_distribution"] = {
                signal_type: (count / total_signals * 100)
                for signal_type, count in self.signal_type_stats.items()
            }
        else:
            momentum_stats["signal_type_distribution"] = {}
        
        return momentum_stats
    
    def configure_thresholds(self, **kwargs):
        """
        Динамическая настройка порогов стратегии
        
        Полезно для оптимизации параметров без перезапуска
        """
        updated_params = []
        
        if "extreme_movement_threshold" in kwargs:
            self.extreme_movement_threshold = kwargs["extreme_movement_threshold"]
            updated_params.append(f"extreme_movement: {self.extreme_movement_threshold}%")
        
        if "impulse_1m_threshold" in kwargs:
            self.impulse_1m_threshold = kwargs["impulse_1m_threshold"]
            updated_params.append(f"impulse_1m: {self.impulse_1m_threshold}%")
        
        if "impulse_5m_threshold" in kwargs:
            self.impulse_5m_threshold = kwargs["impulse_5m_threshold"]
            updated_params.append(f"impulse_5m: {self.impulse_5m_threshold}%")
        
        if "high_volume_threshold" in kwargs:
            self.high_volume_threshold = kwargs["high_volume_threshold"]
            updated_params.append(f"high_volume: {self.high_volume_threshold:,.0f}")
        
        if "low_volume_threshold" in kwargs:
            self.low_volume_threshold = kwargs["low_volume_threshold"]
            updated_params.append(f"low_volume: {self.low_volume_threshold:,.0f}")
        
        if updated_params:
            logger.info(f"🔧 Обновлены параметры MomentumStrategy: {', '.join(updated_params)}")
    
    def enable_signal_type(self, signal_type: str, enabled: bool = True):
        """
        Включение/выключение типов сигналов
        
        Args:
            signal_type: "extreme", "impulse", "reversal", "volume", "orderbook"
            enabled: True для включения, False для выключения
        """
        status = "включен" if enabled else "выключен"
        
        if signal_type == "extreme":
            self.enable_extreme_signals = enabled
            logger.info(f"🚨 Экстремальные сигналы {status}")
        elif signal_type == "impulse":
            self.enable_impulse_signals = enabled
            logger.info(f"🎯 Импульсные сигналы {status}")
        elif signal_type == "reversal":
            self.enable_reversal_signals = enabled
            logger.info(f"🔄 Сигналы разворотов {status}")
        elif signal_type == "volume":
            self.enable_volume_analysis = enabled
            logger.info(f"📊 Объемный анализ {status}")
        elif signal_type == "orderbook":
            self.enable_orderbook_analysis = enabled
            logger.info(f"📋 Анализ ордербука {status}")
        else:
            logger.warning(f"⚠️ Неизвестный тип сигнала: {signal_type}")
    
    def reset_signal_type_stats(self):
        """Сбрасывает статистику по типам сигналов"""
        self.signal_type_stats = {
            "extreme_signals": 0,
            "impulse_signals": 0,
            "reversal_signals": 0,
            "volume_enhanced_signals": 0,
            "orderbook_enhanced_signals": 0
        }
        logger.info("🔄 Статистика типов сигналов сброшена")
    
    def __str__(self):
        """Строковое представление стратегии"""
        stats = self.get_strategy_stats()
        signal_types_enabled = sum([
            self.enable_extreme_signals,
            self.enable_impulse_signals, 
            self.enable_reversal_signals
        ])
        
        return (f"MomentumStrategy(symbol={self.symbol}, "
                f"signals_sent={stats['signals_sent']}, "
                f"success_rate={stats['analysis_success_rate']:.1f}%, "
                f"types_enabled={signal_types_enabled}/3, "
                f"extreme_threshold={self.extreme_movement_threshold}%)")
    
    def __repr__(self):
        """Подробное представление для отладки"""
        return (f"MomentumStrategy(symbol='{self.symbol}', "
                f"extreme_threshold={self.extreme_movement_threshold}, "
                f"impulse_1m={self.impulse_1m_threshold}, "
                f"impulse_5m={self.impulse_5m_threshold}, "
                f"volume_analysis={self.enable_volume_analysis}, "
                f"orderbook_analysis={self.enable_orderbook_analysis})")
