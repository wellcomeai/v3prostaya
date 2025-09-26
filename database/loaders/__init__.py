"""
Database Loaders Module

Provides data loading utilities for populating database with historical
and real-time market data from various sources.

Components:
- HistoricalDataLoader: Loads historical OHLCV data from Bybit API
- RealtimeDataSync: Synchronizes real-time data with database
- DataValidation: Validates and cleans market data before storage
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from .historical_data_loader import (
    HistoricalDataLoader,
    LoaderConfig,
    LoadingProgress,
    LoadingStatus
)

logger = logging.getLogger(__name__)

# Available data intervals for loading
SUPPORTED_INTERVALS = [
    "1m",   # 1 minute - high frequency trading
    "3m",   # 3 minutes
    "5m",   # 5 minutes - common for short-term analysis
    "15m",  # 15 minutes
    "30m",  # 30 minutes
    "1h",   # 1 hour - common for medium-term analysis
    "2h",   # 2 hours
    "4h",   # 4 hours - common for swing trading
    "6h",   # 6 hours
    "12h",  # 12 hours
    "1d",   # 1 day - daily candles
    "1w",   # 1 week - weekly analysis
    "1M"    # 1 month - monthly trends
]

# Data loading priorities (higher = more important)
INTERVAL_PRIORITIES = {
    "1m": 10,   # Highest - for real-time trading
    "5m": 9,    # Very high - for scalping
    "15m": 8,   # High - for short-term strategies
    "1h": 7,    # Medium-high - for intraday
    "4h": 6,    # Medium - for swing trading
    "1d": 5,    # Medium-low - for position trading
    "1w": 4,    # Low - for long-term analysis
    "1M": 3     # Lowest - for macro analysis
}

async def create_historical_loader(symbol: str = "BTCUSDT", 
                                  testnet: bool = True,
                                  enable_progress_tracking: bool = True,
                                  max_concurrent_requests: int = 5,
                                  batch_size: int = 1000) -> HistoricalDataLoader:
    """
    Factory function to create configured historical data loader
    
    Args:
        symbol: Trading symbol to load data for
        testnet: Use Bybit testnet (True) or mainnet (False)
        enable_progress_tracking: Track loading progress
        max_concurrent_requests: Max parallel API requests
        batch_size: Number of candles per database batch
        
    Returns:
        HistoricalDataLoader: Configured loader instance
    """
    config = LoaderConfig(
        symbol=symbol,
        testnet=testnet,
        enable_progress_tracking=enable_progress_tracking,
        max_concurrent_requests=max_concurrent_requests,
        batch_size=batch_size
    )
    
    loader = HistoricalDataLoader(config)
    await loader.initialize()
    
    logger.info(f"Historical data loader created for {symbol}")
    logger.info(f"Mode: {'Testnet' if testnet else 'Mainnet'}")
    logger.info(f"Max concurrent requests: {max_concurrent_requests}")
    
    return loader

async def load_year_data(symbol: str = "BTCUSDT", 
                        intervals: List[str] = None,
                        testnet: bool = True,
                        start_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Convenience function to load a full year of historical data
    
    Args:
        symbol: Trading symbol
        intervals: List of intervals to load (default: common intervals)
        testnet: Use testnet
        start_date: Start date (default: 1 year ago)
        
    Returns:
        Dict: Loading results summary
    """
    if intervals is None:
        # Load most common intervals for trading
        intervals = ["1m", "5m", "15m", "1h", "4h", "1d"]
    
    if start_date is None:
        start_date = datetime.now() - timedelta(days=365)
    
    end_date = datetime.now() - timedelta(hours=2)
    
    logger.info(f"🚀 Starting year data load for {symbol}")
    logger.info(f"📅 Period: {start_date.date()} to {end_date.date()}")
    logger.info(f"📊 Intervals: {intervals}")
    
    loader = await create_historical_loader(
        symbol=symbol,
        testnet=testnet,
        enable_progress_tracking=True,
        max_concurrent_requests=3  # Conservative for year-long loads
    )
    
    try:
        results = await loader.load_historical_data(
            intervals=intervals,
            start_time=start_date,
            end_time=end_date
        )
        
        logger.info("✅ Year data load completed successfully")
        return results
        
    finally:
        await loader.close()

