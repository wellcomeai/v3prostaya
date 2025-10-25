"""
🧪 ТЕСТОВЫЙ СКРИПТ: Проверка цепочки передачи сигналов
Используй этот скрипт чтобы найти, где именно теряются сигналы
"""

import asyncio
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_signal_chain():
    """Тестирование всей цепочки передачи сигналов"""
    
    print("=" * 80)
    print("🧪 ТЕСТИРОВАНИЕ ЦЕПОЧКИ ПЕРЕДАЧИ СИГНАЛОВ")
    print("=" * 80)
    
    # ШАГ 1: Проверка импортов
    print("\n📦 ШАГ 1: Проверка импортов...")
    try:
        from strategies.base_strategy import TradingSignal, SignalType
        from core.signal_manager import SignalManager
        from telegram_bot import TelegramBot
        from config import Config
        print("✅ Все модули успешно импортированы")
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return
    
    # ШАГ 2: Создание тестового сигнала
    print("\n🔔 ШАГ 2: Создание тестового сигнала...")
    test_signal = TradingSignal(
        symbol="BTCUSDT",
        signal_type=SignalType.BUY,
        price=50000.0,
        timestamp=datetime.now(),
        strength=0.8,  # Высокая сила
        confidence=0.9,
        reasons=["Тестовый сигнал для проверки"],
        timeframe="1h"
    )
    print(f"✅ Сигнал создан: {test_signal.symbol} - {test_signal.signal_type.name}")
    print(f"   Сила: {test_signal.strength}, Confidence: {test_signal.confidence}")
    
    # ШАГ 3: Инициализация компонентов
    print("\n🔧 ШАГ 3: Инициализация компонентов...")
    
    # Mock TelegramBot для теста
    class MockTelegramBot:
        def __init__(self):
            self.all_users = {123456789}  # Тестовый пользователь
            self.received_signals = []
        
        async def broadcast_signal(self, message: str):
            print(f"\n📨 TelegramBot.broadcast_signal вызван!")
            print(f"   Пользователей: {len(self.all_users)}")
            print(f"   Сообщение: {message[:100]}...")
            self.received_signals.append(message)
            print("✅ Сигнал успешно получен ботом!")
    
    bot_mock = MockTelegramBot()
    print(f"✅ Mock бот создан с {len(bot_mock.all_users)} пользователями")
    
    # Создаем SignalManager без OpenAI для теста
    signal_manager = SignalManager(
        openai_analyzer=None,
        cooldown_minutes=0,  # Отключаем cooldown
        max_signals_per_hour=1000,  # Большой лимит
        enable_ai_enrichment=False,  # Отключаем AI
        min_signal_strength=0.1  # Низкий порог
    )
    print("✅ SignalManager создан")
    
    # ШАГ 4: Регистрация подписчика
    print("\n📡 ШАГ 4: Регистрация подписчика...")
    signal_manager.add_subscriber(bot_mock.broadcast_signal)
    print(f"✅ Подписчик зарегистрирован. Всего подписчиков: {len(signal_manager.subscribers)}")
    
    if len(signal_manager.subscribers) == 0:
        print("❌ ПРОБЛЕМА: Подписчик не зарегистрирован!")
        return
    
    # ШАГ 5: Отправка тестового сигнала
    print("\n🚀 ШАГ 5: Отправка тестового сигнала через SignalManager...")
    try:
        await signal_manager.process_signal(test_signal)
        print("✅ SignalManager.process_signal выполнен")
    except Exception as e:
        print(f"❌ Ошибка в SignalManager.process_signal: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ШАГ 6: Проверка результата
    print("\n📊 ШАГ 6: Проверка результата...")
    if bot_mock.received_signals:
        print(f"✅✅✅ УСПЕХ! Бот получил {len(bot_mock.received_signals)} сигналов")
        print("\nПолученный сигнал:")
        print("-" * 80)
        print(bot_mock.received_signals[0])
        print("-" * 80)
    else:
        print("❌ ПРОБЛЕМА: Бот НЕ получил сигнал!")
        print("\n🔍 Возможные причины:")
        print("1. SignalManager отфильтровал сигнал")
        print("2. Ошибка в методе process_signal")
        print("3. Подписчик не был вызван")
        print("\nПроверь логи SignalManager выше!")
    
    # ШАГ 7: Проверка статистики SignalManager
    print("\n📈 ШАГ 7: Статистика SignalManager...")
    try:
        stats = signal_manager.get_stats()
        print(f"Всего обработано сигналов: {stats.get('total_signals_processed', 0)}")
        print(f"Принято сигналов: {stats.get('signals_accepted', 0)}")
        print(f"Отклонено сигналов: {stats.get('signals_rejected', 0)}")
        
        if stats.get('signals_rejected', 0) > 0:
            print("\n⚠️ Сигналы отклоняются! Причины:")
            rejection_reasons = stats.get('rejection_reasons', {})
            for reason, count in rejection_reasons.items():
                print(f"   - {reason}: {count}")
    except Exception as e:
        print(f"⚠️ Не удалось получить статистику: {e}")
    
    print("\n" + "=" * 80)
    print("🏁 ТЕСТ ЗАВЕРШЕН")
    print("=" * 80)


if __name__ == "__main__":
    print("🧪 Запуск диагностического теста...\n")
    asyncio.run(test_signal_chain())
