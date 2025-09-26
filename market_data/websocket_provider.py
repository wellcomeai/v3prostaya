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
        
        logger.info(f"📊 RealtimeMarketData инициализирован (max_history={max_history})")
        
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
                
                logger.info(f"📊 Ticker обновлен: ${price:,.2f}, Vol: {volume:,.0f} BTC, Updates: {self.stats['ticker_updates']}")
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
            
            logger.info(f"💰 Trades обновлены: {len(trades_data)} сделок, Total updates: {self.stats['trades_updates']}")
            
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
        logger.debug(f"📦 Объем 24ч: {volume:,.0f} BTC")
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
    """Провайдер WebSocket данных от Bybit с расширенной отладкой"""
    
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
        
        # Статистика подключения
        self.connection_stats = {
            "connection_attempts": 0,
            "successful_connections": 0,
            "connection_failures": 0,
            "messages_received": 0,
            "ticker_messages": 0,
            "orderbook_messages": 0,
            "trades_messages": 0,
            "unknown_messages": 0,
            "error_messages": 0,
            "last_message_time": None,
            "start_time": None
        }
        
        logger.info(f"🔌 WebSocketProvider инициализирован: {self.symbol}, testnet={self.testnet}")
        
    def add_ticker_callback(self, callback: Callable[[dict], None]):
        """Добавляет callback для обновлений тикера"""
        self.ticker_callbacks.append(callback)
        logger.info(f"📝 Добавлен ticker callback ({len(self.ticker_callbacks)} всего)")
        
    def add_orderbook_callback(self, callback: Callable[[dict], None]):
        """Добавляет callback для обновлений ордербука"""
        self.orderbook_callbacks.append(callback)
        logger.info(f"📝 Добавлен orderbook callback ({len(self.orderbook_callbacks)} всего)")
        
    def add_trades_callback(self, callback: Callable[[list], None]):
        """Добавляет callback для обновлений трейдов"""
        self.trades_callbacks.append(callback)
        logger.info(f"📝 Добавлен trades callback ({len(self.trades_callbacks)} всего)")
    
    async def start(self):
        """Запускает WebSocket подключения"""
        try:
            self.connection_stats["connection_attempts"] += 1
            self.connection_stats["start_time"] = datetime.now()
            
            logger.info(f"🚀 Запуск WebSocket провайдера для {self.symbol}...")
            logger.info(f"🔧 Настройки: testnet={self.testnet}, symbol={self.symbol}")
            
            # Создаем WebSocket для linear (USDT перпетуалы)
            logger.info("🔗 Создание WebSocket соединения...")
            self.ws = WebSocket(
                testnet=self.testnet,
                channel_type="linear"
            )
            
            logger.info("📡 Подписка на потоки данных...")
            
            # Подписываемся на нужные потоки с детальным логированием
            logger.info(f"📊 Подписка на ticker stream: {self.symbol}")
            self.ws.ticker_stream(self.symbol, self._handle_ticker)
            
            logger.info(f"📋 Подписка на orderbook stream: {self.symbol} (50 levels)")
            self.ws.orderbook_stream(50, self.symbol, self._handle_orderbook)
            
            logger.info(f"💰 Подписка на trade stream: {self.symbol}")
            self.ws.trade_stream(self.symbol, self._handle_trades)
            
            self.running = True
            self.connection_stats["successful_connections"] += 1
            
            logger.info(f"✅ WebSocket провайдер запущен для {self.symbol}")
            logger.info(f"📞 Registered callbacks: ticker={len(self.ticker_callbacks)}, orderbook={len(self.orderbook_callbacks)}, trades={len(self.trades_callbacks)}")
            
        except Exception as e:
            self.connection_stats["connection_failures"] += 1
            logger.error(f"💥 Ошибка запуска WebSocket провайдера: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            self.running = False
            raise
    
    def _handle_ticker(self, message: dict):
        """Внутренний обработчик обновлений тикера"""
        try:
            self.connection_stats["messages_received"] += 1
            self.connection_stats["last_message_time"] = datetime.now()
            
            logger.info(f"📨 Получено ticker сообщение: {json.dumps(message, indent=2)}")
            
            msg_type = message.get('type')
            logger.info(f"📊 Ticker message type: {msg_type}")
            
            if msg_type == 'snapshot' and message.get('data'):
                self.connection_stats["ticker_messages"] += 1
                data = message['data']
                
                logger.info(f"📊 Ticker data получены: {json.dumps(data, indent=2)}")
                
                # Обновляем внутренние данные
                self.market_data.update_ticker(data)
                
                # Уведомляем всех подписчиков
                logger.info(f"📞 Вызов {len(self.ticker_callbacks)} ticker callbacks...")
                for i, callback in enumerate(self.ticker_callbacks):
                    try:
                        logger.debug(f"📞 Вызов ticker callback #{i}")
                        callback(data)
                        logger.debug(f"✅ Ticker callback #{i} выполнен")
                    except Exception as e:
                        logger.error(f"❌ Ошибка в ticker callback #{i}: {e}")
                        logger.error(f"Stack trace: {traceback.format_exc()}")
                
                logger.info(f"✅ Ticker callbacks завершены")
                
            elif msg_type == 'delta':
                logger.info(f"📊 Получен ticker delta: {message}")
                # Можно обрабатывать дельта-обновления
                pass
            else:
                self.connection_stats["unknown_messages"] += 1
                logger.warning(f"⚠️ Неизвестный тип ticker сообщения: {msg_type}")
                logger.warning(f"Full message: {json.dumps(message, indent=2)}")
                
        except Exception as e:
            self.connection_stats["error_messages"] += 1
            logger.error(f"❌ Ошибка обработки ticker сообщения: {e}")
            logger.error(f"Raw message: {message}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
    
    def _handle_orderbook(self, message: dict):
        """Внутренний обработчик обновлений ордербука"""
        try:
            self.connection_stats["messages_received"] += 1
            self.connection_stats["last_message_time"] = datetime.now()
            
            logger.debug(f"📨 Получено orderbook сообщение: type={message.get('type')}")
            
            msg_type = message.get('type')
            
            if msg_type == 'snapshot' and message.get('data'):
                self.connection_stats["orderbook_messages"] += 1
                data = message['data']
                
                logger.debug(f"📋 Orderbook data: bids={len(data.get('b', []))}, asks={len(data.get('a', []))}")
                
                # Обновляем внутренние данные
                self.market_data.update_orderbook(data)
                
                # Уведомляем всех подписчиков
                logger.debug(f"📞 Вызов {len(self.orderbook_callbacks)} orderbook callbacks...")
                for i, callback in enumerate(self.orderbook_callbacks):
                    try:
                        callback(data)
                        logger.debug(f"✅ Orderbook callback #{i} выполнен")
                    except Exception as e:
                        logger.error(f"❌ Ошибка в orderbook callback #{i}: {e}")
                
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
        """Внутренний обработчик обновлений сделок"""
        try:
            self.connection_stats["messages_received"] += 1
            self.connection_stats["last_message_time"] = datetime.now()
            
            logger.debug(f"📨 Получено trades сообщение: type={message.get('type')}")
            
            msg_type = message.get('type')
            
            if msg_type == 'snapshot' and message.get('data'):
                self.connection_stats["trades_messages"] += 1
                trades = message['data']
                
                logger.info(f"💰 Trades data: {len(trades)} сделок")
                
                # Обновляем внутренние данные
                self.market_data.update_trades(trades)
                
                # Уведомляем всех подписчиков
                logger.debug(f"📞 Вызов {len(self.trades_callbacks)} trades callbacks...")
                for i, callback in enumerate(self.trades_callbacks):
                    try:
                        callback(trades)
                        logger.debug(f"✅ Trades callback #{i} выполнен")
                    except Exception as e:
                        logger.error(f"❌ Ошибка в trades callback #{i}: {e}")
                
            else:
                self.connection_stats["unknown_messages"] += 1
                logger.warning(f"⚠️ Неизвестный тип trades сообщения: {msg_type}")
                
        except Exception as e:
            self.connection_stats["error_messages"] += 1
            logger.error(f"❌ Ошибка обработки trades сообщения: {e}")
            logger.error(f"Raw message: {message}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
    
    def get_market_data(self) -> RealtimeMarketData:
        """Возвращает объект с рыночными данными"""
        return self.market_data
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Возвращает текущую статистику рынка"""
        try:
            stats = {
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
                "last_update": datetime.now().isoformat(),
                "connection_stats": self.connection_stats.copy(),
                "market_data_stats": self.market_data.get_stats()
            }
            
            logger.debug(f"📊 Current stats: price=${stats['current_price']:,.2f}, data_points={stats['data_points']}")
            return stats
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {
                "symbol": self.symbol,
                "current_price": 0,
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
            logger.info(f"   • Попыток подключения: {final_stats['connection_attempts']}")
            logger.info(f"   • Успешных подключений: {final_stats['successful_connections']}")
            logger.info(f"   • Сообщений получено: {final_stats['messages_received']}")
            logger.info(f"   • Ticker сообщений: {final_stats['ticker_messages']}")
            logger.info(f"   • Orderbook сообщений: {final_stats['orderbook_messages']}")
            logger.info(f"   • Trades сообщений: {final_stats['trades_messages']}")
            logger.info(f"   • Время работы: {final_stats['uptime_seconds']:.0f} сек")
            
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
        logger.info(f"⏳ Ожидание данных (таймаут: {timeout}с)...")
        
        check_interval = 1  # Проверяем каждую секунду
        
        while (datetime.now() - start_time).seconds < timeout:
            # Проверяем наличие данных
            has_data = self.market_data.has_sufficient_data()
            messages_received = self.connection_stats["messages_received"]
            
            logger.debug(f"📊 Проверка данных: has_data={has_data}, messages={messages_received}")
            
            if has_data and messages_received > 0:
                logger.info(f"✅ Данные получены за {(datetime.now() - start_time).seconds}с")
                return True
                
            await asyncio.sleep(check_interval)
        
        logger.warning(f"⏰ Таймаут ожидания данных ({timeout}с)")
        logger.warning(f"📊 Итоговая статистика:")
        logger.warning(f"   • Сообщений получено: {self.connection_stats['messages_received']}")
        logger.warning(f"   • Ticker сообщений: {self.connection_stats['ticker_messages']}")
        logger.warning(f"   • Data points: {len(self.market_data.prices)}")
        logger.warning(f"   • Has sufficient data: {self.market_data.has_sufficient_data()}")
            
        return False
    
    def __str__(self):
        """Строковое представление провайдера"""
        status = "Running" if self.running else "Stopped"
        messages = self.connection_stats["messages_received"]
        return f"WebSocketProvider(symbol={self.symbol}, testnet={self.testnet}, status={status}, messages={messages})"
    
    def __repr__(self):
        """Подробное представление для отладки"""
        return (f"WebSocketProvider(symbol='{self.symbol}', testnet={self.testnet}, "
                f"running={self.running}, callbacks=[{len(self.ticker_callbacks)},{len(self.orderbook_callbacks)},{len(self.trades_callbacks)}], "
                f"messages={self.connection_stats['messages_received']})")
