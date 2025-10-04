import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from collections import deque
from pybit.unified_trading import WebSocket
from config import Config

logger = logging.getLogger(__name__)

@dataclass
class Signal:
    """Торговый сигнал"""
    type: str          # "BUY", "SELL", "NEUTRAL"
    strength: float    # 0.0 - 1.0
    reason: str        # Описание причины
    price: float       # Цена на момент сигнала
    volume_24h: float  # Объем торгов
    timestamp: datetime
    change_1m: float   # Изменение за минуту
    change_5m: float   # Изменение за 5 минут

class RealtimeMarketData:
    """Класс для хранения и обработки рыночных данных в реальном времени"""
    
    def __init__(self, max_history: int = 1000):
        self.prices = deque(maxlen=max_history)  # История цен
        self.volumes = deque(maxlen=max_history) # История объемов
        self.timestamps = deque(maxlen=max_history) # История времени
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
            
            logger.debug(f"📊 Ticker: ${price:,.2f}, Vol: {volume:,.0f}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления тикера: {e}")
            
    def update_orderbook(self, orderbook_data: dict):
        """Обновляет данные стакана"""
        try:
            self.current_orderbook = orderbook_data
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
        except Exception as e:
            logger.error(f"❌ Ошибка обновления трейдов: {e}")
    
    def get_price_change(self, minutes: int) -> float:
        """Возвращает изменение цены за N минут в %"""
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

