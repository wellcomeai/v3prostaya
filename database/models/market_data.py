"""
Market Data Models

SQLAlchemy models for cryptocurrency and futures market data storage.
Supports:
- Bybit cryptocurrency data (BTCUSDT, ETHUSDT, etc.)
- YFinance futures data (MCL, MGC, MES, MNQ, etc.)

Optimized for time-series data with proper indexing and validation.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Column, String, DateTime, Numeric, BigInteger, 
    Index, UniqueConstraint, CheckConstraint, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import validates

logger = logging.getLogger(__name__)

# Base class for all models
Base = declarative_base()


class CandleInterval(Enum):
    """Supported candle intervals"""
    MINUTE_1 = "1m"
    MINUTE_3 = "3m" 
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_2 = "2h"
    HOUR_4 = "4h"
    HOUR_6 = "6h"
    HOUR_12 = "12h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"
    
    @classmethod
    def get_all_intervals(cls) -> List[str]:
        """Get all available interval values"""
        return [interval.value for interval in cls]
    
    @classmethod
    def get_short_term_intervals(cls) -> List[str]:
        """Get short-term intervals (≤ 1 hour)"""
        return [cls.MINUTE_1.value, cls.MINUTE_3.value, cls.MINUTE_5.value, 
                cls.MINUTE_15.value, cls.MINUTE_30.value, cls.HOUR_1.value]
    
    @classmethod
    def get_long_term_intervals(cls) -> List[str]:
        """Get long-term intervals (> 1 hour)"""
        return [cls.HOUR_2.value, cls.HOUR_4.value, cls.HOUR_6.value,
                cls.HOUR_12.value, cls.DAY_1.value, cls.WEEK_1.value, cls.MONTH_1.value]
    
    def to_seconds(self) -> int:
        """Convert interval to seconds"""
        interval_seconds = {
            "1m": 60,
            "3m": 180,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "2h": 7200,
            "4h": 14400,
            "6h": 21600,
            "12h": 43200,
            "1d": 86400,
            "1w": 604800,
            "1M": 2592000  # 30 days approximation
        }
        return interval_seconds.get(self.value, 0)


class DataSource(Enum):
    """🆕 Типы источников данных"""
    BYBIT = "bybit"
    YFINANCE = "yfinance"
    BINANCE = "binance"
    UNKNOWN = "unknown"


class MarketDataCandle(Base):
    """
    🚀 OHLCV Candle data model for market data (crypto + futures)
    
    Supports:
    - Bybit cryptocurrency data (BTCUSDT, ETHUSDT, etc.)
    - YFinance CME futures data (MCL, MGC, MES, MNQ, etc.)
    
    Stores time-series market data with proper indexing for fast queries.
    Optimized for large datasets with billions of candles.
    """
    
    __tablename__ = "market_data_candles"
    
    # Primary key - auto-incrementing ID
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # Market identification
    symbol = Column(String(20), nullable=False, index=True, comment="Trading symbol (e.g., BTCUSDT, MCL)")
    interval = Column(String(10), nullable=False, index=True, comment="Candle interval (1m, 5m, 1h, etc.)")
    
    # Time data
    open_time = Column(DateTime(timezone=True), nullable=False, comment="Candle open timestamp")
    close_time = Column(DateTime(timezone=True), nullable=False, comment="Candle close timestamp")
    
    # OHLCV data - using Numeric for precision in financial calculations
    open_price = Column(Numeric(20, 8), nullable=False, comment="Opening price")
    high_price = Column(Numeric(20, 8), nullable=False, comment="Highest price")
    low_price = Column(Numeric(20, 8), nullable=False, comment="Lowest price")
    close_price = Column(Numeric(20, 8), nullable=False, comment="Closing price")
    volume = Column(Numeric(20, 8), nullable=False, comment="Trading volume")
    
    # Additional market data
    quote_volume = Column(Numeric(20, 8), nullable=True, comment="Quote asset volume")
    number_of_trades = Column(BigInteger, nullable=True, comment="Number of trades")
    taker_buy_base_volume = Column(Numeric(20, 8), nullable=True, comment="Taker buy base asset volume")
    taker_buy_quote_volume = Column(Numeric(20, 8), nullable=True, comment="Taker buy quote asset volume")
    
    # 🆕 Metadata (расширено для YFinance)
    data_source = Column(String(50), nullable=True, default="bybit", comment="Data source (bybit, yfinance, binance, etc.)")
    raw_data = Column(JSONB, nullable=True, comment="Raw API response for debugging")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        # Unique constraint to prevent duplicate candles
        UniqueConstraint('symbol', 'interval', 'open_time', name='uq_candle_symbol_interval_time'),
        
        # Check constraints for data validation
        CheckConstraint('open_price > 0', name='ck_open_price_positive'),
        CheckConstraint('high_price > 0', name='ck_high_price_positive'),
        CheckConstraint('low_price > 0', name='ck_low_price_positive'),
        CheckConstraint('close_price > 0', name='ck_close_price_positive'),
        CheckConstraint('volume >= 0', name='ck_volume_non_negative'),
        CheckConstraint('high_price >= low_price', name='ck_high_gte_low'),
        CheckConstraint('high_price >= open_price', name='ck_high_gte_open'),
        CheckConstraint('high_price >= close_price', name='ck_high_gte_close'),
        CheckConstraint('low_price <= open_price', name='ck_low_lte_open'),
        CheckConstraint('low_price <= close_price', name='ck_low_lte_close'),
        CheckConstraint('close_time > open_time', name='ck_close_after_open'),
        
        # Performance indexes
        Index('idx_candles_symbol_interval_open_time', 'symbol', 'interval', 'open_time'),
        Index('idx_candles_close_time', 'close_time'),
        Index('idx_candles_symbol_close_time', 'symbol', 'close_time'),
        Index('idx_candles_created_at', 'created_at'),
        Index('idx_candles_data_source', 'data_source'),  # 🆕 Индекс по источнику
        
        # 🆕 Partial indexes for crypto (Bybit)
        Index('idx_candles_btcusdt_1m', 'open_time', postgresql_where="symbol = 'BTCUSDT' AND interval = '1m'"),
        Index('idx_candles_btcusdt_5m', 'open_time', postgresql_where="symbol = 'BTCUSDT' AND interval = '5m'"),
        Index('idx_candles_btcusdt_1h', 'open_time', postgresql_where="symbol = 'BTCUSDT' AND interval = '1h'"),
        Index('idx_candles_ethusdt_1m', 'open_time', postgresql_where="symbol = 'ETHUSDT' AND interval = '1m'"),
        
        # 🆕 Partial indexes for futures (YFinance)
        Index('idx_candles_mcl_1m', 'open_time', postgresql_where="symbol = 'MCL' AND interval = '1m'"),
        Index('idx_candles_mgc_1m', 'open_time', postgresql_where="symbol = 'MGC' AND interval = '1m'"),
        Index('idx_candles_mes_1m', 'open_time', postgresql_where="symbol = 'MES' AND interval = '1m'"),
        Index('idx_candles_mnq_1m', 'open_time', postgresql_where="symbol = 'MNQ' AND interval = '1m'"),
        
        # 🆕 Composite index по источнику и символу
        Index('idx_candles_source_symbol', 'data_source', 'symbol', 'open_time'),
        
        # Table configuration
        {
            'comment': 'OHLCV candle data for cryptocurrency and futures market analysis',
            'postgresql_partition_by': 'RANGE (open_time)',  # Ready for partitioning by time
        }
    )
    
    @validates('symbol')
    def validate_symbol(self, key: str, symbol: str) -> str:
        """
        🆕 Validate trading symbol format (crypto + futures)
        
        Supports:
        - Crypto: BTCUSDT, ETHUSDT, etc.
        - Futures: MCL, MGC, MES, MNQ, ES, NQ, CL, GC, etc.
        """
        if not symbol:
            raise ValueError("Symbol cannot be empty")
        
        symbol = symbol.upper().strip()
        
        if len(symbol) < 2 or len(symbol) > 20:
            raise ValueError("Symbol must be between 2 and 20 characters")
        
        # 🆕 Расширенная валидация для крипты и фьючерсов
        # Разрешаем буквы, цифры и символ = для фьючерсов (MCL=F)
        allowed_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789=')
        if not all(c in allowed_chars for c in symbol):
            raise ValueError("Symbol must contain only letters, numbers, and '=' (for futures)")
        
        # Список известных фьючерсных префиксов
        futures_prefixes = [
            'MCL', 'MGC', 'MES', 'MNQ',  # Micro futures
            'ES', 'NQ', 'YM', 'RTY',      # E-mini futures
            'CL', 'GC', 'SI', 'HG',       # Commodities
            'ZB', 'ZN', 'ZF', 'ZT',       # Treasuries
            'NG', 'RB', 'HO',             # Energy
            'ZC', 'ZS', 'ZW', 'ZL',       # Grains
            'LE', 'HE', 'GF'              # Livestock
        ]
        
        # Убираем суффикс =F для проверки
        base_symbol = symbol.replace('=F', '')
        
        # Проверяем что это либо крипта, либо фьючерс
        is_crypto = any(c in symbol for c in ['USDT', 'USDC', 'USD', 'BTC', 'ETH'])
        is_futures = any(base_symbol.startswith(prefix) for prefix in futures_prefixes)
        
        if not is_crypto and not is_futures:
            # Логируем предупреждение, но не блокируем
            logger.warning(f"Unknown symbol type: {symbol}. Allowing anyway.")
        
        return symbol
    
    @validates('interval')
    def validate_interval(self, key: str, interval: str) -> str:
        """Validate candle interval"""
        if not interval:
            raise ValueError("Interval cannot be empty")
        
        valid_intervals = CandleInterval.get_all_intervals()
        if interval not in valid_intervals:
            raise ValueError(f"Invalid interval '{interval}'. Valid intervals: {valid_intervals}")
        
        return interval
    
    @validates('open_price', 'high_price', 'low_price', 'close_price')
    def validate_prices(self, key: str, price: Union[Decimal, float]) -> Decimal:
        """Validate price values"""
        if price is None:
            raise ValueError(f"{key} cannot be None")
        
        price_decimal = Decimal(str(price))
        
        if price_decimal <= 0:
            raise ValueError(f"{key} must be positive")
        
        if price_decimal > Decimal('1000000000'):  # 1 billion max
            raise ValueError(f"{key} exceeds maximum allowed value")
        
        return price_decimal
    
    @validates('volume')
    def validate_volume(self, key: str, volume: Union[Decimal, float]) -> Decimal:
        """Validate volume value"""
        if volume is None:
            raise ValueError("Volume cannot be None")
        
        volume_decimal = Decimal(str(volume))
        
        if volume_decimal < 0:
            raise ValueError("Volume cannot be negative")
        
        return volume_decimal
    
    @validates('data_source')
    def validate_data_source(self, key: str, data_source: str) -> str:
        """🆕 Validate data source"""
        if not data_source:
            return "unknown"
        
        data_source = data_source.lower().strip()
        
        # Проверяем что источник известен
        valid_sources = [source.value for source in DataSource]
        if data_source not in valid_sources:
            logger.warning(f"Unknown data source: {data_source}. Using 'unknown'.")
            return "unknown"
        
        return data_source
    
    @property
    def price_change(self) -> Decimal:
        """Calculate price change (close - open)"""
        return self.close_price - self.open_price
    
    @property
    def price_change_percent(self) -> Decimal:
        """Calculate price change percentage"""
        if self.open_price == 0:
            return Decimal('0')
        return (self.price_change / self.open_price) * Decimal('100')
    
    @property
    def is_green(self) -> bool:
        """Check if candle is green (bullish)"""
        return self.close_price > self.open_price
    
    @property
    def is_red(self) -> bool:
        """Check if candle is red (bearish)"""
        return self.close_price < self.open_price
    
    @property
    def is_doji(self) -> bool:
        """Check if candle is doji (open ≈ close)"""
        price_range = self.high_price - self.low_price
        if price_range == 0:
            return True
        
        body_size = abs(self.close_price - self.open_price)
        return (body_size / price_range) < Decimal('0.1')  # Body < 10% of range
    
    @property
    def body_size(self) -> Decimal:
        """Get candle body size"""
        return abs(self.close_price - self.open_price)
    
    @property
    def upper_shadow_size(self) -> Decimal:
        """Get upper shadow (wick) size"""
        return self.high_price - max(self.open_price, self.close_price)
    
    @property
    def lower_shadow_size(self) -> Decimal:
        """Get lower shadow (wick) size"""
        return min(self.open_price, self.close_price) - self.low_price
    
    @property
    def typical_price(self) -> Decimal:
        """Calculate typical price (HLC/3)"""
        return (self.high_price + self.low_price + self.close_price) / Decimal('3')
    
    @property
    def weighted_price(self) -> Decimal:
        """Calculate volume weighted price"""
        return (self.high_price + self.low_price + self.close_price + self.close_price) / Decimal('4')
    
    def get_ohlcv_dict(self) -> Dict[str, Any]:
        """Get OHLCV data as dictionary"""
        return {
            'symbol': self.symbol,
            'interval': self.interval,
            'open_time': self.open_time.isoformat(),
            'close_time': self.close_time.isoformat(),
            'open': float(self.open_price),
            'high': float(self.high_price),
            'low': float(self.low_price),
            'close': float(self.close_price),
            'volume': float(self.volume),
            'data_source': self.data_source  # 🆕
        }
    
    def get_analysis_data(self) -> Dict[str, Any]:
        """Get extended analysis data"""
        return {
            **self.get_ohlcv_dict(),
            'price_change': float(self.price_change),
            'price_change_percent': float(self.price_change_percent),
            'is_green': self.is_green,
            'is_red': self.is_red,
            'is_doji': self.is_doji,
            'body_size': float(self.body_size),
            'upper_shadow_size': float(self.upper_shadow_size),
            'lower_shadow_size': float(self.lower_shadow_size),
            'typical_price': float(self.typical_price),
            'weighted_price': float(self.weighted_price)
        }
    
    @classmethod
    def create_from_bybit_data(cls, symbol: str, interval: str, bybit_candle: List) -> 'MarketDataCandle':
        """
        Create MarketDataCandle from Bybit API response
        
        Bybit format: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
        
        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            interval: Candle interval
            bybit_candle: Raw candle data from Bybit API
            
        Returns:
            MarketDataCandle: New candle instance
        """
        try:
            if len(bybit_candle) < 7:
                raise ValueError(f"Invalid Bybit candle data: expected 7+ elements, got {len(bybit_candle)}")
            
            # Parse Bybit data
            start_time_ms = int(bybit_candle[0])
            open_price = Decimal(str(bybit_candle[1]))
            high_price = Decimal(str(bybit_candle[2])) 
            low_price = Decimal(str(bybit_candle[3]))
            close_price = Decimal(str(bybit_candle[4]))
            volume = Decimal(str(bybit_candle[5]))
            turnover = Decimal(str(bybit_candle[6])) if len(bybit_candle) > 6 else None
            
            # Convert timestamps
            open_time = datetime.fromtimestamp(start_time_ms / 1000, tz=timezone.utc)
            
            # Calculate close time based on interval
            interval_enum = CandleInterval(interval)
            interval_seconds = interval_enum.to_seconds()
            close_time = datetime.fromtimestamp((start_time_ms / 1000) + interval_seconds - 1, tz=timezone.utc)
            
            # Convert list to JSON for JSONB field
            raw_data_json = json.dumps(bybit_candle) if bybit_candle else None
            
            return cls(
                symbol=symbol.upper(),
                interval=interval,
                open_time=open_time,
                close_time=close_time,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                quote_volume=turnover,
                data_source="bybit",
                raw_data=raw_data_json
            )
            
        except Exception as e:
            logger.error(f"Failed to create candle from Bybit data: {e}")
            logger.error(f"Raw data: {bybit_candle}")
            raise ValueError(f"Invalid Bybit candle data: {e}")
    
    @classmethod
    def create_from_yfinance_data(cls, symbol: str, interval: str, yf_data: Dict[str, Any]) -> 'MarketDataCandle':
        """
        🆕 Create MarketDataCandle from YFinance API response
        
        YFinance format (pandas DataFrame row converted to dict):
        {
            'Open': float,
            'High': float,
            'Low': float,
            'Close': float,
            'Volume': int,
            'Datetime': datetime or timestamp
        }
        
        Args:
            symbol: Futures symbol (e.g., MCL, MGC, MES, MNQ)
            interval: Candle interval
            yf_data: Raw candle data from yfinance (DataFrame row as dict)
            
        Returns:
            MarketDataCandle: New candle instance
        """
        try:
            # Парсим данные от yfinance
            # yfinance может использовать разные ключи в зависимости от версии
            open_price = Decimal(str(yf_data.get('Open', yf_data.get('open', 0))))
            high_price = Decimal(str(yf_data.get('High', yf_data.get('high', 0))))
            low_price = Decimal(str(yf_data.get('Low', yf_data.get('low', 0))))
            close_price = Decimal(str(yf_data.get('Close', yf_data.get('close', 0))))
            volume = Decimal(str(yf_data.get('Volume', yf_data.get('volume', 0))))
            
            # Парсим timestamp
            timestamp = yf_data.get('Datetime', yf_data.get('datetime', yf_data.get('Date', datetime.now())))
            
            # Конвертируем timestamp в datetime если нужно
            if isinstance(timestamp, (int, float)):
                open_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            elif isinstance(timestamp, str):
                # Пытаемся распарсить строку
                open_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=timezone.utc)
            elif isinstance(timestamp, datetime):
                open_time = timestamp
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=timezone.utc)
            else:
                logger.warning(f"Unknown timestamp type: {type(timestamp)}, using current time")
                open_time = datetime.now(tz=timezone.utc)
            
            # Calculate close time based on interval
            interval_enum = CandleInterval(interval)
            interval_seconds = interval_enum.to_seconds()
            close_time = datetime.fromtimestamp(open_time.timestamp() + interval_seconds - 1, tz=timezone.utc)
            
            # Convert dict to JSON for JSONB field
            raw_data_json = json.dumps({
                k: str(v) if isinstance(v, (datetime, Decimal)) else v 
                for k, v in yf_data.items()
            })
            
            # Убираем суффикс =F если есть для хранения в БД
            clean_symbol = symbol.replace('=F', '').upper()
            
            return cls(
                symbol=clean_symbol,
                interval=interval,
                open_time=open_time,
                close_time=close_time,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                quote_volume=None,  # yfinance не предоставляет quote volume
                data_source="yfinance",
                raw_data=raw_data_json
            )
            
        except Exception as e:
            logger.error(f"Failed to create candle from yfinance data: {e}")
            logger.error(f"Raw data: {yf_data}")
            raise ValueError(f"Invalid yfinance candle data: {e}")
    
    @classmethod
    def get_crypto_symbols(cls, session) -> List[str]:
        """🆕 Получить все крипто символы из БД"""
        try:
            result = session.query(cls.symbol).filter(
                cls.data_source == 'bybit'
            ).distinct().all()
            return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Error getting crypto symbols: {e}")
            return []
    
    @classmethod
    def get_futures_symbols(cls, session) -> List[str]:
        """🆕 Получить все фьючерсные символы из БД"""
        try:
            result = session.query(cls.symbol).filter(
                cls.data_source == 'yfinance'
            ).distinct().all()
            return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Error getting futures symbols: {e}")
            return []
    
    @classmethod
    def get_all_symbols_by_source(cls, session) -> Dict[str, List[str]]:
        """🆕 Получить все символы сгруппированные по источнику"""
        try:
            result = session.query(
                cls.data_source, 
                cls.symbol
            ).distinct().all()
            
            symbols_by_source = {}
            for source, symbol in result:
                if source not in symbols_by_source:
                    symbols_by_source[source] = []
                symbols_by_source[source].append(symbol)
            
            return symbols_by_source
        except Exception as e:
            logger.error(f"Error getting symbols by source: {e}")
            return {}
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return (f"MarketDataCandle(symbol='{self.symbol}', interval='{self.interval}', "
                f"source='{self.data_source}', open_time={self.open_time}, close={self.close_price})")
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        return (f"{self.symbol} ({self.data_source}) {self.interval} candle: "
                f"O={self.open_price} H={self.high_price} L={self.low_price} C={self.close_price} "
                f"V={self.volume} ({self.open_time})")


# Export main components
__all__ = [
    "Base",
    "MarketDataCandle", 
    "CandleInterval",
    "DataSource"  # 🆕
]

logger.info("✅ Market data models loaded successfully (Bybit + YFinance support)")
