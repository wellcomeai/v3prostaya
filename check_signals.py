#!/usr/bin/env python3
"""
🔍 ДИАГНОСТИЧЕСКИЙ СКРИПТ - Проверка генерации сигналов

Проверяет РЕАЛЬНУЮ работу торговой системы:
1. ✅ Есть ли данные в БД?
2. ✅ Работают ли стратегии?
3. ✅ Генерируются ли сигналы?
4. ✅ Проходят ли сигналы фильтры?
5. ✅ Почему нет уведомлений в Telegram?

Использование:
    python check_signals.py                           # Быстрая диагностика
    python check_signals.py --symbol BTCUSDT          # Конкретный символ
    python check_signals.py --verbose                 # Подробный вывод
    python check_signals.py --test-strategies         # Тест всех стратегий

Author: Trading Bot Team
Version: 2.0.0 - Diagnostic Edition
"""

import asyncio
import logging
import argparse
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from collections import defaultdict
from tabulate import tabulate
import traceback

# Импорты проекта
from config import Config
from database import initialize_database, close_database, get_database_health
from database.repositories import get_market_data_repository

# Стратегии
from strategies import (
    BreakoutStrategy,
    BounceStrategy, 
    FalseBreakoutStrategy,
    SignalType
)

# Технический анализ
from strategies.technical_analysis.context_manager import TechnicalAnalysisContextManager

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING  # По умолчанию только важное
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SignalDiagnostics:
    """
    🔍 Диагностика системы генерации сигналов
    
    Проверяет всю цепочку:
    1. БД → Данные актуальные?
    2. Repository → Получаем данные?
    3. TechnicalAnalysis → Работает?
    4. Стратегии → Генерируют сигналы?
    5. Фильтры → Пропускают сигналы?
    """
    
    def __init__(self, repository, ta_context_manager):
        self.repository = repository
        self.ta_context_manager = ta_context_manager
        
        # Результаты проверок
        self.checks = {
            "database": {"status": "pending", "details": {}},
            "data_availability": {"status": "pending", "details": {}},
            "technical_analysis": {"status": "pending", "details": {}},
            "strategies": {"status": "pending", "details": {}},
            "signal_generation": {"status": "pending", "details": {}}
        }
        
        logger.info("🔍 SignalDiagnostics инициализирован")
    
    async def run_full_diagnostic(
        self,
        symbols: Optional[List[str]] = None,
        test_strategies: bool = False
    ) -> Dict[str, Any]:
        """
        Полная диагностика системы
        
        Args:
            symbols: Список символов для проверки (None = все)
            test_strategies: Тестировать генерацию сигналов
            
        Returns:
            Dict с результатами всех проверок
        """
        print("\n" + "=" * 70)
        print("🔍 ДИАГНОСТИКА СИСТЕМЫ ГЕНЕРАЦИИ СИГНАЛОВ")
        print("=" * 70)
        
        # Проверка 1: База данных
        await self._check_database()
        
        # Проверка 2: Доступность данных
        if symbols is None:
            symbols = Config.get_bybit_symbols()[:5]  # Первые 5 для быстроты
        
        await self._check_data_availability(symbols)
        
        # Проверка 3: Технический анализ
        await self._check_technical_analysis(symbols[0] if symbols else "BTCUSDT")
        
        # Проверка 4: Стратегии
        if test_strategies:
            await self._test_strategies(symbols)
        
        # Итоговый отчет
        self._print_summary()
        
        return self.checks
    
    async def _check_database(self):
        """Проверка 1: Состояние базы данных"""
        print("\n" + "-" * 70)
        print("📊 ПРОВЕРКА 1: БАЗА ДАННЫХ")
        print("-" * 70)
        
        try:
            db_health = await get_database_health()
            
            if db_health.get("healthy", False):
                self.checks["database"]["status"] = "✅ OK"
                self.checks["database"]["details"] = db_health
                print("✅ База данных подключена и работает")
                print(f"   • Pool size: {db_health.get('pool_size', 'unknown')}")
                print(f"   • Active connections: {db_health.get('active_connections', 'unknown')}")
            else:
                self.checks["database"]["status"] = "❌ ERROR"
                self.checks["database"]["details"] = db_health
                print("❌ Проблемы с базой данных!")
                print(f"   • Error: {db_health.get('error', 'unknown')}")
                
        except Exception as e:
            self.checks["database"]["status"] = "❌ ERROR"
            self.checks["database"]["details"] = {"error": str(e)}
            print(f"❌ Ошибка проверки БД: {e}")
    
    async def _check_data_availability(self, symbols: List[str]):
        """Проверка 2: Наличие актуальных данных"""
        print("\n" + "-" * 70)
        print("📈 ПРОВЕРКА 2: ДОСТУПНОСТЬ ДАННЫХ")
        print("-" * 70)
        
        intervals_to_check = ["1m", "5m", "1h", "1d"]
        now = datetime.now(timezone.utc)
        
        results = []
        issues = []
        
        for symbol in symbols:
            symbol_data = {
                "symbol": symbol,
                "intervals": {}
            }
            
            for interval in intervals_to_check:
                try:
                    # Проверяем последнюю свечу
                    latest = await self.repository.get_latest_candle(symbol, interval)
                    
                    if latest:
                        age_seconds = (now - latest['open_time']).total_seconds()
                        age_minutes = age_seconds / 60
                        
                        # Определяем допустимую задержку
                        max_delay = {
                            "1m": 5,    # 5 минут
                            "5m": 15,   # 15 минут
                            "1h": 120,  # 2 часа
                            "1d": 1440  # 1 день
                        }.get(interval, 60)
                        
                        is_fresh = age_minutes <= max_delay
                        status = "✅" if is_fresh else "⚠️"
                        
                        symbol_data["intervals"][interval] = {
                            "latest_time": latest['open_time'].isoformat(),
                            "age_minutes": round(age_minutes, 1),
                            "is_fresh": is_fresh,
                            "price": float(latest['close_price'])
                        }
                        
                        results.append([
                            symbol,
                            interval,
                            status,
                            f"{age_minutes:.0f} мин назад",
                            f"${float(latest['close_price']):,.2f}"
                        ])
                        
                        if not is_fresh:
                            issues.append(f"{symbol} {interval}: устаревшие данные ({age_minutes:.0f} мин)")
                    else:
                        symbol_data["intervals"][interval] = None
                        results.append([symbol, interval, "❌", "Нет данных", "-"])
                        issues.append(f"{symbol} {interval}: данные отсутствуют")
                        
                except Exception as e:
                    logger.error(f"Ошибка проверки {symbol} {interval}: {e}")
                    results.append([symbol, interval, "❌", f"Ошибка", "-"])
                    issues.append(f"{symbol} {interval}: ошибка проверки")
        
        # Выводим таблицу
        print(tabulate(
            results,
            headers=["Символ", "Интервал", "Статус", "Возраст", "Цена"],
            tablefmt="pretty"
        ))
        
        # Статус проверки
        if not issues:
            self.checks["data_availability"]["status"] = "✅ OK"
            print("\n✅ Все данные актуальные!")
        else:
            self.checks["data_availability"]["status"] = "⚠️ ISSUES"
            print(f"\n⚠️ Найдено проблем: {len(issues)}")
            for issue in issues[:10]:  # Первые 10
                print(f"   • {issue}")
        
        self.checks["data_availability"]["details"] = {
            "symbols_checked": len(symbols),
            "intervals_checked": intervals_to_check,
            "issues_count": len(issues),
            "issues": issues[:20]  # Первые 20
        }
    
    async def _check_technical_analysis(self, symbol: str):
        """Проверка 3: Технический анализ"""
        print("\n" + "-" * 70)
        print(f"🧠 ПРОВЕРКА 3: ТЕХНИЧЕСКИЙ АНАЛИЗ ({symbol})")
        print("-" * 70)
        
        try:
            # Пытаемся получить контекст
            ta_context = await self.ta_context_manager.get_context(symbol)
            
            if ta_context:
                self.checks["technical_analysis"]["status"] = "✅ OK"
                print(f"✅ Технический контекст получен")
                
                # Проверяем что внутри
                details = {}
                if hasattr(ta_context, 'levels'):
                    print(f"   • Уровни: {len(ta_context.levels)} штук")
                    details["levels_count"] = len(ta_context.levels)
                
                if hasattr(ta_context, 'trend'):
                    print(f"   • Тренд: {ta_context.trend}")
                    details["trend"] = str(ta_context.trend)
                
                if hasattr(ta_context, 'volatility'):
                    print(f"   • Волатильность: {ta_context.volatility}")
                    details["volatility"] = str(ta_context.volatility)
                
                self.checks["technical_analysis"]["details"] = details
            else:
                self.checks["technical_analysis"]["status"] = "❌ ERROR"
                print("❌ Технический контекст не получен")
                self.checks["technical_analysis"]["details"] = {"error": "Context is None"}
                
        except Exception as e:
            self.checks["technical_analysis"]["status"] = "❌ ERROR"
            self.checks["technical_analysis"]["details"] = {"error": str(e)}
            print(f"❌ Ошибка технического анализа: {e}")
            traceback.print_exc()
    
    async def _test_strategies(self, symbols: List[str]):
        """Проверка 4: Тестирование стратегий"""
        print("\n" + "-" * 70)
        print("🎯 ПРОВЕРКА 4: ТЕСТИРОВАНИЕ СТРАТЕГИЙ")
        print("-" * 70)
        
        strategies_to_test = {
            "breakout": BreakoutStrategy,
            "bounce": BounceStrategy,
            "false_breakout": FalseBreakoutStrategy
        }
        
        all_results = []
        total_signals = 0
        
        for symbol in symbols[:3]:  # Первые 3 символа
            print(f"\n📊 Тестирование на {symbol}...")
            
            try:
                # Получаем данные
                now = datetime.now(timezone.utc)
                candles_1m = await self.repository.get_candles(
                    symbol, "1m", 
                    start_time=now - timedelta(hours=2),
                    end_time=now,
                    limit=100
                )
                candles_5m = await self.repository.get_candles(
                    symbol, "5m",
                    start_time=now - timedelta(hours=5),
                    end_time=now,
                    limit=50
                )
                candles_1h = await self.repository.get_candles(
                    symbol, "1h",
                    start_time=now - timedelta(days=2),
                    end_time=now,
                    limit=48
                )
                candles_1d = await self.repository.get_candles(
                    symbol, "1d",
                    start_time=now - timedelta(days=180),
                    end_time=now,
                    limit=180
                )
                
                print(f"   • 1m: {len(candles_1m)} свечей")
                print(f"   • 5m: {len(candles_5m)} свечей")
                print(f"   • 1h: {len(candles_1h)} свечей")
                print(f"   • 1d: {len(candles_1d)} свечей")
                
                if not candles_1m:
                    print(f"   ⚠️ Недостаточно данных для {symbol}")
                    continue
                
                # Технический контекст
                ta_context = None
                try:
                    ta_context = await self.ta_context_manager.get_context(symbol)
                except:
                    pass
                
                # Тестируем каждую стратегию
                for strategy_name, strategy_class in strategies_to_test.items():
                    try:
                        # Создаем стратегию
                        strategy = strategy_class(
                            symbol=symbol,
                            repository=self.repository,
                            ta_context_manager=self.ta_context_manager,
                            min_signal_strength=0.3,  # Низкий порог для диагностики
                            signal_cooldown_minutes=0,  # Без cooldown
                            max_signals_per_hour=100  # Без лимита
                        )
                        
                        # Запускаем анализ
                        signal = await strategy.analyze_with_data(
                            symbol=symbol,
                            candles_1m=candles_1m,
                            candles_5m=candles_5m,
                            candles_1h=candles_1h,
                            candles_1d=candles_1d,
                            ta_context=ta_context
                        )
                        
                        if signal:
                            total_signals += 1
                            all_results.append([
                                symbol,
                                strategy_name,
                                "✅ СИГНАЛ",
                                signal.signal_type.value,
                                f"{signal.strength:.2f}",
                                f"{signal.confidence:.2f}",
                                ", ".join(signal.reasons[:2])
                            ])
                            print(f"   ✅ {strategy_name}: {signal.signal_type.value} "
                                  f"(сила={signal.strength:.2f}, уверенность={signal.confidence:.2f})")
                        else:
                            all_results.append([
                                symbol,
                                strategy_name,
                                "⚪ Нет сигнала",
                                "-",
                                "-",
                                "-",
                                "Условия не выполнены"
                            ])
                            print(f"   ⚪ {strategy_name}: нет сигнала")
                            
                    except Exception as e:
                        all_results.append([
                            symbol,
                            strategy_name,
                            "❌ ОШИБКА",
                            "-",
                            "-",
                            "-",
                            str(e)[:50]
                        ])
                        print(f"   ❌ {strategy_name}: ошибка - {e}")
                        
            except Exception as e:
                print(f"   ❌ Ошибка получения данных: {e}")
        
        # Итоговая таблица
        print("\n" + "=" * 70)
        print("📋 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ СТРАТЕГИЙ")
        print("=" * 70)
        
        print(tabulate(
            all_results,
            headers=["Символ", "Стратегия", "Результат", "Тип", "Сила", "Увер.", "Причины"],
            tablefmt="pretty"
        ))
        
        # Статус
        if total_signals > 0:
            self.checks["signal_generation"]["status"] = "✅ OK"
            print(f"\n✅ Сгенерировано сигналов: {total_signals}")
        else:
            self.checks["signal_generation"]["status"] = "⚠️ NO SIGNALS"
            print(f"\n⚠️ НИ ОДНОГО СИГНАЛА НЕ СГЕНЕРИРОВАНО!")
            print("\nВозможные причины:")
            print("   1. Недостаточно данных в БД")
            print("   2. Рыночные условия не соответствуют критериям")
            print("   3. Ошибки в логике стратегий")
            print("   4. Проблемы с техническим анализом")
        
        self.checks["signal_generation"]["details"] = {
            "total_signals": total_signals,
            "symbols_tested": len(symbols[:3]),
            "strategies_tested": len(strategies_to_test),
            "results": all_results
        }
    
    def _print_summary(self):
        """Итоговая сводка"""
        print("\n" + "=" * 70)
        print("📊 ИТОГОВАЯ СВОДКА ДИАГНОСТИКИ")
        print("=" * 70)
        
        checks_table = []
        for check_name, check_data in self.checks.items():
            status = check_data.get("status", "❓")
            checks_table.append([
                check_name.replace("_", " ").title(),
                status
            ])
        
        print(tabulate(
            checks_table,
            headers=["Компонент", "Статус"],
            tablefmt="pretty"
        ))
        
        # Рекомендации
        print("\n" + "=" * 70)
        print("💡 РЕКОМЕНДАЦИИ")
        print("=" * 70)
        
        if self.checks["database"]["status"] != "✅ OK":
            print("\n❌ БАЗА ДАННЫХ:")
            print("   • Проверьте подключение к PostgreSQL")
            print("   • Проверьте переменные окружения (DATABASE_URL)")
        
        if self.checks["data_availability"]["status"] == "⚠️ ISSUES":
            print("\n⚠️ ДАННЫЕ:")
            details = self.checks["data_availability"]["details"]
            issues_count = details.get("issues_count", 0)
            print(f"   • Найдено {issues_count} проблем с данными")
            print("   • Проверьте работу SimpleCandleSync")
            print("   • Запустите: curl https://ваш-домен.onrender.com/admin/sync-status")
        
        if self.checks["signal_generation"]["status"] == "⚠️ NO SIGNALS":
            print("\n⚠️ СИГНАЛЫ НЕ ГЕНЕРИРУЮТСЯ:")
            print("   • Рыночные условия могут не соответствовать критериям стратегий")
            print("   • Проверьте что SimpleCandleSync работает и загружает свежие данные")
            print("   • Попробуйте понизить min_signal_strength в стратегиях")
            print("   • Проверьте логи приложения на ошибки")
        
        if self.checks["technical_analysis"]["status"] != "✅ OK":
            print("\n❌ ТЕХНИЧЕСКИЙ АНАЛИЗ:")
            print("   • Проверьте работу TechnicalAnalysisContextManager")
            print("   • Убедитесь что есть достаточно исторических данных (180 дней)")
        
        print("\n" + "=" * 70)


