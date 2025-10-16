#!/usr/bin/env python3
"""
Полный тест: данные + реальный ответ от OpenAI
Запуск: python test_ai_full.py
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

async def main():
    print("\n🤖 ПОЛНЫЙ ТЕСТ: ДАННЫЕ → OpenAI → ОТВЕТ\n")
    
    from database import initialize_database, close_database
    from database.repositories import get_market_data_repository
    from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager
    from strategies import BreakoutStrategy
    from config import Config
    
    symbol = "BTCUSDT"
    
    try:
        # ==================== ШАГ 1: ПОДГОТОВКА ====================
        print("1️⃣ Подключение к БД...")
        await initialize_database()
        repository = await get_market_data_repository()
        
        print("2️⃣ Инициализация Technical Analysis...")
        ta_manager = TechnicalAnalysisContextManager(repository=repository, auto_start_background_updates=False)
        ta_context = await ta_manager.get_context(symbol)
        
        # ==================== ШАГ 2: ЗАГРУЗКА ДАННЫХ ====================
        print("3️⃣ Загрузка рыночных данных...")
        now = datetime.now(timezone.utc)
        
        candles_1m = await repository.get_candles(symbol, "1m", start_time=now-timedelta(hours=2), limit=100)
        candles_5m = await repository.get_candles(symbol, "5m", start_time=now-timedelta(hours=5), limit=50)
        candles_1h = await repository.get_candles(symbol, "1h", start_time=now-timedelta(hours=24), limit=24)
        candles_1d = await repository.get_candles(symbol, "1d", start_time=now-timedelta(days=180), limit=180)
        
        current_price = float(candles_1m[-1]['close_price']) if candles_1m else 0
        print(f"   ✅ Данные загружены. Цена: ${current_price:,.2f}\n")
        
        # ==================== ШАГ 3: ГЕНЕРАЦИЯ СИГНАЛА ====================
        print("4️⃣ Анализ стратегией BreakoutStrategy...")
        strategy = BreakoutStrategy(symbol=symbol, ta_context_manager=ta_manager)
        signal = await strategy.analyze_with_data(symbol, candles_1m, candles_5m, candles_1h, candles_1d, ta_context)
        
        # Если нет реального сигнала - создаем тестовый
        if not signal:
            print("   ⚠️ Реальный сигнал не сгенерирован (условия не выполнены)")
            print("   ℹ️  Создам демо-сигнал для теста AI...\n")
            
            from strategies.base_strategy import SignalType
            signal = strategy.create_signal(
                signal_type=SignalType.BUY,
                strength=0.78,
                confidence=0.85,
                current_price=current_price,
                reasons=[
                    f"Пробой сопротивления @ ${ta_context.levels_d1[0].price:,.2f}" if ta_context.levels_d1 else "Тестовая причина 1",
                    f"ATR использован на {ta_context.atr_data.current_range_used*100:.0f}%" if ta_context.atr_data else "Тестовая причина 2",
                    "Поджатие у уровня обнаружено" if ta_context.has_compression else "Тестовая причина 3"
                ]
            )
            # Добавляем risk management
            signal.stop_loss = current_price * 0.97
            signal.take_profit = current_price * 1.09
        else:
            print("   ✅ Реальный торговый сигнал сгенерирован!\n")
        
        # ==================== ШАГ 4: ПОКАЗЫВАЕМ ДАННЫЕ ====================
        print("="*80)
        print("📦 ДАННЫЕ КОТОРЫЕ ОТПРАВЛЯЮТСЯ В OpenAI")
        print("="*80)
        
        signal_dict = signal.to_dict()
        
        print(f"\n🔸 ОСНОВНОЕ:")
        print(f"   Символ: {signal_dict['symbol']}")
        print(f"   Тип сигнала: {signal_dict['signal_type']}")
        print(f"   Сила: {signal_dict['strength']:.2f} ({signal_dict['strength_level']})")
        print(f"   Уверенность: {signal_dict['confidence']:.2f} ({signal_dict['confidence_level']})")
        print(f"   Цена входа: ${signal_dict['price']:,.2f}")
        print(f"   Стратегия: {signal_dict['strategy_name']}")
        
        print(f"\n🔸 ПРИЧИНЫ:")
        for i, reason in enumerate(signal_dict['reasons'], 1):
            print(f"   {i}. {reason}")
        
        print(f"\n🔸 РИСК-МЕНЕДЖМЕНТ:")
        if signal_dict['stop_loss']:
            print(f"   Stop Loss: ${signal_dict['stop_loss']:,.2f}")
            risk_percent = abs((signal_dict['stop_loss'] - signal_dict['price']) / signal_dict['price'] * 100)
            print(f"   Риск: {risk_percent:.2f}%")
        if signal_dict['take_profit']:
            print(f"   Take Profit: ${signal_dict['take_profit']:,.2f}")
            reward_percent = abs((signal_dict['take_profit'] - signal_dict['price']) / signal_dict['price'] * 100)
            print(f"   Профит: {reward_percent:.2f}%")
            if signal_dict['stop_loss']:
                rr_ratio = reward_percent / risk_percent
                print(f"   R:R соотношение: {rr_ratio:.2f}:1")
        
        print(f"\n🔸 ТЕХНИЧЕСКИЙ КОНТЕКСТ:")
        print(f"   Уровней найдено: {len(ta_context.levels_d1)}")
        if ta_context.levels_d1:
            nearest = ta_context.levels_d1[0]
            print(f"   Ближайший уровень: {nearest.level_type} @ ${nearest.price:,.2f} (сила {nearest.strength:.2f})")
        if ta_context.atr_data:
            print(f"   ATR: {ta_context.atr_data.calculated_atr:.2f}")
            print(f"   Запас хода: {(1 - ta_context.atr_data.current_range_used)*100:.0f}% остался")
        print(f"   Тренд: {ta_context.dominant_trend_h1.value if ta_context.dominant_trend_h1 else 'N/A'}")
        print(f"   Консолидация: {'Да' if ta_context.consolidation_detected else 'Нет'}")
        
        # ==================== ШАГ 5: ФОРМИРУЕМ ПРОМПТ ====================
        print("\n" + "="*80)
        print("💬 ПРОМПТ ДЛЯ OpenAI")
        print("="*80)
        
        # Формируем детальный промпт
        prompt = f"""Проанализируй торговый сигнал для {signal_dict['symbol']}:

