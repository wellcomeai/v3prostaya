import logging
import asyncio
from typing import Set, Optional
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.enums import ParseMode

# ✅ OpenAIAnalyzer оставляем
from openai_integration import OpenAIAnalyzer

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram бот для анализа рынка на aiogram (webhook режим) - v2.3"""
    
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.router = Router()
        
        # ✅ OpenAIAnalyzer сохраняем
        self.openai_analyzer = OpenAIAnalyzer()
        
        # Список пользователей для сигналов
        self.signal_subscribers: Set[int] = set()
        
        # Регистрируем все обработчики
        self._register_handlers()
        
        # Подключаем роутер к диспетчеру
        self.dp.include_router(self.router)
        
        logger.info("🤖 TelegramBot инициализирован для webhook режима (SimpleCandleSync + SimpleFuturesSync)")
    
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
        # Обработчики сигналов
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
            
            welcome_text = f"""🤖 *Bybit Trading Bot v2.3* 

Привет, {user_name}! Я помогаю анализировать рынок криптовалют и фьючерсов.

📊 *Что я умею:*
- Синхронизация данных криптовалют (Bybit)
- 🆕 Синхронизация фьючерсов CME (YFinance)
- Сохранение исторических данных в PostgreSQL
- Отправка торговых сигналов в реальном времени
- Модульная архитектура для надежности

🔥 *Активные компоненты v2.3:*
- SimpleCandleSync - синхронизация криптовалют
- SimpleFuturesSync - синхронизация фьючерсов
- MarketDataManager - real-time данные
- StrategyOrchestrator - управление стратегиями  
- SignalManager - обработка и фильтрация сигналов

🚀 *Символы в мониторинге:*
- Crypto: BTC, ETH, BNB, SOL, XRP, DOGE и др.
- Futures: MCL, MGC, MES, MNQ (CME micro)

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
- 🔄 Автоматическая синхронизация свечей
- 📈 Мониторинг криптовалют (15 пар)
- 🆕 Мониторинг фьючерсов CME (4 контракта)
- 💾 Сохранение в PostgreSQL
- 🚨 Торговые сигналы в реальном времени

🆕 *Архитектура v2.3:*
- SimpleCandleSync - REST API синхронизация (крипта)
- SimpleFuturesSync - YFinance синхронизация (фьючерсы)
- MarketDataManager - WebSocket ticker (опционально)
- StrategyOrchestrator - управление стратегиями
- SignalManager - умная фильтрация сигналов

