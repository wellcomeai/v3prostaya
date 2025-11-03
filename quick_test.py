import asyncio
import logging
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_strategy():
    from database import initialize_database
    from database.repositories import get_market_data_repository
    from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager
    from strategies import BreakoutStrategy
    
    # Инициализация
    await initialize_database()
    repository = await get_market_data_repository()
    ta_manager = TechnicalAnalysisContextManager(repository, auto_start_background_updates=False)
    
    # Тест одной стратегии
    symbol = "BTCUSDT"
    logger.info(f"🔍 Тестирование {symbol}...")
    
    # Загрузка данных
    now = datetime.now(timezone.utc)
    candles_1m = await repository.get_candles(symbol, "1m", start_time=now-timedelta(hours=1), limit=60)
    candles_5m = await repository.get_candles(symbol, "5m", start_time=now-timedelta(hours=5), limit=50)
    candles_1h = await repository.get_candles(symbol, "1h", start_time=now-timedelta(days=2), limit=48)
    candles_1d = await repository.get_candles(symbol, "1d", start_time=now-timedelta(days=180), limit=180)
    
    logger.info(f"📊 Свечи: 1m={len(candles_1m)}, 5m={len(candles_5m)}, 1h={len(candles_1h)}, 1d={len(candles_1d)}")
    
    # Технический контекст
    try:
        context = await ta_manager.get_context(symbol)
        logger.info(f"✅ Контекст получен: {context is not None}")
    except Exception as e:
        logger.error(f"❌ Ошибка контекста: {e}")
        context = None
    
    # Тест стратегии
    try:
        strategy = BreakoutStrategy(symbol, repository, ta_manager)
        
        signal = await strategy.analyze_with_data(
            symbol=symbol,
            candles_1m=candles_1m,
            candles_5m=candles_5m,
            candles_1h=candles_1h,
            candles_1d=candles_1d,
            ta_context=context
        )
        
        if signal:
            logger.info(f"✅ СИГНАЛ! {signal.signal_type.value} @ ${signal.price}")
        else:
            logger.info(f"ℹ️ Сигнала нет (условия не выполнены)")
            
    except Exception as e:
        logger.error(f"❌ ОШИБКА СТРАТЕГИИ: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_strategy())
