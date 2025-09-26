"""
Database Migrations Module

Handles database schema versioning and migration execution.
Provides tools for creating, applying, and tracking database migrations.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Migration directory path
MIGRATIONS_DIR = Path(__file__).parent

def get_migration_files() -> List[Path]:
    """
    Get all migration SQL files in order
    
    Returns:
        List[Path]: Sorted list of migration files
    """
    try:
        migration_files = sorted([
            f for f in MIGRATIONS_DIR.glob("*.sql")
            if f.is_file() and f.name[0].isdigit()
        ])
        
        logger.debug(f"Found {len(migration_files)} migration files")
        return migration_files
        
    except Exception as e:
        logger.error(f"Failed to get migration files: {e}")
        return []

def get_migration_info(migration_file: Path) -> Dict[str, Any]:
    """
    Extract information from migration file
    
    Args:
        migration_file: Path to migration file
        
    Returns:
        Dict: Migration metadata
    """
    try:
        name = migration_file.stem
        content = migration_file.read_text(encoding='utf-8')
        
        # Extract description from first comment line
        description = "No description"
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('-- Description:'):
                description = line.replace('-- Description:', '').strip()
                break
            elif line.startswith('/*') and 'Description:' in line:
                description = line.split('Description:')[1].split('*/')[0].strip()
                break
        
        # Calculate checksum
        import hashlib
        checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        return {
            'name': name,
            'file_path': str(migration_file),
            'description': description,
            'checksum': checksum,
            'size_bytes': len(content.encode())
        }
        
    except Exception as e:
        logger.error(f"Failed to get migration info for {migration_file}: {e}")
        return {
            'name': migration_file.stem,
            'error': str(e)
        }

def validate_migration_sequence() -> bool:
    """
    Validate that migration files have proper sequential numbering
    
    Returns:
        bool: True if sequence is valid
    """
    try:
        migration_files = get_migration_files()
        
        if not migration_files:
            logger.warning("No migration files found")
            return True
        
        # Check sequential numbering
        expected_number = 1
        for migration_file in migration_files:
            name = migration_file.stem
            
            # Extract number from filename (e.g., "001" from "001_create_tables.sql")
            try:
                number_part = name.split('_')[0]
                actual_number = int(number_part)
                
                if actual_number != expected_number:
                    logger.error(f"Migration sequence broken: expected {expected_number:03d}, found {actual_number:03d}")
                    return False
                
                expected_number += 1
                
            except (ValueError, IndexError):
                logger.error(f"Invalid migration filename format: {name}")
                return False
        
        logger.debug(f"Migration sequence validated: {len(migration_files)} files")
        return True
        
    except Exception as e:
        logger.error(f"Failed to validate migration sequence: {e}")
        return False

async def get_applied_migrations(connection_manager) -> List[str]:
    """
    Get list of applied migrations from database
    
    Args:
        connection_manager: Database connection manager
        
    Returns:
        List[str]: Names of applied migrations
    """
    try:
        results = await connection_manager.fetch(
            "SELECT migration_name FROM database_migrations ORDER BY applied_at"
        )
        
        return [row['migration_name'] for row in results]
        
    except Exception as e:
        logger.error(f"Failed to get applied migrations: {e}")
        return []

async def get_pending_migrations(connection_manager) -> List[Path]:
    """
    Get list of pending migrations
    
    Args:
        connection_manager: Database connection manager
        
    Returns:
        List[Path]: Pending migration files
    """
    try:
        all_migrations = get_migration_files()
        applied_migrations = await get_applied_migrations(connection_manager)
        
        pending = [
            migration for migration in all_migrations
            if migration.stem not in applied_migrations
        ]
        
        logger.debug(f"Found {len(pending)} pending migrations")
        return pending
        
    except Exception as e:
        logger.error(f"Failed to get pending migrations: {e}")
        return []

def get_migration_status() -> Dict[str, Any]:
    """
    Get overall migration status
    
    Returns:
        Dict: Migration status information
    """
    try:
        all_migrations = get_migration_files()
        sequence_valid = validate_migration_sequence()
        
        status = {
            'total_migrations': len(all_migrations),
            'sequence_valid': sequence_valid,
            'migrations_directory': str(MIGRATIONS_DIR),
            'migration_files': [
                get_migration_info(migration) for migration in all_migrations
            ]
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Failed to get migration status: {e}")
        return {
            'error': str(e),
            'total_migrations': 0,
            'sequence_valid': False
        }

# Export main functions
__all__ = [
    "get_migration_files",
    "get_migration_info", 
    "validate_migration_sequence",
    "get_applied_migrations",
    "get_pending_migrations",
    "get_migration_status",
    "MIGRATIONS_DIR"
]

logger.info(f"Migrations module loaded from {MIGRATIONS_DIR}")
