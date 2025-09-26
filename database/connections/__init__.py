"""
Database Connections Module

Provides production-ready database connection management for PostgreSQL.
Includes connection pooling, health monitoring, and migration support.
"""

import logging
from typing import Optional, Dict, Any

from .postgres import (
    PostgreSQLManager,
    ConnectionError,
    QueryError, 
    MigrationError
)
from ..config import DatabaseConfig

logger = logging.getLogger(__name__)

# Global connection manager instance
_connection_manager: Optional[PostgreSQLManager] = None

async def get_connection_manager(config: Optional[DatabaseConfig] = None) -> PostgreSQLManager:
    """
    Get or create PostgreSQL connection manager
    
    Args:
        config: Database configuration (optional, uses environment if not provided)
        
    Returns:
        PostgreSQLManager: Initialized connection manager
        
    Raises:
        ConnectionError: If manager cannot be initialized
    """
    global _connection_manager
    
    if _connection_manager is None:
        if config is None:
            config = DatabaseConfig.from_environment()
        
        _connection_manager = PostgreSQLManager(config)
        
        # Initialize if not already done
        if not _connection_manager.is_initialized:
            await _connection_manager.initialize()
    
    return _connection_manager

async def close_connections():
    """Close all database connections"""
    global _connection_manager
    
    if _connection_manager is not None:
        await _connection_manager.close()
        _connection_manager = None
        logger.info("Database connections closed")

async def get_connection_health() -> Dict[str, Any]:
    """
    Get database connection health status
    
    Returns:
        dict: Health status information
    """
    if _connection_manager is None:
        return {
            "healthy": False,
            "error": "Connection manager not initialized"
        }
    
    return await _connection_manager.get_health_status()

# Re-export main components
__all__ = [
    # Connection Manager
    "PostgreSQLManager",
    
    # Helper functions
    "get_connection_manager",
    "close_connections", 
    "get_connection_health",
    
    # Exceptions
    "ConnectionError",
    "QueryError",
    "MigrationError"
]

logger.info("Database connections module loaded")
