import os
from dotenv import load_dotenv
from typing import List

# Загружаем переменные окружения из .env файла
load_dotenv()


class Config:
    """Конфигурация приложения с поддержкой Bybit (крипта) + YFinance (фьючерсы)"""
    
    # ========== TELEGRAM BOT ==========
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
    
    # ========== BYBIT API (КРИПТОВАЛЮТЫ) ==========
    BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "YOUR_BYBIT_TEST_API_KEY")
    BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "YOUR_BYBIT_TEST_SECRET")
    BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
    
    # ✅ ИСПРАВЛЕНО: Все 17 пар криптовалют (в алфавитном порядке)
    BYBIT_SYMBOLS = os.getenv(
        "BYBIT_SYMBOLS", 
        "ADAUSDT,APTUSDT,ATOMUSDT,AVAXUSDT,BNBUSDT,BTCUSDT,DOGEUSDT,DOTUSDT,ETHUSDT,LINKUSDT,LTCUSDT,NEARUSDT,SOLUSDT,SUIUSDT,UNIUSDT,XLMUSDT,XRPUSDT"
    ).split(",")
    SYMBOL = BYBIT_SYMBOLS[0] if BYBIT_SYMBOLS else "BTCUSDT"
    CATEGORY = "linear"
    
    # 🆕 Включение/выключение Bybit WebSocket
    BYBIT_WEBSOCKET_ENABLED = os.getenv("BYBIT_WEBSOCKET_ENABLED", "true").lower() == "true"
    
    # 🆕 Включение/выключение автоматической синхронизации свечей
    CANDLE_SYNC_ENABLED = os.getenv("CANDLE_SYNC_ENABLED", "true").lower() == "true"
    
    # ========== 🆕 YFINANCE (ФЬЮЧЕРСЫ CME) ==========
    
    # ⚠️ ВАЖНО: Символы БЕЗ суффикса =F!
    # SimpleFuturesSync сам добавит =F при запросах к YFinance API
    # Но в БД они хранятся БЕЗ =F для единообразия
    YFINANCE_SYMBOLS_STR = os.getenv(
        "YFINANCE_SYMBOLS", 
        "MCL,MGC,MES,MNQ"  # ✅ БЕЗ =F!
    )
    YFINANCE_SYMBOLS = [s.strip().replace("=F", "") for s in YFINANCE_SYMBOLS_STR.split(",")]  # ✅ Убираем =F если есть
    
    # Включение/выключение YFinance WebSocket
    YFINANCE_WEBSOCKET_ENABLED = os.getenv("YFINANCE_WEBSOCKET_ENABLED", "false").lower() == "true"
    
    # Verbose логирование yfinance (для отладки)
    YFINANCE_VERBOSE = os.getenv("YFINANCE_VERBOSE", "false").lower() == "true"
    
    # Таймауты для YFinance WebSocket
    YFINANCE_WS_TIMEOUT = int(os.getenv("YFINANCE_WS_TIMEOUT", "60"))
    YFINANCE_RECONNECT_DELAY = int(os.getenv("YFINANCE_RECONNECT_DELAY", "10"))
    
    # ========== OPENAI API ==========
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # ========== DATABASE SETTINGS ==========
    
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "trading_bot")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    
    DB_MIN_POOL_SIZE = int(os.getenv("DB_MIN_POOL_SIZE", "5"))
    DB_MAX_POOL_SIZE = int(os.getenv("DB_MAX_POOL_SIZE", "20"))
    DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    
    DB_QUERY_TIMEOUT = int(os.getenv("DB_QUERY_TIMEOUT", "30"))
    DB_CONNECTION_TIMEOUT = int(os.getenv("DB_CONNECTION_TIMEOUT", "10"))
    
    DB_SSL_MODE = os.getenv("DB_SSL_MODE", "prefer")
    DB_SSL_CERT = os.getenv("DB_SSL_CERT")
    DB_SSL_KEY = os.getenv("DB_SSL_KEY")
    DB_SSL_CA = os.getenv("DB_SSL_CA")
    
    DB_ENABLE_QUERY_LOGGING = os.getenv("DB_ENABLE_QUERY_LOGGING", "false").lower() == "true"
    DB_SLOW_QUERY_THRESHOLD = float(os.getenv("DB_SLOW_QUERY_THRESHOLD", "1.0"))
    
    DB_AUTO_MIGRATE = os.getenv("DB_AUTO_MIGRATE", "true").lower() == "true"
    DB_MIGRATIONS_TABLE = os.getenv("DB_MIGRATIONS_TABLE", "database_migrations")
    
    # ========== HISTORICAL DATA LOADER SETTINGS ==========
    
    LOADER_MAX_CONCURRENT_REQUESTS = int(os.getenv("LOADER_MAX_CONCURRENT_REQUESTS", "5"))
    LOADER_REQUESTS_PER_SECOND = float(os.getenv("LOADER_REQUESTS_PER_SECOND", "10.0"))
    LOADER_BATCH_SIZE = int(os.getenv("LOADER_BATCH_SIZE", "1000"))
    LOADER_MAX_RETRIES = int(os.getenv("LOADER_MAX_RETRIES", "3"))
    
    DATA_RETENTION_1M = int(os.getenv("DATA_RETENTION_1M", "30"))
    DATA_RETENTION_5M = int(os.getenv("DATA_RETENTION_5M", "90"))
    DATA_RETENTION_1H = int(os.getenv("DATA_RETENTION_1H", "365"))
    DATA_RETENTION_1D = int(os.getenv("DATA_RETENTION_1D", "1825"))
    
    DEFAULT_INTERVALS = os.getenv("DEFAULT_INTERVALS", "1m,5m,15m,1h,4h,1d").split(",")
    
    YFINANCE_DEFAULT_INTERVALS = os.getenv("YFINANCE_DEFAULT_INTERVALS", "1m,5m,15m,1h,1d").split(",")
    
    # ========== RENDER DEPLOYMENT SETTINGS ==========
    
    PORT = int(os.getenv("PORT", "8080"))
    
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = os.getenv("DEBUG", "true" if ENVIRONMENT == "development" else "false").lower() == "true"
    
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
    if RENDER_EXTERNAL_URL:
        BASE_WEBHOOK_URL = RENDER_EXTERNAL_URL
    else:
        BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL", "https://bybitmybot.onrender.com")
    
    # ========== LOGGING SETTINGS ==========
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    
    if ENVIRONMENT == "development":
        DB_ENABLE_QUERY_LOGGING = True
    
    # ========== MARKET DATA MANAGER SETTINGS ==========
    
    WEBSOCKET_RECONNECT_ENABLED = os.getenv("WEBSOCKET_RECONNECT_ENABLED", "true").lower() == "true"
    WEBSOCKET_MAX_RECONNECT_ATTEMPTS = int(os.getenv("WEBSOCKET_MAX_RECONNECT_ATTEMPTS", "10"))
    WEBSOCKET_RECONNECT_DELAY = int(os.getenv("WEBSOCKET_RECONNECT_DELAY", "5"))
    
    REST_API_CACHE_MINUTES = int(os.getenv("REST_API_CACHE_MINUTES", "1"))
    REST_API_ENABLED = os.getenv("REST_API_ENABLED", "true").lower() == "true"
    
    # ========== HELPER METHODS ==========
    
    @classmethod
    def get_database_url(cls) -> str:
        """Получить URL подключения к БД"""
        if cls.DATABASE_URL:
            return cls.DATABASE_URL
        
        password_part = f":{cls.DB_PASSWORD}" if cls.DB_PASSWORD else ""
        return f"postgresql://{cls.DB_USER}{password_part}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
    
    @classmethod
    def is_production(cls) -> bool:
        """Проверка production окружения"""
        return cls.ENVIRONMENT.lower() == "production"
    
    @classmethod
    def is_development(cls) -> bool:
        """Проверка development окружения"""
        return cls.ENVIRONMENT.lower() == "development"
    
    @classmethod
    def get_ssl_mode(cls) -> str:
        """Получить SSL режим"""
        if cls.is_production():
            return "require"
        return cls.DB_SSL_MODE
    
    @classmethod
    def get_pool_size(cls) -> tuple:
        """Получить размеры пула соединений"""
        if cls.is_production():
            return (cls.DB_MIN_POOL_SIZE * 2, cls.DB_MAX_POOL_SIZE * 2)
        return (cls.DB_MIN_POOL_SIZE, cls.DB_MAX_POOL_SIZE)
    
    @classmethod
    def should_auto_migrate(cls) -> bool:
        """Решение о автоматических миграциях"""
        if cls.is_production():
            return False
        return cls.DB_AUTO_MIGRATE
    
    @classmethod
    def get_bybit_symbols(cls) -> List[str]:
        """✅ Получить список всех 17 крипто символов Bybit"""
        return [s.strip().upper() for s in cls.BYBIT_SYMBOLS if s.strip()]
    
    @classmethod
    def get_yfinance_symbols(cls) -> List[str]:
        """
        🆕 Получить список фьючерсов YFinance
        
        ⚠️ ВАЖНО: Возвращает символы БЕЗ суффикса =F
        Это нужно для единообразного хранения в БД
        """
        # Убираем =F если есть и нормализуем
        symbols = []
        for s in cls.YFINANCE_SYMBOLS:
            symbol = s.strip().upper().replace("=F", "")
            if symbol:
                symbols.append(symbol)
        return symbols
    
    @classmethod
    def get_yfinance_symbols_for_api(cls) -> List[str]:
        """
        🆕 Получить символы для запросов к YFinance API
        
        YFinance требует суффикс =F для фьючерсов
        """
        return [f"{s}=F" for s in cls.get_yfinance_symbols()]
    
    @classmethod
    def get_all_symbols(cls) -> dict:
        """🆕 Получить все символы (крипто + фьючерсы)"""
        return {
            "crypto": cls.get_bybit_symbols(),
            "futures": cls.get_yfinance_symbols()
        }
    
    @classmethod
    def validate_yfinance_symbols(cls) -> bool:
        """🆕 Валидация символов YFinance"""
        valid_prefixes = ["MCL", "MGC", "MES", "MNQ", "ES", "NQ", "CL", "GC"]
        
        for symbol in cls.get_yfinance_symbols():
            base_symbol = symbol.replace("=F", "")
            
            if not any(base_symbol.startswith(prefix) for prefix in valid_prefixes):
                return False
        
        return True
    
    @classmethod
    def get_config_summary(cls) -> dict:
        """Получить сводку конфигурации (без секретов)"""
        return {
            "environment": cls.ENVIRONMENT,
            "debug": cls.DEBUG,
            "port": cls.PORT,
            "webhook_url": cls.BASE_WEBHOOK_URL,
            
            "database_configured": bool(cls.DATABASE_URL or cls.DB_HOST),
            "ssl_mode": cls.get_ssl_mode(),
            "pool_size": f"{cls.get_pool_size()[0]}-{cls.get_pool_size()[1]}",
            "auto_migrate": cls.should_auto_migrate(),
            
            "bybit_testnet": cls.BYBIT_TESTNET,
            "bybit_symbols": cls.get_bybit_symbols(),
            "bybit_symbols_count": len(cls.get_bybit_symbols()),
            "bybit_websocket_enabled": cls.BYBIT_WEBSOCKET_ENABLED,
            "candle_sync_enabled": cls.CANDLE_SYNC_ENABLED,
            
            "yfinance_symbols": cls.get_yfinance_symbols(),
            "yfinance_symbols_for_api": cls.get_yfinance_symbols_for_api(),
            "yfinance_symbols_count": len(cls.get_yfinance_symbols()),
            "yfinance_websocket_enabled": cls.YFINANCE_WEBSOCKET_ENABLED,
            "yfinance_symbols_valid": cls.validate_yfinance_symbols(),
            
            "default_intervals": cls.DEFAULT_INTERVALS,
            "yfinance_intervals": cls.YFINANCE_DEFAULT_INTERVALS,
            "loader_max_concurrent": cls.LOADER_MAX_CONCURRENT_REQUESTS,
            
            "websocket_reconnect": cls.WEBSOCKET_RECONNECT_ENABLED,
            "websocket_max_reconnects": cls.WEBSOCKET_MAX_RECONNECT_ATTEMPTS,
            
            "rest_api_enabled": cls.REST_API_ENABLED,
            "rest_cache_minutes": cls.REST_API_CACHE_MINUTES
        }
    
    @classmethod
    def validate_config(cls) -> List[str]:
        """🆕 Валидация конфигурации"""
        issues = []
        
        if not cls.TELEGRAM_BOT_TOKEN or cls.TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
            issues.append("❌ TELEGRAM_BOT_TOKEN not configured")
        
        if not cls.get_database_url() or "localhost" in cls.get_database_url():
            if cls.is_production():
                issues.append("❌ Production database not configured")
            else:
                issues.append("⚠️ Using local database")
        
        if not cls.OPENAI_API_KEY or cls.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY":
            issues.append("⚠️ OpenAI API key not configured")
        
        if not cls.BYBIT_SYMBOLS or not cls.get_bybit_symbols():
            issues.append("⚠️ No Bybit symbols configured")
        elif len(cls.get_bybit_symbols()) != 17:
            issues.append(f"⚠️ Expected 17 Bybit symbols, found {len(cls.get_bybit_symbols())}")
        
        if cls.BYBIT_WEBSOCKET_ENABLED:
            if not cls.BYBIT_API_KEY or cls.BYBIT_API_KEY == "YOUR_BYBIT_TEST_API_KEY":
                issues.append("⚠️ Bybit API key not configured but WebSocket enabled")
        
        if cls.YFINANCE_WEBSOCKET_ENABLED:
            if not cls.YFINANCE_SYMBOLS or not cls.get_yfinance_symbols():
                issues.append("❌ YFinance WebSocket enabled but no symbols configured")
            elif not cls.validate_yfinance_symbols():
                issues.append("❌ Invalid YFinance symbols detected")
        
        if cls.WEBSOCKET_RECONNECT_ENABLED:
            if cls.WEBSOCKET_MAX_RECONNECT_ATTEMPTS < 1:
                issues.append("⚠️ WEBSOCKET_MAX_RECONNECT_ATTEMPTS should be >= 1")
        
        return issues
    
    @classmethod
    def print_config(cls, verbose: bool = False):
        """🆕 Красиво печатает конфигурацию"""
        print("=" * 80)
        print("🔧 TRADING BOT CONFIGURATION")
        print("=" * 80)
        
        config_summary = cls.get_config_summary()
        
        print("\n📊 ENVIRONMENT:")
        print(f"  • Mode: {config_summary['environment']}")
        print(f"  • Debug: {config_summary['debug']}")
        print(f"  • Port: {config_summary['port']}")
        
        print("\n💾 DATABASE:")
        print(f"  • Configured: {config_summary['database_configured']}")
        print(f"  • SSL Mode: {config_summary['ssl_mode']}")
        print(f"  • Pool Size: {config_summary['pool_size']}")
        print(f"  • Auto Migrate: {config_summary['auto_migrate']}")
        
        print("\n₿ BYBIT CRYPTO (17 PAIRS):")
        print(f"  • Testnet: {config_summary['bybit_testnet']}")
        print(f"  • WebSocket: {'✅' if config_summary['bybit_websocket_enabled'] else '❌'}")
        print(f"  • Candle Sync: {'✅' if config_summary['candle_sync_enabled'] else '❌'}")
        print(f"  • Total Pairs: {config_summary['bybit_symbols_count']}")
        
        symbols = config_summary['bybit_symbols']
        print(f"  • Symbols:")
        for i in range(0, len(symbols), 5):
            batch = symbols[i:i+5]
            print(f"    {', '.join(batch)}")
        
        print("\n📈 YFINANCE FUTURES:")
        print(f"  • WebSocket: {'✅' if config_summary['yfinance_websocket_enabled'] else '❌'}")
        print(f"  • Total Pairs: {config_summary['yfinance_symbols_count']}")
        print(f"  • DB Symbols: {', '.join(config_summary['yfinance_symbols'])}")
        print(f"  • API Symbols: {', '.join(config_summary['yfinance_symbols_for_api'])}")
        print(f"  • Valid: {'✅' if config_summary['yfinance_symbols_valid'] else '❌'}")
        
        if verbose:
            print("\n📥 DATA LOADER:")
            print(f"  • Bybit Intervals: {', '.join(config_summary['default_intervals'])}")
            print(f"  • YFinance Intervals: {', '.join(config_summary['yfinance_intervals'])}")
            print(f"  • Max Concurrent: {config_summary['loader_max_concurrent']}")
            print(f"  • Candle Sync: {'✅' if config_summary['candle_sync_enabled'] else '❌'}")
        
        if verbose:
            print("\n🔌 WEBSOCKET:")
            print(f"  • Reconnect: {'✅' if config_summary['websocket_reconnect'] else '❌'}")
            print(f"  • Max Attempts: {config_summary['websocket_max_reconnects']}")
        
        issues = cls.validate_config()
        if issues:
            print("\n🚨 CONFIGURATION ISSUES:")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("\n✅ Configuration looks good!")
        
        print("=" * 80)


if __name__ == "__main__":
    Config.print_config(verbose=True)
