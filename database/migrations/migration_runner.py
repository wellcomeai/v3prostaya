"""
Migration Runner

Standalone migration execution engine with rollback support,
validation, and comprehensive error handling.
"""

import logging
import asyncio
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from ..connections import get_connection_manager, close_connections
from ..config import DatabaseConfig
from . import (
    get_migration_files, 
    get_migration_info,
    validate_migration_sequence,
    get_applied_migrations,
    get_pending_migrations
)

logger = logging.getLogger(__name__)


class MigrationRunner:
    """
    Production-ready migration runner with rollback support
    """
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        Initialize migration runner
        
        Args:
            config: Database configuration (uses environment if not provided)
        """
        self.config = config or DatabaseConfig.from_environment()
        self.connection_manager = None
        
        # Migration tracking
        self.execution_log: List[Dict[str, Any]] = []
        self.failed_migrations: List[str] = []
        
        # Settings
        self.dry_run = False
        self.stop_on_error = True
        self.backup_before_migration = False
        
    async def initialize(self) -> bool:
        """Initialize database connection"""
        try:
            self.connection_manager = await get_connection_manager(self.config)
            logger.info("Migration runner initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize migration runner: {e}")
            return False
    
    async def run_migrations(self, target_migration: Optional[str] = None,
                           dry_run: bool = False) -> bool:
        """
        Run pending migrations
        
        Args:
            target_migration: Stop at specific migration (None = run all)
            dry_run: Preview migrations without executing
            
        Returns:
            bool: True if all migrations successful
        """
        self.dry_run = dry_run
        
        try:
            if not await self.initialize():
                return False
            
            logger.info(f"Starting migration run (dry_run={dry_run})")
            
            # Validate migration sequence
            if not validate_migration_sequence():
                logger.error("Migration sequence validation failed")
                return False
            
            # Get pending migrations
            pending_migrations = await get_pending_migrations(self.connection_manager)
            
            if not pending_migrations:
                logger.info("No pending migrations found")
                return True
            
            # Filter to target migration if specified
            if target_migration:
                target_index = None
                for i, migration in enumerate(pending_migrations):
                    if migration.stem == target_migration:
                        target_index = i + 1
                        break
                
                if target_index is None:
                    logger.error(f"Target migration not found: {target_migration}")
                    return False
                
                pending_migrations = pending_migrations[:target_index]
            
            logger.info(f"Found {len(pending_migrations)} pending migrations")
            
            # Execute migrations
            success_count = 0
            total_start_time = time.time()
            
            for migration_file in pending_migrations:
                if dry_run:
                    logger.info(f"[DRY RUN] Would execute: {migration_file.stem}")
                    success_count += 1
                else:
                    success = await self._execute_migration(migration_file)
                    if success:
                        success_count += 1
                    else:
                        self.failed_migrations.append(migration_file.stem)
                        if self.stop_on_error:
                            break
            
            # Summary
            total_time = time.time() - total_start_time
            
            if dry_run:
                logger.info(f"[DRY RUN] Would execute {success_count}/{len(pending_migrations)} migrations")
            else:
                logger.info(f"Migration run completed: {success_count}/{len(pending_migrations)} successful")
                logger.info(f"Total execution time: {total_time:.2f}s")
                
                if self.failed_migrations:
                    logger.error(f"Failed migrations: {self.failed_migrations}")
                    return False
            
            return success_count == len(pending_migrations)
            
        except Exception as e:
            logger.error(f"Migration run failed: {e}")
            return False
        finally:
            if self.connection_manager:
                await close_connections()
    
    async def _execute_migration(self, migration_file: Path) -> bool:
        """Execute a single migration file"""
        migration_name = migration_file.stem
        start_time = time.time()
        
        try:
            logger.info(f"Executing migration: {migration_name}")
            
            # Read migration SQL
            sql_content = migration_file.read_text(encoding='utf-8')
            
            # Calculate checksum
            import hashlib
            checksum = hashlib.sha256(sql_content.encode()).hexdigest()[:16]
            
            # Execute in transaction for safety
            async with self.connection_manager.get_transaction() as conn:
                try:
                    # Execute migration SQL
                    await conn.execute(sql_content)
                    
                    # Record migration
                    execution_time_ms = int((time.time() - start_time) * 1000)
                    await conn.execute("""
                        INSERT INTO database_migrations 
                        (migration_name, checksum, execution_time_ms) 
                        VALUES ($1, $2, $3)
                        ON CONFLICT (migration_name) DO UPDATE SET
                            checksum = EXCLUDED.checksum,
                            execution_time_ms = EXCLUDED.execution_time_ms,
                            applied_at = NOW()
                    """, migration_name, checksum, execution_time_ms)
                    
                    # Log execution
                    self.execution_log.append({
                        'migration': migration_name,
                        'status': 'success',
                        'execution_time_ms': execution_time_ms,
                        'checksum': checksum,
                        'executed_at': datetime.now().isoformat()
                    })
                    
                    logger.info(f"Migration completed: {migration_name} ({execution_time_ms}ms)")
                    return True
                    
                except Exception as e:
                    # Transaction will automatically rollback
                    logger.error(f"Migration execution failed: {migration_name}")
                    logger.error(f"Error: {e}")
                    
                    # Log failure
                    self.execution_log.append({
                        'migration': migration_name,
                        'status': 'failed',
                        'error': str(e),
                        'execution_time_ms': int((time.time() - start_time) * 1000),
                        'executed_at': datetime.now().isoformat()
                    })
                    
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to read/prepare migration {migration_name}: {e}")
            return False
    
    async def rollback_migration(self, migration_name: str) -> bool:
        """
        Rollback a specific migration
        
        Args:
            migration_name: Name of migration to rollback
            
        Returns:
            bool: True if rollback successful
        """
        try:
            if not await self.initialize():
                return False
            
            logger.warning(f"Rolling back migration: {migration_name}")
            
            # Check if migration was applied
            applied_migrations = await get_applied_migrations(self.connection_manager)
            if migration_name not in applied_migrations:
                logger.error(f"Migration not found in applied migrations: {migration_name}")
                return False
            
            # Look for rollback script
            rollback_file = Path(__file__).parent / f"{migration_name}_rollback.sql"
            
            if not rollback_file.exists():
                logger.error(f"No rollback script found: {rollback_file}")
                logger.warning("Manual rollback required")
                return False
            
            # Execute rollback
            rollback_sql = rollback_file.read_text(encoding='utf-8')
            
            async with self.connection_manager.get_transaction() as conn:
                await conn.execute(rollback_sql)
                
                # Remove from migrations table
                await conn.execute(
                    "DELETE FROM database_migrations WHERE migration_name = $1",
                    migration_name
                )
            
            logger.info(f"Migration rolled back successfully: {migration_name}")
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed for {migration_name}: {e}")
            return False
    
    async def get_migration_status(self) -> Dict[str, Any]:
        """Get comprehensive migration status"""
        try:
            if not await self.initialize():
                return {"error": "Failed to initialize"}
            
            # Get file and database info
            all_migrations = get_migration_files()
            applied_migrations = await get_applied_migrations(self.connection_manager)
            pending_migrations = await get_pending_migrations(self.connection_manager)
            
            # Get detailed applied migration info
            applied_details = await self.connection_manager.fetch("""
                SELECT migration_name, applied_at, checksum, execution_time_ms
                FROM database_migrations 
                ORDER BY applied_at DESC
            """)
            
            status = {
                'database_status': 'connected',
                'total_migrations': len(all_migrations),
                'applied_count': len(applied_migrations),
                'pending_count': len(pending_migrations),
                'last_migration': applied_migrations[-1] if applied_migrations else None,
                'sequence_valid': validate_migration_sequence(),
                'pending_migrations': [m.stem for m in pending_migrations],
                'applied_migrations': [
                    {
                        'name': row['migration_name'],
                        'applied_at': row['applied_at'].isoformat(),
                        'checksum': row['checksum'],
                        'execution_time_ms': row['execution_time_ms']
                    }
                    for row in applied_details
                ],
                'execution_log': self.execution_log,
                'failed_migrations': self.failed_migrations
            }
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get migration status: {e}")
            return {"error": str(e)}
    
    async def validate_database_schema(self) -> Dict[str, Any]:
        """Validate current database schema against migrations"""
        try:
            if not await self.initialize():
                return {"valid": False, "error": "Failed to initialize"}
            
            # Check core tables exist
            core_tables = ['database_migrations', 'market_data_candles']
            existing_tables = []
            
            for table in core_tables:
                exists = await self.connection_manager.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = $1 AND table_schema = 'public'
                    )
                """, table)
                
                if exists:
                    existing_tables.append(table)
            
            # Check indexes
            index_count = await self.connection_manager.fetchval("""
                SELECT COUNT(*) FROM pg_indexes 
                WHERE tablename = 'market_data_candles'
            """)
            
            validation = {
                'valid': len(existing_tables) == len(core_tables),
                'existing_tables': existing_tables,
                'missing_tables': [t for t in core_tables if t not in existing_tables],
                'index_count': index_count,
                'schema_version': len(await get_applied_migrations(self.connection_manager))
            }
            
            return validation
            
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            return {"valid": False, "error": str(e)}