🚨 *Торговые сигналы:*
- Мониторинг в реальном времени
- Анализ импульсных движений цены
- Детекция резких изменений (>2% за минуту)
- Анализ ордербука и объемов
- Интеллектуальная фильтрация сигналов
- Кулдаун между сигналами (5 минут)

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
        """Обработка запроса анализа рынка - временно недоступен"""
        user_id = callback.from_user.id
        user_name = callback.from_user.first_name or "пользователь"
        
        try:
            await callback.answer()
            
            logger.info(f"📊 Запрос анализа от {user_name} (ID: {user_id})")
            
            # Временное сообщение о недоступности
            response_text = """🔧 *Анализ рынка временно недоступен*

Функция анализа находится в разработке и будет доступна в следующей версии.

🚀 *Что работает сейчас:*
- ✅ SimpleCandleSync - синхронизация 15 криптовалют
  - Интервалы: 1m, 5m, 15m, 1h, 4h, 1d
  - Источник: Bybit REST API
  - Автоматическая проверка пропусков

- ✅ SimpleFuturesSync - синхронизация 4 фьючерсов
  - Символы: MCL, MGC, MES, MNQ (CME micro)
  - Интервалы: 1m, 5m, 15m, 1h, 4h, 1d
  - Источник: Yahoo Finance API

- ✅ PostgreSQL база данных
  - Все данные сохраняются
  - Готовы для бэктестинга
  - Доступны через REST API

- ✅ Торговые сигналы
  - Real-time через StrategyOrchestrator
  - MomentumStrategy активна
  - SignalManager фильтрует дубликаты

🔜 *Скоро будет добавлено:*
- 📊 REST API провайдер для анализа
- 🤖 AI анализ текущего состояния рынка
- 📈 Детальная статистика и графики
- 💡 Рекомендации на основе стратегий

_Система работает в фоновом режиме и собирает данные 24/7_

Проверить состояние системы:
- /health - https://bybitmybot.onrender.com/health
- /sync-status - статус синхронизации криптовалют
- /futures-sync-status - статус синхронизации фьючерсов"""
            
            keyboard = self._create_analysis_menu()
            
            await callback.message.edit_text(
                response_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"ℹ️ Показано временное сообщение пользователю {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_market_analysis: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_about(self, callback: CallbackQuery):
        """Обработка запроса информации о боте"""
        try:
            await callback.answer()
            
            about_text = """ℹ️ *О боте*

🤖 *Bybit Trading Bot v2.3*
SimpleCandleSync + SimpleFuturesSync Architecture

*🏗️ Модульная архитектура:*
- 🔄 SimpleCandleSync - REST API синхронизация криптовалют
  - 15 торговых пар Bybit
  - 6 временных интервалов
  - Автоматическая проверка пропусков
  - Восстановление после сбоев

- 🔄 SimpleFuturesSync - YFinance синхронизация фьючерсов
  - 4 микро-фьючерса CME
  - 6 временных интервалов
  - Учет ограничений YFinance API
  - Параллельная работа с SimpleCandleSync

- 📊 MarketDataManager (опционально)
  - WebSocket ticker для real-time цен
  - Кэширование REST API запросов
  - Переподключение при разрыве

- 🎭 StrategyOrchestrator
  - Координация торговых стратегий
  - MomentumStrategy для импульсов
  - Параллельное выполнение анализа

- 🎛️ SignalManager
  - Интеллектуальная фильтрация
  - Управление кулдаунами
  - Приоритизация сигналов

*Технологии:*
- 📈 Bybit REST API v5 для криптовалют
- 📊 Yahoo Finance для фьючерсов CME
- 🤖 OpenAI GPT-4 для AI анализа
- 🚀 Python aiogram для Telegram
- 💾 PostgreSQL для хранения данных
- ⚡ Асинхронная архитектура

*Мониторинг:*
- 15 криптовалютных пар (BTC, ETH, BNB, SOL...)
- 4 микро-фьючерса CME (MCL, MGC, MES, MNQ)
- 6 интервалов (1m, 5m, 15m, 1h, 4h, 1d)
- Автоматическая синхронизация 24/7

*Надежность:*
- ✅ Отсутствие deadlock благодаря REST API
- ✅ Автоматическое восстановление
- ✅ Проверка и заполнение пропусков
- ✅ Health monitoring
- ✅ Graceful shutdown

*Режим работы:*
- 🔗 Webhook для мгновенных ответов
- 📡 REST API для исторических данных  
- ⚡ WebSocket ticker (опционально)
- ☁️ Развернуто на Render.com

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
    
    async def handle_signals_menu(self, callback: CallbackQuery):
        """Обработка меню торговых сигналов"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            is_subscribed = user_id in self.signal_subscribers
            
            status_text = "✅ Активна" if is_subscribed else "❌ Неактивна"
            subscribers_count = len(self.signal_subscribers)
            
            menu_text = f"""🚨 *Торговые сигналы v2.3*

📊 *Статус подписки:* {status_text}
👥 *Подписчиков:* {subscribers_count}

🏗️ *Модульная архитектура сигналов:*
- SimpleCandleSync - актуальные данные криптовалют
- SimpleFuturesSync - актуальные данные фьючерсов
- MarketDataManager - real-time WebSocket ticker
- StrategyOrchestrator - управление стратегиями
- SignalManager - умная фильтрация
- MomentumStrategy - импульсная торговля

🔥 *Особенности v2.3:*
- REST API синхронизация без deadlock
- Параллельная обработка крипты и фьючерсов
- Анализ 15 криптопар + 4 фьючерса
- Детекция резких движений (>2%)
- Интеллектуальная фильтрация дубликатов
- Управление частотой сигналов (кулдаун 5 минут)

⏱️ *Интервалы и фильтры:*
- Анализ каждые 30 секунд
- Мгновенные экстремальные сигналы (>2%)
- Кулдаун между сигналами: 5 минут
- Минимальная сила сигнала: 0.5
- Максимум 12 сигналов в час

🎯 *Типы сигналов:*
- 🟢 BUY / STRONG_BUY - сигналы на покупку
- 🔴 SELL / STRONG_SELL - сигналы на продажу
- Сила сигнала: 0.5 - 1.0
- Уровень уверенности: LOW/MEDIUM/HIGH

📈 *Источники данных:*
- Bybit REST API - криптовалюты
- Yahoo Finance - CME фьючерсы
- PostgreSQL - исторические данные
- WebSocket - real-time цены (опционально)

⚠️ *ВНИМАНИЕ:* Торговые сигналы несут высокие риски! Это не инвестиционный совет!"""
            
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
                "Теперь вы будете получать торговые сигналы от новой модульной системы v2.3.\n\n"
                "🏗️ *Сигналы генерируются через:*\n"
                "• SimpleCandleSync - синхронизация криптовалют\n"
                "• SimpleFuturesSync - синхронизация фьючерсов\n"
                "• MarketDataManager - real-time данные\n"
                "• StrategyOrchestrator - координация стратегий\n"
                "• SignalManager - фильтрация и обработка\n"
                "• MomentumStrategy - импульсная стратегия\n\n"
                "🔥 *Основа сигналов:*\n"
                "• REST API синхронизация без блокировок\n"
                "• Анализ 15 криптопар + 4 фьючерса\n"
                "• Движения цены за 1m, 5m, 15m, 1h\n"
                "• Мониторинг WebSocket ticker\n"
                "• Объемный анализ торгов\n"
                "• Детекция экстремальных движений\n\n"
                "📱 *Уведомления:*\n"
                "• При сильных сигналах (сила ≥0.5)\n"
                "• Максимум 1 сигнал типа в 5 минут\n"
                "• Умная фильтрация дубликатов\n"
                "• В любое время суток\n\n"
                "⚠️ *Важно:* Торговые сигналы несут высокие риски!\n"
                "_Это не инвестиционный совет!_",
                reply_markup=self._create_signals_menu(True),
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"📡 Пользователь {user_name} ({user_id}) подписался на сигналы v2.3")
            
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
            
            welcome_text = """🤖 *Bybit Trading Bot v2.3*

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
                    text="📊 Информация об анализе",
                    callback_data="market_analysis"
                ))
                
                await message.answer(
                    "📊 Анализ рынка находится в разработке.\n"
                    "_SimpleCandleSync + SimpleFuturesSync собирают данные для будущего анализа_",
                    reply_markup=builder.as_markup(),
                    parse_mode=ParseMode.MARKDOWN
                )
            elif any(word in user_text for word in ['сигнал', 'сигналы', 'уведомления', 'подписка']):
                # Создаем inline кнопку для сигналов
                builder = InlineKeyboardBuilder()
                builder.add(InlineKeyboardButton(
                    text="🚨 Торговые сигналы",
                    callback_data="signals_menu"
                ))
                
                await message.answer(
                    "🚨 Хотите настроить торговые сигналы?\n"
                    "_Сигналы генерируются через StrategyOrchestrator v2.3_",
                    reply_markup=builder.as_markup(),
                    parse_mode=ParseMode.MARKDOWN
                )
            elif any(word in user_text for word in ['помощь', 'справка', 'help']):
                await self.help_command(message)
            else:
                # Для всех остальных сообщений показываем меню
                response_text = """🤖 Я анализирую рынок криптовалют и фьючерсов, отправляю торговые сигналы!

