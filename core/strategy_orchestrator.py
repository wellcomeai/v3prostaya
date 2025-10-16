"""
Simplified Strategy Orchestrator v2.0

Упрощенный оркестратор стратегий без MarketDataSnapshot и DataSourceAdapter.
Стратегии работают напрямую с Repository и сами получают нужные данные.

Ключевые изменения:
- ❌ Убрана зависимость от MarketDataSnapshot
- ❌ Убрана зависимость от DataSourceAdapter
- ❌ Убрана зависимость от MarketDataManager
- ✅ Прямая работа с Repository
- ✅ Простой цикл анализа (каждые 60 секунд)
- ✅ Стратегии сами получают данные
- ✅ Сохранены все фильтры и мониторинг

Author: Trading Bot Team
Version: 2.0.0 - Simplified Architecture
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Callable
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict, deque
import traceback

from strategies import BaseStrategy, TradingSignal, MomentumStrategy, get_available_strategies, create_strategy
from .signal_manager import SignalManager
from .data_models import SystemConfig, StrategyConfig

logger = logging.getLogger(__name__)


# ==================== ENUMS ====================

class OrchestratorStatus(Enum):
    """Статусы оркестратора"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    DEGRADED = "degraded"  # Работает, но не все стратегии активны


class StrategyStatus(Enum):
    """Статусы отдельных стратегий"""
    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


# ==================== STRATEGY INSTANCE ====================

