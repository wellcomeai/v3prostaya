"""
Модели данных для торговой системы

Содержит основные структуры данных, используемые во всей системе:
- Конфигурационные модели
- Метрики и статистика
- Параметры управления рисками
- Настройки уведомлений
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Режимы торговли"""
    PAPER = "paper"           # Бумажная торговля (тестирование)
    LIVE = "live"             # Реальная торговля
    SIMULATION = "simulation"  # Симуляция с историческими данными


class MarketSession(Enum):
    """Торговые сессии"""
    ASIA = "asia"
    EUROPE = "europe" 
    US = "us"
    OVERLAP_ASIA_EUROPE = "asia_europe"
    OVERLAP_EUROPE_US = "europe_us"
    OFF_HOURS = "off_hours"


class NotificationChannel(Enum):
    """Каналы уведомлений"""
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SMS = "sms"
    DISCORD = "discord"


@dataclass
class RiskParameters:
    """Параметры управления рисками"""
    
    # Основные параметры
    max_position_size_percent: float = 5.0          # Максимальный размер позиции (% от капитала)
    max_daily_loss_percent: float = 2.0             # Максимальная дневная просадка (%)
    max_drawdown_percent: float = 10.0              # Максимальная общая просадка (%)
    
    # Stop Loss и Take Profit
    default_stop_loss_percent: float = 3.0          # Стоп-лосс по умолчанию (%)
    default_take_profit_percent: float = 5.0        # Тейк-профит по умолчанию (%)
    trailing_stop_enabled: bool = False             # Включить трейлинг-стоп
    trailing_stop_distance: float = 2.0             # Расстояние трейлинг-стопа (%)
    
    # Управление экспозицией
    max_concurrent_positions: int = 3               # Максимальное количество одновременных позиций
    max_correlation_threshold: float = 0.7          # Максимальная корреляция между позициями
    position_sizing_method: str = "fixed_percent"   # Метод расчета размера позиций
    
    # Частота торговли
    max_trades_per_day: int = 10                    # Максимальное количество сделок в день
    min_time_between_trades: int = 15               # Минимальное время между сделками (минуты)
    
    # Защитные механизмы
    enable_circuit_breaker: bool = True             # Включить автоматическую остановку
    circuit_breaker_loss_threshold: float = 5.0    # Порог потерь для остановки (%)
    emergency_stop_enabled: bool = True             # Аварийная остановка
    
    def __post_init__(self):
        """Валидация параметров после инициализации"""
        # Проверяем разумные пределы
        if self.max_position_size_percent > 20:
            logger.warning(f"⚠️ Большой размер позиции: {self.max_position_size_percent}%")
        
        if self.default_stop_loss_percent > 10:
            logger.warning(f"⚠️ Большой стоп-лосс: {self.default_stop_loss_percent}%")
        
        if self.max_daily_loss_percent > 5:
            logger.warning(f"⚠️ Высокий лимит дневных потерь: {self.max_daily_loss_percent}%")
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RiskParameters':
        """Создание из словаря"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def is_position_size_allowed(self, position_size_percent: float) -> bool:
        """Проверяет, допустим ли размер позиции"""
        return position_size_percent <= self.max_position_size_percent
    
    def calculate_position_size(self, signal_strength: float, account_balance: float, 
                              current_risk_percent: float = 0.0) -> float:
        """
        Рассчитывает размер позиции на основе параметров риска
        
        Args:
            signal_strength: Сила сигнала (0-1)
            account_balance: Баланс счета
            current_risk_percent: Текущий уровень риска в портфеле
            
        Returns:
            Рекомендуемый размер позиции в долларах
        """
        # Базовый размер на основе силы сигнала
        base_size_percent = self.max_position_size_percent * 0.5 * signal_strength
        
        # Корректировка на текущий риск
        risk_adjusted_size = base_size_percent * (1 - current_risk_percent / 100)
        
        # Применяем ограничения
        final_size_percent = min(risk_adjusted_size, self.max_position_size_percent)
        
        return account_balance * (final_size_percent / 100)


@dataclass
class NotificationSettings:
    """Настройки системы уведомлений"""
    
    # Основные каналы
    enabled_channels: Set[NotificationChannel] = field(default_factory=lambda: {NotificationChannel.TELEGRAM})
    primary_channel: NotificationChannel = NotificationChannel.TELEGRAM
    
    # Фильтры уведомлений
    min_signal_strength: float = 0.6                # Минимальная сила сигнала для уведомления
    notify_on_signal_types: Set[str] = field(default_factory=lambda: {"BUY", "SELL", "STRONG_BUY", "STRONG_SELL"})
    
    # Частота уведомлений
    max_notifications_per_hour: int = 15            # Максимальное количество уведомлений в час
    quiet_hours_start: Optional[str] = "23:00"      # Начало тихих часов (HH:MM)
    quiet_hours_end: Optional[str] = "07:00"        # Конец тихих часов (HH:MM)
    quiet_hours_emergency_only: bool = True         # В тихие часы только экстренные уведомления
    
    # Группировка уведомлений
    group_similar_signals: bool = True              # Группировать похожие сигналы
    group_time_window: int = 5                      # Окно группировки (минуты)
    
    # Форматирование
    include_charts: bool = False                    # Включать графики (если поддерживается)
    include_technical_details: bool = True          # Включать технические детали
    message_format: str = "detailed"               # "brief", "detailed", "full"
    
    # Настройки каналов
    telegram_settings: Dict[str, Any] = field(default_factory=dict)
    email_settings: Dict[str, Any] = field(default_factory=dict)
    webhook_settings: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Инициализация настроек по умолчанию"""
        if not self.telegram_settings:
            self.telegram_settings = {
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
                "disable_notification": False
            }
    
    def is_notification_allowed(self, signal_strength: float, signal_type: str, 
                               current_time: Optional[datetime] = None) -> bool:
        """
        Проверяет, разрешено ли уведомление
        
        Args:
            signal_strength: Сила сигнала
            signal_type: Тип сигнала
            current_time: Текущее время (для проверки тихих часов)
            
        Returns:
            True если уведомление разрешено
        """
        # Проверка минимальной силы
        if signal_strength < self.min_signal_strength:
            return False
        
        # Проверка типа сигнала
        if signal_type not in self.notify_on_signal_types:
            return False
        
        # Проверка тихих часов
        if self.quiet_hours_start and self.quiet_hours_end and current_time:
            if self._is_quiet_hours(current_time):
                # В тихие часы только критические уведомления
                return signal_strength >= 0.9 if self.quiet_hours_emergency_only else True
        
        return True
    
    def _is_quiet_hours(self, current_time: datetime) -> bool:
        """Проверяет, попадает ли время в тихие часы"""
        try:
            current_hour_min = current_time.strftime("%H:%M")
            
            start_time = self.quiet_hours_start
            end_time = self.quiet_hours_end
            
            if start_time <= end_time:
                # Обычный случай: 23:00 - 07:00 следующего дня
                return start_time <= current_hour_min <= end_time
            else:
                # Переход через полночь: 23:00 - 07:00
                return current_hour_min >= start_time or current_hour_min <= end_time
                
        except Exception:
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь"""
        data = asdict(self)
        # Преобразуем Set в list для сериализации
        data["enabled_channels"] = [ch.value for ch in self.enabled_channels]
        data["notify_on_signal_types"] = list(self.notify_on_signal_types)
        data["primary_channel"] = self.primary_channel.value
        return data


@dataclass 
class StrategyConfig:
    """Конфигурация торговой стратегии"""
    
    # Основные параметры
    name: str
    enabled: bool = True
    symbol: str = "BTCUSDT"
    
    # Параметры сигналов
    min_signal_strength: float = 0.5
    signal_cooldown_minutes: int = 5
    max_signals_per_hour: int = 12
    
    # Специфичные параметры стратегии
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    
    # Управление рисками для стратегии
    risk_params: Optional[RiskParameters] = None
    
    # Вес стратегии в комбинированных сигналах
    strategy_weight: float = 1.0
    
    # Метаданные
    description: str = ""
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Пост-инициализация"""
        if self.risk_params is None:
            self.risk_params = RiskParameters()
    
    def update_params(self, **kwargs):
        """Обновляет параметры стратегии"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
                self.updated_at = datetime.now()
    
    def update_strategy_params(self, **kwargs):
        """Обновляет специфичные параметры стратегии"""
        self.strategy_params.update(kwargs)
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь"""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StrategyConfig':
        """Создание из словаря"""
        # Преобразуем строки обратно в datetime
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        
        # Создаем RiskParameters если есть
        if "risk_params" in data and isinstance(data["risk_params"], dict):
            data["risk_params"] = RiskParameters.from_dict(data["risk_params"])
        
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MarketCondition:
    """Текущие условия рынка"""
    
    # Основные показатели
    price: float
    volume_24h: float
    price_change_1h: float = 0.0
    price_change_24h: float = 0.0
    price_change_7d: float = 0.0
    
    # Волатильность
    volatility_1h: float = 0.0
    volatility_24h: float = 0.0
    volatility_7d: float = 0.0
    
    # Тренды
    trend_short: str = "neutral"      # "bullish", "bearish", "neutral"
    trend_medium: str = "neutral"
    trend_long: str = "neutral"
    
    # Настроения рынка
    fear_greed_index: Optional[int] = None        # 0-100
    market_sentiment: str = "neutral"             # "bullish", "bearish", "neutral"
    
    # Ликвидность и спреды
    bid_ask_spread: float = 0.0
    market_depth: float = 0.0
    
    # Торговая активность
    trades_count_24h: int = 0
    large_trades_ratio: float = 0.0               # Доля крупных сделок
    
    # Метаданные
    timestamp: datetime = field(default_factory=datetime.now)
    data_sources: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Автоматическое определение условий рынка"""
        self.market_sentiment = self._calculate_market_sentiment()
        self.trend_short = self._determine_short_trend()
    
    def _calculate_market_sentiment(self) -> str:
        """Определяет общие настроения рынка"""
        # Простой алгоритм на основе изменений цены
        if self.price_change_24h > 5:
            return "very_bullish"
        elif self.price_change_24h > 2:
            return "bullish"
        elif self.price_change_24h < -5:
            return "very_bearish"
        elif self.price_change_24h < -2:
            return "bearish"
        else:
            return "neutral"
    
    def _determine_short_trend(self) -> str:
        """Определяет краткосрочный тренд"""
        if self.price_change_1h > 1:
            return "bullish"
        elif self.price_change_1h < -1:
            return "bearish"
        else:
            return "neutral"
    
    def is_high_volatility(self) -> bool:
        """Проверяет, высокая ли волатильность"""
        return self.volatility_24h > 3.0  # Более 3% волатильности
    
    def is_trending_market(self) -> bool:
        """Проверяет, находится ли рынок в тренде"""
        return abs(self.price_change_24h) > 2.0
    
    def get_market_phase(self) -> str:
        """Определяет фазу рынка"""
        if self.is_high_volatility():
            if self.is_trending_market():
                return "trending_volatile"
            else:
                return "ranging_volatile"
        else:
            if self.is_trending_market():
                return "trending_stable" 
            else:
                return "ranging_stable"
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь"""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass
class SignalMetrics:
    """Метрики торговых сигналов"""
    
    # Основные метрики
    total_signals: int = 0
    signals_sent: int = 0
    signals_rejected: int = 0
    
    # Распределение по типам
    buy_signals: int = 0
    sell_signals: int = 0
    strong_buy_signals: int = 0
    strong_sell_signals: int = 0
    neutral_signals: int = 0
    
    # Качественные показатели
    average_signal_strength: float = 0.0
    average_confidence: float = 0.0
    average_quality_score: float = 0.0
    
    # Временные метрики
    average_processing_time: float = 0.0          # В секундах
    signals_per_hour: float = 0.0
    
    # Эффективность фильтров
    filter_rejection_rate: float = 0.0
    most_active_filter: str = ""
    
    # Эффективность стратегий
    strategy_performance: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Временные окна
    last_24h: Dict[str, int] = field(default_factory=dict)
    last_7d: Dict[str, int] = field(default_factory=dict)
    
    # Метаданные
    calculation_time: datetime = field(default_factory=datetime.now)
    period_start: datetime = field(default_factory=lambda: datetime.now() - timedelta(days=1))
    period_end: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Автоматические вычисления"""
        if not self.last_24h:
            self.last_24h = {"total": 0, "sent": 0, "rejected": 0}
        if not self.last_7d:
            self.last_7d = {"total": 0, "sent": 0, "rejected": 0}
    
    @property
    def success_rate(self) -> float:
        """Процент успешно отправленных сигналов"""
        if self.total_signals == 0:
            return 0.0
        return (self.signals_sent / self.total_signals) * 100
    
    @property
    def rejection_rate(self) -> float:
        """Процент отклоненных сигналов"""
        if self.total_signals == 0:
            return 0.0
        return (self.signals_rejected / self.total_signals) * 100
    
    def add_signal_data(self, signal_type: str, strength: float, confidence: float, 
                       quality_score: float, processing_time: float):
        """Добавляет данные нового сигнала"""
        self.total_signals += 1
        
        # Обновляем распределение по типам
        type_mapping = {
            "BUY": "buy_signals",
            "SELL": "sell_signals", 
            "STRONG_BUY": "strong_buy_signals",
            "STRONG_SELL": "strong_sell_signals",
            "NEUTRAL": "neutral_signals"
        }
        
        if signal_type in type_mapping:
            current_value = getattr(self, type_mapping[signal_type])
            setattr(self, type_mapping[signal_type], current_value + 1)
        
        # Обновляем средние значения (скользящие средние)
        self._update_average("average_signal_strength", strength)
        self._update_average("average_confidence", confidence)
        self._update_average("average_quality_score", quality_score)
        self._update_average("average_processing_time", processing_time)
    
    def _update_average(self, field_name: str, new_value: float):
        """Обновляет скользящее среднее"""
        current_avg = getattr(self, field_name)
        if self.total_signals == 1:
            setattr(self, field_name, new_value)
        else:
            # Простое скользящее среднее
            new_avg = (current_avg * (self.total_signals - 1) + new_value) / self.total_signals
            setattr(self, field_name, round(new_avg, 4))
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь"""
        data = asdict(self)
        data["calculation_time"] = self.calculation_time.isoformat()
        data["period_start"] = self.period_start.isoformat()
        data["period_end"] = self.period_end.isoformat()
        data["success_rate"] = self.success_rate
        data["rejection_rate"] = self.rejection_rate
        return data


