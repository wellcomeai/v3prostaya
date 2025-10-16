"""
ATR Calculator - Average True Range Calculator

Расчет запаса хода (ATR) для фильтрации сигналов и определения размеров стопов.

Реализует логику из торговой стратегии:
1. Расчетный ATR - среднее High-Low за 3-5 дней (исключая паранормальные)
2. Технический ATR - расстояние между уровнями на D1
3. Правило 75-80% - фильтрация сигналов при исчерпании ATR
4. Расчет размеров Stop Loss (по тренду 10%, контртренд 5%)

Author: Trading Bot Team
Version: 1.0.1 - FIXED: current_range_used теперь доля (0-1), не проценты
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timezone
from statistics import mean, median, stdev

from .context import ATRData, SupportResistanceLevel

logger = logging.getLogger(__name__)


class ATRCalculator:
    """
    📊 Калькулятор Average True Range (ATR)
    
    Рассчитывает запас хода для торговых стратегий:
    - Расчетный ATR: среднее High-Low за N дней
    - Технический ATR: расстояние между уровнями
    - Фильтр паранормальных баров
    - Проверка исчерпания запаса хода (75-80% правило)
    - Расчет размеров стопов
    
    ВАЖНО: current_range_used хранится как доля (0-1), не проценты!
    Например: 0.75 означает 75% ATR использовано
    
    Usage:
        calculator = ATRCalculator()
        atr_data = calculator.calculate_atr(candles_d1, levels_d1)
        
        if atr_data.is_exhausted:
            # Не входить по тренду
            pass
    """
    
    def __init__(
        self,
        lookback_days: int = 5,
        paranormal_upper_threshold: float = 2.0,  # Бар > 2×ATR = паранормальный
        paranormal_lower_threshold: float = 0.5,  # Бар < 0.5×ATR = паранормальный
        exhaustion_threshold: float = 0.75,       # 0.75 = 75% = исчерпан запас хода
        stop_loss_trend_percent: float = 0.10,    # 10% от ATR для стопа по тренду
        stop_loss_counter_percent: float = 0.05   # 5% от ATR для контртренда
    ):
        """
        Инициализация калькулятора
        
        Args:
            lookback_days: Количество дней для расчета ATR (3-5)
            paranormal_upper_threshold: Верхний порог паранормальности (>2×ATR)
            paranormal_lower_threshold: Нижний порог паранормальности (<0.5×ATR)
            exhaustion_threshold: Порог исчерпания запаса хода (0.75 = 75%)
            stop_loss_trend_percent: % от ATR для стопа по тренду
            stop_loss_counter_percent: % от ATR для контртренда
        """
        self.lookback_days = lookback_days
        self.paranormal_upper = paranormal_upper_threshold
        self.paranormal_lower = paranormal_lower_threshold
        self.exhaustion_threshold = exhaustion_threshold
        self.stop_loss_trend_percent = stop_loss_trend_percent
        self.stop_loss_counter_percent = stop_loss_counter_percent
        
        # Статистика
        self.stats = {
            "calculations_count": 0,
            "paranormal_bars_filtered": 0,
            "average_atr": 0.0,
            "average_atr_percent": 0.0
        }
        
        logger.info("🔧 ATRCalculator инициализирован")
        logger.info(f"   • Lookback: {self.lookback_days} дней")
        logger.info(f"   • Паранормальные фильтры: {self.paranormal_lower}×ATR < bar < {self.paranormal_upper}×ATR")
        logger.info(f"   • Порог исчерпания: {self.exhaustion_threshold*100:.0f}%")
    
    # ==================== ОСНОВНОЙ МЕТОД ====================
    
    def calculate_atr(
        self,
        candles: List,
        levels: Optional[List[SupportResistanceLevel]] = None,
        current_price: Optional[float] = None
    ) -> ATRData:
        """
        🎯 Основной метод расчета ATR
        
        Рассчитывает:
        1. Расчетный ATR (среднее High-Low, исключая паранормальные)
        2. Технический ATR (расстояние между уровнями)
        3. Процент использования ATR сегодня (как ДОЛЯ 0-1)
        4. Флаг исчерпания запаса хода
        
        Args:
            candles: Список свечей D1 (минимум 3-5 дней)
            levels: Список уровней для технического ATR (опционально)
            current_price: Текущая цена для расчета использования ATR
            
        Returns:
            ATRData с рассчитанными данными
            - current_range_used: доля от 0 до 1 (не проценты!)
            - is_exhausted: True если >= exhaustion_threshold
            
        Raises:
            ValueError: Если недостаточно данных
        """
        try:
            self.stats["calculations_count"] += 1
            
            # Валидация входных данных
            if not candles or len(candles) < 3:
                raise ValueError(f"Недостаточно свечей для расчета ATR: {len(candles)}")
            
            # 1. РАСЧЕТНЫЙ ATR - среднее High-Low (исключая паранормальные)
            calculated_atr, last_5_ranges = self._calculate_simple_atr(candles)
            
            if calculated_atr <= 0:
                raise ValueError("Расчетный ATR не может быть <= 0")
            
            # 2. ТЕХНИЧЕСКИЙ ATR - расстояние между уровнями
            technical_atr = self._calculate_technical_atr(levels, current_price) if levels else calculated_atr
            
            # 3. ATR в процентах от цены
            if current_price:
                price = current_price
            elif candles:
                price = float(candles[-1]['close_price'])
            else:
                price = 1.0  # Fallback
            
            atr_percent = (calculated_atr / price) * 100
            
            # 4. ТЕКУЩЕЕ ИСПОЛЬЗОВАНИЕ ATR (сколько пройдено сегодня)
            # ✅ ИСПРАВЛЕНО: храним как ДОЛЮ (0-1), не проценты
            current_range_used = 0.0
            is_exhausted = False
            
            if current_price and len(candles) > 0:
                # Берем текущий бар (последний)
                today_candle = candles[-1]
                today_range = abs(float(today_candle['high_price']) - float(today_candle['low_price']))
                
                # ✅ ИСПРАВЛЕНО: Доля использования = пройденный диапазон / ATR (БЕЗ * 100)
                if calculated_atr > 0:
                    current_range_used = today_range / calculated_atr  # 0-1, не проценты!
                    
                    # ✅ ИСПРАВЛЕНО: Сравниваем с порогом напрямую (оба значения - доли)
                    is_exhausted = current_range_used >= self.exhaustion_threshold
            
            # Обновляем статистику
            self._update_stats(calculated_atr, atr_percent)
            
            # Создаем результат
            atr_data = ATRData(
                calculated_atr=calculated_atr,
                technical_atr=technical_atr,
                atr_percent=atr_percent,
                current_range_used=current_range_used,  # Доля 0-1
                is_exhausted=is_exhausted,
                last_5_ranges=last_5_ranges,
                updated_at=datetime.now(timezone.utc)
            )
            
            logger.debug(f"✅ ATR рассчитан: calculated={calculated_atr:.2f}, "
                        f"technical={technical_atr:.2f}, "
                        f"used={current_range_used:.3f} ({current_range_used*100:.1f}%), "
                        f"exhausted={is_exhausted}")
            
            return atr_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета ATR: {e}")
            raise
    
    # ==================== РАСЧЕТНЫЙ ATR ====================
    
    def _calculate_simple_atr(self, candles: List) -> Tuple[float, List[float]]:
        """
        Расчет простого ATR - среднее High-Low за N дней
        
        Алгоритм:
        1. Берем последние N свечей
        2. Вычисляем High-Low для каждой
        3. Фильтруем паранормальные бары
        4. Считаем среднее
        
        Args:
            candles: Список свечей D1
            
        Returns:
            Tuple[ATR, список диапазонов последних 5 баров]
        """
        try:
            # Берем последние N дней
            recent_candles = candles[-self.lookback_days:] if len(candles) >= self.lookback_days else candles
            
            if len(recent_candles) < 3:
                raise ValueError(f"Недостаточно свечей: {len(recent_candles)}")
            
            # Вычисляем диапазоны High-Low
            ranges = []
            for candle in recent_candles:
                high = float(candle['high_price'])
                low = float(candle['low_price'])
                range_val = high - low
                
                if range_val < 0:
                    logger.warning(f"⚠️ Отрицательный диапазон: High={high}, Low={low}")
                    continue
                
                ranges.append(range_val)
            
            if not ranges:
                raise ValueError("Нет валидных диапазонов для расчета ATR")
            
            # Первичный расчет среднего (для фильтрации)
            initial_atr = mean(ranges)
            
            # ФИЛЬТРУЕМ ПАРАНОРМАЛЬНЫЕ БАРЫ
            filtered_ranges = self._filter_paranormal_bars(ranges, initial_atr)
            
            # Финальный расчет ATR на отфильтрованных данных
            if filtered_ranges:
                final_atr = mean(filtered_ranges)
            else:
                # Если все бары паранормальные - используем медиану
                logger.warning("⚠️ Все бары паранормальные, используем медиану")
                final_atr = median(ranges)
            
            # Сохраняем последние 5 диапазонов для контекста
            last_5_ranges = ranges[-5:] if len(ranges) >= 5 else ranges
            
            logger.debug(f"📊 Расчетный ATR: {final_atr:.2f} (из {len(filtered_ranges)}/{len(ranges)} баров)")
            
            return final_atr, last_5_ranges
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета простого ATR: {e}")
            raise
    
    def _filter_paranormal_bars(self, ranges: List[float], avg_atr: float) -> List[float]:
        """
        Фильтрация паранормальных баров
        
        Паранормальные бары:
        - Слишком большие: range > 2×ATR
        - Слишком маленькие: range < 0.5×ATR
        
        Args:
            ranges: Список диапазонов
            avg_atr: Среднее значение для фильтрации
            
        Returns:
            Отфильтрованный список диапазонов
        """
        if avg_atr <= 0:
            return ranges
        
        upper_limit = avg_atr * self.paranormal_upper  # 2×ATR
        lower_limit = avg_atr * self.paranormal_lower  # 0.5×ATR
        
        filtered = []
        paranormal_count = 0
        
        for r in ranges:
            if lower_limit <= r <= upper_limit:
                filtered.append(r)
            else:
                paranormal_count += 1
                logger.debug(f"⚠️ Паранормальный бар отфильтрован: {r:.2f} (лимиты: {lower_limit:.2f} - {upper_limit:.2f})")
        
        if paranormal_count > 0:
            self.stats["paranormal_bars_filtered"] += paranormal_count
            logger.info(f"🔍 Отфильтровано {paranormal_count} паранормальных баров из {len(ranges)}")
        
        # Если отфильтровали всё - возвращаем оригинальные
        if not filtered:
            logger.warning("⚠️ Все бары паранормальные, возвращаем оригинальные")
            return ranges
        
        return filtered
    
    # ==================== ТЕХНИЧЕСКИЙ ATR ====================
    
    def _calculate_technical_atr(
        self,
        levels: List[SupportResistanceLevel],
        current_price: Optional[float] = None
    ) -> float:
        """
        Расчет технического ATR - расстояние между уровнями
        
        Алгоритм:
        1. Находим ближайший уровень поддержки (ниже цены)
        2. Находим ближайший уровень сопротивления (выше цены)
        3. Технический ATR = расстояние между ними
        
        Args:
            levels: Список уровней
            current_price: Текущая цена (для поиска ближайших уровней)
            
        Returns:
            Технический ATR (расстояние между уровнями)
        """
        try:
            if not levels or len(levels) < 2:
                logger.debug("⚠️ Недостаточно уровней для технического ATR")
                return 0.0
            
            if not current_price:
                # Используем среднюю цену уровней
                prices = [level.price for level in levels]
                current_price = mean(prices)
            
            # Находим ближайшую поддержку (ниже цены)
            supports = [level for level in levels if level.price < current_price]
            nearest_support = max(supports, key=lambda l: l.price) if supports else None
            
            # Находим ближайшее сопротивление (выше цены)
            resistances = [level for level in levels if level.price > current_price]
            nearest_resistance = min(resistances, key=lambda l: l.price) if resistances else None
            
            # Рассчитываем технический ATR
            if nearest_support and nearest_resistance:
                technical_atr = abs(nearest_resistance.price - nearest_support.price)
                logger.debug(f"📊 Технический ATR: {technical_atr:.2f} "
                           f"(между {nearest_support.price:.2f} и {nearest_resistance.price:.2f})")
                return technical_atr
            
            elif nearest_support or nearest_resistance:
                # Если есть только один уровень - удваиваем расстояние
                level = nearest_support or nearest_resistance
                distance = abs(level.price - current_price)
                technical_atr = distance * 2
                logger.debug(f"📊 Технический ATR (один уровень): {technical_atr:.2f}")
                return technical_atr
            
            else:
                logger.warning("⚠️ Не найдено уровней для технического ATR")
                return 0.0
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета технического ATR: {e}")
            return 0.0
    
    # ==================== ПРОВЕРКИ И РАСЧЕТЫ ====================
    
    def check_atr_exhaustion(
        self,
        candles: List,
        current_price: float,
        calculated_atr: Optional[float] = None,
        threshold: Optional[float] = None
    ) -> Tuple[bool, float]:
        """
        Проверка исчерпания запаса хода (правило 75-80%)
        
        Если пройдено >= 75% ATR сегодня:
        - НЕ входить по тренду
        - Можно входить контртренд
        - Исключение: вход у локальных мин/макс
        
        Args:
            candles: Список свечей D1
            current_price: Текущая цена
            calculated_atr: Расчетный ATR (если уже известен)
            threshold: Порог исчерпания (default: 0.75 = 75%)
            
        Returns:
            Tuple[исчерпан?, процент использования (0-100)]
            
        Note: Возвращает ПРОЦЕНТЫ (0-100) для удобства вызывающего кода
        """
        try:
            if threshold is None:
                threshold = self.exhaustion_threshold
            
            # Рассчитываем ATR если не передан
            if calculated_atr is None:
                atr_data = self.calculate_atr(candles, current_price=current_price)
                calculated_atr = atr_data.calculated_atr
            
            # Берем сегодняшний бар
            if not candles:
                return False, 0.0
            
            today_candle = candles[-1]
            today_high = float(today_candle['high_price'])
            today_low = float(today_candle['low_price'])
            today_range = today_high - today_low
            
            # ✅ ИСПРАВЛЕНО: Сначала вычисляем долю, потом проценты
            if calculated_atr > 0:
                used_ratio = today_range / calculated_atr  # Доля 0-1
                used_percent = used_ratio * 100  # Проценты для возврата
            else:
                used_ratio = 0.0
                used_percent = 0.0
            
            # ✅ ИСПРАВЛЕНО: Сравниваем ДОЛИ (не проценты)
            is_exhausted = used_ratio >= threshold
            
            if is_exhausted:
                logger.info(f"⚠️ Запас хода исчерпан: {used_percent:.1f}% >= {threshold*100:.0f}%")
            else:
                logger.debug(f"✅ Запас хода доступен: {used_percent:.1f}%")
            
            return is_exhausted, used_percent
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки исчерпания ATR: {e}")
            return False, 0.0
    
    def calculate_stop_loss_size(
        self,
        atr: float,
        is_trend_trade: bool = True,
        custom_percent: Optional[float] = None
    ) -> float:
        """
        Расчет размера Stop Loss на основе ATR
        
        Правила из стратегии:
        - По тренду: Stop = 0.10 × ATR (10%)
        - Контртренд: Stop = 0.05 × ATR (5%)
        
        Args:
            atr: Значение ATR
            is_trend_trade: True если торговля по тренду
            custom_percent: Кастомный процент (переопределяет дефолтные)
            
        Returns:
            Размер стопа
        """
        try:
            if custom_percent is not None:
                percent = custom_percent
            elif is_trend_trade:
                percent = self.stop_loss_trend_percent
            else:
                percent = self.stop_loss_counter_percent
            
            stop_size = atr * percent
            
            logger.debug(f"📏 Stop Loss: {stop_size:.2f} ({percent*100}% от ATR={atr:.2f})")
            
            return stop_size
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета Stop Loss: {e}")
            return 0.0
    
    def get_remaining_atr(self, atr_data: ATRData) -> float:
        """
        Получить оставшийся запас хода (в процентах)
        
        Args:
            atr_data: Данные ATR (current_range_used как доля 0-1)
            
        Returns:
            Оставшийся процент (0-100)
        """
        # ✅ Конвертируем долю в проценты для удобства
        remaining_percent = max(0.0, (1.0 - atr_data.current_range_used) * 100)
        return remaining_percent
    
    def is_suitable_for_trend_trade(self, atr_data: ATRData, min_remaining: float = 25.0) -> bool:
        """
        Проверка пригодности для торговли по тренду
        
        Требования:
        - ATR не исчерпан (< 75%)
        - Осталось минимум 25% запаса хода
        
        Args:
            atr_data: Данные ATR
            min_remaining: Минимальный остаток в процентах (0-100)
            
        Returns:
            True если можно торговать по тренду
        """
        if atr_data.is_exhausted:
            return False
        
        remaining = self.get_remaining_atr(atr_data)
        suitable = remaining >= min_remaining
        
        if not suitable:
            logger.debug(f"⚠️ Недостаточно запаса хода для тренда: {remaining:.1f}% < {min_remaining}%")
        
        return suitable
    
    def is_suitable_for_counter_trade(self, atr_data: ATRData) -> bool:
        """
        Проверка пригодности для контртрендовой торговли
        
        Контртренд можно торговать даже при исчерпанном ATR.
        Но нужна минимальная волатильность.
        
        Args:
            atr_data: Данные ATR
            
        Returns:
            True если можно торговать контртренд
        """
        # Контртренд можно всегда (даже при исчерпанном ATR)
        # Но проверяем что ATR не нулевой
        return atr_data.calculated_atr > 0
    
    # ==================== СТАТИСТИКА ====================
    
    def _update_stats(self, atr: float, atr_percent: float):
        """Обновление статистики"""
        count = self.stats["calculations_count"]
        
        # Скользящее среднее
        prev_avg = self.stats["average_atr"]
        self.stats["average_atr"] = (prev_avg * (count - 1) + atr) / count
        
        prev_avg_pct = self.stats["average_atr_percent"]
        self.stats["average_atr_percent"] = (prev_avg_pct * (count - 1) + atr_percent) / count
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику калькулятора"""
        return {
            **self.stats,
            "lookback_days": self.lookback_days,
            "paranormal_thresholds": {
                "upper": self.paranormal_upper,
                "lower": self.paranormal_lower
            },
            "exhaustion_threshold": self.exhaustion_threshold,
            "stop_loss_percents": {
                "trend": self.stop_loss_trend_percent,
                "counter": self.stop_loss_counter_percent
            }
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.stats = {
            "calculations_count": 0,
            "paranormal_bars_filtered": 0,
            "average_atr": 0.0,
            "average_atr_percent": 0.0
        }
        logger.info("🔄 Статистика ATRCalculator сброшена")
    
    def __repr__(self) -> str:
        """Представление для отладки"""
        return (f"ATRCalculator(lookback={self.lookback_days}, "
                f"calculations={self.stats['calculations_count']}, "
                f"avg_atr={self.stats['average_atr']:.2f})")
    
    def __str__(self) -> str:
        """Человекочитаемое представление"""
        stats = self.get_stats()
        return (f"ATR Calculator:\n"
                f"  Calculations: {stats['calculations_count']}\n"
                f"  Average ATR: {stats['average_atr']:.2f} ({stats['average_atr_percent']:.2f}%)\n"
                f"  Paranormal bars filtered: {stats['paranormal_bars_filtered']}\n"
                f"  Lookback: {stats['lookback_days']} days\n"
                f"  Exhaustion threshold: {stats['exhaustion_threshold']*100:.0f}%")


# Export
__all__ = ["ATRCalculator"]

logger.info("✅ ATR Calculator module loaded (v1.0.1 - FIXED: current_range_used as ratio)")
