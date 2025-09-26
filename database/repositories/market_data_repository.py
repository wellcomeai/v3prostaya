"""
Market Data Repository

Repository for CRUD operations on market data candles.
Provides optimized queries for time-series analysis and technical indicators.
"""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Union, Tuple
from decimal import Decimal

from sqlalchemy import and_, or_, desc, asc, func, text
from sqlalchemy.dialects.postgresql import insert

from ..models.market_data import MarketDataCandle, CandleInterval
from ..connections.postgres import PostgreSQLManager, QueryError

logger = logging.getLogger(__name__)


class MarketDataRepository:
    """
    Repository for market data operations
    
    Provides high-performance CRUD operations and analytical queries
    for cryptocurrency market data storage and retrieval.
    """
    
    def __init__(self, connection_manager: PostgreSQLManager):
        """
        Initialize repository with connection manager
        
        Args:
            connection_manager: Database connection manager
        """
        self.db = connection_manager
        self.stats = {
            "candles_inserted": 0,
            "candles_updated": 0,
            "candles_queried": 0,
            "batch_operations": 0,
            "query_errors": 0
        }
        
        logger.info("MarketDataRepository initialized")
    
    async def insert_candle(self, candle: MarketDataCandle) -> bool:
        """
        Insert single candle with conflict handling
        
        Args:
            candle: MarketDataCandle instance
            
        Returns:
            bool: True if inserted successfully
        """
        try:
            query = """
                INSERT INTO market_data_candles 
                (symbol, interval, open_time, close_time, open_price, high_price, 
                 low_price, close_price, volume, quote_volume, number_of_trades,
                 taker_buy_base_volume, taker_buy_quote_volume, data_source, raw_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (symbol, interval, open_time) 
                DO UPDATE SET
                    high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price,
                    close_price = EXCLUDED.close_price,
                    volume = EXCLUDED.volume,
                    quote_volume = EXCLUDED.quote_volume,
                    number_of_trades = EXCLUDED.number_of_trades,
                    taker_buy_base_volume = EXCLUDED.taker_buy_base_volume,
                    taker_buy_quote_volume = EXCLUDED.taker_buy_quote_volume,
                    updated_at = NOW()
            """
            
            await self.db.execute(
                query,
                candle.symbol, candle.interval, candle.open_time, candle.close_time,
                candle.open_price, candle.high_price, candle.low_price, candle.close_price,
                candle.volume, candle.quote_volume, candle.number_of_trades,
                candle.taker_buy_base_volume, candle.taker_buy_quote_volume,
                candle.data_source, candle.raw_data
            )
            
            self.stats["candles_inserted"] += 1
            return True
            
        except Exception as e:
            self.stats["query_errors"] += 1
            logger.error(f"Failed to insert candle: {e}")
            return False
    
    async def bulk_insert_candles(self, candles: List[MarketDataCandle], 
                                 batch_size: int = 1000) -> Tuple[int, int]:
        """
        Bulk insert candles with batching for performance
        
        Args:
            candles: List of MarketDataCandle instances
            batch_size: Number of candles per batch
            
        Returns:
            Tuple[int, int]: (inserted_count, updated_count)
        """
        if not candles:
            return 0, 0
        
        inserted_count = 0
        updated_count = 0
        
        try:
            # Process in batches
            for i in range(0, len(candles), batch_size):
                batch = candles[i:i + batch_size]
                
                # Prepare bulk insert data
                values = []
                for candle in batch:
                    values.append((
                        candle.symbol, candle.interval, candle.open_time, candle.close_time,
                        candle.open_price, candle.high_price, candle.low_price, candle.close_price,
                        candle.volume, candle.quote_volume, candle.number_of_trades,
                        candle.taker_buy_base_volume, candle.taker_buy_quote_volume,
                        candle.data_source, candle.raw_data
                    ))
                
                # Execute bulk insert with conflict resolution
                query = """
                    INSERT INTO market_data_candles 
                    (symbol, interval, open_time, close_time, open_price, high_price, 
                     low_price, close_price, volume, quote_volume, number_of_trades,
                     taker_buy_base_volume, taker_buy_quote_volume, data_source, raw_data)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    ON CONFLICT (symbol, interval, open_time) 
                    DO UPDATE SET
                        high_price = EXCLUDED.high_price,
                        low_price = EXCLUDED.low_price,
                        close_price = EXCLUDED.close_price,
                        volume = EXCLUDED.volume,
                        quote_volume = EXCLUDED.quote_volume,
                        number_of_trades = EXCLUDED.number_of_trades,
                        taker_buy_base_volume = EXCLUDED.taker_buy_base_volume,
                        taker_buy_quote_volume = EXCLUDED.taker_buy_quote_volume,
                        updated_at = NOW()
                """
                
                await self.db.executemany(query, values)
                
                # Estimate insert vs update counts (simplified)
                batch_inserted = len(batch)  # Approximate
                inserted_count += batch_inserted
                
                logger.debug(f"Processed batch {i//batch_size + 1}: {len(batch)} candles")
            
            self.stats["candles_inserted"] += inserted_count
            self.stats["batch_operations"] += 1
            
            logger.info(f"Bulk inserted {len(candles)} candles in batches of {batch_size}")
            return inserted_count, updated_count
            
        except Exception as e:
            self.stats["query_errors"] += 1
            logger.error(f"Bulk insert failed: {e}")
            raise QueryError(f"Failed to bulk insert candles: {e}")
    
    async def get_candles(self, symbol: str, interval: str, 
                         start_time: Optional[datetime] = None,
                         end_time: Optional[datetime] = None,
                         limit: Optional[int] = None,
                         order_desc: bool = False) -> List[Dict[str, Any]]:
        """
        Get candles with flexible filtering
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            interval: Candle interval (e.g., '1m', '5m', '1h')
            start_time: Start time filter (inclusive)
            end_time: End time filter (inclusive)
            limit: Maximum number of candles
            order_desc: Order by time descending (newest first)
            
        Returns:
            List[Dict]: Candle data as dictionaries
        """
        try:
            conditions = ["symbol = $1", "interval = $2"]
            params = [symbol.upper(), interval]
            param_count = 2
            
            # Add time filters
            if start_time:
                param_count += 1
                conditions.append(f"open_time >= ${param_count}")
                params.append(start_time)
            
            if end_time:
                param_count += 1
                conditions.append(f"open_time <= ${param_count}")
                params.append(end_time)
            
            # Build query
            order_clause = "DESC" if order_desc else "ASC"
            limit_clause = f"LIMIT {limit}" if limit else ""
            
            query = f"""
                SELECT 
                    id, symbol, interval, open_time, close_time,
                    open_price, high_price, low_price, close_price, volume,
                    quote_volume, number_of_trades, taker_buy_base_volume, 
                    taker_buy_quote_volume, data_source, created_at
                FROM market_data_candles 
                WHERE {' AND '.join(conditions)}
                ORDER BY open_time {order_clause}
                {limit_clause}
            """
            
            results = await self.db.fetch(query, *params)
            
            # Convert to dictionaries
            candles = []
            for row in results:
                candles.append({
                    'id': row['id'],
                    'symbol': row['symbol'],
                    'interval': row['interval'],
                    'open_time': row['open_time'].isoformat(),
                    'close_time': row['close_time'].isoformat(),
                    'open': float(row['open_price']),
                    'high': float(row['high_price']),
                    'low': float(row['low_price']),
                    'close': float(row['close_price']),
                    'volume': float(row['volume']),
                    'quote_volume': float(row['quote_volume']) if row['quote_volume'] else 0,
                    'number_of_trades': row['number_of_trades'],
                    'taker_buy_base_volume': float(row['taker_buy_base_volume']) if row['taker_buy_base_volume'] else 0,
                    'taker_buy_quote_volume': float(row['taker_buy_quote_volume']) if row['taker_buy_quote_volume'] else 0,
                    'data_source': row['data_source'],
                    'created_at': row['created_at'].isoformat()
                })
            
            self.stats["candles_queried"] += len(candles)
            
            logger.debug(f"Retrieved {len(candles)} candles for {symbol} {interval}")
            return candles
            
        except Exception as e:
            self.stats["query_errors"] += 1
            logger.error(f"Failed to get candles: {e}")
            raise QueryError(f"Failed to retrieve candles: {e}")
    
    async def get_latest_candle(self, symbol: str, interval: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent candle for symbol/interval
        
        Args:
            symbol: Trading symbol
            interval: Candle interval
            
        Returns:
            Optional[Dict]: Latest candle data or None
        """
        try:
            candles = await self.get_candles(
                symbol=symbol,
                interval=interval,
                limit=1,
                order_desc=True
            )
            
            return candles[0] if candles else None
            
        except Exception as e:
            logger.error(f"Failed to get latest candle: {e}")
            return None
    
    async def get_candles_range(self, symbol: str, interval: str, 
                               hours_back: int = 24) -> List[Dict[str, Any]]:
        """
        Get candles for the last N hours
        
        Args:
            symbol: Trading symbol
            interval: Candle interval
            hours_back: Number of hours to look back
            
        Returns:
            List[Dict]: Candle data
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_back)
        
        return await self.get_candles(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            order_desc=False
        )
    
    async def calculate_sma(self, symbol: str, interval: str, 
                           periods: int = 20, hours_back: int = 168) -> List[Dict[str, Any]]:
        """
        Calculate Simple Moving Average
        
        Args:
            symbol: Trading symbol
            interval: Candle interval
            periods: Number of periods for SMA
            hours_back: Hours of data to analyze
            
        Returns:
            List[Dict]: Candles with SMA values
        """
        try:
            query = """
                SELECT 
                    open_time, close_price,
                    AVG(close_price) OVER (
                        ORDER BY open_time 
                        ROWS BETWEEN $3-1 PRECEDING AND CURRENT ROW
                    ) as sma
                FROM market_data_candles 
                WHERE symbol = $1 AND interval = $2
                    AND open_time >= $4
                ORDER BY open_time
            """
            
            start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            
            results = await self.db.fetch(
                query, symbol.upper(), interval, periods, start_time
            )
            
            sma_data = []
            for row in results:
                sma_data.append({
                    'open_time': row['open_time'].isoformat(),
                    'close_price': float(row['close_price']),
                    'sma': float(row['sma']) if row['sma'] else None
                })
            
            logger.debug(f"Calculated SMA({periods}) for {len(results)} candles")
            return sma_data
            
        except Exception as e:
            self.stats["query_errors"] += 1
            logger.error(f"Failed to calculate SMA: {e}")
            raise QueryError(f"Failed to calculate SMA: {e}")
    
    async def get_price_statistics(self, symbol: str, interval: str, 
                                  hours_back: int = 24) -> Dict[str, Any]:
        """
        Get price statistics for the specified period
        
        Args:
            symbol: Trading symbol
            interval: Candle interval
            hours_back: Hours to analyze
            
        Returns:
            Dict: Price statistics
        """
        try:
            query = """
                SELECT 
                    COUNT(*) as candle_count,
                    MIN(low_price) as lowest_price,
                    MAX(high_price) as highest_price,
                    AVG(close_price) as avg_price,
                    STDDEV(close_price) as price_stddev,
                    SUM(volume) as total_volume,
                    AVG(volume) as avg_volume
                FROM market_data_candles 
                WHERE symbol = $1 AND interval = $2
                    AND open_time >= $3
            """
            
            start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            result = await self.db.fetchrow(query, symbol.upper(), interval, start_time)
            
            if result:
                return {
                    'symbol': symbol,
                    'interval': interval,
                    'period_hours': hours_back,
                    'candle_count': result['candle_count'],
                    'lowest_price': float(result['lowest_price']) if result['lowest_price'] else 0,
                    'highest_price': float(result['highest_price']) if result['highest_price'] else 0,
                    'avg_price': float(result['avg_price']) if result['avg_price'] else 0,
                    'price_stddev': float(result['price_stddev']) if result['price_stddev'] else 0,
                    'total_volume': float(result['total_volume']) if result['total_volume'] else 0,
                    'avg_volume': float(result['avg_volume']) if result['avg_volume'] else 0,
                    'price_range': float(result['highest_price'] - result['lowest_price']) if result['highest_price'] and result['lowest_price'] else 0,
                }
            
            return {}
            
        except Exception as e:
            self.stats["query_errors"] += 1
            logger.error(f"Failed to get price statistics: {e}")
            return {}
    
    async def delete_old_candles(self, symbol: str, interval: str, 
                                days_to_keep: int = 365) -> int:
        """
        Delete old candles beyond retention period
        
        Args:
            symbol: Trading symbol
            interval: Candle interval
            days_to_keep: Number of days to retain
            
        Returns:
            int: Number of deleted candles
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            
            result = await self.db.execute("""
                DELETE FROM market_data_candles 
                WHERE symbol = $1 AND interval = $2 AND open_time < $3
            """, symbol.upper(), interval, cutoff_time)
            
            # Extract number of affected rows from result
            deleted_count = int(result.split()[-1]) if result else 0
            
            logger.info(f"Deleted {deleted_count} old candles for {symbol} {interval}")
            return deleted_count
            
        except Exception as e:
            self.stats["query_errors"] += 1
            logger.error(f"Failed to delete old candles: {e}")
            return 0
    
    async def get_data_coverage(self, symbol: str, interval: str) -> Dict[str, Any]:
        """
        Get data coverage information
        
        Args:
            symbol: Trading symbol
            interval: Candle interval
            
        Returns:
            Dict: Coverage statistics
        """
        try:
            query = """
                SELECT 
                    COUNT(*) as total_candles,
                    MIN(open_time) as earliest_candle,
                    MAX(open_time) as latest_candle,
                    MAX(created_at) as last_updated
                FROM market_data_candles 
                WHERE symbol = $1 AND interval = $2
            """
            
            result = await self.db.fetchrow(query, symbol.upper(), interval)
            
            if result and result['total_candles']:
                coverage = {
                    'symbol': symbol,
                    'interval': interval,
                    'total_candles': result['total_candles'],
                    'earliest_candle': result['earliest_candle'].isoformat(),
                    'latest_candle': result['latest_candle'].isoformat(),
                    'last_updated': result['last_updated'].isoformat(),
                    'coverage_days': (result['latest_candle'] - result['earliest_candle']).days
                }
                
                return coverage
            
            return {
                'symbol': symbol,
                'interval': interval,
                'total_candles': 0,
                'coverage_days': 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get data coverage: {e}")
            return {}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get repository statistics"""
        return {
            **self.stats,
            'total_operations': (
                self.stats['candles_inserted'] + 
                self.stats['candles_updated'] + 
                self.stats['candles_queried']
            ),
            'error_rate': (
                (self.stats['query_errors'] / max(1, self.stats['candles_queried'])) * 100
            ) if self.stats['candles_queried'] > 0 else 0
        }
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        stats = self.get_stats()
        return (f"MarketDataRepository(inserted={stats['candles_inserted']}, "
                f"queried={stats['candles_queried']}, errors={stats['query_errors']})")


# Export main components
__all__ = ["MarketDataRepository"]