@dataclass
class SystemConfig:
    """Общая конфигурация торговой системы"""
    
    # Основные настройки
    system_name: str = "Advanced Trading System"
    version: str = "2.1.0"
    trading_mode: TradingMode = TradingMode.PAPER
    environment: str = "production"  # "development", "testing", "production"
    
    # Рыночные настройки
    default_symbol: str = "BTCUSDT"
    supported_symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    market_data_update_interval: int = 1  # секунды
    
    # Настройки стратегий
    max_concurrent_strategies: int = 5
    strategy_configs: Dict[str, StrategyConfig] = field(default_factory=dict)
    
    # Управление рисками
    global_risk_params: RiskParameters = field(default_factory=RiskParameters)
    
    # Уведомления
    notification_settings: NotificationSettings = field(default_factory=NotificationSettings)
    
    # Хранение данных
    data_retention_days: int = 30
    metrics_update_interval: int = 300  # 5 минут
    backup_enabled: bool = True
    backup_interval_hours: int = 6
    
    # API и интеграции
    bybit_testnet: bool = True
    api_rate_limits: Dict[str, int] = field(default_factory=lambda: {
        "market_data": 1200,  # requests per minute
        "trading": 600,
        "websocket": 10
    })
    
    # Системные настройки
    log_level: str = "INFO"
    debug_mode: bool = False
    performance_monitoring: bool = True
    
    # Временные настройки
    timezone: str = "UTC"
    trading_hours: Dict[str, str] = field(default_factory=lambda: {
        "start": "00:00",
        "end": "23:59"
    })
    
    # Метаданные
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    config_version: int = 1
    
    def __post_init__(self):
        """Валидация и настройка после инициализации"""
        # Проверяем настройки
        if self.trading_mode == TradingMode.LIVE and self.bybit_testnet:
            logger.warning("⚠️ LIVE режим с testnet API - проверьте настройки!")
        
        # Настраиваем логирование
        if self.debug_mode:
            self.log_level = "DEBUG"
    
    def add_strategy_config(self, config: StrategyConfig):
        """Добавляет конфигурацию стратегии"""
        self.strategy_configs[config.name] = config
        self.updated_at = datetime.now()
        logger.info(f"➕ Добавлена конфигурация стратегии: {config.name}")
    
    def update_strategy_config(self, name: str, **kwargs):
        """Обновляет конфигурацию стратегии"""
        if name in self.strategy_configs:
            self.strategy_configs[name].update_params(**kwargs)
            self.updated_at = datetime.now()
            logger.info(f"🔧 Обновлена конфигурация стратегии: {name}")
        else:
            logger.warning(f"⚠️ Стратегия {name} не найдена")
    
    def enable_strategy(self, name: str, enabled: bool = True):
        """Включает/выключает стратегию"""
        if name in self.strategy_configs:
            self.strategy_configs[name].enabled = enabled
            self.updated_at = datetime.now()
            status = "включена" if enabled else "выключена"
            logger.info(f"🔧 Стратегия {name} {status}")
        else:
            logger.warning(f"⚠️ Стратегия {name} не найдена")
    
    def get_enabled_strategies(self) -> List[str]:
        """Возвращает список включенных стратегий"""
        return [name for name, config in self.strategy_configs.items() if config.enabled]
    
    def validate_config(self) -> Dict[str, Any]:
        """Валидирует конфигурацию системы"""
        issues = []
        warnings = []
        
        # Проверяем критичные настройки
        if self.trading_mode == TradingMode.LIVE:
            if self.bybit_testnet:
                issues.append("LIVE режим не должен использовать testnet")
            if not self.global_risk_params.emergency_stop_enabled:
                warnings.append("Рекомендуется включить аварийную остановку для LIVE режима")
        
        # Проверяем лимиты
        if self.global_risk_params.max_position_size_percent > 10:
            warnings.append(f"Большой максимальный размер позиции: {self.global_risk_params.max_position_size_percent}%")
        
        # Проверяем стратегии
        enabled_strategies = self.get_enabled_strategies()
        if len(enabled_strategies) == 0:
            issues.append("Нет включенных стратегий")
        elif len(enabled_strategies) > self.max_concurrent_strategies:
            issues.append(f"Слишком много стратегий: {len(enabled_strategies)} > {self.max_concurrent_strategies}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "enabled_strategies_count": len(enabled_strategies),
            "trading_mode": self.trading_mode.value
        }
    
    def save_to_file(self, file_path: Union[str, Path]):
        """Сохраняет конфигурацию в файл"""
        try:
            config_data = self.to_dict()
            
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"💾 Конфигурация сохранена: {file_path}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения конфигурации: {e}")
    
    @classmethod
    def load_from_file(cls, file_path: Union[str, Path]) -> 'SystemConfig':
        """Загружает конфигурацию из файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Преобразуем специальные типы
            if "trading_mode" in config_data:
                config_data["trading_mode"] = TradingMode(config_data["trading_mode"])
            
            if "global_risk_params" in config_data:
                config_data["global_risk_params"] = RiskParameters.from_dict(config_data["global_risk_params"])
            
            if "notification_settings" in config_data:
                ns_data = config_data["notification_settings"]
                # Восстанавливаем Set и Enum
                if "enabled_channels" in ns_data:
                    ns_data["enabled_channels"] = {NotificationChannel(ch) for ch in ns_data["enabled_channels"]}
                if "primary_channel" in ns_data:
                    ns_data["primary_channel"] = NotificationChannel(ns_data["primary_channel"])
                if "notify_on_signal_types" in ns_data:
                    ns_data["notify_on_signal_types"] = set(ns_data["notify_on_signal_types"])
                
                config_data["notification_settings"] = NotificationSettings(**ns_data)
            
            if "strategy_configs" in config_data:
                strategy_configs = {}
                for name, strategy_data in config_data["strategy_configs"].items():
                    strategy_configs[name] = StrategyConfig.from_dict(strategy_data)
                config_data["strategy_configs"] = strategy_configs
            
            # Преобразуем datetime поля
            datetime_fields = ["created_at", "updated_at"]
            for field in datetime_fields:
                if field in config_data and isinstance(config_data[field], str):
                    config_data[field] = datetime.fromisoformat(config_data[field])
            
            logger.info(f"📂 Конфигурация загружена: {file_path}")
            return cls(**{k: v for k, v in config_data.items() if k in cls.__dataclass_fields__})
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
            raise
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь для сериализации"""
        data = asdict(self)
        
        # Преобразуем специальные типы
        data["trading_mode"] = self.trading_mode.value
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        
        # Преобразуем стратегии
        data["strategy_configs"] = {
            name: config.to_dict() for name, config in self.strategy_configs.items()
        }
        
        # Преобразуем настройки уведомлений
        data["notification_settings"] = self.notification_settings.to_dict()
        
        return data
    
    def __str__(self):
        """Строковое представление конфигурации"""
        enabled_count = len(self.get_enabled_strategies())
        return (f"SystemConfig(mode={self.trading_mode.value}, "
                f"env={self.environment}, "
                f"strategies={enabled_count}, "
                f"symbol={self.default_symbol})")


