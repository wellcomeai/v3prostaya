import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from bybit_client import BybitClient
from openai_integration import OpenAIAnalyzer
from config import Config

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram бот для анализа рынка"""
    
    def __init__(self, token: str):
        self.token = token
        self.bybit_client = BybitClient()
        self.openai_analyzer = OpenAIAnalyzer()
        self.application = None
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        keyboard = [
            [InlineKeyboardButton("📊 Узнать рынок", callback_data="market_analysis")],
            [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = """
🤖 *Bybit Trading Bot*

Привет! Я помогу тебе анализировать рынок криптовалют.

Нажми кнопку ниже, чтобы получить анализ рынка BTC/USDT от ИИ агента.
        """
        
        await update.message.reply_text(
            welcome_text, 
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий кнопок"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "market_analysis":
            await self.handle_market_analysis(query)
        elif query.data == "about":
            await self.handle_about(query)
    
    async def handle_market_analysis(self, query):
        """Обработка запроса анализа рынка"""
        try:
            # Показываем индикатор загрузки
            await query.edit_message_text("🔄 Получаю данные с Bybit...")
            
            # Получаем данные рынка
            market_data = await self.bybit_client.get_market_data()
            
            await query.edit_message_text("🤖 Анализирую данные с помощью ИИ...")
            
            # Получаем анализ от OpenAI
            ai_analysis = await self.openai_analyzer.analyze_market(market_data)
            
            # Формируем ответное сообщение
            response_text = f"""
📊 *Анализ рынка BTC/USDT*

{ai_analysis}

---
_Данные предоставлены Bybit API_
_Анализ сгенерирован ИИ агентом_
            """
            
            # Добавляем кнопку для нового анализа
            keyboard = [[InlineKeyboardButton("🔄 Обновить анализ", callback_data="market_analysis")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                response_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при анализе рынка: {e}")
            error_text = """
❌ *Ошибка получения данных*

Произошла ошибка при получении данных с Bybit или анализе от ИИ.
Попробуйте позже.
            """
            
            keyboard = [[InlineKeyboardButton("🔄 Попробовать снова", callback_data="market_analysis")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                error_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    
    async def handle_about(self, query):
        """Обработка запроса информации о боте"""
        about_text = """
ℹ️ *О боте*

Этот бот использует:
• 📈 Bybit API для получения рыночных данных
• 🤖 OpenAI GPT для анализа данных
• 📱 Telegram Bot API для интерфейса

*Функции:*
• Анализ рынка BTC/USDT
• ИИ-прогнозы на основе данных
• Актуальная рыночная информация

_Версия: MVP 1.0_
        """
        
        keyboard = [[InlineKeyboardButton("📊 Узнать рынок", callback_data="market_analysis")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            about_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def run(self):
        """Запуск бота"""
        try:
            # Создаем приложение
            self.application = Application.builder().token(self.token).build()
            
            # Регистрируем обработчики
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CallbackQueryHandler(self.button_callback))
            
            # Запускаем бота
            logger.info("🤖 Telegram бот запущен и готов к работе!")
            await self.application.run_polling()
            
        except Exception as e:
            logger.error(f"Ошибка при запуске Telegram бота: {e}")
            raise
