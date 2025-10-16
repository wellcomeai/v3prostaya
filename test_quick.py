#!/usr/bin/env python3
"""
Быстрый тест стратегий в Render Shell
Запуск: python test_quick.py
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

async def main():
    print("\n🔬 БЫСТРЫЙ ТЕСТ СТРАТЕГИЙ\n")
    
    # Импорты
    from database import initialize_database, close_database
    from database.repositories import get_market_data_repository
    from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager
    from strategies import BreakoutStrategy
    
    symbol = "BTCUSDT"  # Тестируемый символ
    
    try:
        # 1. БД
        print("1️⃣ Подключение к БД...")
        await initialize_database()
        repository = await get_market_data_repository()
        print("✅ БД готова\n")
        
        # 2. Technical Analysis
        print("2️⃣ Инициализация Technical Analysis...")
        ta_manager = TechnicalAnalysisContextManager(
            repository=repository,
            auto_start_background_updates=False
        )
        ta_context = await ta_manager.get_context(symbol)
        print(f"✅ Контекст создан для {symbol}\n")
        
        # 3. Получаем данные
        print("3️⃣ Загрузка данных из БД...")
        now = datetime.now(timezone.utc)
        
        candles_1m = await repository.get_candles(symbol, "1m", start_time=now-timedelta(hours=2), limit=100)
        candles_5m = await repository.get_candles(symbol, "5m", start_time=now-timedelta(hours=5), limit=50)
        candles_1h = await repository.get_candles(symbol, "1h", start_time=now-timedelta(hours=24), limit=24)
        candles_1d = await repository.get_candles(symbol, "1d", start_time=now-timedelta(days=180), limit=180)
        
        print(f"   M1: {len(candles_1m)} свечей")
        print(f"   M5: {len(candles_5m)} свечей")
        print(f"   H1: {len(candles_1h)} свечей")
        print(f"   D1: {len(candles_1d)} свечей")
        
        if candles_1m:
            current_price = float(candles_1m[-1]['close_price'])
            print(f"   💰 Текущая цена: ${current_price:,.2f}\n")
        
        # 4. Technical Analysis детали
        print("4️⃣ Технический анализ:")
        print(f"   📊 Уровней D1: {len(ta_context.levels_d1)}")
        if ta_context.levels_d1:
            for i, level in enumerate(ta_context.levels_d1[:3], 1):
                print(f"      #{i}: {level.level_type} @ ${level.price:,.2f} (strength={level.strength:.2f})")
        
        if ta_context.atr_data:
            print(f"   📈 ATR: {ta_context.atr_data.calculated_atr:.2f}")
            print(f"   🔋 Запас хода: {ta_context.atr_data.current_range_used*100:.1f}%")
        
        print(f"   🎯 Тренд: {ta_context.dominant_trend_h1.value if ta_context.dominant_trend_h1 else 'N/A'}")
        print(f"   💥 Консолидация: {'Да' if ta_context.consolidation_detected else 'Нет'}\n")
        
        # 5. Тест стратегии
        print("5️⃣ Анализ BreakoutStrategy...")
        strategy = BreakoutStrategy(
            symbol=symbol,
            ta_context_manager=ta_manager
        )
        
        signal = await strategy.analyze_with_data(
            symbol=symbol,
            candles_1m=candles_1m,
            candles_5m=candles_5m,
            candles_1h=candles_1h,
            candles_1d=candles_1d,
            ta_context=ta_context
        )
        
        if signal:
            print(f"   🔔 СИГНАЛ: {signal.signal_type.value}")
            print(f"   💪 Сила: {signal.strength:.2f}")
            print(f"   🎯 Уверенность: {signal.confidence:.2f}")
            print(f"   💵 Цена: ${signal.price:,.2f}")
            print(f"   📝 Причины:")
            for reason in signal.reasons:
                print(f"      • {reason}")
        else:
            print("   ℹ️  Нет сигнала")
        
        print("\n✅ ТЕСТ ЗАВЕРШЕН")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await close_database()

if __name__ == "__main__":
    asyncio.run(main())