# Утилиты для работы с моделями данных

def create_default_system_config() -> SystemConfig:
    """Создает конфигурацию системы по умолчанию"""
    config = SystemConfig()
    
    # Добавляем базовые стратегии
    momentum_config = StrategyConfig(
        name="MomentumStrategy",
        description="Импульсная торговая стратегия",
        strategy_params={
            "extreme_movement_threshold": 2.0,
            "impulse_1m_threshold": 1.5,
            "impulse_5m_threshold": 2.0,
            "high_volume_threshold": 20000,
            "enable_volume_analysis": True,
            "enable_orderbook_analysis": True
        }
    )
    config.add_strategy_config(momentum_config)
    
    return config

def validate_data_model(instance: Any, model_class: type) -> Dict[str, Any]:
    """
    Валидирует экземпляр модели данных
    
    Args:
        instance: Экземпляр для валидации
        model_class: Класс модели
        
    Returns:
        Результаты валидации
    """
    try:
        if not isinstance(instance, model_class):
            return {
                "valid": False,
                "error": f"Ожидается {model_class.__name__}, получен {type(instance).__name__}"
            }
        
        # Проверяем обязательные поля
        missing_fields = []
        for field_name, field_info in model_class.__dataclass_fields__.items():
            if field_info.default == field_info.default_factory == dataclass.MISSING:
                if not hasattr(instance, field_name) or getattr(instance, field_name) is None:
                    missing_fields.append(field_name)
        
        if missing_fields:
            return {
                "valid": False,
                "error": f"Отсутствуют обязательные поля: {missing_fields}"
            }
        
        return {"valid": True}
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"Ошибка валидации: {str(e)}"
        }
