import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from collections import deque
from pybit.unified_trading import WebSocket
from config import Config
import traceback
import json

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
        
        # Статистика обновлений
        self.stats = {
            "ticker_updates": 0,
            "orderbook_updates": 0,
            "trades_updates": 0,
            "last_ticker_update": None,
            "last_orderbook_update": None,
            "last_trades_update": None
        }
        
        # Отслеживание времени для периодического логирования
        self.last_summary_log = None
        
        logger.debug(f"📊 RealtimeMarketData инициализирован (max_history={max_history})")
        
    def update_ticker(self, ticker_data: dict):
        """Обновляет данные тикера"""
        try:
            logger.debug(f"🔄 Обновление тикера: {json.dumps(ticker_data, indent=2)}")
            
            self.current_ticker = ticker_data
            self.stats["ticker_updates"] += 1
            self.stats["last_ticker_update"] = datetime.now()
            
            price = float(ticker_data.get('lastPrice', 0))
            volume = float(ticker_data.get('volume24h', 0))
            timestamp = datetime.now()
            
            if price > 0:  # Валидная цена
                self.prices.append(price)
                self.volumes.append(volume)  
                self.timestamps.append(timestamp)
                
                # Периодическое логирование раз в минуту
                if self.last_summary_log is None or (datetime.now() - self.last_summary_log).total_seconds() > 60:
                    logger.info(f"📊 Ticker обновлен: ${price:,.2f}, Vol: {volume:,.0f}, Updates: {self.stats['ticker_updates']}")
                    self.last_summary_log = datetime.now()
                else:
                    logger.debug(f"📊 Ticker обновлен: ${price:,.2f}, Vol: {volume:,.0f}, Updates: {self.stats['ticker_updates']}")
            else:
                logger.warning(f"⚠️ Получена невалидная цена: {price}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления тикера: {e}")
            logger.error(f"Raw ticker data: {ticker_data}")
            
    def update_orderbook(self, orderbook_data: dict):
        """Обновляет данные стакана"""
        try:
            logger.debug(f"📋 Обновление ордербука: bids={len(orderbook_data.get('b', []))}, asks={len(orderbook_data.get('a', []))}")
            
            self.current_orderbook = orderbook_data
            self.stats["orderbook_updates"] += 1
            self.stats["last_orderbook_update"] = datetime.now()
            
            logger.debug(f"📋 Orderbook обновлен, updates: {self.stats['orderbook_updates']}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления ордербука: {e}")
            logger.error(f"Raw orderbook data: {orderbook_data}")
    
    def update_trades(self, trades_data: list):
        """Обновляет данные последних сделок"""
        try:
            logger.debug(f"💰 Обновление трейдов: {len(trades_data)} сделок")
            
            for trade in trades_data:
                self.recent_trades.append({
                    'price': float(trade.get('price', 0)),
                    'qty': float(trade.get('size', 0)),
                    'side': trade.get('side', ''),
                    'time': trade.get('time', ''),
                    'timestamp': datetime.now()
                })
                
            self.stats["trades_updates"] += 1
            self.stats["last_trades_update"] = datetime.now()
            
            logger.debug(f"💰 Trades обновлены: {len(trades_data)} сделок, Total updates: {self.stats['trades_updates']}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления трейдов: {e}")
            logger.error(f"Raw trades data: {trades_data}")
    
    def get_price_change(self, minutes: int) -> float:
        """
        Возвращает изменение цены за N минут в %
        
        Args:
            minutes: Количество минут для анализа
            
        Returns:
            Изменение цены в процентах
        """
        if len(self.prices) < 2 or len(self.timestamps) < 2:
            logger.debug(f"🔍 Недостаточно данных для расчета изменения за {minutes}м: prices={len(self.prices)}, timestamps={len(self.timestamps)}")
            return 0.0
            
        current_price = self.prices[-1]
        target_time = datetime.now() - timedelta(minutes=minutes)
        
        # Ищем ближайшую цену к нужному времени
        for i, ts in enumerate(reversed(self.timestamps)):
            if ts <= target_time:
                old_price = self.prices[-(i+1)]
                if old_price > 0:
                    change = (current_price - old_price) / old_price * 100
                    logger.debug(f"📈 Изменение за {minutes}м: {change:+.2f}% (${old_price:,.2f} → ${current_price:,.2f})")
                    return change
                break
                
        logger.debug(f"🔍 Не найдена цена для времени {minutes}м назад")
        return 0.0
    
    def get_current_price(self) -> float:
        """Возвращает текущую цену"""
        price = self.prices[-1] if self.prices else 0.0
        logger.debug(f"💰 Текущая цена: ${price:,.2f}")
        return price
    
    def get_volume_24h(self) -> float:
        """Возвращает текущий объем за 24ч"""
        volume = float(self.current_ticker.get('volume24h', 0))
        logger.debug(f"📦 Объем 24ч: {volume:,.0f}")
        return volume
    
    def get_price_change_24h(self) -> float:
        """Возвращает изменение цены за 24ч в %"""
        change = float(self.current_ticker.get('price24hPcnt', 0)) * 100
        logger.debug(f"📊 Изменение 24ч: {change:+.2f}%")
        return change
        
    def get_volume_analysis(self) -> Dict[str, Any]:
        """Возвращает анализ объемов торгов"""
        try:
            if not self.recent_trades:
                logger.debug("📊 Нет трейдов для анализа объемов")
                return {"buy_volume": 0, "sell_volume": 0, "buy_sell_ratio": 0}
                
            buy_volume = sum(trade['qty'] for trade in self.recent_trades if trade['side'] == 'Buy')
            sell_volume = sum(trade['qty'] for trade in self.recent_trades if trade['side'] == 'Sell')
            
            total_volume = buy_volume + sell_volume
            buy_sell_ratio = buy_volume / total_volume if total_volume > 0 else 0
            
            analysis = {
                "buy_volume": buy_volume,
                "sell_volume": sell_volume, 
                "buy_sell_ratio": buy_sell_ratio,
                "total_trades": len(self.recent_trades)
            }
            
            logger.debug(f"📊 Анализ объемов: B={buy_volume:.0f}, S={sell_volume:.0f}, Ratio={buy_sell_ratio:.2f}")
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа объемов: {e}")
            return {"buy_volume": 0, "sell_volume": 0, "buy_sell_ratio": 0}
    
    def get_orderbook_pressure(self) -> Dict[str, Any]:
        """Анализирует давление в ордербуке"""
        try:
            orderbook = self.current_orderbook
            if not orderbook.get('b') or not orderbook.get('a'):
                logger.debug("📋 Нет данных ордербука для анализа давления")
                return {"bid_pressure": 0, "ask_pressure": 0, "pressure_ratio": 0}
                
            # Берем первые 10 уровней
            bids = orderbook['b'][:10] if len(orderbook['b']) >= 10 else orderbook['b']
            asks = orderbook['a'][:10] if len(orderbook['a']) >= 10 else orderbook['a']
            
            bid_volume = sum(float(bid[1]) for bid in bids)
            ask_volume = sum(float(ask[1]) for ask in asks)
            
            total_volume = bid_volume + ask_volume
            pressure_ratio = bid_volume / total_volume if total_volume > 0 else 0.5
            
            pressure = {
                "bid_pressure": bid_volume,
                "ask_pressure": ask_volume,
                "pressure_ratio": pressure_ratio,
                "total_orderbook_volume": total_volume
            }
            
            logger.debug(f"📋 Давление ордербука: Bids={bid_volume:.0f}, Asks={ask_volume:.0f}, Ratio={pressure_ratio:.2f}")
            return pressure
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа ордербука: {e}")
            return {"bid_pressure": 0, "ask_pressure": 0, "pressure_ratio": 0}
    
    def has_sufficient_data(self, min_data_points: int = 10) -> bool:
        """Проверяет, достаточно ли данных для анализа"""
        sufficient = len(self.prices) >= min_data_points
        logger.debug(f"🔍 Достаточно данных: {sufficient} (есть {len(self.prices)}, нужно {min_data_points})")
        return sufficient
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику обновлений"""
        return {
            **self.stats,
            "data_points": len(self.prices),
            "volume_points": len(self.volumes),
            "timestamp_points": len(self.timestamps),
            "recent_trades_count": len(self.recent_trades),
            "has_ticker_data": bool(self.current_ticker),
            "has_orderbook_data": bool(self.current_orderbook)
        }


class WebSocketProvider:
    """
    🆕 Провайдер WebSocket данных от Bybit с поддержкой МНОЖЕСТВЕННЫХ СИМВОЛОВ
    
    Поддерживает подписку на несколько символов одновременно в одном WebSocket соединении.
    Все 15 криптопар будут получать данные и сохраняться в БД.
    """
    
    def __init__(self, symbols: List[str] = None, testnet: bool = None):
        """
        Инициализация WebSocket провайдера
        
        Args:
            symbols: Список торговых символов (по умолчанию из Config)
            testnet: Использовать testnet (по умолчанию из Config)
        """
        # 🆕 ИЗМЕНЕНО: Поддержка множественных символов
        if symbols is None:
            symbols = [Config.SYMBOL]
        elif isinstance(symbols, str):
            symbols = [symbols]
        
        self.symbols = [s.upper() for s in symbols]
        self.testnet = testnet if testnet is not None else Config.BYBIT_TESTNET
        
        # Данные для каждого символа
        self.market_data_by_symbol: Dict[str, RealtimeMarketData] = {}
        for symbol in self.symbols:
            self.market_data_by_symbol[symbol] = RealtimeMarketData()
        
        self.ws = None
        self.running = False
        
        # Callback функции для уведомления подписчиков
        # 🆕 ИЗМЕНЕНО: Callbacks теперь принимают (symbol: str, data: dict/list)
        self.ticker_callbacks: List[Callable[[str, dict], None]] = []
        self.orderbook_callbacks: List[Callable[[str, dict], None]] = []
        self.trades_callbacks: List[Callable[[str, list], None]] = []
        
        # Время последнего summary лога
        self.last_summary_log = None
        
        # Статистика подключения
        self.connection_stats = {
            "connection_attempts": 0,
            "successful_connections": 0,
            "connection_failures": 0,
            "messages_received": 0,
            "ticker_messages": 0,
            "ticker_messages_by_symbol": {s: 0 for s in self.symbols},  # 🆕 По каждому символу
            "orderbook_messages": 0,
            "orderbook_messages_by_symbol": {s: 0 for s in self.symbols},  # 🆕
            "trades_messages": 0,
            "trades_messages_by_symbol": {s: 0 for s in self.symbols},  # 🆕
            "unknown_messages": 0,
            "error_messages": 0,
            "last_message_time": None,
            "start_time": None
        }
        
        logger.info(f"🔌 WebSocketProvider инициализирован для {len(self.symbols)} символов: {', '.join(self.symbols)}")
    
    def add_ticker_callback(self, callback: Callable[[str, dict], None]):
        """
        Добавляет callback для обновлений тикера
        
        Args:
            callback: Функция с сигнатурой callback(symbol: str, ticker_data: dict)
        """
        self.ticker_callbacks.append(callback)
        logger.info(f"📝 Добавлен ticker callback ({len(self.ticker_callbacks)} всего)")
        
    def add_orderbook_callback(self, callback: Callable[[str, dict], None]):
        """
        Добавляет callback для обновлений ордербука
        
        Args:
            callback: Функция с сигнатурой callback(symbol: str, orderbook_data: dict)
        """
        self.orderbook_callbacks.append(callback)
        logger.info(f"📝 Добавлен orderbook callback ({len(self.orderbook_callbacks)} всего)")
        
    def add_trades_callback(self, callback: Callable[[str, list], None]):
        """
        Добавляет callback для обновлений трейдов
        
        Args:
            callback: Функция с сигнатурой callback(symbol: str, trades_data: list)
        """
        self.trades_callbacks.append(callback)
        logger.info(f"📝 Добавлен trades callback ({len(self.trades_callbacks)} всего)")
    
    async def start(self):
        """Запускает WebSocket подключения для ВСЕХ символов"""
        try:
            self.connection_stats["connection_attempts"] += 1
            self.connection_stats["start_time"] = datetime.now()
            
            logger.info(f"🚀 Запуск WebSocket провайдера для {len(self.symbols)} символов...")
            logger.info(f"🔧 Настройки: testnet={self.testnet}, symbols={', '.join(self.symbols)}")
            
            # Создаем WebSocket для linear (USDT перпетуалы)
            logger.info("🔗 Создание WebSocket соединения...")
            self.ws = WebSocket(
                testnet=self.testnet,
                channel_type="linear"
            )
            
            logger.info("📡 Подписка на потоки данных для всех символов...")
            
            # 🆕 ИЗМЕНЕНО: Подписываемся на каждый символ
            for symbol in self.symbols:
                logger.info(f"📊 Подписка на ticker stream: {symbol}")
                self.ws.ticker_stream(symbol, self._handle_ticker)
                
                logger.info(f"📋 Подписка на orderbook stream: {symbol} (50 levels)")
                self.ws.orderbook_stream(50, symbol, self._handle_orderbook)
                
                logger.info(f"💰 Подписка на trade stream: {symbol}")
                self.ws.trade_stream(symbol, self._handle_trades)
            
            self.running = True
            self.connection_stats["successful_connections"] += 1
            
            logger.info(f"✅ WebSocket провайдер запущен для {len(self.symbols)} символов")
            logger.info(f"📞 Registered callbacks: ticker={len(self.ticker_callbacks)}, orderbook={len(self.orderbook_callbacks)}, trades={len(self.trades_callbacks)}")
            
        except Exception as e:
            self.connection_stats["connection_failures"] += 1
            logger.error(f"💥 Ошибка запуска WebSocket провайдера: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            self.running = False
            raise
    
    def _handle_ticker(self, message: dict):
        """Внутренний обработчик обновлений тикера для МНОЖЕСТВЕННЫХ СИМВОЛОВ"""
        try:
            self.connection_stats["messages_received"] += 1
            self.connection_stats["last_message_time"] = datetime.now()
            
            logger.debug(f"📨 Получено ticker сообщение: {json.dumps(message, indent=2)}")
            
            msg_type = message.get('type')
            logger.debug(f"📊 Ticker message type: {msg_type}")
            
            if msg_type == 'snapshot' and message.get('data'):
                self.connection_stats["ticker_messages"] += 1
                data = message['data']
                
                # 🆕 ИЗМЕНЕНО: Извлекаем символ из данных
                symbol = data.get('symbol', '').upper()
                
                if not symbol:
                    logger.warning(f"⚠️ Ticker без символа: {data}")
                    return
                
                if symbol not in self.symbols:
                    logger.debug(f"🔍 Игнорируем символ {symbol} (не в подписке)")
                    return
                
                # Обновляем статистику по символу
                self.connection_stats["ticker_messages_by_symbol"][symbol] += 1
                
                # Периодическое логирование раз в минуту
                if self.last_summary_log is None or (datetime.now() - self.last_summary_log).total_seconds() > 60:
                    total_msgs = sum(self.connection_stats["ticker_messages_by_symbol"].values())
                    logger.info(f"📊 WebSocket активен: {total_msgs} ticker updates для {len(self.symbols)} символов")
                    for sym in self.symbols:
                        count = self.connection_stats["ticker_messages_by_symbol"][sym]
                        if count > 0:
                            market_data = self.market_data_by_symbol.get(sym)
                            price = market_data.get_current_price() if market_data else 0
                            logger.info(f"   • {sym}: {count} updates, цена: ${price:,.2f}")
                    self.last_summary_log = datetime.now()
                else:
                    logger.debug(f"📊 Ticker data для {symbol}: цена ${float(data.get('lastPrice', 0)):,.2f}")
                
                # Обновляем внутренние данные для конкретного символа
                if symbol in self.market_data_by_symbol:
                    self.market_data_by_symbol[symbol].update_ticker(data)
                
                # 🆕 ИЗМЕНЕНО: Уведомляем всех подписчиков с передачей символа
                logger.debug(f"📞 Вызов {len(self.ticker_callbacks)} ticker callbacks для {symbol}...")
                for i, callback in enumerate(self.ticker_callbacks):
                    try:
                        logger.debug(f"📞 Вызов ticker callback #{i} для {symbol}")
                        callback(symbol, data)  # 🆕 Передаем symbol + data
                        logger.debug(f"✅ Ticker callback #{i} выполнен для {symbol}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка в ticker callback #{i} для {symbol}: {e}")
                        logger.error(f"Stack trace: {traceback.format_exc()}")
                
                logger.debug(f"✅ Ticker callbacks завершены для {symbol}")
                
            elif msg_type == 'delta':
                logger.debug(f"📊 Получен ticker delta: {message}")
                # Можно обрабатывать дельта-обновления
                pass
            else:
                self.connection_stats["unknown_messages"] += 1
                logger.warning(f"⚠️ Неизвестный тип ticker сообщения: {msg_type}")
                logger.debug(f"Full message: {json.dumps(message, indent=2)}")
                
        except Exception as e:
            self.connection_stats["error_messages"] += 1
            logger.error(f"❌ Ошибка обработки ticker сообщения: {e}")
            logger.error(f"Raw message: {message}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
    
    def _handle_orderbook(self, message: dict):
        """Внутренний обработчик обновлений ордербука для МНОЖЕСТВЕННЫХ СИМВОЛОВ"""
        try:
            self.connection_stats["messages_received"] += 1
            self.connection_stats["last_message_time"] = datetime.now()
            
            logger.debug(f"📨 Получено orderbook сообщение: type={message.get('type')}")
            
            msg_type = message.get('type')
            
            if msg_type == 'snapshot' and message.get('data'):
                self.connection_stats["orderbook_messages"] += 1
                data = message['data']
                
                # 🆕 Извлекаем символ
                symbol = data.get('s', '').upper()
                
                if not symbol:
                    logger.warning(f"⚠️ Orderbook без символа")
                    return
                
                if symbol not in self.symbols:
                    logger.debug(f"🔍 Игнорируем orderbook для {symbol}")
                    return
                
                # Обновляем статистику по символу
                self.connection_stats["orderbook_messages_by_symbol"][symbol] += 1
                
                logger.debug(f"📋 Orderbook data для {symbol}: bids={len(data.get('b', []))}, asks={len(data.get('a', []))}")
                
                # Обновляем внутренние данные
                if symbol in self.market_data_by_symbol:
                    self.market_data_by_symbol[symbol].update_orderbook(data)
                
                # Уведомляем всех подписчиков
                logger.debug(f"📞 Вызов {len(self.orderbook_callbacks)} orderbook callbacks для {symbol}...")
                for i, callback in enumerate(self.orderbook_callbacks):
                    try:
                        callback(symbol, data)  # 🆕 Передаем symbol + data
                        logger.debug(f"✅ Orderbook callback #{i} выполнен для {symbol}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка в orderbook callback #{i} для {symbol}: {e}")
                
            elif msg_type == 'delta':
                logger.debug(f"📋 Получен orderbook delta")
                # Можно обрабатывать дельта-обновления
                pass
            else:
                self.connection_stats["unknown_messages"] += 1
                logger.warning(f"⚠️ Неизвестный тип orderbook сообщения: {msg_type}")
                
        except Exception as e:
            self.connection_stats["error_messages"] += 1
            logger.error(f"❌ Ошибка обработки orderbook сообщения: {e}")
            logger.error(f"Raw message: {message}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
    
    def _handle_trades(self, message: dict):
        """Внутренний обработчик обновлений сделок для МНОЖЕСТВЕННЫХ СИМВОЛОВ"""
        try:
            self.connection_stats["messages_received"] += 1
            self.connection_stats["last_message_time"] = datetime.now()
            
            logger.debug(f"📨 Получено trades сообщение: type={message.get('type')}")
            
            msg_type = message.get('type')
            
            if msg_type == 'snapshot' and message.get('data'):
                self.connection_stats["trades_messages"] += 1
                trades = message['data']
                
                if not trades or len(trades) == 0:
                    return
                
                # 🆕 Извлекаем символ из первой сделки
                symbol = trades[0].get('s', '').upper()
                
                if not symbol:
                    logger.warning(f"⚠️ Trades без символа")
                    return
                
                if symbol not in self.symbols:
                    logger.debug(f"🔍 Игнорируем trades для {symbol}")
                    return
                
                # Обновляем статистику по символу
                self.connection_stats["trades_messages_by_symbol"][symbol] += 1
                
                logger.debug(f"💰 Trades data для {symbol}: {len(trades)} сделок")
                
                # Обновляем внутренние данные
                if symbol in self.market_data_by_symbol:
                    self.market_data_by_symbol[symbol].update_trades(trades)
                
                # Уведомляем всех подписчиков
                logger.debug(f"📞 Вызов {len(self.trades_callbacks)} trades callbacks для {symbol}...")
                for i, callback in enumerate(self.trades_callbacks):
                    try:
                        callback(symbol, trades)  # 🆕 Передаем symbol + trades
                        logger.debug(f"✅ Trades callback #{i} выполнен для {symbol}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка в trades callback #{i} для {symbol}: {e}")
                
            else:
                self.connection_stats["unknown_messages"] += 1
                logger.warning(f"⚠️ Неизвестный тип trades сообщения: {msg_type}")
                
        except Exception as e:
            self.connection_stats["error_messages"] += 1
            logger.error(f"❌ Ошибка обработки trades сообщения: {e}")
            logger.error(f"Raw message: {message}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
    
    def get_market_data(self, symbol: str = None) -> RealtimeMarketData:
        """
        🆕 ИЗМЕНЕНО: Возвращает объект с рыночными данными для конкретного символа
        
        Args:
            symbol: Символ (если None, возвращает для первого символа)
            
        Returns:
            RealtimeMarketData: Объект с данными для символа
        """
        if symbol is None:
            symbol = self.symbols[0]
        
        symbol = symbol.upper()
        return self.market_data_by_symbol.get(symbol, RealtimeMarketData())
    
    def get_all_market_data(self) -> Dict[str, RealtimeMarketData]:
        """
        🆕 НОВОЕ: Возвращает данные для всех символов
        
        Returns:
            Dict[str, RealtimeMarketData]: Словарь {symbol: market_data}
        """
        return self.market_data_by_symbol
    
    def get_current_stats(self, symbol: str = None) -> Dict[str, Any]:
        """
        🆕 ИЗМЕНЕНО: Возвращает текущую статистику рынка
        
        Args:
            symbol: Символ (если None, возвращает для всех символов)
            
        Returns:
            Dict: Статистика для символа или всех символов
        """
        try:
            if symbol:
                # Статистика для одного символа
                symbol = symbol.upper()
                market_data = self.market_data_by_symbol.get(symbol)
                
                if not market_data:
                    return {"symbol": symbol, "error": "Symbol not found"}
                
                return {
                    "symbol": symbol,
                    "current_price": market_data.get_current_price(),
                    "price_change_1m": market_data.get_price_change(1),
                    "price_change_5m": market_data.get_price_change(5),
                    "price_change_24h": market_data.get_price_change_24h(),
                    "volume_24h": market_data.get_volume_24h(),
                    "volume_analysis": market_data.get_volume_analysis(),
                    "orderbook_pressure": market_data.get_orderbook_pressure(),
                    "data_points": len(market_data.prices),
                    "has_sufficient_data": market_data.has_sufficient_data(),
                    "last_update": datetime.now().isoformat(),
                    "connection_stats": {
                        "ticker_messages": self.connection_stats["ticker_messages_by_symbol"].get(symbol, 0),
                        "orderbook_messages": self.connection_stats["orderbook_messages_by_symbol"].get(symbol, 0),
                        "trades_messages": self.connection_stats["trades_messages_by_symbol"].get(symbol, 0)
                    },
                    "market_data_stats": market_data.get_stats()
                }
            else:
                # Статистика для всех символов
                stats_by_symbol = {}
                for sym in self.symbols:
                    stats_by_symbol[sym] = self.get_current_stats(sym)
                
                return {
                    "symbols": self.symbols,
                    "total_symbols": len(self.symbols),
                    "data_by_symbol": stats_by_symbol,
                    "connection_stats": self.connection_stats.copy(),
                    "last_update": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {
                "error": str(e)
            }
    
    def is_running(self) -> bool:
        """Проверяет, работает ли провайдер"""
        return self.running
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Возвращает статистику подключения"""
        uptime = None
        if self.connection_stats["start_time"]:
            uptime = (datetime.now() - self.connection_stats["start_time"]).total_seconds()
            
        return {
            **self.connection_stats,
            "symbols": self.symbols,
            "total_symbols": len(self.symbols),
            "uptime_seconds": uptime,
            "messages_per_minute": (self.connection_stats["messages_received"] / (uptime / 60)) if uptime and uptime > 0 else 0,
            "is_healthy": self.is_connection_healthy()
        }
    
    def is_connection_healthy(self) -> bool:
        """Проверяет здоровье подключения"""
        if not self.running:
            return False
            
        # Проверяем получение сообщений за последние 2 минуты
        if self.connection_stats["last_message_time"]:
            time_since_last = datetime.now() - self.connection_stats["last_message_time"]
            if time_since_last > timedelta(minutes=2):
                logger.warning(f"⚠️ Нет сообщений {time_since_last.total_seconds():.0f} секунд")
                return False
                
        return True
    
    async def stop(self):
        """Останавливает WebSocket подключения"""
        try:
            logger.info("🔄 Остановка WebSocket провайдера...")
            self.running = False
            
            if self.ws:
                self.ws.exit()
                logger.info("🔌 WebSocket соединение закрыто")
                
            # Логируем финальную статистику
            final_stats = self.get_connection_stats()
            logger.info(f"📊 Финальная статистика WebSocket:")
            logger.info(f"   • Символов: {len(self.symbols)}")
            logger.info(f"   • Попыток подключения: {final_stats['connection_attempts']}")
            logger.info(f"   • Успешных подключений: {final_stats['successful_connections']}")
            logger.info(f"   • Сообщений получено: {final_stats['messages_received']}")
            logger.info(f"   • Ticker сообщений: {final_stats['ticker_messages']}")
            logger.info(f"   • Orderbook сообщений: {final_stats['orderbook_messages']}")
            logger.info(f"   • Trades сообщений: {final_stats['trades_messages']}")
            
            # Статистика по каждому символу
            for symbol in self.symbols:
                ticker_msgs = final_stats['ticker_messages_by_symbol'].get(symbol, 0)
                market_data = self.market_data_by_symbol.get(symbol)
                data_points = len(market_data.prices) if market_data else 0
                logger.info(f"   • {symbol}: {ticker_msgs} ticker msgs, {data_points} data points")
            
            logger.info(f"   • Время работы: {final_stats['uptime_seconds']:.0f} сек")
            
            logger.info(f"🛑 WebSocket провайдер остановлен для {len(self.symbols)} символов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки WebSocket провайдера: {e}")
    
    async def wait_for_data(self, timeout: int = 30, min_symbols: int = None) -> bool:
        """
        🆕 ИЗМЕНЕНО: Ожидает получения достаточного количества данных для ВСЕХ символов
        
        Args:
            timeout: Таймаут ожидания в секундах
            min_symbols: Минимальное количество символов с данными (по умолчанию все)
            
        Returns:
            bool: True если данные получены, False если таймаут
        """
        if min_symbols is None:
            min_symbols = len(self.symbols)
        
        start_time = datetime.now()
        logger.info(f"⏳ Ожидание данных для минимум {min_symbols}/{len(self.symbols)} символов (таймаут: {timeout}с)...")
        
        check_interval = 1  # Проверяем каждую секунду
        
        while (datetime.now() - start_time).seconds < timeout:
            # Считаем символы с достаточными данными
            symbols_with_data = 0
            for symbol in self.symbols:
                market_data = self.market_data_by_symbol[symbol]
                if market_data.has_sufficient_data(min_data_points=5):
                    symbols_with_data += 1
            
            messages_received = self.connection_stats["messages_received"]
            
            logger.debug(f"📊 Проверка данных: {symbols_with_data}/{len(self.symbols)} символов готовы, messages={messages_received}")
            
            if symbols_with_data >= min_symbols and messages_received > 0:
                logger.info(f"✅ Данные получены за {(datetime.now() - start_time).seconds}с")
                # Показываем статистику по каждому символу
                for symbol in self.symbols:
                    market_data = self.market_data_by_symbol[symbol]
                    msgs = self.connection_stats["ticker_messages_by_symbol"][symbol]
                    has_data = "✅" if market_data.has_sufficient_data() else "❌"
                    logger.info(f"   {has_data} {symbol}: {len(market_data.prices)} точек, {msgs} сообщений, цена ${market_data.get_current_price():,.2f}")
                return True
                
            await asyncio.sleep(check_interval)
        
        logger.warning(f"⏰ Таймаут ожидания данных ({timeout}с)")
        logger.warning(f"📊 Итоговая статистика:")
        logger.warning(f"   • Сообщений получено: {self.connection_stats['messages_received']}")
        for symbol in self.symbols:
            market_data = self.market_data_by_symbol[symbol]
            msgs = self.connection_stats["ticker_messages_by_symbol"][symbol]
            has_data = "✅" if market_data.has_sufficient_data() else "❌"
            logger.warning(f"   {has_data} {symbol}: {msgs} сообщений, {len(market_data.prices)} точек, достаточно={market_data.has_sufficient_data()}")
            
        return False
    
    def __str__(self):
        """Строковое представление провайдера"""
        status = "Running" if self.running else "Stopped"
        messages = self.connection_stats["messages_received"]
        return f"WebSocketProvider(symbols={len(self.symbols)}, status={status}, messages={messages})"
    
    def __repr__(self):
        """Подробное представление для отладки"""
        symbols_str = ','.join(self.symbols[:3]) + ('...' if len(self.symbols) > 3 else '')
        return (f"WebSocketProvider(symbols=[{symbols_str}] ({len(self.symbols)} total), "
                f"running={self.running}, callbacks=[{len(self.ticker_callbacks)},{len(self.orderbook_callbacks)},{len(self.trades_callbacks)}], "
                f"messages={self.connection_stats['messages_received']})")
