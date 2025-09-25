import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.enums import ParseMode
from bybit_client import BybitClient
from openai_integration import OpenAIAnalyzer

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram бот для анализа рынка на aiogram"""
    
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.router = Router()
        
        # Инициализируем клиенты
        self.bybit_client = BybitClient()
        self.openai_analyzer = OpenAIAnalyzer()
        
        # Регистрируем обработчики
        self._register_handlers()
        
        # Подключаем роутер к диспетчеру
        self.dp.include_router(self.router)
    
    def _register_handlers(self):
        """Регистрация всех обработчиков"""
        # Команды
        self.router.message.register(self.start_command, Command("start"))
        
        # Callback query обработчики
        self.router.callback_query.register(
            self.handle_market_analysis, 
            F.data == "market_analysis"
        )
        self.router.callback_query.register(
            self.handle_about, 
            F.data == "about"
        )
    
    async def start_command(self, message: Message):
        """Обработчик команды /start"""
        try:
            # Создаем клавиатуру
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(
                    text="📊 Узнать рынок", 
                    callback_data="market_analysis"
                )
            )
            builder.add(
                InlineKeyboardButton(
                    text="ℹ️ О боте", 
                    callback_data="about"
                )
            )
            builder.adjust(1)  # Располагаем кнопки в один столбец
            
            welcome_text = """🤖 *Bybit Trading Bot*

Привет! Я помогу тебе анализировать рынок криптовалют.

Нажми кнопку ниже, чтобы получить анализ рынка BTC/USDT от ИИ агента."""
            
            await message.answer(
                welcome_text,
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Ошибка в start_command: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте позже.")
    
    async def handle_market_analysis(self, callback: CallbackQuery):
        """Обработка запроса анализа рынка"""
        try:
            # Подтверждаем получение callback
            await callback.answer()
            
            # Показываем индикатор загрузки
            await callback.message.edit_text("🔄 Получаю данные с Bybit...")
            
            # Получаем данные рынка
            market_data = await self.bybit_client.get_market_data()
            
            await callback.message.edit_text("🤖 Анализирую данные с помощью ИИ...")
            
            # Получаем анализ от OpenAI
            ai_analysis = await self.openai_analyzer.analyze_market(market_data)
            
            # Формируем ответное сообщение
            response_text = f"""📊 *Анализ рынка BTC/USDT*

{ai_analysis}

---
_Данные предоставлены Bybit API_
_Анализ сгенерирован ИИ агентом_"""
            
            # Создаем кнопку для нового анализа
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(
                    text="🔄 Обновить анализ", 
                    callback_data="market_analysis"
                )
            )
            builder.add(
                InlineKeyboardButton(
                    text="◀️ Главное меню", 
                    callback_data="back_to_menu"
                )
            )
            builder.adjust(1)
            
            await callback.message.edit_text(
                response_text,
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Ошибка при анализе рынка: {e}")
            
            error_text = """❌ *Ошибка получения данных*

Произошла ошибка при получении данных с Bybit или анализе от ИИ.
Попробуйте позже."""
            
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(
                    text="🔄 Попробовать снова", 
                    callback_data="market_analysis"
                )
            )
            builder.add(
                InlineKeyboardButton(
                    text="◀️ Главное меню", 
                    callback_data="back_to_menu"
                )
            )
            builder.adjust(1)
            
            await callback.message.edit_text(
                error_text,
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def handle_about(self, callback: CallbackQuery):
        """Обработка запроса информации о боте"""
        try:
            await callback.answer()
            
            about_text = """ℹ️ *О боте*

Этот бот использует:
• 📈 Bybit API для получения рыночных данных
• 🤖 OpenAI GPT для анализа данных
• 📱 Telegram Bot API для интерфейса

*Функции:*
• Анализ рынка BTC/USDT
• ИИ-прогнозы на основе данных
• Актуальная рыночная информация

_Версия: MVP 1.0_
_Работает на aiogram 3.x_"""
            
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(
                    text="📊 Узнать рынок", 
                    callback_data="market_analysis"
                )
            )
            builder.add(
                InlineKeyboardButton(
                    text="◀️ Главное меню", 
                    callback_data="back_to_menu"
                )
            )
            builder.adjust(1)
            
            await callback.message.edit_text(
                about_text,
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Ошибка в handle_about: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_back_to_menu(self, callback: CallbackQuery):
        """Возврат в главное меню"""
        try:
            await callback.answer()
            
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(
                    text="📊 Узнать рынок", 
                    callback_data="market_analysis"
                )
            )
            builder.add(
                InlineKeyboardButton(
                    text="ℹ️ О боте", 
                    callback_data="about"
                )
            )
            builder.adjust(1)
            
            welcome_text = """🤖 *Bybit Trading Bot*

Привет! Я помогу тебе анализировать рынок криптовалют.

Нажми кнопку ниже, чтобы получить анализ рынка BTC/USDT от ИИ агента."""
            
            await callback.message.edit_text(
                welcome_text,
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Ошибка в handle_back_to_menu: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def run(self):
        """Запуск бота"""
        try:
            # Регистрируем дополнительный обработчик для возврата в меню
            self.router.callback_query.register(
                self.handle_back_to_menu,
                F.data == "back_to_menu"
            )
            
            logger.info("🤖 Telegram бот (aiogram) запущен и готов к работе!")
            
            # Запускаем polling
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"Ошибка при запуске Telegram бота: {e}")
            raise
    
    async def close(self):
        """Корректное закрытие бота"""
        try:
            await self.bot.session.close()
            logger.info("🔴 Бот корректно остановлен")
        except Exception as e:
            logger.error(f"Ошибка при закрытии бота: {e}")
