import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

class Config:
    """Конфигурация приложения"""
    
    # Telegram Bot Token
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
    
    # Bybit API (тестовые ключи)
    BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "YOUR_BYBIT_TEST_API_KEY")
    BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "YOUR_BYBIT_TEST_SECRET")
    BYBIT_TESTNET = True  # Используем тестнет
    
    # OpenAI API
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
    
    # Настройки торговой пары
    SYMBOL = "BTCUSDT"
    CATEGORY = "linear"  # Деривативы
    
    # Настройки OpenAI
    OPENAI_MODEL = "gpt-4o-mini"  # Более дешевая модель для MVP
    
    # ========== DATABASE SETTINGS ==========
    
    # PostgreSQL Database URL (для Render и других cloud платформ)
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    # Индивидуальные настройки БД (для локальной разработки)
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "trading_bot")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    
    # Connection Pool настройки
    DB_MIN_POOL_SIZE = int(os.getenv("DB_MIN_POOL_SIZE", "5"))
    DB_MAX_POOL_SIZE = int(os.getenv("DB_MAX_POOL_SIZE", "20"))
    DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    
    # Database query настройки  
    DB_QUERY_TIMEOUT = int(os.getenv("DB_QUERY_TIMEOUT", "30"))
    DB_CONNECTION_TIMEOUT = int(os.getenv("DB_CONNECTION_TIMEOUT", "10"))
    
    # SSL настройки (важно для production)
    DB_SSL_MODE = os.getenv("DB_SSL_MODE", "prefer")  # require для production
    DB_SSL_CERT = os.getenv("DB_SSL_CERT")
    DB_SSL_KEY = os.getenv("DB_SSL_KEY")
    DB_SSL_CA = os.getenv("DB_SSL_CA")
    
    # Database maintenance
    DB_ENABLE_QUERY_LOGGING = os.getenv("DB_ENABLE_QUERY_LOGGING", "false").lower() == "true"
    DB_SLOW_QUERY_THRESHOLD = float(os.getenv("DB_SLOW_QUERY_THRESHOLD", "1.0"))
    
    # Migration настройки
    DB_AUTO_MIGRATE = os.getenv("DB_AUTO_MIGRATE", "true").lower() == "true"
    DB_MIGRATIONS_TABLE = os.getenv("DB_MIGRATIONS_TABLE", "database_migrations")
    
    # ========== HISTORICAL DATA LOADER SETTINGS ==========
    
    # Loader performance настройки
    LOADER_MAX_CONCURRENT_REQUESTS = int(os.getenv("LOADER_MAX_CONCURRENT_REQUESTS", "5"))
    LOADER_REQUESTS_PER_SECOND = float(os.getenv("LOADER_REQUESTS_PER_SECOND", "10.0"))
    LOADER_BATCH_SIZE = int(os.getenv("LOADER_BATCH_SIZE", "1000"))
    LOADER_MAX_RETRIES = int(os.getenv("LOADER_MAX_RETRIES", "3"))
    
    # Data retention настройки (в днях)
    DATA_RETENTION_1M = int(os.getenv("DATA_RETENTION_1M", "30"))      # 1 месяц для 1m данных
    DATA_RETENTION_5M = int(os.getenv("DATA_RETENTION_5M", "90"))      # 3 месяца для 5m
    DATA_RETENTION_1H = int(os.getenv("DATA_RETENTION_1H", "365"))     # 1 год для 1h
    DATA_RETENTION_1D = int(os.getenv("DATA_RETENTION_1D", "1825"))    # 5 лет для дневных
    
    # Default intervals для автоматической загрузки
    DEFAULT_INTERVALS = os.getenv("DEFAULT_INTERVALS", "1m,5m,15m,1h,4h,1d").split(",")
    
    # ========== RENDER DEPLOYMENT SETTINGS ==========
    
    # Render автоматически устанавливает PORT
    PORT = int(os.getenv("PORT", "8080"))
    
    # Environment detection
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # production, staging, development
    DEBUG = os.getenv("DEBUG", "true" if ENVIRONMENT == "development" else "false").lower() == "true"
    
    # Render webhook URL (автоматически определяется)
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
    if RENDER_EXTERNAL_URL:
        BASE_WEBHOOK_URL = RENDER_EXTERNAL_URL
    else:
        BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL", "https://bybitmybot.onrender.com")
    
    # ========== LOGGING SETTINGS ==========
    
    # Log level
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Enable database query logging in development
    if ENVIRONMENT == "development":
        DB_ENABLE_QUERY_LOGGING = True
    
    # ========== HELPER METHODS ==========
    
    @classmethod
    def get_database_url(cls) -> str:
        """
        Получить URL подключения к БД
        Приоритет: DATABASE_URL -> составить из компонентов
        """
        if cls.DATABASE_URL:
            return cls.DATABASE_URL
        
        # Составляем URL из компонентов
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
        """Получить SSL режим в зависимости от окружения"""
        if cls.is_production():
            return "require"  # Обязательный SSL в production
        return cls.DB_SSL_MODE
    
    @classmethod
    def get_pool_size(cls) -> tuple:
        """Получить размеры пула соединений"""
        if cls.is_production():
            # В production используем больше соединений
            return (cls.DB_MIN_POOL_SIZE * 2, cls.DB_MAX_POOL_SIZE * 2)
        return (cls.DB_MIN_POOL_SIZE, cls.DB_MAX_POOL_SIZE)
    
    @classmethod
    def should_auto_migrate(cls) -> bool:
        """Решение о автоматических миграциях"""
        if cls.is_production():
            # В production миграции должны быть явными
            return False
        return cls.DB_AUTO_MIGRATE
    
    @classmethod
    def get_config_summary(cls) -> dict:
        """Получить сводку конфигурации (без секретов)"""
        return {
            "environment": cls.ENVIRONMENT,
            "debug": cls.DEBUG,
            "database_configured": bool(cls.DATABASE_URL or cls.DB_HOST),
            "ssl_mode": cls.get_ssl_mode(),
            "pool_size": f"{cls.get_pool_size()[0]}-{cls.get_pool_size()[1]}",
            "auto_migrate": cls.should_auto_migrate(),
            "bybit_testnet": cls.BYBIT_TESTNET,
            "default_intervals": cls.DEFAULT_INTERVALS,
            "loader_max_concurrent": cls.LOADER_MAX_CONCURRENT_REQUESTS,
            "port": cls.PORT,
            "webhook_url": cls.BASE_WEBHOOK_URL
        }

# Validation при импорте
if __name__ == "__main__":
    print("🔧 Trading Bot Configuration")
    print("=" * 40)
    
    config_summary = Config.get_config_summary()
    for key, value in config_summary.items():
        print(f"{key}: {value}")
    
    # Проверки
    issues = []
    
    if not Config.TELEGRAM_BOT_TOKEN or Config.TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        issues.append("❌ TELEGRAM_BOT_TOKEN not configured")
    
    if not Config.get_database_url() or "localhost" in Config.get_database_url():
        if Config.is_production():
            issues.append("❌ Production database not configured")
        else:
            issues.append("⚠️ Using local database")
    
    if not Config.OPENAI_API_KEY or Config.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY":
        issues.append("⚠️ OpenAI API key not configured")
    
    if issues:
        print("\n🚨 Configuration Issues:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✅ Configuration looks good!")
