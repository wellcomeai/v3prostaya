"""
Database configuration management

Handles PostgreSQL connection settings, environment variables,
and database-specific configurations for the trading bot.
"""

import os
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Database configuration settings"""
    
    # Connection settings
    host: str = "localhost"
    port: int = 5432
    database: str = "trading_bot"
    username: str = "postgres"
    password: str = ""
    
    # Connection pool settings
    min_pool_size: int = 5
    max_pool_size: int = 20
    pool_timeout: int = 30
    
    # Query timeouts (seconds)
    query_timeout: int = 30
    connection_timeout: int = 10
    
    # SSL settings
    ssl_mode: str = "prefer"  # disable, allow, prefer, require, verify-ca, verify-full
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    ssl_ca: Optional[str] = None
    
    # Performance settings
    statement_cache_size: int = 0  # 0 = disabled for production safety
    prepared_statement_cache_size: int = 0
    
    # Migration settings
    migrations_table: str = "database_migrations"
    auto_migrate: bool = True
    
    # Maintenance settings
    enable_query_logging: bool = False
    slow_query_threshold: float = 1.0  # seconds
    
    # Time zone settings
    timezone: str = "UTC"
    
    @classmethod
    def from_environment(cls) -> 'DatabaseConfig':
        """
        Create configuration from environment variables
        
        Environment variables:
        - DATABASE_URL: Full PostgreSQL URL (takes precedence)
        - DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD: Individual components
        - DB_MIN_POOL_SIZE, DB_MAX_POOL_SIZE: Connection pool settings
        - DB_SSL_MODE: SSL connection mode
        
        Returns:
            DatabaseConfig: Configuration instance
        """
        config = cls()
        
        # Try to parse DATABASE_URL first (common for cloud deployments)
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            config._parse_database_url(database_url)
        else:
            # Use individual environment variables
            config.host = os.getenv("DB_HOST", config.host)
            config.port = int(os.getenv("DB_PORT", str(config.port)))
            config.database = os.getenv("DB_NAME", config.database)
            config.username = os.getenv("DB_USER", config.username)
            config.password = os.getenv("DB_PASSWORD", config.password)
        
        # Connection pool settings
        config.min_pool_size = int(os.getenv("DB_MIN_POOL_SIZE", str(config.min_pool_size)))
        config.max_pool_size = int(os.getenv("DB_MAX_POOL_SIZE", str(config.max_pool_size)))
        config.pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", str(config.pool_timeout)))
        
        # Timeout settings
        config.query_timeout = int(os.getenv("DB_QUERY_TIMEOUT", str(config.query_timeout)))
        config.connection_timeout = int(os.getenv("DB_CONNECTION_TIMEOUT", str(config.connection_timeout)))
        
        # SSL settings
        config.ssl_mode = os.getenv("DB_SSL_MODE", config.ssl_mode)
        config.ssl_cert = os.getenv("DB_SSL_CERT")
        config.ssl_key = os.getenv("DB_SSL_KEY")
        config.ssl_ca = os.getenv("DB_SSL_CA")
        
        # Performance settings
        config.enable_query_logging = os.getenv("DB_ENABLE_QUERY_LOGGING", "false").lower() == "true"
        config.slow_query_threshold = float(os.getenv("DB_SLOW_QUERY_THRESHOLD", str(config.slow_query_threshold)))
        
        # Migration settings
        config.auto_migrate = os.getenv("DB_AUTO_MIGRATE", "true").lower() == "true"
        
        logger.info(f"Database config loaded: {config.get_host()}:{config.port}/{config.database}")
        
        return config
    
    def _parse_database_url(self, url: str):
        """Parse DATABASE_URL and extract connection parameters"""
        try:
            parsed = urlparse(url)
            
            self.host = parsed.hostname or self.host
            self.port = parsed.port or self.port
            self.database = parsed.path.lstrip('/') or self.database
            self.username = parsed.username or self.username
            self.password = parsed.password or self.password
            
            # Handle SSL parameters from query string
            if parsed.query:
                params = dict(param.split('=') for param in parsed.query.split('&') if '=' in param)
                if 'sslmode' in params:
                    self.ssl_mode = params['sslmode']
                if 'sslcert' in params:
                    self.ssl_cert = params['sslcert']
                if 'sslkey' in params:
                    self.ssl_key = params['sslkey']
                if 'sslrootcert' in params:
                    self.ssl_ca = params['sslrootcert']
                    
        except Exception as e:
            logger.error(f"Failed to parse DATABASE_URL: {e}")
            raise ValueError(f"Invalid DATABASE_URL format: {e}")
    
    def get_connection_string(self) -> str:
        """
        Generate PostgreSQL connection string
        
        Returns:
            str: asyncpg-compatible connection string
        """
        # Build base connection string
        conn_str = f"postgresql://{self.username}"
        
        if self.password:
            conn_str += f":{self.password}"
        
        conn_str += f"@{self.host}:{self.port}/{self.database}"
        
        # Add SSL and other parameters
        params = []
        
        if self.ssl_mode != "prefer":
            params.append(f"sslmode={self.ssl_mode}")
            
        if self.ssl_cert:
            params.append(f"sslcert={self.ssl_cert}")
            
        if self.ssl_key:
            params.append(f"sslkey={self.ssl_key}")
            
        if self.ssl_ca:
            params.append(f"sslrootcert={self.ssl_ca}")
        
        # Add application name for monitoring
        params.append("application_name=trading_bot")
        
        if params:
            conn_str += "?" + "&".join(params)
        
        return conn_str
    
    def get_pool_kwargs(self) -> Dict[str, Any]:
        """
        Get connection pool configuration for asyncpg
        
        Returns:
            dict: Pool configuration parameters
        """
        return {
            "min_size": self.min_pool_size,
            "max_size": self.max_pool_size,
            "timeout": self.pool_timeout,
            "command_timeout": self.query_timeout,
            "server_settings": {
                "timezone": self.timezone,
                "application_name": "trading_bot",
            }
        }
    
    def get_host(self) -> str:
        """Get database host for logging (without credentials)"""
        return f"{self.host}:{self.port}"
    
    def validate(self) -> bool:
        """
        Validate configuration parameters
        
        Returns:
            bool: True if configuration is valid
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not self.host:
            raise ValueError("Database host is required")
        
        if not self.database:
            raise ValueError("Database name is required")
        
        if not self.username:
            raise ValueError("Database username is required")
        
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Invalid port number: {self.port}")
        
        if self.min_pool_size < 1:
            raise ValueError("Minimum pool size must be at least 1")
        
        if self.max_pool_size < self.min_pool_size:
            raise ValueError("Maximum pool size must be >= minimum pool size")
        
        if self.query_timeout < 1:
            raise ValueError("Query timeout must be at least 1 second")
        
        if self.ssl_mode not in ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]:
            raise ValueError(f"Invalid SSL mode: {self.ssl_mode}")
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary (excluding password)"""
        config_dict = {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
            "min_pool_size": self.min_pool_size,
            "max_pool_size": self.max_pool_size,
            "pool_timeout": self.pool_timeout,
            "query_timeout": self.query_timeout,
            "connection_timeout": self.connection_timeout,
            "ssl_mode": self.ssl_mode,
            "enable_query_logging": self.enable_query_logging,
            "slow_query_threshold": self.slow_query_threshold,
            "auto_migrate": self.auto_migrate,
            "timezone": self.timezone
        }
        
        return config_dict
    
    def __repr__(self) -> str:
        """String representation without sensitive data"""
        return (f"DatabaseConfig(host='{self.host}', port={self.port}, "
                f"database='{self.database}', username='{self.username}', "
                f"pool_size={self.min_pool_size}-{self.max_pool_size})")


# Default configuration instance
default_config = DatabaseConfig()

# Export configuration class
__all__ = ["DatabaseConfig", "default_config"]
