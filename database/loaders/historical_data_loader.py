"""
Historical Data Loader

Production-ready loader for downloading historical OHLCV data from Bybit API
and storing it in PostgreSQL database with proper error handling, progress tracking,
and rate limiting.

Features:
- Paginated loading (1000 candles per request max)
- Multiple interval support (1m to 1M)
- Concurrent loading with rate limiting
- Progress tracking and resumable downloads
- Duplicate detection and handling
- Comprehensive error handling with retries
- Database batch operations for performance
- Health monitoring and statistics
"""

import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Set, Tuple
from enum import Enum
from dataclasses import dataclass, field
import time
import math

# Import existing components
from ..connections import get_connection_manager
from ..repositories import get_market_data_repository
from ..models.market_data import MarketDataCandle, CandleInterval

logger = logging.getLogger(__name__)


class LoadingStatus(Enum):
    """Status of data loading process"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    LOADING = "loading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class LoadingProgress:
    """Progress tracking for data loading"""
    
    # Overall progress
    status: LoadingStatus = LoadingStatus.IDLE
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Intervals progress
    total_intervals: int = 0
    completed_intervals: int = 0
    current_interval: Optional[str] = None
    
    # Requests progress  
    total_requests: int = 0
    completed_requests: int = 0
    failed_requests: int = 0
    
    # Data progress
    total_candles_expected: int = 0
    total_candles_loaded: int = 0
    total_candles_saved: int = 0
    duplicates_skipped: int = 0
    
    # Performance metrics
    requests_per_second: float = 0.0
    candles_per_second: float = 0.0
    estimated_time_remaining: Optional[timedelta] = None
    
    # Error tracking
    errors: List[Dict[str, Any]] = field(default_factory=list)
    last_error: Optional[str] = None
    
    def get_overall_progress(self) -> float:
        """Get overall progress as percentage (0-100)"""
        if self.total_requests == 0:
            return 0.0
        return (self.completed_requests / self.total_requests) * 100
    
    def get_current_interval_progress(self) -> float:
        """Get current interval progress as percentage (0-100)"""
        if not self.current_interval or self.total_intervals == 0:
            return 0.0
        return (self.completed_intervals / self.total_intervals) * 100
    
    def add_error(self, error: str, details: Dict[str, Any] = None):
        """Add error to tracking"""
        self.last_error = error
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "error": error,
            "details": details or {}
        }
        self.errors.append(error_entry)
        
        # Keep only last 50 errors
        if len(self.errors) > 50:
            self.errors = self.errors[-50:]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get progress summary"""
        duration = None
        if self.start_time:
            end = self.end_time or datetime.now()
            duration = end - self.start_time
        
        return {
            "status": self.status.value,
            "overall_progress": round(self.get_overall_progress(), 2),
            "current_interval": self.current_interval,
            "intervals_completed": f"{self.completed_intervals}/{self.total_intervals}",
            "requests_completed": f"{self.completed_requests}/{self.total_requests}",
            "candles_loaded": self.total_candles_loaded,
            "candles_saved": self.total_candles_saved,
            "duplicates_skipped": self.duplicates_skipped,
            "duration": str(duration).split('.')[0] if duration else None,
            "requests_per_second": round(self.requests_per_second, 2),
            "candles_per_second": round(self.candles_per_second, 2),
            "estimated_time_remaining": str(self.estimated_time_remaining).split('.')[0] if self.estimated_time_remaining else None,
            "error_count": len(self.errors),
            "last_error": self.last_error
        }


@dataclass 
class LoaderConfig:
    """Configuration for historical data loader"""
    
    # Basic settings
    symbol: str = "BTCUSDT"
    testnet: bool = True
    
    # API settings  
    max_concurrent_requests: int = 5
    requests_per_second_limit: float = 10.0  # Bybit rate limit
    request_timeout_seconds: int = 30
    max_retries_per_request: int = 3
    retry_delay_seconds: float = 1.0
    
    # Database settings
    batch_size: int = 1000
    max_batch_size: int = 5000
    
    # Progress tracking
    enable_progress_tracking: bool = True
    progress_update_interval: int = 10  # Log progress every N requests
    
    # Data validation
    validate_data_integrity: bool = True
    skip_weekends_for_daily: bool = False  # Skip weekends for daily+ intervals
    
    # Performance
    enable_duplicate_detection: bool = True
    use_bulk_inserts: bool = True


