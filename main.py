import asyncio
import logging
import sys
import os
import traceback
from datetime import datetime, timedelta
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from telegram_bot import TelegramBot
from config import Config

# Модульная архитектура v3.0
from market_data import MarketDataManager

# ✅ ИСПРАВЛЕНО: Правильные импорты
from core.signal_manager import SignalManager
from strategies.strategy_orchestrator import StrategyOrchestrator

# ✅ SimpleCandleSync для криптовалют (Bybit)
from market_data.simple_candle_sync import SimpleCandleSync

# ✅ SimpleFuturesSync для фьючерсов (YFinance)
from market_data.simple_futures_sync import SimpleFuturesSync

# ✅ TechnicalAnalysisContextManager
from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager

# База данных
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

# ✅ Глобальные переменные (упрощенная версия v3.0)
bot_instance = None
market_data_manager = None
signal_manager = None
strategy_orchestrator = None
simple_candle_sync = None
simple_futures_sync = None
ta_context_manager = None
repository = None
database_initialized = False
trading_system_ready = False


def serialize_datetime_objects(obj):
    """
    Рекурсивно сериализует datetime объекты в ISO строки для JSON совместимости
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
        
        # ✅ Проверяем все компоненты v3.0
        trading_system_status = {
            "simple_candle_sync": "inactive",
            "simple_futures_sync": "inactive",
            "ta_context_manager": "inactive",
            "repository": "inactive",
            "signal_manager": "inactive", 
            "strategy_orchestrator": "inactive",
            "strategies_active": 0,
            "system_ready": trading_system_ready
        }
        
        # SimpleCandleSync статус
        if simple_candle_sync:
            try:
                trading_system_status["simple_candle_sync"] = "running" if simple_candle_sync.is_running else "inactive"
            except Exception as e:
                logger.warning(f"SimpleCandleSync health check failed: {e}")
                trading_system_status["simple_candle_sync"] = "error"
        
        # SimpleFuturesSync статус
        if simple_futures_sync:
            try:
                trading_system_status["simple_futures_sync"] = "running" if simple_futures_sync.is_running else "inactive"
            except Exception as e:
                logger.warning(f"SimpleFuturesSync health check failed: {e}")
                trading_system_status["simple_futures_sync"] = "error"
        
        # TechnicalAnalysisContextManager статус
        if ta_context_manager:
            try:
                trading_system_status["ta_context_manager"] = "running" if ta_context_manager.is_running else "inactive"
            except Exception as e:
                logger.warning(f"TechnicalAnalysisContextManager health check failed: {e}")
                trading_system_status["ta_context_manager"] = "error"
        
        # Repository статус
        if repository:
            try:
                trading_system_status["repository"] = "active"
            except Exception as e:
                logger.warning(f"Repository health check failed: {e}")
                trading_system_status["repository"] = "error"
        
        # SignalManager статус
        if signal_manager:
            try:
                trading_system_status["signal_manager"] = "running" if signal_manager.is_running else "inactive"
            except Exception as e:
                logger.warning(f"Signal manager health check failed: {e}")
                trading_system_status["signal_manager"] = "error"
        
        # StrategyOrchestrator статус
        if strategy_orchestrator:
            try:
                trading_system_status["strategy_orchestrator"] = "running" if strategy_orchestrator.is_running else "inactive"
                trading_system_status["strategies_active"] = len(strategy_orchestrator.strategies)
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
                "active_users": len(bot_instance.all_users) if bot_instance else 0
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


# ========== SYNC STATUS ENDPOINTS ==========

async def simple_sync_status_handler(request):
    """Endpoint для статуса SimpleCandleSync (крипта)"""
    try:
        if not simple_candle_sync:
            return web.json_response({
                "status": "error",
                "message": "SimpleCandleSync not initialized"
            }, status=503)
        
        stats = simple_candle_sync.get_stats()
        health = simple_candle_sync.get_health_status()
        
        response_data = {
            "status": "running" if simple_candle_sync.is_running else "stopped",
            "health": health,
            "stats": stats,
            "symbols": simple_candle_sync.symbols,
            "intervals": [s.interval for s in simple_candle_sync.schedule],
            "timestamp": datetime.now().isoformat()
        }
        
        response_data = serialize_datetime_objects(response_data)
        
        return web.json_response(response_data)
        
    except Exception as e:
        logger.error(f"Error getting SimpleCandleSync status: {e}")
        logger.error(traceback.format_exc())
        return web.json_response({
            "status": "error",
            "error": str(e)
        }, status=500)


async def futures_sync_status_handler(request):
    """Endpoint для статуса SimpleFuturesSync (фьючерсы)"""
    try:
        if not simple_futures_sync:
            return web.json_response({
                "status": "error",
                "message": "SimpleFuturesSync not initialized"
            }, status=503)
        
        stats = simple_futures_sync.get_stats()
        health = simple_futures_sync.get_health_status()
        
        response_data = {
            "status": "running" if simple_futures_sync.is_running else "stopped",
            "health": health,
            "stats": stats,
            "symbols": simple_futures_sync.symbols,
            "intervals": [s.interval for s in simple_futures_sync.schedule],
            "timestamp": datetime.now().isoformat()
        }
        
        response_data = serialize_datetime_objects(response_data)
        
        return web.json_response(response_data)
        
    except Exception as e:
        logger.error(f"Error getting SimpleFuturesSync status: {e}")
        logger.error(traceback.format_exc())
        return web.json_response({
            "status": "error",
            "error": str(e)
        }, status=500)


async def ta_context_status_handler(request):
    """Endpoint для статуса Technical Analysis Context Manager"""
    try:
        if not ta_context_manager:
            return web.json_response({
                "status": "error",
                "message": "TechnicalAnalysisContextManager not initialized"
            }, status=503)
        
        stats = ta_context_manager.get_stats()
        health = ta_context_manager.get_health_status()
        analyzer_stats = ta_context_manager.get_analyzer_stats_summary()
        
        response_data = {
            "status": "running" if ta_context_manager.is_running else "stopped",
            "health": health,
            "stats": stats,
            "analyzers": analyzer_stats,
            "contexts": list(ta_context_manager.contexts.keys()),
            "contexts_count": len(ta_context_manager.contexts),
            "timestamp": datetime.now().isoformat()
        }
        
        response_data = serialize_datetime_objects(response_data)
        
        return web.json_response(response_data)
        
    except Exception as e:
        logger.error(f"Error getting TA Context status: {e}")
        logger.error(traceback.format_exc())
        return web.json_response({
            "status": "error",
            "error": str(e)
        }, status=500)


async def trading_system_status_handler(request):
    """Endpoint для статуса торговой системы v3.0"""
    try:
        response_data = {}
        
        # SimpleCandleSync статус
        if simple_candle_sync:
            try:
                response_data["simple_candle_sync"] = simple_candle_sync.get_stats()
            except Exception as e:
                logger.warning(f"Failed to get simple_candle_sync stats: {e}")
                response_data["simple_candle_sync"] = {"error": str(e)}
        
        # SimpleFuturesSync статус
        if simple_futures_sync:
            try:
                response_data["simple_futures_sync"] = simple_futures_sync.get_stats()
            except Exception as e:
                logger.warning(f"Failed to get simple_futures_sync stats: {e}")
                response_data["simple_futures_sync"] = {"error": str(e)}
        
        # TechnicalAnalysisContextManager статус
        if ta_context_manager:
            try:
                response_data["ta_context_manager"] = ta_context_manager.get_stats()
            except Exception as e:
                logger.warning(f"Failed to get ta_context_manager stats: {e}")
                response_data["ta_context_manager"] = {"error": str(e)}
        
        # Repository статус
        if repository:
            try:
                response_data["repository"] = {
                    "status": "active",
                    "type": "MarketDataRepository"
                }
            except Exception as e:
                logger.warning(f"Failed to get repository status: {e}")
                response_data["repository"] = {"error": str(e)}
        
        # SignalManager статус
        if signal_manager:
            try:
                response_data["signal_manager"] = signal_manager.get_stats()
            except Exception as e:
                logger.warning(f"Failed to get signal manager stats: {e}")
                response_data["signal_manager"] = {"error": str(e)}
        
        # StrategyOrchestrator статус
        if strategy_orchestrator:
            try:
                response_data["strategy_orchestrator"] = strategy_orchestrator.get_stats()
            except Exception as e:
                logger.warning(f"Failed to get orchestrator stats: {e}")
                response_data["strategy_orchestrator"] = {"error": str(e)}
        
        # System health
        try:
            response_data["system_health"] = {
                "simple_candle_sync": simple_candle_sync.get_health_status() if simple_candle_sync else None,
                "simple_futures_sync": simple_futures_sync.get_health_status() if simple_futures_sync else None,
                "ta_context_manager": ta_context_manager.get_health_status() if ta_context_manager else None,
                "repository": "active" if repository else None,
                "signal_manager": signal_manager.get_health_status() if signal_manager else None,
                "orchestrator": strategy_orchestrator.get_health_status() if strategy_orchestrator else None
            }
        except Exception as e:
            logger.warning(f"Failed to get system health: {e}")
            response_data["system_health"] = {"error": str(e)}
        
        # Database
        try:
            response_data["database"] = await get_database_health()
        except Exception as e:
            logger.warning(f"Failed to get database health: {e}")
            response_data["database"] = {"error": str(e)}
        
        response_data["timestamp"] = datetime.now().isoformat()
        response_data["status"] = "active"
        response_data["system_ready"] = trading_system_ready
        
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
    """Root endpoint с информацией о системе v3.0"""
    try:
        system_info = {
            "message": "Bybit Trading Bot v3.0 - Simplified Architecture",
            "features": [
                "✅ PostgreSQL Database Integration",
                "✅ SimpleCandleSync - REST API Crypto Sync",
                "✅ SimpleFuturesSync - YFinance Futures Sync",
                "✅ TechnicalAnalysisContextManager",
                "✅ Repository - Direct DB Access",
                "✅ SignalManager v3.0",
                "✅ StrategyOrchestrator v3.0",
                "✅ 3 Level-Based Strategies (Breakout, Bounce, False Breakout)",
                "✅ OpenAI GPT-4 Integration",
                "✅ Telegram Notifications",
                "🚀 Production Ready"
            ],
            "status": "active",
            "timestamp": datetime.now().isoformat(),
            "database_enabled": database_initialized,
            "simple_candle_sync_active": bool(simple_candle_sync and simple_candle_sync.is_running),
            "simple_futures_sync_active": bool(simple_futures_sync and simple_futures_sync.is_running),
            "ta_context_manager_active": bool(ta_context_manager and ta_context_manager.is_running),
            "repository_active": bool(repository),
            "signal_manager_active": bool(signal_manager and signal_manager.is_running),
            "orchestrator_active": bool(strategy_orchestrator and strategy_orchestrator.is_running),
            "trading_system_ready": trading_system_ready,
            "environment": Config.ENVIRONMENT,
            "webhook_path": WEBHOOK_PATH,
            "api_endpoints": {
                "health": "/health",
                "database_status": "/database/status", 
                "trading_status": "/trading/status",
                "simple_sync_status": "/admin/sync-status",
                "futures_sync_status": "/admin/futures-sync-status",
                "ta_context_status": "/admin/ta-context-status"
            }
        }
        
        # Дополнительная информация
        if simple_candle_sync:
            try:
                health = simple_candle_sync.get_health_status()
                system_info["simple_candle_sync_health"] = health.get("healthy", False)
                system_info["candles_synced"] = simple_candle_sync.stats.get("candles_synced", 0)
            except Exception as e:
                logger.warning(f"Failed to get SimpleCandleSync status: {e}")
        
        if simple_futures_sync:
            try:
                health = simple_futures_sync.get_health_status()
                system_info["simple_futures_sync_health"] = health.get("healthy", False)
                system_info["futures_candles_synced"] = simple_futures_sync.stats.get("candles_synced", 0)
            except Exception as e:
                logger.warning(f"Failed to get SimpleFuturesSync status: {e}")
        
        if ta_context_manager:
            try:
                health = ta_context_manager.get_health_status()
                system_info["ta_context_manager_health"] = health.get("healthy", False)
                system_info["ta_contexts_count"] = len(ta_context_manager.contexts)
            except Exception as e:
                logger.warning(f"Failed to get TechnicalAnalysisContextManager status: {e}")
        
        if strategy_orchestrator:
            try:
                system_info["active_strategies"] = len(strategy_orchestrator.strategies)
                system_info["orchestrator_cycles"] = strategy_orchestrator.stats.get("total_cycles", 0)
            except Exception as e:
                logger.warning(f"Failed to get orchestrator stats: {e}")
                system_info["active_strategies"] = 0
        
        if bot_instance:
            try:
                system_info["active_users"] = len(bot_instance.all_users)
            except Exception as e:
                logger.warning(f"Failed to get active users count: {e}")
                system_info["active_users"] = 0
        
        system_info = serialize_datetime_objects(system_info)
        
        return web.json_response(system_info)
        
    except Exception as e:
        logger.error(f"❌ Root handler failed: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }, status=500)


# ========== LIFECYCLE HANDLERS ==========

async def on_startup(bot) -> None:
    """Действия при запуске - устанавливаем webhook"""
    webhook_url = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"
    logger.info(f"🔗 Настройка webhook: {webhook_url}")
    
    try:
        logger.info("🔄 Удаляю старый webhook...")
        await bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(2)
        
        logger.info("🔗 Устанавливаю новый webhook...")
        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True
        )
        
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
    global bot_instance, signal_manager, strategy_orchestrator
    global simple_candle_sync, simple_futures_sync, ta_context_manager, repository
    global database_initialized, trading_system_ready
    
    try:
        trading_system_ready = False
        
        # Останавливаем StrategyOrchestrator
        if strategy_orchestrator:
            logger.info("🔄 Остановка StrategyOrchestrator...")
            try:
                await strategy_orchestrator.stop()
                logger.info("✅ StrategyOrchestrator остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки StrategyOrchestrator: {e}")
        
        # Останавливаем TechnicalAnalysisContextManager
        if ta_context_manager:
            logger.info("🔄 Остановка TechnicalAnalysisContextManager...")
            try:
                await ta_context_manager.stop_background_updates()
                logger.info("✅ TechnicalAnalysisContextManager остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки TechnicalAnalysisContextManager: {e}")
        
        # Останавливаем SimpleFuturesSync
        if simple_futures_sync:
            logger.info("🔄 Остановка SimpleFuturesSync...")
            try:
                await simple_futures_sync.stop()
                logger.info("✅ SimpleFuturesSync остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки SimpleFuturesSync: {e}")
        
        # Останавливаем SimpleCandleSync
        if simple_candle_sync:
            logger.info("🔄 Остановка SimpleCandleSync...")
            try:
                await simple_candle_sync.stop()
                logger.info("✅ SimpleCandleSync остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки SimpleCandleSync: {e}")
        
        # Останавливаем SignalManager
        if signal_manager:
            logger.info("🔄 Остановка SignalManager...")
            try:
                await signal_manager.stop()
                logger.info("✅ SignalManager остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки SignalManager: {e}")
        
        # Repository очистка
        if repository:
            logger.info("✅ Repository очищен")
            repository = None
        
        # Закрываем Telegram бот
        if bot_instance:
            try:
                await bot_instance.close()
                logger.info("✅ Telegram бот закрыт")
            except Exception as e:
                logger.error(f"❌ Ошибка закрытия Telegram бота: {e}")
        
        # Закрываем базу данных
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
        
        database_initialized = await initialize_database()
        
        if database_initialized:
            logger.info("✅ База данных инициализирована успешно")
            
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


async def create_trading_components():
    """
    ✅ СОЗДАНИЕ компонентов БЕЗ запуска
    Только инициализация объектов, фоновые задачи не запускаются
    """
    global signal_manager, strategy_orchestrator
    global simple_candle_sync, simple_futures_sync, ta_context_manager
    global repository
    
    try:
        logger.info("📊 Создание торговых компонентов...")
        
        # ==================== ШАГ 1: Repository ====================
        logger.info("📊 Инициализация Repository...")
        from database.repositories import get_market_data_repository
        
        repository = await get_market_data_repository()
        logger.info("✅ Repository создан")
        
        # ==================== ШАГ 2: SimpleCandleSync (БЕЗ запуска) ====================
        logger.info("🔄 Создание SimpleCandleSync...")
        from bybit_client import BybitClient
        
        bybit_client = BybitClient()
        
        simple_candle_sync = SimpleCandleSync(
            symbols=Config.get_bybit_symbols(),
            bybit_client=bybit_client,
            repository=repository,
            check_gaps_on_start=False  # ❗ НЕ проверяем при создании
        )
        
        logger.info("✅ SimpleCandleSync создан (не запущен)")
        
        # ==================== ШАГ 3: SimpleFuturesSync (БЕЗ запуска) ====================
        futures_symbols = Config.get_yfinance_symbols()
        
        if futures_symbols:
            logger.info("🔄 Создание SimpleFuturesSync...")
            simple_futures_sync = SimpleFuturesSync(
                symbols=futures_symbols,
                repository=repository,
                check_gaps_on_start=False  # ❗ НЕ проверяем при создании
            )
            
            logger.info("✅ SimpleFuturesSync создан (не запущен)")
        else:
            logger.info("⏭️ SimpleFuturesSync пропущен (нет символов)")
            simple_futures_sync = None
        
        # ==================== ШАГ 4: TechnicalAnalysis (БЕЗ запуска) ====================
        logger.info("🧠 Создание TechnicalAnalysisContextManager...")
        
        ta_context_manager = TechnicalAnalysisContextManager(
            repository=repository,
            auto_start_background_updates=False  # ❗ НЕ запускаем фон
        )
        
        logger.info("✅ TechnicalAnalysisContextManager создан (не запущен)")
        
        # ==================== ШАГ 5: SignalManager (БЕЗ запуска) ====================
        logger.info("🎛️ Создание SignalManager v3.0...")
        
        # OpenAI анализатор (опционально)
        openai_analyzer = None
        try:
            from openai_integration import OpenAIAnalyzer
            openai_analyzer = OpenAIAnalyzer()
            logger.info("🤖 OpenAI анализатор создан")
        except Exception as e:
            logger.warning(f"⚠️ OpenAI недоступен: {e}")
        
        signal_manager = SignalManager(
            openai_analyzer=openai_analyzer,
            cooldown_minutes=5,
            max_signals_per_hour=12,
            enable_ai_enrichment=True,
            min_signal_strength=0.3
        )
        
        logger.info("✅ SignalManager создан (не запущен)")
        
        # ==================== ШАГ 6: StrategyOrchestrator (БЕЗ запуска) ====================
        logger.info("🎭 Создание StrategyOrchestrator v3.0...")
        
        # ✅ Собираем ВСЕ символы (крипта + фьючерсы)
        all_symbols = Config.get_bybit_symbols()
        if futures_symbols:
            all_symbols.extend(futures_symbols)
        
        logger.info(f"   • Всего символов: {len(all_symbols)}")
        logger.info(f"   • Крипта: {len(Config.get_bybit_symbols())}")
        logger.info(f"   • Фьючерсы: {len(futures_symbols) if futures_symbols else 0}")
        
        strategy_orchestrator = StrategyOrchestrator(
            repository=repository,
            ta_context_manager=ta_context_manager,
            signal_manager=signal_manager,
            symbols=all_symbols,
            analysis_interval_seconds=60,
            enabled_strategies=["breakout", "bounce", "false_breakout"]
        )
        
        logger.info("✅ StrategyOrchestrator создан (не запущен)")
        
        logger.info("=" * 70)
        logger.info("✅ ВСЕ КОМПОНЕНТЫ СОЗДАНЫ")
        logger.info("=" * 70)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания компонентов: {e}")
        logger.error(traceback.format_exc())
        return False


async def start_trading_system_background():
    """
    🚀 ФОНОВЫЙ запуск торговой системы
    Вызывается ПОСЛЕ того как веб-сервер уже работает
    """
    global trading_system_ready
    
    try:
        # Даем время веб-серверу полностью запуститься
        logger.info("⏳ Ожидание 10 секунд перед запуском торговой системы...")
        await asyncio.sleep(10)
        
        logger.info("=" * 70)
        logger.info("🚀 ФОНОВЫЙ ЗАПУСК ТОРГОВОЙ СИСТЕМЫ")
        logger.info("=" * 70)
        
        # ==================== SimpleCandleSync ====================
        if simple_candle_sync:
            logger.info("🔄 Запуск SimpleCandleSync...")
            try:
                await simple_candle_sync.start()
                logger.info("✅ SimpleCandleSync запущен")
            except Exception as e:
                logger.error(f"❌ Ошибка запуска SimpleCandleSync: {e}")
        
        # ==================== SimpleFuturesSync ====================
        if simple_futures_sync:
            logger.info("🔄 Запуск SimpleFuturesSync...")
            try:
                await simple_futures_sync.start()
                logger.info("✅ SimpleFuturesSync запущен")
            except Exception as e:
                logger.error(f"❌ Ошибка запуска SimpleFuturesSync: {e}")
        
        # ==================== TechnicalAnalysisContextManager ====================
        if ta_context_manager:
            logger.info("🧠 Запуск TechnicalAnalysisContextManager...")
            try:
                await ta_context_manager.start_background_updates()
                logger.info("✅ TechnicalAnalysisContextManager запущен")
            except Exception as e:
                logger.error(f"❌ Ошибка запуска TechnicalAnalysisContextManager: {e}")
        
        # ==================== SignalManager ====================
        if signal_manager:
            logger.info("🎛️ Запуск SignalManager...")
            try:
                await signal_manager.start()
                logger.info("✅ SignalManager запущен")
            except Exception as e:
                logger.error(f"❌ Ошибка запуска SignalManager: {e}")
        
        # ==================== StrategyOrchestrator ====================
        if strategy_orchestrator:
            logger.info("🎭 Запуск StrategyOrchestrator...")
            try:
                await strategy_orchestrator.start()
                logger.info("✅ StrategyOrchestrator запущен")
            except Exception as e:
                logger.error(f"❌ Ошибка запуска StrategyOrchestrator: {e}")
        
        trading_system_ready = True
        
        logger.info("=" * 70)
        logger.info("🎉 ТОРГОВАЯ СИСТЕМА ПОЛНОСТЬЮ АКТИВНА")
        logger.info("=" * 70)
        logger.info(f"🔄 SimpleCandleSync: {'✅' if simple_candle_sync and simple_candle_sync.is_running else '❌'}")
        logger.info(f"🔄 SimpleFuturesSync: {'✅' if simple_futures_sync and simple_futures_sync.is_running else '❌'}")
        logger.info(f"🧠 TechnicalAnalysis: {'✅' if ta_context_manager and ta_context_manager.is_running else '❌'}")
        logger.info(f"🎛️ SignalManager: {'✅' if signal_manager and signal_manager.is_running else '❌'}")
        logger.info(f"🎭 StrategyOrchestrator: {'✅' if strategy_orchestrator and strategy_orchestrator.is_running else '❌'}")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка фонового запуска торговой системы: {e}")
        logger.error(traceback.format_exc())
        trading_system_ready = False


async def create_app():
    """
    ✅ ПРАВИЛЬНОЕ создание приложения
    
    Последовательность:
    1. Инициализация БД
    2. СОЗДАНИЕ компонентов (без запуска)
    3. Создание Telegram бота
    4. Установка webhook
    5. Создание веб-приложения
    6. ВОЗВРАТ app (веб-сервер запустится в main())
    7. Торговая система запустится В ФОНЕ после старта веб-сервера
    """
    global bot_instance
    
    logger.info("=" * 70)
    logger.info("🚀 СОЗДАНИЕ ПРИЛОЖЕНИЯ v3.0")
    logger.info("=" * 70)
    
    # ========== ШАГ 1: Инициализация базы данных ==========
    db_success = await initialize_database_system()
    if not db_success:
        logger.error("💥 Критическая ошибка: не удалось инициализировать БД")
        if Config.is_production():
            raise Exception("Database initialization failed in production")
        else:
            logger.warning("⚠️ Продолжаем без базы данных (только для разработки)")
    
    # ========== ШАГ 2: СОЗДАЕМ торговые компоненты (БЕЗ запуска) ==========
    components_created = await create_trading_components()
    if components_created:
        logger.info("✅ Торговые компоненты созданы (фон не запущен)")
    else:
        logger.warning("⚠️ Не удалось создать торговые компоненты")
    
    # ========== ШАГ 3: Создаем Telegram бота ==========
    logger.info("🤖 Инициализация Telegram бота...")
    
    bot_instance = TelegramBot(
        token=Config.TELEGRAM_BOT_TOKEN,
        repository=repository,
        ta_context_manager=ta_context_manager
    )
    
    logger.info("✅ Telegram бот инициализирован")
    
    # ✅ Загружаем пользователей из БД
    if repository:
        try:
            users_loaded = await bot_instance.load_users_from_db()
            logger.info(f"📥 Загружено {users_loaded} пользователей из БД")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить пользователей из БД: {e}")
            logger.warning("⚠️ Продолжаем работу, пользователи будут добавляться при /start")
    
    # Подписываем бота на сигналы
    if signal_manager and bot_instance:
        signal_manager.add_subscriber(bot_instance.broadcast_signal)
        logger.info("📡 Telegram бот подписан на торговые сигналы")
    
    # ========== ШАГ 4: Устанавливаем webhook ==========
    await on_startup(bot_instance.bot)
    
    # ========== ШАГ 5: Создаем веб-приложение ==========
    logger.info("🌐 Создание веб-приложения...")
    app = web.Application()
    
    # Основные endpoints
    app.router.add_get("/health", health_check)
    app.router.add_get("/database/status", database_status)
    app.router.add_get("/trading/status", trading_system_status_handler)
    app.router.add_get("/", root_handler)
    
    # Sync status endpoints
    app.router.add_get("/admin/sync-status", simple_sync_status_handler)
    app.router.add_get("/admin/futures-sync-status", futures_sync_status_handler)
    app.router.add_get("/admin/ta-context-status", ta_context_status_handler)
    
    # Webhook handler
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=bot_instance.dp,
        bot=bot_instance.bot,
        secret_token=WEBHOOK_SECRET
    )
    
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, bot_instance.dp, bot=bot_instance.bot)
    
    logger.info("✅ Веб-приложение создано")
    
    # Graceful shutdown
    async def cleanup_handler(app):
        await cleanup_resources()
    
    app.on_cleanup.append(cleanup_handler)
    
    logger.info("=" * 70)
    logger.info("✅ ПРИЛОЖЕНИЕ ГОТОВО К ЗАПУСКУ")
    logger.info("=" * 70)
    
    return app


async def main():
    """
    ✅ ПРАВИЛЬНАЯ главная функция
    
    Последовательность:
    1. Создать app (БЕЗ запуска торговой системы)
    2. Запустить веб-сервер (открыть порт!)
    3. Запустить торговую систему В ФОНЕ
    4. Мониторинг компонентов
    """
    
    try:
        logger.info("🌟 Запуск Bybit Trading Bot v3.0")
        logger.info(f"🔧 Порт: {WEB_SERVER_PORT}")
        logger.info(f"🔧 Webhook URL: {BASE_WEBHOOK_URL}{WEBHOOK_PATH}")
        logger.info(f"🔧 Environment: {Config.ENVIRONMENT}")
        
        # ========== ШАГ 1: Создаем приложение ==========
        app = await create_app()
        
        # ========== ШАГ 2: Запускаем веб-сервер (ОТКРЫВАЕМ ПОРТ!) ==========
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
        await site.start()
        
        logger.info("=" * 70)
        logger.info("✅ ВЕБ-СЕРВЕР ЗАПУЩЕН (ПОРТ ОТКРЫТ)")
        logger.info("=" * 70)
        logger.info(f"🌐 Веб-сервер: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
        logger.info(f"🤖 Telegram бот: активен")
        logger.info(f"🗄️ База данных: {'подключена' if database_initialized else 'отключена'}")
        logger.info("=" * 70)
        
        # ========== ШАГ 3: Запускаем торговую систему В ФОНЕ ==========
        asyncio.create_task(start_trading_system_background())
        logger.info("🔄 Торговая система запускается в фоновом режиме...")
        
        # ========== ШАГ 4: Основной цикл мониторинга ==========
        try:
            while True:
                await asyncio.sleep(3600)
                
                # Мониторинг компонентов (перезапуск при необходимости)
                if simple_candle_sync and not simple_candle_sync.is_running:
                    logger.warning("⚠️ SimpleCandleSync остановился, перезапуск...")
                    try:
                        await simple_candle_sync.start()
                        logger.info("✅ SimpleCandleSync перезапущен")
                    except Exception as e:
                        logger.error(f"❌ Не удалось перезапустить SimpleCandleSync: {e}")
                
                if simple_futures_sync and not simple_futures_sync.is_running:
                    logger.warning("⚠️ SimpleFuturesSync остановился, перезапуск...")
                    try:
                        await simple_futures_sync.start()
                        logger.info("✅ SimpleFuturesSync перезапущен")
                    except Exception as e:
                        logger.error(f"❌ Не удалось перезапустить SimpleFuturesSync: {e}")
                
                if ta_context_manager and not ta_context_manager.is_running:
                    logger.warning("⚠️ TechnicalAnalysisContextManager остановился, перезапуск...")
                    try:
                        await ta_context_manager.start_background_updates()
                        logger.info("✅ TechnicalAnalysisContextManager перезапущен")
                    except Exception as e:
                        logger.error(f"❌ Не удалось перезапустить TechnicalAnalysisContextManager: {e}")
                
                if strategy_orchestrator and not strategy_orchestrator.is_running:
                    logger.warning("⚠️ StrategyOrchestrator остановился, перезапуск...")
                    try:
                        await strategy_orchestrator.start()
                        logger.info("✅ StrategyOrchestrator перезапущен")
                    except Exception as e:
                        logger.error(f"❌ Не удалось перезапустить StrategyOrchestrator: {e}")
                
        except asyncio.CancelledError:
            logger.info("📡 Получен сигнал отмены")
        except KeyboardInterrupt:
            logger.info("📡 Получен сигнал прерывания")
        finally:
            logger.info("🔄 Начинаю процедуру остановки...")
            
            if bot_instance:
                await on_shutdown(bot_instance.bot)
            
            await runner.cleanup()
            await cleanup_resources()
            
            logger.info("🏁 Приложение полностью остановлено")
            
    except Exception as e:
        logger.error(f"💥 Критическая ошибка в main(): {e}")
        logger.error(traceback.format_exc())
        
        try:
            await cleanup_resources()
        except Exception as cleanup_error:
            logger.error(f"❌ Ошибка аварийной очистки: {cleanup_error}")
            
        raise


def run_app():
    """Запуск приложения с корректной обработкой исключений"""
    try:
        if not Config.TELEGRAM_BOT_TOKEN or Config.TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
            logger.error("💥 ОШИБКА: Telegram Bot Token не настроен!")
            sys.exit(1)
        
        if not Config.get_database_url():
            logger.warning("⚠️ Database URL не настроен - БД будет отключена")
        
        # Запускаем приложение
        if hasattr(asyncio, 'run'):
            asyncio.run(main())
        else:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
            
    except KeyboardInterrupt:
        logger.info("🔴 Приложение остановлено пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка приложения: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    run_app()
