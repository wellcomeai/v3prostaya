import logging
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from enum import Enum
from dataclasses import dataclass, field
import traceback

# Импортируем типы из market_data модуля
from market_data import MarketDataSnapshot

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Типы торговых сигналов"""
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"
    STRONG_BUY = "STRONG_BUY"
    STRONG_SELL = "STRONG_SELL"


class SignalStrength(Enum):
    """Сила торгового сигнала"""
    VERY_WEAK = 0.1
    WEAK = 0.3
    MODERATE = 0.5
    STRONG = 0.7
    VERY_STRONG = 0.9


class ConfidenceLevel(Enum):
    """Уровень уверенности в сигнале"""
    LOW = "low"           # 0-0.3
    MEDIUM = "medium"     # 0.3-0.7
    HIGH = "high"         # 0.7-1.0


@dataclass
class TradingSignal:
    """Структура торгового сигнала"""
    
    # Основные поля
    signal_type: SignalType
    strength: float  # 0.0 - 1.0
    confidence: float  # 0.0 - 1.0
    price: float
    timestamp: datetime
    
    # Метаданные
    strategy_name: str
    symbol: str
    
    # Анализ и обоснование
    reasons: List[str] = field(default_factory=list)
    technical_indicators: Dict[str, Any] = field(default_factory=dict)
    market_conditions: Dict[str, Any] = field(default_factory=dict)
    
    # Дополнительная информация
    volume_24h: float = 0.0
    price_change_1m: float = 0.0
    price_change_5m: float = 0.0
    price_change_24h: float = 0.0
    
    # Рекомендации по управлению рисками
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size_recommendation: float = 0.0  # Как % от капитала
    
    # Валидность и экспирация
    expires_at: Optional[datetime] = None
    is_valid: bool = True
    
    def __post_init__(self):
        """Пост-инициализация для валидации"""
        # Валидируем силу сигнала
        self.strength = max(0.0, min(1.0, self.strength))
        self.confidence = max(0.0, min(1.0, self.confidence))
        
        # Устанавливаем экспирацию если не задана (по умолчанию 5 минут)
        if self.expires_at is None:
            self.expires_at = self.timestamp + timedelta(minutes=5)
    
    @property
    def strength_level(self) -> SignalStrength:
        """Возвращает уровень силы сигнала"""
        if self.strength >= 0.9:
            return SignalStrength.VERY_STRONG
        elif self.strength >= 0.7:
            return SignalStrength.STRONG
        elif self.strength >= 0.5:
            return SignalStrength.MODERATE
        elif self.strength >= 0.3:
            return SignalStrength.WEAK
        else:
            return SignalStrength.VERY_WEAK
    
    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Возвращает уровень уверенности"""
        if self.confidence >= 0.7:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 0.3:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW
    
    @property
    def is_expired(self) -> bool:
        """Проверяет, истек ли срок действия сигнала"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    @property
    def quality_score(self) -> float:
        """Комплексная оценка качества сигнала (0-1)"""
        # Учитываем силу, уверенность и количество причин
        reason_score = min(len(self.reasons) / 3.0, 1.0)  # До 3 причин = 1.0
        return (self.strength * 0.4 + self.confidence * 0.4 + reason_score * 0.2)
    
    def add_reason(self, reason: str):
        """Добавляет причину для сигнала"""
        if reason and reason not in self.reasons:
            self.reasons.append(reason)
    
    def add_technical_indicator(self, name: str, value: Any, interpretation: str = ""):
        """Добавляет технический индикатор"""
        self.technical_indicators[name] = {
            "value": value,
            "interpretation": interpretation,
            "timestamp": datetime.now().isoformat()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь для сериализации"""
        return {
            "signal_type": self.signal_type.value,
            "strength": self.strength,
            "strength_level": self.strength_level.value,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "reasons": self.reasons,
            "technical_indicators": self.technical_indicators,
            "market_conditions": self.market_conditions,
            "volume_24h": self.volume_24h,
            "price_change_1m": self.price_change_1m,
            "price_change_5m": self.price_change_5m,
            "price_change_24h": self.price_change_24h,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_size_recommendation": self.position_size_recommendation,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_valid": self.is_valid,
            "is_expired": self.is_expired,
            "quality_score": self.quality_score
        }
    
    def __str__(self):
        """Строковое представление сигнала"""
        return (f"{self.signal_type.value} {self.symbol} @ ${self.price:,.2f} "
                f"[Strength: {self.strength:.2f}, Confidence: {self.confidence:.2f}] "
                f"by {self.strategy_name}")


