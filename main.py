import asyncio
import logging
import sys
import os
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from telegram_bot import TelegramBot
from websocket_strategy import WebSocketStrategy  # 🆕 НОВЫЙ ИМПОРТ
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
websocket_strategy = None  # 🆕 НОВАЯ ГЛОБАЛЬНАЯ ПЕРЕМЕННАЯ

async def health_check(request):
    """Health check endpoint для Render и мониторинга"""
    try:
        # Проверяем что бот существует и готов
        if bot_instance and bot_instance.bot:
            bot_info = await bot_instance.bot.get_me()
            
            # 🆕 НОВОЕ: Проверяем статус WebSocket стратегии
            websocket_status = "active" if (websocket_strategy and websocket_strategy.running) else "inactive"
            subscribers_count = len(bot_instance.signal_subscribers) if bot_instance else 0
            
            return web.json_response({
                "status": "ok",
                "bot_username": bot_info.username,
                "bot_id": bot_info.id,
                "websocket_strategy": websocket_status,
                "signal_subscribers": subscribers_count,
                "timestamp": asyncio.get_event_loop().time()
            })
        else:
            return web.json_response({
                "status": "initializing",
                "message": "Bot is starting up"
            }, status=503)
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

async def on_startup(bot) -> None:
    """Действия при запуске - устанавливаем webhook"""
    webhook_url = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"
    logger.info(f"🔗 Настройка webhook: {webhook_url}")
    
    try:
        # Сначала удаляем старый webhook если есть
        logger.info("🔄 Удаляю старый webhook...")
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Небольшая пауза для корректного удаления
        await asyncio.sleep(2)
        
        # Устанавливаем новый webhook
        logger.info("🔗 Устанавливаю новый webhook...")
        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True
        )
        
        # Проверяем что webhook установлен
        webhook_info = await bot.get_webhook_info()
        logger.info(f"✅ Webhook установлен: {webhook_info.url}")
        
        if webhook_info.pending_update_count > 0:
            logger.warning(f"⚠️ Ожидающих обновлений: {webhook_info.pending_update_count}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")
        raise

async def on_shutdown(bot) -> None:
    """Действия при остановке"""
    try:
        logger.info("🔄 Остановка бота...")
        
        # Получаем информацию о webhook перед удалением
        try:
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                logger.info(f"🗑️ Удаляю webhook: {webhook_info.url}")
                await bot.delete_webhook()
                await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при удалении webhook: {e}")
        
        logger.info("✅ Бот остановлен")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при остановке: {e}")

async def cleanup_resources():
    """Освобождение всех ресурсов"""
    global bot_instance, websocket_strategy
    
    try:
        # 🆕 НОВОЕ: Останавливаем WebSocket стратегию
        if websocket_strategy:
            logger.info("🔄 Остановка WebSocket стратегии...")
            await websocket_strategy.stop()
            logger.info("✅ WebSocket стратегия остановлена")
        
        if bot_instance:
            # Закрываем HTTP сессии в BybitClient
            if hasattr(bot_instance, 'bybit_client'):
                await bot_instance.bybit_client.close()
                logger.info("✅ BybitClient сессии закрыты")
            
            # Закрываем бота
            await bot_instance.close()
            logger.info("✅ Telegram бот закрыт")
            
    except Exception as e:
        logger.error(f"❌ Ошибка освобождения ресурсов: {e}")

