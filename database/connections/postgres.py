"""
PostgreSQL Connection Manager

Production-ready PostgreSQL connection management with:
- Async connection pooling via asyncpg
- Automatic reconnection and health monitoring
- Migration system integration
- Query performance monitoring
- Transaction management
- Error handling and recovery
"""

import asyncio
import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, AsyncContextManager, Union
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from asyncpg import Pool, Connection, Record

from ..config import DatabaseConfig

logger = logging.getLogger(__name__)


class ConnectionError(Exception):
    """Database connection related errors"""
    pass


class QueryError(Exception):
    """Database query execution errors"""
    pass


class MigrationError(Exception):
    """Database migration related errors"""
    pass


class PostgreSQLManager:
    """
    Production-ready PostgreSQL connection manager
    
    Features:
    - Connection pooling with automatic reconnection
    - Query performance monitoring
    - Migration management
    - Health checks and diagnostics
    - Transaction context managers
    - Prepared statement caching
    """
    
    def __init__(self, config: DatabaseConfig):
        """
        Initialize PostgreSQL manager
        
        Args:
            config: Database configuration
        """
        self.config = config
        self.pool: Optional[Pool] = None
        self.is_initialized = False
        self.is_healthy = False
        
        # Statistics and monitoring
        self.stats = {
            "connections_created": 0,
            "connections_closed": 0,
            "queries_executed": 0,
            "slow_queries": 0,
            "query_errors": 0,
            "connection_errors": 0,
            "migrations_executed": 0,
            "last_health_check": None,
            "start_time": datetime.now(),
            "total_query_time": 0.0,
            "average_query_time": 0.0
        }
        
        # Health monitoring
        self.last_successful_query = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        
        # Migration tracking
        self.migrations_path = Path(__file__).parent.parent / "migrations"
        self.applied_migrations: List[str] = []
        
        logger.info(f"PostgreSQL manager initialized for {config.get_host()}")
    
    async def initialize(self) -> bool:
        """
        Initialize database connection pool
        
        Returns:
            bool: True if initialization successful
        """
        try:
            logger.info("Initializing PostgreSQL connection pool...")
            
            # Validate configuration
            self.config.validate()
            
            # Create connection pool
            await self._create_connection_pool()
            
            # Test connection
            await self._test_connection()
            
            # Initialize migration table
            await self._initialize_migrations_table()
            
            self.is_initialized = True
            self.is_healthy = True
            
            logger.info(f"PostgreSQL initialized successfully with {self.config.min_pool_size}-{self.config.max_pool_size} connection pool")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL: {e}")
            logger.error(traceback.format_exc())
            self.is_initialized = False
            self.is_healthy = False
            raise ConnectionError(f"Database initialization failed: {e}")
    
    async def _create_connection_pool(self):
        """Create asyncpg connection pool"""
        try:
            connection_string = self.config.get_connection_string()
            pool_kwargs = self.config.get_pool_kwargs()
            
            logger.info(f"Creating connection pool: min={pool_kwargs['min_size']}, max={pool_kwargs['max_size']}")
            
            self.pool = await asyncpg.create_pool(
                connection_string,
                **pool_kwargs,
                init=self._init_connection
            )
            
            self.stats["connections_created"] += pool_kwargs['min_size']
            logger.info("Connection pool created successfully")
            
        except Exception as e:
            self.stats["connection_errors"] += 1
            raise ConnectionError(f"Failed to create connection pool: {e}")
    
    async def _init_connection(self, connection: Connection):
        """Initialize each new connection in the pool"""
        try:
            # Set timezone
            await connection.execute(f"SET timezone = '{self.config.timezone}'")
            
            # Set application name for monitoring
            await connection.execute("SET application_name = 'trading_bot'")
            
            # Set statement timeout
            if self.config.query_timeout > 0:
                await connection.execute(f"SET statement_timeout = '{self.config.query_timeout}s'")
            
            logger.debug("Connection initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize connection: {e}")
            raise
    
    async def _test_connection(self):
        """Test database connection"""
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchval("SELECT 1")
                if result != 1:
                    raise ConnectionError("Connection test failed")
                
                # Test database accessibility
                await conn.fetchval("SELECT current_database()")
                
                logger.info("Database connection test passed")
                self.last_successful_query = datetime.now()
                
        except Exception as e:
            self.stats["connection_errors"] += 1
            raise ConnectionError(f"Database connection test failed: {e}")
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncContextManager[Connection]:
        """
        Get database connection from pool
        
        Usage:
            async with manager.get_connection() as conn:
                result = await conn.fetchval("SELECT 1")
        
        Yields:
            Connection: Database connection
        """
        if not self.pool:
            raise ConnectionError("Database pool not initialized")
        
        connection = None
        start_time = time.time()
        
        try:
            connection = await self.pool.acquire(timeout=self.config.connection_timeout)
            yield connection
            
            # Update success stats
            query_time = time.time() - start_time
            self._update_query_stats(query_time, success=True)
            self.last_successful_query = datetime.now()
            self.consecutive_failures = 0
            
        except Exception as e:
            # Update error stats
            self.stats["connection_errors"] += 1
            self.consecutive_failures += 1
            
            if self.consecutive_failures >= self.max_consecutive_failures:
                self.is_healthy = False
                logger.error(f"Database marked as unhealthy after {self.consecutive_failures} consecutive failures")
            
            logger.error(f"Database connection error: {e}")
            raise ConnectionError(f"Failed to acquire database connection: {e}")
            
        finally:
            if connection:
                try:
                    await self.pool.release(connection)
                except Exception as e:
                    logger.error(f"Failed to release connection: {e}")
    
    @asynccontextmanager
    async def get_transaction(self) -> AsyncContextManager[Connection]:
        """
        Get database connection with transaction
        
        Usage:
            async with manager.get_transaction() as conn:
                await conn.execute("INSERT INTO table ...")
                # Automatically commits on success, rolls back on exception
        
        Yields:
            Connection: Database connection with active transaction
        """
        async with self.get_connection() as conn:
            async with conn.transaction():
                yield conn
    
    async def execute(self, query: str, *args, timeout: Optional[float] = None) -> str:
        """
        Execute a SQL query that doesn't return data
        
        Args:
            query: SQL query string
            *args: Query parameters
            timeout: Query timeout override
            
        Returns:
            str: Query execution status
        """
        start_time = time.time()
        
        try:
            async with self.get_connection() as conn:
                if timeout:
                    result = await asyncio.wait_for(
                        conn.execute(query, *args),
                        timeout=timeout
                    )
                else:
                    result = await conn.execute(query, *args)
                
                query_time = time.time() - start_time
                self._update_query_stats(query_time, success=True)
                
                if self.config.enable_query_logging:
                    logger.debug(f"Query executed in {query_time:.3f}s: {query[:100]}...")
                
                return result
                
        except Exception as e:
            query_time = time.time() - start_time
            self._update_query_stats(query_time, success=False)
            
            logger.error(f"Query execution failed after {query_time:.3f}s: {e}")
            logger.error(f"Query: {query[:200]}...")
            raise QueryError(f"Failed to execute query: {e}")
    
    async def fetch(self, query: str, *args, timeout: Optional[float] = None) -> List[Record]:
        """
        Execute a SQL query and return all results
        
        Args:
            query: SQL query string
            *args: Query parameters
            timeout: Query timeout override
            
        Returns:
            List[Record]: Query results
        """
        start_time = time.time()
        
        try:
            async with self.get_connection() as conn:
                if timeout:
                    result = await asyncio.wait_for(
                        conn.fetch(query, *args),
                        timeout=timeout
                    )
                else:
                    result = await conn.fetch(query, *args)
                
                query_time = time.time() - start_time
                self._update_query_stats(query_time, success=True)
                
                if self.config.enable_query_logging:
                    logger.debug(f"Query returned {len(result)} rows in {query_time:.3f}s: {query[:100]}...")
                
                return result
                
        except Exception as e:
            query_time = time.time() - start_time
            self._update_query_stats(query_time, success=False)
            
            logger.error(f"Query fetch failed after {query_time:.3f}s: {e}")
            logger.error(f"Query: {query[:200]}...")
            raise QueryError(f"Failed to fetch query results: {e}")
    
    async def fetchval(self, query: str, *args, timeout: Optional[float] = None) -> Any:
        """
        Execute a SQL query and return single value
        
        Args:
            query: SQL query string
            *args: Query parameters
            timeout: Query timeout override
            
        Returns:
            Any: Single query result value
        """
        start_time = time.time()
        
        try:
            async with self.get_connection() as conn:
                if timeout:
                    result = await asyncio.wait_for(
                        conn.fetchval(query, *args),
                        timeout=timeout
                    )
                else:
                    result = await conn.fetchval(query, *args)
                
                query_time = time.time() - start_time
                self._update_query_stats(query_time, success=True)
                
                if self.config.enable_query_logging:
                    logger.debug(f"Query returned value in {query_time:.3f}s: {query[:100]}...")
                
                return result
                
        except Exception as e:
            query_time = time.time() - start_time
            self._update_query_stats(query_time, success=False)
            
            logger.error(f"Query fetchval failed after {query_time:.3f}s: {e}")
            logger.error(f"Query: {query[:200]}...")
            raise QueryError(f"Failed to fetch query value: {e}")
    
    async def fetchrow(self, query: str, *args, timeout: Optional[float] = None) -> Optional[Record]:
        """
        Execute a SQL query and return single row
        
        Args:
            query: SQL query string
            *args: Query parameters
            timeout: Query timeout override
            
        Returns:
            Optional[Record]: Single query result row
        """
        start_time = time.time()
        
        try:
            async with self.get_connection() as conn:
                if timeout:
                    result = await asyncio.wait_for(
                        conn.fetchrow(query, *args),
                        timeout=timeout
                    )
                else:
                    result = await conn.fetchrow(query, *args)
                
                query_time = time.time() - start_time
                self._update_query_stats(query_time, success=True)
                
                if self.config.enable_query_logging:
                    logger.debug(f"Query returned row in {query_time:.3f}s: {query[:100]}...")
                
                return result
                
        except Exception as e:
            query_time = time.time() - start_time
            self._update_query_stats(query_time, success=False)
            
            logger.error(f"Query fetchrow failed after {query_time:.3f}s: {e}")
            logger.error(f"Query: {query[:200]}...")
            raise QueryError(f"Failed to fetch query row: {e}")
    
    async def executemany(self, query: str, args: List[tuple], timeout: Optional[float] = None) -> None:
        """
        Execute a SQL query multiple times with different parameters
        
        Args:
            query: SQL query string
            args: List of parameter tuples
            timeout: Query timeout override
        """
        start_time = time.time()
        
        try:
            async with self.get_connection() as conn:
                if timeout:
                    await asyncio.wait_for(
                        conn.executemany(query, args),
                        timeout=timeout
                    )
                else:
                    await conn.executemany(query, args)
                
                query_time = time.time() - start_time
                self._update_query_stats(query_time, success=True)
                
                if self.config.enable_query_logging:
                    logger.debug(f"Batch query executed {len(args)} times in {query_time:.3f}s: {query[:100]}...")
                
        except Exception as e:
            query_time = time.time() - start_time
            self._update_query_stats(query_time, success=False)
            
            logger.error(f"Batch query execution failed after {query_time:.3f}s: {e}")
            logger.error(f"Query: {query[:200]}...")
            raise QueryError(f"Failed to execute batch query: {e}")
    
    def _update_query_stats(self, query_time: float, success: bool):
        """Update query execution statistics"""
        self.stats["queries_executed"] += 1
        self.stats["total_query_time"] += query_time
        
        if success:
            self.stats["average_query_time"] = (
                self.stats["total_query_time"] / self.stats["queries_executed"]
            )
        else:
            self.stats["query_errors"] += 1
        
        if query_time > self.config.slow_query_threshold:
            self.stats["slow_queries"] += 1
            if self.config.enable_query_logging:
                logger.warning(f"Slow query detected: {query_time:.3f}s")
    
    async def _initialize_migrations_table(self):
        """Initialize migrations tracking table"""
        try:
            await self.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.migrations_table} (
                    id SERIAL PRIMARY KEY,
                    migration_name VARCHAR(255) UNIQUE NOT NULL,
                    applied_at TIMESTAMPTZ DEFAULT NOW(),
                    checksum VARCHAR(64),
                    execution_time_ms INTEGER
                )
            """)
            
            logger.info("Migrations table initialized")
            
        except Exception as e:
            raise MigrationError(f"Failed to initialize migrations table: {e}")
    
    async def run_migrations(self) -> bool:
        """
        Run pending database migrations
        
        Returns:
            bool: True if migrations completed successfully
        """
        if not self.config.auto_migrate:
            logger.info("Auto-migration disabled, skipping")
            return True
        
        try:
            logger.info("Checking for pending migrations...")
            
            # Get applied migrations
            applied = await self.fetch(
                f"SELECT migration_name FROM {self.config.migrations_table} ORDER BY applied_at"
            )
            self.applied_migrations = [row['migration_name'] for row in applied]
            
            # Find migration files
            if not self.migrations_path.exists():
                logger.warning(f"Migrations directory not found: {self.migrations_path}")
                return True
            
            migration_files = sorted([
                f for f in self.migrations_path.glob("*.sql") 
                if f.is_file()
            ])
            
            if not migration_files:
                logger.info("No migration files found")
                return True
            
            # Execute pending migrations
            executed_count = 0
            for migration_file in migration_files:
                migration_name = migration_file.stem
                
                if migration_name not in self.applied_migrations:
                    success = await self._execute_migration(migration_file)
                    if success:
                        executed_count += 1
                        self.stats["migrations_executed"] += 1
                    else:
                        logger.error(f"Migration failed, stopping: {migration_name}")
                        return False
            
            if executed_count > 0:
                logger.info(f"Applied {executed_count} database migrations successfully")
            else:
                logger.info("All migrations already applied")
            
            return True
            
        except Exception as e:
            logger.error(f"Migration execution failed: {e}")
            raise MigrationError(f"Failed to run migrations: {e}")
    
    async def _execute_migration(self, migration_file: Path) -> bool:
        """Execute a single migration file"""
        migration_name = migration_file.stem
        start_time = time.time()
        
        try:
            logger.info(f"Executing migration: {migration_name}")
            
            # Read migration SQL
            sql_content = migration_file.read_text(encoding='utf-8')
            
            # Calculate checksum for integrity
            import hashlib
            checksum = hashlib.sha256(sql_content.encode()).hexdigest()[:16]
            
            # Execute migration in transaction
            async with self.get_transaction() as conn:
                # Execute migration SQL
                await conn.execute(sql_content)
                
                # Record migration
                execution_time_ms = int((time.time() - start_time) * 1000)
                await conn.execute(
                    f"""INSERT INTO {self.config.migrations_table} 
                        (migration_name, checksum, execution_time_ms) 
                        VALUES ($1, $2, $3)""",
                    migration_name, checksum, execution_time_ms
                )
            
            logger.info(f"Migration completed: {migration_name} ({execution_time_ms}ms)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to execute migration {migration_name}: {e}")
            return False
    
    def _serialize_datetime_objects(self, obj):
        """
        Recursively serialize datetime objects to ISO strings
        
        Args:
            obj: Object that may contain datetime instances
            
        Returns:
            Object with datetime instances converted to strings
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {key: self._serialize_datetime_objects(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_datetime_objects(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._serialize_datetime_objects(item) for item in obj)
        else:
            return obj
    
    async def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive database health status
        
        Returns:
            dict: Health status information (JSON serializable)
        """
        health_status = {
            "healthy": self.is_healthy,
            "initialized": self.is_initialized,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Connection pool status
            if self.pool:
                pool_stats = {
                    "size": self.pool.get_size(),
                    "min_size": self.pool.get_min_size(),
                    "max_size": self.pool.get_max_size(),
                    "idle_connections": self.pool.get_idle_size()
                }
                health_status["connection_pool"] = pool_stats
            
            # Quick connectivity test
            start_time = time.time()
            await self.fetchval("SELECT 1")
            response_time_ms = (time.time() - start_time) * 1000
            
            health_status.update({
                "connectivity": "ok",
                "response_time_ms": round(response_time_ms, 2),
                "last_successful_query": self.last_successful_query.isoformat() if self.last_successful_query else None,
                "consecutive_failures": self.consecutive_failures
            })
            
            # Performance statistics - serialize all datetime objects
            uptime_seconds = (datetime.now() - self.stats["start_time"]).total_seconds()
            serialized_stats = self._serialize_datetime_objects(self.stats.copy())
            
            health_status["performance"] = {
                **serialized_stats,
                "uptime_seconds": uptime_seconds,
                "queries_per_second": self.stats["queries_executed"] / uptime_seconds if uptime_seconds > 0 else 0,
                "error_rate": (self.stats["query_errors"] / self.stats["queries_executed"] * 100) if self.stats["queries_executed"] > 0 else 0
            }
            
            # Migration status
            health_status["migrations"] = {
                "applied_count": len(self.applied_migrations),
                "last_migration": self.applied_migrations[-1] if self.applied_migrations else None
            }
            
        except Exception as e:
            health_status.update({
                "connectivity": "failed",
                "error": str(e),
                "healthy": False
            })
            
            logger.error(f"Health check failed: {e}")
        
        # Update last health check timestamp (already serialized)
        self.stats["last_health_check"] = datetime.now().isoformat()
        return health_status
    
    async def close(self):
        """Close database connections gracefully"""
        if self.pool:
            try:
                # Get final statistics
                final_stats = await self.get_health_status()
                
                # Close the pool
                await self.pool.close()
                self.stats["connections_closed"] += self.pool.get_size()
                
                logger.info("Database connection pool closed")
                logger.info(f"Final stats: {final_stats['performance']['queries_executed']} queries, "
                          f"{final_stats['performance']['error_rate']:.1f}% error rate, "
                          f"{final_stats['performance']['average_query_time']:.3f}s avg query time")
                
            except Exception as e:
                logger.error(f"Error closing database pool: {e}")
            finally:
                self.pool = None
                self.is_initialized = False
                self.is_healthy = False
    
    def get_serializable_stats(self) -> Dict[str, Any]:
        """
        Get statistics in JSON-serializable format
        
        Returns:
            dict: Statistics with datetime objects converted to strings
        """
        uptime = None
        if self.stats["start_time"]:
            uptime = datetime.now() - self.stats["start_time"]
        
        serialized_stats = self._serialize_datetime_objects(self.stats.copy())
        
        return {
            **serialized_stats,
            "uptime": str(uptime).split('.')[0] if uptime else None,
            "is_initialized": self.is_initialized,
            "is_healthy": self.is_healthy,
            "success_rate": (
                (self.stats["queries_executed"] - self.stats["query_errors"]) / 
                max(1, self.stats["queries_executed"])
            ) * 100 if self.stats["queries_executed"] > 0 else 100
        }
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        status = "healthy" if self.is_healthy else "unhealthy"
        pool_info = f"pool={self.pool.get_size()}/{self.pool.get_max_size()}" if self.pool else "no_pool"
        
        return (f"PostgreSQLManager(host={self.config.get_host()}, "
                f"status={status}, {pool_info}, "
                f"queries={self.stats['queries_executed']})")


# Export main components
__all__ = [
    "PostgreSQLManager",
    "ConnectionError", 
    "QueryError",
    "MigrationError"
]
