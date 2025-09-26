"""
Database Models Module

SQLAlchemy models for cryptocurrency trading bot data storage.
Provides ORM models for time-series market data, trading signals, and user management.
"""

import logging
from typing import Dict, Any, List, Type

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from .market_data import MarketDataCandle, CandleInterval, Base

logger = logging.getLogger(__name__)

# Re-export Base for other models
__all__ = [
    "Base",
    "MarketDataCandle", 
    "CandleInterval",
    "get_all_models",
    "create_all_tables",
    "drop_all_tables"
]

def get_all_models() -> List[Type]:
    """
    Get all registered SQLAlchemy models
    
    Returns:
        List[Type]: List of all model classes
    """
    return [
        MarketDataCandle,
        # Future models will be added here:
        # TradingSignal,
        # User,
        # StrategyConfig,
        # etc.
    ]

async def create_all_tables(connection_manager, drop_existing: bool = False) -> bool:
    """
    Create all database tables
    
    Args:
        connection_manager: Database connection manager
        drop_existing: Whether to drop existing tables first
        
    Returns:
        bool: True if successful
    """
    try:
        if drop_existing:
            await drop_all_tables(connection_manager)
        
        # Get table creation SQL
        from sqlalchemy.schema import CreateTable
        
        models = get_all_models()
        for model in models:
            table = model.__table__
            create_sql = str(CreateTable(table).compile(compile_kwargs={"literal_binds": True}))
            
            try:
                await connection_manager.execute(create_sql)
                logger.info(f"Created table: {table.name}")
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.error(f"Failed to create table {table.name}: {e}")
                    raise
                else:
                    logger.debug(f"Table {table.name} already exists")
        
        logger.info(f"Successfully created {len(models)} database tables")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        return False

async def drop_all_tables(connection_manager) -> bool:
    """
    Drop all database tables
    
    Args:
        connection_manager: Database connection manager
        
    Returns:
        bool: True if successful
    """
    try:
        models = get_all_models()
        
        # Drop in reverse order to handle dependencies
        for model in reversed(models):
            table_name = model.__tablename__
            try:
                await connection_manager.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                logger.info(f"Dropped table: {table_name}")
            except Exception as e:
                logger.warning(f"Failed to drop table {table_name}: {e}")
        
        logger.info(f"Successfully dropped {len(models)} database tables")
        return True
        
    except Exception as e:
        logger.error(f"Failed to drop tables: {e}")
        return False

logger.info(f"Database models loaded: {len(get_all_models())} models available")
