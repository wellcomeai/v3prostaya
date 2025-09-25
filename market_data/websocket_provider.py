import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from collections import deque
from pybit.unified_trading import WebSocket
from config import Config

logger = logging.getLogger(__name__)


class RealtimeMarketData:
    """Класс для хранения и обработки рыночных данных в реальном времени"""
    
    def __init__(self, max_history: int = 1000):
        """
        Инициализация хранилища данных
        
        Args:
            max_history: Максимальное количество записей в истории
        """
        self.prices = deque(maxlen=max_history)
        self.volumes = deque(maxlen=max_history)
        self.timestamps = deque(maxlen=max_history)
        self.current_ticker = {}
        self.current_orderbook = {}
        self.recent_trades = deque(maxlen=100)
        
    def update_ticker(self, ticker_data: dict):
        """Обновляет данные тикера"""
        try:
            self.current_ticker = ticker_data
            price = float(ticker_data.get('lastPrice', 0))
            volume = float(ticker_data.get('volume24h', 0))
            timestamp = datetime.now()
            
            self.prices.append(price)
            self.volumes.append(volume)  
            self.timestamps.append(timestamp)
            
            logger.debug(f"📊 Ticker updated: ${price:,.2f}, Vol: {volume:,.0f}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления тикера: {e}")
            
    def update_orderbook(self, orderbook_data: dict):
        """Обновляет данные стакана"""
        try:
            self.current_orderbook = orderbook_data
            logger.debug("📋 Orderbook updated")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления ордербука: {e}")
    
    def update_trades(self, trades_data: list):
        """Обновляет данные последних сделок"""
        try:
            for trade in trades_data:
                self.recent_trades.append({
                    'price': float(trade.get('price', 0)),
                    'qty': float(trade.get('size', 0)),
                    'side': trade.get('side', ''),
                    'time': trade.get('time', ''),
                    'timestamp': datetime.now()
                })
            logger.debug(f"💰 Updated {len(trades_data)} trades")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления трейдов: {e}")
    
    def get_price_change(self, minutes: int) -> float:
        """
        Возвращает изменение цены за N минут в %
        
        Args:
            minutes: Количество минут для анализа
            
        Returns:
            Изменение цены в процентах
        """
        if len(self.prices) < 2 or len(self.timestamps) < 2:
            return 0.0
            
        current_price = self.prices[-1]
        target_time = datetime.now() - timedelta(minutes=minutes)
        
        # Ищем ближайшую цену к нужному времени
        for i, ts in enumerate(reversed(self.timestamps)):
            if ts <= target_time:
                old_price = self.prices[-(i+1)]
                if old_price > 0:
                    return (current_price - old_price) / old_price * 100
                break
                
        return 0.0
    
    def get_current_price(self) -> float:
        """Возвращает текущую цену"""
        return self.prices[-1] if self.prices else 0.0
    
    def get_volume_24h(self) -> float:
        """Возвращает текущий объем за 24ч"""
        return float(self.current_ticker.get('volume24h', 0))
    
    def get_price_change_24h(self) -> float:
        """Возвращает изменение цены за 24ч в %"""
        return float(self.current_ticker.get('price24hPcnt', 0)) * 100
        
    def get_volume_analysis(self) -> Dict[str, Any]:
        """Возвращает анализ объемов торгов"""
        try:
            if not self.recent_trades:
                return {"buy_volume": 0, "sell_volume": 0, "buy_sell_ratio": 0}
                
            buy_volume = sum(trade['qty'] for trade in self.recent_trades if trade['side'] == 'Buy')
            sell_volume = sum(trade['qty'] for trade in self.recent_trades if trade['side'] == 'Sell')
            
            total_volume = buy_volume + sell_volume
            buy_sell_ratio = buy_volume / total_volume if total_volume > 0 else 0
            
            return {
                "buy_volume": buy_volume,
                "sell_volume": sell_volume, 
                "buy_sell_ratio": buy_sell_ratio,
                "total_trades": len(self.recent_trades)
            }
        except Exception as e:
            logger.error(f"❌ Ошибка анализа объемов: {e}")
            return {"buy_volume": 0, "sell_volume": 0, "buy_sell_ratio": 0}
    
    def get_orderbook_pressure(self) -> Dict[str, Any]:
        """Анализирует давление в ордербуке"""
        try:
            orderbook = self.current_orderbook
            if not orderbook.get('b') or not orderbook.get('a'):
                return {"bid_pressure": 0, "ask_pressure": 0, "pressure_ratio": 0}
                
            # Берем первые 10 уровней
            bids = orderbook['b'][:10] if len(orderbook['b']) >= 10 else orderbook['b']
            asks = orderbook['a'][:10] if len(orderbook['a']) >= 10 else orderbook['a']
            
            bid_volume = sum(float(bid[1]) for bid in bids)
            ask_volume = sum(float(ask[1]) for ask in asks)
            
            total_volume = bid_volume + ask_volume
            pressure_ratio = bid_volume / total_volume if total_volume > 0 else 0.5
            
            return {
                "bid_pressure": bid_volume,
                "ask_pressure": ask_volume,
                "pressure_ratio": pressure_ratio,
                "total_orderbook_volume": total_volume
            }
        except Exception as e:
            logger.error(f"❌ Ошибка анализа ордербука: {e}")
            return {"bid_pressure": 0, "ask_pressure": 0, "pressure_ratio": 0}
    
    def has_sufficient_data(self, min_data_points: int = 10) -> bool:
        """Проверяет, достаточно ли данных для анализа"""
        return len(self.prices) >= min_data_points


