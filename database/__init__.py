"""
Database module for cryptocurrency trading bot

Provides PostgreSQL-based persistence for:
- Historical market data (OHLCV candles)
- Trading signals and strategy performance
- User management and subscriptions
- Technical indicators and market analytics

Architecture:
- PostgreSQL as primary database for time-series data
- SQLAlchemy async ORM for database operations
- Connection pooling for performance
- Migration system for schema versioning
"""

import logging
from typing import Optional, Dict, Any
from .config import DatabaseConfig
from .connections.postgres import PostgreSQLManager

logger = logging.getLogger(__name__)

# Global database manager instance
_db_manager: Optional[PostgreSQLManager] = None

def get_database_manager() -> PostgreSQLManager:
    """
    Returns singleton database manager instance
    
    Returns:
        PostgreSQLManager: Configured database manager
        
    Raises:
        RuntimeError: If database is not initialized
    """
    global _db_manager
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return _db_manager

async def initialize_database(config: Optional[DatabaseConfig] = None) -> bool:
    """
    Initialize database connections and run migrations
    
    Args:
        config: Database configuration (defaults to environment config)
        
    Returns:
        bool: True if initialization successful
        
    Raises:
        Exception: If database initialization fails
    """
    global _db_manager
    
    try:
        if config is None:
            config = DatabaseConfig.from_environment()
        
        logger.info(f"Initializing database connection to {config.get_host()}")
        
        _db_manager = PostgreSQLManager(config)
        
        # Test connection
        success = await _db_manager.initialize()
        if not success:
            raise Exception("Failed to establish database connection")
        
        # Run migrations
        logger.info("Running database migrations...")
        migration_success = await _db_manager.run_migrations()
        if not migration_success:
            logger.warning("Database migrations completed with warnings")
        
        logger.info("Database initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        _db_manager = None
        raise

async def close_database():
    """Close database connections gracefully"""
    global _db_manager
    
    if _db_manager is not None:
        await _db_manager.close()
        _db_manager = None
        logger.info("Database connections closed")

async def get_database_health() -> Dict[str, Any]:
    """
    Check database health status
    
    Returns:
        dict: Health status information
    """
    if _db_manager is None:
        return {"status": "disconnected", "error": "Database not initialized"}
    
    return await _db_manager.get_health_status()

# Import main components for external use
try:
    from .models.market_data import MarketDataCandle, CandleInterval
    from .repositories.market_data_repository import MarketDataRepository
    
    # ✅ Алиас для обратной совместимости
    CandleRepository = MarketDataRepository
    
    # Future imports will be added here as modules are created
    # from .repositories.signal_repository import SignalRepository
    # from .repositories.user_repository import UserRepository
    
    __all__ = [
        # Core functions
        "initialize_database",
        "close_database", 
        "get_database_manager",
        "get_database_health",
        
        # Configuration
        "DatabaseConfig",
        
        # Models
        "MarketDataCandle",
        "CandleInterval",
        
        # Repositories  
        "MarketDataRepository",
        "CandleRepository",  # ✅ Алиас для обратной совместимости
        
        # Connection management
        "PostgreSQLManager"
    ]
    
except ImportError as e:
    logger.warning(f"Some database components not yet available: {e}")
    
    # Minimal exports for initial setup
    __all__ = [
        "initialize_database",
        "close_database",
        "get_database_manager", 
        "get_database_health",
        "DatabaseConfig"
    ]

# Version info
__version__ = "1.0.0"
__author__ = "Trading Bot Team"

# Database schema version (for migrations)
SCHEMA_VERSION = 1

logger.info(f"Database module loaded (version {__version__}, schema v{SCHEMA_VERSION})")
