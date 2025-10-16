import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Set, Union
from enum import Enum
from dataclasses import dataclass, field
from collections import deque, defaultdict
import traceback
from abc import ABC, abstractmethod

from strategies import TradingSignal, SignalType, BaseStrategy
from .data_models import SignalMetrics, SystemConfig, NotificationSettings

logger = logging.getLogger(__name__)


class SignalPriority(Enum):
    """Приоритеты обработки сигналов"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class SignalStatus(Enum):
    """Статусы сигналов в системе"""
    PENDING = "pending"
    PROCESSING = "processing"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass
class ProcessedSignal:
    """Сигнал с метаданными обработки"""
    original_signal: TradingSignal
    priority: SignalPriority
    status: SignalStatus
    created_at: datetime
    processed_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    processing_duration: float = 0.0
    filter_results: Dict[str, bool] = field(default_factory=dict)
    rejection_reasons: List[str] = field(default_factory=list)
    enhancement_applied: List[str] = field(default_factory=list)
    final_message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь"""
        return {
            "signal": self.original_signal.to_dict(),
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "processing_duration": self.processing_duration,
            "filter_results": self.filter_results,
            "rejection_reasons": self.rejection_reasons,
            "enhancement_applied": self.enhancement_applied
        }


class SignalFilter(ABC):
    """Абстрактный базовый класс для фильтров сигналов"""
    
    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.stats = {
            "total_processed": 0,
            "approved": 0,
            "rejected": 0,
            "errors": 0
        }
    
    @abstractmethod
    async def apply_filter(self, signal: TradingSignal, context: Dict[str, Any]) -> bool:
        """
        Применяет фильтр к сигналу
        
        Returns:
            True если сигнал прошел фильтр, False если отклонен
        """
        pass
    
    def get_rejection_reason(self) -> str:
        """Возвращает причину отклонения сигнала"""
        return f"Отклонен фильтром {self.name}"


class ConflictFilter(SignalFilter):
    """Фильтр конфликтующих сигналов"""
    
    def __init__(self, conflict_window_minutes: int = 10):
        super().__init__("ConflictFilter")
        self.conflict_window = timedelta(minutes=conflict_window_minutes)
        self.recent_signals: deque = deque(maxlen=50)
    
    async def apply_filter(self, signal: TradingSignal, context: Dict[str, Any]) -> bool:
        """Проверяет конфликты с недавними сигналами"""
        try:
            current_time = datetime.now()
            
            cutoff_time = current_time - self.conflict_window
            self.recent_signals = deque(
                [s for s in self.recent_signals if s.timestamp > cutoff_time],
                maxlen=50
            )
            
            for recent_signal in self.recent_signals:
                if self._signals_conflict(signal, recent_signal):
                    self.stats["rejected"] += 1
                    return False
            
            self.recent_signals.append(signal)
            self.stats["approved"] += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка в ConflictFilter: {e}")
            self.stats["errors"] += 1
            return False
    
    def _signals_conflict(self, signal1: TradingSignal, signal2: TradingSignal) -> bool:
        """Проверяет, конфликтуют ли два сигнала"""
        if signal1.strategy_name != signal2.strategy_name:
            if ((signal1.signal_type in [SignalType.BUY, SignalType.STRONG_BUY] and 
                 signal2.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]) or
                (signal1.signal_type in [SignalType.SELL, SignalType.STRONG_SELL] and 
                 signal2.signal_type in [SignalType.BUY, SignalType.STRONG_BUY])):
                return True
        return False
    
    def get_rejection_reason(self) -> str:
        return "Конфликт с недавним сигналом противоположного направления"