class WebSocketStrategy:
    """Стратегия торговых сигналов на основе WebSocket"""
    
    def __init__(self, telegram_bot):
        self.telegram_bot = telegram_bot
        self.market_data = RealtimeMarketData()
        self.last_signals = deque(maxlen=20)  # Последние 20 сигналов
        self.ws = None
        self.running = False
        
        # Настройки стратегии
        self.min_signal_strength = 0.5  # Минимальная сила сигнала
        self.signal_cooldown = timedelta(minutes=5)  # Минимальный интервал между сигналами одного типа
        
    async def start(self):
        """Запускает WebSocket подключения и мониторинг"""
        try:
            logger.info("🚀 Запуск WebSocket стратегии...")
            
            # Создаем WebSocket для linear (USDT перпетуалы)
            self.ws = WebSocket(
                testnet=Config.BYBIT_TESTNET,
                channel_type="linear"
            )
            
            # Подписываемся на нужные потоки
            self.ws.ticker_stream(Config.SYMBOL, self.handle_ticker)
            self.ws.orderbook_stream(50, Config.SYMBOL, self.handle_orderbook)
            self.ws.trade_stream(Config.SYMBOL, self.handle_trades)
            
            # Запускаем анализ сигналов каждые 30 секунд
            self.running = True
            asyncio.create_task(self.signal_analysis_loop())
            
            logger.info(f"✅ WebSocket стратегия запущена для {Config.SYMBOL}")
            
        except Exception as e:
            logger.error(f"💥 Ошибка запуска WebSocket стратегии: {e}")
            raise
    
    def handle_ticker(self, message):
        """Обработчик обновлений тикера"""
        try:
            if message.get('type') == 'snapshot' and message.get('data'):
                data = message['data']
                self.market_data.update_ticker(data)
                
                # ✅ ИСПРАВЛЕННЫЙ КОД: Проверяем на экстремальные движения в реальном времени
                try:
                    loop = asyncio.get_event_loop()
                    if loop and loop.is_running():
                        loop.create_task(self.check_extreme_movement())
                except:
                    # Если нет event loop - пропускаем, не критично
                    pass
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки тикера: {e}")
    
    def handle_orderbook(self, message):
        """Обработчик обновлений ордербука"""
        try:
            if message.get('type') == 'snapshot' and message.get('data'):
                data = message['data']
                self.market_data.update_orderbook(data)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки ордербука: {e}")
    
    def handle_trades(self, message):
        """Обработчик обновлений сделок"""
        try:
            if message.get('type') == 'snapshot' and message.get('data'):
                trades = message['data']
                self.market_data.update_trades(trades)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки трейдов: {e}")
    
    async def check_extreme_movement(self):
        """Проверяет экстремальные движения цены"""
        try:
            change_1m = self.market_data.get_price_change(1)
            current_price = self.market_data.get_current_price()
            
            # Проверяем резкие движения за минуту
            if abs(change_1m) >= 2.0:  # Движение больше 2% за минуту
                signal_type = "BUY" if change_1m > 0 else "SELL"
                
                signal = Signal(
                    type=signal_type,
                    strength=min(abs(change_1m) / 5.0, 1.0),  # Чем больше движение, тем сильнее сигнал
                    reason=f"🚨 РЕЗКОЕ ДВИЖЕНИЕ: {change_1m:+.2f}% за 1 минуту",
                    price=current_price,
                    volume_24h=self.market_data.get_volume_24h(),
                    timestamp=datetime.now(),
                    change_1m=change_1m,
                    change_5m=self.market_data.get_price_change(5)
                )
                
                if await self.should_send_signal(signal):
                    await self.send_signal_notification(signal)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка проверки движений: {e}")
    
    async def signal_analysis_loop(self):
        """Основной цикл анализа сигналов"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Анализируем каждые 30 секунд
                
                signal = await self.analyze_market()
                if signal and await self.should_send_signal(signal):
                    await self.send_signal_notification(signal)
                    
            except Exception as e:
                logger.error(f"💥 Ошибка в цикле анализа: {e}")
                await asyncio.sleep(10)
    
    async def analyze_market(self) -> Optional[Signal]:
        """Анализирует рыночные данные и генерирует сигнал"""
        try:
            if len(self.market_data.prices) < 10:  # Недостаточно данных
                return None
                
            current_price = self.market_data.get_current_price()
            change_1m = self.market_data.get_price_change(1)
            change_5m = self.market_data.get_price_change(5)
            change_24h = self.market_data.get_price_change_24h()
            volume_24h = self.market_data.get_volume_24h()
            
            signal_type = "NEUTRAL"
            strength = 0.0
            reasons = []
            
            # 🎯 СТРАТЕГИЯ 1: Импульсная торговля
            if change_1m > 1.5 and change_5m > 2.0:  # Устойчивый рост
                signal_type = "BUY"
                strength += 0.4
                reasons.append(f"Импульс вверх: 1м={change_1m:+.1f}%, 5м={change_5m:+.1f}%")
                
            elif change_1m < -1.5 and change_5m < -2.0:  # Устойчивое падение
                signal_type = "SELL" 
                strength += 0.4
                reasons.append(f"Импульс вниз: 1м={change_1m:+.1f}%, 5м={change_5m:+.1f}%")
            
            # 🎯 СТРАТЕГИЯ 2: Разворот тренда
            elif change_1m > 0.8 and change_5m < -1.0:  # Разворот вверх
                signal_type = "BUY"
                strength += 0.3
                reasons.append("Возможный разворот вверх")
                
            elif change_1m < -0.8 and change_5m > 1.0:  # Разворот вниз
                signal_type = "SELL"
                strength += 0.3  
                reasons.append("Возможный разворот вниз")
            
            # 🎯 СТРАТЕГИЯ 3: Объемный анализ
            if volume_24h > 20000:  # Высокий объем
                strength += 0.2
                reasons.append(f"Высокий объем: {volume_24h:,.0f} BTC")
            elif volume_24h < 8000:  # Низкий объем
                strength -= 0.1  # Снижаем силу сигнала
                
            # 🎯 СТРАТЕГИЯ 4: Анализ ордербука
            if self.market_data.current_orderbook:
                orderbook_signal = self.analyze_orderbook()
                if orderbook_signal:
                    if orderbook_signal['type'] == signal_type or signal_type == "NEUTRAL":
                        signal_type = orderbook_signal['type']
                        strength += orderbook_signal['strength']
                        reasons.append(orderbook_signal['reason'])
            
            # Создаем сигнал только если есть причины
            if not reasons:
                return None
                
            return Signal(
                type=signal_type,
                strength=min(strength, 1.0),
                reason=" | ".join(reasons),
                price=current_price,
                volume_24h=volume_24h, 
                timestamp=datetime.now(),
                change_1m=change_1m,
                change_5m=change_5m
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа рынка: {e}")
            return None
    
    def analyze_orderbook(self) -> Optional[Dict]:
        """Анализ ордербука для определения давления"""
        try:
            orderbook = self.market_data.current_orderbook
            if not orderbook.get('b') or not orderbook.get('a'):
                return None
                
            # Берем первые 10 уровней
            bids = orderbook['b'][:10] if len(orderbook['b']) >= 10 else orderbook['b']
            asks = orderbook['a'][:10] if len(orderbook['a']) >= 10 else orderbook['a']
            
            # Вычисляем объемы
            bid_volume = sum(float(bid[1]) for bid in bids)
            ask_volume = sum(float(ask[1]) for ask in asks)
            
            total_volume = bid_volume + ask_volume
            if total_volume == 0:
                return None
                
            # Определяем преимущество
            bid_dominance = bid_volume / total_volume
            
            if bid_dominance > 0.65:  # Преимущество покупателей
                return {
                    'type': 'BUY',
                    'strength': 0.2,
                    'reason': f'Давление покупателей {bid_dominance:.1%}'
                }
            elif bid_dominance < 0.35:  # Преимущество продавцов  
                return {
                    'type': 'SELL',
                    'strength': 0.2,
                    'reason': f'Давление продавцов {1-bid_dominance:.1%}'
                }
                
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа ордербука: {e}")
            return None
    
    async def should_send_signal(self, signal: Signal) -> bool:
        """Проверяет, следует ли отправить сигнал"""
        try:
            # Фильтр по силе сигнала
            if signal.strength < self.min_signal_strength:
                return False
                
            # Проверяем кулдаун
            now = datetime.now()
            for last_signal in self.last_signals:
                if (last_signal.type == signal.type and 
                    now - last_signal.timestamp < self.signal_cooldown):
                    logger.debug(f"⏰ Сигнал {signal.type} в кулдауне")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки сигнала: {e}")
            return False
    
    async def send_signal_notification(self, signal: Signal):
        """Отправляет уведомление о сигнале"""
        try:
            # Эмодзи для сигналов
            emoji_map = {
                "BUY": "🟢",
                "SELL": "🔴",
                "NEUTRAL": "🔶"
            }
            
            # Сила сигнала
            if signal.strength >= 0.8:
                strength_emoji = "🔥"
                strength_text = "ОЧЕНЬ СИЛЬНЫЙ"
            elif signal.strength >= 0.7:
                strength_emoji = "⚡"
                strength_text = "СИЛЬНЫЙ" 
            elif signal.strength >= 0.6:
                strength_emoji = "💪"
                strength_text = "СРЕДНИЙ"
            else:
                strength_emoji = "💡"
                strength_text = "СЛАБЫЙ"
            
            message = f"""
{emoji_map[signal.type]} **WEBSOCKET СИГНАЛ**

🎯 **Тип:** {signal.type}
{strength_emoji} **Сила:** {strength_text} ({signal.strength:.2f})

💰 **Цена:** ${signal.price:,.2f}
📊 **1 мин:** {signal.change_1m:+.2f}%
📈 **5 мин:** {signal.change_5m:+.2f}%  
📦 **Объем 24ч:** {signal.volume_24h:,.0f} BTC

🧠 **Анализ:**
{signal.reason}

⏰ {signal.timestamp.strftime('%H:%M:%S')}
🌐 *Данные в реальном времени*

_Торговые сигналы несут риски!_
            """
            
            # Отправляем через Telegram бот
            await self.telegram_bot.broadcast_signal(message)
            
            # Сохраняем в историю
            self.last_signals.append(signal)
            
            logger.info(f"📨 Отправлен сигнал: {signal.type} ({signal.strength:.2f})")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сигнала: {e}")
    
    async def stop(self):
        """Останавливает стратегию"""
        try:
            self.running = False
            if self.ws:
                self.ws.exit()
            logger.info("🛑 WebSocket стратегия остановлена")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки стратегии: {e}")
