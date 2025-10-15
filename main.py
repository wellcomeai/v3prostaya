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

# Модульная архитектура
from market_data import MarketDataManager
from core import SignalManager, StrategyOrchestrator, DataSourceAdapter  # ✅ ИЗМЕНЕНИЕ 1: Добавлен DataSourceAdapter
from core.data_models import SystemConfig, StrategyConfig, create_default_system_config
from strategies import MomentumStrategy

# ✅ SimpleCandleSync для криптовалют (Bybit)
from market_data.simple_candle_sync import SimpleCandleSync

# ✅ SimpleFuturesSync для фьючерсов (YFinance)
from market_data.simple_futures_sync import SimpleFuturesSync

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

# ✅ ОБНОВЛЕНО: Глобальные переменные с DataSourceAdapter
bot_instance = None
market_data_manager = None
signal_manager = None
strategy_orchestrator = None
simple_candle_sync = None
simple_futures_sync = None
ta_context_manager = None
data_source_adapter = None  # ✅ ДОБАВЛЕНО
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
        
        # ✅ ОБНОВЛЕНО: Проверяем все компоненты включая DataSourceAdapter
        trading_system_status = {
            "simple_candle_sync": "inactive",
            "simple_futures_sync": "inactive",
            "ta_context_manager": "inactive",
            "data_source_adapter": "inactive",  # ✅ ДОБАВЛЕНО
            "market_data_manager": "inactive",
            "signal_manager": "inactive", 
            "strategy_orchestrator": "inactive",
            "strategies_active": 0
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
        
        # ✅ ДОБАВЛЕНО: DataSourceAdapter статус
        if data_source_adapter:
            try:
                trading_system_status["data_source_adapter"] = "active"
            except Exception as e:
                logger.warning(f"DataSourceAdapter health check failed: {e}")
                trading_system_status["data_source_adapter"] = "error"
        
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


# ========== YFINANCE STATUS ENDPOINTS ==========

async def yfinance_status_handler(request):
    """Проверка статуса YFinance WebSocket"""
    try:
        if not market_data_manager:
            return web.json_response({
                "status": "error",
                "message": "MarketDataManager not initialized"
            }, status=503)
        
        # Проверяем YFinance провайдер
        yf_provider = market_data_manager.yfinance_websocket_provider
        
        if not yf_provider:
            return web.json_response({
                "status": "disabled",
                "message": "YFinance WebSocket provider not initialized",
                "config": {
                    "enabled": Config.YFINANCE_WEBSOCKET_ENABLED,
                    "symbols": Config.get_yfinance_symbols()
                }
            })
        
        # Получаем статистику
        is_running = yf_provider.is_running()
        stats = yf_provider.get_current_stats()
        connection_stats = yf_provider.get_connection_stats()
        
        # Получаем снимки всех фьючерсов
        futures_snapshots = {}
        for symbol in Config.get_yfinance_symbols():
            snapshot = await market_data_manager.get_futures_snapshot(symbol)
            if snapshot:
                futures_snapshots[symbol] = snapshot.to_dict()
        
        response_data = {
            "status": "running" if is_running else "stopped",
            "is_running": is_running,
            "symbols": Config.get_yfinance_symbols(),
            "connection_stats": connection_stats,
            "current_stats": stats,
            "futures_snapshots": futures_snapshots,
            "timestamp": datetime.now().isoformat()
        }
        
        # Сериализуем datetime объекты
        response_data = serialize_datetime_objects(response_data)
        
        return web.json_response(response_data)
        
    except Exception as e:
        logger.error(f"Error getting YFinance status: {e}")
        logger.error(traceback.format_exc())
        return web.json_response({
            "status": "error",
            "error": str(e)
        }, status=500)


async def market_data_status_handler(request):
    """Полный статус всех источников данных (Bybit + YFinance)"""
    try:
        if not market_data_manager:
            return web.json_response({
                "status": "error",
                "message": "MarketDataManager not initialized"
            }, status=503)
        
        # Получаем общую статистику
        stats = market_data_manager.get_stats()
        health = market_data_manager.get_health_status()
        
        # Bybit статус
        bybit_status = {
            "websocket_active": stats.get('bybit_websocket_active', False),
            "rest_api_active": stats.get('rest_api_active', False),
            "websocket_updates": stats.get('bybit_websocket_updates', 0),
            "rest_api_calls": stats.get('bybit_rest_api_calls', 0),
            "symbols": Config.get_bybit_symbols(),
            "current_price": market_data_manager.get_current_price() if stats.get('bybit_websocket_active') else 0
        }
        
        # YFinance статус
        yfinance_status = {
            "websocket_active": stats.get('yfinance_websocket_active', False),
            "websocket_updates": stats.get('yfinance_websocket_updates', 0),
            "enabled": Config.YFINANCE_WEBSOCKET_ENABLED,
            "symbols": Config.get_yfinance_symbols()
        }
        
        # Получаем цены фьючерсов
        futures_prices = {}
        if Config.YFINANCE_WEBSOCKET_ENABLED and stats.get('yfinance_websocket_active'):
            for symbol in Config.get_yfinance_symbols():
                price = market_data_manager.get_futures_price(symbol)
                futures_prices[symbol] = price
        
        response_data = {
            "status": "ok",
            "overall_health": health['overall_status'],
            "bybit": bybit_status,
            "yfinance": yfinance_status,
            "futures_prices": futures_prices,
            "general_stats": {
                "uptime_formatted": stats.get('uptime_formatted', '0:00:00'),
                "total_snapshots": stats.get('data_snapshots_created', 0),
                "futures_snapshots": stats.get('futures_snapshots_created', 0),
                "errors": stats.get('errors', 0),
                "success_rate": stats.get('success_rate_percent', 100)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        # Сериализуем datetime объекты
        response_data = serialize_datetime_objects(response_data)
        
        return web.json_response(response_data)
        
    except Exception as e:
        logger.error(f"Error getting market data status: {e}")
        logger.error(traceback.format_exc())
        return web.json_response({
            "status": "error",
            "error": str(e)
        }, status=500)


# ========== ОСТАЛЬНЫЕ ENDPOINTS ==========

async def trading_system_status_handler(request):
    """Endpoint для статуса торговой системы"""
    try:
        # ✅ ОБНОВЛЕНО: Включаем DataSourceAdapter
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
        
        # ✅ ДОБАВЛЕНО: DataSourceAdapter статус
        if data_source_adapter:
            try:
                response_data["data_source_adapter"] = {
                    "crypto_symbols": len(data_source_adapter.crypto_symbols),
                    "futures_symbols": len(data_source_adapter.futures_symbols),
                    "status": "active"
                }
            except Exception as e:
                logger.warning(f"Failed to get data_source_adapter stats: {e}")
                response_data["data_source_adapter"] = {"error": str(e)}
        
        # MarketDataManager статус
        if market_data_manager:
            try:
                response_data["market_data_manager"] = market_data_manager.get_stats()
            except Exception as e:
                logger.warning(f"Failed to get market data stats: {e}")
                response_data["market_data_manager"] = {"error": str(e)}
        
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
                "data_source_adapter": "active" if data_source_adapter else None,  # ✅ ДОБАВЛЕНО
                "market_data": market_data_manager.get_health_status() if market_data_manager else None,
                "strategies": strategy_orchestrator.get_health_status() if strategy_orchestrator else None
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


async def load_historical_data_handler(request):
    """Endpoint для загрузки исторических данных через API"""
    try:
        # Проверяем что БД инициализирована
        if not database_initialized:
            return web.json_response({
                "status": "error",
                "message": "Database not initialized"
            }, status=503)
        
        # Получаем параметры из request
        try:
            if request.content_type == 'application/json':
                data = await request.json()
            else:
                data = {}
        except Exception as e:
            logger.warning(f"Failed to parse JSON, using defaults: {e}")
            data = {}
        
        # Параметры по умолчанию
        symbol = data.get('symbol', Config.SYMBOL)
        days = int(data.get('days', 7))
        intervals = data.get('intervals', ["1m", "5m", "1h", "1d"])
        testnet = data.get('testnet', Config.BYBIT_TESTNET)
        
        # Валидация параметров
        if days <= 0 or days > 365:
            return web.json_response({
                "status": "error",
                "message": "Days must be between 1 and 365"
            }, status=400)
        
        if not isinstance(intervals, list) or len(intervals) == 0:
            return web.json_response({
                "status": "error", 
                "message": "Intervals must be a non-empty list"
            }, status=400)
        
        logger.info(f"🚀 Запуск загрузки исторических данных:")
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Days: {days}")
        logger.info(f"   Intervals: {intervals}")
        logger.info(f"   Testnet: {testnet}")
        
        # Проверяем доступность pybit
        try:
            from pybit.unified_trading import HTTP
            logger.info("✅ pybit library available")
        except ImportError as e:
            logger.error(f"❌ pybit library not installed: {e}")
            return web.json_response({
                "status": "error",
                "message": "pybit library not installed. Please install with: pip install pybit>=5.3.0",
                "details": str(e)
            }, status=500)
        
        # Проверяем БД подключение
        try:
            from database.connections import get_connection_manager
            db_manager = await get_connection_manager()
            health = await db_manager.get_health_status()
            
            if not health.get("healthy", False):
                return web.json_response({
                    "status": "error",
                    "message": "Database connection unhealthy",
                    "db_status": health
                }, status=503)
                
            logger.info("✅ Database connection verified")
            
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            return web.json_response({
                "status": "error",
                "message": f"Database connection failed: {str(e)}"
            }, status=503)
        
        # Пробуем создать и инициализировать загрузчик
        start_time = datetime.now()
        
        try:
            logger.info("📦 Importing loader components...")
            from database.loaders import create_historical_loader
            
            logger.info("🔧 Creating historical data loader...")
            loader = await create_historical_loader(
                symbol=symbol,
                testnet=testnet,
                enable_progress_tracking=True,
                max_concurrent_requests=2,
                batch_size=500
            )
            
            logger.info("✅ Loader created and initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to create/initialize loader: {e}")
            logger.error(f"Loader creation traceback: {traceback.format_exc()}")
            
            return web.json_response({
                "status": "error",
                "message": f"Failed to initialize data loader: {str(e)}",
                "error_type": type(e).__name__,
                "parameters": {
                    "symbol": symbol,
                    "testnet": testnet
                }
            }, status=500)
        
        # Запускаем загрузку данных
        try:
            logger.info("📥 Starting data loading process...")
            
            from database.loaders import load_year_data
            
            result = await load_year_data(
                symbol=symbol,
                intervals=intervals,
                testnet=testnet,
                start_date=datetime.now() - timedelta(days=days)
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info(f"✅ Загрузка данных завершена за {duration:.1f}s")
            
        except Exception as e:
            logger.error(f"❌ Data loading failed: {e}")
            logger.error(f"Loading traceback: {traceback.format_exc()}")
            
            return web.json_response({
                "status": "error",
                "message": f"Data loading failed: {str(e)}",
                "error_type": type(e).__name__,
                "parameters": {
                    "symbol": symbol,
                    "days": days,
                    "intervals": intervals
                }
            }, status=500)
        
        finally:
            try:
                if 'loader' in locals():
                    await loader.close()
                    logger.info("🔐 Loader resources closed")
            except Exception as e:
                logger.warning(f"⚠️ Error closing loader: {e}")
        
        # Проверяем результат
        try:
            db_manager = await get_connection_manager()
            count_result = await db_manager.fetchval(
                "SELECT COUNT(*) FROM market_data_candles WHERE symbol = $1", 
                symbol.upper()
            )
            total_candles = count_result if count_result else 0
            
        except Exception as e:
            logger.warning(f"Failed to count candles: {e}")
            total_candles = "unknown"
        
        response_data = {
            "status": "success",
            "message": f"Historical data loaded successfully for {symbol}",
            "parameters": {
                "symbol": symbol,
                "days": days,
                "intervals": intervals,
                "testnet": testnet
            },
            "result": result,
            "duration_seconds": round(duration, 2),
            "total_candles_in_db": total_candles,
            "timestamp": datetime.now().isoformat()
        }
        
        response_data = serialize_datetime_objects(response_data)
        
        return web.json_response(response_data)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в load_historical_data_handler: {e}")
        logger.error(f"Handler traceback: {traceback.format_exc()}")
        
        return web.json_response({
            "status": "error", 
            "message": str(e),
            "error_type": type(e).__name__,
            "timestamp": datetime.now().isoformat()
        }, status=500)


async def check_database_data_handler(request):
    """Endpoint для проверки данных в БД"""
    try:
        if not database_initialized:
            return web.json_response({
                "status": "error",
                "message": "Database not initialized"
            }, status=503)
        
        from database.connections import get_connection_manager
        db_manager = await get_connection_manager()
        
        # Общая статистика
        total_count = await db_manager.fetchval("SELECT COUNT(*) FROM market_data_candles")
        
        # Статистика по символам и интервалам
        stats_query = """
        SELECT 
            symbol, 
            interval, 
            COUNT(*) as count,
            MIN(open_time) as earliest_data,
            MAX(open_time) as latest_data,
            MAX(open_time) - MIN(open_time) as data_range,
            MAX(created_at) as last_inserted,
            data_source
        FROM market_data_candles 
        GROUP BY symbol, interval, data_source
        ORDER BY symbol, interval
        """
        
        stats_results = await db_manager.fetch(stats_query)
        
        # Последние записи
        latest_query = """
        SELECT symbol, interval, open_time, close_price, volume, data_source, created_at
        FROM market_data_candles 
        ORDER BY created_at DESC 
        LIMIT 10
        """
        
        latest_results = await db_manager.fetch(latest_query)
        
        response_data = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_candles": total_count,
                "symbols_intervals": len(stats_results)
            },
            "data_by_interval": [
                {
                    "symbol": row["symbol"],
                    "interval": row["interval"], 
                    "count": row["count"],
                    "data_source": row.get("data_source", "unknown"),
                    "earliest_data": row["earliest_data"].isoformat() if row["earliest_data"] else None,
                    "latest_data": row["latest_data"].isoformat() if row["latest_data"] else None,
                    "data_range_days": row["data_range"].days if row["data_range"] else 0,
                    "last_inserted": row["last_inserted"].isoformat() if row["last_inserted"] else None
                }
                for row in stats_results
            ],
            "latest_entries": [
                {
                    "symbol": row["symbol"],
                    "interval": row["interval"],
                    "open_time": row["open_time"].isoformat(),
                    "close_price": float(row["close_price"]),
                    "volume": float(row["volume"]),
                    "data_source": row.get("data_source", "unknown"),
                    "created_at": row["created_at"].isoformat()
                }
                for row in latest_results
            ]
        }
        
        return web.json_response(response_data)
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки данных БД: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }, status=500)