class DuplicateFilter(SignalFilter):
    """Фильтр дублирующихся сигналов"""
    
    def __init__(self, duplicate_window_minutes: int = 15):
        super().__init__("DuplicateFilter")
        self.duplicate_window = timedelta(minutes=duplicate_window_minutes)
        self.recent_signals: deque = deque(maxlen=100)
    
    async def apply_filter(self, signal: TradingSignal, context: Dict[str, Any]) -> bool:
        """Проверяет дублирование сигналов"""
        try:
            current_time = datetime.now()
            
            cutoff_time = current_time - self.duplicate_window
            self.recent_signals = deque(
                [s for s in self.recent_signals if s.timestamp > cutoff_time],
                maxlen=100
            )
            
            for recent_signal in self.recent_signals:
                if self._is_duplicate(signal, recent_signal):
                    self.stats["rejected"] += 1
                    return False
            
            self.recent_signals.append(signal)
            self.stats["approved"] += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка в DuplicateFilter: {e}")
            self.stats["errors"] += 1
            return False
    
    def _is_duplicate(self, signal1: TradingSignal, signal2: TradingSignal) -> bool:
        """Проверяет, являются ли сигналы дубликатами"""
        return (signal1.signal_type == signal2.signal_type and 
                signal1.strategy_name == signal2.strategy_name and
                abs(signal1.price - signal2.price) / signal1.price < 0.001)
    
    def get_rejection_reason(self) -> str:
        return "Дублирует недавний сигнал той же стратегии"


class QualityFilter(SignalFilter):
    """Фильтр качества сигналов"""
    
    def __init__(self, min_quality_score: float = 0.6, min_reasons: int = 1):
        super().__init__("QualityFilter")
        self.min_quality_score = min_quality_score
        self.min_reasons = min_reasons
    
    async def apply_filter(self, signal: TradingSignal, context: Dict[str, Any]) -> bool:
        """Проверяет качество сигнала"""
        try:
            if signal.quality_score < self.min_quality_score:
                self.stats["rejected"] += 1
                return False
            
            if len(signal.reasons) < self.min_reasons:
                self.stats["rejected"] += 1
                return False
            
            if not signal.is_valid or signal.is_expired:
                self.stats["rejected"] += 1
                return False
            
            self.stats["approved"] += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка в QualityFilter: {e}")
            self.stats["errors"] += 1
            return False
    
    def get_rejection_reason(self) -> str:
        return f"Низкое качество сигнала (требуется score ≥{self.min_quality_score}, причин ≥{self.min_reasons})"


