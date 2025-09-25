import asyncio
import logging
import sys
import os
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from telegram_bot import TelegramBot
from config import Config

# 🆕 НОВЫЕ ИМПОРТЫ - Модульная архитектура
from market_data import MarketDataManager
from core import SignalManager, StrategyOrchestrator
from core.data_models import SystemConfig, StrategyConfig, create_default_system_config
from strategies import MomentumStrategy

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

# Глобальные переменные для новой архитектуры
bot_instance = None
market_data_manager = None
signal_manager = None
strategy_orchestrator = None
system_config = None

async def health_check(request):
    """Health check endpoint для Render и мониторинга"""
    try:
        # Проверяем что бот существует и готов
        if bot_instance and bot_instance.bot:
            bot_info = await bot_instance.bot.get_me()
            
            # 🆕 НОВОЕ: Проверяем статус новой архитектуры
            health_status = {
                "status": "ok",
                "bot_username": bot_info.username,
                "bot_id": bot_info.id,
                "timestamp": asyncio.get_event_loop().time(),
                "signal_subscribers": len(bot_instance.signal_subscribers) if bot_instance else 0,
                "components": {
                    "market_data_manager": market_data_manager.get_health_status()["overall_status"] if market_data_manager else "inactive",
                    "signal_manager": "running" if signal_manager and signal_manager.is_running else "inactive",
                    "strategy_orchestrator": strategy_orchestrator.status.value if strategy_orchestrator else "inactive",
                    "strategies_active": strategy_orchestrator._count_active_strategies() if strategy_orchestrator else 0
                }
            }
            
            return web.json_response(health_status)
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
    """Освобождение всех ресурсов новой архитектуры"""
    global bot_instance, market_data_manager, signal_manager, strategy_orchestrator
    
    try:
        # Останавливаем оркестратор стратегий
        if strategy_orchestrator:
            logger.info("🔄 Остановка StrategyOrchestrator...")
            await strategy_orchestrator.stop()
            logger.info("✅ StrategyOrchestrator остановлен")
        
        # Останавливаем менеджер сигналов
        if signal_manager:
            logger.info("🔄 Остановка SignalManager...")
            await signal_manager.stop()
            logger.info("✅ SignalManager остановлен")
        
        # Останавливаем менеджер данных
        if market_data_manager:
            logger.info("🔄 Остановка MarketDataManager...")
            await market_data_manager.stop()
            logger.info("✅ MarketDataManager остановлен")
        
        # Закрываем Telegram бот
        if bot_instance:
            await bot_instance.close()
            logger.info("✅ Telegram бот закрыт")
            
    except Exception as e:
        logger.error(f"❌ Ошибка освобождения ресурсов: {e}")

async def initialize_trading_system():
    """Инициализация торговой системы"""
    global market_data_manager, signal_manager, strategy_orchestrator, system_config
    
    try:
        logger.info("🚀 Инициализация торговой системы...")
        
        # 1. Создаем конфигурацию системы
        system_config = create_default_system_config()
        system_config.trading_mode = system_config.trading_mode.PAPER  # Тестовый режим
        system_config.bybit_testnet = Config.BYBIT_TESTNET
        system_config.default_symbol = Config.SYMBOL
        
        # 2. Инициализируем менеджер рыночных данных
        logger.info("📊 Инициализация MarketDataManager...")
        market_data_manager = MarketDataManager(
            symbol=Config.SYMBOL,
            testnet=Config.BYBIT_TESTNET,
            enable_websocket=True,
            enable_rest_api=True
        )
        
        # 3. Инициализируем менеджер сигналов
        logger.info("🎛️ Инициализация SignalManager...")
        signal_manager = SignalManager(
            max_queue_size=1000,
            notification_settings=system_config.notification_settings
        )
        
        # Подписываем Telegram бота на сигналы
        if bot_instance:
            signal_manager.add_subscriber(bot_instance.broadcast_signal)
            logger.info("📡 Telegram бот подписан на торговые сигналы")
        
        # 4. Инициализируем оркестратор стратегий
        logger.info("🎭 Инициализация StrategyOrchestrator...")
        strategy_orchestrator = StrategyOrchestrator(
            market_data_manager=market_data_manager,
            signal_manager=signal_manager,
            system_config=system_config,
            analysis_interval=30.0,  # 30 секунд между анализами
            max_concurrent_analyses=3,
            enable_performance_monitoring=True
        )
        
        # 5. Запускаем все компоненты
        logger.info("▶️ Запуск торговой системы...")
        
        # Запускаем менеджер данных
        market_data_started = await market_data_manager.start()
        if not market_data_started:
            raise Exception("Не удалось запустить MarketDataManager")
        
        # Запускаем менеджер сигналов
        await signal_manager.start()
        
        # Запускаем оркестратор стратегий
        orchestrator_started = await strategy_orchestrator.start()
        if not orchestrator_started:
            raise Exception("Не удалось запустить StrategyOrchestrator")
        
        logger.info("✅ Торговая система запущена успешно!")
        logger.info(f"📊 MarketDataManager: {market_data_manager}")
        logger.info(f"🎛️ SignalManager: {signal_manager}")
        logger.info(f"🎭 StrategyOrchestrator: {strategy_orchestrator}")
        
        return True
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка инициализации торговой системы: {e}")
        return False

