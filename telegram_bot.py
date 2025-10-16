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

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram бот для анализа рынка на aiogram (webhook режим) - v3.0"""
    
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
        
        self.signal_subscribers: Set[int] = set()
        
        self.user_analysis_state: Dict[int, Dict[str, Any]] = {}
        
        self._register_handlers()
        
        self.dp.include_router(self.router)
        
        logger.info("🤖 TelegramBot v3.0 инициализирован")
        logger.info(f"   • Repository: {'✅' if repository else '❌'}")
        logger.info(f"   • TA Context Manager: {'✅' if ta_context_manager else '❌'}")
        logger.info(f"   • OpenAI Analyzer: {'✅' if self.openai_analyzer else '❌'}")
    
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
        
        self.router.callback_query.register(self.handle_unknown_callback)
        
        self.router.message.register(self.handle_text_message, F.text)
        
        logger.info("✅ Все обработчики зарегистрированы")
    
    async def start_command(self, message: Message):
        """Обработчик команды /start с АВТОМАТИЧЕСКОЙ подпиской"""
        try:
            user_name = message.from_user.first_name or "друг"
            user_id = message.from_user.id
            
            self.signal_subscribers.add(user_id)
            
            logger.info(f"👤 Пользователь: {user_name} (ID: {user_id}) ✅ АВТОМАТИЧЕСКИ ПОДПИСАН")
            
            keyboard = self._create_main_menu()
            
            welcome_text = f"""🤖 *Bybit Trading Bot v3.0* 

Привет, {user_name}! 

✅ *Вы автоматически подписаны на торговые сигналы!*

📊 *Что я умею:*
- Синхронизация данных криптовалют (Bybit)
- 🆕 Синхронизация фьючерсов CME (YFinance)
- Сохранение исторических данных в PostgreSQL
- 🤖 AI анализ рынка через OpenAI GPT-4
- 🚨 Отправка торговых сигналов в реальном времени
- Модульная архитектура для надежности

🔥 *Активные компоненты v3.0:*
- SimpleCandleSync - синхронизация криптовалют
- SimpleFuturesSync - синхронизация фьючерсов
- Repository - прямой доступ к БД
- TechnicalAnalysisContextManager - технический анализ
- SignalManager - обработка с AI обогащением
- StrategyOrchestrator - управление стратегиями

🚀 *Символы в мониторинге:*
- Crypto: BTC, ETH, BNB, SOL, XRP, DOGE и др.
- Futures: MCL, MGC, MES, MNQ (CME micro)

🔔 *Уведомления:*
Вы будете получать все торговые сигналы с AI анализом!
_(Можете отписаться в меню "Торговые сигналы")_

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
/start - Запуск бота и автоподписка на сигналы
/help - Эта справка

📊 *Функции:*
- 🔄 Автоматическая синхронизация свечей
- 📈 Мониторинг криптовалют (15 пар)
- 🆕 Мониторинг фьючерсов CME (4 контракта)
- 💾 Сохранение в PostgreSQL
- 🤖 AI анализ через OpenAI GPT-4
- 🚨 Торговые сигналы в реальном времени

🆕 *Архитектура v3.0:*
- SimpleCandleSync - REST API синхронизация (крипта)
- SimpleFuturesSync - YFinance синхронизация (фьючерсы)
- Repository - прямой доступ к базе данных
- TechnicalAnalysisContextManager - технический анализ
- SignalManager - фильтрация + AI обогащение
- StrategyOrchestrator - управление стратегиями
- OpenAI GPT-4 - AI анализ рынка

🚨 *Торговые сигналы:*
- Мониторинг в реальном времени
- Анализ импульсных движений цены
- Детекция резких изменений (>2% за минуту)
- Анализ ордербука и объемов
- Интеллектуальная фильтрация сигналов
- 🤖 AI обогащение каждого сигнала
- Кулдаун между сигналами (5 минут)

🔔 *Подписка на сигналы:*
При первом запуске /start вы автоматически подписываетесь на все сигналы.
Управлять подпиской можно в меню "Торговые сигналы".

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
    
    async def handle_market_analysis_start(self, callback: CallbackQuery):
        """Обработка запроса анализа рынка - выбор типа актива"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            user_name = callback.from_user.first_name or "пользователь"
            
            logger.info(f"📊 {user_name} ({user_id}) запросил анализ рынка")
            
            if not self.repository or not self.openai_analyzer:
                await callback.message.edit_text(
                    "❌ **Анализ рынка временно недоступен**\n\n"
                    "Система анализа не инициализирована.\n"
                    "Обратитесь к администратору.",
                    reply_markup=self._create_back_button(),
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            self.user_analysis_state[user_id] = {}
            
            text = """📊 **АНАЛИЗ РЫНКА С ИИ**

