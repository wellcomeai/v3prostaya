"""
Data Source Adapter

Адаптер между SimpleCandleSync/SimpleFuturesSync и StrategyOrchestrator.
Преобразует данные из базы данных в формат MarketDataSnapshot для стратегий.

Author: Trading Bot Team  
Version: 1.0.3 - Fixed: Priority to fresh M1 candles
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Callable
from decimal import Decimal

from market_data import MarketDataSnapshot, DataQuality
from market_data.market_data_manager import DataSourceType

logger = logging.getLogger(__name__)


class DataSourceAdapter:
    """
    🔌 Адаптер источников данных для StrategyOrchestrator
    
    Преобразует данные из:
    - SimpleCandleSync (криптовалюты Bybit)
    - SimpleFuturesSync (фьючерсы YFinance)  
    - TechnicalAnalysisContextManager (технический анализ)
    
    В формат MarketDataSnapshot для стратегий.
    
    Основные функции:
    1. Получение актуальных рыночных данных
    2. Создание MarketDataSnapshot из свечей
    3. Подписка на обновления данных
    4. Мониторинг качества данных
    
    Usage:
        adapter = DataSourceAdapter(
            ta_context_manager=ta_context,
            simple_candle_sync=candle_sync,
            simple_futures_sync=futures_sync
        )
        
        snapshot = await adapter.get_market_snapshot("BTCUSDT")
    """
    
    def __init__(
        self,
        ta_context_manager,  # TechnicalAnalysisContextManager
        simple_candle_sync=None,  # SimpleCandleSync (опционально)
        simple_futures_sync=None,  # SimpleFuturesSync (опционально)
        default_symbols: Optional[List[str]] = None
    ):
        """
        Инициализация адаптера
        
        Args:
            ta_context_manager: Менеджер технического анализа
            simple_candle_sync: Синхронизатор криптовалют (Bybit)
            simple_futures_sync: Синхронизатор фьючерсов (YFinance)
            default_symbols: Список символов по умолчанию
        """
        self.ta_context_manager = ta_context_manager
        self.simple_candle_sync = simple_candle_sync
        self.simple_futures_sync = simple_futures_sync
        
        # Определяем доступные символы
        self.crypto_symbols = []
        self.futures_symbols = []
        
        if simple_candle_sync:
            self.crypto_symbols = simple_candle_sync.symbols
        
        if simple_futures_sync:
            self.futures_symbols = simple_futures_sync.symbols
        
        self.all_symbols = self.crypto_symbols + self.futures_symbols
        
        if not self.all_symbols and default_symbols:
            self.all_symbols = default_symbols
        
        # Подписчики на обновления данных
        self.data_subscribers: Set[Callable] = set()
        
        # Кэш последних снимков
        self.last_snapshots: Dict[str, MarketDataSnapshot] = {}
        
        # Статистика
        self.stats = {
            "snapshots_created": 0,
            "snapshots_cached": 0,
            "updates_sent": 0,
            "errors": 0,
            "start_time": datetime.now(),
            "last_update_time": None
        }
        
        # Флаг работы
        self.is_running = False
        self._update_task: Optional[asyncio.Task] = None
        
        logger.info("🔌 DataSourceAdapter инициализирован")
        logger.info(f"   • Криптовалюты: {len(self.crypto_symbols)}")
        logger.info(f"   • Фьючерсы: {len(self.futures_symbols)}")
        logger.info(f"   • Всего символов: {len(self.all_symbols)}")
    
    # ==================== ОСНОВНЫЕ МЕТОДЫ ====================
    
    async def get_market_snapshot(self, symbol: str = None) -> Optional[MarketDataSnapshot]:
        """
        Получить актуальный снимок рынка
        
        Args:
            symbol: Торговый символ (если None - берется первый доступный)
            
        Returns:
            MarketDataSnapshot или None при ошибке
        """
        try:
            # Если символ не указан - берем первый
            if not symbol:
                if not self.all_symbols:
                    logger.error("❌ Нет доступных символов")
                    return None
                symbol = self.all_symbols[0]
            
            symbol = symbol.upper()
            
            # Проверяем кэш (если данные свежие - используем кэш)
            if symbol in self.last_snapshots:
                cached_snapshot = self.last_snapshots[symbol]
                age = (datetime.now() - cached_snapshot.timestamp).total_seconds()
                
                if age < 60:  # Кэш валиден 60 секунд
                    self.stats["snapshots_cached"] += 1
                    return cached_snapshot
            
            # Создаем новый снимок
            snapshot = await self._create_snapshot(symbol)
            
            if snapshot:
                # Сохраняем в кэш
                self.last_snapshots[symbol] = snapshot
                self.stats["snapshots_created"] += 1
                
                logger.debug(f"📸 Snapshot создан для {symbol}: ${snapshot.current_price:.2f}")
            
            return snapshot
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания snapshot для {symbol}: {e}")
            self.stats["errors"] += 1
            return None
    
    async def _create_snapshot(self, symbol: str) -> Optional[MarketDataSnapshot]:
        """
        Создать MarketDataSnapshot из данных технического анализа
        
        ✅ ИСПРАВЛЕНО v1.0.3: Приоритет самым свежим данным (M1 → M5 → H1 → D1)
        
        Args:
            symbol: Торговый символ
            
        Returns:
            MarketDataSnapshot с заполненными данными
        """
        try:
            # Получаем контекст технического анализа
            context = await self.ta_context_manager.get_context(symbol)
            
            # ✅ НОВАЯ ЛОГИКА: Берем самую свежую свечу (приоритет короткому интервалу)
            latest_candle = None
            candle_interval = None
            
            # 1️⃣ Пробуем M1 (САМЫЕ СВЕЖИЕ - обновляются каждую минуту!)
            if context.recent_candles_m1 and len(context.recent_candles_m1) > 0:
                latest_candle = context.recent_candles_m1[-1]
                candle_interval = "1m"
                logger.debug(f"✅ {symbol}: Используем M1 свечу (самые свежие данные)")
            
            # 2️⃣ Если нет M1 - пробуем M5
            elif context.recent_candles_m5 and len(context.recent_candles_m5) > 0:
                latest_candle = context.recent_candles_m5[-1]
                candle_interval = "5m"
                logger.debug(f"⚠️ {symbol}: M1 нет, используем M5 свечу")
            
            # 3️⃣ Если нет M5 - пробуем H1
            elif context.recent_candles_h1 and len(context.recent_candles_h1) > 0:
                latest_candle = context.recent_candles_h1[-1]
                candle_interval = "1h"
                logger.warning(f"⚠️ {symbol}: M1 и M5 нет, используем H1 свечу (СТАРЫЕ ДАННЫЕ!)")
            
            # 4️⃣ Если нет H1 - пробуем D1
            elif context.recent_candles_d1 and len(context.recent_candles_d1) > 0:
                latest_candle = context.recent_candles_d1[-1]
                candle_interval = "1d"
                logger.error(f"❌ {symbol}: Только D1 свечи - ОЧЕНЬ СТАРЫЕ ДАННЫЕ!")
            
            # Если вообще нет данных - ошибка
            if not latest_candle:
                logger.error(f"❌ {symbol}: Нет свечей для создания snapshot")
                return None
            
            # Извлекаем текущую цену
            current_price = float(latest_candle['close_price'])
            
            # Логируем источник данных
            candle_time = latest_candle.get('open_time', 'unknown')
            logger.info(f"📊 {symbol}: ${current_price:,.2f} (из {candle_interval} свечи, время: {candle_time})")
            
            # Рассчитываем изменения цены
            price_changes = self._calculate_price_changes(context, current_price)
            
            # Рассчитываем объем 24ч из D1 свечей
            volume_24h = self._calculate_volume_24h(context)
            
            # Рассчитываем high/low 24h из D1 свечей
            high_24h, low_24h = self._calculate_high_low_24h(context, current_price)
            
            # Определяем качество данных
            data_quality_obj = self._assess_data_quality(context)
            
            # Конвертируем DataQuality в словарь
            data_quality_dict = self._data_quality_to_dict(data_quality_obj)
            
            # Создаем snapshot с правильными параметрами
            snapshot = MarketDataSnapshot(
                symbol=symbol,
                timestamp=datetime.now(),
                
                # Цена и изменения
                current_price=current_price,
                price_change_1m=price_changes.get("1m", 0.0),
                price_change_5m=price_changes.get("5m", 0.0),
                price_change_24h=price_changes.get("24h", 0.0),
                
                # Объем и диапазон
                volume_24h=volume_24h,
                high_24h=high_24h,
                low_24h=low_24h,
                
                # Обязательные поля (нет данных - ставим 0)
                bid_price=0.0,
                ask_price=0.0,
                spread=0.0,
                open_interest=0.0,
                
                # Качество данных
                data_quality=data_quality_dict,
                
                # Источник данных
                data_source=DataSourceType.REST_API,
                
                # Флаги данных
                has_realtime_data=False,
                has_historical_data=True
            )
            
            return snapshot
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания snapshot: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _calculate_price_changes(self, context, current_price: float) -> Dict[str, float]:
        """
        Рассчитать изменения цены за разные периоды
        
        Args:
            context: TechnicalAnalysisContext
            current_price: Текущая цена
            
        Returns:
            Словарь с изменениями {период: изменение_%}
        """
        changes = {}
        
        try:
            # 1 минута (из M1 свечей - если есть)
            if hasattr(context, 'recent_candles_m1') and len(context.recent_candles_m1) >= 2:
                price_1m_ago = float(context.recent_candles_m1[-2]['close_price'])
                changes["1m"] = ((current_price - price_1m_ago) / price_1m_ago * 100)
            # Fallback на M5
            elif len(context.recent_candles_m5) >= 1:
                price_1m_ago = float(context.recent_candles_m5[-1]['open_price'])
                changes["1m"] = ((current_price - price_1m_ago) / price_1m_ago * 100)
            
            # 5 минут (из M5 свечей)
            if len(context.recent_candles_m5) >= 2:
                price_5m_ago = float(context.recent_candles_m5[-2]['open_price'])
                changes["5m"] = ((current_price - price_5m_ago) / price_5m_ago * 100)
            
            # 24 часа (из D1 свечей)
            if len(context.recent_candles_d1) >= 2:
                price_24h_ago = float(context.recent_candles_d1[-2]['close_price'])
                changes["24h"] = ((current_price - price_24h_ago) / price_24h_ago * 100)
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета изменений цены: {e}")
        
        return changes
    
    def _calculate_volume_24h(self, context) -> float:
        """
        Рассчитать объем за 24 часа
        
        Args:
            context: TechnicalAnalysisContext
            
        Returns:
            Объем за 24ч
        """
        try:
            # Суммируем объем из последних 24 H1 свечей
            if len(context.recent_candles_h1) >= 24:
                volume_24h = sum(
                    float(candle['volume']) 
                    for candle in context.recent_candles_h1[-24:]
                )
                return volume_24h
            
            # Если нет 24 H1 свечей - берем из D1
            if context.recent_candles_d1:
                return float(context.recent_candles_d1[-1]['volume'])
            
            return 0.0
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета объема: {e}")
            return 0.0
    
    def _calculate_high_low_24h(self, context, current_price: float) -> tuple[float, float]:
        """
        Рассчитать максимум и минимум за 24 часа
        
        Args:
            context: TechnicalAnalysisContext
            current_price: Текущая цена
            
        Returns:
            Tuple[high_24h, low_24h]
        """
        try:
            # Пробуем из последних 24 H1 свечей
            if len(context.recent_candles_h1) >= 24:
                recent_24h = context.recent_candles_h1[-24:]
                high_24h = max(float(candle['high_price']) for candle in recent_24h)
                low_24h = min(float(candle['low_price']) for candle in recent_24h)
                return high_24h, low_24h
            
            # Если нет 24 H1 свечей - берем из последней D1 свечи
            if context.recent_candles_d1:
                last_d1 = context.recent_candles_d1[-1]
                high_24h = float(last_d1['high_price'])
                low_24h = float(last_d1['low_price'])
                return high_24h, low_24h
            
            # Если вообще нет данных - возвращаем текущую цену
            return current_price, current_price
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета high/low: {e}")
            return current_price, current_price
    
    def _assess_data_quality(self, context) -> DataQuality:
        """
        Оценить качество данных
        
        Args:
            context: TechnicalAnalysisContext
            
        Returns:
            DataQuality объект
        """
        try:
            # Проверяем наличие данных по таймфреймам
            has_m1 = hasattr(context, 'recent_candles_m1') and len(context.recent_candles_m1) >= 10
            has_m5 = len(context.recent_candles_m5) >= 10
            has_h1 = len(context.recent_candles_h1) >= 10
            has_d1 = len(context.recent_candles_d1) >= 5
            
            has_levels = len(context.levels_d1) > 0
            has_atr = context.atr_data is not None
            
            # Проверяем свежесть данных
            data_fresh = True
            if context.candles_updated_at:
                age = (datetime.now() - context.candles_updated_at.replace(tzinfo=None)).total_seconds()
                data_fresh = age < 120  # Данные не старше 2 минут
            
            # Определяем overall качество
            quality_score = 0
            if has_m1: quality_score += 25  # M1 самые важные!
            if has_m5: quality_score += 20
            if has_h1: quality_score += 15
            if has_d1: quality_score += 10
            if has_levels: quality_score += 15
            if has_atr: quality_score += 10
            if data_fresh: quality_score += 5
            
            if quality_score >= 90:
                overall = "excellent"
            elif quality_score >= 70:
                overall = "good"
            elif quality_score >= 50:
                overall = "fair"
            else:
                overall = "poor"
            
            return DataQuality(
                bybit_rest_api=data_fresh,
                bybit_websocket=False,  # Не используем WebSocket
                yfinance_websocket=False,
                overall_quality=overall,
                data_completeness=quality_score / 100.0,
                last_update=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка оценки качества данных: {e}")
            return DataQuality(
                bybit_rest_api=False,
                bybit_websocket=False,
                yfinance_websocket=False,
                overall_quality="poor",
                data_completeness=0.0,
                last_update=datetime.now()
            )
    
    def _data_quality_to_dict(self, data_quality: DataQuality) -> Dict[str, Any]:
        """
        Конвертировать DataQuality объект в словарь
        
        Args:
            data_quality: DataQuality объект
            
        Returns:
            Словарь с данными о качестве
        """
        return {
            "bybit_rest_api": data_quality.bybit_rest_api,
            "bybit_websocket": data_quality.bybit_websocket,
            "yfinance_websocket": data_quality.yfinance_websocket,
            "overall_quality": data_quality.overall_quality,
            "data_completeness": data_quality.data_completeness,
            "last_update": data_quality.last_update.isoformat() if data_quality.last_update else None
        }
    
    # ==================== ПОДПИСКИ НА ОБНОВЛЕНИЯ ====================
    
    def add_data_subscriber(self, callback: Callable):
        """
        Добавить подписчика на обновления данных
        
        Args:
            callback: Функция для вызова при обновлении (принимает MarketDataSnapshot)
        """
        self.data_subscribers.add(callback)
        logger.info(f"📝 Добавлен подписчик на обновления ({len(self.data_subscribers)} всего)")
    
    def remove_data_subscriber(self, callback: Callable):
        """Удалить подписчика"""
        self.data_subscribers.discard(callback)
        logger.info(f"🗑️ Удален подписчик ({len(self.data_subscribers)} осталось)")
    
    async def _notify_subscribers(self, snapshot: MarketDataSnapshot):
        """
        Уведомить всех подписчиков о новых данных
        
        Args:
            snapshot: MarketDataSnapshot для отправки
        """
        try:
            if not self.data_subscribers:
                return
            
            for subscriber in self.data_subscribers.copy():
                try:
                    if asyncio.iscoroutinefunction(subscriber):
                        await subscriber(snapshot)
                    else:
                        subscriber(snapshot)
                    
                    self.stats["updates_sent"] += 1
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка уведомления подписчика: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка в _notify_subscribers: {e}")
    
    # ==================== ФОНОВЫЕ ОБНОВЛЕНИЯ ====================
    
    async def start_updates(self, update_interval: float = 60.0):
        """
        Запустить фоновые обновления данных
        
        Args:
            update_interval: Интервал обновления в секундах (по умолчанию 60с)
        """
        if self.is_running:
            logger.warning("⚠️ Обновления уже запущены")
            return
        
        logger.info(f"🚀 Запуск фоновых обновлений (интервал: {update_interval}с)")
        
        self.is_running = True
        self._update_task = asyncio.create_task(
            self._update_loop(update_interval)
        )
        
        logger.info("✅ Фоновые обновления запущены")
    
    async def stop_updates(self):
        """Остановить фоновые обновления"""
        if not self.is_running:
            logger.warning("⚠️ Обновления уже остановлены")
            return
        
        logger.info("🛑 Остановка фоновых обновлений...")
        
        self.is_running = False
        
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ Фоновые обновления остановлены")
    
    async def _update_loop(self, interval: float):
        """
        Цикл фоновых обновлений
        
        Args:
            interval: Интервал обновления в секундах
        """
        logger.info("🔄 Запущен цикл обновлений данных")
        
        while self.is_running:
            try:
                # Обновляем данные для всех символов
                for symbol in self.all_symbols:
                    try:
                        # Создаем snapshot
                        snapshot = await self.get_market_snapshot(symbol)
                        
                        if snapshot:
                            # Уведомляем подписчиков
                            await self._notify_subscribers(snapshot)
                            
                    except Exception as e:
                        logger.error(f"❌ Ошибка обновления {symbol}: {e}")
                
                self.stats["last_update_time"] = datetime.now()
                
                # Ждем до следующего обновления
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                logger.info("🛑 Цикл обновлений отменен")
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в цикле обновлений: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await asyncio.sleep(interval)
        
        logger.info("🛑 Цикл обновлений остановлен")
    
    # ==================== СТАТИСТИКА ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику адаптера"""
        uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
        
        return {
            **self.stats,
            "uptime_seconds": uptime,
            "uptime_formatted": str(timedelta(seconds=int(uptime))),
            "is_running": self.is_running,
            "subscribers_count": len(self.data_subscribers),
            "crypto_symbols": len(self.crypto_symbols),
            "futures_symbols": len(self.futures_symbols),
            "total_symbols": len(self.all_symbols),
            "cached_snapshots": len(self.last_snapshots),
            "snapshots_per_minute": round(
                self.stats["snapshots_created"] / (uptime / 60), 2
            ) if uptime > 0 else 0
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Проверка здоровья адаптера"""
        stats = self.get_stats()
        
        # Проверяем что есть данные
        has_data = len(self.last_snapshots) > 0
        
        # Проверяем свежесть последнего обновления
        last_update_recent = False
        if self.stats["last_update_time"]:
            age = (datetime.now() - self.stats["last_update_time"]).total_seconds()
            last_update_recent = age < 120  # < 2 минут
        
        # Проверяем что нет слишком много ошибок
        error_rate = (self.stats["errors"] / max(self.stats["snapshots_created"], 1)) * 100
        low_error_rate = error_rate < 10  # Менее 10% ошибок
        
        is_healthy = (
            has_data and
            (last_update_recent or stats["snapshots_created"] == 0) and
            low_error_rate and
            len(self.all_symbols) > 0
        )
        
        return {
            "healthy": is_healthy,
            "is_running": self.is_running,
            "has_data": has_data,
            "last_update_recent": last_update_recent,
            "error_rate": round(error_rate, 2),
            "symbols_available": len(self.all_symbols),
            "subscribers": len(self.data_subscribers),
            "uptime_seconds": stats["uptime_seconds"]
        }
    
    def __str__(self):
        """Строковое представление"""
        return (f"DataSourceAdapter(symbols={len(self.all_symbols)}, "
                f"crypto={len(self.crypto_symbols)}, "
                f"futures={len(self.futures_symbols)}, "
                f"running={self.is_running}, "
                f"subscribers={len(self.data_subscribers)})")
    
    def __repr__(self):
        """Подробное представление"""
        return (f"DataSourceAdapter(crypto_symbols={len(self.crypto_symbols)}, "
                f"futures_symbols={len(self.futures_symbols)}, "
                f"snapshots_created={self.stats['snapshots_created']}, "
                f"is_running={self.is_running})")


# Export
__all__ = ["DataSourceAdapter"]

logger.info("✅ Data Source Adapter module loaded (v1.0.3 - Fresh data priority)")
