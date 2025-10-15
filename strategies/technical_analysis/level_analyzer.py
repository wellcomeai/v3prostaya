"""
Level Analyzer - Support and Resistance Level Detection

Анализатор уровней поддержки и сопротивления для торговых стратегий.

Функциональность:
1. Поиск локальных экстремумов (максимумы/минимумы)
2. Кластеризация близких уровней
3. Подсчет касаний (touches) каждого уровня
4. Расчет силы уровня (strength)
5. Идентификация БСУ (Бар Создавший Уровень)
6. Определение времени последнего касания (для анализа ретеста)

Типы уровней:
- Support: уровни поддержки (локальные минимумы)
- Resistance: уровни сопротивления (локальные максимумы)

Author: Trading Bot Team
Version: 1.0.0
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from collections import defaultdict

from .context import SupportResistanceLevel

logger = logging.getLogger(__name__)


@dataclass
class LevelCandidate:
    """
    Кандидат на уровень (промежуточная структура)
    
    Используется внутри анализа перед созданием финального SupportResistanceLevel
    """
    price: float
    level_type: str  # "support" или "resistance"
    touches: List[datetime] = None  # Времена касаний
    touch_prices: List[float] = None  # Точные цены касаний
    created_at: Optional[datetime] = None  # БСУ - когда создан уровень
    
    def __post_init__(self):
        if self.touches is None:
            self.touches = []
        if self.touch_prices is None:
            self.touch_prices = []
    
    @property
    def touch_count(self) -> int:
        return len(self.touches)
    
    @property
    def last_touch(self) -> Optional[datetime]:
        return self.touches[-1] if self.touches else None


class LevelAnalyzer:
    """
    🎯 Анализатор уровней поддержки/сопротивления
    
    Находит значимые уровни на графике для торговых стратегий.
    
    Алгоритм:
    1. Поиск локальных экстремумов (максимумы/минимумы)
    2. Кластеризация близких уровней (группировка)
    3. Подсчет касаний каждого уровня
    4. Расчет силы уровня
    5. Фильтрация слабых уровней
    
    Usage:
        analyzer = LevelAnalyzer()
        levels = analyzer.find_all_levels(candles_d1, min_touches=2)
        
        for level in levels:
            print(f"{level.level_type}: {level.price:.2f}, strength={level.strength:.2f}")
    """
    
    def __init__(
        self,
        min_touches: int = 2,              # Минимум касаний для валидного уровня
        min_strength: float = 0.3,          # Минимальная сила уровня (0.0-1.0)
        touch_tolerance_percent: float = 0.5,  # Допуск касания в % (0.5% = 50 пунктов при цене 10000)
        cluster_tolerance_percent: float = 1.0,  # Допуск кластеризации в %
        lookback_window: int = 10,          # Окно для поиска локальных экстремумов
        max_levels_per_type: int = 10,      # Максимум уровней каждого типа
        min_level_distance_percent: float = 2.0,  # Мин. расстояние между уровнями (%)
    ):
        """
        Инициализация анализатора
        
        Args:
            min_touches: Минимум касаний для валидного уровня
            min_strength: Минимальная сила уровня
            touch_tolerance_percent: Допуск для определения касания
            cluster_tolerance_percent: Допуск для кластеризации уровней
            lookback_window: Окно для поиска локальных экстремумов
            max_levels_per_type: Максимум уровней каждого типа
            min_level_distance_percent: Минимальное расстояние между уровнями
        """
        self.min_touches = min_touches
        self.min_strength = min_strength
        self.touch_tolerance = touch_tolerance_percent / 100.0
        self.cluster_tolerance = cluster_tolerance_percent / 100.0
        self.lookback_window = lookback_window
        self.max_levels_per_type = max_levels_per_type
        self.min_level_distance = min_level_distance_percent / 100.0
        
        # Статистика
        self.stats = {
            "analyses_count": 0,
            "total_levels_found": 0,
            "support_levels_found": 0,
            "resistance_levels_found": 0,
            "average_level_strength": 0.0,
            "strong_levels_count": 0,
            "candidates_clustered": 0
        }
        
        logger.info("🎯 LevelAnalyzer инициализирован")
        logger.info(f"   • Min touches: {min_touches}")
        logger.info(f"   • Min strength: {min_strength}")
        logger.info(f"   • Touch tolerance: {touch_tolerance_percent}%")
        logger.info(f"   • Cluster tolerance: {cluster_tolerance_percent}%")
        logger.info(f"   • Lookback window: {lookback_window}")
    
    # ==================== ОСНОВНОЙ МЕТОД ====================
    
    def find_all_levels(
        self,
        candles: List,
        min_touches: Optional[int] = None,
        min_strength: Optional[float] = None,
        current_price: Optional[float] = None
    ) -> List[SupportResistanceLevel]:
        """
        🔍 Найти все уровни поддержки и сопротивления
        
        Основной метод анализа - выполняет полный цикл:
        1. Поиск локальных экстремумов
        2. Кластеризация близких уровней
        3. Подсчет касаний
        4. Расчет силы
        5. Фильтрация
        
        Args:
            candles: Список свечей D1 (рекомендуется 60-180 свечей)
            min_touches: Переопределить минимум касаний
            min_strength: Переопределить минимальную силу
            current_price: Текущая цена (для расчета расстояний)
            
        Returns:
            Список найденных уровней SupportResistanceLevel
        """
        try:
            self.stats["analyses_count"] += 1
            
            # Валидация входных данных
            if not candles or len(candles) < 20:
                logger.warning(f"⚠️ Недостаточно свечей для анализа: {len(candles)}")
                return []
            
            logger.info(f"🔍 Анализ уровней на {len(candles)} свечах D1")
            
            # Используем переданные параметры или дефолтные
            min_touches = min_touches or self.min_touches
            min_strength = min_strength or self.min_strength
            
            # Определяем текущую цену если не передана
            if current_price is None:
                current_price = float(candles[-1]['close_price'])
            
            # ШАГ 1: Поиск локальных экстремумов
            support_candidates = self._find_local_minima(candles)
            resistance_candidates = self._find_local_maxima(candles)
            
            logger.debug(f"📊 Найдено кандидатов: support={len(support_candidates)}, resistance={len(resistance_candidates)}")
            
            # ШАГ 2: Кластеризация близких уровней
            support_clusters = self._cluster_levels(support_candidates, candles)
            resistance_clusters = self._cluster_levels(resistance_candidates, candles)
            
            logger.debug(f"📊 После кластеризации: support={len(support_clusters)}, resistance={len(resistance_clusters)}")
            self.stats["candidates_clustered"] += (len(support_candidates) - len(support_clusters)) + \
                                                   (len(resistance_candidates) - len(resistance_clusters))
            
            # ШАГ 3: Подсчет касаний для каждого кластера
            support_levels = []
            for cluster in support_clusters:
                touches = self._count_touches(cluster, candles, "support")
                cluster.touches = touches
            
            resistance_levels = []
            for cluster in resistance_clusters:
                touches = self._count_touches(cluster, candles, "resistance")
                cluster.touches = touches
            
            # ШАГ 4: Расчет силы уровней
            for level in support_clusters:
                strength = self._calculate_level_strength(level, candles)
                
                # Создаем финальный уровень
                sr_level = self._create_support_resistance_level(
                    candidate=level,
                    strength=strength,
                    current_price=current_price
                )
                
                # Фильтруем по минимальным требованиям
                if sr_level.touches >= min_touches and sr_level.strength >= min_strength:
                    support_levels.append(sr_level)
            
            for level in resistance_clusters:
                strength = self._calculate_level_strength(level, candles)
                
                sr_level = self._create_support_resistance_level(
                    candidate=level,
                    strength=strength,
                    current_price=current_price
                )
                
                if sr_level.touches >= min_touches and sr_level.strength >= min_strength:
                    resistance_levels.append(sr_level)
            
            # ШАГ 5: Фильтрация и сортировка
            support_levels = self._filter_overlapping_levels(support_levels)
            resistance_levels = self._filter_overlapping_levels(resistance_levels)
            
            # Сортируем по силе и берем топ-N
            support_levels.sort(key=lambda l: l.strength, reverse=True)
            resistance_levels.sort(key=lambda l: l.strength, reverse=True)
            
            support_levels = support_levels[:self.max_levels_per_type]
            resistance_levels = resistance_levels[:self.max_levels_per_type]
            
            # Объединяем все уровни
            all_levels = support_levels + resistance_levels
            
            # Обновляем статистику
            self._update_stats(support_levels, resistance_levels)
            
            logger.info(f"✅ Найдено {len(all_levels)} уровней: "
                       f"support={len(support_levels)}, resistance={len(resistance_levels)}")
            
            return all_levels
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска уровней: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    # ==================== ПОИСК ЭКСТРЕМУМОВ ====================
    
    def _find_local_minima(self, candles: List) -> List[LevelCandidate]:
        """
        Поиск локальных минимумов (уровни поддержки)
        
        Локальный минимум = свеча, у которой Low меньше чем у N свечей слева и справа
        
        Args:
            candles: Список свечей
            
        Returns:
            Список кандидатов на уровни поддержки
        """
        candidates = []
        window = self.lookback_window
        
        for i in range(window, len(candles) - window):
            current_candle = candles[i]
            current_low = float(current_candle['low_price'])
            
            # Проверяем что это локальный минимум
            is_local_min = True
            
            # Проверяем левое окно
            for j in range(i - window, i):
                if float(candles[j]['low_price']) < current_low:
                    is_local_min = False
                    break
            
            if not is_local_min:
                continue
            
            # Проверяем правое окно
            for j in range(i + 1, min(i + window + 1, len(candles))):
                if float(candles[j]['low_price']) < current_low:
                    is_local_min = False
                    break
            
            if is_local_min:
                candidate = LevelCandidate(
                    price=current_low,
                    level_type="support",
                    created_at=current_candle.open_time
                )
                candidates.append(candidate)
                
                logger.debug(f"🔹 Локальный минимум: {current_low:.2f} @ {current_candle.open_time.date()}")
        
        return candidates
    
    def _find_local_maxima(self, candles: List) -> List[LevelCandidate]:
        """
        Поиск локальных максимумов (уровни сопротивления)
        
        Локальный максимум = свеча, у которой High больше чем у N свечей слева и справа
        
        Args:
            candles: Список свечей
            
        Returns:
            Список кандидатов на уровни сопротивления
        """
        candidates = []
        window = self.lookback_window
        
        for i in range(window, len(candles) - window):
            current_candle = candles[i]
            current_high = float(current_candle['high_price'])
            
            # Проверяем что это локальный максимум
            is_local_max = True
            
            # Проверяем левое окно
            for j in range(i - window, i):
                if float(candles[j]['high_price']) > current_high:
                    is_local_max = False
                    break
            
            if not is_local_max:
                continue
            
            # Проверяем правое окно
            for j in range(i + 1, min(i + window + 1, len(candles))):
                if float(candles[j]['high_price']) > current_high:
                    is_local_max = False
                    break
            
            if is_local_max:
                candidate = LevelCandidate(
                    price=current_high,
                    level_type="resistance",
                    created_at=current_candle.open_time
                )
                candidates.append(candidate)
                
                logger.debug(f"🔸 Локальный максимум: {current_high:.2f} @ {current_candle.open_time.date()}")
        
        return candidates
    
    # ==================== КЛАСТЕРИЗАЦИЯ ====================
    
    def _cluster_levels(self, candidates: List[LevelCandidate], candles: List) -> List[LevelCandidate]:
        """
        Кластеризация близких уровней
        
        Группирует уровни которые находятся близко друг к другу (в пределах tolerance).
        Для каждого кластера выбирает центральный уровень.
        
        Args:
            candidates: Список кандидатов
            candles: Список свечей (для контекста)
            
        Returns:
            Отфильтрованный список уровней после кластеризации
        """
        if not candidates:
            return []
        
        # Сортируем по цене
        sorted_candidates = sorted(candidates, key=lambda c: c.price)
        
        clusters = []
        current_cluster = [sorted_candidates[0]]
        
        for i in range(1, len(sorted_candidates)):
            current = sorted_candidates[i]
            prev = current_cluster[-1]
            
            # Проверяем расстояние между уровнями
            distance_percent = abs(current.price - prev.price) / prev.price
            
            if distance_percent <= self.cluster_tolerance:
                # Добавляем в текущий кластер
                current_cluster.append(current)
            else:
                # Закрываем кластер и начинаем новый
                clusters.append(current_cluster)
                current_cluster = [current]
        
        # Добавляем последний кластер
        if current_cluster:
            clusters.append(current_cluster)
        
        # Для каждого кластера выбираем центральный уровень
        clustered_levels = []
        
        for cluster in clusters:
            if len(cluster) == 1:
                clustered_levels.append(cluster[0])
            else:
                # Выбираем медианный уровень
                cluster_prices = [c.price for c in cluster]
                median_price = sorted(cluster_prices)[len(cluster_prices) // 2]
                
                # Находим ближайший к медиане
                closest = min(cluster, key=lambda c: abs(c.price - median_price))
                
                # Объединяем времена создания (выбираем самое раннее)
                earliest_time = min(c.created_at for c in cluster if c.created_at)
                closest.created_at = earliest_time
                
                clustered_levels.append(closest)
                
                logger.debug(f"📍 Кластер из {len(cluster)} уровней → {closest.price:.2f}")
        
        return clustered_levels
    
    # ==================== ПОДСЧЕТ КАСАНИЙ ====================
    
    def _count_touches(
        self,
        level: LevelCandidate,
        candles: List,
        level_type: str
    ) -> List[datetime]:
        """
        Подсчет касаний уровня
        
        Касание = когда цена приближается к уровню в пределах tolerance
        
        Args:
            level: Кандидат на уровень
            candles: Список свечей
            level_type: "support" или "resistance"
            
        Returns:
            Список времен касаний
        """
        touches = []
        tolerance = level.price * self.touch_tolerance
        
        for candle in candles:
            if level_type == "support":
                # Для поддержки смотрим на Low
                price = float(candle['low_price'])
            else:
                # Для сопротивления смотрим на High
                price = float(candle['high_price'])
            
            # Проверяем касание
            distance = abs(price - level.price)
            
            if distance <= tolerance:
                touches.append(candle.open_time)
                logger.debug(f"👉 Касание {level_type} {level.price:.2f} @ {candle.open_time.date()}")
        
        return touches
    
    # ==================== РАСЧЕТ СИЛЫ УРОВНЯ ====================
    
    def _calculate_level_strength(self, level: LevelCandidate, candles: List) -> float:
        """
        Расчет силы уровня (0.0 - 1.0)
        
        Факторы силы:
        1. Количество касаний (больше = сильнее)
        2. Временной диапазон (чем дольше держится = сильнее)
        3. Недавность касаний (недавние = сильнее)
        4. Четкость касаний (точные касания = сильнее)
        
        Args:
            level: Кандидат на уровень
            candles: Список свечей
            
        Returns:
            Сила уровня (0.0 - 1.0)
        """
        if not level.touches:
            return 0.0
        
        # Базовая сила = количество касаний (нормализовано)
        # 2 касания = 0.3, 3 = 0.5, 5 = 0.7, 10+ = 1.0
        touch_score = min(level.touch_count / 10.0, 1.0)
        
        # Бонус за множественные касания
        if level.touch_count >= 5:
            touch_score = min(touch_score + 0.2, 1.0)
        
        # Временной диапазон (чем дольше существует уровень = сильнее)
        if len(level.touches) >= 2:
            first_touch = level.touches[0]
            last_touch = level.touches[-1]
            time_span_days = (last_touch - first_touch).days
            
            # Нормализуем: 7 дней = 0.1, 30 дней = 0.5, 90+ дней = 1.0
            time_score = min(time_span_days / 90.0, 1.0) * 0.3
        else:
            time_score = 0.0
        
        # Недавность последнего касания
        if level.touches:
            days_since_last = (datetime.now(timezone.utc) - level.touches[-1]).days
            
            # Недавние касания ценнее: <7 дней = 0.2, <30 дней = 0.1, >30 дней = 0
            if days_since_last < 7:
                recency_score = 0.2
            elif days_since_last < 30:
                recency_score = 0.1
            else:
                recency_score = 0.0
        else:
            recency_score = 0.0
        
        # Итоговая сила
        total_strength = touch_score * 0.6 + time_score + recency_score
        total_strength = max(0.0, min(1.0, total_strength))
        
        logger.debug(f"💪 Сила уровня {level.price:.2f}: {total_strength:.2f} "
                    f"(touches={touch_score:.2f}, time={time_score:.2f}, recency={recency_score:.2f})")
        
        return total_strength
    
    # ==================== СОЗДАНИЕ ФИНАЛЬНОГО УРОВНЯ ====================
    
    def _create_support_resistance_level(
        self,
        candidate: LevelCandidate,
        strength: float,
        current_price: float
    ) -> SupportResistanceLevel:
        """
        Создание финального SupportResistanceLevel из кандидата
        
        Args:
            candidate: Кандидат на уровень
            strength: Рассчитанная сила
            current_price: Текущая цена
            
        Returns:
            Финальный SupportResistanceLevel
        """
        # Расстояние от текущей цены
        distance_percent = abs(candidate.price - current_price) / current_price * 100
        
        # Метаданные
        metadata = {
            "touches_dates": [t.isoformat() for t in candidate.touches] if candidate.touches else [],
            "first_touch": candidate.touches[0].isoformat() if candidate.touches else None,
            "time_span_days": (candidate.touches[-1] - candidate.touches[0]).days if len(candidate.touches) >= 2 else 0
        }
        
        level = SupportResistanceLevel(
            price=candidate.price,
            level_type=candidate.level_type,
            strength=strength,
            touches=candidate.touch_count,
            last_touch=candidate.last_touch,
            created_at=candidate.created_at,
            distance_from_current=distance_percent,
            metadata=metadata
        )
        
        return level
    
    # ==================== ФИЛЬТРАЦИЯ ====================
    
    def _filter_overlapping_levels(self, levels: List[SupportResistanceLevel]) -> List[SupportResistanceLevel]:
        """
        Фильтрация слишком близких уровней
        
        Если два уровня находятся слишком близко - оставляем более сильный
        
        Args:
            levels: Список уровней
            
        Returns:
            Отфильтрованный список
        """
        if len(levels) <= 1:
            return levels
        
        # Сортируем по цене
        sorted_levels = sorted(levels, key=lambda l: l.price)
        
        filtered = [sorted_levels[0]]
        
        for level in sorted_levels[1:]:
            prev = filtered[-1]
            
            # Проверяем расстояние
            distance_percent = abs(level.price - prev.price) / prev.price
            
            if distance_percent < self.min_level_distance:
                # Слишком близко - выбираем более сильный
                if level.strength > prev.strength:
                    filtered[-1] = level
                    logger.debug(f"🔄 Заменен близкий уровень: {prev.price:.2f} → {level.price:.2f}")
            else:
                filtered.append(level)
        
        return filtered
    
    # ==================== ДОПОЛНИТЕЛЬНЫЕ МЕТОДЫ ====================
    
    def find_nearest_support(
        self,
        candles: List,
        current_price: float,
        max_distance_percent: float = 5.0
    ) -> Optional[SupportResistanceLevel]:
        """
        Найти ближайший уровень поддержки ниже текущей цены
        
        Args:
            candles: Список свечей
            current_price: Текущая цена
            max_distance_percent: Максимальное расстояние в %
            
        Returns:
            Ближайший уровень поддержки или None
        """
        all_levels = self.find_all_levels(candles, current_price=current_price)
        
        supports = [
            level for level in all_levels
            if level.level_type == "support" and level.price < current_price
        ]
        
        if not supports:
            return None
        
        # Сортируем по расстоянию от текущей цены
        supports.sort(key=lambda l: abs(l.price - current_price))
        
        nearest = supports[0]
        
        if nearest.distance_from_current <= max_distance_percent:
            return nearest
        
        return None
    
    def find_nearest_resistance(
        self,
        candles: List,
        current_price: float,
        max_distance_percent: float = 5.0
    ) -> Optional[SupportResistanceLevel]:
        """
        Найти ближайший уровень сопротивления выше текущей цены
        
        Args:
            candles: Список свечей
            current_price: Текущая цена
            max_distance_percent: Максимальное расстояние в %
            
        Returns:
            Ближайший уровень сопротивления или None
        """
        all_levels = self.find_all_levels(candles, current_price=current_price)
        
        resistances = [
            level for level in all_levels
            if level.level_type == "resistance" and level.price > current_price
        ]
        
        if not resistances:
            return None
        
        # Сортируем по расстоянию
        resistances.sort(key=lambda l: abs(l.price - current_price))
        
        nearest = resistances[0]
        
        if nearest.distance_from_current <= max_distance_percent:
            return nearest
        
        return None
    
    def find_strong_levels(
        self,
        candles: List,
        min_strength: float = 0.7
    ) -> List[SupportResistanceLevel]:
        """
        Найти все сильные уровни (strength >= min_strength)
        
        Args:
            candles: Список свечей
            min_strength: Минимальная сила (0.7 = strong)
            
        Returns:
            Список сильных уровней
        """
        all_levels = self.find_all_levels(candles)
        strong = [level for level in all_levels if level.strength >= min_strength]
        
        # Сортируем по силе
        strong.sort(key=lambda l: l.strength, reverse=True)
        
        return strong
    
    # ==================== СТАТИСТИКА ====================
    
    def _update_stats(self, support_levels: List, resistance_levels: List):
        """Обновление статистики анализатора"""
        total = len(support_levels) + len(resistance_levels)
        
        self.stats["total_levels_found"] += total
        self.stats["support_levels_found"] += len(support_levels)
        self.stats["resistance_levels_found"] += len(resistance_levels)
        
        # Средняя сила уровней
        if total > 0:
            all_levels = support_levels + resistance_levels
            avg_strength = sum(l.strength for l in all_levels) / total
            
            # Скользящее среднее
            count = self.stats["analyses_count"]
            prev_avg = self.stats["average_level_strength"]
            self.stats["average_level_strength"] = (prev_avg * (count - 1) + avg_strength) / count
            
            # Количество сильных уровней
            strong_count = sum(1 for l in all_levels if l.is_strong)
            self.stats["strong_levels_count"] += strong_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику анализатора"""
        return {
            **self.stats,
            "config": {
                "min_touches": self.min_touches,
                "min_strength": self.min_strength,
                "touch_tolerance_percent": self.touch_tolerance * 100,
                "cluster_tolerance_percent": self.cluster_tolerance * 100,
                "lookback_window": self.lookback_window,
                "max_levels_per_type": self.max_levels_per_type
            }
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.stats = {
            "analyses_count": 0,
            "total_levels_found": 0,
            "support_levels_found": 0,
            "resistance_levels_found": 0,
            "average_level_strength": 0.0,
            "strong_levels_count": 0,
            "candidates_clustered": 0
        }
        logger.info("🔄 Статистика LevelAnalyzer сброшена")
    
    def __repr__(self) -> str:
        """Представление для отладки"""
        return (f"LevelAnalyzer(analyses={self.stats['analyses_count']}, "
                f"total_levels={self.stats['total_levels_found']}, "
                f"avg_strength={self.stats['average_level_strength']:.2f})")
    
    def __str__(self) -> str:
        """Человекочитаемое представление"""
        stats = self.get_stats()
        return (f"Level Analyzer:\n"
                f"  Analyses: {stats['analyses_count']}\n"
                f"  Total levels found: {stats['total_levels_found']}\n"
                f"  Support levels: {stats['support_levels_found']}\n"
                f"  Resistance levels: {stats['resistance_levels_found']}\n"
                f"  Average strength: {stats['average_level_strength']:.2f}\n"
                f"  Strong levels: {stats['strong_levels_count']}\n"
                f"  Config: touches≥{self.min_touches}, strength≥{self.min_strength}")


# Export
__all__ = ["LevelAnalyzer", "LevelCandidate"]

logger.info("✅ Level Analyzer module loaded")