class BaseStrategy(ABC):
    """
    Абстрактный базовый класс для всех торговых стратегий
    
    Предоставляет общую функциональность:
    - Анализ рыночных данных
    - Генерация торговых сигналов
    - Управление cooldown периодами
    - Валидация данных
    - Статистика и мониторинг
    """
    
    def __init__(self, name: str, symbol: str = "BTCUSDT", 
                 min_signal_strength: float = 0.5, 
                 signal_cooldown_minutes: int = 5,
                 max_signals_per_hour: int = 12,
                 enable_risk_management: bool = True):
        """
        Инициализация базовой стратегии
        
        Args:
            name: Имя стратегии
            symbol: Торговый символ
            min_signal_strength: Минимальная сила сигнала для отправки
            signal_cooldown_minutes: Минуты между сигналами одного типа
            max_signals_per_hour: Максимум сигналов в час
            enable_risk_management: Включить управление рисками
        """
        self.name = name
        self.symbol = symbol
        self.min_signal_strength = min_signal_strength
        self.signal_cooldown = timedelta(minutes=signal_cooldown_minutes)
        self.max_signals_per_hour = max_signals_per_hour
        self.enable_risk_management = enable_risk_management
        
        # История сигналов и управление частотой
        self.signal_history: List[TradingSignal] = []
        self.last_signals_by_type: Dict[SignalType, datetime] = {}
        
        # Статистика стратегии
        self.stats = {
            "signals_generated": 0,
            "signals_sent": 0,
            "signals_filtered_by_strength": 0,
            "signals_filtered_by_cooldown": 0,
            "signals_filtered_by_rate_limit": 0,
            "analysis_calls": 0,
            "analysis_errors": 0,
            "start_time": datetime.now(),
            "last_analysis_time": None,
            "last_signal_time": None,
            "average_signal_strength": 0.0,
            "average_signal_confidence": 0.0
        }
        
        # Настройки анализа
        self.analysis_enabled = True
        self.debug_mode = False
        
        logger.info(f"🧠 Стратегия '{self.name}' инициализирована для {self.symbol}")
        logger.info(f"   • Мин. сила сигнала: {self.min_signal_strength}")
        logger.info(f"   • Cooldown: {signal_cooldown_minutes} мин")
        logger.info(f"   • Макс. сигналов/час: {max_signals_per_hour}")
    
    @abstractmethod
    async def analyze_market_data(self, market_data: MarketDataSnapshot) -> Optional[TradingSignal]:
        """
        Абстрактный метод анализа рыночных данных
        
        Должен быть реализован в каждой конкретной стратегии.
        
        Args:
            market_data: Снимок рыночных данных
            
        Returns:
            Торговый сигнал или None если сигнала нет
        """
        pass
    
    async def process_market_data(self, market_data: MarketDataSnapshot) -> Optional[TradingSignal]:
        """
        Основной метод обработки рыночных данных
        
        Выполняет полный цикл:
        1. Валидация входных данных
        2. Вызов анализа стратегии
        3. Фильтрация сигналов
        4. Обновление статистики
        
        Args:
            market_data: Снимок рыночных данных
            
        Returns:
            Готовый к отправке торговый сигнал или None
        """
        try:
            self.stats["analysis_calls"] += 1
            self.stats["last_analysis_time"] = datetime.now()
            
            # Проверяем, включен ли анализ
            if not self.analysis_enabled:
                if self.debug_mode:
                    logger.debug(f"📵 Анализ отключен для стратегии {self.name}")
                return None
            
            # Валидируем входные данные
            if not self._validate_market_data(market_data):
                if self.debug_mode:
                    logger.warning(f"⚠️ Невалидные рыночные данные для {self.name}")
                return None
            
            # Вызываем анализ конкретной стратегии
            raw_signal = await self.analyze_market_data(market_data)
            
            if raw_signal is None:
                return None
            
            self.stats["signals_generated"] += 1
            
            # Фильтруем сигнал по всем критериям
            if not await self._should_send_signal(raw_signal):
                return None
            
            # Применяем управление рисками если включено
            if self.enable_risk_management:
                self._apply_risk_management(raw_signal, market_data)
            
            # Добавляем в историю и обновляем статистику
            self._add_signal_to_history(raw_signal)
            self._update_signal_stats(raw_signal)
            
            self.stats["signals_sent"] += 1
            self.stats["last_signal_time"] = datetime.now()
            
            logger.info(f"✅ Сигнал создан {self.name}: {raw_signal}")
            
            return raw_signal
            
        except Exception as e:
            self.stats["analysis_errors"] += 1
            logger.error(f"❌ Ошибка в process_market_data для {self.name}: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return None
    
    @abstractmethod
    async def analyze_market_opinion(
        self,
        market_snapshot,
        ta_context
    ) -> Dict[str, Any]:
        """
        Анализирует рынок и возвращает мнение стратегии БЕЗ генерации сигнала
        
        Используется для получения аналитического мнения стратегии
        о текущем состоянии рынка.
        
        Args:
            market_snapshot: MarketDataSnapshot с рыночными данными
            ta_context: TechnicalAnalysisContext с техническим анализом
            
        Returns:
            Dict с полями:
                - opinion: str ("BULLISH", "BEARISH", "NEUTRAL")
                - confidence: float (0.0 - 1.0)
                - reasoning: str (краткое обоснование)
                - signal_strength: float (0.0 - 1.0)
                - key_points: List[str] (ключевые моменты)
        
        Example:
            {
                "opinion": "BULLISH",
                "confidence": 0.75,
                "reasoning": "Сильный импульс роста с увеличением объемов",
                "signal_strength": 0.8,
                "key_points": [
                    "Рост +2.5% за 5 минут",
                    "Объем на 30% выше среднего",
                    "Пробой ключевого уровня $50,000"
                ]
            }
        """
        pass
    
    def _validate_market_data(self, market_data: MarketDataSnapshot) -> bool:
        """Валидация рыночных данных"""
        try:
            # Проверяем основные поля
            if not market_data or market_data.symbol != self.symbol:
                return False
            
            # Проверяем что цена валидна
            if market_data.current_price <= 0:
                return False
            
            # Проверяем свежесть данных (не старше 5 минут)
            age = datetime.now() - market_data.timestamp
            if age > timedelta(minutes=5):
                if self.debug_mode:
                    logger.warning(f"⚠️ Устаревшие данные: {age.total_seconds():.1f} сек")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка валидации данных: {e}")
            return False
    
    async def _should_send_signal(self, signal: TradingSignal) -> bool:
        """
        Проверяет, должен ли быть отправлен сигнал
        
        Фильтры:
        1. Минимальная сила сигнала
        2. Cooldown между сигналами
        3. Rate limiting (макс. сигналов в час)
        4. Валидность сигнала
        """
        try:
            # Проверка силы сигнала
            if signal.strength < self.min_signal_strength:
                self.stats["signals_filtered_by_strength"] += 1
                if self.debug_mode:
                    logger.debug(f"🔇 Сигнал отфильтрован по силе: {signal.strength:.2f} < {self.min_signal_strength}")
                return False
            
            # Проверка cooldown
            if not self._check_cooldown(signal.signal_type):
                self.stats["signals_filtered_by_cooldown"] += 1
                if self.debug_mode:
                    logger.debug(f"⏰ Сигнал в cooldown: {signal.signal_type.value}")
                return False
            
            # Проверка rate limit
            if not self._check_rate_limit():
                self.stats["signals_filtered_by_rate_limit"] += 1
                if self.debug_mode:
                    logger.debug(f"🚦 Превышен лимит сигналов в час")
                return False
            
            # Проверка валидности и экспирации
            if not signal.is_valid or signal.is_expired:
                if self.debug_mode:
                    logger.debug(f"❌ Сигнал невалиден или истек")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки сигнала: {e}")
            return False
    
    def _check_cooldown(self, signal_type: SignalType) -> bool:
        """Проверка cooldown между сигналами одного типа"""
        last_signal_time = self.last_signals_by_type.get(signal_type)
        
        if last_signal_time is None:
            return True
        
        time_since_last = datetime.now() - last_signal_time
        return time_since_last >= self.signal_cooldown
    
    def _check_rate_limit(self) -> bool:
        """Проверка лимита сигналов в час"""
        if self.max_signals_per_hour <= 0:
            return True  # Без ограничений
        
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_signals = [
            s for s in self.signal_history 
            if s.timestamp > one_hour_ago
        ]
        
        return len(recent_signals) < self.max_signals_per_hour
    
    def _apply_risk_management(self, signal: TradingSignal, market_data: MarketDataSnapshot):
        """Применяет правила управления рисками"""
        try:
            current_price = signal.price
            
            # Рекомендации по позиции (базовые правила)
            if signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]:
                # Stop loss на 2-3% ниже цены входа
                signal.stop_loss = current_price * 0.97  # 3% стоп
                # Take profit на 4-6% выше
                signal.take_profit = current_price * 1.05  # 5% профит
                
            elif signal.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]:
                # Для коротких позиций (если поддерживается)
                signal.stop_loss = current_price * 1.03  # 3% стоп
                signal.take_profit = current_price * 0.95  # 5% профит
            
            # Размер позиции на основе силы сигнала и волатильности
            base_position_size = 0.02  # 2% от капитала базово
            volatility_factor = abs(market_data.price_change_24h) / 100
            confidence_factor = signal.confidence
            
            # Корректируем размер позиции
            signal.position_size_recommendation = (
                base_position_size * 
                confidence_factor * 
                min(1.5, 1 + volatility_factor)  # Увеличиваем до 1.5x при высокой волатильности
            )
            
            # Ограничиваем максимальным размером
            signal.position_size_recommendation = min(signal.position_size_recommendation, 0.05)  # Макс 5%
            
        except Exception as e:
            logger.error(f"❌ Ошибка применения risk management: {e}")
    
    def _add_signal_to_history(self, signal: TradingSignal):
        """Добавляет сигнал в историю"""
        self.signal_history.append(signal)
        self.last_signals_by_type[signal.signal_type] = signal.timestamp
        
        # Ограничиваем размер истории
        max_history = 100
        if len(self.signal_history) > max_history:
            self.signal_history = self.signal_history[-max_history:]
    
    def _update_signal_stats(self, signal: TradingSignal):
        """Обновляет статистику сигналов"""
        # Вычисляем скользящие средние
        recent_signals = self.signal_history[-20:]  # Последние 20 сигналов
        
        if recent_signals:
            self.stats["average_signal_strength"] = sum(s.strength for s in recent_signals) / len(recent_signals)
            self.stats["average_signal_confidence"] = sum(s.confidence for s in recent_signals) / len(recent_signals)
    
    def create_signal(self, signal_type: SignalType, strength: float, confidence: float, 
                     current_price: float, reasons: List[str] = None, 
                     technical_indicators: Dict[str, Any] = None) -> TradingSignal:
        """
        Помощник для создания торговых сигналов
        
        Args:
            signal_type: Тип сигнала
            strength: Сила сигнала (0-1)
            confidence: Уверенность (0-1)
            current_price: Текущая цена
            reasons: Список причин
            technical_indicators: Технические индикаторы
            
        Returns:
            Новый торговый сигнал
        """
        return TradingSignal(
            signal_type=signal_type,
            strength=strength,
            confidence=confidence,
            price=current_price,
            timestamp=datetime.now(),
            strategy_name=self.name,
            symbol=self.symbol,
            reasons=reasons or [],
            technical_indicators=technical_indicators or {}
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику стратегии"""
        uptime = datetime.now() - self.stats["start_time"]
        
        # Показатели эффективности
        total_signals = self.stats["signals_generated"]
        sent_signals = self.stats["signals_sent"]
        filter_rate = ((total_signals - sent_signals) / total_signals * 100) if total_signals > 0 else 0
        
        # Показатели производительности
        analysis_calls = self.stats["analysis_calls"]
        errors = self.stats["analysis_errors"]
        success_rate = ((analysis_calls - errors) / analysis_calls * 100) if analysis_calls > 0 else 100
        
        return {
            **self.stats,
            "uptime_seconds": uptime.total_seconds(),
            "uptime_formatted": str(uptime).split('.')[0],
            "signals_filter_rate": round(filter_rate, 2),
            "analysis_success_rate": round(success_rate, 2),
            "signals_per_hour": round(sent_signals / (uptime.total_seconds() / 3600), 2) if uptime.total_seconds() > 0 else 0,
            "recent_signals_count": len([s for s in self.signal_history if (datetime.now() - s.timestamp).total_seconds() < 3600])
        }
    
    def get_recent_signals(self, hours: int = 1) -> List[TradingSignal]:
        """Возвращает недавние сигналы"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [s for s in self.signal_history if s.timestamp > cutoff_time]
    
    def enable_debug_mode(self, enabled: bool = True):
        """Включает/выключает режим отладки"""
        self.debug_mode = enabled
        level = "включен" if enabled else "выключен"
        logger.info(f"🐛 Режим отладки {level} для стратегии {self.name}")
    
    def enable_analysis(self, enabled: bool = True):
        """Включает/выключает анализ стратегии"""
        self.analysis_enabled = enabled
        status = "включен" if enabled else "отключен"
        logger.info(f"🧠 Анализ {status} для стратегии {self.name}")
    
    def reset_stats(self):
        """Сбрасывает статистику стратегии"""
        logger.info(f"🔄 Сброс статистики для стратегии {self.name}")
        self.stats = {
            "signals_generated": 0,
            "signals_sent": 0,
            "signals_filtered_by_strength": 0,
            "signals_filtered_by_cooldown": 0,
            "signals_filtered_by_rate_limit": 0,
            "analysis_calls": 0,
            "analysis_errors": 0,
            "start_time": datetime.now(),
            "last_analysis_time": None,
            "last_signal_time": None,
            "average_signal_strength": 0.0,
            "average_signal_confidence": 0.0
        }
        
        # Очищаем историю
        self.signal_history.clear()
        self.last_signals_by_type.clear()
    
    def __str__(self):
        """Строковое представление стратегии"""
        stats = self.get_stats()
        return (f"{self.name}(symbol={self.symbol}, "
                f"signals_sent={stats['signals_sent']}, "
                f"success_rate={stats['analysis_success_rate']:.1f}%, "
                f"enabled={self.analysis_enabled})")
    
    def __repr__(self):
        """Подробное представление для отладки"""
        return (f"{self.__class__.__name__}(name='{self.name}', symbol='{self.symbol}', "
                f"min_strength={self.min_signal_strength}, cooldown={self.signal_cooldown}, "
                f"enabled={self.analysis_enabled}, debug={self.debug_mode})")
