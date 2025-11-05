#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '/opt/render/project/src')

from database import initialize_database
from database.repositories import get_market_data_repository
from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager

async def test():
    await initialize_database()
    repo = await get_market_data_repository()
    ta_mgr = TechnicalAnalysisContextManager(repo, auto_start_background_updates=False)
    
    symbol = "BTCUSDT"
    
    print(f"\n🔍 Получение TA Context для {symbol}...")
    ta_context = await ta_mgr.get_context(symbol)
    
    print(f"\n📊 РЕАЛЬНАЯ СТРУКТУРА TechnicalAnalysisContext:")
    print(f"   Type: {type(ta_context)}")
    print(f"   Symbol: {ta_context.symbol}")
    
    # ========== ПРАВИЛЬНЫЕ АТРИБУТЫ ==========
    
    print(f"\n✅ УРОВНИ:")
    print(f"   • levels_d1: {len(ta_context.levels_d1)} уровней")
    if ta_context.levels_d1:
        for i, level in enumerate(ta_context.levels_d1[:3], 1):
            print(f"      {i}. {level.level_type} @ ${level.price:.2f} (сила={level.strength:.2f})")
    
    print(f"\n✅ ATR:")
    if ta_context.atr_data:
        print(f"   • calculated_atr: {ta_context.atr_data.calculated_atr:.2f}")
        print(f"   • technical_atr: {ta_context.atr_data.technical_atr:.2f}")
        print(f"   • atr_percent: {ta_context.atr_data.atr_percent:.2f}%")
        print(f"   • is_exhausted: {ta_context.atr_data.is_exhausted}")
    else:
        print(f"   ❌ atr_data = None")
    
    print(f"\n✅ ТРЕНДЫ:")
    print(f"   • dominant_trend_h1: {ta_context.dominant_trend_h1.value}")
    print(f"   • dominant_trend_d1: {ta_context.dominant_trend_d1.value}")
    
    print(f"\n✅ РЫНОЧНЫЕ УСЛОВИЯ:")
    print(f"   • market_condition: {ta_context.market_condition.value}")
    print(f"   • volatility_level: {ta_context.volatility_level}")
    print(f"   • consolidation_detected: {ta_context.consolidation_detected}")
    print(f"   • consolidation_bars_count: {ta_context.consolidation_bars_count}")
    
    print(f"\n✅ ПАТТЕРНЫ:")
    print(f"   • has_compression: {ta_context.has_compression}")
    print(f"   • has_recent_breakout: {ta_context.has_recent_breakout}")
    print(f"   • has_v_formation: {ta_context.has_v_formation}")
    
    print(f"\n✅ СВЕЧИ:")
    print(f"   • recent_candles_m5: {len(ta_context.recent_candles_m5)}")
    print(f"   • recent_candles_m30: {len(ta_context.recent_candles_m30)}")
    print(f"   • recent_candles_h1: {len(ta_context.recent_candles_h1)}")
    print(f"   • recent_candles_h4: {len(ta_context.recent_candles_h4)}")
    print(f"   • recent_candles_d1: {len(ta_context.recent_candles_d1)}")
    
    print(f"\n✅ МЕТОДЫ:")
    if ta_context.levels_d1:
        current_price = float(ta_context.recent_candles_h1[-1]['close_price']) if ta_context.recent_candles_h1 else None
        if current_price:
            nearest_support = ta_context.get_nearest_support(current_price)
            nearest_resistance = ta_context.get_nearest_resistance(current_price)
            
            if nearest_support:
                print(f"   • Ближайший support: ${nearest_support.price:.2f} (сила={nearest_support.strength:.2f})")
            if nearest_resistance:
                print(f"   • Ближайший resistance: ${nearest_resistance.price:.2f} (сила={nearest_resistance.strength:.2f})")
            
            is_near_level = ta_context.is_near_level(current_price)
            if is_near_level:
                print(f"   • Цена рядом с уровнем: ${is_near_level.price:.2f}")
    
    print(f"\n✅ СТАТУС:")
    print(f"   • is_fully_initialized: {ta_context.is_fully_initialized()}")
    print(f"   • is_levels_cache_valid: {ta_context.is_levels_cache_valid()}")
    print(f"   • is_atr_cache_valid: {ta_context.is_atr_cache_valid()}")
    print(f"   • is_candles_cache_valid: {ta_context.is_candles_cache_valid()}")
    
    # ========== ЧТО НУЖНО СТРАТЕГИЯМ ==========
    
    print(f"\n" + "="*70)
    print(f"🎯 ЧТО ДОСТУПНО ДЛЯ СТРАТЕГИЙ:")
    print(f"="*70)
    
    print(f"\n1. УРОВНИ - context.levels_d1")
    print(f"   ✅ {len(ta_context.levels_d1)} уровней доступно")
    
    print(f"\n2. ATR - context.atr_data")
    print(f"   ✅ ATR = {ta_context.atr_data.calculated_atr if ta_context.atr_data else 0:.2f}")
    
    print(f"\n3. ТРЕНД - context.dominant_trend_h1, context.dominant_trend_d1")
    print(f"   ✅ H1: {ta_context.dominant_trend_h1.value}, D1: {ta_context.dominant_trend_d1.value}")
    
    print(f"\n4. ВОЛАТИЛЬНОСТЬ - context.volatility_level")
    print(f"   ✅ {ta_context.volatility_level}")
    
    print(f"\n5. РЫНОЧНЫЕ УСЛОВИЯ - context.market_condition")
    print(f"   ✅ {ta_context.market_condition.value}")
    
    print(f"\n6. ПАТТЕРНЫ:")
    print(f"   ✅ has_compression: {ta_context.has_compression}")
    print(f"   ✅ consolidation_detected: {ta_context.consolidation_detected}")
    print(f"   ✅ has_recent_breakout: {ta_context.has_recent_breakout}")

asyncio.run(test())
