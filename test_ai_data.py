#!/usr/bin/env python3
"""
Проверка данных отправляемых в OpenAI
Запуск: python test_ai_data.py
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

async def main():
    print("\n🤖 ПРОВЕРКА ДАННЫХ ДЛЯ AI АНАЛИЗА\n")
    
    from database import initialize_database, close_database
    from database.repositories import get_market_data_repository
    from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager
    from strategies import BreakoutStrategy
    
    symbol = "BTCUSDT"
    
    try:
        # Инициализация
        print("⏳ Подключение...")
        await initialize_database()
        repository = await get_market_data_repository()
        ta_manager = TechnicalAnalysisContextManager(repository=repository, auto_start_background_updates=False)
        
        # Получаем данные
        print("📊 Загрузка данных...\n")
        now = datetime.now(timezone.utc)
        ta_context = await ta_manager.get_context(symbol)
        
        candles_1m = await repository.get_candles(symbol, "1m", start_time=now-timedelta(hours=2), limit=100)
        candles_5m = await repository.get_candles(symbol, "5m", start_time=now-timedelta(hours=5), limit=50)
        candles_1h = await repository.get_candles(symbol, "1h", start_time=now-timedelta(hours=24), limit=24)
        candles_1d = await repository.get_candles(symbol, "1d", start_time=now-timedelta(days=180), limit=180)
        
        # Создаем стратегию и генерируем сигнал
        print("🎯 Генерация сигнала...\n")
        strategy = BreakoutStrategy(symbol=symbol, ta_context_manager=ta_manager)
        signal = await strategy.analyze_with_data(symbol, candles_1m, candles_5m, candles_1h, candles_1d, ta_context)
        
        if not signal:
            print("ℹ️  Нет сигнала для анализа. Создам тестовый сигнал...\n")
            from strategies.base_strategy import SignalType
            signal = strategy.create_signal(
                signal_type=SignalType.BUY,
                strength=0.75,
                confidence=0.8,
                current_price=float(candles_1m[-1]['close_price']),
                reasons=["Тестовый сигнал для проверки AI"]
            )
        
        # ========== ПОКАЗЫВАЕМ ЧТО ОТПРАВЛЯЕТСЯ В AI ==========
        
        print("=" * 80)
        print("📦 ДАННЫЕ СИГНАЛА (что видит AI)")
        print("=" * 80)
        
        signal_dict = signal.to_dict()
        
        print("\n🔹 ОСНОВНАЯ ИНФОРМАЦИЯ:")
        print(f"   Символ: {signal_dict['symbol']}")
        print(f"   Тип: {signal_dict['signal_type']}")
        print(f"   Сила: {signal_dict['strength']:.2f} ({signal_dict['strength_level']})")
        print(f"   Уверенность: {signal_dict['confidence']:.2f} ({signal_dict['confidence_level']})")
        print(f"   Цена: ${signal_dict['price']:,.2f}")
        print(f"   Стратегия: {signal_dict['strategy_name']}")
        
        print("\n🔹 ПРИЧИНЫ СИГНАЛА:")
        for i, reason in enumerate(signal_dict['reasons'], 1):
            print(f"   {i}. {reason}")
        
        print("\n🔹 ТЕХНИЧЕСКИЕ ИНДИКАТОРЫ:")
        for key, value in signal_dict['technical_indicators'].items():
            if isinstance(value, dict):
                print(f"   • {key}:")
                for k, v in value.items():
                    print(f"      - {k}: {v}")
            else:
                print(f"   • {key}: {value}")
        
        print("\n🔹 УПРАВЛЕНИЕ РИСКАМИ:")
        print(f"   Stop Loss: ${signal_dict['stop_loss']:,.2f}" if signal_dict['stop_loss'] else "   Stop Loss: не установлен")
        print(f"   Take Profit: ${signal_dict['take_profit']:,.2f}" if signal_dict['take_profit'] else "   Take Profit: не установлен")
        print(f"   Размер позиции: {signal_dict['position_size_recommendation']*100:.2f}%")
        
        print("\n🔹 РЫНОЧНЫЕ УСЛОВИЯ:")
        for key, value in signal_dict['market_conditions'].items():
            print(f"   • {key}: {value}")
        
        print("\n🔹 ДОПОЛНИТЕЛЬНО:")
        print(f"   Quality Score: {signal_dict['quality_score']:.2f}")
        print(f"   Истекает: {signal_dict['expires_at']}")
        print(f"   Валиден: {signal_dict['is_valid']}")
        
        # ========== ПОКАЗЫВАЕМ КОНТЕКСТ РЫНКА ==========
        
        print("\n" + "=" * 80)
        print("📊 ТЕХНИЧЕСКИЙ КОНТЕКСТ (дополнительные данные для AI)")
        print("=" * 80)
        
        print("\n🔹 УРОВНИ ПОДДЕРЖКИ/СОПРОТИВЛЕНИЯ:")
        for i, level in enumerate(ta_context.levels_d1[:5], 1):
            print(f"   #{i}: {level.level_type.upper()} @ ${level.price:,.2f}")
            print(f"       Сила: {level.strength:.2f} | Касания: {level.touches} | Сильный: {level.is_strong}")
        
        if ta_context.atr_data:
            print("\n🔹 ATR (ЗАПАС ХОДА):")
            print(f"   Calculated ATR: {ta_context.atr_data.calculated_atr:.2f}")
            print(f"   ATR в %: {ta_context.atr_data.atr_percentage:.2f}%")
            print(f"   Использовано: {ta_context.atr_data.current_range_used*100:.1f}%")
            print(f"   Осталось: {ta_context.atr_data.remaining_range:.2f}")
        
        print("\n🔹 РЫНОЧНЫЕ УСЛОВИЯ:")
        print(f"   Тренд H1: {ta_context.dominant_trend_h1.value if ta_context.dominant_trend_h1 else 'N/A'}")
        print(f"   Тренд D1: {ta_context.dominant_trend_d1.value if ta_context.dominant_trend_d1 else 'N/A'}")
        print(f"   Консолидация: {'Да' if ta_context.consolidation_detected else 'Нет'}")
        print(f"   Поджатие: {'Да' if ta_context.has_compression else 'Нет'}")
        print(f"   V-формация: {'Да' if ta_context.has_v_formation else 'Нет'}")
        
        # ========== ПОКАЗЫВАЕМ ПРОМПТ ДЛЯ AI ==========
        
        print("\n" + "=" * 80)
        print("💬 ПРИМЕРНЫЙ ПРОМПТ ДЛЯ OpenAI")
        print("=" * 80)
        
        prompt = f"""
