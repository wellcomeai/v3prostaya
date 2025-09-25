import asyncio
import logging
import signal
import sys
from telegram_bot import TelegramBot
from config import Config

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальная переменная для бота
bot_instance = None

async def shutdown_handler():
    """Обработчик корректного завершения"""
    global bot_instance
    if bot_instance:
        logger.info("🔄 Останавливаю бота...")
        await bot_instance.close()
        logger.info("✅ Бот остановлен")

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    logger.info(f"📡 Получен сигнал {signum}, завершаю работу...")
    asyncio.create_task(shutdown_handler())
    sys.exit(0)

async def main():
    """Главная функция приложения"""
    global bot_instance
    
    try:
        # Регистрируем обработчики сигналов
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Создаем экземпляр бота
        bot_instance = TelegramBot(Config.TELEGRAM_BOT_TOKEN)
        
        logger.info("🚀 Запуск Bybit Trading Bot (aiogram)...")
        
        # Запускаем бота
        await bot_instance.run()
        
    except KeyboardInterrupt:
        logger.info("📡 Получен сигнал прерывания")
        await shutdown_handler()
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")
        if bot_instance:
            await shutdown_handler()
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🔴 Приложение остановлено пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        sys.exit(1)