async def main():
    """CLI interface for migration runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Migration Runner")
    parser.add_argument('--dry-run', action='store_true', help='Preview migrations without executing')
    parser.add_argument('--target', help='Target migration to stop at')
    parser.add_argument('--rollback', help='Rollback specific migration')
    parser.add_argument('--status', action='store_true', help='Show migration status')
    parser.add_argument('--validate', action='store_true', help='Validate database schema')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    runner = MigrationRunner()
    
    try:
        if args.status:
            status = await runner.get_migration_status()
            print("Migration Status:")
            print(f"Applied: {status.get('applied_count', 0)}")
            print(f"Pending: {status.get('pending_count', 0)}")
            print(f"Total: {status.get('total_migrations', 0)}")
            print(f"Last Migration: {status.get('last_migration', 'None')}")
            
        elif args.validate:
            validation = await runner.validate_database_schema()
            print("Schema Validation:")
            print(f"Valid: {validation.get('valid', False)}")
            print(f"Existing Tables: {validation.get('existing_tables', [])}")
            print(f"Missing Tables: {validation.get('missing_tables', [])}")
            
        elif args.rollback:
            success = await runner.rollback_migration(args.rollback)
            sys.exit(0 if success else 1)
            
        else:
            success = await runner.run_migrations(
                target_migration=args.target,
                dry_run=args.dry_run
            )
            sys.exit(0 if success else 1)
            
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
