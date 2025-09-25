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
