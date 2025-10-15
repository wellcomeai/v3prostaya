"""
Pattern Detector - Детектор торговых паттернов

Анализирует свечные паттерны для торговых стратегий:
1. БСУ (Бар Создавший Уровень) - исторический бар, создавший уровень
2. БПУ (Бар Подтвердивший Уровень) - касание уровня "точка в точку"
3. Пучки свечей - группа свечей с близкими High/Low
4. Поджатие - маленькие бары у уровня перед пробоем
5. Консолидация - длительное боковое движение
6. V-формация - резкий разворот без консолидации

Author: Trading Bot Team
Version: 1.0.0
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from statistics import mean, stdev

from .context import SupportResistanceLevel

logger = logging.getLogger(__name__)


@dataclass
class PatternMatch:
    """
    Результат обнаружения паттерна
    
    Attributes:
        pattern_type: Тип паттерна
        confidence: Уверенность (0.0-1.0)
        candles: Список свечей в паттерне
        metadata: Дополнительная информация
        detected_at: Время обнаружения
    """
    pattern_type: str
    confidence: float
    candles: List = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "confidence": self.confidence,
            "candles_count": len(self.candles),
            "metadata": self.metadata,
            "detected_at": self.detected_at.isoformat()
        }


@dataclass
class BSUPattern:
    """
    БСУ - Бар Создавший Уровень
    
    Исторический бар, который создал уровень поддержки или сопротивления
    """
    candle: Any  # MarketDataCandle
    level_price: float
    level_type: str  # "support" или "resistance"
    created_at: datetime
    is_strong: bool = False
    
    @property
    def age_days(self) -> int:
        """Возраст БСУ в днях"""
        return (datetime.now(timezone.utc) - self.created_at).days


@dataclass
class BPUPattern:
    """
    БПУ - Бар Подтвердивший Уровень
    
    Касание уровня "точка в точку" после создания БСУ
    """
    candle: Any
    level_price: float
    level_type: str
    touch_accuracy: float  # Точность касания (0.0-1.0)
    is_bpu1: bool = False  # Первое касание
    is_bpu2: bool = False  # Второе касание (должно быть пучком с БПУ-1)
    forms_cluster_with: Optional['BPUPattern'] = None


class PatternDetector:
    """
    🔍 Детектор торговых паттернов
    
    Анализирует свечи для поиска торговых паттернов:
    - БСУ/БПУ модель для стратегии отбоя
    - Поджатие для стратегии пробоя
    - Пучки, консолидация, V-формации
    
    Usage:
        detector = PatternDetector()
        
        # Проверка поджатия
        has_compression = detector.detect_compression(candles_m5, level)
        
        # Поиск БСУ-БПУ
        bsu = detector.find_bsu(candles_d1, level)
        bpu_patterns = detector.find_bpu(candles_m30, bsu)
    """
    
    def __init__(
        self,
        # Параметры поджатия
        compression_bar_threshold: float = 0.3,  # Бар < 30% от ATR = маленький
        compression_min_bars: int = 3,           # Минимум баров для поджатия
        
        # Параметры пучка
        cluster_tolerance_percent: float = 0.5,  # Допуск для пучка (0.5%)
        cluster_min_bars: int = 2,               # Минимум баров в пучке
        
        # Параметры БПУ
        bpu_touch_tolerance_percent: float = 0.2,  # Допуск касания БПУ (0.2%)
        bpu_max_gap_percent: float = 0.3,        # Макс люфт для БПУ-2
        
        # Параметры консолидации
        consolidation_min_bars: int = 10,        # Минимум баров
        consolidation_max_range_percent: float = 2.0,  # Макс диапазон 2%
        
        # Параметры V-формации
        v_formation_min_move_percent: float = 3.0,  # Минимальное движение 3%
        v_formation_max_correction_percent: float = 30.0,  # Макс откат 30%
    ):
        """
        Инициализация детектора паттернов
        
        Args:
            compression_bar_threshold: Порог маленького бара для поджатия
            compression_min_bars: Минимум баров для поджатия
            cluster_tolerance_percent: Допуск для определения пучка
            cluster_min_bars: Минимум баров в пучке
            bpu_touch_tolerance_percent: Допуск касания для БПУ
            bpu_max_gap_percent: Максимальный люфт для БПУ-2
            consolidation_min_bars: Минимум баров для консолидации
            consolidation_max_range_percent: Максимальный диапазон консолидации
            v_formation_min_move_percent: Минимальное движение для V-формации
            v_formation_max_correction_percent: Максимальный откат V-формации
        """
        self.compression_threshold = compression_bar_threshold
        self.compression_min_bars = compression_min_bars
        
        self.cluster_tolerance = cluster_tolerance_percent / 100.0
        self.cluster_min_bars = cluster_min_bars
        
        self.bpu_touch_tolerance = bpu_touch_tolerance_percent / 100.0
        self.bpu_max_gap = bpu_max_gap_percent / 100.0
        
        self.consolidation_min_bars = consolidation_min_bars
        self.consolidation_max_range = consolidation_max_range_percent / 100.0
        
        self.v_min_move = v_formation_min_move_percent / 100.0
        self.v_max_correction = v_formation_max_correction_percent / 100.0
        
        # Статистика
        self.stats = {
            "compressions_detected": 0,
            "clusters_detected": 0,
            "bsu_found": 0,
            "bpu_found": 0,
            "consolidations_detected": 0,
            "v_formations_detected": 0,
            "total_patterns": 0
        }
        
        logger.info("🔍 PatternDetector инициализирован")
        logger.info(f"   • Compression threshold: {compression_bar_threshold}")
        logger.info(f"   • Cluster tolerance: {cluster_tolerance_percent}%")
        logger.info(f"   • BPU touch tolerance: {bpu_touch_tolerance_percent}%")
    
    # ==================== ПОДЖАТИЕ ====================
    
    def detect_compression(
        self,
        candles: List,
        level: Optional[SupportResistanceLevel] = None,
        atr: Optional[float] = None,
        lookback: int = 20
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Обнаружение поджатия (compression) - маленькие бары у уровня
        
        Поджатие = серия маленьких свечей (< 30% ATR) перед пробоем уровня
        
        Условия:
        1. Минимум 3+ маленьких бара подряд
        2. Размер бара < 30% от ATR
        3. Бары находятся близко к уровню
        
        Args:
            candles: Список свечей (M5, M30, H1)
            level: Уровень для проверки близости
            atr: ATR для определения маленьких баров
            lookback: Сколько последних свечей анализировать
            
        Returns:
            Tuple[has_compression, details]
        """
        try:
            if not candles or len(candles) < self.compression_min_bars:
                return False, {}
            
            # Берем последние N свечей
            recent_candles = candles[-lookback:] if len(candles) > lookback else candles
            
            # Если нет ATR - рассчитываем средний диапазон
            if atr is None:
                ranges = [float(c.high_price - c.low_price) for c in recent_candles]
                atr = mean(ranges) if ranges else 0
            
            if atr <= 0:
                return False, {}
            
            # Ищем последовательность маленьких баров
            small_bars_streak = 0
            max_streak = 0
            small_bars_indices = []
            
            for i, candle in enumerate(recent_candles):
                bar_range = float(candle.high_price - candle.low_price)
                
                # Проверяем что бар маленький
                if bar_range < (atr * self.compression_threshold):
                    small_bars_streak += 1
                    small_bars_indices.append(i)
                    max_streak = max(max_streak, small_bars_streak)
                else:
                    small_bars_streak = 0
            
            has_compression = max_streak >= self.compression_min_bars
            
            # Дополнительная проверка - бары у уровня
            near_level = False
            if level and has_compression:
                last_candles = recent_candles[-self.compression_min_bars:]
                prices = [float(c.close_price) for c in last_candles]
                avg_price = mean(prices)
                
                distance_percent = abs(avg_price - level.price) / level.price
                near_level = distance_percent < 0.01  # В пределах 1%
            
            details = {
                "max_streak": max_streak,
                "small_bars_count": len(small_bars_indices),
                "near_level": near_level,
                "atr": atr,
                "threshold_used": atr * self.compression_threshold
            }
            
            if has_compression:
                self.stats["compressions_detected"] += 1
                self.stats["total_patterns"] += 1
                logger.info(f"✅ Поджатие обнаружено: {max_streak} маленьких баров (ATR={atr:.2f})")
            
            return has_compression, details
            
        except Exception as e:
            logger.error(f"❌ Ошибка детекции поджатия: {e}")
            return False, {}
    
    # ==================== ПУЧКИ ====================
    
    def detect_cluster(
        self,
        candles: List,
        lookback: int = 10
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Обнаружение пучка свечей - группа баров с близкими High/Low
        
        Пучок = свечи, у которых High и Low находятся близко друг к другу
        
        Args:
            candles: Список свечей
            lookback: Сколько последних свечей анализировать
            
        Returns:
            Tuple[has_cluster, details]
        """
        try:
            if not candles or len(candles) < self.cluster_min_bars:
                return False, {}
            
            # Берем последние N свечей
            recent_candles = candles[-lookback:] if len(candles) > lookback else candles
            
            if len(recent_candles) < self.cluster_min_bars:
                return False, {}
            
            # Собираем High и Low
            highs = [float(c.high_price) for c in recent_candles]
            lows = [float(c.low_price) for c in recent_candles]
            
            # Диапазон High
            max_high = max(highs)
            min_high = min(highs)
            high_range_percent = (max_high - min_high) / min_high
            
            # Диапазон Low
            max_low = max(lows)
            min_low = min(lows)
            low_range_percent = (max_low - min_low) / min_low
            
            # Проверяем что High и Low сгруппированы
            has_cluster = (
                high_range_percent <= self.cluster_tolerance and
                low_range_percent <= self.cluster_tolerance
            )
            
            details = {
                "high_range_percent": high_range_percent * 100,
                "low_range_percent": low_range_percent * 100,
                "max_high": max_high,
                "min_high": min_high,
                "max_low": max_low,
                "min_low": min_low,
                "candles_in_cluster": len(recent_candles)
            }
            
            if has_cluster:
                self.stats["clusters_detected"] += 1
                self.stats["total_patterns"] += 1
                logger.info(f"✅ Пучок обнаружен: {len(recent_candles)} свечей "
                          f"(High: {high_range_percent*100:.2f}%, Low: {low_range_percent*100:.2f}%)")
            
            return has_cluster, details
            
        except Exception as e:
            logger.error(f"❌ Ошибка детекции пучка: {e}")
            return False, {}
    
    # ==================== БСУ (БАР СОЗДАВШИЙ УРОВЕНЬ) ====================
    
    def find_bsu(
        self,
        candles: List,
        level: SupportResistanceLevel,
        max_age_days: int = 180
    ) -> Optional[BSUPattern]:
        """
        Найти БСУ (Бар Создавший Уровень)
        
        БСУ = исторический бар, который создал уровень (локальный экстремум)
        
        Args:
            candles: Список свечей D1
            level: Уровень для которого ищем БСУ
            max_age_days: Максимальный возраст БСУ
            
        Returns:
            BSUPattern или None
        """
        try:
            if not candles or not level:
                return None
            
            # Допуск для поиска БСУ
            tolerance = level.price * 0.005  # 0.5%
            
            # Ищем свечу, которая создала уровень
            for candle in candles:
                if level.level_type == "support":
                    # Для поддержки смотрим на Low
                    candle_price = float(candle.low_price)
                else:
                    # Для сопротивления смотрим на High
                    candle_price = float(candle.high_price)
                
                # Проверяем совпадение с уровнем
                if abs(candle_price - level.price) <= tolerance:
                    # Проверяем возраст
                    age_days = (datetime.now(timezone.utc) - candle.open_time).days
                    
                    if age_days <= max_age_days:
                        bsu = BSUPattern(
                            candle=candle,
                            level_price=level.price,
                            level_type=level.level_type,
                            created_at=candle.open_time,
                            is_strong=level.is_strong
                        )
                        
                        self.stats["bsu_found"] += 1
                        self.stats["total_patterns"] += 1
                        
                        logger.info(f"✅ БСУ найден: {level.level_type} @ {level.price:.2f}, "
                                  f"age={age_days} дней")
                        
                        return bsu
            
            logger.debug(f"⚠️ БСУ не найден для уровня {level.price:.2f}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска БСУ: {e}")
            return None
    
    # ==================== БПУ (БАР ПОДТВЕРДИВШИЙ УРОВЕНЬ) ====================
    
    def find_bpu(
        self,
        candles: List,
        level: SupportResistanceLevel,
        lookback: int = 50
    ) -> List[BPUPattern]:
        """
        Найти БПУ (Бар Подтвердивший Уровень)
        
        БПУ = касание уровня "точка в точку" после создания БСУ
        БПУ-1 = первое касание
        БПУ-2 = второе касание, должно быть пучком с БПУ-1
        
        Args:
            candles: Список свечей (M30, H1)
            level: Уровень для проверки
            lookback: Сколько последних свечей анализировать
            
        Returns:
            Список найденных БПУ
        """
        try:
            if not candles or not level:
                return []
            
            # Берем последние N свечей
            recent_candles = candles[-lookback:] if len(candles) > lookback else candles
            
            if len(recent_candles) < 2:
                return []
            
            # Допуск для касания
            tolerance = level.price * self.bpu_touch_tolerance
            
            bpu_list = []
            
            for i, candle in enumerate(recent_candles):
                if level.level_type == "support":
                    # Для поддержки смотрим на Low
                    candle_price = float(candle.low_price)
                else:
                    # Для сопротивления смотрим на High
                    candle_price = float(candle.high_price)
                
                # Проверяем касание
                distance = abs(candle_price - level.price)
                
                if distance <= tolerance:
                    # Рассчитываем точность касания
                    touch_accuracy = 1.0 - (distance / tolerance)
                    
                    bpu = BPUPattern(
                        candle=candle,
                        level_price=level.price,
                        level_type=level.level_type,
                        touch_accuracy=touch_accuracy
                    )
                    
                    bpu_list.append(bpu)
            
            # Определяем БПУ-1 и БПУ-2
            if len(bpu_list) >= 1:
                bpu_list[0].is_bpu1 = True
            
            if len(bpu_list) >= 2:
                bpu_list[1].is_bpu2 = True
                
                # Проверяем что БПУ-2 формирует пучок с БПУ-1
                forms_cluster = self._check_bpu_cluster(bpu_list[0], bpu_list[1])
                
                if forms_cluster:
                    bpu_list[1].forms_cluster_with = bpu_list[0]
                    logger.info(f"✅ БПУ-2 формирует пучок с БПУ-1")
            
            if bpu_list:
                self.stats["bpu_found"] += len(bpu_list)
                self.stats["total_patterns"] += len(bpu_list)
                
                logger.info(f"✅ Найдено {len(bpu_list)} БПУ для уровня {level.price:.2f}")
            
            return bpu_list
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска БПУ: {e}")
            return []
    
    def _check_bpu_cluster(self, bpu1: BPUPattern, bpu2: BPUPattern) -> bool:
        """
        Проверка что БПУ-2 формирует пучок с БПУ-1
        
        Пучок = High и Low обоих баров близки (в пределах допуска)
        
        Args:
            bpu1: Первый БПУ
            bpu2: Второй БПУ
            
        Returns:
            True если формируют пучок
        """
        try:
            candle1 = bpu1.candle
            candle2 = bpu2.candle
            
            # Сравниваем High
            high1 = float(candle1.high_price)
            high2 = float(candle2.high_price)
            high_diff_percent = abs(high1 - high2) / high1
            
            # Сравниваем Low
            low1 = float(candle1.low_price)
            low2 = float(candle2.low_price)
            low_diff_percent = abs(low1 - low2) / low1
            
            # Проверяем что оба в пределах допуска
            # БПУ-2 может не добивать на люфт (до 0.3%)
            forms_cluster = (
                high_diff_percent <= self.bpu_max_gap and
                low_diff_percent <= self.bpu_max_gap
            )
            
            logger.debug(f"📊 Проверка пучка БПУ: high_diff={high_diff_percent*100:.2f}%, "
                        f"low_diff={low_diff_percent*100:.2f}%, cluster={forms_cluster}")
            
            return forms_cluster
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки пучка БПУ: {e}")
            return False
    
    # ==================== КОНСОЛИДАЦИЯ ====================
    
    def detect_consolidation(
        self,
        candles: List,
        lookback: int = 20
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Обнаружение консолидации - длительное боковое движение
        
        Консолидация = цена движется в узком диапазоне длительное время
        
        Условия:
        1. Минимум 10+ баров
        2. Диапазон движения < 2% от средней цены
        3. Нет явного тренда
        
        Args:
            candles: Список свечей (H1, D1)
            lookback: Сколько последних свечей анализировать
            
        Returns:
            Tuple[has_consolidation, details]
        """
        try:
            if not candles or len(candles) < self.consolidation_min_bars:
                return False, {}
            
            # Берем последние N свечей
            recent_candles = candles[-lookback:] if len(candles) > lookback else candles
            
            if len(recent_candles) < self.consolidation_min_bars:
                return False, {}
            
            # Собираем High и Low
            highs = [float(c.high_price) for c in recent_candles]
            lows = [float(c.low_price) for c in recent_candles]
            
            max_high = max(highs)
            min_low = min(lows)
            
            # Средняя цена
            closes = [float(c.close_price) for c in recent_candles]
            avg_close = mean(closes)
            
            # Диапазон консолидации
            consolidation_range = max_high - min_low
            range_percent = consolidation_range / avg_close
            
            # Проверяем условия консолидации
            has_consolidation = (
                len(recent_candles) >= self.consolidation_min_bars and
                range_percent <= self.consolidation_max_range
            )
            
            # Дополнительная проверка - нет явного тренда
            if has_consolidation:
                first_half = closes[:len(closes)//2]
                second_half = closes[len(closes)//2:]
                
                avg_first = mean(first_half)
                avg_second = mean(second_half)
                
                trend_percent = abs(avg_second - avg_first) / avg_first
                
                # Если есть сильный тренд (>1.5%) - это не консолидация
                if trend_percent > 0.015:
                    has_consolidation = False
            
            details = {
                "bars_count": len(recent_candles),
                "range_percent": range_percent * 100,
                "max_high": max_high,
                "min_low": min_low,
                "avg_close": avg_close
            }
            
            if has_consolidation:
                self.stats["consolidations_detected"] += 1
                self.stats["total_patterns"] += 1
                
                logger.info(f"✅ Консолидация обнаружена: {len(recent_candles)} баров, "
                          f"диапазон {range_percent*100:.2f}%")
            
            return has_consolidation, details
            
        except Exception as e:
            logger.error(f"❌ Ошибка детекции консолидации: {e}")
            return False, {}
    
    # ==================== V-ФОРМАЦИЯ ====================
    
    def detect_v_formation(
        self,
        candles: List,
        lookback: int = 10
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Обнаружение V-формации - резкий разворот без консолидации
        
        V-формация = быстрое падение/рост с последующим резким разворотом
        
        Условия:
        1. Сильное движение в одну сторону (>3%)
        2. Резкий разворот без консолидации
        3. Движение в обратную сторону (>70% от первого движения)
        
        Args:
            candles: Список свечей (M30, H1)
            lookback: Сколько последних свечей анализировать
            
        Returns:
            Tuple[has_v_formation, details]
        """
        try:
            if not candles or len(candles) < 5:
                return False, {}
            
            # Берем последние N свечей
            recent_candles = candles[-lookback:] if len(candles) > lookback else candles
            
            if len(recent_candles) < 5:
                return False, {}
            
            closes = [float(c.close_price) for c in recent_candles]
            
            # Ищем экстремум (дно или вершину V)
            highs = [float(c.high_price) for c in recent_candles]
            lows = [float(c.low_price) for c in recent_candles]
            
            max_high = max(highs)
            min_low = min(lows)
            max_high_idx = highs.index(max_high)
            min_low_idx = lows.index(min_low)
            
            has_v_formation = False
            v_type = None
            details = {}
            
            # V-формация вниз-вверх (дно)
            if min_low_idx > 0 and min_low_idx < len(recent_candles) - 2:
                # Движение до экстремума
                before = closes[:min_low_idx+1]
                # Движение после экстремума
                after = closes[min_low_idx:]
                
                if before and after:
                    down_move_percent = (before[0] - min_low) / before[0]
                    up_move_percent = (after[-1] - min_low) / min_low
                    
                    # Проверяем условия V-формации
                    if (down_move_percent >= self.v_min_move and
                        up_move_percent >= self.v_min_move * 0.7):
                        
                        has_v_formation = True
                        v_type = "bullish_v"
                        
                        details = {
                            "v_type": v_type,
                            "down_move_percent": down_move_percent * 100,
                            "up_move_percent": up_move_percent * 100,
                            "bottom_price": min_low,
                            "bottom_index": min_low_idx
                        }
            
            # V-формация вверх-вниз (вершина)
            if not has_v_formation and max_high_idx > 0 and max_high_idx < len(recent_candles) - 2:
                # Движение до экстремума
                before = closes[:max_high_idx+1]
                # Движение после экстремума
                after = closes[max_high_idx:]
                
                if before and after:
                    up_move_percent = (max_high - before[0]) / before[0]
                    down_move_percent = (max_high - after[-1]) / max_high
                    
                    # Проверяем условия V-формации
                    if (up_move_percent >= self.v_min_move and
                        down_move_percent >= self.v_min_move * 0.7):
                        
                        has_v_formation = True
                        v_type = "bearish_v"
                        
                        details = {
                            "v_type": v_type,
                            "up_move_percent": up_move_percent * 100,
                            "down_move_percent": down_move_percent * 100,
                            "top_price": max_high,
                            "top_index": max_high_idx
                        }
            
            if has_v_formation:
                self.stats["v_formations_detected"] += 1
                self.stats["total_patterns"] += 1
                
                logger.info(f"✅ V-формация обнаружена: {v_type}")
            
            return has_v_formation, details
            
        except Exception as e:
            logger.error(f"❌ Ошибка детекции V-формации: {e}")
            return False, {}
    
    # ==================== ДОПОЛНИТЕЛЬНЫЕ ПРОВЕРКИ ====================
    
    def check_close_near_level(
        self,
        candle: Any,
        level: SupportResistanceLevel,
        tolerance_percent: float = 0.5
    ) -> bool:
        """
        Проверка что свеча закрылась вблизи уровня
        
        Args:
            candle: Свеча для проверки
            level: Уровень
            tolerance_percent: Допуск в процентах
            
        Returns:
            True если закрытие у уровня
        """
        try:
            close_price = float(candle.close_price)
            distance_percent = abs(close_price - level.price) / level.price * 100
            
            is_near = distance_percent <= tolerance_percent
            
            if is_near:
                logger.debug(f"✅ Закрытие у уровня: {close_price:.2f} vs {level.price:.2f} "
                           f"(distance={distance_percent:.2f}%)")
            
            return is_near
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки закрытия: {e}")
            return False
    
    def check_close_near_extreme(
        self,
        candle: Any,
        max_pullback_percent: float = 10.0
    ) -> Tuple[bool, str]:
        """
        Проверка что свеча закрылась под самый Hi/Low без отката
        
        Для пробоя важно что закрытие близко к экстремуму (откат < 10%)
        
        Args:
            candle: Свеча для проверки
            max_pullback_percent: Максимальный откат в %
            
        Returns:
            Tuple[is_near_extreme, extreme_type ("high" или "low")]
        """
        try:
            high = float(candle.high_price)
            low = float(candle.low_price)
            close = float(candle.close_price)
            
            candle_range = high - low
            
            if candle_range == 0:
                return False, "none"
            
            # Откат от High
            pullback_from_high = (high - close) / candle_range * 100
            
            # Откат от Low
            pullback_from_low = (close - low) / candle_range * 100
            
            # Проверяем закрытие у High
            if pullback_from_high <= max_pullback_percent:
                logger.debug(f"✅ Закрытие у High: откат {pullback_from_high:.1f}%")
                return True, "high"
            
            # Проверяем закрытие у Low
            if pullback_from_low <= max_pullback_percent:
                logger.debug(f"✅ Закрытие у Low: откат {pullback_from_low:.1f}%")
                return True, "low"
            
            return False, "none"
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки закрытия у экстремума: {e}")
            return False, "none"
    
    # ==================== СТАТИСТИКА ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику детектора"""
        return {
            **self.stats,
            "config": {
                "compression_threshold": self.compression_threshold,
                "compression_min_bars": self.compression_min_bars,
                "cluster_tolerance_percent": self.cluster_tolerance * 100,
                "bpu_touch_tolerance_percent": self.bpu_touch_tolerance * 100,
                "consolidation_min_bars": self.consolidation_min_bars,
                "v_formation_min_move_percent": self.v_min_move * 100
            }
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.stats = {
            "compressions_detected": 0,
            "clusters_detected": 0,
            "bsu_found": 0,
            "bpu_found": 0,
            "consolidations_detected": 0,
            "v_formations_detected": 0,
            "total_patterns": 0
        }
        logger.info("🔄 Статистика PatternDetector сброшена")
    
    def __repr__(self) -> str:
        """Представление для отладки"""
        return (f"PatternDetector(total_patterns={self.stats['total_patterns']}, "
                f"compressions={self.stats['compressions_detected']}, "
                f"clusters={self.stats['clusters_detected']})")
    
    def __str__(self) -> str:
        """Человекочитаемое представление"""
        stats = self.get_stats()
        return (f"Pattern Detector:\n"
                f"  Total patterns: {stats['total_patterns']}\n"
                f"  Compressions: {stats['compressions_detected']}\n"
                f"  Clusters: {stats['clusters_detected']}\n"
                f"  BSU found: {stats['bsu_found']}\n"
                f"  BPU found: {stats['bpu_found']}\n"
                f"  Consolidations: {stats['consolidations_detected']}\n"
                f"  V-formations: {stats['v_formations_detected']}")


# Export
__all__ = [
    "PatternDetector",
    "PatternMatch",
    "BSUPattern",
    "BPUPattern"
]

logger.info("✅ Pattern Detector module loaded")
