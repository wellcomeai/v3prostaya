import logging
from datetime import datetime, timedelta
from pybit.unified_trading import HTTP
from config import Config

logger = logging.getLogger(__name__)

class BybitClient:
    """Клиент для работы с Bybit API"""
    
    def __init__(self):
        self.session = HTTP(
            testnet=Config.BYBIT_TESTNET,
            api_key=Config.BYBIT_API_KEY,
            api_secret=Config.BYBIT_API_SECRET,
        )
    
    async def get_market_data(self) -> dict:
        """Получение рыночных данных за последний день"""
        try:
            logger.info(f"Получение данных для {Config.SYMBOL}")
            
            # Получаем текущую цену и основную информацию
            ticker_data = self.session.get_tickers(
                category=Config.CATEGORY,
                symbol=Config.SYMBOL
            )
            
            # Получаем свечи за последние 24 часа (интервал 1 час)
            kline_data = self.session.get_kline(
                category=Config.CATEGORY,
                symbol=Config.SYMBOL,
                interval="60",  # 60 минут
                limit=24  # Последние 24 часа
            )
            
            # Получаем информацию об инструменте
            instrument_info = self.session.get_instruments_info(
                category=Config.CATEGORY,
                symbol=Config.SYMBOL
            )
            
            # Получаем последние сделки
            recent_trades = self.session.get_public_trade_history(
                category=Config.CATEGORY,
                symbol=Config.SYMBOL,
                limit=100
            )
            
            # Формируем структурированные данные
            market_data = self._format_market_data(
                ticker_data,
                kline_data, 
                instrument_info,
                recent_trades
            )
            
            logger.info("Данные успешно получены с Bybit")
            return market_data
            
        except Exception as e:
            logger.error(f"Ошибка получения данных с Bybit: {e}")
            raise
    
    def _format_market_data(self, ticker_data, kline_data, instrument_info, recent_trades) -> dict:
        """Форматирование данных для анализа"""
        try:
            # Извлекаем данные тикера
            ticker = ticker_data['result']['list'][0] if ticker_data['result']['list'] else {}
            
            # Извлекаем данные свечей (последние 24 часа)
            klines = kline_data['result']['list'] if kline_data['result']['list'] else []
            
            # Извлекаем информацию об инструменте
            instrument = instrument_info['result']['list'][0] if instrument_info['result']['list'] else {}
            
            # Извлекаем последние сделки
            trades = recent_trades['result']['list'][:10] if recent_trades['result']['list'] else []
            
            # Вычисляем статистику за 24 часа
            stats_24h = self._calculate_24h_stats(klines)
            
            return {
                "symbol": Config.SYMBOL,
                "timestamp": datetime.now().isoformat(),
                "current_price": float(ticker.get('lastPrice', 0)),
                "price_change_24h": float(ticker.get('price24hPcnt', 0)) * 100,  # В процентах
                "volume_24h": float(ticker.get('volume24h', 0)),
                "high_24h": float(ticker.get('highPrice24h', 0)),
                "low_24h": float(ticker.get('lowPrice24h', 0)),
                "bid_price": float(ticker.get('bid1Price', 0)),
                "ask_price": float(ticker.get('ask1Price', 0)),
                "open_interest": float(ticker.get('openInterest', 0)),
                "hourly_data": stats_24h,
                "recent_trades_count": len(trades),
                "recent_trades_avg_size": sum(float(trade.get('size', 0)) for trade in trades) / len(trades) if trades else 0,
                "instrument_info": {
                    "min_price": float(instrument.get('priceFilter', {}).get('minPrice', 0)),
                    "max_price": float(instrument.get('priceFilter', {}).get('maxPrice', 0)),
                    "tick_size": float(instrument.get('priceFilter', {}).get('tickSize', 0)),
                    "min_order_qty": float(instrument.get('lotSizeFilter', {}).get('minOrderQty', 0)),
                    "max_order_qty": float(instrument.get('lotSizeFilter', {}).get('maxOrderQty', 0)),
                }
            }
            
        except Exception as e:
            logger.error(f"Ошибка форматирования данных: {e}")
            raise
    
    def _calculate_24h_stats(self, klines) -> dict:
        """Вычисление статистики за 24 часа на основе свечей"""
        if not klines:
            return {}
        
        try:
            # Сортируем свечи по времени (от старых к новым)
            sorted_klines = sorted(klines, key=lambda x: int(x[0]))
            
            prices = [float(kline[4]) for kline in sorted_klines]  # Цены закрытия
            volumes = [float(kline[5]) for kline in sorted_klines]  # Объемы
            
            return {
                "price_trend": "up" if prices[-1] > prices[0] else "down" if prices[-1] < prices[0] else "sideways",
                "avg_price_24h": sum(prices) / len(prices),
                "price_volatility": (max(prices) - min(prices)) / min(prices) * 100,  # Волатильность в %
                "total_volume_24h": sum(volumes),
                "avg_hourly_volume": sum(volumes) / len(volumes),
                "highest_hourly_volume": max(volumes),
                "lowest_hourly_volume": min(volumes),
                "hours_analyzed": len(sorted_klines)
            }
            
        except Exception as e:
            logger.error(f"Ошибка расчета 24ч статистики: {e}")
            return {}