🤖 Выберите тип актива для анализа:

**🪙 Криптовалюты** - Bybit spot pairs
- BTC, ETH, BNB, SOL, XRP, DOGE, ADA и др.
- Анализ текущей ситуации
- Технический анализ
- AI прогноз на 1-3 дня

**📊 Фьючерсы** - CME micro futures
- MCL (нефть), MGC (золото)
- MES (S&P 500), MNQ (Nasdaq)
- Комплексный технический анализ
- AI оценка перспектив

Нажмите кнопку ниже для выбора ⬇️"""
            
            keyboard = self._create_asset_type_menu()
            
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
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
            
            text = """🪙 **ВЫБЕРИТЕ КРИПТОВАЛЮТУ**

Доступные пары для анализа:"""
            
            keyboard = self._create_symbol_selection_menu(crypto_symbols, "crypto")
            
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
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
                    "⚠️ **Фьючерсы недоступны**\n\n"
                    "Список фьючерсов не настроен в конфигурации.",
                    reply_markup=self._create_back_button(),
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            text = """📊 **ВЫБЕРИТЕ ФЬЮЧЕРС**

Доступные контракты для анализа:

- **MCL** - Micro WTI Crude Oil
- **MGC** - Micro Gold
- **MES** - Micro E-mini S&P 500
- **MNQ** - Micro E-mini Nasdaq-100"""
            
            keyboard = self._create_symbol_selection_menu(futures_symbols, "futures")
            
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
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
            
            text = f"""{emoji} **АНАЛИЗ {symbol}**

Вы выбрали: **{symbol}**

📊 **Что будет проанализировано:**
- Текущая цена и изменения
- Технический анализ (уровни, ATR, тренд)
- Данные из базы за последние 24 часа
- 🤖 AI прогноз от OpenAI GPT-4

⏱️ Анализ займет 5-10 секунд.