async def get_strategies_handler(request):
    """Endpoint для получения списка доступных стратегий"""
    try:
        from strategies import get_available_strategies
        
        strategies = []
        for key, info in get_available_strategies().items():
            strategies.append({
                "value": key,
                "label": info["name"],
                "description": info["description"]
            })
        
        logger.info(f"📊 Возвращено {len(strategies)} доступных стратегий")
        
        return web.json_response({
            "status": "success",
            "strategies": strategies,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения стратегий: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }, status=500)


async def run_backtest_handler(request):
    """Endpoint для бэктестинга с умной агрегацией данных"""
    try:
        if not database_initialized:
            return web.json_response({
                "status": "error",
                "message": "Database not initialized"
            }, status=503)
        
        # GET запрос - возвращаем интерактивный дашборд
        if request.method == 'GET':
            from backtesting import ReportGenerator
            html = ReportGenerator.generate_dashboard_html()
            return web.Response(text=html, content_type='text/html')
        
        # POST запрос - выполняем бэктест и возвращаем JSON
        try:
            params = await request.json()
        except:
            return web.json_response({
                "status": "error",
                "message": "Invalid JSON"
            }, status=400)
        
        symbol = params.get('symbol', Config.SYMBOL)
        interval = params.get('interval', '1h')
        initial_capital = float(params.get('initial_capital', 10000))
        strategy_type = params.get('strategy', 'momentum')
        
        # Параметры периода (опционально)
        days = params.get('days', 365)  # По умолчанию 365 дней
        
        logger.info(f"🎯 Запуск бэктестинга: {symbol}, {interval}, капитал=${initial_capital:,.2f}, стратегия={strategy_type}, период={days}д")
        
        # Импорты
        from backtesting import BacktestEngine, ReportGenerator
        from database.repositories import get_market_data_repository
        from strategies import create_strategy, get_available_strategies
        
        # Проверяем доступность стратегии
        available_strategies = get_available_strategies()
        if strategy_type not in available_strategies:
            return web.json_response({
                "status": "error",
                "message": f"Strategy '{strategy_type}' not available",
                "available_strategies": list(available_strategies.keys())
            }, status=400)
        
        # Загружаем данные через репозиторий с умной агрегацией
        repository = await get_market_data_repository()
        
        # Определяем временной диапазон
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        logger.info(f"📊 Загрузка данных из БД: {start_time.date()} - {end_time.date()}")
        
        try:
            # Используем get_candles_smart для автоматической агрегации
            candles_raw = await repository.get_candles_smart(
                symbol=symbol.upper(),
                interval=interval,
                start_time=start_time,
                end_time=end_time
            )
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки данных: {e}")
            logger.error(traceback.format_exc())
            return web.json_response({
                "status": "error",
                "message": f"Failed to load data: {str(e)}"
            }, status=500)
        
        if not candles_raw:
            return web.json_response({
                "status": "error",
                "message": f"No data found for {symbol} {interval} in specified period. Try loading historical data first via /admin/load-history"
            }, status=404)
        
        # Преобразуем в формат для бэктеста
        candles = []
        for candle in candles_raw:
            candles.append({
                'symbol': candle['symbol'],
                'interval': candle['interval'],
                'open_time': candle['open_time'].isoformat() if isinstance(candle['open_time'], datetime) else candle['open_time'],
                'close_time': candle['close_time'].isoformat() if isinstance(candle['close_time'], datetime) else candle['close_time'],
                'open': float(candle['open']),
                'high': float(candle['high']),
                'low': float(candle['low']),
                'close': float(candle['close']),
                'volume': float(candle['volume'])
            })
        
        logger.info(f"📊 Загружено {len(candles)} свечей ({interval}) из БД")
        logger.info(f"   • Период: {candles[0]['open_time']} - {candles[-1]['open_time']}")
        
        # Создаем стратегию
        try:
            strategy = create_strategy(
                strategy_type=strategy_type,
                symbol=symbol,
                min_signal_strength=0.5,
                signal_cooldown_minutes=60
            )
            logger.info(f"✅ Стратегия '{strategy_type}' создана успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка создания стратегии: {e}")
            return web.json_response({
                "status": "error",
                "message": f"Failed to create strategy: {str(e)}"
            }, status=500)
        
        # Создаем движок бэктестинга
        engine = BacktestEngine(
            initial_capital=initial_capital,
            commission_rate=0.001,
            position_size_pct=0.95
        )
        
        # Запускаем бэктест
        result = await engine.run_backtest(candles, strategy, symbol)
        
        # Возвращаем JSON
        json_data = ReportGenerator.generate_backtest_json(result)
        
        logger.info(f"✅ Бэктест завершен: PnL={result.total_pnl_percent:+.2f}%")
        
        return web.json_response(json_data)
        
    except Exception as e:
        logger.error(f"❌ Ошибка бэктестинга: {e}")
        logger.error(traceback.format_exc())
        
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)


