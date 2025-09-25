import logging
import asyncio
from typing import Set
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
        
        # 🆕 НОВОЕ: Список пользователей для сигналов
        self.signal_subscribers: Set[int] = set()
        
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
        # 🆕 НОВОЕ: Обработчики сигналов
        self.router.callback_query.register(
            self.handle_signals_menu,
            F.data == "signals_menu"
        )
        self.router.callback_query.register(
            self.handle_subscribe_signals,
            F.data == "subscribe_signals"
        )
        self.router.callback_query.register(
            self.handle_unsubscribe_signals,
            F.data == "unsubscribe_signals"
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
            
            welcome_text = f"""🤖 *Bybit Trading Bot v2.1*

Привет, {user_name}! Я помогу тебе анализировать рынок криптовалют.

📊 *Что я умею:*
• Получать актуальные данные с Bybit
• Анализировать рынок BTC/USDT с помощью ИИ
• Предоставлять статистику за 24 часа
• 🆕 Отправлять торговые сигналы в реальном времени

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
• 🆕 🚨 Торговые сигналы WebSocket в реальном времени

🆕 *Торговые сигналы:*
• Мониторинг в реальном времени через WebSocket
• Анализ импульсных движений цены
• Детекция резких изменений (>2% за минуту)
• Анализ ордербука и объемов
• Умная фильтрация сигналов

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

🤖 *Bybit Trading Bot v2.1*

*Технологии:*
• 📈 Bybit REST API v5 для рыночных данных
• ⚡ Bybit WebSocket API для данных в реальном времени
• 🤖 OpenAI GPT-4 для анализа и прогнозов
• 🚀 Python aiogram для Telegram интеграции
• ⚡ Асинхронная архитектура для скорости

*Функции:*
• Анализ рынка BTC/USDT в реальном времени
• ИИ-прогнозы на основе текущих данных
• Статистика объемов и волатильности
• Отслеживание трендов за 24 часа
• 🆕 Торговые сигналы WebSocket в реальном времени

*🆕 Новые возможности v2.1:*
• WebSocket подключение для мгновенных данных
• Анализ импульсных движений цены
• Мониторинг ордербука в реальном времени
• Детекция резких движений (>2% за минуту)
• Умная система фильтрации сигналов
• Подписка на персональные уведомления

*Режим работы:*
• 🔗 Webhook для мгновенных ответов
• ⚡ WebSocket для сигналов в реальном времени
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
    
    # 🆕 НОВЫЕ МЕТОДЫ ДЛЯ ТОРГОВЫХ СИГНАЛОВ
    
    async def handle_signals_menu(self, callback: CallbackQuery):
        """Обработка меню торговых сигналов"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            is_subscribed = user_id in self.signal_subscribers
            
            status_text = "✅ Активна" if is_subscribed else "❌ Неактивна"
            subscribers_count = len(self.signal_subscribers)
            
            menu_text = f"""🚨 *Торговые сигналы WebSocket*

📊 *Статус подписки:* {status_text}
👥 *Подписчиков:* {subscribers_count}

🔥 *Особенности:*
• Данные в реальном времени через WebSocket
• Анализ импульсных движений
• Мониторинг ордербука  
• Детекция резких движений цены
• Интеллектуальная фильтрация сигналов

⏱️ *Интервалы анализа:*
• Мгновенные уведомления при движении >2%
• Полный анализ каждые 30 секунд
• Кулдаун между сигналами: 5 минут

🎯 *Типы сигналов:*
• 🟢 BUY - сигналы на покупку
• 🔴 SELL - сигналы на продажу
• Сила сигнала от 0.5 до 1.0

⚠️ *ВНИМАНИЕ:* Торговые сигналы несут высокие риски!"""
            
            keyboard = self._create_signals_menu(is_subscribed)
            
            await callback.message.edit_text(
                menu_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в меню сигналов: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_subscribe_signals(self, callback: CallbackQuery):
        """Подписка на торговые сигналы"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            user_name = callback.from_user.first_name or "пользователь"
            
            self.signal_subscribers.add(user_id)
            
            await callback.message.edit_text(
                "✅ *Подписка активирована!*\n\n"
                "Теперь вы будете получать торговые сигналы в реальном времени.\n\n"
                "🔥 *Сигналы основаны на:*\n"
                "• WebSocket данных в реальном времени\n"  
                "• Анализе движений цены и объемов\n"
                "• Анализе ордербука\n"
                "• Импульсных стратегиях\n"
                "• Детекции резких движений >2%\n\n"
                "📱 *Уведомления будут приходить:*\n"
                "• При сильных сигналах (сила ≥0.5)\n"
                "• Максимум 1 сигнал одного типа в 5 минут\n"
                "• В любое время суток\n\n"
                "⚠️ *Важно:* Торговые сигналы несут высокие риски!\n"
                "_Это не инвестиционный совет!_",
                reply_markup=self._create_signals_menu(True),
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"📡 Пользователь {user_name} ({user_id}) подписался на сигналы")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подписки на сигналы: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_unsubscribe_signals(self, callback: CallbackQuery):
        """Отписка от торговых сигналов"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            user_name = callback.from_user.first_name or "пользователь"
            
            self.signal_subscribers.discard(user_id)
            
            await callback.message.edit_text(
                "🔕 *Подписка отключена*\n\n"
                "Вы больше не будете получать торговые сигналы.\n\n"
                "Вы можете снова подписаться в любое время через главное меню.\n\n"
                "Спасибо за использование наших сигналов! 🙏",
                reply_markup=self._create_signals_menu(False),
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"📡 Пользователь {user_name} ({user_id}) отписался от сигналов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отписки от сигналов: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def broadcast_signal(self, message: str):
        """Отправляет сигнал всем подписчикам"""
        try:
            if not self.signal_subscribers:
                logger.info("📡 Нет подписчиков для сигнала")
                return
            
            sent_count = 0
            failed_count = 0
            blocked_users = []
            
            for user_id in self.signal_subscribers.copy():  # Копируем для безопасности
                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    sent_count += 1
                    
                    # Небольшая задержка между отправками для избежания rate limit
                    await asyncio.sleep(0.05)
                    
                except Exception as e:
                    failed_count += 1
                    error_msg = str(e).lower()
                    
                    # Если пользователь заблокировал бота или удалил чат
                    if any(phrase in error_msg for phrase in [
                        "bot was blocked by the user",
                        "user is deactivated", 
                        "chat not found"
                    ]):
                        blocked_users.append(user_id)
                        logger.info(f"🚫 Пользователь {user_id} заблокировал бота или удалил чат")
                    else:
                        logger.warning(f"⚠️ Не удалось отправить сигнал пользователю {user_id}: {e}")
            
            # Удаляем заблокировавших пользователей из списка подписчиков
            for user_id in blocked_users:
                self.signal_subscribers.discard(user_id)
            
            if blocked_users:
                logger.info(f"🧹 Удалено {len(blocked_users)} неактивных подписчиков")
            
            logger.info(f"📨 Сигнал отправлен: ✅{sent_count} успешно, ❌{failed_count} ошибок")
            
        except Exception as e:
            logger.error(f"💥 Ошибка рассылки сигнала: {e}")
    
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
            elif any(word in user_text for word in ['сигнал', 'сигналы', 'уведомления', 'подписка']):
                # Создаем inline кнопку для сигналов
                builder = InlineKeyboardBuilder()
                builder.add(InlineKeyboardButton(
                    text="🚨 Торговые сигналы",
                    callback_data="signals_menu"
                ))
                
                await message.answer(
                    "🚨 Хотите настроить торговые сигналы?",
                    reply_markup=builder.as_markup()
                )
            elif any(word in user_text for word in ['помощь', 'справка', 'help']):
                await self.help_command(message)
            else:
                # Для всех остальных сообщений показываем меню
                response_text = """🤖 Я анализирую рынок криптовалют и отправляю торговые сигналы!

Используйте кнопки меню или команды:
/start - главное меню
/help - справка

Или просто напишите:
• "анализ" для получения данных о рынке
• "сигналы" для настройки уведомлений"""
                
                keyboard = self._create_main_menu()
                await message.answer(response_text, reply_markup=keyboard)
                
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_text_message: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте /start")
    
    # МЕНЮ И КЛАВИАТУРЫ
    
    def _create_main_menu(self) -> InlineKeyboardBuilder:
        """Создание главного меню"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="📊 Анализ рынка", callback_data="market_analysis")
        )
        # 🆕 НОВОЕ: Кнопка торговых сигналов
        builder.add(
            InlineKeyboardButton(text="🚨 Торговые сигналы", callback_data="signals_menu")
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
            InlineKeyboardButton(text="🚨 Торговые сигналы", callback_data="signals_menu")
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
            InlineKeyboardButton(text="🚨 Торговые сигналы", callback_data="signals_menu")
        )
        builder.add(
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu")
        )
        builder.adjust(1)
        return builder.as_markup()
    
    def _create_signals_menu(self, is_subscribed: bool) -> InlineKeyboardBuilder:
        """Создание меню сигналов"""
        builder = InlineKeyboardBuilder()
        
        if is_subscribed:
            builder.add(InlineKeyboardButton(text="🔕 Отписаться", callback_data="unsubscribe_signals"))
        else:
            builder.add(InlineKeyboardButton(text="🔔 Подписаться", callback_data="subscribe_signals"))
            
        builder.add(InlineKeyboardButton(text="📊 Анализ рынка", callback_data="market_analysis"))
        builder.add(InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu"))
        builder.adjust(1)
        
        return builder.as_markup()
    
    def _create_error_menu(self) -> InlineKeyboardBuilder:
        """Создание меню при ошибке"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="market_analysis")
        )
        builder.add(
            InlineKeyboardButton(text="🚨 Торговые сигналы", callback_data="signals_menu")
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
