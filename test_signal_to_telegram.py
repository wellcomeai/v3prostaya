"""
Тестовый скрипт для проверки отправки сигналов в Telegram

Проверяет всю цепочку:
1. Создание фиктивного сигнала
2. Прохождение через стратегию
3. Отправка в Telegram

Usage:
    python test_signal_to_telegram.py --mode simple
    python test_signal_to_telegram.py --mode full
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== РЕЖИМ 1: ПРОСТОЙ (только TradingSignal → Telegram) ====================

async def test_simple_signal():
    """
    🎯 Простой тест: создать TradingSignal и отправить в Telegram
    Минимальная проверка без стратегий
    """
    logger.info("=" * 80)
    logger.info("🧪 РЕЖИМ 1: Простой тест (TradingSignal → Telegram)")
    logger.info("=" * 80)
    
    try:
        # Импортируем необходимые модули
        from strategies.base_strategy import TradingSignal, SignalType, SignalStrength
        from telegram_bot import TelegramBot
        from config import Config
        
        # Получаем токен из Config
        telegram_token = Config.TELEGRAM_BOT_TOKEN
        
        # Инициализируем Telegram бота
        telegram_bot = TelegramBot(
            token=telegram_token,
            repository=None,
            ta_context_manager=None
        )
        
        logger.info("✅ Модули импортированы")
        
        # Создаем фиктивный сигнал
        signal = TradingSignal(
            symbol="TESTUSDT",
            signal_type=SignalType.STRONG_BUY,
            strength=SignalStrength.STRONG,
            confidence=0.95,
            current_price=50000.0,
            timestamp=datetime.now(),
            strategy_name="TestStrategy",
            reasons=[
                "🧪 Тестовый сигнал",
                "💥 Пробой через 49500",
                "📊 Консолидация 24 часа",
                "✅ Все условия выполнены"
            ]
        )
        
        # Добавляем параметры ордера
        signal.stop_loss = 48000.0
        signal.take_profit = 56000.0
        signal.position_size_recommendation = 0.03
        
        # Добавляем технические индикаторы
        signal.add_technical_indicator("breakout_level", 49500, "Resistance @ 49500")
        signal.add_technical_indicator("risk_reward_ratio", 3.0, "R:R = 3:1")
        
        logger.info(f"✅ Сигнал создан: {signal.symbol} {signal.signal_type.value}")
        logger.info(f"   • Price: {signal.current_price}")
        logger.info(f"   • SL: {signal.stop_loss}")
        logger.info(f"   • TP: {signal.take_profit}")
        logger.info(f"   • Confidence: {signal.confidence*100:.0f}%")
        
        # Формируем сообщение для Telegram
        logger.info("\n📤 Отправка в Telegram...")
        
        # Формируем красивое сообщение
        signal_emoji = "🚀" if "BUY" in signal.signal_type.value else "⚠️"
        signal_text = "ПОКУПКУ" if "BUY" in signal.signal_type.value else "ПРОДАЖУ"
        
        sl_percent = ((signal.stop_loss - signal.current_price) / signal.current_price * 100)
        tp_percent = ((signal.take_profit - signal.current_price) / signal.current_price * 100)
        
        message = f"""{signal_emoji} <b>🧪 ТЕСТОВЫЙ СИГНАЛ НА {signal_text}</b>

💰 <b>{signal.symbol}</b>
Цена: {signal.current_price:,.2f}

📊 <b>Параметры входа:</b>
• Stop Loss: {signal.stop_loss:,.2f} ({sl_percent:+.1f}%)
• Take Profit: {signal.take_profit:,.2f} ({tp_percent:+.1f}%)
• Риск/Прибыль: 3:1
• Размер позиции: {signal.position_size_recommendation*100:.1f}%

🎯 <b>Причины сигнала:</b>
• 🧪 Тестовый сигнал
• 💥 Пробой через 49500
• 📊 Консолидация 24 часа
• ✅ Все условия выполнены

💪 <b>Уверенность:</b> {signal.confidence*100:.0f}%

