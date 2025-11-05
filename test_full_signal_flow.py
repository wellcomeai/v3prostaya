#!/usr/bin/env python3
"""
🔥 ПОЛНЫЙ ТЕСТ ЦЕПОЧКИ СИГНАЛОВ

Проверяет ВСЮ систему от начала до конца:
1. ✅ Создает ИДЕАЛЬНЫЕ данные для сигнала
2. ✅ Стратегия генерирует сигнал
3. ✅ SignalManager обрабатывает
4. ✅ Telegram получает уведомление

Если все работает - увидишь сообщение в Telegram!

FIXED v2: Увеличено количество свечей до 40 (было 20)
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
from config import Config


async def create_mock_candles_for_breakout(base_price: float = 50000.0):
    """
    Создать ИДЕАЛЬНЫЕ данные для пробоя
    
    Имитирует:
    - Консолидацию у уровня 50000
    - Поджатие (маленькие свечи)
    - Резкий пробой вверх
    
    FIXED v2: Создаём 40 свечей вместо 20 (требование стратегии: min 30 для D1)
    """
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
    print("🔥 ТЕСТ ПОЛНОЙ ЦЕПОЧКИ СИГНАЛОВ v2 (FIXED)")
    print("="*70)
    
    try:
        # ==================== ИНИЦИАЛИЗАЦИЯ ====================
        
        print("\n1️⃣ Инициализация компонентов...")
        
        await initialize_database()
        repo = await get_market_data_repository()
        ta_mgr = TechnicalAnalysisContextManager(repo, auto_start_background_updates=False)
        
        # ✅ ИСПРАВЛЕНО: Создаем тестовую функцию подписчика
        messages_received = []
        
        async def test_subscriber(message: str):
            """Тестовый подписчик вместо реального Telegram бота"""
            print(f"\n📨 ТЕСТОВЫЙ ПОДПИСЧИК ПОЛУЧИЛ СООБЩЕНИЕ:")
            print(f"{'='*70}")
            print(message)
            print(f"{'='*70}")
            messages_received.append(message)
        
        # Создаем SignalManager
        signal_manager = SignalManager(
            openai_analyzer=None,
            cooldown_minutes=0,  # БЕЗ cooldown для теста!
            max_signals_per_hour=100,  # БЕЗ лимитов!
            min_signal_strength=0.3  # Низкий порог
        )
        await signal_manager.start()
        
        print("   ✅ SignalManager запущен")
        print(f"   • Подписчиков ДО: {len(signal_manager.subscribers)}")
        
        # ПОДПИСЫВАЕМ тестовую функцию
        signal_manager.add_subscriber(test_subscriber)
        
        print(f"   ✅ Тестовый подписчик добавлен")
        print(f"   • Подписчиков ПОСЛЕ: {len(signal_manager.subscribers)}")
        
        # ==================== СОЗДАЕМ ИДЕАЛЬНЫЕ ДАННЫЕ ====================
        
        print("\n2️⃣ Создание идеальных данных для пробоя...")
        
        # Идеальные свечи (теперь 41 штука!)
        candles_5m = await create_mock_candles_for_breakout(base_price=50000.0)
        candles_1m = candles_5m  # Используем те же для простоты
        candles_1h = candles_5m[:24]  # Первые 24 для H1
        candles_1d = candles_5m  # ✅ ИСПРАВЛЕНО: все свечи (41 штука > 30!)
        
        print(f"   ✅ Создано свечей:")
        print(f"      • 1m: {len(candles_1m)}")
        print(f"      • 5m: {len(candles_5m)}")
        print(f"      • 1h: {len(candles_1h)}")
        print(f"      • 1d: {len(candles_1d)} (требуется min 30) ✅")
        
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
            max_signals_per_hour=100,
            require_compression=False,  # НЕ требуем для теста
            require_consolidation=False  # НЕ требуем для теста
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
            
            print(f"\n🔍 ДИАГНОСТИКА: Почему нет сигнала?")
            print(f"      Проверяем условия входа стратегии...")
            
            # Останавливаем SignalManager
            await signal_manager.stop()
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
        
        # Даем время на обработку
        await asyncio.sleep(1)
        
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
        
        print(f"\n   📬 Сообщений получено тестовым подписчиком: {len(messages_received)}")
        
        # ==================== ИТОГ ====================
        
        print("\n" + "="*70)
        print("📊 ИТОГОВЫЙ ОТЧЕТ")
        print("="*70)
        
        print(f"\n✅ Стратегия: {'Работает' if signal else 'НЕ работает'}")
        print(f"✅ SignalManager: {'Пропустил' if result else 'Отклонил'}")
        print(f"✅ Подписчик: {'Получил сообщение' if messages_received else 'НЕ получил'}")
        
        if signal and result and messages_received:
            print(f"\n🎉 ВСЯ ЦЕПОЧКА РАБОТАЕТ!")
            print(f"   Тестовый подписчик получил {len(messages_received)} сообщений")
        elif signal and result and not messages_received:
            print(f"\n⚠️ ПРОБЛЕМА В РАССЫЛКЕ!")
            print(f"   SignalManager принял, но подписчик не получил")
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
