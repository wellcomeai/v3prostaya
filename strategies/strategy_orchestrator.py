"""
Strategy Orchestrator - Координатор торговых стратегий

Управляет выполнением всех торговых стратегий:
- Запускает анализ каждую минуту для всех символов
- Координирует получение данных из Repository и TA Context Manager
- Передает сигналы в SignalManager для обработки
- Обеспечивает параллельное выполнение и обработку ошибок

Architecture:
- TechnicalAnalysisContextManager -> кэшированный техн. анализ
- Repository -> свежие данные из БД
- Strategies -> генерация сигналов
- SignalManager -> обработка и рассылка

Author: Trading Bot Team
Version: 3.0.1 - FIXED: Removed MomentumStrategy
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class OrchestratorStatus(Enum):
    """Статус оркестратора"""
    IDLE = "idle"
    RUNNING = "running"
    ANALYZING = "analyzing"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class AnalysisResult:
    """Результат анализа одного символа"""
    symbol: str
    success: bool
    signals_count: int
    strategies_run: int
    execution_time: float
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CycleStats:
    """Статистика одного цикла анализа"""
    cycle_number: int
    start_time: datetime
    end_time: Optional[datetime] = None
    symbols_analyzed: int = 0
    signals_count: int = 0
    errors_count: int = 0
    execution_time: float = 0.0
    
    def finalize(self):
        """Завершить цикл и рассчитать время"""
        self.end_time = datetime.now(timezone.utc)
        self.execution_time = (self.end_time - self.start_time).total_seconds()


class StrategyOrchestrator:
    """
    🎭 Координатор торговых стратегий v3.0
    
    Управляет выполнением всех стратегий для всех символов.
    Запускается каждую минуту, анализирует все пары параллельно.
    
    Features:
    - Параллельный анализ всех символов
    - Кэширование технического контекста
    - Умное получение данных из БД
    - Обработка ошибок без остановки
    - Детальная статистика и метрики
    - Graceful shutdown
    """
    
    def __init__(
        self,
        repository,
        ta_context_manager,
        signal_manager,
        symbols: List[str],
        analysis_interval_seconds: int = 60,
        enabled_strategies: List[str] = None
    ):
        """
        Args:
            repository: MarketDataRepository для доступа к БД
            ta_context_manager: TechnicalAnalysisContextManager для техн. анализа
            signal_manager: SignalManager для обработки сигналов
            symbols: Список символов для анализа
            analysis_interval_seconds: Интервал между циклами (секунды)
            enabled_strategies: Список включенных стратегий (None = все)
        """
        self.repository = repository
        self.ta_context_manager = ta_context_manager
        self.signal_manager = signal_manager
        self.symbols = symbols
        self.analysis_interval = analysis_interval_seconds
        
        # Статус
        self.status = OrchestratorStatus.IDLE
        self.is_running = False
        self.start_time: Optional[datetime] = None
        
        # Задачи
        self._main_task: Optional[asyncio.Task] = None
        
        # Инициализация стратегий
        self.strategies = self._initialize_strategies(enabled_strategies)
        
        # Статистика
        self.stats = {
            "total_cycles": 0,
            "total_symbols_analyzed": 0,
            "total_signals_generated": 0,
            "total_errors": 0,
            "uptime_seconds": 0,
            "last_cycle_time": None,
            "average_cycle_time": 0.0,
            "cycles_history": []  # Последние 100 циклов
        }
        
        # История последнего цикла
        self.last_cycle: Optional[CycleStats] = None
        self.symbol_results: Dict[str, AnalysisResult] = {}
        
        logger.info("=" * 70)
        logger.info("🎭 StrategyOrchestrator v3.0 инициализирован")
        logger.info("=" * 70)
        logger.info(f"   • Символы: {len(symbols)}")
        logger.info(f"   • Стратегии: {len(self.strategies)}")
        logger.info(f"   • Интервал анализа: {analysis_interval_seconds}s")
        logger.info(f"   • Repository: {'✅' if repository else '❌'}")
        logger.info(f"   • TA Manager: {'✅' if ta_context_manager else '❌'}")
        logger.info(f"   • Signal Manager: {'✅' if signal_manager else '❌'}")
        logger.info("=" * 70)
        
        # Логируем стратегии
        for strategy in self.strategies:
            strategy_name = strategy.__class__.__name__
            logger.info(f"   ✅ {strategy_name}")
        
        logger.info("=" * 70)
    
    def _initialize_strategies(self, enabled_strategies: List[str] = None):
        """
        Инициализация стратегий
        
        Args:
            enabled_strategies: Список названий стратегий для включения
            
        Returns:
            List[BaseStrategy]: Список инициализированных стратегий
        """
        # ✅ ИСПРАВЛЕНО: Убран MomentumStrategy
        from strategies import (
            BreakoutStrategy,
            BounceStrategy,
            FalseBreakoutStrategy
        )
        
        # ✅ ИСПРАВЛЕНО: Только 3 стратегии v3.0
        available_strategies = {
            "breakout": BreakoutStrategy,
            "bounce": BounceStrategy,
            "false_breakout": FalseBreakoutStrategy
        }
        
        # Если не указано - включаем все
        if enabled_strategies is None:
            enabled_strategies = list(available_strategies.keys())
        
        # Создаем экземпляры
        strategies = []
        for name in enabled_strategies:
            if name.lower() in available_strategies:
                strategy_class = available_strategies[name.lower()]
                try:
                    # Стратегии сейчас требуют symbol и ta_context_manager в конструкторе
                    # Но мы будем передавать данные через analyze_with_data
                    # Поэтому создаем с фиктивными параметрами
                    strategy = strategy_class(
                        symbol="PLACEHOLDER",  # Будет переопределено при анализе
                        ta_context_manager=self.ta_context_manager
                    )
                    strategies.append(strategy)
                    logger.info(f"✅ Инициализирована стратегия: {strategy_class.__name__}")
                except Exception as e:
                    logger.error(f"❌ Ошибка инициализации {name}: {e}")
            else:
                logger.warning(f"⚠️ Неизвестная стратегия: {name}")
        
        if not strategies:
            logger.warning("⚠️ Ни одна стратегия не инициализирована!")
        
        return strategies
    
    async def start(self):
        """Запуск оркестратора"""
        if self.is_running:
            logger.warning("⚠️ StrategyOrchestrator уже запущен")
            return
        
        try:
            logger.info("🚀 Запуск StrategyOrchestrator...")
            
            # Проверка зависимостей
            if not self.repository:
                raise ValueError("Repository не инициализирован")
            
            if not self.ta_context_manager:
                raise ValueError("TechnicalAnalysisContextManager не инициализирован")
            
            if not self.signal_manager:
                raise ValueError("SignalManager не инициализирован")
            
            if not self.strategies:
                raise ValueError("Нет инициализированных стратегий")
            
            # Запуск
            self.is_running = True
            self.status = OrchestratorStatus.RUNNING
            self.start_time = datetime.now(timezone.utc)
            
            # Запускаем основной цикл
            self._main_task = asyncio.create_task(self._main_loop())
            
            logger.info("✅ StrategyOrchestrator запущен успешно")
            logger.info(f"   • Будет анализировать {len(self.symbols)} символов каждые {self.analysis_interval}s")
            logger.info(f"   • Активных стратегий: {len(self.strategies)}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска StrategyOrchestrator: {e}")
            self.is_running = False
            self.status = OrchestratorStatus.ERROR
            raise
    
    async def stop(self):
        """Остановка оркестратора"""
        if not self.is_running:
            logger.warning("⚠️ StrategyOrchestrator уже остановлен")
            return
        
        logger.info("🛑 Остановка StrategyOrchestrator...")
        
        self.is_running = False
        self.status = OrchestratorStatus.STOPPED
        
        # Отменяем основную задачу
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
        
        # Финальная статистика
        uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        logger.info("=" * 70)
        logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА STRATEGY ORCHESTRATOR")
        logger.info("=" * 70)
        logger.info(f"   • Время работы: {uptime:.0f}s ({uptime/3600:.1f}h)")
        logger.info(f"   • Циклов выполнено: {self.stats['total_cycles']}")
        logger.info(f"   • Символов проанализировано: {self.stats['total_symbols_analyzed']}")
        logger.info(f"   • Сигналов сгенерировано: {self.stats['total_signals_generated']}")
        logger.info(f"   • Ошибок: {self.stats['total_errors']}")
        logger.info(f"   • Среднее время цикла: {self.stats['average_cycle_time']:.2f}s")
        logger.info("=" * 70)
        
        logger.info("✅ StrategyOrchestrator остановлен")
    
    async def _main_loop(self):
        """Основной цикл анализа"""
        logger.info("🔄 Основной цикл StrategyOrchestrator запущен")
        
        while self.is_running:
            try:
                cycle_start = datetime.now(timezone.utc)
                
                # Запускаем цикл анализа
                await self._run_analysis_cycle()
                
                # Пауза до следующего цикла
                cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(0, self.analysis_interval - cycle_duration)
                
                if wait_time > 0:
                    logger.debug(f"💤 Ожидание {wait_time:.1f}s до следующего цикла")
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(f"⚠️ Цикл занял {cycle_duration:.1f}s (больше интервала {self.analysis_interval}s)")
                
            except asyncio.CancelledError:
                logger.info("🛑 Основной цикл отменен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в основном цикле: {e}")
                self.stats["total_errors"] += 1
                self.status = OrchestratorStatus.ERROR
                
                # Пауза при ошибке
                await asyncio.sleep(60)
                self.status = OrchestratorStatus.RUNNING
    
    async def _run_analysis_cycle(self):
        """Выполнить один цикл анализа всех символов"""
        try:
            self.status = OrchestratorStatus.ANALYZING
            
            # Создаем статистику цикла
            cycle_stats = CycleStats(
                cycle_number=self.stats["total_cycles"] + 1,
                start_time=datetime.now(timezone.utc)
            )
            
            logger.info("=" * 70)
            logger.info(f"🔍 ЦИКЛ АНАЛИЗА #{cycle_stats.cycle_number}")
            logger.info("=" * 70)
            logger.info(f"   • Символов: {len(self.symbols)}")
            logger.info(f"   • Стратегий: {len(self.strategies)}")
            
            # Анализируем все символы параллельно
            tasks = [
                self._analyze_symbol(symbol)
                for symbol in self.symbols
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            for result in results:
                if isinstance(result, AnalysisResult):
                    self.symbol_results[result.symbol] = result
                    cycle_stats.symbols_analyzed += 1
                    cycle_stats.signals_count += result.signals_count
                    
                    if not result.success:
                        cycle_stats.errors_count += 1
                elif isinstance(result, Exception):
                    logger.error(f"❌ Необработанная ошибка в цикле: {result}")
                    cycle_stats.errors_count += 1
            
            # Финализируем статистику
            cycle_stats.finalize()
            
            # Обновляем общую статистику
            self.stats["total_cycles"] += 1
            self.stats["total_symbols_analyzed"] += cycle_stats.symbols_analyzed
            self.stats["total_signals_generated"] += cycle_stats.signals_count
            self.stats["total_errors"] += cycle_stats.errors_count
            self.stats["last_cycle_time"] = cycle_stats.start_time
            
            # Обновляем среднее время цикла
            total_time = self.stats.get("total_cycle_time", 0) + cycle_stats.execution_time
            self.stats["total_cycle_time"] = total_time
            self.stats["average_cycle_time"] = total_time / self.stats["total_cycles"]
            
            # Сохраняем историю (последние 100 циклов)
            self.stats["cycles_history"].append({
                "cycle": cycle_stats.cycle_number,
                "time": cycle_stats.start_time.isoformat(),
                "symbols": cycle_stats.symbols_analyzed,
                "signals": cycle_stats.signals_count,
                "errors": cycle_stats.errors_count,
                "duration": cycle_stats.execution_time
            })
            
            if len(self.stats["cycles_history"]) > 100:
                self.stats["cycles_history"].pop(0)
            
            self.last_cycle = cycle_stats
            
            # Логируем результаты
            logger.info("=" * 70)
            logger.info(f"✅ ЦИКЛ #{cycle_stats.cycle_number} ЗАВЕРШЕН")
            logger.info("=" * 70)
            logger.info(f"   • Проанализировано символов: {cycle_stats.symbols_analyzed}/{len(self.symbols)}")
            logger.info(f"   • Сигналов сгенерировано: {cycle_stats.signals_count}")
            logger.info(f"   • Ошибок: {cycle_stats.errors_count}")
            logger.info(f"   • Время выполнения: {cycle_stats.execution_time:.2f}s")
            logger.info("=" * 70)
            
            self.status = OrchestratorStatus.RUNNING
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в цикле анализа: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats["total_errors"] += 1
            self.status = OrchestratorStatus.ERROR
    
    async def _analyze_symbol(self, symbol: str) -> AnalysisResult:
        """
        Анализ одного символа всеми стратегиями
        
        Args:
            symbol: Торговый символ (BTCUSDT, ETHUSDT, etc)
            
        Returns:
            AnalysisResult: Результат анализа
        """
        start_time = datetime.now(timezone.utc)
        signals_count = 0
        strategies_run = 0
        
        try:
            logger.debug(f"📊 Анализ {symbol}...")
            
            # ШАГ 1: Получаем технический контекст (кэшированный)
            ta_context = await self.ta_context_manager.get_context(
                symbol=symbol,
                interval="1h"  # Основной интервал для контекста
            )
            
            if not ta_context:
                logger.warning(f"⚠️ {symbol}: технический контекст недоступен")
            
            # ШАГ 2: Получаем свежие свечи из БД
            now = datetime.now(timezone.utc)
            
            # Минутные свечи (последние 100)
            candles_1m = await self.repository.get_candles(
                symbol=symbol,
                interval="1m",
                start_time=now - timedelta(hours=2),
                end_time=now,
                limit=100
            )
            
            # 5-минутные свечи (последние 50)
            candles_5m = await self.repository.get_candles(
                symbol=symbol,
                interval="5m",
                start_time=now - timedelta(hours=5),
                end_time=now,
                limit=50
            )
            
            # Часовые свечи (последние 24)
            candles_1h = await self.repository.get_candles(
                symbol=symbol,
                interval="1h",
                start_time=now - timedelta(hours=24),
                end_time=now,
                limit=24
            )
            
            # Дневные свечи (последние 180 для уровней)
            candles_1d = await self.repository.get_candles(
                symbol=symbol,
                interval="1d",
                start_time=now - timedelta(days=180),
                end_time=now,
                limit=180
            )
            
            # Проверка минимального количества данных
            if not candles_1m or len(candles_1m) < 10:
                logger.warning(f"⚠️ {symbol}: недостаточно данных M1 ({len(candles_1m) if candles_1m else 0})")
                return AnalysisResult(
                    symbol=symbol,
                    success=False,
                    signals_count=0,
                    strategies_run=0,
                    execution_time=0,
                    error="Insufficient data"
                )
            
            # ШАГ 3: Запускаем все стратегии
            for strategy in self.strategies:
                try:
                    strategies_run += 1
                    
                    # Вызываем analyze с данными
                    signal = await strategy.analyze_with_data(
                        symbol=symbol,
                        candles_1m=candles_1m,
                        candles_5m=candles_5m,
                        candles_1h=candles_1h,
                        candles_1d=candles_1d,
                        ta_context=ta_context
                    )
                    
                    # Если есть сигнал - передаем в SignalManager
                    if signal:
                        await self.signal_manager.process_signal(signal)
                        signals_count += 1
                        
                        logger.info(
                            f"🔔 {symbol}: {strategy.__class__.__name__} → "
                            f"{signal.signal_type.name} (сила: {signal.strength:.2f})"
                        )
                
                except Exception as e:
                    logger.error(f"❌ {symbol}: ошибка в {strategy.__class__.__name__}: {e}")
                    continue
            
            # Успешно завершили
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            return AnalysisResult(
                symbol=symbol,
                success=True,
                signals_count=signals_count,
                strategies_run=strategies_run,
                execution_time=execution_time
            )
            
        except Exception as e:
            logger.error(f"❌ {symbol}: критическая ошибка анализа: {e}")
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            return AnalysisResult(
                symbol=symbol,
                success=False,
                signals_count=0,
                strategies_run=strategies_run,
                execution_time=execution_time,
                error=str(e)
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить полную статистику"""
        uptime = 0
        if self.start_time:
            uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        return {
            **self.stats,
            "status": self.status.value,
            "is_running": self.is_running,
            "uptime_seconds": uptime,
            "uptime_formatted": str(timedelta(seconds=int(uptime))),
            "symbols_count": len(self.symbols),
            "strategies_count": len(self.strategies),
            "analysis_interval": self.analysis_interval,
            "last_cycle": {
                "cycle_number": self.last_cycle.cycle_number if self.last_cycle else 0,
                "start_time": self.last_cycle.start_time.isoformat() if self.last_cycle else None,
                "symbols_analyzed": self.last_cycle.symbols_analyzed if self.last_cycle else 0,
                "signals_count": self.last_cycle.signals_count if self.last_cycle else 0,
                "errors_count": self.last_cycle.errors_count if self.last_cycle else 0,
                "execution_time": self.last_cycle.execution_time if self.last_cycle else 0
            } if self.last_cycle else None
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Проверка здоровья оркестратора"""
        is_healthy = (
            self.is_running and
            self.status == OrchestratorStatus.RUNNING and
            self.stats["total_errors"] < 100
        )
        
        # Проверка что циклы выполняются
        if self.stats["last_cycle_time"]:
            time_since_last_cycle = (
                datetime.now(timezone.utc) - self.stats["last_cycle_time"]
            ).total_seconds()
            
            # Если прошло больше 2 интервалов - что-то не так
            if time_since_last_cycle > self.analysis_interval * 2:
                is_healthy = False
        
        return {
            "healthy": is_healthy,
            "status": self.status.value,
            "is_running": self.is_running,
            "total_cycles": self.stats["total_cycles"],
            "total_signals": self.stats["total_signals_generated"],
            "total_errors": self.stats["total_errors"],
            "last_cycle_time": self.stats["last_cycle_time"].isoformat() if self.stats["last_cycle_time"] else None,
            "average_cycle_time": self.stats["average_cycle_time"]
        }
    
    def __repr__(self):
        return (
            f"StrategyOrchestrator("
            f"symbols={len(self.symbols)}, "
            f"strategies={len(self.strategies)}, "
            f"status={self.status.value}, "
            f"cycles={self.stats['total_cycles']})"
        )


# Export
__all__ = [
    "StrategyOrchestrator",
    "OrchestratorStatus",
    "AnalysisResult",
    "CycleStats"
]

logger.info("✅ StrategyOrchestrator module loaded successfully")