🆕 *Версия 2.3 - SimpleCandleSync + SimpleFuturesSync*

Используйте кнопки меню или команды:
/start - главное меню
/help - справка

Или просто напишите:
- "сигналы" для настройки уведомлений
- "помощь" для подробной информации"""
                
                keyboard = self._create_main_menu()
                await message.answer(response_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
                
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_text_message: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте /start")
    
    # ========== МЕНЮ И КЛАВИАТУРЫ ==========
    
    def _create_main_menu(self) -> InlineKeyboardBuilder:
        """Создание главного меню"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="📊 О системе анализа", callback_data="market_analysis")
        )
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
            InlineKeyboardButton(text="🚨 Торговые сигналы", callback_data="signals_menu")
        )
        builder.add(
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")
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
            
        builder.add(InlineKeyboardButton(text="ℹ️ О боте", callback_data="about"))
        builder.add(InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu"))
        builder.adjust(1)
        
        return builder.as_markup()
    
    async def close(self):
        """Корректное закрытие всех ресурсов бота"""
        try:
            logger.info("🔄 Закрытие Telegram бота...")
            
            # Закрываем HTTP сессию бота
            if self.bot and self.bot.session:
                await self.bot.session.close()
                logger.info("✅ Telegram bot сессия закрыта")
                
            logger.info("🔴 Telegram бот корректно остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при закрытии бота: {e}")