⚠️ <i>Это тестовый сигнал для проверки системы!</i>
"""
        
        await telegram_bot.broadcast_signal(message)
        
        logger.info("✅ Сигнал отправлен в Telegram!")
        
        # Закрываем бота
        await telegram_bot.close()
        
        logger.info("\n🎉 ТЕСТ ПРОЙДЕН: Проверьте Telegram бота!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка в простом тесте: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


# ==================== РЕЖИМ 2: ПОЛНЫЙ (через стратегию) ====================

def create_fake_candles(
    symbol: str,
    interval: str,
    count: int,
    base_price: float = 50000.0
) -> List[Dict]:
    """Создание фиктивных свечей"""
    candles = []
    current_time = datetime.now()
    
    # Интервалы в минутах
    interval_minutes = {
        "1m": 1,
        "5m": 5,
        "1h": 60,
        "1d": 1440
    }
    
    delta_minutes = interval_minutes.get(interval, 5)
    
    for i in range(count):
        timestamp = current_time - timedelta(minutes=delta_minutes * (count - i))
        
        # Небольшие колебания цены
        variation = (i % 10 - 5) * 10
        open_price = base_price + variation
        close_price = base_price + variation + 5
        high_price = max(open_price, close_price) + 10
        low_price = min(open_price, close_price) - 10
        
        candle = {
            "timestamp": timestamp,
            "open_price": open_price,
            "high_price": high_price,
            "low_price": low_price,
            "close_price": close_price,
            "volume": 1000000.0,
            "symbol": symbol,
            "interval": interval
        }
        
        candles.append(candle)
    
    return candles


def create_fake_ta_context(symbol: str, current_price: float):
    """Создание фиктивного технического контекста"""
    
    class FakeLevel:
        def __init__(self, price, level_type, strength):
            self.price = price
            self.level_type = level_type
            self.strength = strength
            self.touches = 5
            self.is_strong = strength >= 0.8
            self.last_touch = datetime.now() - timedelta(days=3)
    
    class FakeATR:
        def __init__(self):
            self.calculated_atr = current_price * 0.02
            self.current_range_used = 0.3  # 30% использовано
    
    class FakeContext:
        def __init__(self):
            # Уровни: сопротивление чуть выше, поддержка чуть ниже
            self.levels_d1 = [
                FakeLevel(current_price * 0.99, "support", 0.85),      # Поддержка -1%
                FakeLevel(current_price * 1.01, "resistance", 0.90),   # Сопротивление +1%
            ]
            self.atr_data = FakeATR()
    
    return FakeContext()


async def test_full_pipeline():
    """
    🎯 Полный тест: эмуляция данных → стратегия → сигнал → Telegram
    Проверяет всю цепочку как в оркестраторе
    """
    logger.info("=" * 80)
    logger.info("🧪 РЕЖИМ 2: Полный тест (данные → стратегия → Telegram)")
    logger.info("=" * 80)
    
    try:
        # Импортируем модули
        from strategies.breakout_strategy import BreakoutStrategy
        from telegram_bot import TelegramBot
        from config import Config
        
        # Получаем токен из Config
        telegram_token = Config.TELEGRAM_BOT_TOKEN
        
        # Инициализируем Telegram бота
        telegram_bot = TelegramBot(
            token=telegram_token,
            repository=None,
            ta_context_manager=None
        )
        
        logger.info("✅ Модули импортированы")
        
        # Создаем фиктивные данные
        symbol = "TESTUSDT"
        current_price = 50000.0
        
        logger.info(f"\n📊 Создание фиктивных данных для {symbol}...")
        
        candles_1m = create_fake_candles(symbol, "1m", 100, current_price)
        candles_5m = create_fake_candles(symbol, "5m", 50, current_price)
        candles_1h = create_fake_candles(symbol, "1h", 24, current_price)
        candles_1d = create_fake_candles(symbol, "1d", 180, current_price)
        
        logger.info(f"   • 1m свечей: {len(candles_1m)}")
        logger.info(f"   • 5m свечей: {len(candles_5m)}")
        logger.info(f"   • 1h свечей: {len(candles_1h)}")
        logger.info(f"   • 1d свечей: {len(candles_1d)}")
        
        # Создаем фиктивный технический контекст
        ta_context = create_fake_ta_context(symbol, current_price)
        
        logger.info(f"\n🔧 Создание технического контекста...")
        logger.info(f"   • Уровней D1: {len(ta_context.levels_d1)}")
        logger.info(f"   • ATR: {ta_context.atr_data.calculated_atr:.2f}")
        logger.info(f"   • ATR использовано: {ta_context.atr_data.current_range_used*100:.0f}%")
        
        # Создаем стратегию с МЯГКИМИ параметрами
        logger.info(f"\n💡 Создание стратегии...")
        
        strategy = BreakoutStrategy(
            symbol=symbol,
            repository=None,
            ta_context_manager=None,
            # МЯГКИЕ параметры для теста
            require_compression=False,
            require_consolidation=False,
            min_signal_strength=0.1,  # Минимальный порог
        )
        
        logger.info(f"   • Стратегия: {strategy.name}")
        logger.info(f"   • require_compression: {strategy.require_compression}")
        logger.info(f"   • require_consolidation: {strategy.require_consolidation}")
        
        # Запускаем анализ
        logger.info(f"\n🔍 Запуск анализа...")
        
        signal = await strategy.analyze_with_data(
            symbol=symbol,
            candles_1m=candles_1m,
            candles_5m=candles_5m,
            candles_1h=candles_1h,
            candles_1d=candles_1d,
            ta_context=ta_context
        )
        
        if signal:
            logger.info(f"✅ Сигнал создан стратегией!")
            logger.info(f"   • Symbol: {signal.symbol}")
            logger.info(f"   • Type: {signal.signal_type.value}")
            logger.info(f"   • Strength: {signal.strength.value}")
            logger.info(f"   • Confidence: {signal.confidence*100:.0f}%")
            logger.info(f"   • Price: {signal.current_price}")
            logger.info(f"   • SL: {signal.stop_loss}")
            logger.info(f"   • TP: {signal.take_profit}")
            logger.info(f"   • Reasons: {len(signal.reasons)}")
            
            # Отправляем в Telegram
            logger.info(f"\n📤 Отправка в Telegram...")
            
            # Формируем красивое сообщение
            signal_emoji = "🚀" if "BUY" in signal.signal_type.value else "⚠️"
            signal_text = "ПОКУПКУ" if "BUY" in signal.signal_type.value else "ПРОДАЖУ"
            
            sl_percent = ((signal.stop_loss - signal.current_price) / signal.current_price * 100) if signal.stop_loss else 0
            tp_percent = ((signal.take_profit - signal.current_price) / signal.current_price * 100) if signal.take_profit else 0
            
            # Собираем причины
            reasons_text = "\n".join(f"• {reason}" for reason in signal.reasons[:4])
            
            message = f"""{signal_emoji} <b>СИГНАЛ НА {signal_text}</b>

