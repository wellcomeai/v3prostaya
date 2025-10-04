"""
YFinance WebSocket Provider

Провайдер WebSocket для получения данных фьючерсов CME в реальном времени через yfinance.
Поддерживает:
- MCL (Micro WTI Crude Oil Futures)
- MGC (Micro Gold Futures)  
- MES (Micro E-mini S&P 500 Futures)
- MNQ (Micro E-mini Nasdaq 100 Futures)

Архитектура:
- Асинхронный WebSocket клиент yfinance
- Thread-safe обработка сообщений
- Callback система для подписчиков
- Детальная статистика и мониторинг
- Graceful shutdown
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from collections import deque
import traceback
import json

logger = logging.getLogger(__name__)


class RealtimeFuturesData:
    """Класс для хранения и обработки данных фьючерсов в реальном времени"""
    
    def __init__(self, symbol: str, max_history: int = 1000):
        """
        Инициализация хранилища данных для фьючерса
        
        Args:
            symbol: Символ фьючерса (MCL, MGC, MES, MNQ)
            max_history: Максимальное количество записей в истории
        """
        self.symbol = symbol
        self.prices = deque(maxlen=max_history)
        self.volumes = deque(maxlen=max_history)
        self.timestamps = deque(maxlen=max_history)
        self.current_data = {}
        
        # Статистика обновлений
        self.stats = {
            "updates": 0,
            "last_update": None,
            "first_update": None,
            "errors": 0
        }
        
        # Время последнего summary лога
        self.last_summary_log = None
        
        logger.info(f"📊 RealtimeFuturesData инициализирован для {symbol} (max_history={max_history})")
    
    def update(self, data: dict):
        """
        Обновляет данные фьючерса
        
        Args:
            data: Данные от yfinance WebSocket
        """
        try:
            logger.debug(f"🔄 Обновление данных {self.symbol}: {json.dumps(data, indent=2)}")
            
            self.current_data = data
            self.stats["updates"] += 1
            self.stats["last_update"] = datetime.now()
            
            if self.stats["first_update"] is None:
                self.stats["first_update"] = datetime.now()
            
            # Извлекаем цену (разные поля в зависимости от типа сообщения)
            price = None
            if 'price' in data:
                price = float(data['price'])
            elif 'last' in data:
                price = float(data['last'])
            elif 'lastPrice' in data:
                price = float(data['lastPrice'])
            
            # Извлекаем объем
            volume = None
            if 'volume' in data:
                volume = float(data['volume'])
            elif 'dayVolume' in data:
                volume = float(data['dayVolume'])
            
            timestamp = datetime.now()
            
            if price and price > 0:  # Валидная цена
                self.prices.append(price)
                if volume is not None:
                    self.volumes.append(volume)
                self.timestamps.append(timestamp)
                
                # Периодическое логирование раз в минуту
                if self.last_summary_log is None or (datetime.now() - self.last_summary_log).total_seconds() > 60:
                    logger.info(f"📊 {self.symbol} обновлен: ${price:,.2f}, Vol: {volume:,.0f if volume else 0}, Updates: {self.stats['updates']}")
                    self.last_summary_log = datetime.now()
                else:
                    logger.debug(f"📊 {self.symbol} обновлен: ${price:,.2f}")
            else:
                logger.warning(f"⚠️ {self.symbol}: Невалидная цена: {price}")
                self.stats["errors"] += 1
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления данных {self.symbol}: {e}")
            logger.error(f"Raw data: {data}")
            self.stats["errors"] += 1
    
    def get_price_change(self, minutes: int) -> float:
        """
        Возвращает изменение цены за N минут в %
        
        Args:
            minutes: Количество минут для анализа
            
        Returns:
            Изменение цены в процентах
        """
        if len(self.prices) < 2 or len(self.timestamps) < 2:
            logger.debug(f"🔍 {self.symbol}: Недостаточно данных для расчета изменения за {minutes}м")
            return 0.0
        
        current_price = self.prices[-1]
        target_time = datetime.now() - timedelta(minutes=minutes)
        
        # Ищем ближайшую цену к нужному времени
        for i, ts in enumerate(reversed(self.timestamps)):
            if ts <= target_time:
                old_price = self.prices[-(i+1)]
                if old_price > 0:
                    change = (current_price - old_price) / old_price * 100
                    logger.debug(f"📈 {self.symbol} изменение за {minutes}м: {change:+.2f}%")
                    return change
                break
        
        logger.debug(f"🔍 {self.symbol}: Не найдена цена для времени {minutes}м назад")
        return 0.0
    
    def get_current_price(self) -> float:
        """Возвращает текущую цену"""
        price = self.prices[-1] if self.prices else 0.0
        logger.debug(f"💰 {self.symbol} текущая цена: ${price:,.2f}")
        return price
    
    def get_volume(self) -> float:
        """Возвращает текущий объем"""
        volume = self.volumes[-1] if self.volumes else 0.0
        logger.debug(f"📦 {self.symbol} объем: {volume:,.0f}")
        return volume
    
    def has_sufficient_data(self, min_data_points: int = 10) -> bool:
        """Проверяет, достаточно ли данных для анализа"""
        sufficient = len(self.prices) >= min_data_points
        logger.debug(f"🔍 {self.symbol} достаточно данных: {sufficient} (есть {len(self.prices)}, нужно {min_data_points})")
        return sufficient
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику обновлений"""
        uptime = None
        if self.stats["first_update"]:
            uptime = (datetime.now() - self.stats["first_update"]).total_seconds()
        
        return {
            **self.stats,
            "symbol": self.symbol,
            "data_points": len(self.prices),
            "volume_points": len(self.volumes),
            "timestamp_points": len(self.timestamps),
            "has_data": bool(self.current_data),
            "uptime_seconds": uptime,
            "current_price": self.get_current_price(),
            "current_volume": self.get_volume()
        }


