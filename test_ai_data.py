#!/usr/bin/env python3
"""
Полный тест: данные + реальный ответ от OpenAI
Запуск: python test_ai_data.py
"""
import asyncio
from datetime import datetime, timedelta, timezone

async def main():
    print("\n🤖 ПОЛНЫЙ ТЕСТ: ДАННЫЕ → OpenAI → ОТВЕТ\n")
    
    from database import initialize_database, close_database
    from database.repositories import get_market_data_repository
    from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager
    from strategies import BreakoutStrategy
    from openai_integration import OpenAIAnalyzer
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
                    "Консолидация завершена",
                    "Тренд восходящий"
                ]
            )
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
            risk_percent = abs((signal_dict['stop_loss'] - signal_dict['price']) / signal_dict['price'] * 100)
            print(f"   Stop Loss: ${signal_dict['stop_loss']:,.2f} (риск {risk_percent:.2f}%)")
        if signal_dict['take_profit']:
            reward_percent = abs((signal_dict['take_profit'] - signal_dict['price']) / signal_dict['price'] * 100)
            print(f"   Take Profit: ${signal_dict['take_profit']:,.2f} (профит {reward_percent:.2f}%)")
            if signal_dict['stop_loss']:
                rr_ratio = reward_percent / risk_percent
                print(f"   R:R соотношение: {rr_ratio:.2f}:1")
        
        print(f"\n🔸 ТЕХНИЧЕСКИЙ КОНТЕКСТ:")
        print(f"   Уровней найдено: {len(ta_context.levels_d1)}")
        if ta_context.levels_d1:
            nearest = ta_context.levels_d1[0]
            print(f"   Ближайший: {nearest.level_type} @ ${nearest.price:,.2f} (сила {nearest.strength:.2f})")
        if ta_context.atr_data:
            print(f"   ATR: {ta_context.atr_data.calculated_atr:.2f}")
            print(f"   Запас хода: {(1 - ta_context.atr_data.current_range_used)*100:.0f}%")
        print(f"   Тренд: {ta_context.dominant_trend_h1.value if ta_context.dominant_trend_h1 else 'N/A'}")
        print(f"   Консолидация: {'Да' if ta_context.consolidation_detected else 'Нет'}")
        
        # ==================== ШАГ 5: ПОДГОТОВКА market_data ДЛЯ OpenAI ====================
        
        # Рассчитываем изменения цены
        price_change_1m = 0
        price_change_5m = 0
        price_change_24h = 0
        
        if len(candles_1m) >= 2:
            price_change_1m = (float(candles_1m[-1]['close_price']) - float(candles_1m[-2]['close_price'])) / float(candles_1m[-2]['close_price']) * 100
        
        if len(candles_5m) >= 2:
            price_change_5m = (float(candles_5m[-1]['close_price']) - float(candles_5m[-2]['close_price'])) / float(candles_5m[-2]['close_price']) * 100
        
        if len(candles_1d) >= 2:
            price_change_24h = (float(candles_1d[-1]['close_price']) - float(candles_1d[-2]['close_price'])) / float(candles_1d[-2]['close_price']) * 100
        
        # Формируем market_data словарь (как требует analyze_market)
        market_data = {
            # Основные показатели
            'current_price': signal_dict['price'],
            'price_change_1m': price_change_1m,
            'price_change_5m': price_change_5m,
            'price_change_24h': price_change_24h,
            'volume_24h': float(candles_1d[-1]['volume']) if candles_1d else 0,
            'high_24h': float(candles_1d[-1]['high_price']) if candles_1d else current_price,
            'low_24h': float(candles_1d[-1]['low_price']) if candles_1d else current_price,
            'open_interest': 0,
            
            # Контекст сигнала
            'signal_type': signal_dict['signal_type'],
            'signal_strength': signal_dict['strength'],
            'signal_confidence': signal_dict['confidence'],
            'strategy_name': signal_dict['strategy_name'],
            'signal_reasons': signal_dict['reasons'],
            
            # Почасовая статистика
            'hourly_data': {
                'price_trend': ta_context.dominant_trend_h1.value if ta_context.dominant_trend_h1 else 'unknown',
                'avg_price_24h': current_price,
                'price_volatility': (float(candles_1d[-1]['high_price']) - float(candles_1d[-1]['low_price'])) / float(candles_1d[-1]['low_price']) * 100 if candles_1d else 0,
                'avg_hourly_volume': float(candles_1d[-1]['volume']) / 24 if candles_1d else 0
            }
        }
        
        print("\n" + "="*80)
        print("📤 СТРУКТУРА market_data ДЛЯ OpenAI")
        print("="*80)
        print(f"\n💰 Цена: ${market_data['current_price']:,.2f}")
        print(f"📊 Изменения: 1m={price_change_1m:+.2f}%, 5m={price_change_5m:+.2f}%, 24h={price_change_24h:+.2f}%")
        print(f"📈 Объем 24h: {market_data['volume_24h']:,.0f}")
        print(f"🔸 Сигнал: {market_data['signal_type']} (сила={market_data['signal_strength']:.2f})")
        print(f"🧠 Стратегия: {market_data['strategy_name']}")
        print(f"📝 Причин: {len(market_data['signal_reasons'])}")
        
        # ==================== ШАГ 6: ЗАПРОС К OpenAI ====================
        print("\n" + "="*80)
        print("🤖 ОТПРАВКА ЗАПРОСА В OpenAI...")
        print("="*80)
        
        if not Config.OPENAI_API_KEY or Config.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY":
            print("\n❌ OpenAI API ключ не настроен!")
            print("   Установите OPENAI_API_KEY в переменных окружения")
            print("   Будет использован резервный анализ (fallback)\n")
        else:
            print(f"\n⏳ Отправка в OpenAI (модель: {Config.OPENAI_MODEL})...\n")
        
        try:
            analyzer = OpenAIAnalyzer()
            
            # ✅ ПРАВИЛЬНЫЙ ВЫЗОВ: analyze_market(market_data)
            ai_response = await analyzer.analyze_market(market_data)
            
            print("="*80)
            print("✅ АНАЛИЗ ОТ OpenAI (или fallback)")
            print("="*80)
            print(f"\n{ai_response}\n")
            print("="*80)
            
        except Exception as e:
            print(f"\n❌ Ошибка запроса к OpenAI: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n✅ ПОЛНЫЙ ТЕСТ ЗАВЕРШЕН\n")
        
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await close_database()

if __name__ == "__main__":
    asyncio.run(main())