class SignalProcessor:
    """Процессор сигналов с применением фильтров и улучшений"""
    
    def __init__(self):
        self.filters: List[SignalFilter] = []
        self.enhancement_plugins: List[Callable] = []
        
        self.add_filter(ConflictFilter())
        self.add_filter(DuplicateFilter())
        self.add_filter(QualityFilter())
        
        self.stats = {
            "total_processed": 0,
            "approved": 0,
            "rejected": 0,
            "errors": 0,
            "processing_time_total": 0.0,
            "last_reset": datetime.now()
        }
    
    def add_filter(self, filter_instance: SignalFilter):
        """Добавляет фильтр в процессор"""
        self.filters.append(filter_instance)
        logger.info(f"➕ Добавлен фильтр: {filter_instance.name}")
    
    def remove_filter(self, filter_name: str):
        """Удаляет фильтр по имени"""
        self.filters = [f for f in self.filters if f.name != filter_name]
        logger.info(f"➖ Удален фильтр: {filter_name}")
    
    def enable_filter(self, filter_name: str, enabled: bool = True):
        """Включает/выключает фильтр"""
        for filter_instance in self.filters:
            if filter_instance.name == filter_name:
                filter_instance.enabled = enabled
                status = "включен" if enabled else "выключен"
                logger.info(f"🔧 Фильтр {filter_name} {status}")
                return
        logger.warning(f"⚠️ Фильтр {filter_name} не найден")
    
    async def process_signal(self, signal: TradingSignal) -> ProcessedSignal:
        """
        Обрабатывает сигнал через все фильтры
        
        Returns:
            ProcessedSignal с результатами обработки
        """
        start_time = datetime.now()
        self.stats["total_processed"] += 1
        
        priority = self._determine_priority(signal)
        
        processed_signal = ProcessedSignal(
            original_signal=signal,
            priority=priority,
            status=SignalStatus.PROCESSING,
            created_at=start_time
        )
        
        try:
            context = {"signal": signal, "timestamp": start_time}
            
            for filter_instance in self.filters:
                if not filter_instance.enabled:
                    continue
                
                filter_instance.stats["total_processed"] += 1
                
                try:
                    passed = await filter_instance.apply_filter(signal, context)
                    processed_signal.filter_results[filter_instance.name] = passed
                    
                    if not passed:
                        processed_signal.status = SignalStatus.REJECTED
                        processed_signal.rejection_reasons.append(filter_instance.get_rejection_reason())
                        self.stats["rejected"] += 1
                        break
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка в фильтре {filter_instance.name}: {e}")
                    filter_instance.stats["errors"] += 1
                    processed_signal.filter_results[filter_instance.name] = False
                    processed_signal.rejection_reasons.append(f"Ошибка фильтра {filter_instance.name}")
            
            if processed_signal.status == SignalStatus.PROCESSING:
                processed_signal.status = SignalStatus.APPROVED
                self.stats["approved"] += 1
                
                await self._apply_enhancements(processed_signal)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сигнала: {e}")
            processed_signal.status = SignalStatus.ERROR
            processed_signal.rejection_reasons.append(f"Ошибка обработки: {str(e)}")
            self.stats["errors"] += 1
        
        end_time = datetime.now()
        processed_signal.processed_at = end_time
        processed_signal.processing_duration = (end_time - start_time).total_seconds()
        self.stats["processing_time_total"] += processed_signal.processing_duration
        
        return processed_signal
    
    def _determine_priority(self, signal: TradingSignal) -> SignalPriority:
        """Определяет приоритет сигнала"""
        if (signal.signal_type in [SignalType.STRONG_BUY, SignalType.STRONG_SELL] and 
            signal.strength >= 0.9 and signal.confidence >= 0.9):
            return SignalPriority.CRITICAL
        
        if signal.strength >= 0.8 and signal.confidence >= 0.8:
            return SignalPriority.HIGH
        
        if signal.strength >= 0.6 or signal.confidence >= 0.7:
            return SignalPriority.MEDIUM
        
        return SignalPriority.LOW
    
    async def _apply_enhancements(self, processed_signal: ProcessedSignal):
        """Применяет улучшения к одобренному сигналу"""
        try:
            signal = processed_signal.original_signal
            
            processed_signal.final_message = self._format_signal_message(signal)
            processed_signal.enhancement_applied.append("formatted_message")
            
        except Exception as e:
            logger.error(f"❌ Ошибка применения улучшений: {e}")
    
    def _format_signal_message(self, signal: TradingSignal) -> str:
        """Форматирует сигнал для отправки"""
        try:
            emoji_map = {
                SignalType.STRONG_BUY: "🟢🔥",
                SignalType.BUY: "🟢",
                SignalType.STRONG_SELL: "🔴🔥", 
                SignalType.SELL: "🔴",
                SignalType.NEUTRAL: "🔶"
            }
            
            if signal.strength >= 0.9:
                strength_emoji = "🔥🔥🔥"
                strength_text = "ЭКСТРЕМАЛЬНО СИЛЬНЫЙ"
            elif signal.strength >= 0.8:
                strength_emoji = "🔥🔥"
                strength_text = "ОЧЕНЬ СИЛЬНЫЙ"
            elif signal.strength >= 0.7:
                strength_emoji = "🔥"
                strength_text = "СИЛЬНЫЙ"
            elif signal.strength >= 0.6:
                strength_emoji = "💪"
                strength_text = "СРЕДНИЙ"
            else:
                strength_emoji = "💡"
                strength_text = "СЛАБЫЙ"
            
            message = f"""
{emoji_map.get(signal.signal_type, "🔶")} **ТОРГОВЫЙ СИГНАЛ**

🎯 **Тип:** {signal.signal_type.value}
{strength_emoji} **Сила:** {strength_text} ({signal.strength:.2f})
🎲 **Уверенность:** {signal.confidence_level.value.upper()} ({signal.confidence:.2f})

💰 **Цена:** ${signal.price:,.2f}
📊 **Изменения:**
   • 1 мин: {signal.price_change_1m:+.2f}%
   • 5 мин: {signal.price_change_5m:+.2f}%  
   • 24 ч: {signal.price_change_24h:+.2f}%
📦 **Объем 24ч:** {signal.volume_24h:,.0f} BTC

🧠 **Стратегия:** {signal.strategy_name}
📝 **Анализ:**
"""
            
            for reason in signal.reasons[:3]:
                message += f"   • {reason}\n"
            
            if signal.stop_loss or signal.take_profit:
                message += f"\n🛡️ **Управление рисками:**\n"
                if signal.stop_loss:
                    message += f"   • Stop Loss: ${signal.stop_loss:,.2f}\n"
                if signal.take_profit:
                    message += f"   • Take Profit: ${signal.take_profit:,.2f}\n"
                if signal.position_size_recommendation > 0:
                    message += f"   • Рекомендуемый размер: {signal.position_size_recommendation:.1%}\n"
            
            message += f"""
⏰ {signal.timestamp.strftime('%H:%M:%S')}
⭐ Качество: {signal.quality_score:.2f}/1.0

_Торговые сигналы несут риски!_
            """
            
            return message.strip()
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования сообщения: {e}")
            return f"🚨 СИГНАЛ: {signal.signal_type.value} {signal.symbol} @ ${signal.price:,.2f} ({signal.strategy_name})"
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику процессора"""
        avg_processing_time = (
            self.stats["processing_time_total"] / self.stats["total_processed"]
            if self.stats["total_processed"] > 0 else 0
        )
        
        filter_stats = {}
        for filter_instance in self.filters:
            filter_stats[filter_instance.name] = {
                **filter_instance.stats,
                "enabled": filter_instance.enabled
            }
        
        return {
            **self.stats,
            "average_processing_time": round(avg_processing_time, 4),
            "approval_rate": round(
                self.stats["approved"] / self.stats["total_processed"] * 100, 2
            ) if self.stats["total_processed"] > 0 else 0,
            "filter_stats": filter_stats,
            "active_filters": len([f for f in self.filters if f.enabled])
        }


class SignalManager:
    """
    Центральный менеджер торговых сигналов
    
    Основные функции:
    1. Получение сигналов от стратегий
    2. Обработка и фильтрация сигналов  
    3. Управление подписчиками
    4. Отправка уведомлений
    5. Мониторинг и статистика
    """
    
    def __init__(self, 
                 max_queue_size: int = 1000, 
                 notification_settings: Optional[NotificationSettings] = None,
                 data_source_adapter = None,
                 openai_analyzer = None):
        """
        Инициализация SignalManager
        
        Args:
            max_queue_size: Максимальный размер очереди сигналов
            notification_settings: Настройки уведомлений
            data_source_adapter: Адаптер для получения рыночных данных (опционально)
            openai_analyzer: Анализатор OpenAI для AI обогащения сигналов (опционально)
        """
        self.processor = SignalProcessor()
        self.notification_settings = notification_settings or NotificationSettings()
        
        self.data_source_adapter = data_source_adapter
        self.openai_analyzer = openai_analyzer
        
        self.ai_analysis_enabled = bool(data_source_adapter and openai_analyzer)
        
        if self.ai_analysis_enabled:
            logger.info("🤖 AI анализ включен для всех сигналов")
        else:
            logger.info("⚠️ AI анализ отключен (отсутствует data_source_adapter или openai_analyzer)")
        
        self.signal_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.processed_signals: deque = deque(maxlen=1000)
        
        self.subscribers: Set[Callable] = set()
        
        self.is_running = False
        self.processing_task: Optional[asyncio.Task] = None
        
        self.stats = {
            "signals_received": 0,
            "signals_processed": 0,
            "signals_sent": 0,
            "signals_dropped": 0,
            "subscribers_count": 0,
            "notifications_sent": 0,
            "notification_errors": 0,
            "start_time": datetime.now(),
            "last_signal_time": None,
            "processing_errors": 0,
            "ai_analysis_enabled": self.ai_analysis_enabled,
            "ai_analysis_attempts": 0,
            "ai_analysis_success": 0,
            "ai_analysis_errors": 0,
            "ai_analysis_skipped": 0
        }
        
        logger.info("🎛️ SignalManager инициализирован")
        logger.info(f"   • Размер очереди: {max_queue_size}")
        logger.info(f"   • Процессор с {len(self.processor.filters)} фильтрами")
    
    async def start(self):
        """Запуск менеджера сигналов"""
        try:
            if self.is_running:
                logger.warning("⚠️ SignalManager уже запущен")
                return
            
            logger.info("🚀 Запуск SignalManager...")
            
            self.is_running = True
            self.stats["start_time"] = datetime.now()
            
            self.processing_task = asyncio.create_task(self._signal_processing_loop())
            
            logger.info("✅ SignalManager запущен успешно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска SignalManager: {e}")
            self.is_running = False
            raise
    
    async def stop(self):
        """Остановка менеджера сигналов"""
        try:
            logger.info("🔄 Остановка SignalManager...")
            
            self.is_running = False
            
            if self.processing_task and not self.processing_task.done():
                self.processing_task.cancel()
                try:
                    await self.processing_task
                except asyncio.CancelledError:
                    pass
            
            remaining_signals = []
            while not self.signal_queue.empty():
                try:
                    signal = self.signal_queue.get_nowait()
                    remaining_signals.append(signal)
                except asyncio.QueueEmpty:
                    break
            
            if remaining_signals:
                logger.info(f"⏳ Обрабатываем {len(remaining_signals)} оставшихся сигналов...")
                for signal in remaining_signals:
                    processed_signal = await self.processor.process_signal(signal)
                    if processed_signal.status == SignalStatus.APPROVED:
                        await self._send_to_subscribers(processed_signal)
            
            logger.info("🛑 SignalManager остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки SignalManager: {e}")
    
    async def submit_signal(self, signal: TradingSignal) -> bool:
        """
        Отправляет сигнал в очередь обработки
        
        Args:
            signal: Торговый сигнал для обработки
            
        Returns:
            True если сигнал добавлен в очередь, False если очередь переполнена
        """
        try:
            if not self.is_running:
                logger.warning("⚠️ SignalManager не запущен, сигнал отклонен")
                return False
            
            self.stats["signals_received"] += 1
            self.stats["last_signal_time"] = datetime.now()
            
            try:
                self.signal_queue.put_nowait(signal)
                logger.debug(f"📥 Сигнал добавлен в очередь: {signal.strategy_name}")
                return True
            except asyncio.QueueFull:
                self.stats["signals_dropped"] += 1
                logger.warning(f"⚠️ Очередь сигналов переполнена, сигнал отброшен")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления сигнала: {e}")
            return False
    
    async def _signal_processing_loop(self):
        """Основной цикл обработки сигналов"""
        logger.info("🔄 Запущен цикл обработки сигналов")
        
        while self.is_running:
            try:
                try:
                    signal = await asyncio.wait_for(self.signal_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                processed_signal = await self.processor.process_signal(signal)
                self.stats["signals_processed"] += 1
                
                self.processed_signals.append(processed_signal)
                
                if processed_signal.status == SignalStatus.APPROVED:
                    await self._send_to_subscribers(processed_signal)
                
                self.signal_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("🔄 Цикл обработки сигналов отменен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле обработки сигналов: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.stats["processing_errors"] += 1
                await asyncio.sleep(1)
        
        logger.info("🛑 Цикл обработки сигналов остановлен")
    
    async def _enhance_with_ai_analysis(self, processed_signal: ProcessedSignal) -> str:
        """
        Обогащает сигнал AI анализом от OpenAI
        
        Берет уже отформатированное сообщение и ДОПОЛНЯЕТ его AI анализом:
        1. Получает актуальные рыночные данные через data_source_adapter
        2. Формирует market_data для OpenAI
        3. Вызывает OpenAI анализ
        4. Комбинирует исходное сообщение + AI анализ
        
        Args:
            processed_signal: Обработанный сигнал с final_message
            
        Returns:
            Обогащенное сообщение (исходное + AI анализ)
        """
        try:
            self.stats["ai_analysis_attempts"] += 1
            
            if not self.ai_analysis_enabled:
                logger.debug("AI анализ отключен, возвращаю исходное сообщение")
                self.stats["ai_analysis_skipped"] += 1
                return processed_signal.final_message
            
            original_signal = processed_signal.original_signal
            
            logger.info(f"🤖 Запуск AI анализа для {original_signal.strategy_name} сигнала...")
            
            try:
                market_snapshot = await self.data_source_adapter.get_market_snapshot(
                    symbol=original_signal.symbol
                )
                
                if not market_snapshot:
                    logger.warning("⚠️ Не удалось получить market_snapshot, пропускаю AI анализ")
                    self.stats["ai_analysis_skipped"] += 1
                    return processed_signal.final_message
                    
            except Exception as e:
                logger.error(f"❌ Ошибка получения market_snapshot: {e}")
                self.stats["ai_analysis_errors"] += 1
                return processed_signal.final_message
            
            market_data_for_ai = {
                'current_price': market_snapshot.current_price,
                'price_change_24h': market_snapshot.price_change_24h,
                'volume_24h': market_snapshot.volume_24h,
                'high_24h': market_snapshot.high_24h,
                'low_24h': market_snapshot.low_24h,
                'open_interest': market_snapshot.open_interest,
                'price_change_1m': getattr(market_snapshot, 'price_change_1m', 0),
                'price_change_5m': getattr(market_snapshot, 'price_change_5m', 0),
                'signal_type': original_signal.signal_type.value,
                'signal_strength': original_signal.strength,
                'signal_confidence': original_signal.confidence,
                'strategy_name': original_signal.strategy_name,
                'signal_reasons': original_signal.reasons[:3],
                'hourly_data': market_snapshot.hourly_stats if hasattr(market_snapshot, 'hourly_stats') else {}
            }
            
            logger.debug(f"📊 Market data подготовлены: price=${market_data_for_ai['current_price']:.2f}, "
                        f"24h_change={market_data_for_ai['price_change_24h']:+.2f}%")
            
            try:
                ai_analysis = await self.openai_analyzer.analyze_market(market_data_for_ai)
                
                if not ai_analysis or len(ai_analysis.strip()) < 50:
                    logger.warning("⚠️ AI анализ пустой или слишком короткий, пропускаю")
                    self.stats["ai_analysis_skipped"] += 1
                    return processed_signal.final_message
                
                logger.info(f"✅ AI анализ получен ({len(ai_analysis)} символов)")
                self.stats["ai_analysis_success"] += 1
                
            except Exception as e:
                logger.error(f"❌ Ошибка вызова OpenAI: {e}")
                self.stats["ai_analysis_errors"] += 1
                return processed_signal.final_message
            
            enhanced_message = f"""{processed_signal.final_message}

