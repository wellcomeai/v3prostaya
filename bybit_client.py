import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import aiohttp
import json
from config import Config

logger = logging.getLogger(__name__)

class BybitClient:
    """Асинхронный клиент для работы с Bybit API"""
    
    def __init__(self):
        self.base_url = "https://api-testnet.bybit.com" if Config.BYBIT_TESTNET else "https://api.bybit.com"
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
                    'User-Agent': 'BybitTradingBot/1.0'
                }
            )
            self._session_created = True
            logger.info("✅ HTTP сессия создана")
        return self.session
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Выполнение HTTP запроса к Bybit API"""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        try:
            logger.debug(f"🌐 Запрос: {url} с параметрами: {params}")
            
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
                
                logger.debug("✅ Запрос выполнен успешно")
                return data
                
        except aiohttp.ClientError as e:
            logger.error(f"❌ Ошибка сети: {e}")
            raise Exception(f"Network error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка декодирования JSON: {e}")
            raise Exception(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"❌ Общая ошибка запроса: {e}")
            raise
    
    async def get_market_data(self) -> Dict[str, Any]:
        """Получение рыночных данных за последний день"""
        try:
            logger.info(f"📊 Получение данных для {Config.SYMBOL}")
            
            # Выполняем все запросы параллельно для ускорения
            tasks = [
                self._get_ticker_data(),
                self._get_kline_data(),
                self._get_instrument_info(),
                self._get_recent_trades()
            ]
            
            ticker_data, kline_data, instrument_info, recent_trades = await asyncio.gather(
                *tasks, return_exceptions=True
            )
            
            # Проверяем на ошибки в параллельных запросах
            for i, result in enumerate([ticker_data, kline_data, instrument_info, recent_trades]):
                if isinstance(result, Exception):
                    logger.warning(f"⚠️ Ошибка в запросе {i}: {result}")
            
            # Формируем структурированные данные
            market_data = await self._format_market_data(
                ticker_data if not isinstance(ticker_data, Exception) else {},
                kline_data if not isinstance(kline_data, Exception) else {},
                instrument_info if not isinstance(instrument_info, Exception) else {},
                recent_trades if not isinstance(recent_trades, Exception) else {}
            )
            
            logger.info("✅ Данные успешно получены с Bybit")
            return market_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных с Bybit: {e}")
            raise
    
    async def _get_ticker_data(self) -> Dict[str, Any]:
        """Получение данных тикера"""
        params = {
            'category': Config.CATEGORY,
            'symbol': Config.SYMBOL
        }
        return await self._make_request('/v5/market/tickers', params)
    
    async def _get_kline_data(self) -> Dict[str, Any]:
        """Получение данных свечей за последние 24 часа"""
        params = {
            'category': Config.CATEGORY,
            'symbol': Config.SYMBOL,
            'interval': '60',  # 60 минут
            'limit': 24  # Последние 24 часа
        }
        return await self._make_request('/v5/market/kline', params)
    
    async def _get_instrument_info(self) -> Dict[str, Any]:
        """Получение информации об инструменте"""
        params = {
            'category': Config.CATEGORY,
            'symbol': Config.SYMBOL
        }
        return await self._make_request('/v5/market/instruments-info', params)
    
    async def _get_recent_trades(self) -> Dict[str, Any]:
        """Получение последних сделок"""
        params = {
            'category': Config.CATEGORY,
            'symbol': Config.SYMBOL,
            'limit': 100
        }
        return await self._make_request('/v5/market/recent-trade', params)
    
    async def _format_market_data(self, ticker_data: Dict, kline_data: Dict, 
                                instrument_info: Dict, recent_trades: Dict) -> Dict[str, Any]:
        """Форматирование данных для анализа"""
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
            
            # Вычисляем статистику за 24 часа
            stats_24h = await self._calculate_24h_stats(klines)
            
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
                "symbol": Config.SYMBOL,
                "timestamp": datetime.now().isoformat(),
                "current_price": current_price,
                "price_change_24h": price_change_24h,
                "volume_24h": volume_24h,
                "high_24h": high_24h,
                "low_24h": low_24h,
                "bid_price": bid_price,
                "ask_price": ask_price,
                "open_interest": open_interest,
                "hourly_data": stats_24h,
                "recent_trades_count": len(trades),
                "recent_trades_avg_size": sum(float(trade.get('size', 0)) for trade in trades) / len(trades) if trades else 0,
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
                    "trades_available": len(trades),
                    "instrument_info_available": bool(instrument)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования данных: {e}")
            # Возвращаем минимальные данные при ошибке
            return {
                "symbol": Config.SYMBOL,
                "timestamp": datetime.now().isoformat(),
                "current_price": 0,
                "price_change_24h": 0,
                "volume_24h": 0,
                "high_24h": 0,
                "low_24h": 0,
                "bid_price": 0,
                "ask_price": 0,
                "open_interest": 0,
                "hourly_data": {},
                "recent_trades_count": 0,
                "recent_trades_avg_size": 0,
                "instrument_info": {},
                "error": str(e)
            }
    
    async def _calculate_24h_stats(self, klines: list) -> Dict[str, Any]:
        """Вычисление статистики за 24 часа на основе свечей"""
        if not klines:
            logger.warning("⚠️ Нет данных свечей для расчета статистики")
            return {}
        
        try:
            # Сортируем свечи по времени (от старых к новым)
            # В Bybit API klines возвращаются в формате: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
            sorted_klines = sorted(klines, key=lambda x: int(x[0]))
            
            prices = [float(kline[4]) for kline in sorted_klines]  # Цены закрытия
            volumes = [float(kline[5]) for kline in sorted_klines]  # Объемы
            
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
                    "highest": max(prices),
                    "lowest": min(prices)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета 24ч статистики: {e}")
            return {"error": str(e)}
    
    async def get_server_time(self) -> Dict[str, Any]:
        """Получение серверного времени Bybit (для проверки подключения)"""
        try:
            return await self._make_request('/v5/market/time')
        except Exception as e:
            logger.error(f"❌ Ошибка получения серверного времени: {e}")
            raise
    
    async def check_connection(self) -> bool:
        """Проверка подключения к Bybit API"""
        try:
            await self.get_server_time()
            logger.info("✅ Подключение к Bybit API успешно")
            return True
        except Exception as e:
            logger.error(f"❌ Не удалось подключиться к Bybit API: {e}")
            return False
    
    async def close(self):
        """Закрытие HTTP сессии"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("✅ HTTP сессия закрыта")
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        await self.close()
