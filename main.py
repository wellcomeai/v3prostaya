import asyncio
import logging
import sys
import os
from datetime import datetime
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from telegram_bot import TelegramBot
from config import Config

# Модульная архитектура
from market_data import MarketDataManager
from core import SignalManager, StrategyOrchestrator
from core.data_models import SystemConfig, StrategyConfig, create_default_system_config
from strategies import MomentumStrategy

# 🆕 НОВОЕ: База данных
from database import initialize_database, close_database, get_database_health

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
market_data_manager = None
signal_manager = None
strategy_orchestrator = None
system_config = None
database_initialized = False


def serialize_datetime_objects(obj):
    """
    Рекурсивно сериализует datetime объекты в ISO строки для JSON совместимости
    
    Args:
        obj: Объект который может содержать datetime экземпляры
        
    Returns:
        Объект с datetime экземплярами, преобразованными в строки
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_datetime_objects(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetime_objects(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(serialize_datetime_objects(item) for item in obj)
    elif hasattr(obj, '__dict__'):
        # Для пользовательских объектов с атрибутами
        return {key: serialize_datetime_objects(value) for key, value in obj.__dict__.items()}
    else:
        return obj


async def health_check(request):
    """Health check endpoint для Render и мониторинга"""
    try:
        # Проверяем бот
        bot_status = "inactive"
        bot_info = None
        if bot_instance and bot_instance.bot:
            try:
                bot_info = await bot_instance.bot.get_me()
                bot_status = "active"
            except Exception as e:
                bot_status = "error"
                logger.warning(f"Bot health check failed: {e}")
        
        # Проверяем БД
        db_health = await get_database_health()
        # БД уже возвращает сериализованные данные из исправленного postgres.py
        
        # Проверяем торговую систему
        trading_system_status = {
            "market_data_manager": "inactive",
            "signal_manager": "inactive", 
            "strategy_orchestrator": "inactive",
            "strategies_active": 0
        }
        
        if market_data_manager:
            try:
                health_status = market_data_manager.get_health_status()
                trading_system_status["market_data_manager"] = health_status.get("overall_status", "unknown")
            except Exception as e:
                logger.warning(f"Market data manager health check failed: {e}")
                trading_system_status["market_data_manager"] = "error"
        
        if signal_manager:
            try:
                trading_system_status["signal_manager"] = "running" if signal_manager.is_running else "inactive"
            except Exception as e:
                logger.warning(f"Signal manager health check failed: {e}")
                trading_system_status["signal_manager"] = "error"
        
        if strategy_orchestrator:
            try:
                trading_system_status["strategy_orchestrator"] = strategy_orchestrator.status.value
                trading_system_status["strategies_active"] = strategy_orchestrator._count_active_strategies()
            except Exception as e:
                logger.warning(f"Strategy orchestrator health check failed: {e}")
                trading_system_status["strategy_orchestrator"] = "error"
                trading_system_status["strategies_active"] = 0
        
        # Формируем ответ
        health_response = {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "database": {
                "status": "connected" if db_health.get("healthy", False) else "disconnected",
                "initialized": database_initialized,
                **db_health
            },
            "telegram_bot": {
                "status": bot_status,
                "username": bot_info.username if bot_info else None,
                "bot_id": bot_info.id if bot_info else None,
                "signal_subscribers": len(bot_instance.signal_subscribers) if bot_instance else 0
            },
            "trading_system": trading_system_status
        }
        
        # Сериализуем все datetime объекты
        health_response = serialize_datetime_objects(health_response)
        
        # Определяем HTTP статус
        overall_healthy = (
            db_health.get("healthy", False) and 
            bot_status == "active" and
            database_initialized
        )
        
        status_code = 200 if overall_healthy else 503
        
        return web.json_response(health_response, status=status_code)
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }, status=500)


async def database_status(request):
    """Endpoint для детального статуса БД"""
    try:
        db_health = await get_database_health()
        
        # Дополнительная информация о БД
        additional_info = {
            "config": {
                "database_url_configured": bool(Config.get_database_url()),
                "ssl_mode": Config.get_ssl_mode(),
                "environment": Config.ENVIRONMENT,
                "auto_migrate": Config.should_auto_migrate()
            }
        }
        
        response_data = {
            **db_health,
            **additional_info,
            "initialized": database_initialized
        }
        
        # Сериализуем datetime объекты
        response_data = serialize_datetime_objects(response_data)
        
        return web.json_response(response_data)
        
    except Exception as e:
        logger.error(f"❌ Database status check failed: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e),
            "initialized": database_initialized,
            "timestamp": datetime.now().isoformat()
        }, status=500)


async def trading_system_status_handler(request):
    """Endpoint для статуса торговой системы"""
    try:
        if not market_data_manager or not signal_manager or not strategy_orchestrator:
            return web.json_response({
                "status": "inactive",
                "message": "Trading system not initialized",
                "timestamp": datetime.now().isoformat()
            }, status=503)
        
        # Собираем статистику
        response_data = {}
        
        try:
            response_data["market_data_manager"] = market_data_manager.get_stats()
        except Exception as e:
            logger.warning(f"Failed to get market data stats: {e}")
            response_data["market_data_manager"] = {"error": str(e)}
        
        try:
            response_data["signal_manager"] = signal_manager.get_stats()
        except Exception as e:
            logger.warning(f"Failed to get signal manager stats: {e}")
            response_data["signal_manager"] = {"error": str(e)}
        
        try:
            response_data["strategy_orchestrator"] = strategy_orchestrator.get_stats()
        except Exception as e:
            logger.warning(f"Failed to get orchestrator stats: {e}")
            response_data["strategy_orchestrator"] = {"error": str(e)}
        
        try:
            response_data["system_health"] = {
                "market_data": market_data_manager.get_health_status() if market_data_manager else None,
                "strategies": strategy_orchestrator.get_health_status() if strategy_orchestrator else None
            }
        except Exception as e:
            logger.warning(f"Failed to get system health: {e}")
            response_data["system_health"] = {"error": str(e)}
        
        try:
            response_data["database"] = await get_database_health()
        except Exception as e:
            logger.warning(f"Failed to get database health: {e}")
            response_data["database"] = {"error": str(e)}
        
        response_data["timestamp"] = datetime.now().isoformat()
        response_data["status"] = "active"
        
        # Сериализуем все datetime объекты
        response_data = serialize_datetime_objects(response_data)
        
        return web.json_response(response_data)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в trading_system_status: {e}")
        return web.json_response({
            "status": "error", 
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }, status=500)


async def root_handler(request):
    """Root endpoint с информацией о системе"""
    try:
        system_info = {
            "message": "Bybit Trading Bot v2.1 - Production Ready",
            "features": [
                "✅ PostgreSQL Database Integration",
                "✅ Historical Data Storage", 
                "✅ Modular Market Data Management",
                "✅ Strategy Orchestration System",
                "✅ Advanced Signal Management",
                "✅ REST API + WebSocket Integration",
                "✅ OpenAI Integration",
                "✅ Telegram Notifications"
            ],
            "status": "active",
            "timestamp": datetime.now().isoformat(),
            "database_enabled": database_initialized,
            "trading_system_active": bool(strategy_orchestrator and strategy_orchestrator.is_running),
            "environment": Config.ENVIRONMENT,
            "webhook_path": WEBHOOK_PATH
        }
        
        # Дополнительная информация если доступна
        if market_data_manager:
            try:
                system_info["market_data_status"] = market_data_manager.get_health_status().get("overall_status", "unknown")
            except Exception as e:
                logger.warning(f"Failed to get market data status: {e}")
                system_info["market_data_status"] = "error"
        
        if strategy_orchestrator:
            try:
                system_info["active_strategies"] = strategy_orchestrator._count_active_strategies()
            except Exception as e:
                logger.warning(f"Failed to get active strategies count: {e}")
                system_info["active_strategies"] = 0
        
        if bot_instance:
            try:
                system_info["signal_subscribers"] = len(bot_instance.signal_subscribers)
            except Exception as e:
                logger.warning(f"Failed to get signal subscribers count: {e}")
                system_info["signal_subscribers"] = 0
        
        # Сериализуем datetime объекты
        system_info = serialize_datetime_objects(system_info)
        
        return web.json_response(system_info)
        
    except Exception as e:
        logger.error(f"❌ Root handler failed: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }, status=500)


async def on_startup(bot) -> None:
    """Действия при запуске - устанавливаем webhook"""
    webhook_url = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"
    logger.info(f"🔗 Настройка webhook: {webhook_url}")
    
    try:
        # Удаляем старый webhook
        logger.info("🔄 Удаляю старый webhook...")
        await bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(2)
        
        # Устанавливаем новый webhook
        logger.info("🔗 Устанавливаю новый webhook...")
        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True
        )
        
        # Проверяем webhook
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
    global bot_instance, market_data_manager, signal_manager, strategy_orchestrator, database_initialized
    
    try:
        # Останавливаем торговую систему
        if strategy_orchestrator:
            logger.info("🔄 Остановка StrategyOrchestrator...")
            try:
                await strategy_orchestrator.stop()
                logger.info("✅ StrategyOrchestrator остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки StrategyOrchestrator: {e}")
        
        if signal_manager:
            logger.info("🔄 Остановка SignalManager...")
            try:
                await signal_manager.stop()
                logger.info("✅ SignalManager остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки SignalManager: {e}")
        
        if market_data_manager:
            logger.info("🔄 Остановка MarketDataManager...")
            try:
                await market_data_manager.stop()
                logger.info("✅ MarketDataManager остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки MarketDataManager: {e}")
        
        # Закрываем Telegram бот
        if bot_instance:
            try:
                await bot_instance.close()
                logger.info("✅ Telegram бот закрыт")
            except Exception as e:
                logger.error(f"❌ Ошибка закрытия Telegram бота: {e}")
        
        # 🆕 НОВОЕ: Закрываем базу данных
        if database_initialized:
            logger.info("🔄 Закрытие базы данных...")
            try:
                await close_database()
                database_initialized = False
                logger.info("✅ База данных закрыта")
            except Exception as e:
                logger.error(f"❌ Ошибка закрытия базы данных: {e}")
                database_initialized = False
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка освобождения ресурсов: {e}")


async def initialize_database_system():
    """Инициализация базы данных"""
    global database_initialized
    
    try:
        logger.info("🗄️ Инициализация базы данных...")
        logger.info(f"   • Database URL: {'настроен' if Config.get_database_url() else 'НЕ НАСТРОЕН'}")
        logger.info(f"   • SSL Mode: {Config.get_ssl_mode()}")
        logger.info(f"   • Environment: {Config.ENVIRONMENT}")
        logger.info(f"   • Auto-migrate: {Config.should_auto_migrate()}")
        
        # Инициализируем БД
        database_initialized = await initialize_database()
        
        if database_initialized:
            logger.info("✅ База данных инициализирована успешно")
            
            # Проверяем статус БД
            try:
                db_health = await get_database_health()
                if db_health.get("healthy", False):
                    logger.info(f"✅ База данных работает: {db_health.get('status', 'unknown')}")
                else:
                    logger.warning(f"⚠️ Проблема с базой данных: {db_health}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось проверить статус БД: {e}")
                
            return True
        else:
            logger.error("❌ Не удалось инициализировать базу данных")
            return False
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка инициализации БД: {e}")
        database_initialized = False
        return False


async def initialize_trading_system():
    """Инициализация торговой системы"""
    global market_data_manager, signal_manager, strategy_orchestrator, system_config
    
    try:
        logger.info("🚀 Инициализация торговой системы...")
        
        # Создаем конфигурацию системы
        system_config = create_default_system_config()
        system_config.trading_mode = system_config.trading_mode.PAPER
        system_config.bybit_testnet = Config.BYBIT_TESTNET
        system_config.default_symbol = Config.SYMBOL
        
        # Инициализируем менеджер рыночных данных
        logger.info("📊 Инициализация MarketDataManager...")
        market_data_manager = MarketDataManager(
            symbol=Config.SYMBOL,
            testnet=Config.BYBIT_TESTNET,
            enable_websocket=True,
            enable_rest_api=True
        )
        
        # Инициализируем менеджер сигналов
        logger.info("🎛️ Инициализация SignalManager...")
        signal_manager = SignalManager(
            max_queue_size=1000,
            notification_settings=system_config.notification_settings
        )
        
        # Подписываем Telegram бота на сигналы
        if bot_instance:
            signal_manager.add_subscriber(bot_instance.broadcast_signal)
            logger.info("📡 Telegram бот подписан на торговые сигналы")
        
        # Инициализируем оркестратор стратегий
        logger.info("🎭 Инициализация StrategyOrchestrator...")
        strategy_orchestrator = StrategyOrchestrator(
            market_data_manager=market_data_manager,
            signal_manager=signal_manager,
            system_config=system_config,
            analysis_interval=30.0,
            max_concurrent_analyses=3,
            enable_performance_monitoring=True
        )
        
        # Запускаем все компоненты
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
        logger.info(f"📊 MarketDataManager: активен")
        logger.info(f"🎛️ SignalManager: активен") 
        logger.info(f"🎭 StrategyOrchestrator: активен")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка инициализации торговой системы: {e}")
        return False


async def create_app():
    """Создание веб-приложения"""
    global bot_instance
    
    # 🆕 НОВОЕ: Инициализируем базу данных ПЕРВОЙ
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК BYBIT TRADING BOT v2.1")
    logger.info("=" * 50)
    
    # Шаг 1: Инициализация базы данных
    db_success = await initialize_database_system()
    if not db_success:
        logger.error("💥 Критическая ошибка: не удалось инициализировать БД")
        if Config.is_production():
            # В продакшене БД критична
            raise Exception("Database initialization failed in production")
        else:
            # В разработке можем продолжить без БД
            logger.warning("⚠️ Продолжаем без базы данных (только для разработки)")
    
    # Шаг 2: Создаем экземпляр бота
    logger.info("🤖 Инициализация Telegram бота...")
    bot_instance = TelegramBot(Config.TELEGRAM_BOT_TOKEN)
    
    # Шаг 3: Инициализируем торговую систему
    trading_system_started = await initialize_trading_system()
    if trading_system_started:
        logger.info("✅ Торговая система активна")
        logger.info(f"📊 Мониторинг символа: {Config.SYMBOL}")
        logger.info(f"🔧 Режим: {'Testnet' if Config.BYBIT_TESTNET else 'Mainnet'}")
        logger.info(f"🗄️ База данных: {'подключена' if database_initialized else 'отключена'}")
    else:
        logger.warning("⚠️ Торговая система не активна, только Telegram бот")
    
    # Шаг 4: Устанавливаем webhook
    await on_startup(bot_instance.bot)
    
    # Шаг 5: Создаем веб-приложение
    app = web.Application()
    
    # Основные endpoints
    app.router.add_get("/health", health_check)
    app.router.add_get("/database/status", database_status)
    app.router.add_get("/trading/status", trading_system_status_handler)
    app.router.add_get("/", root_handler)
    
    # Webhook handler
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=bot_instance.dp,
        bot=bot_instance.bot,
        secret_token=WEBHOOK_SECRET
    )
    
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, bot_instance.dp, bot=bot_instance.bot)
    
    # Graceful shutdown
    async def cleanup_handler(app):
        await cleanup_resources()
    
    app.on_cleanup.append(cleanup_handler)
    
    return app


async def main():
    """Главная функция приложения"""
    
    try:
        logger.info("🌟 Запуск Bybit Trading Bot v2.1 (Production Ready)")
        logger.info(f"🔧 Порт: {WEB_SERVER_PORT}")
        logger.info(f"🔧 Webhook URL: {BASE_WEBHOOK_URL}{WEBHOOK_PATH}")
        logger.info(f"🔧 Testnet: {Config.BYBIT_TESTNET}")
        logger.info(f"🔧 Symbol: {Config.SYMBOL}")
        logger.info(f"🔧 Environment: {Config.ENVIRONMENT}")
        logger.info(f"🔧 Database: {'настроена' if Config.get_database_url() else 'НЕ НАСТРОЕНА'}")
        
        # Создаем приложение
        app = await create_app()
        
        # Запускаем веб-сервер
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
        await site.start()
        
        logger.info("=" * 50)
        logger.info("✅ ПРИЛОЖЕНИЕ УСПЕШНО ЗАПУЩЕНО")
        logger.info("=" * 50)
        logger.info(f"🌐 Веб-сервер: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
        logger.info(f"🤖 Telegram бот: активен")
        logger.info(f"🗄️ База данных: {'подключена' if database_initialized else 'отключена'}")
        logger.info(f"🚀 Торговая система: {'активна' if strategy_orchestrator and strategy_orchestrator.is_running else 'неактивна'}")
        logger.info("=" * 50)
        logger.info("📡 Endpoints:")
        logger.info(f"   • Health: {BASE_WEBHOOK_URL}/health")
        logger.info(f"   • Database: {BASE_WEBHOOK_URL}/database/status")
        logger.info(f"   • Trading: {BASE_WEBHOOK_URL}/trading/status")
        logger.info("=" * 50)
        
        # Основной цикл приложения
        try:
            while True:
                await asyncio.sleep(3600)  # Проверяем каждый час
                
                # Проверка торговой системы
                if strategy_orchestrator and not strategy_orchestrator.is_running:
                    logger.warning("⚠️ StrategyOrchestrator остановился, перезапуск...")
                    try:
                        await strategy_orchestrator.start()
                        logger.info("✅ StrategyOrchestrator перезапущен")
                    except Exception as e:
                        logger.error(f"❌ Не удалось перезапустить StrategyOrchestrator: {e}")
                
                # Логируем статистику
                if bot_instance and strategy_orchestrator:
                    try:
                        subscribers_count = len(bot_instance.signal_subscribers)
                        strategies_active = strategy_orchestrator._count_active_strategies()
                        db_status = "OK" if database_initialized else "OFF"
                        logger.info(f"📊 Статистика: {subscribers_count} подписчиков, "
                                  f"{strategies_active} стратегий, БД: {db_status}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось получить статистику: {e}")
                
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
        except Exception as cleanup_error:
            logger.error(f"❌ Ошибка аварийной очистки: {cleanup_error}")
            
        raise


def run_app():
    """Запуск приложения с корректной обработкой исключений"""
    try:
        # Проверяем критически важные настройки
        if not Config.TELEGRAM_BOT_TOKEN or Config.TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
            logger.error("💥 ОШИБКА: Telegram Bot Token не настроен!")
            sys.exit(1)
        
        if not Config.get_database_url():
            logger.warning("⚠️ Database URL не настроен - БД будет отключена")
        
        # Запускаем приложение
        if hasattr(asyncio, 'run'):
            asyncio.run(main())
        else:
            # Для более старых версий Python
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
            
    except KeyboardInterrupt:
        logger.info("🔴 Приложение остановлено пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка приложения: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_app()