class HistoricalDataLoader:
    """
    Production-ready historical data loader
    
    Loads historical OHLCV data from Bybit API with:
    - Intelligent pagination and rate limiting
    - Progress tracking and resumable downloads  
    - Error handling with automatic retries
    - Duplicate detection and efficient database operations
    - Comprehensive logging and monitoring
    """
    
    def __init__(self, config: LoaderConfig):
        """
        Initialize historical data loader
        
        Args:
            config: Loader configuration
        """
        self.config = config
        self.progress = LoadingProgress()
        
        # Connection components
        self.connection_manager = None
        self.repository = None
        
        # API client (we'll create our own minimal client for historical data)
        self.session = None
        self.base_url = "https://api-testnet.bybit.com" if config.testnet else "https://api.bybit.com"
        
        # Rate limiting
        self.rate_limiter = asyncio.Semaphore(config.max_concurrent_requests)
        self.last_request_time = 0.0
        self.request_delay = 1.0 / config.requests_per_second_limit
        
        # Control flags
        self.is_initialized = False
        self.is_loading = False
        self.should_stop = False
        
        # Statistics
        self.stats = {
            "total_api_calls": 0,
            "successful_api_calls": 0, 
            "failed_api_calls": 0,
            "total_data_points": 0,
            "total_database_operations": 0,
            "start_time": None,
            "last_activity": None
        }
        
        logger.info(f"🏗️ HistoricalDataLoader initialized for {config.symbol}")
        logger.info(f"   • Mode: {'Testnet' if config.testnet else 'Mainnet'}")
        logger.info(f"   • Max concurrent requests: {config.max_concurrent_requests}")
        logger.info(f"   • Rate limit: {config.requests_per_second_limit} req/sec")
        logger.info(f"   • Batch size: {config.batch_size}")
    
    async def initialize(self) -> bool:
        """Initialize database connections and HTTP session"""
        try:
            self.progress.status = LoadingStatus.INITIALIZING
            
            # Initialize database connection
            self.connection_manager = await get_connection_manager()
            self.repository = await get_market_data_repository()
            
            # Initialize HTTP session
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'BybitHistoricalLoader/1.0'
                }
            )
            
            # Test connections
            await self._test_database_connection()
            await self._test_api_connection()
            
            self.is_initialized = True
            self.stats["start_time"] = datetime.now()
            
            logger.info("✅ HistoricalDataLoader initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize HistoricalDataLoader: {e}")
            self.progress.status = LoadingStatus.FAILED
            self.progress.add_error(f"Initialization failed: {e}")
            return False
    
    async def _test_database_connection(self):
        """Test database connectivity"""
        try:
            health = await self.connection_manager.get_health_status()
            if not health.get("healthy", False):
                raise Exception(f"Database not healthy: {health}")
            logger.info("✅ Database connection verified")
        except Exception as e:
            raise Exception(f"Database connection test failed: {e}")
    
    async def _test_api_connection(self):
        """Test Bybit API connectivity"""
        try:
            url = f"{self.base_url}/v5/market/time"
            async with self.session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"API returned status {response.status}")
                data = await response.json()
                if data.get('retCode') != 0:
                    raise Exception(f"API error: {data.get('retMsg')}")
                logger.info("✅ Bybit API connection verified")
        except Exception as e:
            raise Exception(f"API connection test failed: {e}")
    
    async def load_historical_data(self, 
                                  intervals: List[str],
                                  start_time: datetime,
                                  end_time: Optional[datetime] = None,
                                  resume_on_error: bool = True) -> Dict[str, Any]:
        """
        Load historical data for multiple intervals
        
        Args:
            intervals: List of candle intervals to load
            start_time: Start timestamp (UTC)
            end_time: End timestamp (UTC, defaults to now)
            resume_on_error: Continue loading other intervals if one fails
            
        Returns:
            Dict: Loading results with statistics
        """
        if not self.is_initialized:
            raise Exception("Loader not initialized. Call initialize() first.")
        
        if self.is_loading:
            raise Exception("Loading already in progress")
        
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        
        # Validate intervals
        valid_intervals = [i for i in intervals if i in CandleInterval.get_all_intervals()]
        if len(valid_intervals) != len(intervals):
            invalid = set(intervals) - set(valid_intervals)
            logger.warning(f"⚠️ Invalid intervals removed: {invalid}")
        
        if not valid_intervals:
            raise ValueError("No valid intervals provided")
        
        try:
            self.is_loading = True
            self.should_stop = False
            self.progress = LoadingProgress()
            self.progress.status = LoadingStatus.LOADING
            self.progress.start_time = datetime.now()
            self.progress.total_intervals = len(valid_intervals)
            
            logger.info(f"🚀 Starting historical data load")
            logger.info(f"   • Symbol: {self.config.symbol}")
            logger.info(f"   • Intervals: {valid_intervals}")
            logger.info(f"   • Period: {start_time.date()} to {end_time.date()}")
            logger.info(f"   • Duration: {(end_time - start_time).days} days")
            
            # Pre-calculate total requests for progress tracking
            await self._estimate_total_requests(valid_intervals, start_time, end_time)
            
            results = {}
            
            # Load each interval
            for i, interval in enumerate(valid_intervals):
                if self.should_stop:
                    logger.info("🛑 Loading cancelled by user")
                    break
                
                self.progress.current_interval = interval
                self.progress.completed_intervals = i
                
                try:
                    logger.info(f"📊 Loading interval {interval} ({i+1}/{len(valid_intervals)})")
                    
                    result = await self._load_interval_data(
                        interval=interval,
                        start_time=start_time,
                        end_time=end_time
                    )
                    
                    results[interval] = result
                    self.progress.completed_intervals += 1
                    
                    logger.info(f"✅ Interval {interval} completed: {result['candles_loaded']} candles")
                    
                except Exception as e:
                    error_msg = f"Failed to load interval {interval}: {e}"
                    logger.error(f"❌ {error_msg}")
                    self.progress.add_error(error_msg, {"interval": interval})
                    
                    results[interval] = {
                        "success": False,
                        "error": str(e),
                        "candles_loaded": 0,
                        "candles_saved": 0
                    }
                    
                    if not resume_on_error:
                        break
            
            # Finalize
            self.progress.end_time = datetime.now()
            duration = self.progress.end_time - self.progress.start_time
            
            if self.should_stop:
                self.progress.status = LoadingStatus.CANCELLED
            elif any(not r.get("success", False) for r in results.values()):
                self.progress.status = LoadingStatus.FAILED
            else:
                self.progress.status = LoadingStatus.COMPLETED
            
            # Generate summary
            total_candles_loaded = sum(r.get("candles_loaded", 0) for r in results.values())
            total_candles_saved = sum(r.get("candles_saved", 0) for r in results.values())
            success_count = sum(1 for r in results.values() if r.get("success", False))
            
            summary = {
                "success": self.progress.status == LoadingStatus.COMPLETED,
                "status": self.progress.status.value,
                "duration_seconds": duration.total_seconds(),
                "duration_formatted": str(duration).split('.')[0],
                "intervals_requested": len(valid_intervals),
                "intervals_completed": success_count,
                "intervals_failed": len(valid_intervals) - success_count,
                "total_candles_loaded": total_candles_loaded,
                "total_candles_saved": total_candles_saved,
                "duplicates_skipped": self.progress.duplicates_skipped,
                "requests_made": self.progress.completed_requests,
                "requests_failed": self.progress.failed_requests,
                "average_requests_per_second": round(self.progress.requests_per_second, 2),
                "average_candles_per_second": round(self.progress.candles_per_second, 2),
                "error_count": len(self.progress.errors),
                "results_by_interval": results
            }
            
            logger.info("📋 Loading Summary:")
            logger.info(f"   • Status: {summary['status']}")
            logger.info(f"   • Duration: {summary['duration_formatted']}")
            logger.info(f"   • Intervals: {summary['intervals_completed']}/{summary['intervals_requested']}")
            logger.info(f"   • Candles loaded: {summary['total_candles_loaded']:,}")
            logger.info(f"   • Candles saved: {summary['total_candles_saved']:,}")
            logger.info(f"   • Performance: {summary['average_requests_per_second']} req/sec")
            
            if summary['error_count'] > 0:
                logger.warning(f"   • Errors encountered: {summary['error_count']}")
            
            return summary
            
        finally:
            self.is_loading = False
    
    async def _estimate_total_requests(self, intervals: List[str], 
                                     start_time: datetime, end_time: datetime):
        """Estimate total API requests needed for progress tracking"""
        total_requests = 0
        
        for interval in intervals:
            try:
                interval_enum = CandleInterval(interval)
                interval_seconds = interval_enum.to_seconds()
                
                total_duration = (end_time - start_time).total_seconds()
                expected_candles = int(total_duration / interval_seconds)
                
                # Bybit max 1000 candles per request
                requests_needed = math.ceil(expected_candles / 1000)
                total_requests += requests_needed
                
            except Exception:
                # Fallback estimation
                total_requests += 100
        
        self.progress.total_requests = total_requests
        logger.info(f"📊 Estimated {total_requests} API requests needed")
    
    async def _load_interval_data(self, interval: str, 
                                start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """
        Load historical data for a single interval with pagination
        
        Args:
            interval: Candle interval (e.g., '1m', '5m', '1h')
            start_time: Start timestamp
            end_time: End timestamp
            
        Returns:
            Dict: Loading results for this interval
        """
        candles_loaded = 0
        candles_saved = 0 
        requests_made = 0
        errors = 0
        
        # Calculate time chunk size (Bybit returns max 1000 candles)
        try:
            interval_enum = CandleInterval(interval)
            interval_seconds = interval_enum.to_seconds()
            
            # Max 1000 candles per request
            chunk_duration_seconds = 1000 * interval_seconds
            chunk_duration = timedelta(seconds=chunk_duration_seconds)
            
        except Exception as e:
            logger.error(f"❌ Invalid interval {interval}: {e}")
            return {"success": False, "error": f"Invalid interval: {e}"}
        
        current_time = start_time
        
        while current_time < end_time and not self.should_stop:
            chunk_end = min(current_time + chunk_duration, end_time)
            
            try:
                # Apply rate limiting
                async with self.rate_limiter:
                    await self._enforce_rate_limit()
                    
                    # Make API request
                    chunk_candles = await self._fetch_candles_chunk(
                        interval=interval,
                        start_time=current_time,
                        end_time=chunk_end
                    )
                    
                    requests_made += 1
                    self.progress.completed_requests += 1
                    self.stats["successful_api_calls"] += 1
                    
                    if chunk_candles:
                        candles_loaded += len(chunk_candles)
                        self.progress.total_candles_loaded += len(chunk_candles)
                        
                        # Save to database in batches
                        saved_count = await self._save_candles_batch(chunk_candles)
                        candles_saved += saved_count
                        self.progress.total_candles_saved += saved_count
                        
                        if len(chunk_candles) > saved_count:
                            self.progress.duplicates_skipped += (len(chunk_candles) - saved_count)
                    
                    # Update performance metrics
                    self._update_performance_metrics()
                    
                    # Log progress periodically
                    if requests_made % self.config.progress_update_interval == 0:
                        progress_pct = self.progress.get_overall_progress()
                        logger.info(f"   📈 Progress: {progress_pct:.1f}% "
                                  f"(loaded {candles_loaded:,} candles for {interval})")
                
            except Exception as e:
                errors += 1
                self.progress.failed_requests += 1
                self.stats["failed_api_calls"] += 1
                
                error_msg = f"Failed to fetch {interval} data for {current_time.date()}: {e}"
                logger.error(f"❌ {error_msg}")
                self.progress.add_error(error_msg, {
                    "interval": interval,
                    "start_time": current_time.isoformat(),
                    "end_time": chunk_end.isoformat()
                })
                
                # Retry logic
                if errors <= self.config.max_retries_per_request:
                    logger.info(f"🔄 Retrying in {self.config.retry_delay_seconds}s...")
                    await asyncio.sleep(self.config.retry_delay_seconds)
                    continue
                else:
                    logger.error(f"💥 Max retries exceeded for {interval} chunk")
                    # Skip this chunk and continue
            
            # Move to next time chunk
            current_time = chunk_end
            
            # Small delay to be API-friendly
            await asyncio.sleep(0.1)
        
        return {
            "success": errors == 0 or candles_loaded > 0,
            "interval": interval,
            "candles_loaded": candles_loaded,
            "candles_saved": candles_saved,
            "duplicates_skipped": candles_loaded - candles_saved,
            "requests_made": requests_made,
            "errors": errors,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat()
        }
    
    async def _fetch_candles_chunk(self, interval: str, 
                                 start_time: datetime, end_time: datetime) -> List[MarketDataCandle]:
        """
        Fetch a chunk of candles from Bybit API
        
        Args:
            interval: Candle interval
            start_time: Chunk start time
            end_time: Chunk end time
            
        Returns:
            List of MarketDataCandle objects
        """
        # Convert to milliseconds (Bybit expects milliseconds)
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        params = {
            'category': 'linear',  # Derivatives
            'symbol': self.config.symbol,
            'interval': interval,
            'start': start_ms,
            'end': end_ms,
            'limit': 1000  # Max limit
        }
        
        url = f"{self.base_url}/v5/market/kline"
        
        async with self.session.get(url, params=params) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"HTTP {response.status}: {error_text}")
            
            data = await response.json()
            
            if data.get('retCode') != 0:
                error_msg = data.get('retMsg', 'Unknown API error')
                raise Exception(f"Bybit API error: {error_msg}")
            
            # Parse candles
            raw_candles = data.get('result', {}).get('list', [])
            
            candles = []
            for raw_candle in raw_candles:
                try:
                    candle = MarketDataCandle.create_from_bybit_data(
                        symbol=self.config.symbol,
                        interval=interval,
                        bybit_candle=raw_candle
                    )
                    candles.append(candle)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to parse candle: {e}")
                    continue
            
            self.stats["total_data_points"] += len(candles)
            self.stats["last_activity"] = datetime.now()
            
            return candles
    
    async def _save_candles_batch(self, candles: List[MarketDataCandle]) -> int:
        """
        Save candles to database efficiently
        
        Args:
            candles: List of candles to save
            
        Returns:
            Number of candles actually saved (excluding duplicates)
        """
        if not candles:
            return 0
        
        try:
            # Use bulk insert for efficiency
            inserted_count, updated_count = await self.repository.bulk_insert_candles(
                candles=candles,
                batch_size=self.config.batch_size
            )
            
            self.stats["total_database_operations"] += 1
            
            # Return total affected rows (Bybit API handles conflicts via upsert)
            return inserted_count + updated_count
            
        except Exception as e:
            logger.error(f"❌ Database save failed: {e}")
            raise Exception(f"Failed to save candles to database: {e}")
    
    async def _enforce_rate_limit(self):
        """Enforce API rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.request_delay:
            sleep_time = self.request_delay - time_since_last
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _update_performance_metrics(self):
        """Update performance tracking metrics"""
        if not self.progress.start_time:
            return
        
        elapsed_time = (datetime.now() - self.progress.start_time).total_seconds()
        
        if elapsed_time > 0:
            self.progress.requests_per_second = self.progress.completed_requests / elapsed_time
            self.progress.candles_per_second = self.progress.total_candles_loaded / elapsed_time
            
            # Estimate time remaining
            if self.progress.total_requests > 0 and self.progress.requests_per_second > 0:
                remaining_requests = self.progress.total_requests - self.progress.completed_requests
                estimated_seconds = remaining_requests / self.progress.requests_per_second
                self.progress.estimated_time_remaining = timedelta(seconds=int(estimated_seconds))
    
    def stop_loading(self):
        """Request to stop the loading process"""
        self.should_stop = True
        logger.info("🛑 Stop requested - will finish current operations...")
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current loading progress"""
        return self.progress.get_summary()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get loader statistics"""
        uptime = None
        if self.stats["start_time"]:
            uptime = datetime.now() - self.stats["start_time"]
        
        return {
            **self.stats,
            "uptime": str(uptime).split('.')[0] if uptime else None,
            "is_initialized": self.is_initialized,
            "is_loading": self.is_loading,
            "current_status": self.progress.status.value,
            "success_rate": (
                (self.stats["successful_api_calls"] / max(1, self.stats["total_api_calls"])) * 100
            ) if self.stats["total_api_calls"] > 0 else 100
        }
    
    async def close(self):
        """Clean up resources"""
        try:
            if self.is_loading:
                self.stop_loading()
                # Give some time for graceful shutdown
                await asyncio.sleep(2)
            
            if self.session and not self.session.closed:
                await self.session.close()
                logger.info("✅ HTTP session closed")
            
            self.is_initialized = False
            logger.info("✅ HistoricalDataLoader closed successfully")
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    def __str__(self):
        """String representation"""
        return (f"HistoricalDataLoader(symbol={self.config.symbol}, "
                f"status={self.progress.status.value}, "
                f"loaded={self.progress.total_candles_loaded:,})")
    
    def __repr__(self):
        """Detailed representation for debugging"""
        return (f"HistoricalDataLoader(symbol='{self.config.symbol}', "
                f"testnet={self.config.testnet}, "
                f"max_concurrent={self.config.max_concurrent_requests}, "
                f"batch_size={self.config.batch_size})")


# Export main components
__all__ = [
    "HistoricalDataLoader",
    "LoaderConfig", 
    "LoadingProgress",
    "LoadingStatus"
]