━━━━━━━━━━━━━━━━━━━━━━

🤖 **AI АНАЛИЗ РЫНКА**

{ai_analysis}

━━━━━━━━━━━━━━━━━━━━━━
_Анализ сгенерирован OpenAI на основе текущих рыночных данных_
"""
            
            logger.info("✅ Сообщение успешно обогащено AI анализом")
            return enhanced_message
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в _enhance_with_ai_analysis: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            self.stats["ai_analysis_errors"] += 1
            return processed_signal.final_message
    
    async def _send_to_subscribers(self, processed_signal: ProcessedSignal):
        """Отправляет обработанный сигнал всем подписчикам"""
        try:
            if not self.subscribers:
                return
            
            processed_signal.status = SignalStatus.SENT
            processed_signal.sent_at = datetime.now()
            
            final_message_to_send = processed_signal.final_message
            
            if self.ai_analysis_enabled:
                try:
                    logger.info("🤖 Обогащение сигнала AI анализом...")
                    enhanced_message = await self._enhance_with_ai_analysis(processed_signal)
                    final_message_to_send = enhanced_message
                    logger.info("✅ Сигнал успешно обогащен AI")
                except Exception as e:
                    logger.error(f"❌ Ошибка AI обогащения: {e}")
                    final_message_to_send = processed_signal.final_message
            else:
                logger.debug("AI анализ отключен, отправляю исходное сообщение")
            
            success_count = 0
            error_count = 0
            
            tasks = []
            for subscriber in self.subscribers.copy():
                task = asyncio.create_task(
                    self._notify_subscriber(subscriber, final_message_to_send)
                )
                tasks.append(task)
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        error_count += 1
                        logger.error(f"❌ Ошибка уведомления подписчика: {result}")
                    else:
                        success_count += 1
            
            self.stats["signals_sent"] += 1
            self.stats["notifications_sent"] += success_count
            self.stats["notification_errors"] += error_count
            
            logger.info(f"📤 Сигнал отправлен: ✅{success_count} успешно, ❌{error_count} ошибок")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки подписчикам: {e}")
    
    async def _notify_subscriber(self, subscriber: Callable, message: str):
        """Уведомляет конкретного подписчика"""
        try:
            if asyncio.iscoroutinefunction(subscriber):
                await subscriber(message)
            else:
                subscriber(message)
                
        except Exception as e:
            logger.error(f"❌ Ошибка вызова подписчика: {e}")
            raise
    
    def add_subscriber(self, callback: Callable):
        """
        Добавляет подписчика на уведомления о сигналах
        
        Args:
            callback: Функция для обработки сигналов (может быть async)
        """
        self.subscribers.add(callback)
        self.stats["subscribers_count"] = len(self.subscribers)
        logger.info(f"📝 Добавлен подписчик ({len(self.subscribers)} всего)")
    
    def remove_subscriber(self, callback: Callable):
        """Удаляет подписчика"""
        self.subscribers.discard(callback)
        self.stats["subscribers_count"] = len(self.subscribers)
        logger.info(f"🗑️ Удален подписчик ({len(self.subscribers)} осталось)")
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает полную статистику менеджера"""
        uptime = datetime.now() - self.stats["start_time"]
        
        processor_stats = self.processor.get_stats()
        
        return {
            **self.stats,
            "uptime_seconds": uptime.total_seconds(),
            "uptime_formatted": str(uptime).split('.')[0],
            "is_running": self.is_running,
            "queue_size": self.signal_queue.qsize(),
            "queue_max_size": self.signal_queue.maxsize,
            "processed_signals_history": len(self.processed_signals),
            "processor_stats": processor_stats,
            "success_rate": round(
                (self.stats["signals_sent"] / self.stats["signals_processed"] * 100)
                if self.stats["signals_processed"] > 0 else 0, 2
            ),
            "signals_per_hour": round(
                self.stats["signals_processed"] / (uptime.total_seconds() / 3600)
                if uptime.total_seconds() > 0 else 0, 2
            )
        }
    
    def get_recent_signals(self, hours: int = 1) -> List[ProcessedSignal]:
        """Возвращает недавние обработанные сигналы"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            signal for signal in self.processed_signals 
            if signal.created_at > cutoff_time
        ]
    
    def get_filter_stats(self) -> Dict[str, Any]:
        """Возвращает статистику фильтров"""
        return self.processor.get_stats()["filter_stats"]
    
    def configure_processor(self, **kwargs):
        """Настройка процессора сигналов"""
        if "enable_filter" in kwargs:
            filter_name, enabled = kwargs["enable_filter"]
            self.processor.enable_filter(filter_name, enabled)
    
    def __str__(self):
        """Строковое представление менеджера"""
        stats = self.get_stats()
        return (f"SignalManager(running={self.is_running}, "
                f"processed={stats['signals_processed']}, "
                f"sent={stats['signals_sent']}, "
                f"subscribers={len(self.subscribers)}, "
                f"queue={stats['queue_size']}/{stats['queue_max_size']})")
