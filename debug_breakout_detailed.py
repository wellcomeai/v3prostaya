#!/usr/bin/env python3
"""
🔍 ДЕТАЛЬНАЯ ОТЛАДКА BREAKOUT STRATEGY

Показывает ШАГ ЗА ШАГОМ что происходит в стратегии

FIXED v2: Увеличено количество свечей до 40 (было 20)
"""

import asyncio
import sys
sys.path.insert(0, '/opt/render/project/src')

from datetime import datetime, timedelta, timezone
from database import initialize_database
from database.repositories import get_market_data_repository
from strategies import BreakoutStrategy
from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager
from strategies.technical_analysis.context import (
    TechnicalAnalysisContext,
    SupportResistanceLevel,
    ATRData,
    MarketCondition,
    TrendDirection
)


async def create_test_data():
    """
    Создать тестовые данные
    
    FIXED v2: Создаём 40 свечей вместо 20 (требование стратегии: min 30 для D1)
    """
    base_price = 50000.0
    now = datetime.now(timezone.utc)
    candles = []
    
    # 1. Консолидация (40 свечей - достаточно для D1!) ✅
    for i in range(40):  # ✅ ИСПРАВЛЕНО: было 20
        time = now - timedelta(minutes=200-i*5)  # ✅ ИСПРАВЛЕНО: было 100
        candles.append({
            'symbol': 'BTCUSDT',
            'interval': '5m',
            'open_time': time,
            'open_price': base_price - 50,
            'high_price': base_price + 30,
            'low_price': base_price - 80,
            'close_price': base_price - 20,
            'volume': 100.0
        })
    
    # 2. Пробой
    breakout_time = now - timedelta(minutes=5)
    candles.append({
        'symbol': 'BTCUSDT',
        'interval': '5m',
        'open_time': breakout_time,
        'open_price': base_price,
        'high_price': base_price + 500,
        'low_price': base_price - 10,
        'close_price': base_price + 450,
        'volume': 500.0
    })
    
    # 3. Технический контекст
    resistance = SupportResistanceLevel(
        price=50000.0,
        level_type="resistance",
        strength=0.8,
        touches=5,
        last_touch=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    
    atr_data = ATRData(
        calculated_atr=1000.0,
        technical_atr=2000.0,
        atr_percent=2.0,
        current_range_used=0.3,
        is_exhausted=False,
        updated_at=datetime.now(timezone.utc)
    )
    
    context = TechnicalAnalysisContext(
        symbol="BTCUSDT",
        levels_d1=[resistance],
        atr_data=atr_data,
        market_condition=MarketCondition.CONSOLIDATION,
        dominant_trend_h1=TrendDirection.NEUTRAL,
        volatility_level="low",
        consolidation_detected=True,
        consolidation_bars_count=15,
        has_compression=True,
        has_recent_breakout=False,
        has_v_formation=False
    )
    
    return candles, context


async def debug_strategy():
    """Детальная отладка"""
    
    print("\n" + "="*70)
    print("🔍 ДЕТАЛЬНАЯ ОТЛАДКА BREAKOUT STRATEGY v2 (FIXED)")
    print("="*70)
    
    try:
        await initialize_database()
        repo = await get_market_data_repository()
        ta_mgr = TechnicalAnalysisContextManager(repo, auto_start_background_updates=False)
        
        # Создаем данные
        candles, ta_context = await create_test_data()
        
        print(f"\n📊 ТЕСТОВЫЕ ДАННЫЕ:")
        print(f"   • Всего свечей: {len(candles)} (требуется min 30 для D1) ✅")
        print(f"   • Последняя цена: ${float(candles[-1]['close_price']):,.2f}")
        print(f"   • Уровень сопротивления: ${ta_context.levels_d1[0].price:,.2f}")
        print(f"   • Разница: +${float(candles[-1]['close_price']) - ta_context.levels_d1[0].price:,.2f}")
        
        # Создаем стратегию с ОТЛАДКОЙ
        strategy = BreakoutStrategy(
            symbol="BTCUSDT",
            repository=repo,
            ta_context_manager=ta_mgr,
            min_signal_strength=0.1,  # ✅ ОЧЕНЬ НИЗКИЙ!
            signal_cooldown_minutes=0,  # ✅ НЕТ COOLDOWN
            max_signals_per_hour=1000,  # ✅ БЕЗ ЛИМИТА
            require_compression=False,  # ✅ НЕ ТРЕБУЕМ
            require_consolidation=False  # ✅ НЕ ТРЕБУЕМ
        )
        
        # ✅ ВКЛЮЧАЕМ ОТЛАДКУ!
        strategy.enable_debug_mode(True)
        
        print(f"\n🎯 ПАРАМЕТРЫ СТРАТЕГИИ:")
        print(f"   • min_signal_strength: {strategy.min_signal_strength}")
        print(f"   • require_compression: {strategy.require_compression}")
        print(f"   • require_consolidation: {strategy.require_consolidation}")
        print(f"   • debug_mode: {strategy.debug_mode}")
        
        print(f"\n" + "="*70)
        print(f"🚀 ЗАПУСК АНАЛИЗА С ОТЛАДКОЙ")
        print(f"="*70)
        
        # ЗАПУСКАЕМ С ОТЛАДКОЙ
        signal = await strategy.analyze_with_data(
            symbol="BTCUSDT",
            candles_1m=candles,
            candles_5m=candles,
            candles_1h=candles[:24],
            candles_1d=candles,  # ✅ ИСПРАВЛЕНО: все свечи (41 штука)
            ta_context=ta_context
        )
        
        print(f"\n" + "="*70)
        print(f"📊 РЕЗУЛЬТАТ")
        print(f"="*70)
        
        if signal:
            print(f"\n✅ СИГНАЛ СОЗДАН!")
            print(f"   • Тип: {signal.signal_type.value}")
            print(f"   • Сила: {signal.strength:.2f}")
            print(f"   • Уверенность: {signal.confidence:.2f}")
            print(f"   • Цена: ${signal.price:,.2f}")
            print(f"   • Причины:")
            for reason in signal.reasons:
                print(f"      - {reason}")
        else:
            print(f"\n❌ СИГНАЛ НЕ СОЗДАН")
            print(f"\n🔍 Смотри логи выше - там должно быть указано где стратегия отвалилась!")
        
        print(f"\n📊 СТАТИСТИКА СТРАТЕГИИ:")
        stats = strategy.get_strategy_stats()
        print(f"   • levels_analyzed: {stats['strategy_stats']['levels_analyzed']}")
        print(f"   • setups_found: {stats['strategy_stats']['setups_found']}")
        print(f"   • signals_generated: {stats['strategy_stats']['signals_generated']}")
        print(f"   • setups_filtered_by_atr: {stats['strategy_stats']['setups_filtered_by_atr']}")
        print(f"   • setups_filtered_by_compression: {stats['strategy_stats']['setups_filtered_by_compression']}")
        print(f"   • setups_filtered_by_energy: {stats['strategy_stats']['setups_filtered_by_energy']}")
        
        print(f"\n" + "="*70)
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Включаем логирование
    import logging
    logging.basicConfig(
        level=logging.DEBUG,  # ✅ МАКСИМАЛЬНАЯ ОТЛАДКА!
        format='%(levelname)s - %(name)s - %(message)s'
    )
    
    asyncio.run(debug_strategy())