СИГНАЛ:
- Тип: {signal_dict['signal_type']}
- Цена входа: ${signal_dict['price']:,.2f}
- Сила сигнала: {signal_dict['strength']:.2f}/1.0 ({signal_dict['strength_level']})
- Уверенность: {signal_dict['confidence']:.2f}/1.0 ({signal_dict['confidence_level']})
- Стратегия: {signal_dict['strategy_name']}

ПРИЧИНЫ СИГНАЛА:
{chr(10).join('• ' + r for r in signal_dict['reasons'])}

ТЕХНИЧЕСКИЙ АНАЛИЗ:
- Тренд: {ta_context.dominant_trend_h1.value if ta_context.dominant_trend_h1 else 'неопределен'}
- ATR использован: {ta_context.atr_data.current_range_used*100:.0f}% (остаток {(1-ta_context.atr_data.current_range_used)*100:.0f}%)
- Консолидация: {'обнаружена' if ta_context.consolidation_detected else 'отсутствует'}
- Поджатие: {'есть' if ta_context.has_compression else 'нет'}
- Ближайших уровней: {len([l for l in ta_context.levels_d1 if abs(l.price - signal_dict['price'])/signal_dict['price'] < 0.02])}

РИСК-МЕНЕДЖМЕНТ:
- Stop Loss: ${signal_dict['stop_loss']:,.2f} ({abs((signal_dict['stop_loss']-signal_dict['price'])/signal_dict['price']*100):.2f}%)
- Take Profit: ${signal_dict['take_profit']:,.2f} ({abs((signal_dict['take_profit']-signal_dict['price'])/signal_dict['price']*100):.2f}%)
- R:R соотношение: {abs((signal_dict['take_profit']-signal_dict['price'])/signal_dict['price']) / abs((signal_dict['stop_loss']-signal_dict['price'])/signal_dict['price']):.2f}:1

Дай анализ в формате:
1. КАЧЕСТВО СИГНАЛА (1-2 предложения)
2. КЛЮЧЕВЫЕ РИСКИ (1-2 предложения)
3. РЕКОМЕНДАЦИЯ (входить/ждать/пропустить + почему)
"""
        
        print(prompt)
        
        # ==================== ШАГ 6: ЗАПРОС К OpenAI ====================
        print("\n" + "="*80)
        print("🤖 ОТПРАВКА ЗАПРОСА В OpenAI...")
        print("="*80)
        
        # Проверяем API ключ
        if not Config.OPENAI_API_KEY or Config.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY":
            print("\n❌ OpenAI API ключ не настроен!")
            print("   Установите OPENAI_API_KEY в переменных окружения\n")
        else:
            print(f"\n⏳ Отправка запроса (модель: {Config.OPENAI_MODEL})...")
            
            try:
                # Используем OpenAI напрямую
                from openai_integration import OpenAIAnalyzer
                
                analyzer = OpenAIAnalyzer()
                ai_response = await analyzer.analyze_signal(signal)
                
                print("\n✅ ОТВЕТ ПОЛУЧЕН!\n")
                
                print("="*80)
                print("🎯 АНАЛИЗ ОТ OpenAI")
                print("="*80)
                print(f"\n{ai_response}\n")
                print("="*80)
                
            except Exception as e:
                print(f"\n❌ Ошибка запроса к OpenAI: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n✅ ПОЛНЫЙ ТЕСТ ЗАВЕРШЕН")
        
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await close_database()

if __name__ == "__main__":
    asyncio.run(main())
