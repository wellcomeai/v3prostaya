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
    """Telegram бот для анализа рынка на aiogram (webhook режим)"""
    
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.router = Router()
        
        # Инициализируем клиенты
        self.bybit_client = BybitClient()
        self.openai_analyzer = OpenAIAnalyzer()
        
        # Регистрируем все обработчики
        self._register_handlers()
        
        # Подключаем роутер к диспетчеру
        self.dp.include_router(self.router)
        
        logger.info("🤖 TelegramBot инициализирован для webhook режима")
    
    def _register_handlers(self):
        """Регистрация всех обработчиков"""
        # Команды
        self.router.message.register(self.start_command, Command("start"))
        self.router.message.register(self.help_command, Command("help"))
        
        # Callback query обработчики
        self.router.callback_query.register(
            self.handle_market_analysis, 
            F.data == "market_analysis"
        )
        self.router.callback_query.register(
            self.handle_about, 
            F.data == "about"
        )
        self.router.callback_query.register(
            self.handle_back_to_menu,
            F.data == "back_to_menu"
        )
        
        # Обработчик для неизвестных callback данных
        self.router.callback_query.register(self.handle_unknown_callback)
        
        # Обработчик для обычных текстовых сообщений
        self.router.message.register(self.handle_text_message, F.text)
        
        logger.info("✅ Все обработчики зарегистрированы")
    
    async def start_command(self, message: Message):
        """Обработчик команды /start"""
        try:
            user_name = message.from_user.first_name or "друг"
            user_id = message.from_user.id
            
            logger.info(f"👤 Новый пользователь: {user_name} (ID: {user_id})")
            
            # Создаем главное меню
            keyboard = self._create_main_menu()
            
            welcome_text = f"""🤖 *Bybit Trading Bot*

Привет, {user_name}! Я помогу тебе анализировать рынок криптовалют.

📊 *Что я умею:*
• Получать актуальные данные с Bybit
• Анализировать рынок BTC/USDT с помощью ИИ
• Предоставлять статистику за 24 часа

Нажми кнопку ниже, чтобы начать! 👇"""
            
            await message.answer(
                welcome_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в start_command: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте позже.")
    
    async def help_command(self, message: Message):
        """Обработчик команды /help"""
        try:
            help_text = """📖 *Справка по боту*

🔧 *Доступные команды:*
/start - Запуск бота и главное меню
/help - Эта справка

📊 *Функции:*
• 📈 Анализ рынка BTC/USDT
• 🤖 ИИ-прогнозы на основе данных Bybit
• 📊 Статистика волатильности и объемов
• 🕐 Данные за последние 24 часа

⚠️ *Важно:*
Бот предоставляет аналитическую информацию, но не является инвестиционным советом. Торговля криптовалютами связана с высокими рисками.

🔄 Для начала работы используйте /start"""
            
            keyboard = self._create_main_menu()
            
            await message.answer(
                help_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в help_command: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте /start")
    
    async def handle_market_analysis(self, callback: CallbackQuery):
        """Обработка запроса анализа рынка"""
        user_id = callback.from_user.id
        user_name = callback.from_user.first_name or "пользователь"
        
        try:
            # Подтверждаем получение callback
            await callback.answer()
            
            logger.info(f"📊 Запрос анализа от {user_name} (ID: {user_id})")
            
            # Показываем индикатор загрузки
            await callback.message.edit_text(
                "🔄 Получаю свежие данные с Bybit...\n_Это может занять несколько секунд_",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Получаем данные рынка
            market_data = await self.bybit_client.get_market_data()
            
            await callback.message.edit_text(
                "🤖 Анализирую данные с помощью ИИ...\n_Генерирую прогноз_",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Получаем анализ от OpenAI
            ai_analysis = await self.openai_analyzer.analyze_market(market_data)
            
            # Формируем краткую сводку
            quick_stats = self._format_quick_stats(market_data)
            
            # Формируем ответное сообщение
            response_text = f"""📊 *Анализ рынка BTC/USDT*

{quick_stats}

🤖 *ИИ Анализ:*
{ai_analysis}

---
_Данные: Bybit API • Анализ: OpenAI GPT_
_Обновлено: {market_data.get('timestamp', 'неизвестно')[:19]}_"""
            
            # Создаем кнопки для дальнейших действий
            keyboard = self._create_analysis_menu()
            
            await callback.message.edit_text(
                response_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"✅ Анализ предоставлен пользователю {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при анализе рынка для пользователя {user_id}: {e}")
            
            error_text = """❌ *Ошибка получения данных*

К сожалению, произошла ошибка при получении данных с Bybit или анализе от ИИ.

🔧 *Возможные причины:*
• Временные проблемы с Bybit API
• Ошибка OpenAI сервиса
• Проблемы с сетью

Попробуйте позже или обратитесь к администратору."""
            
            keyboard = self._create_error_menu()
            
            await callback.message.edit_text(
                error_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def handle_about(self, callback: CallbackQuery):
        """Обработка запроса информации о боте"""
        try:
            await callback.answer()
            
            about_text = """ℹ️ *О боте*

🤖 *Bybit Trading Bot v2.0*

*Технологии:*
• 📈 Bybit REST API v5 для рыночных данных
• 🤖 OpenAI GPT-4 для анализа и прогнозов
• 🚀 Python aiogram для Telegram интеграции
• ⚡ Асинхронная архитектура для скорости

*Функции:*
• Анализ рынка BTC/USDT в реальном времени
• ИИ-прогнозы на основе текущих данных
• Статистика объемов и волатильности
• Отслеживание трендов за 24 часа

*Режим работы:*
• 🔗 Webhook для мгновенных ответов
• ☁️ Развернуто на Render.com
• 🏥 Health monitoring для стабильности

⚠️ *Дисклеймер:*
Все данные предоставляются исключительно в информационных целях и не являются инвестиционным советом."""
            
            keyboard = self._create_about_menu()
            
            await callback.message.edit_text(
                about_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_about: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_back_to_menu(self, callback: CallbackQuery):
        """Возврат в главное меню"""
        try:
            await callback.answer()
            
            keyboard = self._create_main_menu()
            
            welcome_text = """🤖 *Bybit Trading Bot*

Главное меню. Выберите действие:"""
            
            await callback.message.edit_text(
                welcome_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_back_to_menu: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_unknown_callback(self, callback: CallbackQuery):
        """Обработка неизвестных callback данных"""
        try:
            await callback.answer("❓ Неизвестная команда")
            logger.warning(f"⚠️ Неизвестный callback: {callback.data} от пользователя {callback.from_user.id}")
            
            # Возвращаем в главное меню
            await self.handle_back_to_menu(callback)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_unknown_callback: {e}")
    
    async def handle_text_message(self, message: Message):
        """Обработка обычных текстовых сообщений"""
        try:
            user_text = message.text.lower()
            
            # Простые команды текстом
            if any(word in user_text for word in ['привет', 'старт', 'начать', 'hello', 'hi']):
                await self.start_command(message)
            elif any(word in user_text for word in ['анализ', 'рынок', 'btc', 'биткоин', 'цена']):
                # Создаем inline кнопку для анализа
                builder = InlineKeyboardBuilder()
                builder.add(InlineKeyboardButton(
                    text="📊 Получить анализ",
                    callback_data="market_analysis"
                ))
                
                await message.answer(
                    "📊 Хотите получить анализ рынка BTC/USDT?",
                    reply_markup=builder.as_markup()
                )
            elif any(word in user_text for word in ['помощь', 'справка', 'help']):
                await self.help_command(message)
            else:
                # Для всех остальных сообщений показываем меню
                response_text = """🤖 Я анализирую рынок криптовалют!

Используйте кнопки меню или команды:
/start - главное меню
/help - справка

Или просто напишите "анализ" для получения данных о рынке."""
                
                keyboard = self._create_main_menu()
                await message.answer(response_text, reply_markup=keyboard)
                
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_text_message: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте /start")
    
    def _create_main_menu(self) -> InlineKeyboardBuilder:
        """Создание главного меню"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="📊 Анализ рынка", callback_data="market_analysis")
        )
        builder.add(
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")
        )
        builder.adjust(1)  # Одна кнопка в ряд
        return builder.as_markup()
    
    def _create_analysis_menu(self) -> InlineKeyboardBuilder:
        """Создание меню после анализа"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="🔄 Обновить анализ", callback_data="market_analysis")
        )
        builder.add(
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu")
        )
        builder.adjust(1)
        return builder.as_markup()
    
    def _create_about_menu(self) -> InlineKeyboardBuilder:
        """Создание меню в разделе О боте"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="📊 Попробовать анализ", callback_data="market_analysis")
        )
        builder.add(
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu")
        )
        builder.adjust(1)
        return builder.as_markup()
    
    def _create_error_menu(self) -> InlineKeyboardBuilder:
        """Создание меню при ошибке"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="market_analysis")
        )
        builder.add(
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu")
        )
        builder.adjust(1)
        return builder.as_markup()
    
    def _format_quick_stats(self, market_data: dict) -> str:
        """Форматирование краткой статистики"""
        try:
            price = market_data.get('current_price', 0)
            change_24h = market_data.get('price_change_24h', 0)
            volume_24h = market_data.get('volume_24h', 0)
            high_24h = market_data.get('high_24h', 0)
            low_24h = market_data.get('low_24h', 0)
            
            # Эмодзи для тренда
            trend_emoji = "🟢" if change_24h > 0 else "🔴" if change_24h < 0 else "🔶"
            
            # Форматируем объем
            if volume_24h > 1000:
                volume_str = f"{volume_24h/1000:.1f}K"
            else:
                volume_str = f"{volume_24h:.0f}"
            
            return f"""💰 *Текущая цена:* ${price:,.2f}
{trend_emoji} *Изменение 24ч:* {change_24h:+.2f}%
📊 *Объем 24ч:* {volume_str} BTC
📈 *Максимум:* ${high_24h:,.2f}
📉 *Минимум:* ${low_24h:,.2f}"""
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования статистики: {e}")
            return "📊 *Статистика недоступна*"
    
    async def close(self):
        """Корректное закрытие всех ресурсов бота"""
        try:
            logger.info("🔄 Закрытие Telegram бота...")
            
            # Закрываем HTTP сессию Bybit клиента
            if self.bybit_client:
                await self.bybit_client.close()
                logger.info("✅ BybitClient сессии закрыты")
            
            # Закрываем HTTP сессию бота
            if self.bot and self.bot.session:
                await self.bot.session.close()
                logger.info("✅ Telegram bot сессия закрыта")
                
            logger.info("🔴 Telegram бот корректно остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при закрытии бота: {e}")