class WebSocketProvider:
    """Провайдер WebSocket данных от Bybit"""
    
    def __init__(self, symbol: str = None, testnet: bool = None):
        """
        Инициализация WebSocket провайдера
        
        Args:
            symbol: Торговый символ (по умолчанию из Config)
            testnet: Использовать testnet (по умолчанию из Config)
        """
        self.symbol = symbol or Config.SYMBOL
        self.testnet = testnet if testnet is not None else Config.BYBIT_TESTNET
        self.market_data = RealtimeMarketData()
        self.ws = None
        self.running = False
        
        # Callback функции для уведомления подписчиков
        self.ticker_callbacks: List[Callable] = []
        self.orderbook_callbacks: List[Callable] = []
        self.trades_callbacks: List[Callable] = []
        
    def add_ticker_callback(self, callback: Callable[[dict], None]):
        """Добавляет callback для обновлений тикера"""
        self.ticker_callbacks.append(callback)
        
    def add_orderbook_callback(self, callback: Callable[[dict], None]):
        """Добавляет callback для обновлений ордербука"""
        self.orderbook_callbacks.append(callback)
        
    def add_trades_callback(self, callback: Callable[[list], None]):
        """Добавляет callback для обновлений трейдов"""
        self.trades_callbacks.append(callback)
    
    async def start(self):
        """Запускает WebSocket подключения"""
        try:
            logger.info(f"🚀 Запуск WebSocket провайдера для {self.symbol}...")
            
            # Создаем WebSocket для linear (USDT перпетуалы)
            self.ws = WebSocket(
                testnet=self.testnet,
                channel_type="linear"
            )
            
            # Подписываемся на нужные потоки
            self.ws.ticker_stream(self.symbol, self._handle_ticker)
            self.ws.orderbook_stream(50, self.symbol, self._handle_orderbook)
            self.ws.trade_stream(self.symbol, self._handle_trades)
            
            self.running = True
            logger.info(f"✅ WebSocket провайдер запущен для {self.symbol}")
            
        except Exception as e:
            logger.error(f"💥 Ошибка запуска WebSocket провайдера: {e}")
            self.running = False
            raise
    
    def _handle_ticker(self, message: dict):
        """Внутренний обработчик обновлений тикера"""
        try:
            if message.get('type') == 'snapshot' and message.get('data'):
                data = message['data']
                self.market_data.update_ticker(data)
                
                # Уведомляем всех подписчиков
                for callback in self.ticker_callbacks:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.error(f"❌ Ошибка в ticker callback: {e}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки тикера: {e}")
    
    def _handle_orderbook(self, message: dict):
        """Внутренний обработчик обновлений ордербука"""
        try:
            if message.get('type') == 'snapshot' and message.get('data'):
                data = message['data']
                self.market_data.update_orderbook(data)
                
                # Уведомляем всех подписчиков
                for callback in self.orderbook_callbacks:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.error(f"❌ Ошибка в orderbook callback: {e}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки ордербука: {e}")
    
    def _handle_trades(self, message: dict):
        """Внутренний обработчик обновлений сделок"""
        try:
            if message.get('type') == 'snapshot' and message.get('data'):
                trades = message['data']
                self.market_data.update_trades(trades)
                
                # Уведомляем всех подписчиков
                for callback in self.trades_callbacks:
                    try:
                        callback(trades)
                    except Exception as e:
                        logger.error(f"❌ Ошибка в trades callback: {e}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки трейдов: {e}")
    
    def get_market_data(self) -> RealtimeMarketData:
        """Возвращает объект с рыночными данными"""
        return self.market_data
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Возвращает текущую статистику рынка"""
        return {
            "symbol": self.symbol,
            "current_price": self.market_data.get_current_price(),
            "price_change_1m": self.market_data.get_price_change(1),
            "price_change_5m": self.market_data.get_price_change(5),
            "price_change_24h": self.market_data.get_price_change_24h(),
            "volume_24h": self.market_data.get_volume_24h(),
            "volume_analysis": self.market_data.get_volume_analysis(),
            "orderbook_pressure": self.market_data.get_orderbook_pressure(),
            "data_points": len(self.market_data.prices),
            "has_sufficient_data": self.market_data.has_sufficient_data(),
            "last_update": datetime.now().isoformat()
        }
    
    def is_running(self) -> bool:
        """Проверяет, работает ли провайдер"""
        return self.running
    
    async def stop(self):
        """Останавливает WebSocket подключения"""
        try:
            self.running = False
            if self.ws:
                self.ws.exit()
            logger.info(f"🛑 WebSocket провайдер остановлен для {self.symbol}")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки WebSocket провайдера: {e}")
    
    async def wait_for_data(self, timeout: int = 30) -> bool:
        """
        Ожидает получения достаточного количества данных
        
        Args:
            timeout: Таймаут ожидания в секундах
            
        Returns:
            True если данные получены, False если таймаут
        """
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < timeout:
            if self.market_data.has_sufficient_data():
                return True
            await asyncio.sleep(1)
            
        return False
    
    def __str__(self):
        """Строковое представление провайдера"""
        status = "Running" if self.running else "Stopped"
        return f"WebSocketProvider(symbol={self.symbol}, testnet={self.testnet}, status={status})"
