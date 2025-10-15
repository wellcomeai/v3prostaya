"""
Technical Analysis Context Manager

Управляет кэшированием и автоматическим обновлением технического анализа.
Обновляет данные в фоновом режиме по расписанию:
- Уровни D1: каждые 24 часа
- ATR: каждый час  
- Свечи: каждую минуту

Author: Trading Bot Team
Version: 1.0.0
"""

import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Any
from collections import defaultdict

from .context import (
    TechnicalAnalysisContext,
    SupportResistanceLevel,
    ATRData,
    MarketCondition,
    TrendDirection
)

logger = logging.getLogger(__name__)


class TechnicalAnalysisContextManager:
    """
    🧠 Менеджер контекстов технического анализа
    
    Централизованное управление техническим анализом для всех символов:
    - Кэширование данных с автоматическим обновлением
    - Фоновые задачи обновления по расписанию
    - Ленивая инициализация (контексты создаются по запросу)
    - Интеграция с MarketDataRepository
    - Мониторинг и статистика
    
    Расписание обновлений:
    - Уровни D1: раз в 24 часа (в 00:00 UTC)
    - ATR: раз в час
    - Свечи: каждую минуту
    
    Usage:
        manager = TechnicalAnalysisContextManager(repository, level_analyzer, atr_calculator)
        await manager.start()
        
        context = await manager.get_context("BTCUSDT")
        levels = context.levels_d1
    """
    
    def __init__(
        self,
        repository,  # MarketDataRepository
        level_analyzer=None,  # LevelAnalyzer (будет создан позже)
        atr_calculator=None,  # ATRCalculator (будет создан позже)
        auto_start_background_updates: bool = True
    ):
        """
        Инициализация менеджера
        
        Args:
            repository: MarketDataRepository для доступа к БД
            level_analyzer: Анализатор уровней (опционально)
            atr_calculator: Калькулятор ATR (опционально)
            auto_start_background_updates: Автоматически запускать фоновые обновления
        """
        self.repository = repository
        self.level_analyzer = level_analyzer
        self.atr_calculator = atr_calculator
        self.auto_start = auto_start_background_updates
        
        # Кэш контекстов для каждого символа
        self.contexts: Dict[str, TechnicalAnalysisContext] = {}
        
        # Фоновые задачи обновления
        self._update_tasks: List[asyncio.Task] = []
        self.is_running = False
        
        # Статистика
        self.stats = {
            "start_time": None,
            "contexts_created": 0,
            "total_updates": 0,
            "successful_updates": 0,
            "failed_updates": 0,
            "levels_updates": 0,
            "atr_updates": 0,
            "candles_updates": 0,
            "last_update_time": None,
            "update_times": defaultdict(list),  # Время обновления по типу
            "errors_by_type": defaultdict(int)
        }
        
        logger.info("🏗️ TechnicalAnalysisContextManager инициализирован")
        logger.info(f"   • Auto-start background updates: {auto_start}")
    
    # ==================== ОСНОВНЫЕ МЕТОДЫ ====================
    
    async def get_context(
        self, 
        symbol: str, 
        force_update: bool = False,
        data_source: str = "bybit"
    ) -> TechnicalAnalysisContext:
        """
        Получить контекст технического анализа для символа
        
        Если контекст не существует - создается новый.
        Если кэш устарел - обновляется автоматически.
        
        Args:
            symbol: Торговый символ (BTCUSDT, ETHUSDT, etc.)
            force_update: Принудительно обновить все данные
            data_source: Источник данных (bybit, yfinance)
            
        Returns:
            TechnicalAnalysisContext с актуальными данными
        """
        try:
            symbol = symbol.upper()
            
            # Создаем контекст если не существует
            if symbol not in self.contexts:
                logger.info(f"📝 Создание нового контекста для {symbol}")
                self.contexts[symbol] = TechnicalAnalysisContext(
                    symbol=symbol,
                    data_source=data_source
                )
                self.stats["contexts_created"] += 1
            
            context = self.contexts[symbol]
            
            # Обновляем если нужно
            if force_update:
                logger.info(f"🔄 Принудительное обновление контекста {symbol}")
                await self._full_update_context(context)
            else:
                await self._update_context_if_needed(context)
            
            return context
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения контекста для {symbol}: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def _update_context_if_needed(self, context: TechnicalAnalysisContext):
        """
        Обновить контекст если кэш устарел
        
        Проверяет валидность каждого типа данных и обновляет только устаревшие.
        """
        try:
            updates_needed = []
            
            # 1. Проверяем уровни D1
            if not context.is_levels_cache_valid():
                updates_needed.append("levels")
            
            # 2. Проверяем ATR
            if not context.is_atr_cache_valid():
                updates_needed.append("atr")
            
            # 3. Проверяем свечи
            if not context.is_candles_cache_valid():
                updates_needed.append("candles")
            
            # Обновляем только то, что нужно
            if updates_needed:
                logger.debug(f"🔄 Обновление {context.symbol}: {', '.join(updates_needed)}")
                
                if "levels" in updates_needed:
                    await self._update_levels(context)
                
                if "atr" in updates_needed:
                    await self._update_atr(context)
                
                if "candles" in updates_needed:
                    await self._update_candles(context)
                
                context.last_full_update = datetime.now(timezone.utc)
                context.update_count += 1
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления контекста {context.symbol}: {e}")
            context.error_count += 1
            context.last_error = str(e)
            raise
    
    async def _full_update_context(self, context: TechnicalAnalysisContext):
        """Полное обновление всех данных контекста"""
        try:
            logger.info(f"🔄 Полное обновление контекста {context.symbol}")
            start_time = datetime.now()
            
            # Обновляем все типы данных
            await self._update_levels(context)
            await self._update_atr(context)
            await self._update_candles(context)
            
            # Обновляем метаданные
            context.last_full_update = datetime.now(timezone.utc)
            context.update_count += 1
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"✅ Контекст {context.symbol} обновлен за {duration:.2f}s")
            
            self.stats["total_updates"] += 1
            self.stats["successful_updates"] += 1
            self.stats["last_update_time"] = datetime.now()
            
        except Exception as e:
            logger.error(f"❌ Ошибка полного обновления {context.symbol}: {e}")
            context.error_count += 1
            context.last_error = str(e)
            self.stats["failed_updates"] += 1
            raise
    
    # ==================== ОБНОВЛЕНИЕ УРОВНЕЙ ====================
    
    async def _update_levels(self, context: TechnicalAnalysisContext):
        """
        Обновить уровни поддержки/сопротивления D1
        
        Загружает 180 дней истории и анализирует уровни.
        """
        try:
            update_start = datetime.now()
            
            # Загружаем 180 свечей D1 (6 месяцев)
            candles_d1 = await self.repository.get_candles(
                symbol=context.symbol,
                interval="1d",
                limit=180
            )
            
            if not candles_d1:
                logger.warning(f"⚠️ Нет данных D1 для {context.symbol}")
                return
            
            logger.debug(f"📊 Загружено {len(candles_d1)} свечей D1 для {context.symbol}")
            
            # Сохраняем свечи D1 в контексте
            context.recent_candles_d1 = candles_d1
            
            # Анализируем уровни (пока заглушка, будет реализовано в level_analyzer)
            if self.level_analyzer:
                levels = self.level_analyzer.find_all_levels(candles_d1)
                context.levels_d1 = levels
                logger.info(f"✅ Найдено {len(levels)} уровней для {context.symbol}")
            else:
                # Временная заглушка - создаем простые уровни
                context.levels_d1 = self._create_dummy_levels(candles_d1)
                logger.debug(f"⚠️ LevelAnalyzer не подключен, используется заглушка")
            
            context.levels_updated_at = datetime.now(timezone.utc)
            
            self.stats["levels_updates"] += 1
            update_duration = (datetime.now() - update_start).total_seconds()
            self.stats["update_times"]["levels"].append(update_duration)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления уровней {context.symbol}: {e}")
            self.stats["errors_by_type"]["levels"] += 1
            raise
    
    def _create_dummy_levels(self, candles: List) -> List[SupportResistanceLevel]:
        """
        Временная заглушка для создания простых уровней
        
        Будет заменена на level_analyzer.find_all_levels()
        """
        if not candles or len(candles) < 20:
            return []
        
        levels = []
        
        # Берем последние 30 свечей
        recent_candles = candles[-30:]
        
        # Находим максимумы и минимумы
        highs = [float(c.high_price) for c in recent_candles]
        lows = [float(c.low_price) for c in recent_candles]
        
        # Сопротивление - максимум
        max_high = max(highs)
        levels.append(SupportResistanceLevel(
            price=max_high,
            level_type="resistance",
            strength=0.7,
            touches=1,
            last_touch=recent_candles[-1].close_time,
            metadata={"type": "dummy", "source": "max_high"}
        ))
        
        # Поддержка - минимум
        min_low = min(lows)
        levels.append(SupportResistanceLevel(
            price=min_low,
            level_type="support",
            strength=0.7,
            touches=1,
            last_touch=recent_candles[-1].close_time,
            metadata={"type": "dummy", "source": "min_low"}
        ))
        
        return levels
    
    # ==================== ОБНОВЛЕНИЕ ATR ====================
    
    async def _update_atr(self, context: TechnicalAnalysisContext):
        """
        Обновить данные ATR (Average True Range)
        
        Рассчитывает расчетный и технический ATR на основе последних 5 дней.
        """
        try:
            update_start = datetime.now()
            
            # Используем уже загруженные D1 свечи если есть
            if len(context.recent_candles_d1) >= 5:
                candles_for_atr = context.recent_candles_d1[-5:]
            else:
                # Загружаем 5 дней для ATR
                candles_for_atr = await self.repository.get_candles(
                    symbol=context.symbol,
                    interval="1d",
                    limit=5
                )
            
            if not candles_for_atr or len(candles_for_atr) < 3:
                logger.warning(f"⚠️ Недостаточно данных для ATR {context.symbol}")
                return
            
            # Рассчитываем ATR (пока заглушка, будет реализовано в atr_calculator)
            if self.atr_calculator:
                atr_result = self.atr_calculator.calculate_atr(candles_for_atr)
                
                context.atr_data = ATRData(
                    calculated_atr=atr_result["calculated_atr"],
                    technical_atr=atr_result["technical_atr"],
                    atr_percent=atr_result["atr_percent"],
                    current_range_used=atr_result.get("current_range_used", 0.0),
                    is_exhausted=atr_result.get("is_exhausted", False),
                    last_5_ranges=atr_result.get("last_5_ranges", []),
                    updated_at=datetime.now(timezone.utc)
                )
            else:
                # Временная заглушка - простой расчет
                atr_simple = self._calculate_simple_atr(candles_for_atr)
                context.atr_data = atr_simple
                logger.debug(f"⚠️ ATRCalculator не подключен, используется простой расчет")
            
            logger.debug(f"✅ ATR обновлен для {context.symbol}: {context.atr_data.calculated_atr:.2f}")
            
            self.stats["atr_updates"] += 1
            update_duration = (datetime.now() - update_start).total_seconds()
            self.stats["update_times"]["atr"].append(update_duration)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления ATR {context.symbol}: {e}")
            self.stats["errors_by_type"]["atr"] += 1
            raise
    
    def _calculate_simple_atr(self, candles: List) -> ATRData:
        """
        Простой расчет ATR (заглушка)
        
        Будет заменен на atr_calculator.calculate_atr()
        """
        if not candles:
            return ATRData(
                calculated_atr=0.0,
                technical_atr=0.0,
                atr_percent=0.0,
                updated_at=datetime.now(timezone.utc)
            )
        
        # Среднее High - Low за последние свечи
        ranges = [float(c.high_price - c.low_price) for c in candles]
        avg_range = sum(ranges) / len(ranges)
        
        # Текущая цена
        current_price = float(candles[-1].close_price)
        atr_percent = (avg_range / current_price) * 100
        
        return ATRData(
            calculated_atr=avg_range,
            technical_atr=avg_range,  # Упрощенно
            atr_percent=atr_percent,
            last_5_ranges=ranges,
            updated_at=datetime.now(timezone.utc)
        )
    
    # ==================== ОБНОВЛЕНИЕ СВЕЧЕЙ ====================
    
    async def _update_candles(self, context: TechnicalAnalysisContext):
        """
        Обновить последние свечи всех таймфреймов
        
        Загружает свечи параллельно для M5, M30, H1, H4.
        """
        try:
            update_start = datetime.now()
            
            # Параллельная загрузка всех таймфреймов
            tasks = [
                self.repository.get_candles(context.symbol, "5m", limit=100),   # 8 часов
                self.repository.get_candles(context.symbol, "30m", limit=50),   # 25 часов
                self.repository.get_candles(context.symbol, "1h", limit=24),    # 1 день
                self.repository.get_candles(context.symbol, "4h", limit=24),    # 4 дня
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            context.recent_candles_m5 = results[0] if not isinstance(results[0], Exception) else []
            context.recent_candles_m30 = results[1] if not isinstance(results[1], Exception) else []
            context.recent_candles_h1 = results[2] if not isinstance(results[2], Exception) else []
            context.recent_candles_h4 = results[3] if not isinstance(results[3], Exception) else []
            
            context.candles_updated_at = datetime.now(timezone.utc)
            
            # Логируем результаты
            candle_counts = f"M5={len(context.recent_candles_m5)}, M30={len(context.recent_candles_m30)}, " \
                          f"H1={len(context.recent_candles_h1)}, H4={len(context.recent_candles_h4)}"
            logger.debug(f"✅ Свечи обновлены для {context.symbol}: {candle_counts}")
            
            self.stats["candles_updates"] += 1
            update_duration = (datetime.now() - update_start).total_seconds()
            self.stats["update_times"]["candles"].append(update_duration)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления свечей {context.symbol}: {e}")
            self.stats["errors_by_type"]["candles"] += 1
            raise
    
    # ==================== ФОНОВЫЕ ОБНОВЛЕНИЯ ====================
    
    async def start_background_updates(self):
        """
        Запустить фоновые задачи автоматического обновления
        
        Создает 3 фоновых задачи:
        - Обновление свечей (каждую минуту)
        - Обновление ATR (каждый час)
        - Обновление уровней (раз в сутки)
        """
        if self.is_running:
            logger.warning("⚠️ Фоновые обновления уже запущены")
            return
        
        logger.info("🚀 Запуск фоновых обновлений технического анализа...")
        
        self.is_running = True
        self.stats["start_time"] = datetime.now()
        
        # Задача 1: Обновление свечей (каждую минуту)
        self._update_tasks.append(
            asyncio.create_task(self._candles_update_loop(), name="candles_update")
        )
        
        # Задача 2: Обновление ATR (каждый час)
        self._update_tasks.append(
            asyncio.create_task(self._atr_update_loop(), name="atr_update")
        )
        
        # Задача 3: Обновление уровней (раз в сутки)
        self._update_tasks.append(
            asyncio.create_task(self._levels_update_loop(), name="levels_update")
        )
        
        logger.info(f"✅ Запущено {len(self._update_tasks)} фоновых задач")
        logger.info("   • Свечи: каждую минуту")
        logger.info("   • ATR: каждый час")
        logger.info("   • Уровни: раз в сутки (00:00 UTC)")
    
    async def stop_background_updates(self):
        """Остановить все фоновые задачи"""
        if not self.is_running:
            logger.warning("⚠️ Фоновые обновления уже остановлены")
            return
        
        logger.info("🛑 Остановка фоновых обновлений...")
        
        self.is_running = False
        
        # Отменяем все задачи
        for task in self._update_tasks:
            if not task.done():
                task.cancel()
        
        # Ждем завершения
        if self._update_tasks:
            await asyncio.gather(*self._update_tasks, return_exceptions=True)
        
        self._update_tasks.clear()
        
        logger.info("✅ Фоновые обновления остановлены")
    
    async def _candles_update_loop(self):
        """Цикл обновления свечей (каждую минуту)"""
        logger.info("🔄 Запущен цикл обновления свечей (1 минута)")
        
        while self.is_running:
            try:
                # Обновляем свечи для всех существующих контекстов
                for symbol, context in self.contexts.items():
                    try:
                        await self._update_candles(context)
                    except Exception as e:
                        logger.error(f"❌ Ошибка обновления свечей {symbol}: {e}")
                
                # Ждем 60 секунд
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                logger.info("🛑 Цикл обновления свечей остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в цикле свечей: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(60)
    
    async def _atr_update_loop(self):
        """Цикл обновления ATR (каждый час)"""
        logger.info("🔄 Запущен цикл обновления ATR (1 час)")
        
        while self.is_running:
            try:
                # Обновляем ATR для всех контекстов
                for symbol, context in self.contexts.items():
                    try:
                        await self._update_atr(context)
                    except Exception as e:
                        logger.error(f"❌ Ошибка обновления ATR {symbol}: {e}")
                
                # Ждем 1 час
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                logger.info("🛑 Цикл обновления ATR остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в цикле ATR: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(3600)
    
    async def _levels_update_loop(self):
        """Цикл обновления уровней (раз в сутки в 00:00 UTC)"""
        logger.info("🔄 Запущен цикл обновления уровней (24 часа)")
        
        while self.is_running:
            try:
                # Обновляем уровни для всех контекстов
                for symbol, context in self.contexts.items():
                    try:
                        await self._update_levels(context)
                    except Exception as e:
                        logger.error(f"❌ Ошибка обновления уровней {symbol}: {e}")
                
                # Ждем до следующего 00:00 UTC
                now = datetime.now(timezone.utc)
                next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                sleep_seconds = (next_midnight - now).total_seconds()
                
                logger.info(f"⏰ Следующее обновление уровней: {next_midnight.strftime('%Y-%m-%d %H:%M UTC')}")
                
                await asyncio.sleep(sleep_seconds)
                
            except asyncio.CancelledError:
                logger.info("🛑 Цикл обновления уровней остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в цикле уровней: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(86400)  # 24 часа
    
    # ==================== УПРАВЛЕНИЕ ====================
    
    async def refresh_all_contexts(self):
        """Принудительно обновить все контексты"""
        logger.info(f"🔄 Принудительное обновление всех контекстов ({len(self.contexts)})")
        
        for symbol, context in self.contexts.items():
            try:
                await self._full_update_context(context)
            except Exception as e:
                logger.error(f"❌ Ошибка обновления {symbol}: {e}")
        
        logger.info("✅ Все контексты обновлены")
    
    def clear_context(self, symbol: str):
        """Удалить контекст для символа"""
        symbol = symbol.upper()
        if symbol in self.contexts:
            del self.contexts[symbol]
            logger.info(f"🗑️ Контекст {symbol} удален")
    
    def clear_all_contexts(self):
        """Очистить все контексты"""
        count = len(self.contexts)
        self.contexts.clear()
        logger.info(f"🗑️ Удалено {count} контекстов")
    
    # ==================== СТАТИСТИКА ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику менеджера"""
        uptime = None
        if self.stats["start_time"]:
            uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
        
        # Средние времена обновления
        avg_times = {}
        for update_type, times in self.stats["update_times"].items():
            if times:
                avg_times[f"{update_type}_avg_seconds"] = sum(times) / len(times)
        
        return {
            **self.stats,
            "uptime_seconds": uptime,
            "is_running": self.is_running,
            "active_tasks": len([t for t in self._update_tasks if not t.done()]),
            "contexts_count": len(self.contexts),
            "contexts_symbols": list(self.contexts.keys()),
            "success_rate": (self.stats["successful_updates"] / self.stats["total_updates"] * 100) 
                           if self.stats["total_updates"] > 0 else 100,
            **avg_times
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Проверка здоровья менеджера"""
        stats = self.get_stats()
        
        # Проверяем что все задачи работают
        all_tasks_alive = all(not task.done() for task in self._update_tasks) if self._update_tasks else False
        
        # Проверяем недавние обновления
        last_update_recent = False
        if self.stats["last_update_time"]:
            age = (datetime.now() - self.stats["last_update_time"]).total_seconds()
            last_update_recent = age < 300  # Последнее обновление < 5 минут назад
        
        is_healthy = (
            self.is_running and
            all_tasks_alive and
            (last_update_recent or self.stats["total_updates"] == 0) and
            stats["success_rate"] > 80
        )
        
        return {
            "healthy": is_healthy,
            "is_running": self.is_running,
            "all_tasks_alive": all_tasks_alive,
            "last_update_recent": last_update_recent,
            "success_rate": stats["success_rate"],
            "contexts_count": len(self.contexts),
            "errors": sum(self.stats["errors_by_type"].values()),
            "uptime_seconds": stats["uptime_seconds"]
        }
    
    def __repr__(self) -> str:
        """Представление для отладки"""
        return (f"TechnicalAnalysisContextManager(contexts={len(self.contexts)}, "
                f"running={self.is_running}, "
                f"updates={self.stats['total_updates']})")
    
    def __str__(self) -> str:
        """Человекочитаемое представление"""
        stats = self.get_stats()
        return (f"Technical Analysis Context Manager:\n"
                f"  Status: {'🟢 Running' if self.is_running else '🔴 Stopped'}\n"
                f"  Contexts: {len(self.contexts)} active\n"
                f"  Updates: {stats['total_updates']} total, {stats['successful_updates']} successful\n"
                f"  Success rate: {stats['success_rate']:.1f}%\n"
                f"  Tasks: {stats['active_tasks']}/{len(self._update_tasks)} active")


# Export
__all__ = ["TechnicalAnalysisContextManager"]

logger.info("✅ Technical Analysis Context Manager module loaded")