@dataclass
class StrategyInstance:
    """
    Экземпляр стратегии с метаданными
    
    Содержит саму стратегию и всю статистику её работы
    """
    strategy: BaseStrategy
    config: StrategyConfig
    status: StrategyStatus = StrategyStatus.INACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    last_analysis_at: Optional[datetime] = None
    last_signal_at: Optional[datetime] = None
    error_count: int = 0
    total_analyses: int = 0
    successful_analyses: int = 0
    signals_generated: int = 0
    average_analysis_time: float = 0.0
    last_error: Optional[str] = None
    
    def __post_init__(self):
        """Пост-инициализация"""
        self.strategy_name = self.strategy.name
    
    @property
    def success_rate(self) -> float:
        """Процент успешных анализов"""
        if self.total_analyses == 0:
            return 100.0
        return (self.successful_analyses / self.total_analyses) * 100
    
    @property
    def uptime(self) -> timedelta:
        """Время работы стратегии"""
        return datetime.now() - self.created_at
    
    def update_analysis_stats(self, success: bool, analysis_time: float):
        """Обновляет статистику анализов"""
        self.total_analyses += 1
        self.last_analysis_at = datetime.now()
        
        if success:
            self.successful_analyses += 1
        else:
            self.error_count += 1
        
        # Обновляем скользящее среднее времени анализа
        if self.total_analyses == 1:
            self.average_analysis_time = analysis_time
        else:
            self.average_analysis_time = (
                (self.average_analysis_time * (self.total_analyses - 1) + analysis_time) 
                / self.total_analyses
            )
    
    def record_signal(self):
        """Записывает генерацию сигнала"""
        self.signals_generated += 1
        self.last_signal_at = datetime.now()
    
    def record_error(self, error_message: str):
        """Записывает ошибку"""
        self.error_count += 1
        self.last_error = error_message
        self.status = StrategyStatus.ERROR
        logger.error(f"❌ Ошибка в стратегии {self.strategy_name}: {error_message}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь"""
        return {
            "strategy_name": self.strategy_name,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_analysis_at": self.last_analysis_at.isoformat() if self.last_analysis_at else None,
            "last_signal_at": self.last_signal_at.isoformat() if self.last_signal_at else None,
            "uptime_seconds": self.uptime.total_seconds(),
            "error_count": self.error_count,
            "total_analyses": self.total_analyses,
            "successful_analyses": self.successful_analyses,
            "signals_generated": self.signals_generated,
            "success_rate": self.success_rate,
            "average_analysis_time": self.average_analysis_time,
            "last_error": self.last_error
        }


# ==================== STRATEGY ORCHESTRATOR ====================

class StrategyOrchestrator:
    """
    🚀 Упрощенный оркестратор торговых стратегий v2.0
    
    Ключевые изменения:
    - ❌ Нет MarketDataSnapshot
    - ❌ Нет DataSourceAdapter
    - ❌ Нет MarketDataManager
    - ✅ Простой цикл: каждые 60 секунд вызываем analyze() у стратегий
    - ✅ Стратегии сами получают данные из БД через repository
    
    Что осталось:
    - ✅ Управление жизненным циклом стратегий
    - ✅ Передача сигналов в SignalManager
    - ✅ Мониторинг производительности
    - ✅ Error recovery
    - ✅ Health monitoring
    
    Usage:
        ```python
        orchestrator = StrategyOrchestrator(
            signal_manager=signal_manager,
            repository=repository,
            ta_context_manager=ta_context_manager,  # Опционально
            system_config=system_config,
            analysis_interval=60.0  # Каждую минуту
        )
        
        await orchestrator.start()
        ```
    """
    
    def __init__(
        self,
        signal_manager: SignalManager,
        repository,  # MarketDataRepository
        ta_context_manager=None,  # TechnicalAnalysisContextManager (опционально)
        system_config: Optional[SystemConfig] = None,
        analysis_interval: float = 60.0,  # Секунд между анализами
        max_concurrent_analyses: int = 5,
        enable_performance_monitoring: bool = True
    ):
        """
        Инициализация оркестратора
        
        Args:
            signal_manager: Менеджер сигналов
            repository: MarketDataRepository для доступа к БД
            ta_context_manager: Менеджер технического анализа (опционально)
            system_config: Конфигурация системы
            analysis_interval: Интервал между анализами в секундах (по умолчанию 60с)
            max_concurrent_analyses: Максимум одновременных анализов
            enable_performance_monitoring: Включить мониторинг производительности
        """
        self.signal_manager = signal_manager
        self.repository = repository
        self.ta_context_manager = ta_context_manager
        self.system_config = system_config
        
        # Настройки работы
        self.analysis_interval = analysis_interval
        self.max_concurrent_analyses = max_concurrent_analyses
        self.enable_performance_monitoring = enable_performance_monitoring
        
        # Состояние оркестратора
        self.status = OrchestratorStatus.STOPPED
        self.strategy_instances: Dict[str, StrategyInstance] = {}
        
        # Управление жизненным циклом
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        
        # Фоновые задачи
        self.background_tasks: List[asyncio.Task] = []
        self.analysis_task: Optional[asyncio.Task] = None
        
        # Семафор для ограничения параллелизма
        self.analysis_semaphore = asyncio.Semaphore(max_concurrent_analyses)
        
        # Метрики и статистика
        self.stats = {
            "total_analyses": 0,
            "successful_analyses": 0,
            "failed_analyses": 0,
            "signals_generated": 0,
            "signals_sent": 0,
            "start_time": None,
            "last_analysis_time": None,
            "strategies_loaded": 0,
            "strategies_active": 0,
            "strategies_failed": 0,
            "analysis_cycles": 0,
            "average_cycle_time": 0.0
        }
        
        # История производительности (последние 100 циклов)
        self.performance_history: deque = deque(maxlen=100)
        
        # Callback'и для событий
        self.event_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        
        logger.info(f"🎭 StrategyOrchestrator v2.0 инициализирован")
        logger.info(f"   • Интервал анализа: {analysis_interval}с")
        logger.info(f"   • Макс. параллельных анализов: {max_concurrent_analyses}")
        logger.info(f"   • Repository: {'✓' if repository else '✗'}")
        logger.info(f"   • TechnicalAnalysis: {'✓' if ta_context_manager else '✗'}")
    
    # ==================== LIFECYCLE MANAGEMENT ====================
    
    async def start(self) -> bool:
        """
        Запуск оркестратора
        
        Returns:
            True если запуск успешен
        """
        try:
            if self.status != OrchestratorStatus.STOPPED:
                logger.warning(f"⚠️ Оркестратор уже запущен (статус: {self.status.value})")
                return False
            
            logger.info("🚀 Запуск StrategyOrchestrator v2.0...")
            self.status = OrchestratorStatus.STARTING
            self.is_running = True
            self.stats["start_time"] = datetime.now()
            
            # Загружаем стратегии из конфигурации
            await self._load_strategies()
            
            # Запускаем фоновые задачи
            await self._start_background_tasks()
            
            # Запускаем основной цикл анализа
            self.analysis_task = asyncio.create_task(self._analysis_loop())
            
            self.status = OrchestratorStatus.RUNNING
            logger.info("✅ StrategyOrchestrator запущен успешно")
            logger.info(f"📊 Загружено стратегий: {len(self.strategy_instances)}")
            logger.info(f"⚡ Активных стратегий: {self._count_active_strategies()}")
            
            # Уведомляем о запуске
            await self._emit_event("orchestrator_started", {"strategies_count": len(self.strategy_instances)})
            
            return True
            
        except Exception as e:
            logger.error(f"💥 Ошибка запуска StrategyOrchestrator: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            self.status = OrchestratorStatus.ERROR
            await self.stop()
            return False
    
    async def stop(self):
        """Graceful shutdown оркестратора"""
        try:
            logger.info("🔄 Остановка StrategyOrchestrator...")
            self.status = OrchestratorStatus.STOPPING
            self.is_running = False
            self.shutdown_event.set()
            
            # Останавливаем основной цикл анализа
            if self.analysis_task and not self.analysis_task.done():
                self.analysis_task.cancel()
                try:
                    await self.analysis_task
                except asyncio.CancelledError:
                    pass
            
            # Останавливаем фоновые задачи
            if self.background_tasks:
                logger.info(f"⏹️ Останавливаю {len(self.background_tasks)} фоновых задач...")
                for task in self.background_tasks:
                    if not task.done():
                        task.cancel()
                
                await asyncio.gather(*self.background_tasks, return_exceptions=True)
                logger.info("✅ Фоновые задачи остановлены")
            
            # Деактивируем все стратегии
            for strategy_instance in self.strategy_instances.values():
                strategy_instance.status = StrategyStatus.STOPPED
            
            # Финальная статистика
            await self._log_final_statistics()
            
            self.status = OrchestratorStatus.STOPPED
            logger.info("🛑 StrategyOrchestrator остановлен")
            
            # Уведомляем об остановке
            await self._emit_event("orchestrator_stopped", self.get_stats())
            
        except Exception as e:
            logger.error(f"❌ Ошибка при остановке StrategyOrchestrator: {e}")
            self.status = OrchestratorStatus.ERROR
    
    # ==================== STRATEGY MANAGEMENT ====================
    
    async def _load_strategies(self):
        """Загружает и инициализирует стратегии из конфигурации"""
        try:
            strategies_loaded = 0
            strategies_failed = 0
            
            # Если нет конфигурации, создаем базовую MomentumStrategy
            if not self.system_config or not self.system_config.strategy_configs:
                logger.info("📝 Конфигурация стратегий не найдена, создаю базовую MomentumStrategy")
                await self._create_default_strategies()
                return
            
            # Загружаем стратегии из конфигурации
            for name, config in self.system_config.strategy_configs.items():
                try:
                    if not config.enabled:
                        logger.info(f"⏸️ Стратегия {name} отключена в конфигурации")
                        continue
                    
                    logger.info(f"📥 Загружаю стратегию: {name}")
                    strategy_instance = await self._create_strategy_instance(config)
                    
                    if strategy_instance:
                        self.strategy_instances[name] = strategy_instance
                        strategies_loaded += 1
                        logger.info(f"✅ Стратегия {name} загружена")
                    else:
                        strategies_failed += 1
                        logger.error(f"❌ Не удалось создать стратегию {name}")
                        
                except Exception as e:
                    strategies_failed += 1
                    logger.error(f"❌ Ошибка загрузки стратегии {name}: {e}")
            
            self.stats["strategies_loaded"] = strategies_loaded
            self.stats["strategies_failed"] = strategies_failed
            
            logger.info(f"📊 Результат загрузки: ✅{strategies_loaded} успешно, ❌{strategies_failed} ошибок")
            
            if strategies_loaded == 0:
                logger.warning("⚠️ Ни одна стратегия не загружена, создаю базовую")
                await self._create_default_strategies()
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка загрузки стратегий: {e}")
            raise
    
    async def _create_default_strategies(self):
        """Создает базовые стратегии по умолчанию"""
        try:
            # Создаем базовую MomentumStrategy
            momentum_config = StrategyConfig(
                name="MomentumStrategy",
                description="Базовая импульсная стратегия",
                strategy_params={
                    "extreme_movement_threshold": 2.0,
                    "impulse_1m_threshold": 1.5,
                    "impulse_5m_threshold": 2.0,
                    "high_volume_threshold": 20000,
                    "enable_volume_analysis": True
                }
            )
            
            strategy_instance = await self._create_strategy_instance(momentum_config)
            if strategy_instance:
                self.strategy_instances["MomentumStrategy"] = strategy_instance
                self.stats["strategies_loaded"] = 1
                logger.info("✅ Базовая MomentumStrategy создана")
            else:
                logger.error("❌ Не удалось создать базовую стратегию")
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания базовых стратегий: {e}")
            raise
    
    async def _create_strategy_instance(self, config: StrategyConfig) -> Optional[StrategyInstance]:
        """
        Создает экземпляр стратегии по конфигурации
        
        Args:
            config: Конфигурация стратегии
            
        Returns:
            StrategyInstance или None при ошибке
        """
        try:
            # Определяем тип стратегии
            strategy_type = config.name.lower().replace("strategy", "")
            
            # Создаем стратегию (теперь с repository и ta_context_manager)
            if strategy_type == "momentum":
                strategy = MomentumStrategy(
                    name=config.name,
                    symbol=config.symbol,
                    repository=self.repository,  # ✅ Передаем repository
                    ta_context_manager=self.ta_context_manager,  # ✅ Опционально
                    min_signal_strength=config.min_signal_strength,
                    signal_cooldown_minutes=config.signal_cooldown_minutes,
                    max_signals_per_hour=config.max_signals_per_hour,
                    **config.strategy_params
                )
            else:
                # Пытаемся создать через фабрику стратегий
                try:
                    strategy = create_strategy(
                        strategy_type,
                        repository=self.repository,
                        ta_context_manager=self.ta_context_manager,
                        **config.strategy_params
                    )
                except Exception as e:
                    logger.error(f"❌ Неизвестный тип стратегии: {strategy_type}, ошибка: {e}")
                    return None
            
            # Создаем экземпляр с метаданными
            strategy_instance = StrategyInstance(
                strategy=strategy,
                config=config,
                status=StrategyStatus.INITIALIZING
            )
            
            # Применяем настройки отладки если включен debug mode
            if self.system_config and self.system_config.debug_mode:
                strategy.enable_debug_mode(True)
            
            strategy_instance.status = StrategyStatus.ACTIVE
            return strategy_instance
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания стратегии {config.name}: {e}")
            logger.error(traceback.format_exc())
            return None
    
    # ==================== ANALYSIS LOOP ====================
    
    async def _analysis_loop(self):
        """
        🔄 Основной цикл анализа (упрощенный)
        
        Простая логика:
        1. Каждые N секунд (analysis_interval)
        2. Запускаем analyze() у всех активных стратегий
        3. Стратегии сами получают данные из БД
        4. Отправляем сигналы в SignalManager
        """
        logger.info("🔄 Запущен основной цикл анализа (упрощенный v2.0)")
        logger.info(f"   • Интервал: {self.analysis_interval}с")
        logger.info(f"   • Стратегии сами получают данные из БД")
        
        while self.is_running and not self.shutdown_event.is_set():
            try:
                cycle_start_time = datetime.now()
                
                # Запускаем анализ всех активных стратегий
                await self._analyze_all_strategies()
                
                # Обновляем статистику цикла
                cycle_end_time = datetime.now()
                cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
                
                self.stats["analysis_cycles"] += 1
                self.stats["last_analysis_time"] = cycle_end_time
                
                # Обновляем скользящее среднее времени цикла
                if self.stats["analysis_cycles"] == 1:
                    self.stats["average_cycle_time"] = cycle_duration
                else:
                    prev_avg = self.stats["average_cycle_time"]
                    cycles_count = self.stats["analysis_cycles"]
                    self.stats["average_cycle_time"] = (prev_avg * (cycles_count - 1) + cycle_duration) / cycles_count
                
                # Сохраняем для истории производительности
                if self.enable_performance_monitoring:
                    self.performance_history.append({
                        "timestamp": cycle_end_time,
                        "cycle_duration": cycle_duration,
                        "strategies_analyzed": self._count_active_strategies()
                    })
                
                # Ждем до следующего цикла
                await asyncio.sleep(self.analysis_interval)
                
            except asyncio.CancelledError:
                logger.info("🔄 Цикл анализа отменен")
                break
            except Exception as e:
                logger.error(f"💥 Ошибка в цикле анализа: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.stats["failed_analyses"] += 1
                
                # При критических ошибках - пауза перед продолжением
                await asyncio.sleep(5)
        
        logger.info("🛑 Основной цикл анализа остановлен")
    
    async def _analyze_all_strategies(self):
        """
        Запускает анализ всех активных стратегий параллельно
        
        Каждая стратегия сама вызывает repository.get_recent_candles()
        """
        try:
            active_strategies = [
                instance for instance in self.strategy_instances.values()
                if instance.status == StrategyStatus.ACTIVE
            ]
            
            if not active_strategies:
                return
            
            # Создаем задачи для параллельного анализа
            analysis_tasks = [
                asyncio.create_task(self._analyze_single_strategy(instance))
                for instance in active_strategies
            ]
            
            # Ждем завершения всех анализов
            results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            successful_analyses = 0
            signals_generated = 0
            
            for i, result in enumerate(results):
                strategy_name = active_strategies[i].strategy_name
                
                if isinstance(result, Exception):
                    logger.error(f"❌ Ошибка анализа {strategy_name}: {result}")
                    active_strategies[i].record_error(str(result))
                    self.stats["failed_analyses"] += 1
                elif result:  # Сигнал сгенерирован
                    successful_analyses += 1
                    signals_generated += 1
                    active_strategies[i].record_signal()
                    
                    # Отправляем сигнал в SignalManager
                    await self.signal_manager.submit_signal(result)
                else:  # Анализ успешен, но сигнал не сгенерирован
                    successful_analyses += 1
            
            # Обновляем общую статистику
            self.stats["successful_analyses"] += successful_analyses
            self.stats["signals_generated"] += signals_generated
            
            if signals_generated > 0:
                logger.info(f"📊 Цикл анализа: ✅{successful_analyses} успешно, 🚨{signals_generated} сигналов")
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в _analyze_all_strategies: {e}")
            self.stats["failed_analyses"] += 1
    
    async def _analyze_single_strategy(self, strategy_instance: StrategyInstance) -> Optional[TradingSignal]:
        """
        Анализирует рынок одной стратегией
        
        Args:
            strategy_instance: Экземпляр стратегии
            
        Returns:
            TradingSignal если сгенерирован, None если нет
        """
        analysis_start_time = datetime.now()
        
        try:
            # Используем семафор для ограничения параллелизма
            async with self.analysis_semaphore:
                # Вызываем run_analysis() - стратегия сама получит данные
                signal = await strategy_instance.strategy.run_analysis()
                
                # Вычисляем время анализа
                analysis_duration = (datetime.now() - analysis_start_time).total_seconds()
                
                # Обновляем статистику стратегии
                strategy_instance.update_analysis_stats(True, analysis_duration)
                
                return signal
                
        except Exception as e:
            analysis_duration = (datetime.now() - analysis_start_time).total_seconds()
            strategy_instance.update_analysis_stats(False, analysis_duration)
            strategy_instance.record_error(str(e))
            logger.error(f"❌ Ошибка анализа стратегии {strategy_instance.strategy_name}: {e}")
            raise
    
    # ==================== BACKGROUND TASKS ====================
    
    async def _start_background_tasks(self):
        """Запускает фоновые задачи"""
        try:
            # Задача мониторинга производительности
            if self.enable_performance_monitoring:
                performance_task = asyncio.create_task(self._performance_monitoring_task())
                self.background_tasks.append(performance_task)
                logger.info("📊 Запущен мониторинг производительности")
            
            # Задача проверки здоровья стратегий
            health_task = asyncio.create_task(self._health_monitoring_task())
            self.background_tasks.append(health_task)
            logger.info("🏥 Запущен мониторинг здоровья стратегий")
            
            # Задача периодической статистики
            stats_task = asyncio.create_task(self._statistics_task())
            self.background_tasks.append(stats_task)
            logger.info("📈 Запущена задача статистики")
            
            logger.info(f"🔄 Запущено {len(self.background_tasks)} фоновых задач")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска фоновых задач: {e}")
    
    async def _performance_monitoring_task(self):
        """Задача мониторинга производительности"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(300)  # Каждые 5 минут
                
                # Анализируем производительность за последний час
                performance_report = self._analyze_performance()
                
                if performance_report:
                    logger.info(f"📊 Отчет о производительности: {performance_report}")
                    
                    # Уведомляем о проблемах производительности
                    if performance_report.get("slow_strategies"):
                        await self._emit_event("performance_degradation", performance_report)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в мониторинге производительности: {e}")
                await asyncio.sleep(60)
    
    async def _health_monitoring_task(self):
        """Задача мониторинга здоровья стратегий"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(120)  # Каждые 2 минуты
                
                # Проверяем здоровье всех стратегий
                health_issues = []
                
                for name, instance in self.strategy_instances.items():
                    issue = self._check_strategy_health(instance)
                    if issue:
                        health_issues.append((name, issue))
                
                # Обрабатываем проблемы
                for strategy_name, issue in health_issues:
                    logger.warning(f"⚠️ Проблема со стратегией {strategy_name}: {issue}")
                    
                    # Пытаемся восстановить стратегию если возможно
                    if issue == "too_many_errors":
                        await self._attempt_strategy_recovery(strategy_name)
                
                # Обновляем статус оркестратора
                self._update_orchestrator_status()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в мониторинге здоровья: {e}")
                await asyncio.sleep(60)
    
    async def _statistics_task(self):
        """Задача периодической статистики"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(1800)  # Каждые 30 минут
                
                # Логируем текущую статистику
                stats = self.get_stats()
                logger.info(f"📈 Статистика оркестратора:")
                logger.info(f"   • Циклов анализа: {stats['analysis_cycles']}")
                logger.info(f"   • Успешных анализов: {stats['successful_analyses']}")
                logger.info(f"   • Сигналов сгенерировано: {stats['signals_generated']}")
                logger.info(f"   • Активных стратегий: {stats['strategies_active']}")
                logger.info(f"   • Среднее время цикла: {stats['average_cycle_time']:.3f}с")
                
                # Статистика по стратегиям
                for name, instance in self.strategy_instances.items():
                    logger.info(f"   📊 {name}: анализов={instance.total_analyses}, "
                              f"сигналов={instance.signals_generated}, "
                              f"успешность={instance.success_rate:.1f}%")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в задаче статистики: {e}")
                await asyncio.sleep(300)
    
    # ==================== HELPER METHODS ====================
    
    def _analyze_performance(self) -> Optional[Dict[str, Any]]:
        """Анализирует производительность системы"""
        try:
            if not self.performance_history:
                return None
            
            # Анализируем последние записи (за час)
            recent_records = list(self.performance_history)[-20:]
            
            if len(recent_records) < 5:
                return None
            
            # Средние показатели
            avg_cycle_time = sum(r["cycle_duration"] for r in recent_records) / len(recent_records)
            max_cycle_time = max(r["cycle_duration"] for r in recent_records)
            
            # Ищем медленные стратегии
            slow_strategies = []
            for name, instance in self.strategy_instances.items():
                if instance.average_analysis_time > 5.0:  # Более 5 секунд
                    slow_strategies.append({
                        "name": name,
                        "avg_time": instance.average_analysis_time,
                        "error_rate": (instance.error_count / max(instance.total_analyses, 1)) * 100
                    })
            
            return {
                "avg_cycle_time": round(avg_cycle_time, 3),
                "max_cycle_time": round(max_cycle_time, 3),
                "slow_strategies": slow_strategies,
                "records_analyzed": len(recent_records)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа производительности: {e}")
            return None
    
    def _check_strategy_health(self, instance: StrategyInstance) -> Optional[str]:
        """
        Проверяет здоровье стратегии
        
        Returns:
            Строка с описанием проблемы или None если все в порядке
        """
        try:
            # Проверка на слишком много ошибок
            if instance.total_analyses > 10:
                error_rate = instance.error_count / instance.total_analyses
                if error_rate > 0.5:  # Более 50% ошибок
                    return "too_many_errors"
            
            # Проверка на долгое отсутствие активности
            if instance.last_analysis_at:
                time_since_analysis = datetime.now() - instance.last_analysis_at
                if time_since_analysis > timedelta(minutes=10):
                    return "inactive_too_long"
            
            # Проверка на слишком медленный анализ
            if instance.average_analysis_time > 10.0:  # Более 10 секунд
                return "analysis_too_slow"
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки здоровья стратегии: {e}")
            return "health_check_error"
    
    async def _attempt_strategy_recovery(self, strategy_name: str):
        """Пытается восстановить проблемную стратегию"""
        try:
            if strategy_name not in self.strategy_instances:
                return
            
            instance = self.strategy_instances[strategy_name]
            
            logger.info(f"🔄 Попытка восстановления стратегии {strategy_name}")
            
            # Сбрасываем статистику ошибок
            instance.error_count = 0
            instance.last_error = None
            instance.status = StrategyStatus.ACTIVE
            
            # Сбрасываем внутреннюю статистику стратегии если есть соответствующий метод
            if hasattr(instance.strategy, 'reset_stats'):
                instance.strategy.reset_stats()
            
            logger.info(f"✅ Стратегия {strategy_name} восстановлена")
            await self._emit_event("strategy_recovered", {"strategy": strategy_name})
            
        except Exception as e:
            logger.error(f"❌ Ошибка восстановления стратегии {strategy_name}: {e}")
    
    def _update_orchestrator_status(self):
        """Обновляет общий статус оркестратора"""
        try:
            active_count = self._count_active_strategies()
            total_count = len(self.strategy_instances)
            failed_count = sum(1 for i in self.strategy_instances.values() if i.status == StrategyStatus.ERROR)
            
            self.stats["strategies_active"] = active_count
            self.stats["strategies_failed"] = failed_count
            
            # Определяем статус
            if not self.is_running:
                self.status = OrchestratorStatus.STOPPED
            elif active_count == 0:
                self.status = OrchestratorStatus.ERROR
            elif active_count < total_count / 2:  # Менее половины стратегий работают
                self.status = OrchestratorStatus.DEGRADED
            else:
                self.status = OrchestratorStatus.RUNNING
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса оркестратора: {e}")
    
    def _count_active_strategies(self) -> int:
        """Подсчитывает количество активных стратегий"""
        return sum(1 for instance in self.strategy_instances.values() 
                  if instance.status == StrategyStatus.ACTIVE)
    
    async def _emit_event(self, event_name: str, data: Any):
        """Испускает событие для подписчиков"""
        try:
            callbacks = self.event_callbacks.get(event_name, [])
            if callbacks:
                for callback in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(data)
                        else:
                            callback(data)
                    except Exception as e:
                        logger.error(f"❌ Ошибка в callback события {event_name}: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка испускания события {event_name}: {e}")
    
    async def _log_final_statistics(self):
        """Логирует финальную статистику при остановке"""
        try:
            stats = self.get_stats()
            uptime = datetime.now() - self.stats["start_time"]
            
            logger.info("📊 Финальная статистика StrategyOrchestrator:")
            logger.info(f"   • Время работы: {uptime}")
            logger.info(f"   • Циклов анализа: {stats['analysis_cycles']}")
            logger.info(f"   • Успешных анализов: {stats['successful_analyses']}")
            logger.info(f"   • Неудачных анализов: {stats['failed_analyses']}")
            logger.info(f"   • Сигналов сгенерировано: {stats['signals_generated']}")
            logger.info(f"   • Стратегий загружено: {stats['strategies_loaded']}")
            logger.info(f"   • Успешность: {stats['success_rate']:.2f}%")
            
        except Exception as e:
            logger.error(f"❌ Ошибка логирования финальной статистики: {e}")
    
    # ==================== PUBLIC API ====================
    
    def add_event_callback(self, event_name: str, callback: Callable):
        """Добавляет callback для события"""
        self.event_callbacks[event_name].append(callback)
        logger.info(f"📝 Добавлен callback для события {event_name}")
    
    def remove_event_callback(self, event_name: str, callback: Callable):
        """Удаляет callback для события"""
        if event_name in self.event_callbacks:
            try:
                self.event_callbacks[event_name].remove(callback)
                logger.info(f"🗑️ Удален callback для события {event_name}")
            except ValueError:
                logger.warning(f"⚠️ Callback для события {event_name} не найден")
    
    async def add_strategy(self, config: StrategyConfig) -> bool:
        """Добавляет новую стратегию во время работы"""
        try:
            if config.name in self.strategy_instances:
                logger.warning(f"⚠️ Стратегия {config.name} уже существует")
                return False
            
            logger.info(f"➕ Добавление стратегии {config.name}")
            
            strategy_instance = await self._create_strategy_instance(config)
            if strategy_instance:
                self.strategy_instances[config.name] = strategy_instance
                self.stats["strategies_loaded"] += 1
                
                logger.info(f"✅ Стратегия {config.name} добавлена")
                await self._emit_event("strategy_added", {"strategy": config.name})
                return True
            else:
                logger.error(f"❌ Не удалось создать стратегию {config.name}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления стратегии {config.name}: {e}")
            return False
    
    async def remove_strategy(self, strategy_name: str) -> bool:
        """Удаляет стратегию"""
        try:
            if strategy_name not in self.strategy_instances:
                logger.warning(f"⚠️ Стратегия {strategy_name} не найдена")
                return False
            
            logger.info(f"➖ Удаление стратегии {strategy_name}")
            
            # Деактивируем стратегию
            instance = self.strategy_instances[strategy_name]
            instance.status = StrategyStatus.STOPPED
            
            # Удаляем из словаря
            del self.strategy_instances[strategy_name]
            
            logger.info(f"✅ Стратегия {strategy_name} удалена")
            await self._emit_event("strategy_removed", {"strategy": strategy_name})
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления стратегии {strategy_name}: {e}")
            return False
    
    async def pause_strategy(self, strategy_name: str) -> bool:
        """Приостанавливает стратегию"""
        try:
            if strategy_name in self.strategy_instances:
                self.strategy_instances[strategy_name].status = StrategyStatus.PAUSED
                logger.info(f"⏸️ Стратегия {strategy_name} приостановлена")
                await self._emit_event("strategy_paused", {"strategy": strategy_name})
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка паузы стратегии {strategy_name}: {e}")
            return False
    
    async def resume_strategy(self, strategy_name: str) -> bool:
        """Возобновляет работу стратегии"""
        try:
            if strategy_name in self.strategy_instances:
                instance = self.strategy_instances[strategy_name]
                if instance.status == StrategyStatus.PAUSED:
                    instance.status = StrategyStatus.ACTIVE
                    logger.info(f"▶️ Стратегия {strategy_name} возобновлена")
                    await self._emit_event("strategy_resumed", {"strategy": strategy_name})
                    return True
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка возобновления стратегии {strategy_name}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает полную статистику оркестратора"""
        try:
            uptime = datetime.now() - self.stats["start_time"] if self.stats["start_time"] else timedelta(0)
            
            # Основная статистика
            base_stats = {
                **self.stats,
                "status": self.status.value,
                "uptime_seconds": uptime.total_seconds(),
                "uptime_formatted": str(uptime).split('.')[0],
                "is_running": self.is_running,
                "strategies_total": len(self.strategy_instances),
                "strategies_active": self._count_active_strategies(),
                "success_rate": round(
                    (self.stats["successful_analyses"] / max(self.stats["total_analyses"], 1) * 100), 2
                ) if self.stats["successful_analyses"] > 0 else 0,
                "analyses_per_hour": round(
                    (self.stats["successful_analyses"] / max(uptime.total_seconds() / 3600, 0.001)), 2
                ) if uptime.total_seconds() > 0 else 0
            }
            
            # Статистика по стратегиям
            strategy_stats = {}
            for name, instance in self.strategy_instances.items():
                strategy_stats[name] = instance.to_dict()
            
            # Производительность
            performance_stats = {}
            if self.performance_history:
                recent_performance = list(self.performance_history)[-10:]
                if recent_performance:
                    performance_stats = {
                        "recent_avg_cycle_time": sum(p["cycle_duration"] for p in recent_performance) / len(recent_performance),
                        "recent_max_cycle_time": max(p["cycle_duration"] for p in recent_performance),
                        "performance_records": len(self.performance_history)
                    }
            
            return {
                **base_stats,
                "strategy_stats": strategy_stats,
                "performance_stats": performance_stats,
                "background_tasks": len([t for t in self.background_tasks if not t.done()])
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {"error": str(e)}
    
    def get_strategy_stats(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """Возвращает статистику конкретной стратегии"""
        if strategy_name in self.strategy_instances:
            return self.strategy_instances[strategy_name].to_dict()
        return None
    
    def get_health_status(self) -> Dict[str, Any]:
        """Возвращает статус здоровья системы"""
        try:
            strategy_health = {}
            overall_healthy = True
            
            for name, instance in self.strategy_instances.items():
                health_issue = self._check_strategy_health(instance)
                is_healthy = health_issue is None
                
                strategy_health[name] = {
                    "healthy": is_healthy,
                    "status": instance.status.value,
                    "issue": health_issue,
                    "error_rate": (instance.error_count / max(instance.total_analyses, 1)) * 100,
                    "last_analysis": instance.last_analysis_at.isoformat() if instance.last_analysis_at else None
                }
                
                if not is_healthy:
                    overall_healthy = False
            
            return {
                "overall_healthy": overall_healthy,
                "orchestrator_status": self.status.value,
                "active_strategies": self._count_active_strategies(),
                "total_strategies": len(self.strategy_instances),
                "strategy_health": strategy_health,
                "last_analysis_cycle": self.stats["last_analysis_time"].isoformat() if self.stats["last_analysis_time"] else None,
                "average_cycle_time": self.stats["average_cycle_time"]
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса здоровья: {e}")
            return {"error": str(e), "overall_healthy": False}
    
    def __str__(self):
        """Строковое представление оркестратора"""
        active_count = self._count_active_strategies()
        total_count = len(self.strategy_instances)
        
        return (f"StrategyOrchestrator(status={self.status.value}, "
                f"strategies={active_count}/{total_count}, "
                f"cycles={self.stats['analysis_cycles']}, "
                f"signals={self.stats['signals_generated']})")
    
    def __repr__(self):
        """Подробное представление для отладки"""
        return (f"StrategyOrchestrator(status={self.status.value}, "
                f"interval={self.analysis_interval}s, "
                f"max_concurrent={self.max_concurrent_analyses}, "
                f"monitoring={self.enable_performance_monitoring})")


# ==================== EXPORTS ====================

__all__ = [
    "StrategyOrchestrator",
    "StrategyInstance",
    "OrchestratorStatus",
    "StrategyStatus"
]

logger.info("✅ Simplified StrategyOrchestrator v2.0 loaded - Direct Repository Access")
