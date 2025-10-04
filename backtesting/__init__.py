"""
Backtesting Module - Модуль для бэктестирования торговых стратегий

Предоставляет инструменты для:
- Запуска бэктестов на исторических данных
- Расчета метрик производительности
- Генерации отчетов в HTML формате
"""

from .backtest_engine import BacktestEngine, BacktestResult
from .performance_metrics import PerformanceMetrics
from .report_generator import ReportGenerator

__all__ = [
    "BacktestEngine",
    "BacktestResult", 
    "PerformanceMetrics",
    "ReportGenerator"
]
