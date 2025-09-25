import asyncio
import logging
import signal
import sys
import os
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from telegram_bot import TelegramBot
from config import Config

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройки webhook
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 8080))
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "bybit_trading_bot_secret_2025"

# URL вашего сервера
BASE_WEBHOOK_URL = "https://bybitmybot.onrender.com"

# Глобальные переменные
bot_instance = None
app_runner = None

async def on_startup(bot) -> None:
    """Действия при запуске - устанавливаем webhook"""
    webhook_url = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"
    logger.info(f"🔗 Устанавливаю webhook: {webhook_url}")
    
    try:
        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True  # Убираем накопившиеся обновления
        )
        logger.info("✅ Webhook установлен успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")

async def on_shutdown(bot) -> None:
    """Действия при остановке - удаляем webhook"""
    try:
        logger.info("🔄 Удаляю webhook...")
        await bot.delete_webhook()
        logger.info("✅ Webhook удален")
    except Exception as e:
        logger.error(f"❌ Ошибка удаления webhook: {e}")

async def shutdown_handler():
    """Обработчик корректного завершения"""
    global bot_instance, app_runner
    
    if bot_instance:
        logger.info("🔄 Останавливаю бота...")
        
        # Удаляем webhook
        await on_shutdown(bot_instance.bot)
        
        # Закрываем бота
        await bot_instance.close()
        logger.info("✅ Бот остановлен")
    
    if app_runner:
        logger.info("🔄 Останавливаю веб-сервер...")
        await app_runner.cleanup()
        logger.info("✅ Веб-сервер остановлен")

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    logger.info(f"📡 Получен сигнал {signum}, завершаю работу...")
    asyncio.create_task(shutdown_handler())
    sys.exit(0)

async def main():
    """Главная функция приложения"""
    global bot_instance, app_runner
    
    try:
        # Регистрируем обработчики сигналов
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Создаем экземпляр бота
        bot_instance = TelegramBot(Config.TELEGRAM_BOT_TOKEN)
        
        logger.info("🚀 Запуск Bybit Trading Bot (webhook режим)...")
        
        # Устанавливаем webhook при запуске
        await on_startup(bot_instance.bot)
        
        # Создаем веб-приложение для webhook
        app = web.Application()
        
        # Создаем обработчик webhook запросов
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=bot_instance.dp,
            bot=bot_instance.bot,
            secret_token=WEBHOOK_SECRET
        )
        
        # Регистрируем webhook маршрут
        webhook_requests_handler.register(app, path=WEBHOOK_PATH)
        
        # Настраиваем приложение
        setup_application(app, bot_instance.dp, bot=bot_instance.bot)
        
        # Запускаем веб-сервер
        app_runner = web.AppRunner(app)
        await app_runner.setup()
        
        site = web.TCPSite(app_runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
        await site.start()
        
        logger.info(f"🌐 Веб-сервер запущен на {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
        logger.info(f"🔗 Webhook URL: {BASE_WEBHOOK_URL}{WEBHOOK_PATH}")
        logger.info("🤖 Telegram бот готов к работе через webhook!")
        
        # Держим приложение запущенным
        try:
            await asyncio.Future()  # Бесконечное ожидание
        except KeyboardInterrupt:
            logger.info("📡 Получен сигнал прерывания")
            await shutdown_handler()
            
    except KeyboardInterrupt:
        logger.info("📡 Получен сигнал прерывания")
        await shutdown_handler()
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")
        if bot_instance or app_runner:
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
