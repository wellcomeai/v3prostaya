"""
Signal Manager v3.0 - Упрощенная версия

Управляет торговыми сигналами:
- Фильтрация дубликатов
- Управление кулдаунами
- Рассылка подписчикам
- Опциональное AI обогащение через OpenAI

Author: Trading Bot Team
Version: 3.0.0 - Simplified Edition
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Callable, Dict, Any, Optional, Set
from collections import defaultdict

logger = logging.getLogger(__name__)


class SignalManager:
    """
    🎛️ Менеджер торговых сигналов v3.0
    
    Упрощенная версия без сложных зависимостей.
    Фокус на надежности и простоте.
    
    Features:
    - Фильтрация дубликатов по symbol + type
    - Cooldown между сигналами (по умолчанию 5 минут)
    - Подписчики через callback функции
    - Опциональное AI обогащение через OpenAI
    - Статистика и мониторинг
    
    Usage:
        signal_manager = SignalManager(
            openai_analyzer=openai_analyzer
        )
        
        # Добавляем подписчика (например TelegramBot)
        signal_manager.add_subscriber(bot.broadcast_signal)
        
        # Запускаем
        await signal_manager.start()
        
        # Обрабатываем сигнал
        await signal_manager.process_signal(trading_signal)
    """
    
    def __init__(
        self,
        openai_analyzer=None,  # OpenAIAnalyzer (опционально)
        cooldown_minutes: int = 5,
        max_signals_per_hour: int = 12,
        enable_ai_enrichment: bool = True,
        min_signal_strength: float = 0.5
    ):
        """
        Args:
            openai_analyzer: OpenAIAnalyzer для AI обогащения (опционально)
            cooldown_minutes: Минуты между сигналами одного типа/символа
            max_signals_per_hour: Максимум сигналов в час
            enable_ai_enrichment: Включить AI обогащение сигналов
            min_signal_strength: Минимальная сила сигнала для отправки
        """
        self.openai_analyzer = openai_analyzer
        self.cooldown_minutes = cooldown_minutes
        self.max_signals_per_hour = max_signals_per_hour
        self.enable_ai_enrichment = enable_ai_enrichment and openai_analyzer is not None
        self.min_signal_strength = min_signal_strength
        
        # Подписчики (callback функции)
        self.subscribers: List[Callable] = []
        
        # История сигналов для фильтрации
        self.last_signals: Dict[str, datetime] = {}  # key = f"{symbol}_{signal_type}"
        self.signals_history: List[Dict] = []  # Последние сигналы
        
        # Статус
        self.is_running = False
        self.start_time: Optional[datetime] = None
        
        # Статистика
        self.stats = {
            "signals_received": 0,
            "signals_sent": 0,
            "signals_filtered_strength": 0,
            "signals_filtered_cooldown": 0,
            "signals_filtered_rate_limit": 0,
            "ai_enrichments": 0,
            "ai_enrichment_errors": 0,
            "broadcast_errors": 0,
            "start_time": None
        }
        
        logger.info("=" * 70)
        logger.info("🎛️ SignalManager v3.0 инициализирован")
        logger.info("=" * 70)
        logger.info(f"   • Cooldown: {cooldown_minutes} минут")
        logger.info(f"   • Max signals/hour: {max_signals_per_hour}")
        logger.info(f"   • Min strength: {min_signal_strength}")
        logger.info(f"   • AI enrichment: {'✅' if self.enable_ai_enrichment else '❌'}")
        logger.info("=" * 70)
    
    async def start(self):
        """Запустить SignalManager"""
        if self.is_running:
            logger.warning("⚠️ SignalManager уже запущен")
            return
        
        self.is_running = True
        self.start_time = datetime.now(timezone.utc)
        self.stats["start_time"] = self.start_time
        
        logger.info("✅ SignalManager запущен")
    
    async def stop(self):
        """Остановить SignalManager"""
        if not self.is_running:
            logger.warning("⚠️ SignalManager уже остановлен")
            return
        
        self.is_running = False
        
        # Финальная статистика
        uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        logger.info("=" * 70)
        logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА SIGNAL MANAGER")
        logger.info("=" * 70)
        logger.info(f"   • Время работы: {uptime:.0f}s ({uptime/3600:.1f}h)")
        logger.info(f"   • Сигналов получено: {self.stats['signals_received']}")
        logger.info(f"   • Сигналов отправлено: {self.stats['signals_sent']}")
        logger.info(f"   • Отфильтровано по силе: {self.stats['signals_filtered_strength']}")
        logger.info(f"   • Отфильтровано по cooldown: {self.stats['signals_filtered_cooldown']}")
        logger.info(f"   • AI обогащений: {self.stats['ai_enrichments']}")
        logger.info("=" * 70)
        
        logger.info("✅ SignalManager остановлен")
    
    def add_subscriber(self, callback: Callable):
        """
        Добавить подписчика на сигналы
        
        Args:
            callback: Async функция для отправки сигнала
                     Сигнатура: async def callback(message: str)
        """
        if callback not in self.subscribers:
            self.subscribers.append(callback)
            logger.info(f"📡 Добавлен подписчик (всего: {len(self.subscribers)})")
    
    def remove_subscriber(self, callback: Callable):
        """Удалить подписчика"""
        if callback in self.subscribers:
            self.subscribers.remove(callback)
            logger.info(f"📡 Удален подписчик (осталось: {len(self.subscribers)})")
    
    async def process_signal(self, signal) -> bool:
        """
        Обработать торговый сигнал
        
        Args:
            signal: TradingSignal из стратегии
            
        Returns:
            bool: True если сигнал был отправлен
        """
        try:
            self.stats["signals_received"] += 1
            
            # Проверка что менеджер запущен
            if not self.is_running:
                logger.warning("⚠️ SignalManager не запущен, сигнал пропущен")
                return False
            
            # Фильтр 1: Минимальная сила сигнала
            if signal.strength < self.min_signal_strength:
                self.stats["signals_filtered_strength"] += 1
                logger.debug(
                    f"🔇 Сигнал отфильтрован по силе: {signal.symbol} "
                    f"{signal.signal_type.value} (strength={signal.strength:.2f})"
                )
                return False
            
            # Фильтр 2: Cooldown
            signal_key = f"{signal.symbol}_{signal.signal_type.value}"
            
            if signal_key in self.last_signals:
                time_since_last = datetime.now(timezone.utc) - self.last_signals[signal_key]
                cooldown_delta = timedelta(minutes=self.cooldown_minutes)
                
                if time_since_last < cooldown_delta:
                    self.stats["signals_filtered_cooldown"] += 1
                    logger.debug(
                        f"⏰ Сигнал в cooldown: {signal.symbol} {signal.signal_type.value} "
                        f"(прошло {time_since_last.total_seconds():.0f}s)"
                    )
                    return False
            
            # Фильтр 3: Rate limit (максимум сигналов в час)
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            recent_signals = [
                s for s in self.signals_history 
                if s['timestamp'] > one_hour_ago
            ]
            
            if len(recent_signals) >= self.max_signals_per_hour:
                self.stats["signals_filtered_rate_limit"] += 1
                logger.warning(
                    f"🚦 Превышен лимит сигналов: {len(recent_signals)}/{self.max_signals_per_hour}"
                )
                return False
            
            # Формируем базовое сообщение
            message = self._format_signal_message(signal)
            
            # AI обогащение (опционально)
            if self.enable_ai_enrichment:
                try:
                    ai_analysis = await self._enrich_with_ai(signal)
                    if ai_analysis:
                        message += f"\n\n{ai_analysis}"
                        self.stats["ai_enrichments"] += 1
                except Exception as e:
                    logger.error(f"❌ Ошибка AI обогащения: {e}")
                    self.stats["ai_enrichment_errors"] += 1
            
            # Отправляем подписчикам
            await self._broadcast_to_subscribers(message)
            
            # Обновляем историю
            self.last_signals[signal_key] = datetime.now(timezone.utc)
            self.signals_history.append({
                'symbol': signal.symbol,
                'type': signal.signal_type.value,
                'timestamp': datetime.now(timezone.utc),
                'strength': signal.strength
            })
            
            # Ограничиваем размер истории
            if len(self.signals_history) > 100:
                self.signals_history = self.signals_history[-100:]
            
            self.stats["signals_sent"] += 1
            
            logger.info(
                f"✅ Сигнал отправлен: {signal.symbol} {signal.signal_type.value} "
                f"(сила: {signal.strength:.2f}, уверенность: {signal.confidence:.2f})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка обработки сигнала: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _format_signal_message(self, signal) -> str:
        """
        Форматировать сообщение о сигнале
        
        Args:
            signal: TradingSignal
            
        Returns:
            str: Отформатированное сообщение для Telegram
        """
        try:
            # Эмодзи для типов сигналов
            emoji_map = {
                "BUY": "🟢",
                "STRONG_BUY": "🟢🟢",
                "SELL": "🔴",
                "STRONG_SELL": "🔴🔴",
                "NEUTRAL": "🔵"
            }
            
            signal_emoji = emoji_map.get(signal.signal_type.value, "⚪")
            
            # Основное сообщение
            message = f"""🚨 *ТОРГОВЫЙ СИГНАЛ v3.0*

