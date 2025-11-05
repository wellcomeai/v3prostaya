#!/usr/bin/env python3
"""
🔍 ПОЛНАЯ ДИАГНОСТИКА ТОРГОВОЙ СИСТЕМЫ v3.0

Имитирует реальный цикл работы и находит ВСЕ ошибки:
1. ✅ Инициализация всех компонентов
2. ✅ Получение данных из БД
3. ✅ Создание TA Context
4. ✅ Запуск всех стратегий
5. ✅ Обработка сигналов
6. ❌ ЛОВИТ ВСЕ ОШИБКИ с traceback!

Использование:
    python full_system_diagnostic.py                    # Полная диагностика
    python full_system_diagnostic.py --quick            # Быстрый тест (5 символов)
    python full_system_diagnostic.py --symbol BTCUSDT   # Один символ
    python full_system_diagnostic.py --cycles 3         # Несколько циклов
"""

import asyncio
import sys
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from collections import defaultdict
import argparse

sys.path.insert(0, '/opt/render/project/src')

# Импорты системы
from config import Config
from database import initialize_database, close_database
from database.repositories import get_market_data_repository

# Стратегии
from strategies import (
    BreakoutStrategy,
    BounceStrategy,
    FalseBreakoutStrategy
)

# Технический анализ
from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class SystemDiagnostics:
    """🔬 Полная диагностика торговой системы"""
    
    def __init__(self):
        self.repository = None
        self.ta_context_manager = None
        
        # Статистика
        self.stats = {
            "total_symbols": 0,
            "successful_symbols": 0,
            "failed_symbols": 0,
            "total_strategies_tested": 0,
            "successful_strategies": 0,
            "failed_strategies": 0,
            "total_signals": 0,
            "errors_by_component": defaultdict(int),
            "errors_by_symbol": defaultdict(int),
            "errors_by_strategy": defaultdict(int),
            "error_details": []
        }
    
    async def initialize_system(self) -> bool:
        """Шаг 1: Инициализация системы"""
        print("\n" + "=" * 70)
        print("🚀 ШАГ 1: ИНИЦИАЛИЗАЦИЯ СИСТЕМЫ")
        print("=" * 70)
        
        try:
            # БД
            print("\n📊 Инициализация базы данных...")
            db_initialized = await initialize_database()
            if not db_initialized:
                print("❌ База данных не инициализирована!")
                return False
            print("✅ База данных подключена")
            
            # Repository
            print("\n📦 Создание Repository...")
            self.repository = await get_market_data_repository()
            print("✅ Repository создан")
            
            # TechnicalAnalysisContextManager
            print("\n📈 Инициализация TechnicalAnalysisContextManager...")
            self.ta_context_manager = TechnicalAnalysisContextManager(
                repository=self.repository,
                auto_start_background_updates=False  # Без фона для теста
            )
            print("✅ TechnicalAnalysisContextManager создан")
            
            return True
            
        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА инициализации: {e}")
            traceback.print_exc()
            return False
    
    async def test_data_availability(self, symbols: List[str]) -> Dict[str, bool]:
        """Шаг 2: Проверка доступности данных"""
        print("\n" + "=" * 70)
        print("🔍 ШАГ 2: ПРОВЕРКА ДОСТУПНОСТИ ДАННЫХ")
        print("=" * 70)
        
        results = {}
        now = datetime.now(timezone.utc)
        
        for symbol in symbols:
            try:
                print(f"\n📊 Проверка {symbol}...")
                
                # Получаем данные как в реальной системе
                candles_1m = await self.repository.get_candles(
                    symbol, "1m", 
                    now - timedelta(hours=2), 
                    now, 
                    100
                )
                candles_5m = await self.repository.get_candles(
                    symbol, "5m",
                    now - timedelta(hours=5),
                    now,
                    50
                )
                candles_1h = await self.repository.get_candles(
                    symbol, "1h",
                    now - timedelta(days=2),
                    now,
                    48
                )
                candles_1d = await self.repository.get_candles(
                    symbol, "1d",
                    now - timedelta(days=180),
                    now,
                    180
                )
                
                # Проверяем достаточность данных
                if len(candles_1m) < 50:
                    print(f"   ⚠️ Мало данных 1m: {len(candles_1m)}")
                    results[symbol] = False
                    self.stats["errors_by_component"]["data_1m"] += 1
                    continue
                
                if len(candles_5m) < 20:
                    print(f"   ⚠️ Мало данных 5m: {len(candles_5m)}")
                    results[symbol] = False
                    self.stats["errors_by_component"]["data_5m"] += 1
                    continue
                
                if len(candles_1h) < 24:
                    print(f"   ⚠️ Мало данных 1h: {len(candles_1h)}")
                    results[symbol] = False
                    self.stats["errors_by_component"]["data_1h"] += 1
                    continue
                
                if len(candles_1d) < 90:
                    print(f"   ⚠️ Мало данных 1d: {len(candles_1d)}")
                    results[symbol] = False
                    self.stats["errors_by_component"]["data_1d"] += 1
                    continue
                
                print(f"   ✅ Данные: 1m={len(candles_1m)}, 5m={len(candles_5m)}, 1h={len(candles_1h)}, 1d={len(candles_1d)}")
                results[symbol] = True
                
            except Exception as e:
                print(f"   ❌ ОШИБКА: {e}")
                results[symbol] = False
                self.stats["errors_by_component"]["data_fetch"] += 1
                self.stats["errors_by_symbol"][symbol] += 1
                self.stats["error_details"].append({
                    "symbol": symbol,
                    "component": "data_fetch",
                    "error": str(e),
                    "traceback": traceback.format_exc()
                })
        
        successful = sum(1 for v in results.values() if v)
        print(f"\n✅ Успешно: {successful}/{len(symbols)}")
        
        return results
    
    async def test_ta_context(self, symbols: List[str]) -> Dict[str, bool]:
        """Шаг 3: Проверка технического анализа"""
        print("\n" + "=" * 70)
        print("📈 ШАГ 3: ПРОВЕРКА ТЕХНИЧЕСКОГО АНАЛИЗА")
        print("=" * 70)
        
        results = {}
        
        for symbol in symbols:
            try:
                print(f"\n🔍 TA Context для {symbol}...")
                
                ta_context = await self.ta_context_manager.get_context(symbol)
                
                if ta_context is None:
                    print(f"   ❌ TA Context = None")
                    results[symbol] = False
                    self.stats["errors_by_component"]["ta_context_none"] += 1
                    self.stats["errors_by_symbol"][symbol] += 1
                    continue
                
                # Проверяем что внутри
                has_levels = hasattr(ta_context, 'levels') and ta_context.levels
                has_trend = hasattr(ta_context, 'trend')
                has_volatility = hasattr(ta_context, 'volatility')
                
                print(f"   ✅ TA Context создан:")
                print(f"      • Levels: {len(ta_context.levels) if has_levels else 0}")
                print(f"      • Trend: {ta_context.trend if has_trend else 'N/A'}")
                print(f"      • Volatility: {ta_context.volatility if has_volatility else 'N/A'}")
                
                results[symbol] = True
                
            except Exception as e:
                print(f"   ❌ ОШИБКА: {e}")
                results[symbol] = False
                self.stats["errors_by_component"]["ta_context_error"] += 1
                self.stats["errors_by_symbol"][symbol] += 1
                self.stats["error_details"].append({
                    "symbol": symbol,
                    "component": "ta_context",
                    "error": str(e),
                    "traceback": traceback.format_exc()
                })
        
        successful = sum(1 for v in results.values() if v)
        print(f"\n✅ Успешно: {successful}/{len(symbols)}")
        
        return results
    
    async def test_strategies(self, symbols: List[str]) -> Dict[str, Any]:
        """Шаг 4: ПОЛНОЕ ТЕСТИРОВАНИЕ СТРАТЕГИЙ (как Orchestrator)"""
        print("\n" + "=" * 70)
        print("🎯 ШАГ 4: ТЕСТИРОВАНИЕ СТРАТЕГИЙ (КАК ORCHESTRATOR)")
        print("=" * 70)
        
        strategies_config = [
            ("BreakoutStrategy", BreakoutStrategy),
            ("BounceStrategy", BounceStrategy),
            ("FalseBreakoutStrategy", FalseBreakoutStrategy)
        ]
        
        results = {
            "by_symbol": {},
            "by_strategy": defaultdict(lambda: {"success": 0, "fail": 0, "signals": 0}),
            "all_signals": []
        }
        
        now = datetime.now(timezone.utc)
        
        for symbol in symbols:
            print(f"\n{'='*70}")
            print(f"📊 АНАЛИЗ {symbol}")
            print(f"{'='*70}")
            
            symbol_results = {
                "data_ok": False,
                "ta_ok": False,
                "strategies": {}
            }
            
            try:
                # Получаем данные
                print(f"\n1️⃣ Получение данных...")
                candles_1m = await self.repository.get_candles(symbol, "1m", now - timedelta(hours=2), now, 100)
                candles_5m = await self.repository.get_candles(symbol, "5m", now - timedelta(hours=5), now, 50)
                candles_1h = await self.repository.get_candles(symbol, "1h", now - timedelta(days=2), now, 48)
                candles_1d = await self.repository.get_candles(symbol, "1d", now - timedelta(days=180), now, 180)
                
                print(f"   ✅ Свечи: 1m={len(candles_1m)}, 5m={len(candles_5m)}, 1h={len(candles_1h)}, 1d={len(candles_1d)}")
                symbol_results["data_ok"] = True
                
                # Проверяем достаточность
                if len(candles_1m) < 50 or len(candles_1h) < 24:
                    print(f"   ⚠️ НЕДОСТАТОЧНО ДАННЫХ, пропускаем {symbol}")
                    self.stats["failed_symbols"] += 1
                    self.stats["errors_by_component"]["insufficient_data"] += 1
                    continue
                
                # TA Context
                print(f"\n2️⃣ Получение TA Context...")
                ta_context = await self.ta_context_manager.get_context(symbol)
                
                if ta_context:
                    print(f"   ✅ TA Context получен")
                    symbol_results["ta_ok"] = True
                else:
                    print(f"   ⚠️ TA Context = None")
                    self.stats["errors_by_component"]["ta_context_none"] += 1
                
                # Тестируем каждую стратегию
                print(f"\n3️⃣ Тестирование стратегий...")
                
                for strategy_name, strategy_class in strategies_config:
                    print(f"\n   🎯 {strategy_name}...")
                    self.stats["total_strategies_tested"] += 1
                    
                    try:
                        # Создаем стратегию КАК В ORCHESTRATOR
                        strategy = strategy_class(
                            symbol=symbol,
                            repository=self.repository,
                            ta_context_manager=self.ta_context_manager,
                            min_signal_strength=0.3,
                            signal_cooldown_minutes=5,
                            max_signals_per_hour=12
                        )
                        
                        # ЗАПУСКАЕМ АНАЛИЗ КАК В ORCHESTRATOR
                        signal = await strategy.analyze_with_data(
                            symbol=symbol,
                            candles_1m=candles_1m,
                            candles_5m=candles_5m,
                            candles_1h=candles_1h,
                            candles_1d=candles_1d,
                            ta_context=ta_context
                        )
                        
                        if signal:
                            print(f"      ✅ СИГНАЛ: {signal.signal_type.value} (сила={signal.strength:.2f}, уверенность={signal.confidence:.2f})")
                            symbol_results["strategies"][strategy_name] = {
                                "status": "signal",
                                "signal": {
                                    "type": signal.signal_type.value,
                                    "strength": signal.strength,
                                    "confidence": signal.confidence,
                                    "price": signal.price,
                                    "reasons": signal.reasons
                                }
                            }
                            self.stats["total_signals"] += 1
                            results["by_strategy"][strategy_name]["signals"] += 1
                            results["all_signals"].append({
                                "symbol": symbol,
                                "strategy": strategy_name,
                                "signal": signal.signal_type.value,
                                "strength": signal.strength
                            })
                        else:
                            print(f"      ⚪ Нет сигнала (условия не выполнены)")
                            symbol_results["strategies"][strategy_name] = {"status": "no_signal"}
                        
                        self.stats["successful_strategies"] += 1
                        results["by_strategy"][strategy_name]["success"] += 1
                        
                    except Exception as e:
                        print(f"      ❌ ОШИБКА: {e}")
                        print(f"         Traceback:")
                        traceback.print_exc()
                        
                        symbol_results["strategies"][strategy_name] = {
                            "status": "error",
                            "error": str(e)
                        }
                        
                        self.stats["failed_strategies"] += 1
                        self.stats["errors_by_strategy"][strategy_name] += 1
                        self.stats["errors_by_symbol"][symbol] += 1
                        results["by_strategy"][strategy_name]["fail"] += 1
                        
                        self.stats["error_details"].append({
                            "symbol": symbol,
                            "component": "strategy",
                            "strategy": strategy_name,
                            "error": str(e),
                            "traceback": traceback.format_exc()
                        })
                
                self.stats["successful_symbols"] += 1
                
            except Exception as e:
                print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА для {symbol}: {e}")
                traceback.print_exc()
                self.stats["failed_symbols"] += 1
                self.stats["errors_by_symbol"][symbol] += 1
                self.stats["error_details"].append({
                    "symbol": symbol,
                    "component": "symbol_processing",
                    "error": str(e),
                    "traceback": traceback.format_exc()
                })
            
            results["by_symbol"][symbol] = symbol_results
            self.stats["total_symbols"] += 1
        
        return results
    
    def print_final_report(self, strategy_results: Dict[str, Any]):
        """Финальный отчет"""
        print("\n" + "=" * 70)
        print("📊 ФИНАЛЬНЫЙ ОТЧЕТ ДИАГНОСТИКИ")
        print("=" * 70)
        
        # Общая статистика
        print(f"\n🎯 ОБЩАЯ СТАТИСТИКА:")
        print(f"   • Символов протестировано: {self.stats['total_symbols']}")
        print(f"   • Успешно: {self.stats['successful_symbols']}")
        print(f"   • С ошибками: {self.stats['failed_symbols']}")
        print(f"   • Стратегий запущено: {self.stats['total_strategies_tested']}")
        print(f"   • Успешно: {self.stats['successful_strategies']}")
        print(f"   • С ошибками: {self.stats['failed_strategies']}")
        print(f"   • СИГНАЛОВ НАЙДЕНО: {self.stats['total_signals']}")
        
        # Ошибки по компонентам
        if self.stats["errors_by_component"]:
            print(f"\n❌ ОШИБКИ ПО КОМПОНЕНТАМ:")
            for component, count in sorted(self.stats["errors_by_component"].items(), key=lambda x: x[1], reverse=True):
                print(f"   • {component}: {count}")
        
        # Ошибки по стратегиям
        if self.stats["errors_by_strategy"]:
            print(f"\n❌ ОШИБКИ ПО СТРАТЕГИЯМ:")
            for strategy, count in sorted(self.stats["errors_by_strategy"].items(), key=lambda x: x[1], reverse=True):
                print(f"   • {strategy}: {count}")
        
        # Топ символов с ошибками
        if self.stats["errors_by_symbol"]:
            print(f"\n❌ СИМВОЛЫ С НАИБОЛЬШИМ КОЛИЧЕСТВОМ ОШИБОК:")
            top_errors = sorted(self.stats["errors_by_symbol"].items(), key=lambda x: x[1], reverse=True)[:5]
            for symbol, count in top_errors:
                print(f"   • {symbol}: {count} ошибок")
        
        # Сигналы
        if self.stats["total_signals"] > 0:
            print(f"\n✅ НАЙДЕННЫЕ СИГНАЛЫ:")
            for signal in strategy_results["all_signals"]:
                print(f"   • {signal['symbol']} - {signal['strategy']}: {signal['signal']} (сила={signal['strength']:.2f})")
        
        # Детали ошибок
        if self.stats["error_details"]:
            print(f"\n🔍 ДЕТАЛИ ОШИБОК (первые 5):")
            for i, error in enumerate(self.stats["error_details"][:5], 1):
                print(f"\n   {i}. {error['symbol']} - {error['component']}")
                print(f"      Error: {error['error']}")
                if error.get('strategy'):
                    print(f"      Strategy: {error['strategy']}")
        
        # Итог
        print("\n" + "=" * 70)
        if self.stats["failed_strategies"] > 0:
            print("⚠️ НАЙДЕНЫ ПРОБЛЕМЫ! См. детали выше.")
        else:
            print("✅ ВСЕ КОМПОНЕНТЫ РАБОТАЮТ БЕЗ ОШИБОК!")
        print("=" * 70)
    
    async def run_full_diagnostic(
        self, 
        symbols: Optional[List[str]] = None,
        cycles: int = 1
    ):
        """Запуск полной диагностики"""
        try:
            # Инициализация
            if not await self.initialize_system():
                print("❌ Не удалось инициализировать систему!")
                return
            
            # Символы
            if symbols is None:
                symbols = Config.get_bybit_symbols()
            
            print(f"\n🎯 Тестирование {len(symbols)} символов, {cycles} циклов")
            
            for cycle in range(cycles):
                if cycles > 1:
                    print(f"\n{'='*70}")
                    print(f"🔄 ЦИКЛ {cycle + 1}/{cycles}")
                    print(f"{'='*70}")
                
                # Проверяем данные
                data_results = await self.test_data_availability(symbols)
                
                # Проверяем TA
                ta_results = await self.test_ta_context(symbols)
                
                # Тестируем стратегии (ГЛАВНОЕ)
                strategy_results = await self.test_strategies(symbols)
                
                if cycle < cycles - 1:
                    await asyncio.sleep(5)
            
            # Финальный отчет
            self.print_final_report(strategy_results)
            
        except KeyboardInterrupt:
            print("\n⚠️ Диагностика прервана пользователем")
        except Exception as e:
            print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
            traceback.print_exc()
        finally:
            # Закрываем БД
            try:
                await close_database()
                print("\n✅ База данных закрыта")
            except Exception as e:
                print(f"⚠️ Ошибка закрытия БД: {e}")


async def main():
    parser = argparse.ArgumentParser(description="🔍 Полная диагностика торговой системы")
    parser.add_argument("--quick", action="store_true", help="Быстрый тест (5 символов)")
    parser.add_argument("--symbol", type=str, help="Тест одного символа")
    parser.add_argument("--cycles", type=int, default=1, help="Количество циклов")
    
    args = parser.parse_args()
    
    # Определяем символы
    symbols = None
    if args.symbol:
        symbols = [args.symbol.upper()]
    elif args.quick:
        symbols = Config.get_bybit_symbols()[:5]
    
    # Запускаем диагностику
    diagnostics = SystemDiagnostics()
    await diagnostics.run_full_diagnostic(symbols=symbols, cycles=args.cycles)


if __name__ == "__main__":
    asyncio.run(main())
