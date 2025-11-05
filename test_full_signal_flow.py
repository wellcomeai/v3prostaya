#!/usr/bin/env python3
"""
🔥 ПОЛНЫЙ ТЕСТ ЦЕПОЧКИ СИГНАЛОВ

Проверяет ВСЮ систему от начала до конца:
1. ✅ Создает ИДЕАЛЬНЫЕ данные для сигнала
2. ✅ Стратегия генерирует сигнал
3. ✅ SignalManager обрабатывает
4. ✅ Telegram получает уведомление

Если все работает - увидишь сообщение в Telegram!
"""

import asyncio
import sys
sys.path.insert(0, '/opt/render/project/src')

from datetime import datetime, timedelta, timezone
from database import initialize_database
from database.repositories import get_market_data_repository
from strategies import BreakoutStrategy
from strategies.base_strategy import TradingSignal, SignalType
from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager
from core.signal_manager import SignalManager

# Для прямой отправки в Telegram
from telegram_bot import TelegramBot
from config import Config


async def create_mock_candles_for_breakout(base_price: float = 50000.0):
    """
    Создать ИДЕАЛЬНЫЕ данные для пробоя
    
    Имитирует:
    - Консолидацию у уровня 50000
    - Поджатие (маленькие свечи)
    - Резкий пробой вверх
    """
    now = datetime.now(timezone.utc)
    candles = []
    
    # 1. Консолидация (20 свечей у уровня)
    for i in range(20):
        time = now - timedelta(minutes=100-i*5)
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
    
    # 2. Пробой (последняя свеча)
    breakout_time = now - timedelta(minutes=5)
    candles.append({
        'symbol': 'BTCUSDT',
        'interval': '5m',
        'open_time': breakout_time,
        'open_price': base_price,
        'high_price': base_price + 500,  # СИЛЬНЫЙ пробой!
        'low_price': base_price - 10,
        'close_price': base_price + 450,
        'volume': 500.0
    })
    
    return candles


