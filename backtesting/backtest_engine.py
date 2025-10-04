# backtesting/backtest_engine.py

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Одна сделка в бэктесте"""
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    side: str = "BUY"  # BUY или SELL
    quantity: float = 1.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    is_open: bool = True
    signal_strength: float = 0.0
    signal_reasons: List[str] = field(default_factory=list)


@dataclass
class BacktestResult:
    """Результат бэктестинга"""
    trades: List[Trade]
    initial_capital: float
    final_capital: float
    total_pnl: float
    total_pnl_percent: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    equity_curve: List[Dict[str, Any]]
    candles_data: List[Dict[str, Any]]
    start_time: datetime
    end_time: datetime
    duration_days: int


class BacktestEngine:
    """
    Движок бэктестинга
    
    Симулирует торговлю по историческим данным:
    1. Загружает свечи из БД
    2. Генерирует сигналы через стратегию
    3. Симулирует вход/выход по сигналам
    4. Считает PnL и метрики
    """
    
    def __init__(self, initial_capital: float = 10000.0, 
                 commission_rate: float = 0.001,
                 position_size_pct: float = 0.95):
        """
        Args:
            initial_capital: Начальный капитал ($)
            commission_rate: Комиссия биржи (0.1% = 0.001)
            position_size_pct: Размер позиции от капитала (95% = 0.95)
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.position_size_pct = position_size_pct
        
        self.current_capital = initial_capital
        self.trades: List[Trade] = []
        self.current_trade: Optional[Trade] = None
        self.equity_curve: List[Dict[str, Any]] = []
        
        logger.info(f"🎯 BacktestEngine создан: капитал=${initial_capital:,.2f}, комиссия={commission_rate*100}%")
    
    async def run_backtest(self, candles: List[Dict[str, Any]], 
                          strategy, symbol: str) -> BacktestResult:
        """
        Запускает бэктестинг на исторических данных
        
        Args:
            candles: Список свечей из БД
            strategy: Экземпляр стратегии (BaseStrategy)
            symbol: Торговый символ
            
        Returns:
            BacktestResult с результатами
        """
        logger.info(f"🚀 Запуск бэктеста на {len(candles)} свечах для {symbol}")
        
        self._reset()
        
        for i, candle in enumerate(candles):
            # Создаем snapshot для стратегии
            snapshot = self._candle_to_snapshot(candle, candles, i)
            
            # Генерируем сигнал через стратегию
            signal = await strategy.analyze_market_data(snapshot)
            
            # Обрабатываем сигнал
            if signal and signal.strength >= strategy.min_signal_strength:
                await self._process_signal(signal, candle)
            
            # Записываем equity
            self.equity_curve.append({
                "timestamp": candle["open_time"],
                "equity": self.current_capital,
                "price": candle["close"]
            })
            
            if (i + 1) % 1000 == 0:
                logger.info(f"📊 Обработано {i+1}/{len(candles)} свечей")
        
        # Закрываем открытую позицию если есть
        if self.current_trade and self.current_trade.is_open:
            last_candle = candles[-1]
            self._close_trade(last_candle["close"], last_candle["open_time"])
        
        # Формируем результат
        result = self._generate_result(candles, symbol)
        
        logger.info(f"✅ Бэктест завершен: {result.total_trades} сделок, PnL: {result.total_pnl_percent:+.2f}%")
        
        return result
    
    def _candle_to_snapshot(self, candle: Dict, all_candles: List[Dict], index: int):
        """Преобразует свечу в MarketDataSnapshot для стратегии"""
        from market_data import MarketDataSnapshot, DataSourceType
        
        # Вычисляем изменения цены
        price_change_1m = 0.0
        price_change_5m = 0.0
        
        if index > 0:
            prev_candle = all_candles[index - 1]
            price_change_1m = ((candle["close"] - prev_candle["close"]) / prev_candle["close"]) * 100
        
        if index >= 5:
            candle_5m_ago = all_candles[index - 5]
            price_change_5m = ((candle["close"] - candle_5m_ago["close"]) / candle_5m_ago["close"]) * 100
        
        return MarketDataSnapshot(
            symbol=candle["symbol"],
            timestamp=datetime.fromisoformat(candle["open_time"]),
            current_price=candle["close"],
            price_change_1m=price_change_1m,
            price_change_5m=price_change_5m,
            price_change_24h=0.0,  # Не используется в бэктесте
            volume_24h=candle["volume"],
            high_24h=candle["high"],
            low_24h=candle["low"],
            bid_price=candle["close"],
            ask_price=candle["close"],
            spread=0.0,
            open_interest=0.0,
            data_source=DataSourceType.REST_API,
            has_realtime_data=False,
            has_historical_data=True
        )
    
    async def _process_signal(self, signal, candle: Dict):
        """Обрабатывает торговый сигнал"""
        from strategies import SignalType
        
        current_price = candle["close"]
        timestamp = datetime.fromisoformat(candle["open_time"])
        
        # Если есть открытая позиция - закрываем
        if self.current_trade and self.current_trade.is_open:
            self._close_trade(current_price, timestamp)
        
        # Открываем новую позицию
        if signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]:
            self._open_trade("BUY", current_price, timestamp, signal)
        elif signal.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]:
            self._open_trade("SELL", current_price, timestamp, signal)
    
    def _open_trade(self, side: str, price: float, timestamp: datetime, signal):
        """Открывает сделку"""
        position_value = self.current_capital * self.position_size_pct
        commission = position_value * self.commission_rate
        quantity = (position_value - commission) / price
        
        self.current_trade = Trade(
            entry_time=timestamp,
            entry_price=price,
            side=side,
            quantity=quantity,
            signal_strength=signal.strength,
            signal_reasons=signal.reasons.copy()
        )
        
        self.current_capital -= commission
        
        logger.debug(f"📈 Открыта {side} позиция: ${price:,.2f}, кол-во: {quantity:.6f}")
    
    def _close_trade(self, price: float, timestamp: datetime):
        """Закрывает сделку"""
        if not self.current_trade:
            return
        
        trade = self.current_trade
        
        # Рассчитываем PnL
        if trade.side == "BUY":
            pnl = (price - trade.entry_price) * trade.quantity
        else:  # SELL
            pnl = (trade.entry_price - price) * trade.quantity
        
        commission = price * trade.quantity * self.commission_rate
        pnl -= commission
        
        trade.exit_time = timestamp
        trade.exit_price = price
        trade.pnl = pnl
        trade.pnl_percent = (pnl / (trade.entry_price * trade.quantity)) * 100
        trade.is_open = False
        
        self.current_capital += pnl
        self.trades.append(trade)
        self.current_trade = None
        
        logger.debug(f"📉 Закрыта позиция: PnL={pnl:+.2f} ({trade.pnl_percent:+.2f}%)")
    
    def _generate_result(self, candles: List[Dict], symbol: str) -> BacktestResult:
        """Генерирует финальный результат бэктеста"""
        from .performance_metrics import PerformanceMetrics
        
        metrics = PerformanceMetrics.calculate(
            trades=self.trades,
            equity_curve=self.equity_curve,
            initial_capital=self.initial_capital
        )
        
        return BacktestResult(
            trades=self.trades,
            initial_capital=self.initial_capital,
            final_capital=self.current_capital,
            total_pnl=self.current_capital - self.initial_capital,
            total_pnl_percent=((self.current_capital - self.initial_capital) / self.initial_capital) * 100,
            win_rate=metrics["win_rate"],
            profit_factor=metrics["profit_factor"],
            max_drawdown=metrics["max_drawdown"],
            total_trades=len(self.trades),
            winning_trades=metrics["winning_trades"],
            losing_trades=metrics["losing_trades"],
            avg_win=metrics["avg_win"],
            avg_loss=metrics["avg_loss"],
            largest_win=metrics["largest_win"],
            largest_loss=metrics["largest_loss"],
            equity_curve=self.equity_curve,
            candles_data=candles,
            start_time=datetime.fromisoformat(candles[0]["open_time"]),
            end_time=datetime.fromisoformat(candles[-1]["open_time"]),
            duration_days=(datetime.fromisoformat(candles[-1]["open_time"]) - 
                          datetime.fromisoformat(candles[0]["open_time"])).days
        )
    
    def _reset(self):
        """Сброс состояния перед новым бэктестом"""
        self.current_capital = self.initial_capital
        self.trades = []
        self.current_trade = None
        self.equity_curve = []
