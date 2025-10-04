"""
Database Repositories Module

Provides repository pattern implementations for database operations.
Repositories abstract database access and provide business-logic methods
for data manipulation and queries.
"""

import logging
from typing import Optional

from .market_data_repository import MarketDataRepository

logger = logging.getLogger(__name__)

# Global repository instances (singleton pattern)
_market_data_repo: Optional[MarketDataRepository] = None

async def get_market_data_repository() -> MarketDataRepository:
    """
    Get or create market data repository instance
    
    Returns:
        MarketDataRepository: Repository instance
        
    Raises:
        RuntimeError: If database is not initialized
    """
    global _market_data_repo
    
    if _market_data_repo is None:
        from ..connections import get_connection_manager
        connection_manager = await get_connection_manager()
        _market_data_repo = MarketDataRepository(connection_manager)
    
    return _market_data_repo

def close_repositories():
    """Close and cleanup all repository instances"""
    global _market_data_repo
    
    if _market_data_repo is not None:
        _market_data_repo = None
        logger.info("Repositories closed and cleaned up")

# Future repository getters will be added here:
# async def get_signal_repository() -> SignalRepository:
# async def get_user_repository() -> UserRepository:
# async def get_strategy_repository() -> StrategyRepository:

# Re-export repository classes
__all__ = [
    # Repository classes
    "MarketDataRepository",
    
    # Repository getters
    "get_market_data_repository",
    
    # Management functions
    "close_repositories"
]

logger.info("Database repositories module loaded")
