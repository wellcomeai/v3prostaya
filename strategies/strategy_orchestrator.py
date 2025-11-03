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
Version: 3.1.2 - FIXED: Низкие пороги сигналов + поддержка фьючерсов с малым кол-вом данных
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
    🎭 Координатор торговых стратегий v3.1.2
    
    Управляет выполнением всех стратегий для всех символов.
    Запускается каждую минуту, анализирует все пары параллельно.
    
    Features:
    - Параллельный анализ всех символов
    - Кэширование технического контекста
    - Умное получение данных из БД
    - Обработка ошибок без остановки
    - Детальная статистика и метрики
    - Graceful shutdown
    - ✅ Синхронизация времени с data sync
    - ✅ Правильные запросы данных (без end_time для M1/M5)
    - ✅ Валидация минимального количества свечей
    - ✅ Поддержка фьючерсов с нерабочими часами
    - ✅ FIXED v3.1.2: Низкие пороги (min_signal_strength=0.3)
    - ✅ FIXED v3.1.2: Поддержка фьючерсов (MIN_CANDLES 1d: 30)
    """
    
    # ✅ ИСПРАВЛЕНО v3.1.2: Снижены требования к данным для поддержки фьючерсов
    MIN_CANDLES = {
        "1m": 60,    # 60 минут = 1 час (было 100)
        "5m": 30,    # 150 минут = 2.5 часа (было 50)
        "1h": 24,    # 24 часа = 1 день (без изменений)
        "1d": 30     # 30 дней = 1 месяц (было 180!) - КРИТИЧНО для фьючерсов
    }
    
    # ✅ Задержка старта для синхронизации с data sync
    SYNC_START_SECOND = 40  # Запускаем анализ в :40 секунды каждой минуты
    
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
            "cycles_history": []
        }
        
        # История последнего цикла
        self.last_cycle: Optional[CycleStats] = None
        self.symbol_results: Dict[str, AnalysisResult] = {}
        
        logger.info("=" * 70)
        logger.info("🎭 StrategyOrchestrator v3.1.2 инициализирован")
        logger.info("=" * 70)
        logger.info(f"   • Символы: {len(symbols)}")
        logger.info(f"   • Стратегии: {len(self.strategies)}")
        logger.info(f"   • Интервал анализа: {analysis_interval_seconds}s")
        logger.info(f"   • Старт в : {self.SYNC_START_SECOND} секунды каждой минуты")
        logger.info(f"   • Repository: {'✅' if repository else '❌'}")
        logger.info(f"   • TA Manager: {'✅' if ta_context_manager else '❌'}")
        logger.info(f"   • Signal Manager: {'✅' if signal_manager else '❌'}")
        logger.info("=" * 70)
        
        for strategy in self.strategies:
            logger.info(f"   ✅ {strategy.__class__.__name__}")
        
        logger.info("=" * 70)
        logger.info("📊 Минимальные требования к данным:")
        for interval, min_count in self.MIN_CANDLES.items():
            logger.info(f"   • {interval}: {min_count} свечей")
        logger.info("=" * 70)
    
    def _initialize_strategies(self, enabled_strategies: List[str] = None):
        """
        ✅ ИСПРАВЛЕНО v3.1.2: Добавлены параметры min_signal_strength и cooldown
        """
        from strategies import (
            BreakoutStrategy,
            BounceStrategy,
            FalseBreakoutStrategy
        )
        
        available_strategies = {
            "breakout": BreakoutStrategy,
            "bounce": BounceStrategy,
            "false_breakout": FalseBreakoutStrategy
        }
        
        if enabled_strategies is None:
            enabled_strategies = list(available_strategies.keys())
        
        strategies = []
        for name in enabled_strategies:
            if name.lower() in available_strategies:
                strategy_class = available_strategies[name.lower()]
                try:
                    # ✅ ИСПРАВЛЕНО v3.1.2: Добавлены критически важные параметры!
                    strategy = strategy_class(
                        symbol="PLACEHOLDER",
                        ta_context_manager=self.ta_context_manager,
                        min_signal_strength=0.3,  # ✅ НИЗКИЙ ПОРОГ!
                        signal_cooldown_minutes=15,  # ✅ Разумный cooldown
                        max_signals_per_hour=4  # ✅ Не слишком часто
                    )
                    strategies.append(strategy)
                    logger.info(f"✅ Инициализирована стратегия: {strategy_class.__name__} (min_strength=0.3)")
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
            
            if not self.repository:
                raise ValueError("Repository не инициализирован")
            if not self.ta_context_manager:
                raise ValueError("TechnicalAnalysisContextManager не инициализирован")
            if not self.signal_manager:
                raise ValueError("SignalManager не инициализирован")
            if not self.strategies:
                raise ValueError("Нет инициализированных стратегий")
            
            self.is_running = True
            self.status = OrchestratorStatus.RUNNING
            self.start_time = datetime.now(timezone.utc)
            
            self._main_task = asyncio.create_task(self._main_loop())
            
            logger.info("✅ StrategyOrchestrator запущен успешно")
            logger.info(f"   • Будет анализировать {len(self.symbols)} символов каждые {self.analysis_interval}s")
            logger.info(f"   • Активных стратегий: {len(self.strategies)}")
            logger.info(f"   • Старт анализа в :{self.SYNC_START_SECOND} секунды каждой минуты")
            
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
        
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
        
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
        
        await self._wait_for_sync_time()
        
        while self.is_running:
            try:
                cycle_start = datetime.now(timezone.utc)
                
                await self._run_analysis_cycle()
                
                cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = await self._calculate_wait_time(cycle_duration)
                
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
                await asyncio.sleep(60)
                self.status = OrchestratorStatus.RUNNING
    
    async def _wait_for_sync_time(self):
        """Ожидание синхронизированного времени старта"""
        now = datetime.now(timezone.utc)
        current_second = now.second
        
        if current_second < self.SYNC_START_SECOND:
            wait_seconds = self.SYNC_START_SECOND - current_second
        else:
            wait_seconds = (60 - current_second) + self.SYNC_START_SECOND
        
        if wait_seconds > 0:
            logger.info(f"⏰ Синхронизация времени: ожидание {wait_seconds}s до :{self.SYNC_START_SECOND} секунды")
            await asyncio.sleep(wait_seconds)
    
    async def _calculate_wait_time(self, cycle_duration: float) -> float:
        """Расчёт времени ожидания с учётом синхронизации"""
        now = datetime.now(timezone.utc)
        current_second = now.second
        
        if current_second < self.SYNC_START_SECOND:
            seconds_until_next = self.SYNC_START_SECOND - current_second
        else:
            seconds_until_next = (60 - current_second) + self.SYNC_START_SECOND
        
        return max(0, seconds_until_next)
    
    async def _run_analysis_cycle(self):
        """Выполнить один цикл анализа всех символов"""
        try:
            self.status = OrchestratorStatus.ANALYZING
            
            cycle_stats = CycleStats(
                cycle_number=self.stats["total_cycles"] + 1,
                start_time=datetime.now(timezone.utc)
            )
            
            logger.info("=" * 70)
            logger.info(f"🔍 ЦИКЛ АНАЛИЗА #{cycle_stats.cycle_number}")
            logger.info("=" * 70)
            logger.info(f"   • Символов: {len(self.symbols)}")
            logger.info(f"   • Стратегий: {len(self.strategies)}")
            
            tasks = [self._analyze_symbol(symbol) for symbol in self.symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
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
            
            cycle_stats.finalize()
            
            self.stats["total_cycles"] += 1
            self.stats["total_symbols_analyzed"] += cycle_stats.symbols_analyzed
            self.stats["total_signals_generated"] += cycle_stats.signals_count
            self.stats["total_errors"] += cycle_stats.errors_count
            self.stats["last_cycle_time"] = cycle_stats.start_time
            
            total_time = self.stats.get("total_cycle_time", 0) + cycle_stats.execution_time
            self.stats["total_cycle_time"] = total_time
            self.stats["average_cycle_time"] = total_time / self.stats["total_cycles"]
            
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
            symbol: Торговый символ (BTCUSDT, ETHUSDT, MCL, MGC, etc)
            
        Returns:
            AnalysisResult: Результат анализа
        """
        start_time = datetime.now(timezone.utc)
        signals_count = 0
        strategies_run = 0
        
        try:
            logger.debug(f"📊 Анализ {symbol}...")
            
            # ШАГ 1: Получаем технический контекст (кэшированный)
            ta_context = await self.ta_context_manager.get_context(symbol=symbol)
            
            if not ta_context:
                logger.warning(f"⚠️ {symbol}: технический контекст недоступен")
            
            # ШАГ 2: Получаем свежие свечи из БД
            now = datetime.now(timezone.utc)
            
            # ✅ КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ v3.1.1:
            # Убран end_time для M1 и M5 - берём последние N свечей что есть
            # Это важно для фьючерсов которые не торгуются ночью!
            
            # Минутные свечи (последние 60)
            # БЕЗ end_time - возьмёт последние 60 даже если они вчерашние
            candles_1m = await self.repository.get_candles(
                symbol=symbol,
                interval="1m",
                start_time=now - timedelta(days=1),  # Последние 24 часа
                limit=self.MIN_CANDLES["1m"]
            )
            
            # 5-минутные свечи (последние 30)
            # БЕЗ end_time
            candles_5m = await self.repository.get_candles(
                symbol=symbol,
                interval="5m",
                start_time=now - timedelta(days=2),  # Последние 48 часов
                limit=self.MIN_CANDLES["5m"]
            )
            
            # Часовые свечи (последние 24)
            # Можно с end_time так как это длинный период
            candles_1h = await self.repository.get_candles(
                symbol=symbol,
                interval="1h",
                start_time=now - timedelta(days=2),
                limit=self.MIN_CANDLES["1h"]
            )
            
            # Дневные свечи (последние 30)
            # ✅ ИСПРАВЛЕНО v3.1.2: Было 180, стало 30 - поддержка фьючерсов!
            candles_1d = await self.repository.get_candles(
                symbol=symbol,
                interval="1d",
                start_time=now - timedelta(days=50),  # С запасом
                limit=self.MIN_CANDLES["1d"]
            )
            
            # ✅ Улучшенная валидация данных v3.1.2
            data_validation = self._validate_candles_data(
                symbol=symbol,
                candles_1m=candles_1m,
                candles_5m=candles_5m,
                candles_1h=candles_1h,
                candles_1d=candles_1d
            )
            
            if not data_validation["valid"]:
                logger.warning(f"⚠️ {symbol}: {data_validation['error']}")
                return AnalysisResult(
                    symbol=symbol,
                    success=False,
                    signals_count=0,
                    strategies_run=0,
                    execution_time=0,
                    error=data_validation['error']
                )
            
            # ШАГ 3: Запускаем все стратегии
            for strategy in self.strategies:
                try:
                    strategies_run += 1
                    
                    signal = await strategy.analyze_with_data(
                        symbol=symbol,
                        candles_1m=candles_1m,
                        candles_5m=candles_5m,
                        candles_1h=candles_1h,
                        candles_1d=candles_1d,
                        ta_context=ta_context
                    )
                    
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
    
    def _validate_candles_data(
        self,
        symbol: str,
        candles_1m: List,
        candles_5m: List,
        candles_1h: List,
        candles_1d: List
    ) -> Dict[str, Any]:
        """
        ✅ ИСПРАВЛЕНО v3.1.2: Смягченная валидация - требуем только критичные интервалы
        """
        details = {
            "1m": {
                "received": len(candles_1m) if candles_1m else 0,
                "required": self.MIN_CANDLES["1m"],
                "valid": False,
                "critical": False  # ✅ Опционально
            },
            "5m": {
                "received": len(candles_5m) if candles_5m else 0,
                "required": self.MIN_CANDLES["5m"],
                "valid": False,
                "critical": False  # ✅ Опционально
            },
            "1h": {
                "received": len(candles_1h) if candles_1h else 0,
                "required": self.MIN_CANDLES["1h"],
                "valid": False,
                "critical": True  # ✅ Обязательно!
            },
            "1d": {
                "received": len(candles_1d) if candles_1d else 0,
                "required": self.MIN_CANDLES["1d"],
                "valid": False,
                "critical": True  # ✅ Обязательно!
            }
        }
        
        errors = []
        
        # ✅ Проверяем только КРИТИЧНЫЕ интервалы (1h и 1d)
        for interval, data in details.items():
            if data["received"] >= data["required"]:
                data["valid"] = True
            elif data["critical"]:  # ✅ Ошибка только для критичных
                errors.append(f"{interval}: {data['received']}/{data['required']}")
        
        if errors:
            return {
                "valid": False,
                "error": f"Недостаточно критичных данных: {', '.join(errors)}",
                "details": details
            }
        
        return {
            "valid": True,
            "error": None,
            "details": details
        }
    
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
            "sync_start_second": self.SYNC_START_SECOND,
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
        
        if self.stats["last_cycle_time"]:
            time_since_last_cycle = (
                datetime.now(timezone.utc) - self.stats["last_cycle_time"]
            ).total_seconds()
            
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
            "average_cycle_time": self.stats["average_cycle_time"],
            "sync_second": self.SYNC_START_SECOND
        }
    
    def __repr__(self):
        return (
            f"StrategyOrchestrator("
            f"symbols={len(self.symbols)}, "
            f"strategies={len(self.strategies)}, "
            f"status={self.status.value}, "
            f"cycles={self.stats['total_cycles']})"
        )


__all__ = [
    "StrategyOrchestrator",
    "OrchestratorStatus",
    "AnalysisResult",
    "CycleStats"
]

logger.info("✅ StrategyOrchestrator v3.1.2 module loaded successfully - FIXED: Low thresholds + futures support")