Проанализируй торговый сигнал:

СИГНАЛ:
- Инструмент: {signal_dict['symbol']}
- Тип: {signal_dict['signal_type']}
- Сила: {signal_dict['strength']:.2f} ({signal_dict['strength_level']})
- Уверенность: {signal_dict['confidence']:.2f}
- Цена входа: ${signal_dict['price']:,.2f}
- Стратегия: {signal_dict['strategy_name']}

ПРИЧИНЫ:
{chr(10).join('- ' + r for r in signal_dict['reasons'])}

ТЕХНИЧЕСКИЙ КОНТЕКСТ:
- Тренд: {ta_context.dominant_trend_h1.value if ta_context.dominant_trend_h1 else 'N/A'}
- ATR использовано: {ta_context.atr_data.current_range_used*100:.1f}% (осталось {ta_context.atr_data.remaining_range:.2f})
- Консолидация: {'Да' if ta_context.consolidation_detected else 'Нет'}
- Уровней рядом: {len([l for l in ta_context.levels_d1 if abs(l.price - signal_dict['price']) / signal_dict['price'] < 0.02])}

РИСК МЕНЕДЖМЕНТ:
- Stop Loss: ${signal_dict['stop_loss']:,.2f}
- Take Profit: ${signal_dict['take_profit']:,.2f}
- Размер позиции: {signal_dict['position_size_recommendation']*100:.2f}%

Дай краткий анализ (2-3 предложения):
1. Оценка качества сигнала
2. Ключевые риски
3. Рекомендация (подходит/не подходит для входа)
"""
        
        print(prompt)
        
        # ========== ПОЛНЫЙ JSON ДЛЯ ОТЛАДКИ ==========
        
        print("\n" + "=" * 80)
        print("📄 ПОЛНЫЙ JSON СИГНАЛА (для разработчиков)")
        print("=" * 80)
        print("\n" + json.dumps(signal_dict, indent=2, default=str))
        
        print("\n✅ ПРОВЕРКА ЗАВЕРШЕНА")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await close_database()

if __name__ == "__main__":
    asyncio.run(main())