Нажмите кнопку для запуска анализа ⬇️"""
            
            keyboard = self._create_confirm_analysis_menu()
            
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_symbol_selection: {e}")
            await callback.answer("❌ Произошла ошибка")
    
    async def handle_request_analysis(self, callback: CallbackQuery):
        """Обработка запроса анализа - выполняем анализ через Repository + OpenAI"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            user_name = callback.from_user.first_name or "пользователь"
            
            if user_id not in self.user_analysis_state:
                await callback.message.edit_text(
                    "❌ Сессия истекла. Начните заново.",
                    reply_markup=self._create_back_button(),
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            symbol = self.user_analysis_state[user_id].get("symbol")
            asset_type = self.user_analysis_state[user_id].get("asset_type", "crypto")
            
            if not symbol:
                await callback.message.edit_text(
                    "❌ Символ не выбран. Начните заново.",
                    reply_markup=self._create_back_button(),
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            emoji = "🪙" if asset_type == "crypto" else "📊"
            await callback.message.edit_text(
                f"{emoji} **АНАЛИЗ {symbol}**\n\n"
                f"⏳ Собираю данные из БД...\n"
                f"📊 Получаю технический анализ...\n"
                f"🤖 Запрашиваю AI анализ...\n\n"
                f"_Пожалуйста, подождите 5-10 секунд..._",
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"🔬 {user_name} ({user_id}) запустил анализ {symbol}")
            
            try:
                # ========== ШАГ 1: Получаем последние свечи из БД ==========
                end_time = datetime.now()
                start_time_24h = end_time - timedelta(hours=24)
                start_time_1h = end_time - timedelta(hours=1)
                
                # Получаем часовые свечи за 24ч
                candles_1h = await self.repository.get_candles(
                    symbol=symbol.upper(),
                    interval="1h",
                    start_time=start_time_24h,
                    end_time=end_time,
                    limit=24
                )
                
                # Получаем минутные свечи за последний час
                candles_1m = await self.repository.get_candles(
                    symbol=symbol.upper(),
                    interval="1m",
                    start_time=start_time_1h,
                    end_time=end_time,
                    limit=60
                )
                
                if not candles_1h or len(candles_1h) < 5:
                    await callback.message.edit_text(
                        f"❌ **Недостаточно данных для анализа {symbol}**\n\n"
                        f"В базе данных найдено {len(candles_1h) if candles_1h else 0} свечей.\n"
                        f"Для анализа требуется минимум 5 часовых свечей.\n\n"
                        f"Попробуйте позже или выберите другой символ.",
                        reply_markup=self._create_back_button(),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
                # ========== ШАГ 2: Рассчитываем базовые показатели ==========
                latest_candle = candles_1h[-1]
                first_candle_24h = candles_1h[0]
                
                # ✅ ИСПРАВЛЕНО: Используем правильные ключи с суффиксом _price
                current_price = float(latest_candle['close_price'])
                price_24h_ago = float(first_candle_24h['open_price'])
                price_change_24h = ((current_price - price_24h_ago) / price_24h_ago) * 100
                
                high_24h = max(float(c['high_price']) for c in candles_1h)
                low_24h = min(float(c['low_price']) for c in candles_1h)
                volume_24h = sum(float(c['volume']) for c in candles_1h)
                
                # Краткосрочные изменения (если есть минутные данные)
                price_change_1m = 0
                price_change_5m = 0
                
                if candles_1m and len(candles_1m) >= 5:
                    latest_1m = candles_1m[-1]
                    candle_5m_ago = candles_1m[-6] if len(candles_1m) >= 6 else candles_1m[0]
                    candle_1m_ago = candles_1m[-2] if len(candles_1m) >= 2 else candles_1m[0]
                    
                    # ✅ ИСПРАВЛЕНО: Используем правильные ключи
                    price_now = float(latest_1m['close_price'])
                    price_1m = float(candle_1m_ago['close_price'])
                    price_5m = float(candle_5m_ago['close_price'])
                    
                    if price_1m > 0:
                        price_change_1m = ((price_now - price_1m) / price_1m) * 100
                    if price_5m > 0:
                        price_change_5m = ((price_now - price_5m) / price_5m) * 100
                
                # ========== ШАГ 3: Получаем технический анализ (опционально) ==========
                trend = "NEUTRAL"
                volatility = "MEDIUM"
                atr = 0.0
                key_levels = []
                
                if self.ta_context_manager:
                    try:
                        context = await self.ta_context_manager.get_context(
                            symbol=symbol.upper(),
                            interval="1h"
                        )
                        
                        if context:
                            trend = context.trend or "NEUTRAL"
                            volatility = context.volatility or "MEDIUM"
                            atr = context.atr or 0.0
                            
                            # Извлекаем ключевые уровни
                            if hasattr(context, 'support_levels') and context.support_levels:
                                for level in context.support_levels[:3]:
                                    key_levels.append({
                                        'type': 'support',
                                        'price': level
                                    })
                            
                            if hasattr(context, 'resistance_levels') and context.resistance_levels:
                                for level in context.resistance_levels[:3]:
                                    key_levels.append({
                                        'type': 'resistance',
                                        'price': level
                                    })
                            
                            logger.info(f"✅ Получен технический анализ: trend={trend}, volatility={volatility}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось получить технический анализ: {e}")
                else:
                    logger.info("ℹ️ TechnicalAnalysisContextManager не доступен")
                
                # ========== ШАГ 4: Формируем данные для OpenAI ==========
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
                    'strategies_opinions': []  # Можно добавить если есть
                }
                
                logger.info(f"📊 Данные для анализа подготовлены:")
                logger.info(f"   • Цена: ${current_price:,.2f}")
                logger.info(f"   • Изменение 24ч: {price_change_24h:+.2f}%")
                logger.info(f"   • Свечей 1h: {len(candles_1h)}")
                logger.info(f"   • Свечей 1m: {len(candles_1m)}")
                logger.info(f"   • Тренд: {trend}")
                logger.info(f"   • Ключевых уровней: {len(key_levels)}")
                
                # ========== ШАГ 5: Получаем AI анализ ==========
                logger.info("🤖 Запрос AI анализа к OpenAI...")
                ai_analysis = await self.openai_analyzer.comprehensive_market_analysis(analysis_data)
                
                if not ai_analysis or len(ai_analysis) < 50:
                    logger.warning("⚠️ AI анализ пустой или слишком короткий, используем fallback")
                    ai_analysis = "❌ Не удалось получить детальный AI анализ. Попробуйте позже."
                else:
                    logger.info(f"✅ AI анализ получен ({len(ai_analysis)} символов)")
                
                # ========== ШАГ 6: Формируем сообщение ==========
                message_text = f"""{emoji} **АНАЛИЗ {symbol}**

💰 **Текущая цена:** ${current_price:,.2f}

📊 **Изменения:**
- 1 минута: {price_change_1m:+.2f}%
- 5 минут: {price_change_5m:+.2f}%
- 24 часа: {price_change_24h:+.2f}%

📈 **Диапазон 24ч:**
- Максимум: ${high_24h:,.2f}
- Минимум: ${low_24h:,.2f}
- Объем: {volume_24h:,.0f}

🔧 **Технический анализ:**
- Тренд: {trend}
- Волатильность: {volatility}
- ATR: {atr:.2f}

🤖 **AI АНАЛИЗ:**

{ai_analysis}

_Анализ основан на {len(candles_1h)} часовых свечах из базы данных_
"""
                
                keyboard = self._create_analysis_result_menu()
                
                await callback.message.edit_text(
                    message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                logger.info(f"✅ Анализ {symbol} отправлен пользователю {user_id}")
                
                if user_id in self.user_analysis_state:
                    del self.user_analysis_state[user_id]
                
            except Exception as e:
                logger.error(f"❌ Ошибка выполнения анализа {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
                await callback.message.edit_text(
                    f"❌ **Произошла ошибка при анализе {symbol}**\n\n"
                    f"Детали: {str(e)[:100]}\n\n"
                    f"Попробуйте еще раз или выберите другой символ.",
                    reply_markup=self._create_back_button(),
                    parse_mode=ParseMode.MARKDOWN
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
            
            about_text = """ℹ️ *О боте*

🤖 *Bybit Trading Bot v3.0*
Direct Repository + AI Edition

*🏗️ Упрощенная архитектура:*
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

- 📊 Repository - прямой доступ к данным
  - Быстрые запросы к PostgreSQL
  - Оптимизированные индексы
  - Поддержка агрегации данных

- 🧠 TechnicalAnalysisContextManager - технический анализ
  - Автоматический расчет индикаторов
  - Определение трендов и уровней
  - Кэширование результатов

- 📊 MarketDataManager (опционально)
  - WebSocket ticker для real-time цен
  - Кэширование REST API запросов
  - Переподключение при разрыве

- 🎭 StrategyOrchestrator
  - Координация торговых стратегий
  - MomentumStrategy для импульсов
  - Параллельное выполнение анализа

- 🎛️ SignalManager + AI
  - Интеллектуальная фильтрация
  - Управление кулдаунами
  - Приоритизация сигналов
  - 🤖 AI обогащение каждого сигнала через OpenAI GPT-4

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
- 🤖 AI анализ рынка через OpenAI

*Надежность:*
- ✅ Отсутствие deadlock благодаря REST API
- ✅ Автоматическое восстановление
- ✅ Проверка и заполнение пропусков
- ✅ Health monitoring
- ✅ Graceful shutdown

*Особенности v3.0:*
- ✅ Прямой доступ к данным через Repository
- ✅ Упрощенная архитектура без лишних слоев
- ✅ AI анализ через OpenAI GPT-4
- ✅ Поддержка крипты + фьючерсов

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
            
            menu_text = f"""🚨 *Торговые сигналы v3.0*

📊 *Статус подписки:* {status_text}
👥 *Подписчиков:* {subscribers_count}

🏗️ *Архитектура сигналов:*
- SimpleCandleSync - актуальные данные криптовалют
- SimpleFuturesSync - актуальные данные фьючерсов
- Repository - прямой доступ к БД
- TechnicalAnalysisContextManager - технический анализ
- MarketDataManager - real-time WebSocket ticker
- StrategyOrchestrator - управление стратегиями
- SignalManager - умная фильтрация
- 🤖 OpenAI GPT-4 - AI анализ каждого сигнала
- MomentumStrategy - импульсная торговля

🔥 *Особенности v3.0:*
- ✅ Автоподписка при /start
- REST API синхронизация без deadlock
- Параллельная обработка крипты и фьючерсов
- Анализ 15 криптопар + 4 фьючерса
- Детекция резких движений (>2%)
- Интеллектуальная фильтрация дубликатов
- 🤖 AI обогащение каждого сигнала
- Управление частотой сигналов (кулдаун 5 минут)

⏱️ *Интервалы и фильтры:*
- Анализ каждые 60 секунд
- Мгновенные экстремальные сигналы (>2%)
- Кулдаун между сигналами: 5 минут
- Минимальная сила сигнала: 0.5
- Максимум 12 сигналов в час

🎯 *Типы сигналов:*
- 🟢 BUY / STRONG_BUY - сигналы на покупку
- 🔴 SELL / STRONG_SELL - сигналы на продажу
- Сила сигнала: 0.5 - 1.0
- Уровень уверенности: LOW/MEDIUM/HIGH
- 🤖 AI анализ с рыночным контекстом

📈 *Источники данных:*
- Bybit REST API - криптовалюты
- Yahoo Finance - CME фьючерсы
- PostgreSQL - исторические данные
- WebSocket - real-time цены (опционально)
- OpenAI GPT-4 - AI анализ

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
                "Теперь вы будете получать торговые сигналы от системы v3.0.\n\n"
                "🏗️ *Сигналы генерируются через:*\n"
                "• SimpleCandleSync - синхронизация криптовалют\n"
                "• SimpleFuturesSync - синхронизация фьючерсов\n"
                "• Repository - прямой доступ к БД\n"
                "• TechnicalAnalysisContextManager - технический анализ\n"
                "• MarketDataManager - real-time данные\n"
                "• StrategyOrchestrator - координация стратегий\n"
                "• SignalManager - фильтрация и обработка\n"
                "• 🤖 OpenAI GPT-4 - AI анализ каждого сигнала\n"
                "• MomentumStrategy - импульсная стратегия\n\n"
                "🔥 *Основа сигналов:*\n"
                "• REST API синхронизация без блокировок\n"
                "• Анализ 15 криптопар + 4 фьючерса\n"
                "• Движения цены за 1m, 5m, 15m, 1h\n"
                "• Мониторинг WebSocket ticker\n"
                "• Объемный анализ торгов\n"
                "• Детекция экстремальных движений\n"
                "• 🤖 AI контекстный анализ от OpenAI\n\n"
                "📱 *Уведомления:*\n"
                "• При сильных сигналах (сила ≥0.5)\n"
                "• Максимум 1 сигнал типа в 5 минут\n"
                "• Умная фильтрация дубликатов\n"
                "• AI обогащение каждого сигнала\n"
                "• В любое время суток\n\n"
                "⚠️ *Важно:* Торговые сигналы несут высокие риски!\n"
                "_Это не инвестиционный совет!_",
                reply_markup=self._create_signals_menu(True),
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"📡 Пользователь {user_name} ({user_id}) подписался на сигналы v3.0")
            
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
                "Вы можете снова подписаться в любое время через меню сигналов или выполнив /start.\n\n"
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
            
            for user_id in self.signal_subscribers.copy():
                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    sent_count += 1
                    
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
                        logger.info(f"🚫 Пользователь {user_id} заблокировал бота или удалил чат")
                    else:
                        logger.warning(f"⚠️ Не удалось отправить сигнал пользователю {user_id}: {e}")
            
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
            
            welcome_text = """🤖 *Bybit Trading Bot v3.0*

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
            
            await self.handle_back_to_menu(callback)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_unknown_callback: {e}")
    
    async def handle_text_message(self, message: Message):
        """Обработка обычных текстовых сообщений"""
        try:
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
                    "_Данные берутся из БД + OpenAI GPT-4_",
                    reply_markup=builder.as_markup(),
                    parse_mode=ParseMode.MARKDOWN
                )
            elif any(word in user_text for word in ['сигнал', 'сигналы', 'уведомления', 'подписка']):
                builder = InlineKeyboardBuilder()
                builder.add(InlineKeyboardButton(
                    text="🚨 Торговые сигналы",
                    callback_data="signals_menu"
                ))
                
                await message.answer(
                    "🚨 Хотите настроить торговые сигналы?\n"
                    "_Сигналы генерируются через StrategyOrchestrator v3.0 с AI_",
                    reply_markup=builder.as_markup(),
                    parse_mode=ParseMode.MARKDOWN
                )
            elif any(word in user_text for word in ['помощь', 'справка', 'help']):
                await self.help_command(message)
            else:
                response_text = """🤖 Я анализирую рынок криптовалют и фьючерсов, отправляю торговые сигналы с AI!

🆕 *Версия 3.0 - Direct Repository + AI Edition*

При /start вы автоматически подписываетесь на сигналы!

Используйте кнопки меню или команды:
/start - главное меню и автоподписка
/help - справка

Или просто напишите:
- "анализ" для AI анализа рынка
- "сигналы" для настройки уведомлений
- "помощь" для подробной информации"""
                
                keyboard = self._create_main_menu()
                await message.answer(response_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
                
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_text_message: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте /start")
    
    def _create_main_menu(self):
        """Создание главного меню"""
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="📊 Анализ рынка с ИИ", callback_data="market_analysis")
        )
        builder.add(
            InlineKeyboardButton(text="🚨 Торговые сигналы", callback_data="signals_menu")
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
    
    def _create_about_menu(self):
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
    
    def _create_signals_menu(self, is_subscribed: bool):
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
        builder.add(InlineKeyboardButton(text="🚨 Торговые сигналы", callback_data="signals_menu"))
        builder.add(InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu"))
        builder.adjust(1)
        return builder.as_markup()
    
    def _create_back_button(self):
        """Простая кнопка назад"""
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu"))
        return builder.as_markup()
    
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
