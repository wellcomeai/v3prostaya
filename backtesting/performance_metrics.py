# backtesting/performance_metrics.py

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Расчет метрик производительности стратегии"""
    
    @staticmethod
    def calculate(trades: List, equity_curve: List[Dict], 
                  initial_capital: float) -> Dict[str, Any]:
        """
        Вычисляет все метрики производительности
        
        Returns:
            Dict с метриками: win_rate, profit_factor, max_drawdown, etc
        """
        if not trades:
            return PerformanceMetrics._empty_metrics()
        
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]
        
        total_wins = sum(t.pnl for t in winning_trades)
        total_losses = abs(sum(t.pnl for t in losing_trades))
        
        profit_factor = (total_wins / total_losses) if total_losses > 0 else float('inf')
        
        max_drawdown = PerformanceMetrics._calculate_max_drawdown(equity_curve)
        
        return {
            "win_rate": (len(winning_trades) / len(trades)) * 100 if trades else 0,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "avg_win": (total_wins / len(winning_trades)) if winning_trades else 0,
            "avg_loss": (total_losses / len(losing_trades)) if losing_trades else 0,
            "largest_win": max((t.pnl for t in winning_trades), default=0),
            "largest_loss": min((t.pnl for t in losing_trades), default=0),
            "total_pnl": total_wins - total_losses
        }
    
    @staticmethod
    def _calculate_max_drawdown(equity_curve: List[Dict]) -> float:
        """Вычисляет максимальную просадку"""
        if not equity_curve:
            return 0.0
        
        peak = equity_curve[0]["equity"]
        max_dd = 0.0
        
        for point in equity_curve:
            equity = point["equity"]
            if equity > peak:
                peak = equity
            drawdown = ((peak - equity) / peak) * 100
            max_dd = max(max_dd, drawdown)
        
        return max_dd
    
    @staticmethod
    def _empty_metrics() -> Dict[str, Any]:
        """Метрики для пустого результата"""
        return {
            "win_rate": 0,
            "profit_factor": 0,
            "max_drawdown": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "largest_win": 0,
            "largest_loss": 0,
            "total_pnl": 0
        }