{signal_emoji} *{signal.signal_type.value}* {signal.symbol}

💰 *Цена:* ${signal.price:,.2f}

📊 *Параметры сигнала:*
- Сила: {signal.strength:.2f} ({signal.strength_level.value})
- Уверенность: {signal.confidence:.2f} ({signal.confidence_level.value})
- Качество: {signal.quality_score:.2f}
- Стратегия: {signal.strategy_name}

📈 *Изменения цены:*
- 1 минута: {signal.price_change_1m:+.2f}%
- 5 минут: {signal.price_change_5m:+.2f}%
- 24 часа: {signal.price_change_24h:+.2f}%"""

            # Причины сигнала
            if signal.reasons:
                message += "\n\n🔍 *Причины сигнала:*"
                for i, reason in enumerate(signal.reasons[:5], 1):
                    message += f"\n{i}. {reason}"
            
            # Risk Management (если есть)
            if signal.stop_loss or signal.take_profit:
                message += "\n\n🎯 *Управление рисками:*"
                if signal.stop_loss:
                    message += f"\n• Stop Loss: ${signal.stop_loss:,.2f}"
                if signal.take_profit:
                    message += f"\n• Take Profit: ${signal.take_profit:,.2f}"
                if signal.position_size_recommendation > 0:
                    message += f"\n• Размер позиции: {signal.position_size_recommendation*100:.1f}%"
            
            # Время и валидность
            message += f"\n\n⏰ *Время:* {signal.timestamp.strftime('%H:%M:%S UTC')}"
            if signal.expires_at:
                expires_in = (signal.expires_at - datetime.now()).total_seconds() / 60
                message += f"\n⏳ *Действителен:* {expires_in:.0f} минут"
            
            # Дисклеймер
            message += "\n\n⚠️ _Это не инвестиционный совет! Торговля криптовалютами связана с высокими рисками._"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования сообщения: {e}")
            # Минимальный fallback
            return f"🚨 *СИГНАЛ:* {signal.signal_type.value} {signal.symbol} @ ${signal.price:,.2f}"
    
    async def _enrich_with_ai(self, signal) -> Optional[str]:
        """
        Обогатить сигнал AI анализом через OpenAI
        
        Args:
            signal: TradingSignal
            
        Returns:
            Optional[str]: AI анализ или None
        """
        try:
            if not self.openai_analyzer:
                return None
            
            logger.debug(f"🤖 Запрос AI анализа для {signal.symbol}")
            
            # Формируем данные для AI
            market_data = {
                'current_price': signal.price,
                'price_change_1m': signal.price_change_1m,
                'price_change_5m': signal.price_change_5m,
                'price_change_24h': signal.price_change_24h,
                'volume_24h': signal.volume_24h,
                'signal_type': signal.signal_type.value,
                'signal_strength': signal.strength,
                'signal_confidence': signal.confidence,
                'strategy_name': signal.strategy_name,
                'signal_reasons': signal.reasons
            }
            
            # Получаем AI анализ
            ai_analysis = await self.openai_analyzer.analyze_market(market_data)
            
            if ai_analysis and len(ai_analysis) > 50:
                logger.debug(f"✅ AI анализ получен ({len(ai_analysis)} символов)")
                return f"🤖 *AI АНАЛИЗ:*\n\n{ai_analysis}"
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка AI обогащения: {e}")
            return None
    
    async def _broadcast_to_subscribers(self, message: str):
        """
        Отправить сообщение всем подписчикам
        
        Args:
            message: Сообщение для рассылки
        """
        if not self.subscribers:
            logger.warning("⚠️ Нет подписчиков для рассылки сигнала")
            return
        
        logger.debug(f"📡 Рассылка сигнала {len(self.subscribers)} подписчикам")
        
        # Отправляем параллельно всем подписчикам
        tasks = []
        for callback in self.subscribers:
            tasks.append(self._safe_call_subscriber(callback, message))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Подсчитываем успешные/неудачные
        success_count = sum(1 for r in results if r is True)
        error_count = sum(1 for r in results if isinstance(r, Exception))
        
        logger.info(f"📨 Рассылка завершена: ✅{success_count} успешно, ❌{error_count} ошибок")
        
        if error_count > 0:
            self.stats["broadcast_errors"] += error_count
    
    async def _safe_call_subscriber(self, callback: Callable, message: str) -> bool:
        """
        Безопасный вызов подписчика с обработкой ошибок
        
        Args:
            callback: Async функция подписчика
            message: Сообщение
            
        Returns:
            bool: True если успешно
        """
        try:
            await callback(message)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка вызова подписчика: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику"""
        uptime = 0
        if self.start_time:
            uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        filter_rate = 0
        if self.stats["signals_received"] > 0:
            filtered_total = (
                self.stats["signals_filtered_strength"] +
                self.stats["signals_filtered_cooldown"] +
                self.stats["signals_filtered_rate_limit"]
            )
            filter_rate = (filtered_total / self.stats["signals_received"]) * 100
        
        return {
            **self.stats,
            "is_running": self.is_running,
            "uptime_seconds": uptime,
            "subscribers_count": len(self.subscribers),
            "recent_signals_count": len(self.signals_history),
            "filter_rate_percent": filter_rate,
            "signals_per_hour": (self.stats["signals_sent"] / (uptime / 3600)) if uptime > 0 else 0
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Проверка здоровья"""
        stats = self.get_stats()
        
        is_healthy = (
            self.is_running and
            len(self.subscribers) > 0 and
            stats["signals_received"] >= 0
        )
        
        return {
            "healthy": is_healthy,
            "is_running": self.is_running,
            "subscribers_count": len(self.subscribers),
            "signals_sent": self.stats["signals_sent"],
            "signals_filtered": (
                self.stats["signals_filtered_strength"] +
                self.stats["signals_filtered_cooldown"] +
                self.stats["signals_filtered_rate_limit"]
            ),
            "uptime_seconds": stats["uptime_seconds"]
        }
    
    def __repr__(self) -> str:
        """Представление для отладки"""
        return (f"SignalManager(running={self.is_running}, "
                f"subscribers={len(self.subscribers)}, "
                f"signals_sent={self.stats['signals_sent']})")


# Export
__all__ = ["SignalManager"]

logger.info("✅ SignalManager v3.0 loaded - Simplified Edition")
