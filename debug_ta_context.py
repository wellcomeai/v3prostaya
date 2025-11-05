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
    
    print(f"\n📊 TA Context type: {type(ta_context)}")
    print(f"📊 TA Context: {ta_context}")
    
    if ta_context:
        print(f"\n🔎 Все атрибуты объекта:")
        for attr in dir(ta_context):
            if not attr.startswith('_'):
                try:
                    value = getattr(ta_context, attr)
                    if not callable(value):
                        print(f"   • {attr}: {value}")
                except Exception as e:
                    print(f"   • {attr}: ERROR - {e}")
        
        # Попробуем обратиться к ожидаемым полям
        print(f"\n🎯 Проверка ожидаемых полей:")
        
        fields_to_check = [
            'levels', 'support_levels', 'resistance_levels',
            'trend', 'trend_direction', 'trend_strength',
            'volatility', 'atr', 'market_condition',
            'compression', 'consolidation', 'energy',
            'breakout', 'breakout_data'
        ]
        
        for field in fields_to_check:
            if hasattr(ta_context, field):
                value = getattr(ta_context, field)
                print(f"   ✅ {field}: {value}")
            else:
                print(f"   ❌ {field}: НЕТ")

asyncio.run(test())