def get_recommended_intervals(trading_style: str = "swing") -> List[str]:
    """
    Get recommended intervals based on trading style
    
    Args:
        trading_style: "scalping", "day", "swing", "position", "all"
        
    Returns:
        List[str]: Recommended intervals
    """
    recommendations = {
        "scalping": ["1m", "3m", "5m"],
        "day": ["5m", "15m", "30m", "1h"],
        "swing": ["15m", "1h", "4h", "1d"],
        "position": ["4h", "1d", "1w"],
        "analysis": ["1h", "4h", "1d", "1w", "1M"],
        "all": SUPPORTED_INTERVALS
    }
    
    return recommendations.get(trading_style, recommendations["swing"])

def estimate_loading_time(intervals: List[str], 
                         days: int = 365,
                         requests_per_second: float = 2.0) -> Dict[str, Any]:
    """
    Estimate time required to load historical data
    
    Args:
        intervals: List of intervals to load
        days: Number of days to load
        requests_per_second: Expected API request rate
        
    Returns:
        Dict: Time estimates and recommendations
    """
    # Estimate number of requests needed per interval
    interval_candles = {
        "1m": days * 24 * 60,      # 1 candle per minute
        "3m": days * 24 * 20,      # 1 candle per 3 minutes  
        "5m": days * 24 * 12,      # 1 candle per 5 minutes
        "15m": days * 24 * 4,      # 1 candle per 15 minutes
        "30m": days * 24 * 2,      # 1 candle per 30 minutes
        "1h": days * 24,           # 1 candle per hour
        "2h": days * 12,           # 1 candle per 2 hours
        "4h": days * 6,            # 1 candle per 4 hours
        "6h": days * 4,            # 1 candle per 6 hours
        "12h": days * 2,           # 1 candle per 12 hours
        "1d": days,                # 1 candle per day
        "1w": days // 7,           # 1 candle per week
        "1M": days // 30           # 1 candle per month
    }
    
    total_candles = 0
    total_requests = 0
    
    for interval in intervals:
        if interval in interval_candles:
            candles = interval_candles[interval]
            requests = (candles + 999) // 1000  # Round up, max 1000 per request
            total_candles += candles
            total_requests += requests
    
    estimated_seconds = total_requests / requests_per_second
    estimated_hours = estimated_seconds / 3600
    
    return {
        "total_candles": total_candles,
        "total_requests": total_requests,
        "estimated_time_seconds": estimated_seconds,
        "estimated_time_hours": round(estimated_hours, 2),
        "estimated_time_formatted": str(timedelta(seconds=int(estimated_seconds))),
        "intervals_breakdown": {
            interval: {
                "candles": interval_candles.get(interval, 0),
                "requests": (interval_candles.get(interval, 0) + 999) // 1000
            }
            for interval in intervals if interval in interval_candles
        },
        "recommendations": {
            "use_concurrent_loading": estimated_hours > 2,
            "recommended_concurrency": min(5, max(2, int(estimated_hours))),
            "suggested_batch_size": 1000 if total_candles > 100000 else 500
        }
    }

# Export main components
__all__ = [
    # Main loader
    "HistoricalDataLoader",
    "LoaderConfig", 
    "LoadingProgress",
    "LoadingStatus",
    
    # Factory functions
    "create_historical_loader",
    "load_year_data",
    
    # Utilities
    "get_recommended_intervals",
    "estimate_loading_time",
    
    # Constants
    "SUPPORTED_INTERVALS",
    "INTERVAL_PRIORITIES"
]

# Version info
__version__ = "1.0.0"
__author__ = "Trading Bot Team"

logger.info(f"Database loaders module loaded (version {__version__})")
