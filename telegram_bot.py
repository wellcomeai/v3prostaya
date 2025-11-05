import logging
import asyncio
from typing import Set, Optional, Dict, Any, List
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.enums import ParseMode

from openai_integration import OpenAIAnalyzer
from database import get_database_manager

logger = logging.getLogger(__name__)

class TelegramBot:
    """
    Telegram бот для анализа рынка на aiogram (webhook режим) - v3.2.1
    
    ✅ Исправлено в v3.2.1:
    - Правильный доступ к БД через get_database_manager()
    - Удален неправильный self.repository.pool
    - Все методы БД используют единый подход
    
    ✅ Функции v3.2.0:
    - Сохранение пользователей в PostgreSQL
    - Загрузка пользователей при старте
    - Автоматическая синхронизация с БД
    - Статистика использования
    - Управление заблокированными пользователями
    """
    
    def __init__(self, token: str, repository=None, ta_context_manager=None):
        """
        Args:
            token: Telegram bot token
            repository: MarketDataRepository для доступа к данным
            ta_context_manager: TechnicalAnalysisContextManager для технического анализа
        """
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.router = Router()
        
        self.openai_analyzer = OpenAIAnalyzer()
        self.repository = repository
        self.ta_context_manager = ta_context_manager
        
        # ✅ Все пользователи в памяти (для быстрого доступа)
        self.all_users: Set[int] = set()
        
        self.user_analysis_state: Dict[int, Dict[str, Any]] = {}
        
        self._register_handlers()
        
        self.dp.include_router(self.router)
        
        logger.info("🤖 TelegramBot v3.2.1 инициализирован (DB-backed users, fixed)")
        logger.info(f"   • Repository: {'✅' if repository else '❌'}")
        logger.info(f"   • TA Context Manager: {'✅' if ta_context_manager else '❌'}")
        logger.info(f"   • OpenAI Analyzer: {'✅' if self.openai_analyzer else '❌'}")
    
    # ==================== DATABASE METHODS ====================
    
    async def load_users_from_db(self) -> int:
        """
        ✅ Загрузить всех активных пользователей из БД при старте
        
        Returns:
            int: Количество загруженных пользователей
        """
        try:
            logger.info("📥 Загрузка пользователей из БД...")
            
            # ✅ ИСПРАВЛЕНО: Правильный доступ к БД
            db_manager = get_database_manager()
            
            # Проверяем существование таблицы
            check_table_query = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'bot_users'
                );
            """
            
            table_exists = await db_manager.fetchval(check_table_query)
            
            if not table_exists:
                logger.warning("⚠️ Таблица bot_users не существует, создаю...")
                await self._create_bot_users_table()
            
            # Загружаем активных пользователей
            query = """
                SELECT user_id 
                FROM bot_users 
                WHERE is_active = TRUE AND is_blocked = FALSE
                ORDER BY last_interaction_at DESC;
            """
            
            rows = await db_manager.fetch(query)
            
            # Добавляем в память
            for row in rows:
                self.all_users.add(row['user_id'])
            
            logger.info(f"✅ Загружено {len(self.all_users)} активных пользователей")
            
            return len(self.all_users)
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки пользователей из БД: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0
    
    async def _create_bot_users_table(self):
        """Создать таблицу bot_users если её нет"""
        try:
            # ✅ ИСПРАВЛЕНО: Правильный доступ к БД
            db_manager = get_database_manager()
            
            create_table_query = """
                CREATE TABLE IF NOT EXISTS bot_users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    language_code VARCHAR(10),
                    is_active BOOLEAN DEFAULT TRUE,
                    is_blocked BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    last_interaction_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    signals_received_count INTEGER DEFAULT 0
                );
                
                CREATE INDEX IF NOT EXISTS idx_bot_users_active 
                    ON bot_users(is_active) WHERE is_active = TRUE;
                    
                CREATE INDEX IF NOT EXISTS idx_bot_users_last_interaction 
                    ON bot_users(last_interaction_at);
            """
            
            await db_manager.execute(create_table_query)
            logger.info("✅ Таблица bot_users создана")
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания таблицы bot_users: {e}")
    
    async def save_user_to_db(
        self, 
        user_id: int, 
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: Optional[str] = None
    ) -> bool:
        """
        ✅ Сохранить пользователя в БД (INSERT or UPDATE)
        
        Args:
            user_id: ID пользователя Telegram
            username: Username (@username)
            first_name: Имя
            last_name: Фамилия
            language_code: Код языка
            
        Returns:
            bool: True если успешно
        """
        try:
            # ✅ ИСПРАВЛЕНО: Правильный доступ к БД
            db_manager = get_database_manager()
            
            query = """
                INSERT INTO bot_users (
                    user_id, username, first_name, last_name, language_code,
                    is_active, is_blocked, created_at, last_interaction_at
                )
                VALUES ($1, $2, $3, $4, $5, TRUE, FALSE, NOW(), NOW())
                ON CONFLICT (user_id) 
                DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    language_code = EXCLUDED.language_code,
                    last_interaction_at = NOW(),
                    is_active = TRUE,
                    is_blocked = FALSE;
            """
            
            await db_manager.execute(
                query,
                user_id,
                username,
                first_name,
                last_name,
                language_code
            )
            
            logger.debug(f"💾 Пользователь {user_id} сохранен в БД")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения пользователя {user_id} в БД: {e}")
            return False
    
    async def update_user_interaction(self, user_id: int) -> bool:
        """
        ✅ Обновить время последнего взаимодействия
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если успешно
        """
        try:
            # ✅ ИСПРАВЛЕНО: Правильный доступ к БД
            db_manager = get_database_manager()
            
            query = """
                UPDATE bot_users 
                SET last_interaction_at = NOW()
                WHERE user_id = $1;
            """
            
            await db_manager.execute(query, user_id)
            return True
            
        except Exception as e:
            logger.debug(f"⚠️ Ошибка обновления взаимодействия {user_id}: {e}")
            return False
    
    async def mark_user_blocked(self, user_id: int) -> bool:
        """
        ✅ Пометить пользователя как заблокировавшего бота
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если успешно
        """
        try:
            # ✅ ИСПРАВЛЕНО: Правильный доступ к БД
            db_manager = get_database_manager()
            
            query = """
                UPDATE bot_users 
                SET is_blocked = TRUE, is_active = FALSE
                WHERE user_id = $1;
            """
            
            await db_manager.execute(query, user_id)
            logger.info(f"🚫 Пользователь {user_id} помечен как заблокированный")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка пометки пользователя {user_id} заблокированным: {e}")
            return False
    
    async def increment_signals_count(self, user_id: int) -> bool:
        """
        ✅ Увеличить счетчик полученных сигналов
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если успешно
        """
        try:
            # ✅ ИСПРАВЛЕНО: Правильный доступ к БД
            db_manager = get_database_manager()
            
            query = """
                UPDATE bot_users 
                SET signals_received_count = signals_received_count + 1,
                    last_interaction_at = NOW()
                WHERE user_id = $1;
            """
            
            await db_manager.execute(query, user_id)
            return True
            
        except Exception as e:
            logger.debug(f"⚠️ Ошибка увеличения счетчика сигналов {user_id}: {e}")
            return False
    
    async def get_user_stats(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        ✅ Получить статистику пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Optional[Dict]: Статистика или None
        """
        try:
            # ✅ ИСПРАВЛЕНО: Правильный доступ к БД
            db_manager = get_database_manager()
            
            query = """
                SELECT 
                    user_id,
                    username,
                    first_name,
                    is_active,
                    is_blocked,
                    created_at,
                    last_interaction_at,
                    signals_received_count
                FROM bot_users
                WHERE user_id = $1;
            """
            
            row = await db_manager.fetchrow(query, user_id)
            
            if row:
                return dict(row)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики пользователя {user_id}: {e}")
            return None
    
    async def get_all_users_stats(self) -> Dict[str, Any]:
        """
        ✅ Получить общую статистику по всем пользователям
        
        Returns:
            Dict: Статистика
        """
        try:
            # ✅ ИСПРАВЛЕНО: Правильный доступ к БД
            db_manager = get_database_manager()
            
            query = """
                SELECT 
                    COUNT(*) as total_users,
                    COUNT(*) FILTER (WHERE is_active = TRUE AND is_blocked = FALSE) as active_users,
                    COUNT(*) FILTER (WHERE is_blocked = TRUE) as blocked_users,
                    SUM(signals_received_count) as total_signals_sent,
                    MAX(last_interaction_at) as last_interaction
                FROM bot_users;
            """
            
            row = await db_manager.fetchrow(query)
            
            return {
                "total_users": row['total_users'] or 0,
                "active_users": row['active_users'] or 0,
                "blocked_users": row['blocked_users'] or 0,
                "total_signals_sent": row['total_signals_sent'] or 0,
                "last_interaction": row['last_interaction']
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения общей статистики: {e}")
            return {
                "total_users": len(self.all_users),
                "active_users": len(self.all_users),
                "blocked_users": 0,
                "total_signals_sent": 0
            }
    
    # ==================== UTILITY METHODS ====================
    
    @staticmethod
    def escape_html(text: str) -> str:
        """
        Экранирование HTML спецсимволов для безопасной отправки в Telegram
        
        Args:
            text: Исходный текст (может содержать <, >, &)
            
        Returns:
            str: Экранированный текст
        """
        if not text:
            return ""
        
        return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))
    
    # ==================== HANDLERS REGISTRATION ====================
    
    def _register_handlers(self):
        """Регистрация всех обработчиков"""
        self.router.message.register(self.start_command, Command("start"))
        self.router.message.register(self.help_command, Command("help"))
        
        self.router.callback_query.register(
            self.handle_market_analysis_start,
            F.data == "market_analysis"
        )
        self.router.callback_query.register(
            self.handle_select_crypto,
            F.data == "select_crypto"
        )
        self.router.callback_query.register(
            self.handle_select_futures,
            F.data == "select_futures"
        )
        self.router.callback_query.register(
            self.handle_symbol_selection,
            F.data.startswith("analyze_")
        )
        self.router.callback_query.register(
            self.handle_request_analysis,
            F.data == "request_analysis"
        )
        self.router.callback_query.register(
            self.handle_cancel_analysis,
            F.data == "cancel_analysis"
        )
        self.router.callback_query.register(
            self.handle_about, 
            F.data == "about"
        )
        self.router.callback_query.register(
            self.handle_back_to_menu,
            F.data == "back_to_menu"
        )
        
        self.router.callback_query.register(self.handle_unknown_callback)
        
        self.router.message.register(self.handle_text_message, F.text)
        
        logger.info("✅ Все обработчики зарегистрированы")
    
    # ==================== COMMAND HANDLERS ====================
    
    async def start_command(self, message: Message):
        """
        ✅ Обработчик команды /start - добавляем пользователя в список И в БД
        """
        try:
            user_name = message.from_user.first_name or "друг"
            user_id = message.from_user.id
            username = message.from_user.username
            last_name = message.from_user.last_name
            language_code = message.from_user.language_code
            
            # ✅ Добавляем в память
            self.all_users.add(user_id)
            
            # ✅ Сохраняем в БД
            await self.save_user_to_db(
                user_id=user_id,
                username=username,
                first_name=user_name,
                last_name=last_name,
                language_code=language_code
            )
            
            logger.info(
                f"👤 Пользователь: {user_name} (@{username}) (ID: {user_id}) "
                f"добавлен. Всего: {len(self.all_users)}"
            )
            
            keyboard = self._create_main_menu()
            
            welcome_text = f"""🤖 <b>Bybit Trading Bot v3.2.1</b> 

Привет, {self.escape_html(user_name)}! 

📊 <b>Что я умею:</b>
- Синхронизация данных криптовалют (Bybit)
- 🆕 Синхронизация фьючерсов CME (YFinance)
- Сохранение исторических данных в PostgreSQL
- 🤖 AI анализ рынка через OpenAI GPT-4
- 🎭 Анализ через 3 торговые стратегии одновременно
- 🚨 Отправка торговых сигналов в реальном времени
- 💾 Хранение пользователей в БД
- Модульная архитектура для надежности

🔥 <b>Активные компоненты v3.2:</b>
- SimpleCandleSync - синхронизация криптовалют
- SimpleFuturesSync - синхронизация фьючерсов
- Repository - прямой доступ к БД
- TechnicalAnalysisContextManager - технический анализ
- SignalManager - обработка с AI обогащением
- StrategyOrchestrator - управление стратегиями
- 🆕 Multi-Strategy Analysis - 3 стратегии параллельно
- 🆕 PostgreSQL User Storage - сохранение пользователей

🎭 <b>Стратегии для анализа:</b>
- BreakoutStrategy - пробои уровней
- BounceStrategy - отбои от уровней
- FalseBreakoutStrategy - ложные пробои

🚀 <b>Символы в мониторинге:</b>
- Crypto: BTC, ETH, BNB, SOL, XRP, DOGE и др.
- Futures: MCL, MGC, MES, MNQ (CME micro)

🔔 <b>Уведомления:</b>
Вы будете получать все торговые сигналы с AI анализом автоматически!
Ваши данные сохранены в базе - сигналы будут приходить даже после перезапуска бота.

Нажми кнопку ниже, чтобы начать! 👇"""
            
            await message.answer(
                welcome_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в start_command: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте позже.")
    
    async def help_command(self, message: Message):
        """Обработчик команды /help"""
        try:
            # Обновляем взаимодействие
            await self.update_user_interaction(message.from_user.id)
            
            help_text = """📖 <b>Справка по боту</b>

🔧 <b>Доступные команды:</b>
/start - Запуск бота
/help - Эта справка

📊 <b>Функции:</b>
- 🔄 Автоматическая синхронизация свечей
- 📈 Мониторинг криптовалют (15 пар)
- 🆕 Мониторинг фьючерсов CME (4 контракта)
- 💾 Сохранение в PostgreSQL
- 🤖 AI анализ через OpenAI GPT-4
- 🎭 Анализ через 3 торговые стратегии
- 🚨 Торговые сигналы в реальном времени
- 💾 Хранение пользователей в БД

🆕 <b>Архитектура v3.2:</b>
- SimpleCandleSync - REST API синхронизация (крипта)
- SimpleFuturesSync - YFinance синхронизация (фьючерсы)
- Repository - прямой доступ к базе данных
- TechnicalAnalysisContextManager - технический анализ
- SignalManager - фильтрация + AI обогащение
- StrategyOrchestrator - управление стратегиями
- 🆕 Multi-Strategy Analysis - параллельный запуск
- 🆕 PostgreSQL User Storage - надежное хранение
- OpenAI GPT-4 - AI анализ рынка

🎭 <b>Торговые стратегии:</b>
- BreakoutStrategy - торговля пробоев уровней
- BounceStrategy - торговля отбоев (БСУ-БПУ)
- FalseBreakoutStrategy - ловля ложных пробоев

🚨 <b>Торговые сигналы:</b>
- Мониторинг в реальном времени
- Анализ импульсных движений цены
- Детекция резких изменений (&gt;2% за минуту)
- Анализ ордербука и объемов
- Интеллектуальная фильтрация сигналов
- 🤖 AI обогащение каждого сигнала
- Кулдаун между сигналами (5 минут)

🔔 <b>Уведомления:</b>
Все пользователи бота автоматически получают торговые сигналы.
Ваш профиль сохранен в БД - сигналы будут приходить всегда!

⚠️ <b>Важно:</b>
Бот предоставляет аналитическую информацию, но не является инвестиционным советом. Торговля криптовалютами связана с высокими рисками.

🔄 Для начала работы используйте /start"""
            
            keyboard = self._create_main_menu()
            
            await message.answer(
                help_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в help_command: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте /start")
    
    # ==================== CALLBACK HANDLERS ====================
    
    async def handle_market_analysis_start(self, callback: CallbackQuery):
        """Обработка запроса анализа рынка - выбор типа актива"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            user_name = callback.from_user.first_name or "пользователь"
            
            # Обновляем взаимодействие
            await self.update_user_interaction(user_id)
            
            logger.info(f"📊 {user_name} ({user_id}) запросил анализ рынка")
            
            if not self.repository or not self.openai_analyzer:
                await callback.message.edit_text(
                    "❌ <b>Анализ рынка временно недоступен</b>\n\n"
                    "Система анализа не инициализирована.\n"
                    "Обратитесь к администратору.",
                    reply_markup=self._create_back_button(),
                    parse_mode=ParseMode.HTML
                )
                return
            
            self.user_analysis_state[user_id] = {}
            
            text = """📊 <b>АНАЛИЗ РЫНКА С ИИ</b>

🤖 Выберите тип актива для анализа:

<b>🪙 Криптовалюты</b> - Bybit spot pairs
- BTC, ETH, BNB, SOL, XRP, DOGE, ADA и др.
- Анализ текущей ситуации
- Технический анализ
- 🎭 Мнения 3 торговых стратегий
- AI прогноз на 1-3 дня

<b>📊 Фьючерсы</b> - CME micro futures
- MCL (нефть), MGC (золото)
- MES (S&amp;P 500), MNQ (Nasdaq)
- Комплексный технический анализ
- 🎭 Консенсус стратегий
- AI оценка перспектив

Нажмите кнопку ниже для выбора ⬇️"""
            
            keyboard = self._create_asset_type_menu()
            
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_market_analysis_start: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_select_crypto(self, callback: CallbackQuery):
        """Обработка выбора криптовалют"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            
            self.user_analysis_state[user_id] = {"asset_type": "crypto"}
            
            from config import Config
            crypto_symbols = Config.get_bybit_symbols()
            
            text = """🪙 <b>ВЫБЕРИТЕ КРИПТОВАЛЮТУ</b>

Доступные пары для анализа:"""
            
            keyboard = self._create_symbol_selection_menu(crypto_symbols, "crypto")
            
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_select_crypto: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_select_futures(self, callback: CallbackQuery):
        """Обработка выбора фьючерсов"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            
            self.user_analysis_state[user_id] = {"asset_type": "futures"}
            
            from config import Config
            futures_symbols = Config.get_yfinance_symbols() if hasattr(Config, 'get_yfinance_symbols') else []
            
            if not futures_symbols:
                await callback.message.edit_text(
                    "⚠️ <b>Фьючерсы недоступны</b>\n\n"
                    "Список фьючерсов не настроен в конфигурации.",
                    reply_markup=self._create_back_button(),
                    parse_mode=ParseMode.HTML
                )
                return
            
            text = """📊 <b>ВЫБЕРИТЕ ФЬЮЧЕРС</b>

Доступные контракты для анализа:

- <b>MCL</b> - Micro WTI Crude Oil
- <b>MGC</b> - Micro Gold
- <b>MES</b> - Micro E-mini S&amp;P 500
- <b>MNQ</b> - Micro E-mini Nasdaq-100"""
            
            keyboard = self._create_symbol_selection_menu(futures_symbols, "futures")
            
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_select_futures: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_symbol_selection(self, callback: CallbackQuery):
        """Обработка выбора конкретного символа"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            
            symbol = callback.data.replace("analyze_", "")
            
            if user_id not in self.user_analysis_state:
                self.user_analysis_state[user_id] = {}
            
            self.user_analysis_state[user_id]["symbol"] = symbol
            
            asset_type = self.user_analysis_state[user_id].get("asset_type", "crypto")
            emoji = "🪙" if asset_type == "crypto" else "📊"
            
            text = f"""{emoji} <b>АНАЛИЗ {symbol}</b>

Вы выбрали: <b>{symbol}</b>

📊 <b>Что будет проанализировано:</b>
- Текущая цена и изменения
- Технический анализ (уровни, ATR, тренд)
- Данные из базы за последние 24 часа
- 🎭 Запуск 3 торговых стратегий:
  • BreakoutStrategy
  • BounceStrategy
  • FalseBreakoutStrategy
- 🤖 AI прогноз от OpenAI GPT-4

⏱️ Анализ займет 8-12 секунд (запуск стратегий).

Нажмите кнопку для запуска анализа ⬇️"""
            
            keyboard = self._create_confirm_analysis_menu()
            
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_symbol_selection: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_request_analysis(self, callback: CallbackQuery):
        """
        🆕 v3.1: Обработка запроса анализа с запуском ВСЕХ стратегий
        (Полный код анализа сохранен из оригинального файла)
        """
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            user_name = callback.from_user.first_name or "пользователь"
            
            # Обновляем взаимодействие
            await self.update_user_interaction(user_id)
            
            if user_id not in self.user_analysis_state:
                await callback.message.edit_text(
                    "❌ Сессия истекла. Начните заново.",
                    reply_markup=self._create_back_button(),
                    parse_mode=ParseMode.HTML
                )
                return
            
            symbol = self.user_analysis_state[user_id].get("symbol")
            asset_type = self.user_analysis_state[user_id].get("asset_type", "crypto")
            
            if not symbol:
                await callback.message.edit_text(
                    "❌ Символ не выбран. Начните заново.",
                    reply_markup=self._create_back_button(),
                    parse_mode=ParseMode.HTML
                )
                return
            
            emoji = "🪙" if asset_type == "crypto" else "📊"
            await callback.message.edit_text(
                f"{emoji} <b>АНАЛИЗ {symbol}</b>\n\n"
                f"⏳ Собираю данные из БД...\n"
                f"📊 Получаю технический анализ...\n"
                f"🎭 Запускаю 3 торговые стратегии...\n"
                f"🤖 Запрашиваю AI анализ...\n\n"
                f"<i>Пожалуйста, подождите 8-12 секунд...</i>",
                parse_mode=ParseMode.HTML
            )
            
            logger.info(f"🔬 {user_name} ({user_id}) запустил Multi-Strategy анализ {symbol}")
            
            try:
                # ========== ПОЛНЫЙ КОД АНАЛИЗА ИЗ ОРИГИНАЛА ==========
                
                end_time = datetime.now()
                start_time_24h = end_time - timedelta(hours=24)
                start_time_1h = end_time - timedelta(hours=1)
                start_time_5h = end_time - timedelta(hours=5)
                start_time_180d = end_time - timedelta(days=180)
                
                logger.info(f"📥 Загрузка свечей для {symbol}...")
                
                candles_1m, candles_5m, candles_1h, candles_1d = await asyncio.gather(
                    self.repository.get_candles(symbol.upper(), "1m", start_time=start_time_1h, limit=60),
                    self.repository.get_candles(symbol.upper(), "5m", start_time=start_time_5h, limit=50),
                    self.repository.get_candles(symbol.upper(), "1h", start_time=start_time_24h, limit=24),
                    self.repository.get_candles(symbol.upper(), "1d", start_time=start_time_180d, limit=180)
                )
                
                logger.info(f"✅ Загружено свечей: 1m={len(candles_1m)}, 5m={len(candles_5m)}, "
                           f"1h={len(candles_1h)}, 1d={len(candles_1d)}")
                
                if not candles_1h or len(candles_1h) < 5:
                    await callback.message.edit_text(
                        f"❌ <b>Недостаточно данных для анализа {symbol}</b>\n\n"
                        f"В базе данных найдено {len(candles_1h) if candles_1h else 0} свечей.\n"
                        f"Для анализа требуется минимум 5 часовых свечей.\n\n"
                        f"Попробуйте позже или выберите другой символ.",
                        reply_markup=self._create_back_button(),
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                latest_candle = candles_1h[-1]
                first_candle_24h = candles_1h[0]
                
                current_price = float(latest_candle['close_price'])
                price_24h_ago = float(first_candle_24h['open_price'])
                price_change_24h = ((current_price - price_24h_ago) / price_24h_ago) * 100
                
                high_24h = max(float(c['high_price']) for c in candles_1h)
                low_24h = min(float(c['low_price']) for c in candles_1h)
                volume_24h = sum(float(c['volume']) for c in candles_1h)
                
                price_change_1m = 0
                price_change_5m = 0
                
                if candles_1m and len(candles_1m) >= 5:
                    latest_1m = candles_1m[-1]
                    candle_5m_ago = candles_1m[-6] if len(candles_1m) >= 6 else candles_1m[0]
                    candle_1m_ago = candles_1m[-2] if len(candles_1m) >= 2 else candles_1m[0]
                    
                    price_now = float(latest_1m['close_price'])
                    price_1m = float(candle_1m_ago['close_price'])
                    price_5m = float(candle_5m_ago['close_price'])
                    
                    if price_1m > 0:
                        price_change_1m = ((price_now - price_1m) / price_1m) * 100
                    if price_5m > 0:
                        price_change_5m = ((price_now - price_5m) / price_5m) * 100
                
                logger.info(f"💰 Цена: ${current_price:,.2f}, изменение 24ч: {price_change_24h:+.2f}%")
                
                context = None
                trend = "NEUTRAL"
                volatility = "MEDIUM"
                atr = 0.0
                key_levels = []
                
                if self.ta_context_manager:
                    try:
                        logger.info(f"🧠 Получение технического контекста для {symbol}...")
                        context = await self.ta_context_manager.get_context(symbol.upper())
                        
                        if context:
                            trend = context.dominant_trend_h1.value if context.dominant_trend_h1 else "NEUTRAL"
                            volatility = context.volatility_level or "MEDIUM"
                            
                            if context.atr_data:
                                atr = context.atr_data.calculated_atr
                            
                            if context.levels_d1:
                                for level in context.levels_d1[:5]:
                                    key_levels.append({
                                        'type': level.level_type,
                                        'price': level.price,
                                        'strength': level.strength
                                    })
                            
                            logger.info(f"✅ Технический контекст: trend={trend}, volatility={volatility}, "
                                       f"atr={atr:.2f}, levels={len(key_levels)}")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка получения технического контекста: {e}")
                
                logger.info(f"🎭 Запуск торговых стратегий для {symbol}...")
                
                strategies_opinions = []
                
                if len(candles_5m) >= 20 and len(candles_1d) >= 30:
                    from strategies import (
                        BreakoutStrategy,
                        BounceStrategy,
                        FalseBreakoutStrategy
                    )
                    
                    strategies = [
                        BreakoutStrategy(
                            symbol=symbol.upper(),
                            repository=self.repository,
                            ta_context_manager=self.ta_context_manager
                        ),
                        BounceStrategy(
                            symbol=symbol.upper(),
                            repository=self.repository,
                            ta_context_manager=self.ta_context_manager
                        ),
                        FalseBreakoutStrategy(
                            symbol=symbol.upper(),
                            repository=self.repository,
                            ta_context_manager=self.ta_context_manager
                        )
                    ]
                    
                    for strategy in strategies:
                        try:
                            logger.info(f"   🔄 Запуск {strategy.name}...")
                            
                            signal = await strategy.analyze_with_data(
                                symbol=symbol.upper(),
                                candles_1m=candles_1m,
                                candles_5m=candles_5m,
                                candles_1h=candles_1h,
                                candles_1d=candles_1d,
                                ta_context=context
                            )
                            
                            if signal:
                                signal_type = signal.signal_type.value
                                
                                if 'BUY' in signal_type:
                                    opinion = 'BULLISH'
                                elif 'SELL' in signal_type:
                                    opinion = 'BEARISH'
                                else:
                                    opinion = 'NEUTRAL'
                                
                                strategies_opinions.append({
                                    'name': strategy.name,
                                    'opinion': opinion,
                                    'confidence': signal.confidence,
                                    'reasoning': ', '.join(signal.reasons[:2])
                                })
                                
                                logger.info(f"   ✅ {strategy.name}: {opinion} (confidence={signal.confidence:.2f})")
                            else:
                                strategies_opinions.append({
                                    'name': strategy.name,
                                    'opinion': 'NEUTRAL',
                                    'confidence': 0.5,
                                    'reasoning': 'Условия для сигнала не выполнены'
                                })
                                
                                logger.info(f"   ℹ️  {strategy.name}: NEUTRAL (нет сигнала)")
                        
                        except Exception as e:
                            logger.error(f"   ❌ Ошибка в {strategy.name}: {e}")
                            strategies_opinions.append({
                                'name': strategy.name,
                                'opinion': 'NEUTRAL',
                                'confidence': 0.3,
                                'reasoning': f'Ошибка анализа: {str(e)[:50]}'
                            })
                    
                    logger.info(f"🎭 Завершен анализ стратегий: {len(strategies_opinions)} мнений")
                else:
                    logger.warning(f"⚠️ Недостаточно данных для запуска стратегий "
                                  f"(5m={len(candles_5m)}, 1d={len(candles_1d)})")
                
                analysis_data = {
                    'symbol': symbol,
                    'current_price': current_price,
                    'price_change_24h': price_change_24h,
                    'price_change_1m': price_change_1m,
                    'price_change_5m': price_change_5m,
                    'volume_24h': volume_24h,
                    'high_24h': high_24h,
                    'low_24h': low_24h,
                    'trend': trend,
                    'volatility': volatility,
                    'atr': atr,
                    'key_levels': key_levels,
                    'strategies_opinions': strategies_opinions
                }
                
                logger.info(f"🤖 Запрос комплексного AI анализа к OpenAI...")
                ai_analysis = await self.openai_analyzer.comprehensive_market_analysis(analysis_data)
                
                if not ai_analysis or len(ai_analysis) < 50:
                    logger.warning("⚠️ AI анализ пустой или слишком короткий, используем fallback")
                    ai_analysis = "❌ Не удалось получить детальный AI анализ. Попробуйте позже."
                else:
                    logger.info(f"✅ AI анализ получен ({len(ai_analysis)} символов)")
                
                ai_analysis_safe = self.escape_html(ai_analysis)
                
                strategies_text = ""
                if strategies_opinions:
                    strategies_text = "\n🎭 <b>Мнения торговых стратегий:</b>\n"
                    
                    for opinion in strategies_opinions:
                        emoji_opinion = {
                            'BULLISH': '🟢',
                            'BEARISH': '🔴',
                            'NEUTRAL': '🔶'
                        }.get(opinion['opinion'], '⚪')
                        
                        confidence_pct = opinion['confidence'] * 100
                        
                        strategy_name = self.escape_html(opinion['name'])
                        reasoning = self.escape_html(opinion['reasoning'])
                        
                        strategies_text += (
                            f"{emoji_opinion} <b>{strategy_name}</b>: {opinion['opinion']} "
                            f"({confidence_pct:.0f}%)\n"
                            f"   <i>{reasoning}</i>\n"
                        )
                
                message_text = f"""{emoji} <b>АНАЛИЗ {symbol}</b>

💰 <b>Текущая цена:</b> ${current_price:,.2f}

📊 <b>Изменения:</b>
- 1 минута: {price_change_1m:+.2f}%
- 5 минут: {price_change_5m:+.2f}%
- 24 часа: {price_change_24h:+.2f}%

📈 <b>Диапазон 24ч:</b>
- Максимум: ${high_24h:,.2f}
- Минимум: ${low_24h:,.2f}
- Объем: {volume_24h:,.0f}

🔧 <b>Технический анализ:</b>
- Тренд: {trend}
- Волатильность: {volatility}
- ATR: {atr:.2f}
{strategies_text}
🤖 <b>AI АНАЛИЗ:</b>

{ai_analysis_safe}

<i>Анализ основан на {len(candles_1h)} часовых свечах и мнениях {len(strategies_opinions)} стратегий</i>
"""
                
                keyboard = self._create_analysis_result_menu()
                
                await callback.message.edit_text(
                    message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
                
                logger.info(f"✅ Multi-Strategy анализ {symbol} отправлен пользователю {user_id}")
                
                if user_id in self.user_analysis_state:
                    del self.user_analysis_state[user_id]
                
            except Exception as e:
                logger.error(f"❌ Ошибка выполнения анализа {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
                await callback.message.edit_text(
                    f"❌ <b>Произошла ошибка при анализе {symbol}</b>\n\n"
                    f"Детали: {self.escape_html(str(e)[:100])}\n\n"
                    f"Попробуйте еще раз или выберите другой символ.",
                    reply_markup=self._create_back_button(),
                    parse_mode=ParseMode.HTML
                )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_request_analysis: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_cancel_analysis(self, callback: CallbackQuery):
        """Отмена анализа"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            
            if user_id in self.user_analysis_state:
                del self.user_analysis_state[user_id]
            
            await self.handle_back_to_menu(callback)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_cancel_analysis: {e}")
    
    async def handle_about(self, callback: CallbackQuery):
        """Обработка запроса информации о боте"""
        try:
            await callback.answer()
            
            # Обновляем взаимодействие
            await self.update_user_interaction(callback.from_user.id)
            
            # Получаем статистику
            stats = await self.get_all_users_stats()
            
            about_text = f"""ℹ️ <b>О боте</b>

🤖 <b>Bybit Trading Bot v3.2.1</b>
Multi-Strategy + AI + DB Storage Edition (Fixed)

📊 <b>Статистика пользователей:</b>
- Всего пользователей: {stats['total_users']}
- Активных: {stats['active_users']}
- Заблокированных: {stats['blocked_users']}
- Отправлено сигналов: {stats['total_signals_sent']}

<b>🏗️ Упрощенная архитектура:</b>
- 🔄 SimpleCandleSync - REST API синхронизация криптовалют
- 🔄 SimpleFuturesSync - YFinance синхронизация фьючерсов
- 📊 Repository - прямой доступ к данным
- 🧠 TechnicalAnalysisContextManager - технический анализ
- 🎭 StrategyOrchestrator - управление стратегиями
- 🎛️ SignalManager + AI - интеллектуальная фильтрация
- 💾 PostgreSQL User Storage - надежное хранение

<b>🆕 Multi-Strategy Analysis v3.2:</b>
- При анализе запускаются ВСЕ 3 стратегии
- OpenAI получает консенсус стратегий
- Более точный и обоснованный анализ
- Учет разных торговых подходов
- Хранение пользователей в БД

<b>Технологии:</b>
- 📈 Bybit REST API v5 для криптовалют
- 📊 Yahoo Finance для фьючерсов CME
- 🤖 OpenAI GPT-4 для AI анализа
- 🚀 Python aiogram для Telegram
- 💾 PostgreSQL для хранения данных
- ⚡ Асинхронная архитектура

<b>Надежность:</b>
- ✅ Отсутствие deadlock благодаря REST API
- ✅ Автоматическое восстановление
- ✅ Проверка и заполнение пропусков
- ✅ Health monitoring
- ✅ Graceful shutdown
- ✅ Сохранение пользователей в БД
- ✅ Исправлен доступ к БД (v3.2.1)

⚠️ <b>Дисклеймер:</b>
Все данные предоставляются исключительно в информационных целях и не являются инвестиционным советом."""
            
            keyboard = self._create_about_menu()
            
            await callback.message.edit_text(
                about_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_about: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    # ==================== BROADCAST ====================
    
    async def broadcast_signal(self, message: str):
        """
        ✅ Отправляет сигнал ВСЕМ активным пользователям
        + Обновляет статистику в БД
        """
        try:
            if not self.all_users:
                logger.info("📡 Нет пользователей для отправки сигнала")
                return
            
            sent_count = 0
            failed_count = 0
            blocked_users = []
            
            logger.info(f"📤 Отправка сигнала {len(self.all_users)} пользователям...")
            
            for user_id in self.all_users.copy():
                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode=ParseMode.HTML
                    )
                    sent_count += 1
                    
                    # ✅ Увеличиваем счетчик сигналов в БД
                    await self.increment_signals_count(user_id)
                    
                    await asyncio.sleep(0.05)
                    
                except Exception as e:
                    failed_count += 1
                    error_msg = str(e).lower()
                    
                    if any(phrase in error_msg for phrase in [
                        "bot was blocked by the user",
                        "user is deactivated", 
                        "chat not found"
                    ]):
                        blocked_users.append(user_id)
                        logger.info(f"🚫 Пользователь {user_id} заблокировал бота")
                        
                        # ✅ Помечаем в БД как заблокированного
                        await self.mark_user_blocked(user_id)
                    else:
                        logger.warning(f"⚠️ Не удалось отправить сигнал пользователю {user_id}: {e}")
            
            # Удаляем заблокированных из памяти
            for user_id in blocked_users:
                self.all_users.discard(user_id)
            
            if blocked_users:
                logger.info(f"🧹 Удалено {len(blocked_users)} заблокированных пользователей")
            
            logger.info(f"📨 Сигнал отправлен: ✅{sent_count} успешно, ❌{failed_count} ошибок. "
                       f"Осталось: {len(self.all_users)} активных")
            
        except Exception as e:
            logger.error(f"💥 Ошибка рассылки сигнала: {e}")
    
    # ==================== OTHER HANDLERS ====================
    
    async def handle_back_to_menu(self, callback: CallbackQuery):
        """Возврат в главное меню"""
        try:
            await callback.answer()
            
            keyboard = self._create_main_menu()
            
            welcome_text = """🤖 <b>Bybit Trading Bot v3.2.1</b>

Главное меню. Выберите действие:"""
            
            await callback.message.edit_text(
                welcome_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_back_to_menu: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_unknown_callback(self, callback: CallbackQuery):
        """Обработка неизвестных callback данных"""
        try:
            await callback.answer("❓ Неизвестная команда")
            logger.warning(f"⚠️ Неизвестный callback: {callback.data} от пользователя {callback.from_user.id}")
            
            await self.handle_back_to_menu(callback)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_unknown_callback: {e}")
    
    async def handle_text_message(self, message: Message):
        """Обработка обычных текстовых сообщений"""
        try:
            # Обновляем взаимодействие
            await self.update_user_interaction(message.from_user.id)
            
            user_text = message.text.lower()
            
            if any(word in user_text for word in ['привет', 'старт', 'начать', 'hello', 'hi']):
                await self.start_command(message)
            elif any(word in user_text for word in ['анализ', 'рынок', 'btc', 'биткоин', 'цена']):
                builder = InlineKeyboardBuilder()
                builder.add(InlineKeyboardButton(
                    text="📊 Анализ рынка с AI",
                    callback_data="market_analysis"
                ))
                
                await message.answer(
                    "📊 Хотите получить AI анализ рынка?\n"
                    "<i>Данные берутся из БД + 3 стратегии + OpenAI GPT-4</i>",
                    reply_markup=builder.as_markup(),
                    parse_mode=ParseMode.HTML
                )
            elif any(word in user_text for word in ['помощь', 'справка', 'help']):
                await self.help_command(message)
            else:
                response_text = """🤖 Я анализирую рынок криптовалют и фьючерсов, отправляю торговые сигналы с AI!

🆕 <b>Версия 3.2.1 - DB Storage Fixed</b>

При /start вы автоматически сохраняетесь в БД и получаете все сигналы!

Используйте кнопки меню или команды:
/start - главное меню
/help - справка

Или просто напишите:
- "анализ" для AI анализа рынка (+ 3 стратегии)
- "помощь" для подробной информации"""
                
                keyboard = self._create_main_menu()
                await message.answer(response_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_text_message: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте /start")
    
    # ==================== KEYBOARD BUILDERS ====================
    
    def _create_main_menu(self):
        """Создание главного меню"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="📊 Анализ рынка с ИИ", callback_data="market_analysis")
        )
        builder.add(
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")
        )
        builder.adjust(1)
        return builder.as_markup()
    
    def _create_analysis_menu(self):
        """Создание меню после анализа"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")
        )
        builder.add(
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu")
        )
        builder.adjust(1)
        return builder.as_markup()
    
    def _create_about_menu(self):
        """Создание меню в разделе О боте"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu")
        )
        builder.adjust(1)
        return builder.as_markup()
    
    def _create_asset_type_menu(self):
        """Создание меню выбора типа актива"""
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🪙 Криптовалюты", callback_data="select_crypto"))
        builder.add(InlineKeyboardButton(text="📊 Фьючерсы", callback_data="select_futures"))
        builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu"))
        builder.adjust(1)
        return builder.as_markup()
    
    def _create_symbol_selection_menu(self, symbols: List[str], asset_type: str):
        """Создание меню выбора символа"""
        builder = InlineKeyboardBuilder()
        
        for symbol in symbols:
            display_name = symbol
            if asset_type == "crypto":
                display_name = symbol.replace("USDT", "/USDT")
            
            builder.add(InlineKeyboardButton(
                text=display_name,
                callback_data=f"analyze_{symbol}"
            ))
        
        builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data="market_analysis"))
        
        builder.adjust(2, 2, 2, 2, 2, 1)
        
        return builder.as_markup()
    
    def _create_confirm_analysis_menu(self):
        """Создание меню подтверждения анализа"""
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🤖 Получить анализ", callback_data="request_analysis"))
        builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_analysis"))
        builder.adjust(1)
        return builder.as_markup()
    
    def _create_analysis_result_menu(self):
        """Создание меню после получения анализа"""
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🔄 Другой символ", callback_data="market_analysis"))
        builder.add(InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu"))
        builder.adjust(1)
        return builder.as_markup()
    
    def _create_back_button(self):
        """Простая кнопка назад"""
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu"))
        return builder.as_markup()
    
    # ==================== CLEANUP ====================
    
    async def close(self):
        """Корректное закрытие всех ресурсов бота"""
        try:
            logger.info("🔄 Закрытие Telegram бота...")
            
            if self.bot and self.bot.session:
                await self.bot.session.close()
                logger.info("✅ Telegram bot сессия закрыта")
                
            logger.info("🔴 Telegram бот корректно остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при закрытии бота: {e}")