async def create_app():
    """Создание веб-приложения"""
    global bot_instance, websocket_strategy
    
    # Создаем экземпляр бота
    bot_instance = TelegramBot(Config.TELEGRAM_BOT_TOKEN)
    
    # 🆕 НОВОЕ: Создаем и запускаем WebSocket стратегию
    try:
        logger.info("🚀 Инициализация WebSocket стратегии...")
        websocket_strategy = WebSocketStrategy(bot_instance)
        
        # Запускаем стратегию в фоне
        logger.info("⚡ Запуск WebSocket стратегии в фоновом режиме...")
        asyncio.create_task(websocket_strategy.start())
        
        # Небольшая пауза для инициализации
        await asyncio.sleep(2)
        
        logger.info("✅ WebSocket стратегия инициализирована")
        
    except Exception as e:
        logger.error(f"💥 Ошибка запуска WebSocket стратегии: {e}")
        logger.warning("⚠️ Продолжаем работу без WebSocket стратегии")
        # Продолжаем работу без стратегии - бот все равно будет работать
        websocket_strategy = None
    
    # Устанавливаем webhook при запуске
    await on_startup(bot_instance.bot)
    
    # Создаем веб-приложение
    app = web.Application()
    
    # Health check endpoint
    app.router.add_get("/health", health_check)
    
    # Root endpoint для проверки
    async def root_handler(request):
        # 🆕 НОВОЕ: Добавляем информацию о WebSocket стратегии
        websocket_info = {
            "websocket_strategy_active": websocket_strategy.running if websocket_strategy else False,
            "signal_subscribers": len(bot_instance.signal_subscribers) if bot_instance else 0
        }
        
        return web.json_response({
            "message": "Bybit Trading Bot v2.1 is running",
            "features": [
                "REST API Market Analysis",
                "OpenAI Integration", 
                "WebSocket Real-time Signals",
                "Telegram Notifications"
            ],
            "webhook_path": WEBHOOK_PATH,
            "status": "active",
            **websocket_info
        })
    
    app.router.add_get("/", root_handler)
    
    # 🆕 НОВОЕ: Дополнительный endpoint для статуса сигналов
    async def signals_status_handler(request):
        """Endpoint для проверки статуса торговых сигналов"""
        try:
            if not bot_instance or not websocket_strategy:
                return web.json_response({
                    "status": "inactive",
                    "message": "WebSocket strategy not initialized"
                }, status=503)
            
            return web.json_response({
                "websocket_strategy": {
                    "status": "active" if websocket_strategy.running else "inactive",
                    "symbol": Config.SYMBOL,
                    "testnet": Config.BYBIT_TESTNET,
                    "min_signal_strength": websocket_strategy.min_signal_strength,
                    "signal_cooldown_minutes": websocket_strategy.signal_cooldown.total_seconds() / 60,
                    "price_data_points": len(websocket_strategy.market_data.prices) if websocket_strategy.market_data else 0,
                    "last_signals_count": len(websocket_strategy.last_signals) if websocket_strategy.last_signals else 0
                },
                "subscribers": {
                    "count": len(bot_instance.signal_subscribers),
                    "active": True
                },
                "market_data": {
                    "current_price": websocket_strategy.market_data.get_current_price() if websocket_strategy and websocket_strategy.market_data else 0,
                    "data_available": len(websocket_strategy.market_data.prices) > 0 if websocket_strategy and websocket_strategy.market_data else False
                }
            })
            
        except Exception as e:
            logger.error(f"❌ Ошибка в signals_status: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    app.router.add_get("/signals/status", signals_status_handler)
    
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
    
    # Настраиваем graceful shutdown
    async def cleanup_handler(app):
        await cleanup_resources()
    
    app.on_cleanup.append(cleanup_handler)
    
    return app

async def main():
    """Главная функция приложения"""
    
    try:
        logger.info("🚀 Запуск Bybit Trading Bot v2.1 (webhook режим)...")
        logger.info(f"🔧 Порт: {WEB_SERVER_PORT}")
        logger.info(f"🔧 Webhook URL: {BASE_WEBHOOK_URL}{WEBHOOK_PATH}")
        logger.info(f"🔧 Testnet: {Config.BYBIT_TESTNET}")
        logger.info(f"🔧 Symbol: {Config.SYMBOL}")
        
        # 🆕 НОВОЕ: Логируем WebSocket настройки
        logger.info("🚨 WebSocket Features:")
        logger.info("   • Real-time price monitoring")
        logger.info("   • Orderbook analysis")
        logger.info("   • Trade flow analysis")
        logger.info("   • Momentum detection")
        logger.info("   • Automatic signal distribution")
        
        # Создаем приложение
        app = await create_app()
        
        # Запускаем веб-сервер
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
        await site.start()
        
        logger.info(f"🌐 Веб-сервер запущен на {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
        logger.info("🤖 Telegram бот готов к работе через webhook!")
        logger.info(f"🏥 Health check доступен по адресу: {BASE_WEBHOOK_URL}/health")
        logger.info(f"📊 Статус сигналов: {BASE_WEBHOOK_URL}/signals/status")
        
        # Проверяем подключение к Bybit
        try:
            if bot_instance and bot_instance.bybit_client:
                connection_ok = await bot_instance.bybit_client.check_connection()
                if connection_ok:
                    logger.info("✅ Подключение к Bybit API успешно")
                else:
                    logger.warning("⚠️ Проблемы с подключением к Bybit API")
        except Exception as e:
            logger.error(f"❌ Ошибка проверки Bybit API: {e}")
        
        # 🆕 НОВОЕ: Проверяем статус WebSocket стратегии
        if websocket_strategy:
            await asyncio.sleep(5)  # Ждем инициализации WebSocket
            if websocket_strategy.running:
                logger.info("🚨 ✅ WebSocket стратегия торговых сигналов активна")
                logger.info(f"📊 Мониторинг символа: {Config.SYMBOL}")
                logger.info(f"🔧 Режим: {'Testnet' if Config.BYBIT_TESTNET else 'Mainnet'}")
            else:
                logger.warning("⚠️ WebSocket стратегия не активна")
        else:
            logger.warning("⚠️ WebSocket стратегия не инициализирована")
        
        # Держим приложение запущенным
        try:
            while True:
                await asyncio.sleep(3600)  # Проверяем каждый час
                
                # 🆕 НОВОЕ: Периодическая проверка WebSocket стратегии
                if websocket_strategy and not websocket_strategy.running:
                    logger.warning("⚠️ WebSocket стратегия остановилась, перезапуск...")
                    try:
                        await websocket_strategy.start()
                        logger.info("✅ WebSocket стратегия перезапущена")
                    except Exception as e:
                        logger.error(f"❌ Не удалось перезапустить WebSocket стратегию: {e}")
                
                # Логируем статистику
                if bot_instance:
                    subscribers_count = len(bot_instance.signal_subscribers)
                    logger.info(f"📊 Статистика: {subscribers_count} подписчиков на сигналы")
                
        except asyncio.CancelledError:
            logger.info("📡 Получен сигнал отмены")
        except KeyboardInterrupt:
            logger.info("📡 Получен сигнал прерывания")
        finally:
            logger.info("🔄 Начинаю процедуру остановки...")
            
            # Останавливаем webhook
            if bot_instance:
                await on_shutdown(bot_instance.bot)
            
            # Закрываем runner
            await runner.cleanup()
            
            # Освобождаем ресурсы
            await cleanup_resources()
            
            logger.info("🏁 Приложение полностью остановлено")
            
    except Exception as e:
        logger.error(f"💥 Критическая ошибка в main(): {e}")
        
        # Аварийная очистка ресурсов
        try:
            await cleanup_resources()
        except:
            pass
            
        raise

def run_app():
    """Запуск приложения с корректной обработкой исключений"""
    try:
        # Для Python 3.7+ используем asyncio.run
        if hasattr(asyncio, 'run'):
            asyncio.run(main())
        else:
            # Для более старых версий
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("🔴 Приложение остановлено пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка приложения: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_app()
