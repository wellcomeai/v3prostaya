import asyncio
import logging
from telegram_bot import TelegramBot
from config import Config

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main():
    """Главная функция приложения"""
    try:
        # Создаем экземпляр бота
        bot = TelegramBot(Config.TELEGRAM_BOT_TOKEN)
        
        logger.info("🚀 Запуск Bybit Trading Bot...")
        
        # Запускаем бота
        await bot.run()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