async def root_handler(request):
    """Root endpoint с информацией о системе"""
    try:
        system_info = {
            "message": "Bybit Trading Bot v2.5 - DataSourceAdapter Edition",
            "features": [
                "✅ PostgreSQL Database Integration",
                "✅ Historical Data Storage", 
                "✅ SimpleCandleSync - REST API Based Sync (Crypto)",
                "✅ SimpleFuturesSync - YFinance REST API Sync (Futures)",
                "✅ TechnicalAnalysisContextManager - Full TA Integration",
                "🆕 DataSourceAdapter - Universal Data Provider",
                "✅ Bybit WebSocket (Ticker Only - Optional)",
                "✅ Strategy Orchestration System (Works WITHOUT WebSocket!)",
                "✅ Advanced Signal Management",
                "✅ OpenAI Integration",
                "✅ Telegram Notifications",
                "✅ Historical Data Loading via API",
                "✅ Backtesting Engine with Interactive Dashboard",
                "✅ Dynamic Strategy Loading",
                "✅ Smart Candle Aggregation",
                "🚀 Production Ready - Maximum Reliability"
            ],
            "status": "active",
            "timestamp": datetime.now().isoformat(),
            "database_enabled": database_initialized,
            "simple_candle_sync_active": bool(simple_candle_sync and simple_candle_sync.is_running),
            "simple_futures_sync_active": bool(simple_futures_sync and simple_futures_sync.is_running),
            "ta_context_manager_active": bool(ta_context_manager and ta_context_manager.is_running),
            "data_source_adapter_active": bool(data_source_adapter),  # ✅ ДОБАВЛЕНО
            "environment": Config.ENVIRONMENT,
            "webhook_path": WEBHOOK_PATH,
            "api_endpoints": {
                "health": "/health",
                "database_status": "/database/status", 
                "trading_status": "/trading/status",
                "simple_sync_status": "/admin/sync-status",
                "futures_sync_status": "/admin/futures-sync-status",
                "ta_context_status": "/admin/ta-context-status",
                "market_data_status": "/admin/market-data-status",
                "yfinance_status": "/admin/yfinance-status",
                "check_data": "/admin/check-data",
                "load_history": "/admin/load-history (POST)",
                "strategies": "/backtest/strategies (GET)",
                "backtest_get": "/backtest/run (GET)",
                "backtest_post": "/backtest/run (POST)"
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
                system_info["ta_updates_total"] = ta_context_manager.stats.get("total_updates", 0)
            except Exception as e:
                logger.warning(f"Failed to get TechnicalAnalysisContextManager status: {e}")
        
        # ✅ ДОБАВЛЕНО: DataSourceAdapter info
        if data_source_adapter:
            try:
                system_info["data_source_adapter_info"] = {
                    "crypto_symbols": len(data_source_adapter.crypto_symbols),
                    "futures_symbols": len(data_source_adapter.futures_symbols)
                }
            except Exception as e:
                logger.warning(f"Failed to get DataSourceAdapter info: {e}")
        
        if market_data_manager:
            try:
                system_info["market_data_status"] = market_data_manager.get_health_status().get("overall_status", "unknown")
            except Exception as e:
                logger.warning(f"Failed to get market data status: {e}")
                system_info["market_data_status"] = "error"
        
        if strategy_orchestrator:
            try:
                system_info["active_strategies"] = strategy_orchestrator._count_active_strategies()
                system_info["orchestrator_mode"] = "WebSocket (real-time)" if market_data_manager else "REST API (1 min)"
            except Exception as e:
                logger.warning(f"Failed to get active strategies count: {e}")
                system_info["active_strategies"] = 0
        
        if bot_instance:
            try:
                system_info["signal_subscribers"] = len(bot_instance.signal_subscribers)
            except Exception as e:
                logger.warning(f"Failed to get signal subscribers count: {e}")
                system_info["signal_subscribers"] = 0
        
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
    """✅ ОБНОВЛЕНО: Освобождение всех ресурсов включая DataSourceAdapter"""
    global bot_instance, market_data_manager, signal_manager, strategy_orchestrator
    global simple_candle_sync, simple_futures_sync, ta_context_manager, data_source_adapter, database_initialized
    
    try:
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
        
        # ✅ DataSourceAdapter не требует явной остановки (нет фоновых задач)
        if data_source_adapter:
            logger.info("✅ DataSourceAdapter очищен")
            data_source_adapter = None
        
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


async def initialize_trading_system():
    """✅ ИЗМЕНЕНИЕ 2: Полностью обновленная инициализация с DataSourceAdapter"""
    global market_data_manager, signal_manager, strategy_orchestrator
    global simple_candle_sync, simple_futures_sync, ta_context_manager, data_source_adapter, system_config
    
    try:
        logger.info("🚀 Инициализация торговой системы с DataSourceAdapter...")
        
        # Создаем конфигурацию системы
        system_config = create_default_system_config()
        system_config.trading_mode = system_config.trading_mode.PAPER
        system_config.bybit_testnet = Config.BYBIT_TESTNET
        system_config.default_symbol = Config.SYMBOL
        
        # ✅ ШАГ 1: SimpleCandleSync для крипты (Bybit)
        logger.info("🔄 Инициализация SimpleCandleSync для криптовалют...")
        from database.repositories import get_market_data_repository
        from bybit_client import BybitClient
        
        repository = await get_market_data_repository()
        bybit_client = BybitClient()
        
        # Создаем SimpleCandleSync
        simple_candle_sync = SimpleCandleSync(
            symbols=Config.get_bybit_symbols(),
            bybit_client=bybit_client,
            repository=repository,
            check_gaps_on_start=True
        )
        
        # Запускаем синхронизацию
        await simple_candle_sync.start()
        logger.info("✅ SimpleCandleSync запущен и работает")
        logger.info(f"   • Символы: {', '.join(Config.get_bybit_symbols())}")
        logger.info(f"   • Интервалы: 1m, 5m, 15m, 1h, 4h, 1d")
        
        # ✅ ШАГ 2: SimpleFuturesSync для фьючерсов (YFinance)
        logger.info("🔄 Инициализация SimpleFuturesSync для фьючерсов...")
        
        futures_symbols = Config.get_yfinance_symbols() if hasattr(Config, 'get_yfinance_symbols') else []
        
        if futures_symbols:
            simple_futures_sync = SimpleFuturesSync(
                symbols=futures_symbols,
                repository=repository,
                check_gaps_on_start=True
            )
            
            await simple_futures_sync.start()
            logger.info("✅ SimpleFuturesSync запущен и работает")
            logger.info(f"   • Символы: {', '.join(futures_symbols)}")
            logger.info(f"   • Интервалы: 1m, 5m, 15m, 1h, 4h, 1d")
        else:
            logger.info("⏭️ SimpleFuturesSync пропущен (нет фьючерсных символов в Config)")
            simple_futures_sync = None
        
        # ✅ ШАГ 3: TechnicalAnalysisContextManager (КРИТИЧНО ДЛЯ СТРАТЕГИЙ!)
        logger.info("🧠 Инициализация TechnicalAnalysisContextManager...")
        from strategies.technical_analysis import TechnicalAnalysisContextManager
        
        ta_context_manager = TechnicalAnalysisContextManager(
            repository=repository,
            auto_start_background_updates=True
        )
        
        # Запускаем фоновые обновления
        await ta_context_manager.start_background_updates()
        
        logger.info("✅ TechnicalAnalysisContextManager запущен")
        logger.info("   • Уровни D1: обновление каждые 24 часа")
        logger.info("   • ATR: обновление каждый час")
        logger.info("   • Свечи: обновление каждую минуту")
        logger.info("   • Рыночные условия: обновление каждые 15 минут")
        logger.info("   • Анализаторы: 5 (Levels, ATR, Patterns, Breakouts, Market)")
        
        # ✅ ШАГ 4: MarketDataManager (ОПЦИОНАЛЬНО - только для WebSocket ticker)
        if Config.BYBIT_WEBSOCKET_ENABLED:
            logger.info("📊 Инициализация MarketDataManager (только WebSocket ticker)...")
            market_data_manager = MarketDataManager(
                symbols_crypto=Config.get_bybit_symbols(),
                symbols_futures=[],
                testnet=Config.BYBIT_TESTNET,
                enable_bybit_websocket=True,
                enable_yfinance_websocket=False,
                enable_rest_api=False,
                enable_candle_sync=False,
                rest_cache_minutes=Config.REST_API_CACHE_MINUTES,
                websocket_reconnect=Config.WEBSOCKET_RECONNECT_ENABLED
            )
            
            market_data_started = await market_data_manager.start()
            if market_data_started:
                logger.info("✅ MarketDataManager (ticker only) активен")
            else:
                logger.warning("⚠️ MarketDataManager не запустился, продолжаем без WebSocket")
                market_data_manager = None
        else:
            logger.info("⏭️ WebSocket отключен в конфиге, используем только SimpleCandleSync")
            market_data_manager = None
        
        # ✅ ШАГ 5: SignalManager
        logger.info("🎛️ Инициализация SignalManager...")
        signal_manager = SignalManager(
            max_queue_size=1000,
            notification_settings=system_config.notification_settings
        )
        
        # Подписываем Telegram бота на сигналы
        if bot_instance:
            signal_manager.add_subscriber(bot_instance.broadcast_signal)
            logger.info("📡 Telegram бот подписан на торговые сигналы")
        
        # Запускаем менеджер сигналов
        await signal_manager.start()
        logger.info("✅ SignalManager запущен")
        
        # ✅ ШАГ 6: DataSourceAdapter - НОВЫЙ КОМПОНЕНТ!
        logger.info("🔌 Создание DataSourceAdapter...")
        data_source_adapter = DataSourceAdapter(
            ta_context_manager=ta_context_manager,
            simple_candle_sync=simple_candle_sync,
            simple_futures_sync=simple_futures_sync,
            default_symbols=Config.get_bybit_symbols() + (Config.get_yfinance_symbols() if hasattr(Config, 'get_yfinance_symbols') else [])
        )
        logger.info("✅ DataSourceAdapter создан")
        
        # ✅ ШАГ 7: StrategyOrchestrator - ТЕПЕРЬ ВСЕГДА ЗАПУСКАЕТСЯ!
        logger.info("🎭 Инициализация StrategyOrchestrator...")
        
        # Определяем источник данных
        if market_data_manager:
            logger.info("   • Источник данных: MarketDataManager (WebSocket)")
            strategy_orchestrator = StrategyOrchestrator(
                signal_manager=signal_manager,
                market_data_manager=market_data_manager,
                ta_context_manager=ta_context_manager,
                system_config=system_config,
                analysis_interval=30.0,
                max_concurrent_analyses=3,
                enable_performance_monitoring=True
            )
        else:
            logger.info("   • Источник данных: DataSourceAdapter (REST API)")
            strategy_orchestrator = StrategyOrchestrator(
                signal_manager=signal_manager,
                data_source_adapter=data_source_adapter,
                ta_context_manager=ta_context_manager,
                system_config=system_config,
                analysis_interval=60.0,  # 60 секунд для REST API
                max_concurrent_analyses=3,
                enable_performance_monitoring=True
            )
        
        # Запускаем оркестратор
        orchestrator_started = await strategy_orchestrator.start()
        if orchestrator_started:
            logger.info("✅ StrategyOrchestrator активен")
        else:
            logger.warning("⚠️ StrategyOrchestrator не запустился")
            strategy_orchestrator = None
        
        # ✅ ИЗМЕНЕНИЕ 3: ФИНАЛЬНАЯ СТАТИСТИКА
        logger.info("=" * 70)
        logger.info("✅ ТОРГОВАЯ СИСТЕМА ЗАПУЩЕНА УСПЕШНО!")
        logger.info("=" * 70)
        logger.info(f"🔄 SimpleCandleSync (Crypto): ✅ АКТИВЕН")
        logger.info(f"   • Символы: {len(Config.get_bybit_symbols())}")
        logger.info(f"   • Интервалы: 6 (1m, 5m, 15m, 1h, 4h, 1d)")
        
        if simple_futures_sync:
            logger.info(f"🔄 SimpleFuturesSync (Futures): ✅ АКТИВЕН")
            logger.info(f"   • Символы: {len(futures_symbols)}")
            logger.info(f"   • Интервалы: 6 (1m, 5m, 15m, 1h, 4h, 1d)")
        else:
            logger.info(f"🔄 SimpleFuturesSync: ❌ ОТКЛЮЧЕН")
        
        logger.info(f"🧠 TechnicalAnalysis: {'✅ АКТИВЕН' if ta_context_manager else '❌ ОТКЛЮЧЕН'}")
        if ta_context_manager:
            logger.info(f"   • Анализаторы: LevelAnalyzer, ATRCalculator, PatternDetector,")
            logger.info(f"                 BreakoutAnalyzer, MarketConditionsAnalyzer")
        
        logger.info(f"🔌 DataSourceAdapter: ✅ СОЗДАН")
        logger.info(f"   • Криптовалюты: {len(data_source_adapter.crypto_symbols)}")
        logger.info(f"   • Фьючерсы: {len(data_source_adapter.futures_symbols)}")
        
        logger.info(f"📊 WebSocket ticker: {'✅ АКТИВЕН' if market_data_manager else '❌ ОТКЛЮЧЕН'}")
        logger.info(f"🎛️ SignalManager: ✅ АКТИВЕН")
        logger.info(f"🎭 StrategyOrchestrator: {'✅ АКТИВЕН' if strategy_orchestrator else '❌ ОТКЛЮЧЕН'}")
        if strategy_orchestrator:
            logger.info(f"   • Режим: {'WebSocket (real-time)' if market_data_manager else 'REST API (1 min)'}")
        logger.info("=" * 70)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка инициализации торговой системы: {e}")
        logger.error(traceback.format_exc())
        return False


async def create_app():
    """Создание веб-приложения"""
    global bot_instance
    
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК BYBIT TRADING BOT v2.5")
    logger.info("   DataSourceAdapter Edition")
    logger.info("=" * 60)
    
    # Шаг 1: Инициализация базы данных
    db_success = await initialize_database_system()
    if not db_success:
        logger.error("💥 Критическая ошибка: не удалось инициализировать БД")
        if Config.is_production():
            raise Exception("Database initialization failed in production")
        else:
            logger.warning("⚠️ Продолжаем без базы данных (только для разработки)")
    
    # Шаг 2: Создаем экземпляр бота
    logger.info("🤖 Инициализация Telegram бота...")
    bot_instance = TelegramBot(Config.TELEGRAM_BOT_TOKEN)
    
    # Шаг 3: Инициализируем торговую систему
    trading_system_started = await initialize_trading_system()
    if trading_system_started:
        logger.info("✅ Торговая система активна")
        logger.info(f"📊 Crypto: {', '.join(Config.get_bybit_symbols())}")
        futures_symbols = Config.get_yfinance_symbols() if hasattr(Config, 'get_yfinance_symbols') else []
        if futures_symbols:
            logger.info(f"📊 Futures: {', '.join(futures_symbols)}")
        logger.info(f"🧠 Technical Analysis: {'✅ Active' if ta_context_manager else '❌ Inactive'}")
        logger.info(f"🔌 Data Source Adapter: {'✅ Active' if data_source_adapter else '❌ Inactive'}")
        logger.info(f"🎭 Strategy Mode: {'WebSocket' if market_data_manager else 'REST API'}")
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
    
    # Endpoints для работы с историческими данными
    app.router.add_post("/admin/load-history", load_historical_data_handler)
    app.router.add_get("/admin/check-data", check_database_data_handler)
    
    # SimpleCandleSync + SimpleFuturesSync + TechnicalAnalysisContextManager endpoints
    app.router.add_get("/admin/sync-status", simple_sync_status_handler)
    app.router.add_get("/admin/futures-sync-status", futures_sync_status_handler)
    app.router.add_get("/admin/ta-context-status", ta_context_status_handler)
    
    # YFinance endpoints
    app.router.add_get("/admin/yfinance-status", yfinance_status_handler)
    app.router.add_get("/admin/market-data-status", market_data_status_handler)
    
    # Бэктестинг endpoints
    app.router.add_get("/backtest/strategies", get_strategies_handler)
    app.router.add_post("/backtest/run", run_backtest_handler)
    app.router.add_get("/backtest/run", run_backtest_handler)
    
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
        logger.info("🌟 Запуск Bybit Trading Bot v2.5 - DataSourceAdapter Edition")
        logger.info(f"🔧 Порт: {WEB_SERVER_PORT}")
        logger.info(f"🔧 Webhook URL: {BASE_WEBHOOK_URL}{WEBHOOK_PATH}")
        logger.info(f"🔧 Testnet: {Config.BYBIT_TESTNET}")
        logger.info(f"🔧 Crypto: {', '.join(Config.get_bybit_symbols())}")
        
        futures_symbols = Config.get_yfinance_symbols() if hasattr(Config, 'get_yfinance_symbols') else []
        if futures_symbols:
            logger.info(f"🔧 Futures: {', '.join(futures_symbols)}")
        
        logger.info(f"🔧 Environment: {Config.ENVIRONMENT}")
        logger.info(f"🔧 Database: {'настроена' if Config.get_database_url() else 'НЕ НАСТРОЕНА'}")
        
        # Создаем приложение
        app = await create_app()
        
        # Запускаем веб-сервер
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
        await site.start()
        
        logger.info("=" * 60)
        logger.info("✅ ПРИЛОЖЕНИЕ УСПЕШНО ЗАПУЩЕНО")
        logger.info("=" * 60)
        logger.info(f"🌐 Веб-сервер: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
        logger.info(f"🤖 Telegram бот: активен")
        logger.info(f"🗄️ База данных: {'подключена' if database_initialized else 'отключена'}")
        logger.info(f"🔄 SimpleCandleSync: {'активен' if simple_candle_sync and simple_candle_sync.is_running else 'неактивен'}")
        logger.info(f"🔄 SimpleFuturesSync: {'активен' if simple_futures_sync and simple_futures_sync.is_running else 'неактивен'}")
        logger.info(f"🧠 TechnicalAnalysis: {'активен' if ta_context_manager and ta_context_manager.is_running else 'неактивен'}")
        logger.info(f"🔌 DataSourceAdapter: {'создан' if data_source_adapter else 'не создан'}")
        logger.info(f"🚀 Торговая система: {'активна' if strategy_orchestrator and strategy_orchestrator.is_running else 'неактивна'}")
        if strategy_orchestrator:
            logger.info(f"   • Режим работы: {'WebSocket (real-time)' if market_data_manager else 'REST API (1 min)'}")
        logger.info("=" * 60)
        logger.info("📡 Endpoints:")
        logger.info(f"   • Health: {BASE_WEBHOOK_URL}/health")
        logger.info(f"   • Database: {BASE_WEBHOOK_URL}/database/status")
        logger.info(f"   • Trading: {BASE_WEBHOOK_URL}/trading/status")
        logger.info(f"   • Crypto Sync: {BASE_WEBHOOK_URL}/admin/sync-status")
        logger.info(f"   • Futures Sync: {BASE_WEBHOOK_URL}/admin/futures-sync-status")
        logger.info(f"   • TA Context: {BASE_WEBHOOK_URL}/admin/ta-context-status")
        logger.info(f"   • Market Data: {BASE_WEBHOOK_URL}/admin/market-data-status")
        logger.info(f"   • Check Data: {BASE_WEBHOOK_URL}/admin/check-data")
        logger.info(f"   • Load History: {BASE_WEBHOOK_URL}/admin/load-history")
        logger.info(f"   • Strategies: {BASE_WEBHOOK_URL}/backtest/strategies")
        logger.info(f"   • Backtest: {BASE_WEBHOOK_URL}/backtest/run")
        logger.info("=" * 60)
        
        # Основной цикл приложения
        try:
            while True:
                await asyncio.sleep(3600)
                
                # Мониторинг SimpleCandleSync
                if simple_candle_sync and not simple_candle_sync.is_running:
                    logger.warning("⚠️ SimpleCandleSync остановился, перезапуск...")
                    try:
                        await simple_candle_sync.start()
                        logger.info("✅ SimpleCandleSync перезапущен")
                    except Exception as e:
                        logger.error(f"❌ Не удалось перезапустить SimpleCandleSync: {e}")
                
                # Мониторинг SimpleFuturesSync
                if simple_futures_sync and not simple_futures_sync.is_running:
                    logger.warning("⚠️ SimpleFuturesSync остановился, перезапуск...")
                    try:
                        await simple_futures_sync.start()
                        logger.info("✅ SimpleFuturesSync перезапущен")
                    except Exception as e:
                        logger.error(f"❌ Не удалось перезапустить SimpleFuturesSync: {e}")
                
                # Мониторинг TechnicalAnalysisContextManager
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
                
                # Статистика
                if bot_instance:
                    try:
                        subscribers_count = len(bot_instance.signal_subscribers)
                        strategies_active = strategy_orchestrator._count_active_strategies() if strategy_orchestrator else 0
                        db_status = "OK" if database_initialized else "OFF"
                        
                        crypto_synced = simple_candle_sync.get_stats().get('candles_synced', 0) if simple_candle_sync else 0
                        futures_synced = simple_futures_sync.get_stats().get('candles_synced', 0) if simple_futures_sync else 0
                        ta_contexts = len(ta_context_manager.contexts) if ta_context_manager else 0
                        
                        logger.info(f"📊 Статистика:")
                        logger.info(f"   • Подписчики: {subscribers_count}")
                        logger.info(f"   • Крипта свечей: {crypto_synced}")
                        logger.info(f"   • Фьючерсы свечей: {futures_synced}")
                        logger.info(f"   • TA контекстов: {ta_contexts}")
                        logger.info(f"   • Стратегии: {strategies_active}")
                        logger.info(f"   • Режим оркестратора: {'WebSocket' if market_data_manager else 'REST API'}")
                        logger.info(f"   • БД: {db_status}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось получить статистику: {e}")
                
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