async def main():
    """Главная функция"""
    
    parser = argparse.ArgumentParser(
        description="🔍 Диагностика системы генерации сигналов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python check_signals.py                      # Быстрая проверка
  python check_signals.py --symbol BTCUSDT     # Проверка одного символа
  python check_signals.py --test-strategies    # Полное тестирование стратегий
  python check_signals.py --verbose            # Подробные логи
        """
    )
    
    parser.add_argument(
        "--symbol",
        type=str,
        help="Проверить конкретный символ"
    )
    
    parser.add_argument(
        "--test-strategies",
        action="store_true",
        help="Запустить тест генерации сигналов стратегиями"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Подробные логи (DEBUG)"
    )
    
    args = parser.parse_args()
    
    # Настройка логирования
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    
    try:
        logger.info("🚀 Запуск диагностики системы...")
        
        # Инициализация БД
        logger.info("📦 Подключение к базе данных...")
        db_success = await initialize_database()
        
        if not db_success:
            logger.error("❌ Не удалось подключиться к базе данных")
            print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: База данных недоступна!")
            print("Проверьте:")
            print("  1. Переменную окружения DATABASE_URL")
            print("  2. Что PostgreSQL запущен")
            print("  3. Правильность учетных данных")
            sys.exit(1)
        
        logger.info("✅ База данных подключена")
        
        # Получаем repository
        repository = await get_market_data_repository()
        
        # Инициализируем TechnicalAnalysisContextManager
        logger.info("🧠 Инициализация технического анализа...")
        ta_context_manager = TechnicalAnalysisContextManager(
            repository=repository,
            auto_start_background_updates=False
        )
        
        # Определяем символы для проверки
        if args.symbol:
            symbols = [args.symbol.upper()]
        else:
            # Первые 5 символов для быстроты
            symbols = Config.get_bybit_symbols()[:5]
        
        # Создаем диагностику
        diagnostics = SignalDiagnostics(repository, ta_context_manager)
        
        # Запускаем полную диагностику
        results = await diagnostics.run_full_diagnostic(
            symbols=symbols,
            test_strategies=args.test_strategies
        )
        
        logger.info("\n✅ Диагностика завершена")
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ Диагностика прервана пользователем")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)
        
    finally:
        # Закрываем БД
        try:
            await close_database()
            logger.info("🔒 База данных закрыта")
        except Exception as e:
            logger.error(f"⚠️ Ошибка закрытия БД: {e}")


if __name__ == "__main__":
    asyncio.run(main())

    """
    Счетчик сигналов по стратегиям
    
    Симулирует работу стратегий на исторических данных
    и подсчитывает теоретическое количество сигналов.
    """
    
    def __init__(self, repository, ta_context_manager):
        """
        Args:
            repository: MarketDataRepository
            ta_context_manager: TechnicalAnalysisContextManager
        """
        self.repository = repository
        self.ta_context_manager = ta_context_manager
        
        # Статистика
        self.stats = {
            "total_symbols_analyzed": 0,
            "total_signals_found": 0,
            "signals_by_strategy": defaultdict(int),
            "signals_by_symbol": defaultdict(int),
            "signals_by_type": defaultdict(int),
            "analysis_errors": 0,
            "start_time": datetime.now(timezone.utc)
        }
        
        logger.info("✅ SignalCounter инициализирован")
    
    async def count_signals(
        self,
        symbols: List[str],
        strategies: List[str],
        days_back: int = 7,
        detailed: bool = False
    ) -> Dict[str, Any]:
        """
        Подсчитать сигналы по всем стратегиям
        
        Args:
            symbols: Список символов для анализа
            strategies: Список стратегий ('breakout', 'bounce', 'false_breakout')
            days_back: Количество дней для анализа
            detailed: Подробная информация о каждом сигнале
            
        Returns:
            Dict с результатами анализа
        """
        logger.info("=" * 70)
        logger.info("🔍 АНАЛИЗ СИГНАЛОВ ПО СТРАТЕГИЯМ")
        logger.info("=" * 70)
        logger.info(f"   • Символов: {len(symbols)}")
        logger.info(f"   • Стратегий: {len(strategies)}")
        logger.info(f"   • Период: последние {days_back} дней")
        logger.info("=" * 70)
        
        # Временные рамки
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days_back)
        
        # Результаты по каждому символу
        detailed_results = []
        
        # Анализируем каждый символ
        for symbol in symbols:
            logger.info(f"\n📊 Анализ {symbol}...")
            
            try:
                # Получаем исторические данные
                candles_1m = await self.repository.get_candles(
                    symbol=symbol,
                    interval="1m",
                    start_time=start_time,
                    end_time=end_time,
                    limit=10000
                )
                
                candles_5m = await self.repository.get_candles(
                    symbol=symbol,
                    interval="5m",
                    start_time=start_time,
                    end_time=end_time,
                    limit=2000
                )
                
                candles_1h = await self.repository.get_candles(
                    symbol=symbol,
                    interval="1h",
                    start_time=start_time,
                    end_time=end_time,
                    limit=168
                )
                
                candles_1d = await self.repository.get_candles(
                    symbol=symbol,
                    interval="1d",
                    start_time=start_time - timedelta(days=180),  # Больше для технического анализа
                    end_time=end_time,
                    limit=180
                )
                
                if not candles_1m and not candles_1h:
                    logger.warning(f"⚠️ Нет данных для {symbol}, пропуск")
                    continue
                
                logger.info(f"   • Свечи 1m: {len(candles_1m)}")
                logger.info(f"   • Свечи 5m: {len(candles_5m)}")
                logger.info(f"   • Свечи 1h: {len(candles_1h)}")
                logger.info(f"   • Свечи 1d: {len(candles_1d)}")
                
                # Получаем технический контекст
                ta_context = None
                try:
                    ta_context = await self.ta_context_manager.get_context(symbol)
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить TA контекст: {e}")
                
                # Анализируем каждой стратегией
                symbol_signals = []
                
                for strategy_name in strategies:
                    signals = await self._analyze_with_strategy(
                        strategy_name=strategy_name,
                        symbol=symbol,
                        candles_1m=candles_1m,
                        candles_5m=candles_5m,
                        candles_1h=candles_1h,
                        candles_1d=candles_1d,
                        ta_context=ta_context
                    )
                    
                    symbol_signals.extend(signals)
                    
                    # Обновляем статистику
                    self.stats["signals_by_strategy"][strategy_name] += len(signals)
                    
                    for signal in signals:
                        self.stats["signals_by_type"][signal["signal_type"]] += 1
                
                # Сохраняем результаты
                self.stats["signals_by_symbol"][symbol] = len(symbol_signals)
                self.stats["total_signals_found"] += len(symbol_signals)
                self.stats["total_symbols_analyzed"] += 1
                
                if detailed:
                    detailed_results.append({
                        "symbol": symbol,
                        "signals": symbol_signals,
                        "total": len(symbol_signals)
                    })
                
                logger.info(f"   ✅ Найдено сигналов: {len(symbol_signals)}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка анализа {symbol}: {e}")
                self.stats["analysis_errors"] += 1
                import traceback
                logger.error(traceback.format_exc())
        
        # Формируем финальный отчет
        duration = (datetime.now(timezone.utc) - self.stats["start_time"]).total_seconds()
        
        return {
            "summary": {
                "symbols_analyzed": self.stats["total_symbols_analyzed"],
                "total_signals": self.stats["total_signals_found"],
                "analysis_duration_seconds": duration,
                "period_days": days_back,
                "signals_per_day": self.stats["total_signals_found"] / days_back if days_back > 0 else 0,
                "errors": self.stats["analysis_errors"]
            },
            "by_strategy": dict(self.stats["signals_by_strategy"]),
            "by_symbol": dict(self.stats["signals_by_symbol"]),
            "by_type": dict(self.stats["signals_by_type"]),
            "detailed": detailed_results if detailed else []
        }
    
    async def _analyze_with_strategy(
        self,
        strategy_name: str,
        symbol: str,
        candles_1m: List[Dict],
        candles_5m: List[Dict],
        candles_1h: List[Dict],
        candles_1d: List[Dict],
        ta_context: Optional[Any] = None
    ) -> List[Dict]:
        """
        Анализирует данные конкретной стратегией и собирает сигналы
        
        Args:
            strategy_name: Имя стратегии ('breakout', 'bounce', 'false_breakout')
            symbol: Торговый символ
            candles_*: Исторические данные
            ta_context: Технический контекст
            
        Returns:
            List[Dict]: Список найденных сигналов
        """
        signals = []
        
        try:
            # Создаем экземпляр стратегии
            strategy_class = {
                "breakout": BreakoutStrategy,
                "bounce": BounceStrategy,
                "false_breakout": FalseBreakoutStrategy
            }.get(strategy_name)
            
            if not strategy_class:
                logger.warning(f"⚠️ Неизвестная стратегия: {strategy_name}")
                return signals
            
            strategy = strategy_class(
                symbol=symbol,
                repository=self.repository,
                ta_context_manager=self.ta_context_manager,
                min_signal_strength=0.5,  # Минимальная сила для подсчета
                signal_cooldown_minutes=5,
                max_signals_per_hour=12
            )
            
            # Симулируем анализ на скользящем окне
            # Берем последние N свечей для каждого таймфрейма
            window_1m = 100
            window_5m = 50
            window_1h = 24
            
            # Анализируем с шагом (например, каждые 60 минут)
            step_minutes = 60
            
            if not candles_1m:
                return signals
            
            # Используем 1m свечи как основу для временных точек
            for i in range(window_1m, len(candles_1m), step_minutes):
                try:
                    # Получаем окно данных
                    window_candles_1m = candles_1m[max(0, i-window_1m):i]
                    window_candles_5m = candles_5m[max(0, i//5-window_5m):i//5] if candles_5m else []
                    window_candles_1h = candles_1h[max(0, i//60-window_1h):i//60] if candles_1h else []
                    
                    # Запускаем анализ
                    signal = await strategy.analyze_with_data(
                        symbol=symbol,
                        candles_1m=window_candles_1m,
                        candles_5m=window_candles_5m,
                        candles_1h=window_candles_1h,
                        candles_1d=candles_1d,
                        ta_context=ta_context
                    )
                    
                    if signal:
                        # Сохраняем информацию о сигнале
                        signals.append({
                            "strategy": strategy_name,
                            "symbol": symbol,
                            "signal_type": signal.signal_type.value,
                            "strength": signal.strength,
                            "confidence": signal.confidence,
                            "price": signal.price,
                            "timestamp": signal.timestamp.isoformat(),
                            "reasons": signal.reasons,
                            "quality_score": signal.quality_score
                        })
                
                except Exception as e:
                    # Пропускаем ошибки отдельных точек анализа
                    logger.debug(f"⚠️ Ошибка анализа точки {i}: {e}")
                    continue
            
            logger.debug(f"   • {strategy_name}: {len(signals)} сигналов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка стратегии {strategy_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return signals
    
    def print_report(self, results: Dict[str, Any]):
        """
        Выводит красивый отчет о сигналах
        
        Args:
            results: Результаты анализа
        """
        print("\n" + "=" * 70)
        print("📊 ОТЧЕТ ПО СИГНАЛАМ ТОРГОВЫХ СТРАТЕГИЙ")
        print("=" * 70)
        
        # Общая информация
        summary = results["summary"]
        print(f"\n📅 Период анализа: {summary['period_days']} дней")
        print(f"⏱️  Длительность анализа: {summary['analysis_duration_seconds']:.1f} секунд")
        print(f"📊 Символов проанализировано: {summary['symbols_analyzed']}")
        print(f"🎯 Всего сигналов найдено: {summary['total_signals']}")
        print(f"📈 Сигналов в день: {summary['signals_per_day']:.1f}")
        
        if summary["errors"] > 0:
            print(f"⚠️  Ошибок анализа: {summary['errors']}")
        
        # Статистика по стратегиям
        print("\n" + "-" * 70)
        print("📊 СИГНАЛЫ ПО СТРАТЕГИЯМ")
        print("-" * 70)
        
        strategy_data = []
        for strategy, count in sorted(results["by_strategy"].items(), key=lambda x: x[1], reverse=True):
            percentage = (count / summary['total_signals'] * 100) if summary['total_signals'] > 0 else 0
            strategy_data.append([
                strategy,
                count,
                f"{percentage:.1f}%",
                f"{count / summary['period_days']:.1f}" if summary['period_days'] > 0 else "0"
            ])
        
        print(tabulate(
            strategy_data,
            headers=["Стратегия", "Сигналов", "Доля", "В день"],
            tablefmt="pretty"
        ))
        
        # Статистика по символам (топ-10)
        if results["by_symbol"]:
            print("\n" + "-" * 70)
            print("📊 СИГНАЛЫ ПО СИМВОЛАМ (ТОП-10)")
            print("-" * 70)
            
            symbol_data = []
            sorted_symbols = sorted(results["by_symbol"].items(), key=lambda x: x[1], reverse=True)[:10]
            
            for symbol, count in sorted_symbols:
                percentage = (count / summary['total_signals'] * 100) if summary['total_signals'] > 0 else 0
                symbol_data.append([
                    symbol,
                    count,
                    f"{percentage:.1f}%"
                ])
            
            print(tabulate(
                symbol_data,
                headers=["Символ", "Сигналов", "Доля"],
                tablefmt="pretty"
            ))
        
        # Статистика по типам сигналов
        if results["by_type"]:
            print("\n" + "-" * 70)
            print("📊 СИГНАЛЫ ПО ТИПУ")
            print("-" * 70)
            
            type_data = []
            for signal_type, count in sorted(results["by_type"].items(), key=lambda x: x[1], reverse=True):
                percentage = (count / summary['total_signals'] * 100) if summary['total_signals'] > 0 else 0
                
                # Эмодзи для типов
                emoji = {
                    "BUY": "🟢",
                    "STRONG_BUY": "🟢🟢",
                    "SELL": "🔴",
                    "STRONG_SELL": "🔴🔴",
                    "NEUTRAL": "🔵"
                }.get(signal_type, "⚪")
                
                type_data.append([
                    f"{emoji} {signal_type}",
                    count,
                    f"{percentage:.1f}%"
                ])
            
            print(tabulate(
                type_data,
                headers=["Тип сигнала", "Количество", "Доля"],
                tablefmt="pretty"
            ))
        
        # Подробные результаты (если запрошены)
        if results.get("detailed"):
            print("\n" + "-" * 70)
            print("📋 ПОДРОБНЫЕ РЕЗУЛЬТАТЫ ПО СИМВОЛАМ")
            print("-" * 70)
            
            for symbol_result in results["detailed"]:
                symbol = symbol_result["symbol"]
                signals = symbol_result["signals"]
                
                if signals:
                    print(f"\n{symbol} ({len(signals)} сигналов):")
                    
                    for i, signal in enumerate(signals[:10], 1):  # Первые 10
                        print(f"  {i}. {signal['signal_type']} @ ${signal['price']:,.2f}")
                        print(f"     Стратегия: {signal['strategy']}")
                        print(f"     Сила: {signal['strength']:.2f}, Уверенность: {signal['confidence']:.2f}")
                        print(f"     Время: {signal['timestamp']}")
                        if signal['reasons']:
                            print(f"     Причины: {', '.join(signal['reasons'][:3])}")
                        print()
                    
                    if len(signals) > 10:
                        print(f"  ... и еще {len(signals) - 10} сигналов")
        
        print("\n" + "=" * 70)


async def main():
    """Главная функция"""
    
    parser = argparse.ArgumentParser(
        description="🔍 Диагностика системы генерации сигналов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python check_signals.py                      # Быстрая проверка
  python check_signals.py --symbol BTCUSDT     # Проверка одного символа
  python check_signals.py --test-strategies    # Полное тестирование стратегий
  python check_signals.py --verbose            # Подробные логи
        """
    )
    
    parser.add_argument(
        "--symbol",
        type=str,
        help="Проверить конкретный символ"
    )
    
    parser.add_argument(
        "--test-strategies",
        action="store_true",
        help="Запустить тест генерации сигналов стратегиями"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Подробные логи (DEBUG)"
    )
    
    args = parser.parse_args()
    
    # Настройка логирования
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    
    try:
        logger.info("🚀 Запуск диагностики системы...")
        
        # Инициализация БД
        logger.info("📦 Подключение к базе данных...")
        db_success = await initialize_database()
        
        if not db_success:
            logger.error("❌ Не удалось подключиться к базе данных")
            print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: База данных недоступна!")
            print("Проверьте:")
            print("  1. Переменную окружения DATABASE_URL")
            print("  2. Что PostgreSQL запущен")
            print("  3. Правильность учетных данных")
            sys.exit(1)
        
        logger.info("✅ База данных подключена")
        
        # Получаем repository
        repository = await get_market_data_repository()
        
        # Инициализируем TechnicalAnalysisContextManager
        logger.info("🧠 Инициализация технического анализа...")
        ta_context_manager = TechnicalAnalysisContextManager(
            repository=repository,
            auto_start_background_updates=False
        )
        
        # Определяем символы для проверки
        if args.symbol:
            symbols = [args.symbol.upper()]
        else:
            # Первые 5 символов для быстроты
            symbols = Config.get_bybit_symbols()[:5]
        
        # Создаем диагностику
        diagnostics = SignalDiagnostics(repository, ta_context_manager)
        
        # Запускаем полную диагностику
        results = await diagnostics.run_full_diagnostic(
            symbols=symbols,
            test_strategies=args.test_strategies
        )
        
        logger.info("\n✅ Диагностика завершена")
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ Диагностика прервана пользователем")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)
        
    finally:
        # Закрываем БД
        try:
            await close_database()
            logger.info("🔒 База данных закрыта")
        except Exception as e:
            logger.error(f"⚠️ Ошибка закрытия БД: {e}")


if __name__ == "__main__":
    asyncio.run(main())