class YFinanceWebSocketProvider:
    """
    Провайдер WebSocket данных от yfinance для фьючерсов CME
    
    Особенности:
    - Поддержка множественных символов одновременно
    - Асинхронная архитектура
    - Thread-safe callbacks
    - Детальная статистика и мониторинг
    - Graceful shutdown
    """
    
    def __init__(self, symbols: List[str] = None, verbose: bool = True):
        """
        Инициализация YFinance WebSocket провайдера
        
        Args:
            symbols: Список символов фьючерсов (по умолчанию MCL, MGC, MES, MNQ)
            verbose: Детальное логирование
        """
        # Символы по умолчанию - фьючерсы CME
        self.symbols = symbols or ["MCL", "MGC", "MES", "MNQ"]
        self.verbose = verbose
        
        # ✅ ИСПРАВЛЕНИЕ 2: Сохраняем символы БЕЗ суффикса для внутреннего использования
        self.symbols_base = self.symbols.copy()
        
        # Добавляем суффикс =F для WebSocket подписки
        self.symbols_ws = [f"{symbol}=F" if not symbol.endswith('=F') else symbol 
                          for symbol in self.symbols]
        
        logger.info(f"📊 Базовые символы: {self.symbols_base}")
        logger.info(f"📊 WebSocket символы: {self.symbols_ws}")
        
        # Хранилища данных для каждого символа (используем базовые символы)
        self.futures_data: Dict[str, RealtimeFuturesData] = {}
        for symbol in self.symbols_base:
            self.futures_data[symbol] = RealtimeFuturesData(symbol)
        
        # WebSocket клиент
        self.ws_client = None
        self.running = False
        self.connection_ready = asyncio.Event()
        
        # Callback функции для уведомления подписчиков
        self.data_callbacks: List[Callable] = []
        
        # Время последнего summary лога
        self.last_summary_log = None
        
        # Статистика подключения
        self.connection_stats = {
            "connection_attempts": 0,
            "successful_connections": 0,
            "connection_failures": 0,
            "messages_received": 0,
            "messages_by_symbol": {symbol: 0 for symbol in self.symbols_base},
            "unknown_messages": 0,
            "error_messages": 0,
            "last_message_time": None,
            "start_time": None
        }
        
        logger.info(f"🔌 YFinanceWebSocketProvider инициализирован: {', '.join(self.symbols_base)}")
    
    def add_data_callback(self, callback: Callable[[str, dict], None]):
        """
        Добавляет callback для обновлений данных
        
        Args:
            callback: Функция с сигнатурой callback(symbol: str, data: dict)
        """
        self.data_callbacks.append(callback)
        logger.info(f"📝 Добавлен data callback ({len(self.data_callbacks)} всего)")
    
    async def start(self):
        """Запускает WebSocket подключение"""
        try:
            self.connection_stats["connection_attempts"] += 1
            self.connection_stats["start_time"] = datetime.now()
            
            logger.info(f"🚀 Запуск YFinance WebSocket провайдера...")
            logger.info(f"🔧 Символы: {', '.join(self.symbols_base)}")
            
            # Импортируем yfinance
            try:
                import yfinance as yf
                logger.info("✅ yfinance library загружена")
            except ImportError as e:
                logger.error("❌ yfinance не установлен! Установите: pip install yfinance")
                raise ImportError("yfinance library required. Install with: pip install yfinance") from e
            
            # ✅ ИСПРАВЛЕНИЕ 1: Правильный порядок операций
            # Создаем WebSocket клиент
            logger.info("🔗 Создание yfinance AsyncWebSocket соединения...")
            self.ws_client = yf.AsyncWebSocket(verbose=self.verbose)
            
            # Добавляем символы с суффиксом =F для фьючерсов
            symbols_with_suffix = [f"{symbol}=F" if not symbol.endswith('=F') else symbol 
                                  for symbol in self.symbols_base]
            logger.info(f"📊 Символы для подписки: {symbols_with_suffix}")
            
            # СНАЧАЛА подписываемся на символы
            logger.info(f"📊 Подписка на символы...")
            await self.ws_client.subscribe(symbols_with_suffix)
            
            # Даем время на обработку подписки
            await asyncio.sleep(2)
            
            # ПОТОМ запускаем прослушивание
            logger.info("📡 Запуск прослушивания WebSocket...")
            asyncio.create_task(self.ws_client.listen(self._handle_message))
            
            # Даем время на установку соединения и получение данных
            await asyncio.sleep(3)
            
            self.running = True
            self.connection_ready.set()
            self.connection_stats["successful_connections"] += 1
            
            logger.info(f"✅ YFinance WebSocket провайдер запущен")
            logger.info(f"📞 Registered callbacks: {len(self.data_callbacks)}")
            
        except Exception as e:
            self.connection_stats["connection_failures"] += 1
            logger.error(f"💥 Ошибка запуска YFinance WebSocket провайдера: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            self.running = False
            raise
    
    def _handle_message(self, message: dict):
        """
        Внутренний обработчик сообщений от WebSocket
        
        Args:
            message: Сообщение от yfinance WebSocket
        """
        try:
            self.connection_stats["messages_received"] += 1
            self.connection_stats["last_message_time"] = datetime.now()
            
            logger.debug(f"📨 Получено сообщение: {json.dumps(message, indent=2)}")
            
            # ✅ ИСПРАВЛЕНИЕ 3: Правильная обработка символов с =F
            # Извлекаем символ из сообщения
            symbol_raw = message.get('id') or message.get('symbol')
            
            if not symbol_raw:
                logger.warning(f"⚠️ Сообщение без символа: {message}")
                self.connection_stats["unknown_messages"] += 1
                return
            
            # Убираем суффикс =F если есть для внутренней обработки
            symbol = symbol_raw.replace('=F', '')
            
            # Проверяем что это наш символ (БЕЗ суффикса)
            if symbol not in self.symbols_base:
                logger.debug(f"🔍 Игнорируем символ {symbol_raw} (не в подписке)")
                return
            
            logger.debug(f"📨 Обработка данных для {symbol} (raw: {symbol_raw})")
            
            self.connection_stats["messages_by_symbol"][symbol] += 1
            
            # Периодическое логирование раз в минуту
            if self.last_summary_log is None or (datetime.now() - self.last_summary_log).total_seconds() > 60:
                total_msgs = sum(self.connection_stats["messages_by_symbol"].values())
                logger.info(f"📊 WebSocket активен: {total_msgs} сообщений получено")
                for sym in self.symbols_base:
                    count = self.connection_stats["messages_by_symbol"][sym]
                    logger.info(f"   • {sym}: {count} сообщений")
                self.last_summary_log = datetime.now()
            
            # Обновляем данные
            self.futures_data[symbol].update(message)
            
            # Уведомляем подписчиков
            logger.debug(f"📞 Вызов {len(self.data_callbacks)} callbacks для {symbol}...")
            for i, callback in enumerate(self.data_callbacks):
                try:
                    logger.debug(f"📞 Вызов callback #{i} для {symbol}")
                    callback(symbol, message)
                    logger.debug(f"✅ Callback #{i} выполнен для {symbol}")
                except Exception as e:
                    logger.error(f"❌ Ошибка в callback #{i} для {symbol}: {e}")
                    logger.error(f"Stack trace: {traceback.format_exc()}")
            
        except Exception as e:
            self.connection_stats["error_messages"] += 1
            logger.error(f"❌ Ошибка обработки сообщения: {e}")
            logger.error(f"Raw message: {message}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
    
    def get_futures_data(self, symbol: str) -> Optional[RealtimeFuturesData]:
        """
        Возвращает объект с данными фьючерса
        
        Args:
            symbol: Символ фьючерса
            
        Returns:
            RealtimeFuturesData или None
        """
        return self.futures_data.get(symbol)
    
    def get_all_futures_data(self) -> Dict[str, RealtimeFuturesData]:
        """Возвращает все объекты с данными фьючерсов"""
        return self.futures_data
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Возвращает текущую статистику по всем фьючерсам"""
        try:
            stats = {
                "symbols": self.symbols_base,
                "data_by_symbol": {},
                "connection_stats": self.connection_stats.copy(),
                "last_update": datetime.now().isoformat()
            }
            
            for symbol in self.symbols_base:
                futures = self.futures_data[symbol]
                stats["data_by_symbol"][symbol] = {
                    "current_price": futures.get_current_price(),
                    "price_change_1m": futures.get_price_change(1),
                    "price_change_5m": futures.get_price_change(5),
                    "volume": futures.get_volume(),
                    "data_points": len(futures.prices),
                    "has_sufficient_data": futures.has_sufficient_data(),
                    "stats": futures.get_stats()
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {
                "symbols": self.symbols_base,
                "error": str(e)
            }
    
    def is_running(self) -> bool:
        """✅ ИСПРАВЛЕНИЕ 4: Проверяет, работает ли провайдер с реальными проверками"""
        if not self.running:
            return False
        
        # Проверяем что WebSocket клиент существует
        if not self.ws_client:
            logger.warning("⚠️ WebSocket клиент не инициализирован")
            return False
        
        # Проверяем здоровье соединения
        return self.is_connection_healthy()
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Возвращает детальную статистику подключения"""
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
        
        # Проверяем получение сообщений за последние 5 минут
        if self.connection_stats["last_message_time"]:
            time_since_last = datetime.now() - self.connection_stats["last_message_time"]
            if time_since_last > timedelta(minutes=5):
                logger.warning(f"⚠️ Нет сообщений {time_since_last.total_seconds():.0f} секунд")
                return False
        
        return True
    
    async def stop(self):
        """Останавливает WebSocket подключение"""
        try:
            logger.info("🔄 Остановка YFinance WebSocket провайдера...")
            self.running = False
            
            if self.ws_client:
                # ✅ ИСПРАВЛЕНИЕ 5: Отписываемся от символов с суффиксом =F
                logger.info(f"📡 Отписка от символов: {', '.join(self.symbols_ws)}")
                try:
                    await self.ws_client.unsubscribe(self.symbols_ws)
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка отписки от символов: {e}")
                
                # Закрываем соединение
                logger.info("🔌 Закрытие WebSocket соединения...")
                try:
                    await self.ws_client.close()
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка закрытия соединения: {e}")
            
            # Логируем финальную статистику
            final_stats = self.get_connection_stats()
            logger.info(f"📊 Финальная статистика YFinance WebSocket:")
            logger.info(f"   • Попыток подключения: {final_stats['connection_attempts']}")
            logger.info(f"   • Успешных подключений: {final_stats['successful_connections']}")
            logger.info(f"   • Сообщений получено: {final_stats['messages_received']}")
            
            for symbol in self.symbols_base:
                count = final_stats['messages_by_symbol'][symbol]
                futures = self.futures_data[symbol]
                logger.info(f"   • {symbol}: {count} сообщений, {len(futures.prices)} точек данных")
            
            logger.info(f"   • Время работы: {final_stats['uptime_seconds']:.0f} сек")
            logger.info(f"🛑 YFinance WebSocket провайдер остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки YFinance WebSocket провайдера: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
    
    async def wait_for_data(self, timeout: int = 60) -> bool:
        """
        Ожидает получения достаточного количества данных для всех символов
        
        Args:
            timeout: Таймаут ожидания в секундах
            
        Returns:
            True если данные получены, False если таймаут
        """
        start_time = datetime.now()
        logger.info(f"⏳ Ожидание данных для {len(self.symbols_base)} символов (таймаут: {timeout}с)...")
        
        check_interval = 2  # Проверяем каждые 2 секунды
        
        while (datetime.now() - start_time).seconds < timeout:
            # Проверяем наличие данных для всех символов
            all_have_data = True
            for symbol in self.symbols_base:
                futures = self.futures_data[symbol]
                if not futures.has_sufficient_data(min_data_points=5):
                    all_have_data = False
                    break
            
            messages_received = self.connection_stats["messages_received"]
            
            logger.debug(f"📊 Проверка данных: all_have_data={all_have_data}, messages={messages_received}")
            
            if all_have_data and messages_received > 0:
                logger.info(f"✅ Данные получены за {(datetime.now() - start_time).seconds}с")
                # Показываем статистику по каждому символу
                for symbol in self.symbols_base:
                    futures = self.futures_data[symbol]
                    logger.info(f"   • {symbol}: {len(futures.prices)} точек, цена ${futures.get_current_price():,.2f}")
                return True
            
            await asyncio.sleep(check_interval)
        
        logger.warning(f"⏰ Таймаут ожидания данных ({timeout}с)")
        logger.warning(f"📊 Итоговая статистика:")
        logger.warning(f"   • Сообщений получено: {self.connection_stats['messages_received']}")
        for symbol in self.symbols_base:
            futures = self.futures_data[symbol]
            msgs = self.connection_stats['messages_by_symbol'][symbol]
            logger.warning(f"   • {symbol}: {msgs} сообщений, {len(futures.prices)} точек, достаточно={futures.has_sufficient_data()}")
        
        return False
    
    def __str__(self):
        """Строковое представление провайдера"""
        status = "Running" if self.running else "Stopped"
        messages = self.connection_stats["messages_received"]
        return f"YFinanceWebSocketProvider(symbols={self.symbols_base}, status={status}, messages={messages})"
    
    def __repr__(self):
        """Подробное представление для отладки"""
        return (f"YFinanceWebSocketProvider(symbols={self.symbols_base}, "
                f"running={self.running}, callbacks={len(self.data_callbacks)}, "
                f"messages={self.connection_stats['messages_received']})")


# Export main components
__all__ = [
    "RealtimeFuturesData",
    "YFinanceWebSocketProvider"
]

logger.info("YFinance WebSocket provider module loaded successfully")