💰 <b>{signal.symbol}</b>
Цена: {signal.current_price:,.2f}

📊 <b>Параметры входа:</b>
• Stop Loss: {signal.stop_loss:,.2f} ({sl_percent:+.1f}%)
• Take Profit: {signal.take_profit:,.2f} ({tp_percent:+.1f}%)
• Размер позиции: {signal.position_size_recommendation*100:.1f}%

🎯 <b>Причины сигнала:</b>
{reasons_text}

💪 <b>Уверенность:</b> {signal.confidence*100:.0f}%
🎭 <b>Стратегия:</b> {signal.strategy_name}

⚠️ <i>Тестовый сигнал через {strategy.name}</i>
"""
            
            await telegram_bot.broadcast_signal(message)
            
            logger.info("✅ Сигнал отправлен в Telegram!")
            
            # Закрываем бота
            await telegram_bot.close()
            
            logger.info("\n🎉 ТЕСТ ПРОЙДЕН: Проверьте Telegram бота!")
            
            return True
        else:
            logger.warning("⚠️ Стратегия не создала сигнал!")
            logger.warning("   Возможно, условия все равно слишком жесткие")
            logger.warning("   Попробуйте режим --mode simple")
            
            # Закрываем бота
            await telegram_bot.close()
            
            return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка в полном тесте: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


# ==================== MAIN ====================

async def main():
    """Главная функция"""
    
    # Парсим аргументы
    mode = "simple"  # По умолчанию
    
    if len(sys.argv) > 1:
        if "--mode" in sys.argv:
            idx = sys.argv.index("--mode")
            if idx + 1 < len(sys.argv):
                mode = sys.argv[idx + 1]
    
    logger.info(f"🚀 Запуск теста в режиме: {mode}")
    
    if mode == "simple":
        success = await test_simple_signal()
    elif mode == "full":
        success = await test_full_pipeline()
    else:
        logger.error(f"❌ Неизвестный режим: {mode}")
        logger.info("Доступные режимы: simple, full")
        return
    
    if success:
        logger.info("\n" + "=" * 80)
        logger.info("✅ ТЕСТ ЗАВЕРШЕН УСПЕШНО")
        logger.info("=" * 80)
    else:
        logger.info("\n" + "=" * 80)
        logger.info("❌ ТЕСТ ЗАВЕРШЕН С ОШИБКАМИ")
        logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