async def create_app():
    """Создание веб-приложения"""
    global bot_instance
    
    # Создаем экземпляр бота
    bot_instance = TelegramBot(Config.TELEGRAM_BOT_TOKEN)
    
    # 🆕 НОВОЕ: Инициализируем торговую систему вместо старой WebSocket стратегии
    try:
        logger.info("🚀 Инициализация новой торговой системы...")
        trading_system_started = await initialize_trading_system()
        
        if trading_system_started:
            logger.info("🚨 ✅ Новая торговая система активна")
            logger.info(f"📊 Мониторинг символа: {Config.SYMBOL}")
            logger.info(f"🔧 Режим: {'Testnet' if Config.BYBIT_TESTNET else 'Mainnet'}")
        else:
            logger.warning("⚠️ Торговая система не активна")
            
    except Exception as e:
        logger.error(f"💥 Ошибка запуска торговой системы: {e}")
        logger.warning("⚠️ Продолжаем работу без торговой системы")
        # Продолжаем работу без торговой системы - бот все равно будет работать
    
    # Устанавливаем webhook при запуске
    await on_startup(bot_instance.bot)
    
    # Создаем веб-приложение
    app = web.Application()
    
    # Health check endpoint
    app.router.add_get("/health", health_check)
    
    # Root endpoint для проверки
    async def root_handler(request):
        # 🆕 НОВОЕ: Информация о новой торговой системе
        trading_system_info = {
            "trading_system_active": bool(strategy_orchestrator and strategy_orchestrator.is_running),
            "market_data_status": market_data_manager.get_health_status()["overall_status"] if market_data_manager else "inactive",
            "active_strategies": strategy_orchestrator._count_active_strategies() if strategy_orchestrator else 0,
            "signal_subscribers": len(bot_instance.signal_subscribers) if bot_instance else 0
        }
        
        return web.json_response({
            "message": "Bybit Trading Bot v2.1 - Modular Architecture",
            "features": [
                "Modular Market Data Management",
                "Strategy Orchestration System", 
                "Advanced Signal Management",
                "REST API + WebSocket Integration",
                "OpenAI Integration", 
                "Telegram Notifications"
            ],
            "webhook_path": WEBHOOK_PATH,
            "status": "active",
            **trading_system_info
        })
    
    app.router.add_get("/", root_handler)
    
    # 🆕 НОВОЕ: Дополнительный endpoint для статуса торговой системы
    async def trading_system_status_handler(request):
        """Endpoint для проверки статуса торговой системы"""
        try:
            if not market_data_manager or not signal_manager or not strategy_orchestrator:
                return web.json_response({
                    "status": "inactive",
                    "message": "Trading system not initialized"
                }, status=503)
            
            return web.json_response({
                "market_data_manager": market_data_manager.get_stats(),
                "signal_manager": signal_manager.get_stats(),
                "strategy_orchestrator": strategy_orchestrator.get_stats(),
                "system_health": {
                    "market_data": market_data_manager.get_health_status(),
                    "strategies": strategy_orchestrator.get_health_status()
                }
            })
            
        except Exception as e:
            logger.error(f"❌ Ошибка в trading_system_status: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    app.router.add_get("/trading/status", trading_system_status_handler)
    
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
        logger.info("🚀 Запуск Bybit Trading Bot v2.1 (modular architecture)...")
        logger.info(f"🔧 Порт: {WEB_SERVER_PORT}")
        logger.info(f"🔧 Webhook URL: {BASE_WEBHOOK_URL}{WEBHOOK_PATH}")
        logger.info(f"🔧 Testnet: {Config.BYBIT_TESTNET}")
        logger.info(f"🔧 Symbol: {Config.SYMBOL}")
        
        # 🆕 НОВОЕ: Логируем новую архитектуру
        logger.info("🏗️ Modular Architecture Features:")
        logger.info("   • MarketDataManager с WebSocket + REST API")
        logger.info("   • StrategyOrchestrator для управления стратегиями")
        logger.info("   • SignalManager для фильтрации и рассылки сигналов")
        logger.info("   • Импульсная MomentumStrategy")
        logger.info("   • Автоматическая рассылка торговых сигналов")
        
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
        logger.info(f"📊 Статус торговой системы: {BASE_WEBHOOK_URL}/trading/status")
        
        # Держим приложение запущенным
        try:
            while True:
                await asyncio.sleep(3600)  # Проверяем каждый час
                
                # 🆕 НОВОЕ: Периодическая проверка торговой системы
                if strategy_orchestrator and not strategy_orchestrator.is_running:
                    logger.warning("⚠️ StrategyOrchestrator остановился, перезапуск...")
                    try:
                        await strategy_orchestrator.start()
                        logger.info("✅ StrategyOrchestrator перезапущен")
                    except Exception as e:
                        logger.error(f"❌ Не удалось перезапустить StrategyOrchestrator: {e}")
                
                # Логируем статистику
                if bot_instance:
                    subscribers_count = len(bot_instance.signal_subscribers)
                    strategies_active = strategy_orchestrator._count_active_strategies() if strategy_orchestrator else 0
                    logger.info(f"📊 Статистика: {subscribers_count} подписчиков, {strategies_active} активных стратегий")
                
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