async def create_perfect_ta_context(symbol: str = "BTCUSDT"):
    """
    Создать ИДЕАЛЬНЫЙ технический контекст для пробоя
    """
    from strategies.technical_analysis.context import (
        TechnicalAnalysisContext,
        SupportResistanceLevel,
        ATRData,
        MarketCondition,
        TrendDirection
    )
    
    # Уровень сопротивления у 50000
    resistance_level = SupportResistanceLevel(
        price=50000.0,
        level_type="resistance",
        strength=0.8,  # Сильный уровень
        touches=5,
        last_touch=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    
    # ATR с запасом хода
    atr_data = ATRData(
        calculated_atr=1000.0,
        technical_atr=2000.0,
        atr_percent=2.0,
        current_range_used=0.3,  # Всего 30% использовано - много запаса!
        is_exhausted=False,
        updated_at=datetime.now(timezone.utc)
    )
    
    # Создаем контекст
    context = TechnicalAnalysisContext(
        symbol=symbol,
        levels_d1=[resistance_level],
        atr_data=atr_data,
        market_condition=MarketCondition.CONSOLIDATION,  # Консолидация перед пробоем
        dominant_trend_h1=TrendDirection.NEUTRAL,
        volatility_level="low",
        consolidation_detected=True,
        consolidation_bars_count=15,
        has_compression=True,  # ✅ ЕСТЬ ПОДЖАТИЕ!
        has_recent_breakout=False,  # ✅ НЕТ недавнего пробоя
        has_v_formation=False
    )
    
    return context


async def test_full_chain():
    """Полный тест цепочки сигналов"""
    
    print("\n" + "="*70)
    print("🔥 ТЕСТ ПОЛНОЙ ЦЕПОЧКИ СИГНАЛОВ")
    print("="*70)
    
    try:
        # ==================== ИНИЦИАЛИЗАЦИЯ ====================
        
        print("\n1️⃣ Инициализация компонентов...")
        
        await initialize_database()
        repo = await get_market_data_repository()
        ta_mgr = TechnicalAnalysisContextManager(repo, auto_start_background_updates=False)
        
        # Создаем SignalManager
        signal_manager = SignalManager(
            openai_analyzer=None,
            cooldown_minutes=0,  # БЕЗ cooldown для теста!
            max_signals_per_hour=100,  # БЕЗ лимитов!
            min_signal_strength=0.3  # Низкий порог
        )
        await signal_manager.start()
        
        print("   ✅ SignalManager запущен")
        print(f"   • Подписчиков: {len(signal_manager.subscribers)}")
        
        # Создаем Telegram бота
        bot = TelegramBot()
        
        # ПОДПИСЫВАЕМ бота на сигналы
        signal_manager.add_subscriber(bot.broadcast_signal)
        
        print(f"   ✅ Telegram бот подписан")
        print(f"   • Подписчиков теперь: {len(signal_manager.subscribers)}")
        
        # ==================== СОЗДАЕМ ИДЕАЛЬНЫЕ ДАННЫЕ ====================
        
        print("\n2️⃣ Создание идеальных данных для пробоя...")
        
        # Идеальные свечи
        candles_5m = await create_mock_candles_for_breakout(base_price=50000.0)
        candles_1m = candles_5m  # Используем те же для простоты
        candles_1h = candles_5m[:10]
        candles_1d = candles_5m[:5]
        
        print(f"   ✅ Создано свечей: 5m={len(candles_5m)}, 1h={len(candles_1h)}, 1d={len(candles_1d)}")
        
        # Идеальный технический контекст
        ta_context = await create_perfect_ta_context("BTCUSDT")
        
        print(f"   ✅ Технический контекст:")
        print(f"      • Уровни: {len(ta_context.levels_d1)}")
        print(f"      • ATR: {ta_context.atr_data.calculated_atr:.2f}")
        print(f"      • ATR исчерпан: {ta_context.atr_data.is_exhausted}")
        print(f"      • Консолидация: {ta_context.consolidation_detected}")
        print(f"      • Поджатие: {ta_context.has_compression}")
        print(f"      • Недавний пробой: {ta_context.has_recent_breakout}")
        
        # ==================== ЗАПУСКАЕМ СТРАТЕГИЮ ====================
        
        print("\n3️⃣ Запуск BreakoutStrategy...")
        
        strategy = BreakoutStrategy(
            symbol="BTCUSDT",
            repository=repo,
            ta_context_manager=ta_mgr,
            min_signal_strength=0.3,  # Низкий порог
            signal_cooldown_minutes=0,  # БЕЗ cooldown
            max_signals_per_hour=100
        )
        
        signal = await strategy.analyze_with_data(
            symbol="BTCUSDT",
            candles_1m=candles_1m,
            candles_5m=candles_5m,
            candles_1h=candles_1h,
            candles_1d=candles_1d,
            ta_context=ta_context
        )
        
        if signal:
            print(f"   ✅ СТРАТЕГИЯ СГЕНЕРИРОВАЛА СИГНАЛ!")
            print(f"      • Тип: {signal.signal_type.value}")
            print(f"      • Сила: {signal.strength:.2f}")
            print(f"      • Уверенность: {signal.confidence:.2f}")
            print(f"      • Цена: ${signal.price:,.2f}")
            print(f"      • Причины:")
            for reason in signal.reasons:
                print(f"         - {reason}")
        else:
            print(f"   ❌ Стратегия НЕ сгенерировала сигнал")
            print(f"      Даже с идеальными данными!")
            print(f"      Это означает проблему в логике стратегии!")
            return
        
        # ==================== ОТПРАВЛЯЕМ В SIGNALMANAGER ====================
        
        print("\n4️⃣ Отправка сигнала в SignalManager...")
        
        result = await signal_manager.process_signal(signal)
        
        if result:
            print(f"   ✅ SignalManager ПРИНЯЛ сигнал!")
            print(f"      • Сигнал прошел все фильтры")
            print(f"      • Должен быть отправлен подписчикам")
        else:
            print(f"   ❌ SignalManager ОТКЛОНИЛ сигнал!")
            print(f"      Возможные причины:")
            print(f"      • Сила < {signal_manager.min_signal_strength}")
            print(f"      • Cooldown активен")
            print(f"      • Превышен лимит в час")
        
        # ==================== ПРОВЕРЯЕМ СТАТИСТИКУ ====================
        
        print("\n5️⃣ Проверка статистики SignalManager...")
        
        stats = signal_manager.get_stats()
        
        print(f"   📊 Статистика:")
        print(f"      • Получено сигналов: {stats['signals_received']}")
        print(f"      • Отправлено: {stats['signals_sent']}")
        print(f"      • Отфильтровано по силе: {stats['signals_filtered_strength']}")
        print(f"      • Отфильтровано cooldown: {stats['signals_filtered_cooldown']}")
        print(f"      • Отфильтровано лимит: {stats['signals_filtered_rate_limit']}")
        print(f"      • Ошибки рассылки: {stats['broadcast_errors']}")
        
        # ==================== ПРЯМАЯ ОТПРАВКА В TELEGRAM ====================
        
        print("\n6️⃣ АЛЬТЕРНАТИВА: Прямая отправка в Telegram (если SignalManager отклонил)...")
        
        if stats['signals_sent'] == 0:
            print(f"   ⚠️ SignalManager не отправил - пробуем напрямую...")
            
            # Форматируем сообщение
            message = f"""
🔔 ТЕСТОВЫЙ СИГНАЛ

Symbol: {signal.symbol}
Type: {signal.signal_type.value}
Strength: {signal.strength:.2f}
Confidence: {signal.confidence:.2f}
Price: ${signal.price:,.2f}

Reasons:
{chr(10).join(f"• {r}" for r in signal.reasons)}

⚠️ ЭТО ТЕСТ! Не торговый сигнал!
"""
            
            try:
                await bot.broadcast_signal(message)
                print(f"   ✅ Сообщение отправлено НАПРЯМУЮ в Telegram!")
                print(f"      • Всем подписчикам бота")
            except Exception as e:
                print(f"   ❌ Ошибка отправки в Telegram: {e}")
        else:
            print(f"   ✅ SignalManager отправил сам!")
        
        # ==================== ИТОГ ====================
        
        print("\n" + "="*70)
        print("📊 ИТОГОВЫЙ ОТЧЕТ")
        print("="*70)
        
        print(f"\n✅ Стратегия: {'Работает' if signal else 'НЕ работает'}")
        print(f"✅ SignalManager: {'Пропустил' if result else 'Отклонил'}")
        print(f"✅ Telegram: {'Отправлено' if stats['signals_sent'] > 0 else 'Проверь бот вручную'}")
        
        if signal and result and stats['signals_sent'] > 0:
            print(f"\n🎉 ВСЯ ЦЕПОЧКА РАБОТАЕТ!")
            print(f"   Проверь Telegram - должно прийти уведомление!")
        elif signal and not result:
            print(f"\n⚠️ ПРОБЛЕМА В SIGNALMANAGER!")
            print(f"   Стратегия работает, но SignalManager фильтрует")
        elif not signal:
            print(f"\n⚠️ ПРОБЛЕМА В СТРАТЕГИИ!")
            print(f"   Даже с идеальными данными не генерирует сигнал")
        
        print("\n" + "="*70)
        
        # Останавливаем SignalManager
        await signal_manager.stop()
        
    except Exception as e:
        print(f"\n❌ ОШИБКА ТЕСТА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_full_chain())
