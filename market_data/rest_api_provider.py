import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import aiohttp
import json
from config import Config

logger = logging.getLogger(__name__)


class RestApiProvider:
    """Провайдер для REST API запросов к Bybit"""
    
    def __init__(self, testnet: bool = None):
        """
        Инициализация REST API провайдера
        
        Args:
            testnet: Использовать testnet (по умолчанию из Config)
        """
        self.testnet = testnet if testnet is not None else Config.BYBIT_TESTNET
        self.base_url = "https://api-testnet.bybit.com" if self.testnet else "https://api.bybit.com"
        self.session: Optional[aiohttp.ClientSession] = None
        self._session_created = False
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получение или создание HTTP сессии"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'BybitTradingBot/2.1'
                }
            )
            self._session_created = True
            logger.info("✅ REST API сессия создана")
        return self.session
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Выполнение HTTP запроса к Bybit API
        
        Args:
            endpoint: Путь к эндпоинту
            params: Параметры запроса
            
        Returns:
            Ответ от API
            
        Raises:
            Exception: При ошибке запроса
        """
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        try:
            logger.debug(f"🌐 REST запрос: {endpoint} с параметрами: {params}")
            
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"❌ HTTP {response.status}: {error_text}")
                    raise Exception(f"HTTP {response.status}: {error_text}")
                
                data = await response.json()
                
                # Проверяем успешность ответа от Bybit
                if data.get('retCode') != 0:
                    error_msg = data.get('retMsg', 'Unknown error')
                    logger.error(f"❌ Bybit API error: {error_msg}")
                    raise Exception(f"Bybit API error: {error_msg}")
                
                logger.debug("✅ REST запрос выполнен успешно")
                return data
                
        except aiohttp.ClientError as e:
            logger.error(f"❌ Ошибка сети: {e}")
            raise Exception(f"Network error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка декодирования JSON: {e}")
            raise Exception(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"❌ Общая ошибка REST запроса: {e}")
            raise
    
    async def get_ticker_data(self, symbol: str = None) -> Dict[str, Any]:
        """
        Получение данных тикера для символа
        
        Args:
            symbol: Торговый символ (по умолчанию из Config)
            
        Returns:
            Данные тикера
        """
        symbol = symbol or Config.SYMBOL
        params = {
            'category': Config.CATEGORY,
            'symbol': symbol
        }
        return await self._make_request('/v5/market/tickers', params)
    
    async def get_kline_data(self, symbol: str = None, interval: str = '60', limit: int = 24) -> Dict[str, Any]:
        """
        Получение данных свечей
        
        Args:
            symbol: Торговый символ
            interval: Интервал свечей (в минутах)
            limit: Количество свечей
            
        Returns:
            Данные свечей
        """
        symbol = symbol or Config.SYMBOL
        params = {
            'category': Config.CATEGORY,
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        return await self._make_request('/v5/market/kline', params)
    
    async def get_instrument_info(self, symbol: str = None) -> Dict[str, Any]:
        """
        Получение информации об инструменте
        
        Args:
            symbol: Торговый символ
            
        Returns:
            Информация об инструменте
        """
        symbol = symbol or Config.SYMBOL
        params = {
            'category': Config.CATEGORY,
            'symbol': symbol
        }
        return await self._make_request('/v5/market/instruments-info', params)
    
    async def get_recent_trades(self, symbol: str = None, limit: int = 100) -> Dict[str, Any]:
        """
        Получение последних сделок
        
        Args:
            symbol: Торговый символ
            limit: Количество сделок
            
        Returns:
            Данные последних сделок
        """
        symbol = symbol or Config.SYMBOL
        params = {
            'category': Config.CATEGORY,
            'symbol': symbol,
            'limit': limit
        }
        return await self._make_request('/v5/market/recent-trade', params)
    
    async def get_orderbook(self, symbol: str = None, limit: int = 50) -> Dict[str, Any]:
        """
        Получение данных ордербука
        
        Args:
            symbol: Торговый символ
            limit: Глубина ордербука
            
        Returns:
            Данные ордербука
        """
        symbol = symbol or Config.SYMBOL
        params = {
            'category': Config.CATEGORY,
            'symbol': symbol,
            'limit': limit
        }
        return await self._make_request('/v5/market/orderbook', params)
    
    async def get_comprehensive_market_data(self, symbol: str = None) -> Dict[str, Any]:
        """
        Получение комплексных рыночных данных (объединяет все запросы)
        
        Args:
            symbol: Торговый символ
            
        Returns:
            Структурированные рыночные данные
        """
        symbol = symbol or Config.SYMBOL
        
        try:
            logger.info(f"📊 Получение комплексных данных для {symbol}")
            
            # Выполняем все запросы параллельно для ускорения
            tasks = [
                self.get_ticker_data(symbol),
                self.get_kline_data(symbol),
                self.get_instrument_info(symbol),
                self.get_recent_trades(symbol),
                self.get_orderbook(symbol)
            ]
            
            ticker_data, kline_data, instrument_info, recent_trades, orderbook_data = await asyncio.gather(
                *tasks, return_exceptions=True
            )
            
            # Проверяем на ошибки в параллельных запросах
            for i, result in enumerate([ticker_data, kline_data, instrument_info, recent_trades, orderbook_data]):
                if isinstance(result, Exception):
                    logger.warning(f"⚠️ Ошибка в запросе {i}: {result}")
            
            # Формируем структурированные данные
            market_data = await self._format_comprehensive_data(
                symbol,
                ticker_data if not isinstance(ticker_data, Exception) else {},
                kline_data if not isinstance(kline_data, Exception) else {},
                instrument_info if not isinstance(instrument_info, Exception) else {},
                recent_trades if not isinstance(recent_trades, Exception) else {},
                orderbook_data if not isinstance(orderbook_data, Exception) else {}
            )
            
            logger.info("✅ Комплексные данные успешно получены с Bybit REST API")
            return market_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения комплексных данных: {e}")
            raise
    
    async def _format_comprehensive_data(self, symbol: str, ticker_data: Dict, kline_data: Dict, 
                                       instrument_info: Dict, recent_trades: Dict, 
                                       orderbook_data: Dict) -> Dict[str, Any]:
        """
        Форматирование комплексных данных для анализа
        
        Args:
            symbol: Торговый символ
            ticker_data: Данные тикера
            kline_data: Данные свечей
            instrument_info: Информация об инструменте
            recent_trades: Последние сделки
            orderbook_data: Данные ордербука
            
        Returns:
            Форматированные рыночные данные
        """
        try:
            # Безопасное извлечение данных тикера
            ticker = {}
            if ticker_data.get('result', {}).get('list'):
                ticker = ticker_data['result']['list'][0]
            
            # Безопасное извлечение данных свечей
            klines = []
            if kline_data.get('result', {}).get('list'):
                klines = kline_data['result']['list']
            
            # Безопасное извлечение информации об инструменте
            instrument = {}
            if instrument_info.get('result', {}).get('list'):
                instrument = instrument_info['result']['list'][0]
            
            # Безопасное извлечение последних сделок
            trades = []
            if recent_trades.get('result', {}).get('list'):
                trades = recent_trades['result']['list'][:10]  # Берем только первые 10
            
            # Безопасное извлечение ордербука
            orderbook = {}
            if orderbook_data.get('result'):
                orderbook = orderbook_data['result']
            
            # Вычисляем статистику за 24 часа
            stats_24h = await self._calculate_24h_stats(klines)
            
            # Анализируем ордербук
            orderbook_analysis = self._analyze_orderbook(orderbook)
            
            # Анализируем трейды
            trades_analysis = self._analyze_recent_trades(trades)
            
            # Безопасное извлечение значений с fallback
            current_price = float(ticker.get('lastPrice', 0))
            price_change_24h = float(ticker.get('price24hPcnt', 0)) * 100
            volume_24h = float(ticker.get('volume24h', 0))
            high_24h = float(ticker.get('highPrice24h', 0))
            low_24h = float(ticker.get('lowPrice24h', 0))
            bid_price = float(ticker.get('bid1Price', 0))
            ask_price = float(ticker.get('ask1Price', 0))
            open_interest = float(ticker.get('openInterest', 0))
            
            # Информация об инструменте
            price_filter = instrument.get('priceFilter', {})
            lot_size_filter = instrument.get('lotSizeFilter', {})
            
            return {
                "symbol": symbol,
                "data_source": "REST_API",
                "timestamp": datetime.now().isoformat(),
                "current_price": current_price,
                "price_change_24h": price_change_24h,
                "volume_24h": volume_24h,
                "high_24h": high_24h,
                "low_24h": low_24h,
                "bid_price": bid_price,
                "ask_price": ask_price,
                "open_interest": open_interest,
                "spread": ask_price - bid_price if ask_price > 0 and bid_price > 0 else 0,
                "hourly_stats": stats_24h,
                "orderbook_analysis": orderbook_analysis,
                "trades_analysis": trades_analysis,
                "instrument_info": {
                    "min_price": float(price_filter.get('minPrice', 0)),
                    "max_price": float(price_filter.get('maxPrice', 0)),
                    "tick_size": float(price_filter.get('tickSize', 0)),
                    "min_order_qty": float(lot_size_filter.get('minOrderQty', 0)),
                    "max_order_qty": float(lot_size_filter.get('maxOrderQty', 0)),
                },
                "data_quality": {
                    "ticker_available": bool(ticker),
                    "klines_count": len(klines),
                    "trades_count": len(trades),
                    "orderbook_levels": len(orderbook.get('b', [])) + len(orderbook.get('a', [])),
                    "instrument_info_available": bool(instrument),
                    "all_data_complete": all([ticker, klines, trades, orderbook, instrument])
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования комплексных данных: {e}")
            # Возвращаем минимальные данные при ошибке
            return {
                "symbol": symbol,
                "data_source": "REST_API",
                "timestamp": datetime.now().isoformat(),
                "current_price": 0,
                "price_change_24h": 0,
                "volume_24h": 0,
                "high_24h": 0,
                "low_24h": 0,
                "bid_price": 0,
                "ask_price": 0,
                "open_interest": 0,
                "hourly_stats": {},
                "orderbook_analysis": {},
                "trades_analysis": {},
                "instrument_info": {},
                "error": str(e),
                "data_quality": {"all_data_complete": False}
            }
    
    async def _calculate_24h_stats(self, klines: list) -> Dict[str, Any]:
        """Вычисление статистики за 24 часа на основе свечей"""
        if not klines:
            logger.warning("⚠️ Нет данных свечей для расчета статистики")
            return {}
        
        try:
            # Сортируем свечи по времени (от старых к новым)
            sorted_klines = sorted(klines, key=lambda x: int(x[0]))
            
            prices = [float(kline[4]) for kline in sorted_klines]  # Цены закрытия
            volumes = [float(kline[5]) for kline in sorted_klines]  # Объемы
            highs = [float(kline[2]) for kline in sorted_klines]  # Максимумы
            lows = [float(kline[3]) for kline in sorted_klines]  # Минимумы
            
            if not prices or not volumes:
                return {}
            
            # Расчет тренда
            price_trend = "sideways"
            if len(prices) >= 2:
                if prices[-1] > prices[0]:
                    price_trend = "up"
                elif prices[-1] < prices[0]:
                    price_trend = "down"
            
            # Расчет волатильности
            price_volatility = 0
            if min(prices) > 0:
                price_volatility = (max(prices) - min(prices)) / min(prices) * 100
            
            return {
                "price_trend": price_trend,
                "avg_price_24h": sum(prices) / len(prices),
                "price_volatility": price_volatility,
                "total_volume_24h": sum(volumes),
                "avg_hourly_volume": sum(volumes) / len(volumes),
                "highest_hourly_volume": max(volumes),
                "lowest_hourly_volume": min(volumes),
                "hours_analyzed": len(sorted_klines),
                "price_range": {
                    "highest": max(highs),
                    "lowest": min(lows),
                    "range_percent": ((max(highs) - min(lows)) / min(lows) * 100) if min(lows) > 0 else 0
                },
                "volume_trend": self._calculate_volume_trend(volumes)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета 24ч статистики: {e}")
            return {"error": str(e)}
    
    def _calculate_volume_trend(self, volumes: List[float]) -> str:
        """Определение тренда объемов"""
        if len(volumes) < 2:
            return "insufficient_data"
        
        recent_avg = sum(volumes[-6:]) / len(volumes[-6:])  # Последние 6 часов
        older_avg = sum(volumes[:-6]) / len(volumes[:-6]) if len(volumes) > 6 else recent_avg
        
        if recent_avg > older_avg * 1.2:
            return "increasing"
        elif recent_avg < older_avg * 0.8:
            return "decreasing"
        else:
            return "stable"
    
    def _analyze_orderbook(self, orderbook: Dict) -> Dict[str, Any]:
        """Анализ ордербука"""
        try:
            if not orderbook.get('b') or not orderbook.get('a'):
                return {"error": "No orderbook data"}
            
            bids = orderbook['b'][:10]  # Первые 10 уровней
            asks = orderbook['a'][:10]
            
            bid_volumes = [float(bid[1]) for bid in bids]
            ask_volumes = [float(ask[1]) for ask in asks]
            
            total_bid_volume = sum(bid_volumes)
            total_ask_volume = sum(ask_volumes)
            total_volume = total_bid_volume + total_ask_volume
            
            bid_ask_ratio = total_bid_volume / total_ask_volume if total_ask_volume > 0 else 0
            
            return {
                "total_bid_volume": total_bid_volume,
                "total_ask_volume": total_ask_volume,
                "bid_ask_ratio": bid_ask_ratio,
                "bid_levels": len(bids),
                "ask_levels": len(asks),
                "market_pressure": "bullish" if bid_ask_ratio > 1.2 else "bearish" if bid_ask_ratio < 0.8 else "balanced"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _analyze_recent_trades(self, trades: List[Dict]) -> Dict[str, Any]:
        """Анализ последних сделок"""
        try:
            if not trades:
                return {"error": "No trades data"}
            
            buy_volume = sum(float(trade.get('size', 0)) for trade in trades if trade.get('side') == 'Buy')
            sell_volume = sum(float(trade.get('size', 0)) for trade in trades if trade.get('side') == 'Sell')
            
            total_volume = buy_volume + sell_volume
            buy_sell_ratio = buy_volume / sell_volume if sell_volume > 0 else 0
            
            # Анализ размеров сделок
            trade_sizes = [float(trade.get('size', 0)) for trade in trades]
            avg_trade_size = sum(trade_sizes) / len(trade_sizes) if trade_sizes else 0
            
            return {
                "total_trades": len(trades),
                "buy_volume": buy_volume,
                "sell_volume": sell_volume,
                "buy_sell_ratio": buy_sell_ratio,
                "avg_trade_size": avg_trade_size,
                "max_trade_size": max(trade_sizes) if trade_sizes else 0,
                "market_sentiment": "bullish" if buy_sell_ratio > 1.2 else "bearish" if buy_sell_ratio < 0.8 else "neutral"
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def get_server_time(self) -> Dict[str, Any]:
        """Получение серверного времени Bybit (для проверки подключения)"""
        try:
            return await self._make_request('/v5/market/time')
        except Exception as e:
            logger.error(f"❌ Ошибка получения серверного времени: {e}")
            raise
    
    async def check_connection(self) -> bool:
        """
        Проверка подключения к Bybit API
        
        Returns:
            True если подключение успешно
        """
        try:
            await self.get_server_time()
            logger.info("✅ Подключение к Bybit REST API успешно")
            return True
        except Exception as e:
            logger.error(f"❌ Не удалось подключиться к Bybit REST API: {e}")
            return False
    
    async def close(self):
        """Закрытие HTTP сессии"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("✅ REST API сессия закрыта")
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        await self.close()
    
    def __str__(self):
        """Строковое представление провайдера"""
        status = "Active" if self.session and not self.session.closed else "Inactive"
        return f"RestApiProvider(testnet={self.testnet}, status={status})"
