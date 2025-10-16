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
    """Telegram бот для анализа рынка на aiogram (webhook режим) - v3.1.1 с HTML"""
    
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
        
        logger.info("🤖 TelegramBot v3.1.1 инициализирован (Multi-Strategy + HTML)")
        logger.info(f"   • Repository: {'✅' if repository else '❌'}")
        logger.info(f"   • TA Context Manager: {'✅' if ta_context_manager else '❌'}")
        logger.info(f"   • OpenAI Analyzer: {'✅' if self.openai_analyzer else '❌'}")
    
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
            
            welcome_text = f"""🤖 <b>Bybit Trading Bot v3.1.1</b> 

Привет, {self.escape_html(user_name)}! 

✅ <b>Вы автоматически подписаны на торговые сигналы!</b>

📊 <b>Что я умею:</b>
- Синхронизация данных криптовалют (Bybit)
- 🆕 Синхронизация фьючерсов CME (YFinance)
- Сохранение исторических данных в PostgreSQL
- 🤖 AI анализ рынка через OpenAI GPT-4
- 🎭 Анализ через 3 торговые стратегии одновременно
- 🚨 Отправка торговых сигналов в реальном времени
- Модульная архитектура для надежности

🔥 <b>Активные компоненты v3.1:</b>
- SimpleCandleSync - синхронизация криптовалют
- SimpleFuturesSync - синхронизация фьючерсов
- Repository - прямой доступ к БД
- TechnicalAnalysisContextManager - технический анализ
- SignalManager - обработка с AI обогащением
- StrategyOrchestrator - управление стратегиями
- 🆕 Multi-Strategy Analysis - 3 стратегии параллельно

🎭 <b>Стратегии для анализа:</b>
- BreakoutStrategy - пробои уровней
- BounceStrategy - отбои от уровней
- FalseBreakoutStrategy - ложные пробои

🚀 <b>Символы в мониторинге:</b>
- Crypto: BTC, ETH, BNB, SOL, XRP, DOGE и др.
- Futures: MCL, MGC, MES, MNQ (CME micro)

🔔 <b>Уведомления:</b>
Вы будете получать все торговые сигналы с AI анализом!
<i>(Можете отписаться в меню "Торговые сигналы")</i>

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
            help_text = """📖 <b>Справка по боту</b>

🔧 <b>Доступные команды:</b>
/start - Запуск бота и автоподписка на сигналы
/help - Эта справка

📊 <b>Функции:</b>
- 🔄 Автоматическая синхронизация свечей
- 📈 Мониторинг криптовалют (15 пар)
- 🆕 Мониторинг фьючерсов CME (4 контракта)
- 💾 Сохранение в PostgreSQL
- 🤖 AI анализ через OpenAI GPT-4
- 🎭 Анализ через 3 торговые стратегии
- 🚨 Торговые сигналы в реальном времени

🆕 <b>Архитектура v3.1:</b>
- SimpleCandleSync - REST API синхронизация (крипта)
- SimpleFuturesSync - YFinance синхронизация (фьючерсы)
- Repository - прямой доступ к базе данных
- TechnicalAnalysisContextManager - технический анализ
- SignalManager - фильтрация + AI обогащение
- StrategyOrchestrator - управление стратегиями
- 🆕 Multi-Strategy Analysis - параллельный запуск
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

🔔 <b>Подписка на сигналы:</b>
При первом запуске /start вы автоматически подписываетесь на все сигналы.
Управлять подпиской можно в меню "Торговые сигналы".

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
    
    async def handle_market_analysis_start(self, callback: CallbackQuery):
        """Обработка запроса анализа рынка - выбор типа актива"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            user_name = callback.from_user.first_name or "пользователь"
            
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
        
        Алгоритм:
        1. Загрузка всех необходимых свечей (1m, 5m, 1h, 1d)
        2. Получение технического контекста
        3. 🆕 ЗАПУСК ВСЕХ СТРАТЕГИЙ
        4. Формирование analysis_data с мнениями стратегий
        5. Отправка в OpenAI для комплексного анализа
        6. Вывод результата пользователю
        """
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            user_name = callback.from_user.first_name or "пользователь"
            
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
                # ========== ШАГ 1: Получаем ВСЕ свечи из БД ==========
                end_time = datetime.now()
                start_time_24h = end_time - timedelta(hours=24)
                start_time_1h = end_time - timedelta(hours=1)
                start_time_5h = end_time - timedelta(hours=5)
                start_time_180d = end_time - timedelta(days=180)
                
                logger.info(f"📥 Загрузка свечей для {symbol}...")
                
                # Параллельная загрузка всех таймфреймов
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
                
                # ========== ШАГ 2: Рассчитываем базовые показатели ==========
                latest_candle = candles_1h[-1]
                first_candle_24h = candles_1h[0]
                
                current_price = float(latest_candle['close_price'])
                price_24h_ago = float(first_candle_24h['open_price'])
                price_change_24h = ((current_price - price_24h_ago) / price_24h_ago) * 100
                
                high_24h = max(float(c['high_price']) for c in candles_1h)
                low_24h = min(float(c['low_price']) for c in candles_1h)
                volume_24h = sum(float(c['volume']) for c in candles_1h)
                
                # Краткосрочные изменения
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
                
                # ========== ШАГ 3: Получаем технический контекст ==========
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
                            
                            # Извлекаем ключевые уровни
                            if context.levels_d1:
                                for level in context.levels_d1[:5]:  # Топ-5 уровней
                                    key_levels.append({
                                        'type': level.level_type,
                                        'price': level.price,
                                        'strength': level.strength
                                    })
                            
                            logger.info(f"✅ Технический контекст: trend={trend}, volatility={volatility}, "
                                       f"atr={atr:.2f}, levels={len(key_levels)}")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка получения технического контекста: {e}")
                
                # ========== ШАГ 4: 🆕 ЗАПУСК ВСЕХ СТРАТЕГИЙ ==========
                logger.info(f"🎭 Запуск торговых стратегий для {symbol}...")
                
                strategies_opinions = []
                
                # Проверяем что есть минимум данных для стратегий
                if len(candles_5m) >= 20 and len(candles_1d) >= 30:
                    # Импортируем стратегии
                    from strategies import (
                        BreakoutStrategy,
                        BounceStrategy,
                        FalseBreakoutStrategy
                    )
                    
                    # Создаем экземпляры стратегий
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
                    
                    # Запускаем каждую стратегию
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
                                # Стратегия нашла сигнал
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
                                    'reasoning': ', '.join(signal.reasons[:2])  # Первые 2 причины
                                })
                                
                                logger.info(f"   ✅ {strategy.name}: {opinion} (confidence={signal.confidence:.2f})")
                            else:
                                # Стратегия не нашла сигнал = нейтральна
                                strategies_opinions.append({
                                    'name': strategy.name,
                                    'opinion': 'NEUTRAL',
                                    'confidence': 0.5,
                                    'reasoning': 'Условия для сигнала не выполнены'
                                })
                                
                                logger.info(f"   ℹ️  {strategy.name}: NEUTRAL (нет сигнала)")
                        
                        except Exception as e:
                            logger.error(f"   ❌ Ошибка в {strategy.name}: {e}")
                            # Добавляем как нейтральную в случае ошибки
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
                
                # ========== ШАГ 5: Формируем данные для OpenAI ==========
                analysis_data = {
                    # Основные показатели
                    'symbol': symbol,
                    'current_price': current_price,
                    'price_change_24h': price_change_24h,
                    'price_change_1m': price_change_1m,
                    'price_change_5m': price_change_5m,
                    'volume_24h': volume_24h,
                    'high_24h': high_24h,
                    'low_24h': low_24h,
                    
                    # Технический анализ
                    'trend': trend,
                    'volatility': volatility,
                    'atr': atr,
                    'key_levels': key_levels,
                    
                    # 🆕 МНЕНИЯ СТРАТЕГИЙ
                    'strategies_opinions': strategies_opinions
                }
                
                logger.info(f"📊 Данные для AI подготовлены:")
                logger.info(f"   • Цена: ${current_price:,.2f}")
                logger.info(f"   • Изменение 24ч: {price_change_24h:+.2f}%")
                logger.info(f"   • Тренд: {trend}")
                logger.info(f"   • Ключевых уровней: {len(key_levels)}")
                logger.info(f"   • Мнений стратегий: {len(strategies_opinions)}")
                
                # ========== ШАГ 6: Получаем AI анализ ==========
                logger.info(f"🤖 Запрос комплексного AI анализа к OpenAI...")
                ai_analysis = await self.openai_analyzer.comprehensive_market_analysis(analysis_data)
                
                if not ai_analysis or len(ai_analysis) < 50:
                    logger.warning("⚠️ AI анализ пустой или слишком короткий, используем fallback")
                    ai_analysis = "❌ Не удалось получить детальный AI анализ. Попробуйте позже."
                else:
                    logger.info(f"✅ AI анализ получен ({len(ai_analysis)} символов)")
                
                # ========== ШАГ 7: Формируем сообщение ==========
                
                # ✅ Экранируем AI-анализ от потенциально опасных HTML-символов
                ai_analysis_safe = self.escape_html(ai_analysis)
                
                # Формируем секцию с мнениями стратегий
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
                        
                        # ✅ Экранируем данные от стратегий
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
            
            about_text = """ℹ️ <b>О боте</b>

🤖 <b>Bybit Trading Bot v3.1.1</b>
Multi-Strategy + AI Edition

<b>🏗️ Упрощенная архитектура:</b>
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

- 🎭 StrategyOrchestrator
  - Координация торговых стратегий
  - 🆕 BreakoutStrategy - пробои уровней
  - 🆕 BounceStrategy - отбои от уровней
  - 🆕 FalseBreakoutStrategy - ложные пробои
  - Параллельное выполнение анализа

- 🎛️ SignalManager + AI
  - Интеллектуальная фильтрация
  - Управление кулдаунами
  - Приоритизация сигналов
  - 🤖 AI обогащение каждого сигнала через OpenAI GPT-4

<b>🆕 Multi-Strategy Analysis v3.1:</b>
- При анализе запускаются ВСЕ 3 стратегии
- OpenAI получает консенсус стратегий
- Более точный и обоснованный анализ
- Учет разных торговых подходов

<b>Технологии:</b>
- 📈 Bybit REST API v5 для криптовалют
- 📊 Yahoo Finance для фьючерсов CME
- 🤖 OpenAI GPT-4 для AI анализа
- 🚀 Python aiogram для Telegram
- 💾 PostgreSQL для хранения данных
- ⚡ Асинхронная архитектура

<b>Мониторинг:</b>
- 15 криптовалютных пар (BTC, ETH, BNB, SOL...)
- 4 микро-фьючерса CME (MCL, MGC, MES, MNQ)
- 6 интервалов (1m, 5m, 15m, 1h, 4h, 1d)
- Автоматическая синхронизация 24/7
- 🤖 AI анализ рынка через OpenAI

<b>Надежность:</b>
- ✅ Отсутствие deadlock благодаря REST API
- ✅ Автоматическое восстановление
- ✅ Проверка и заполнение пропусков
- ✅ Health monitoring
- ✅ Graceful shutdown

<b>Особенности v3.1.1:</b>
- ✅ Прямой доступ к данным через Repository
- ✅ Упрощенная архитектура без лишних слоев
- ✅ AI анализ через OpenAI GPT-4
- ✅ Поддержка крипты + фьючерсов
- ✅ 🆕 Запуск всех 3 стратегий при анализе
- ✅ 🆕 HTML-форматирование для стабильности

<b>Режим работы:</b>
- 🔗 Webhook для мгновенных ответов
- 📡 REST API для исторических данных  
- ⚡ WebSocket ticker (опционально)
- ☁️ Развернуто на Render.com

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
    
    async def handle_signals_menu(self, callback: CallbackQuery):
        """Обработка меню торговых сигналов"""
        try:
            await callback.answer()
            
            user_id = callback.from_user.id
            is_subscribed = user_id in self.signal_subscribers
            
            status_text = "✅ Активна" if is_subscribed else "❌ Неактивна"
            subscribers_count = len(self.signal_subscribers)
            
            menu_text = f"""🚨 <b>Торговые сигналы v3.1.1</b>

📊 <b>Статус подписки:</b> {status_text}
👥 <b>Подписчиков:</b> {subscribers_count}

🏗️ <b>Архитектура сигналов:</b>
- SimpleCandleSync - актуальные данные криптовалют
- SimpleFuturesSync - актуальные данные фьючерсов
- Repository - прямой доступ к БД
- TechnicalAnalysisContextManager - технический анализ
- StrategyOrchestrator - управление стратегиями
- SignalManager - умная фильтрация
- 🤖 OpenAI GPT-4 - AI анализ каждого сигнала

🔥 <b>Особенности v3.1.1:</b>
- ✅ Автоподписка при /start
- REST API синхронизация без deadlock
- Параллельная обработка крипты и фьючерсов
- Анализ 15 криптопар + 4 фьючерса
- Детекция резких движений (&gt;2%)
- Интеллектуальная фильтрация дубликатов
- 🤖 AI обогащение каждого сигнала
- Управление частотой сигналов (кулдаун 5 минут)

⏱️ <b>Интервалы и фильтры:</b>
- Анализ каждые 60 секунд
- Мгновенные экстремальные сигналы (&gt;2%)
- Кулдаун между сигналами: 5 минут
- Минимальная сила сигнала: 0.5
- Максимум 12 сигналов в час

🎯 <b>Типы сигналов:</b>
- 🟢 BUY / STRONG_BUY - сигналы на покупку
- 🔴 SELL / STRONG_SELL - сигналы на продажу
- Сила сигнала: 0.5 - 1.0
- Уровень уверенности: LOW/MEDIUM/HIGH
- 🤖 AI анализ с рыночным контекстом

📈 <b>Источники данных:</b>
- Bybit REST API - криптовалюты
- Yahoo Finance - CME фьючерсы
- PostgreSQL - исторические данные
- OpenAI GPT-4 - AI анализ

⚠️ <b>ВНИМАНИЕ:</b> Торговые сигналы несут высокие риски! Это не инвестиционный совет!"""
            
            keyboard = self._create_signals_menu(is_subscribed)
            
            await callback.message.edit_text(
                menu_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
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
                "✅ <b>Подписка активирована!</b>\n\n"
                "Теперь вы будете получать торговые сигналы от системы v3.1.1.\n\n"
                "🏗️ <b>Сигналы генерируются через:</b>\n"
                "• SimpleCandleSync - синхронизация криптовалют\n"
                "• SimpleFuturesSync - синхронизация фьючерсов\n"
                "• Repository - прямой доступ к БД\n"
                "• TechnicalAnalysisContextManager - технический анализ\n"
                "• StrategyOrchestrator - координация стратегий\n"
                "• SignalManager - фильтрация и обработка\n"
                "• 🤖 OpenAI GPT-4 - AI анализ каждого сигнала\n\n"
                "🔥 <b>Основа сигналов:</b>\n"
                "• REST API синхронизация без блокировок\n"
                "• Анализ 15 криптопар + 4 фьючерса\n"
                "• Движения цены за 1m, 5m, 15m, 1h\n"
                "• Объемный анализ торгов\n"
                "• Детекция экстремальных движений\n"
                "• 🤖 AI контекстный анализ от OpenAI\n\n"
                "📱 <b>Уведомления:</b>\n"
                "• При сильных сигналах (сила ≥0.5)\n"
                "• Максимум 1 сигнал типа в 5 минут\n"
                "• Умная фильтрация дубликатов\n"
                "• AI обогащение каждого сигнала\n"
                "• В любое время суток\n\n"
                "⚠️ <b>Важно:</b> Торговые сигналы несут высокие риски!\n"
                "<i>Это не инвестиционный совет!</i>",
                reply_markup=self._create_signals_menu(True),
                parse_mode=ParseMode.HTML
            )
            
            logger.info(f"📡 Пользователь {user_name} ({user_id}) подписался на сигналы v3.1.1")
            
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
                "🔕 <b>Подписка отключена</b>\n\n"
                "Вы больше не будете получать торговые сигналы.\n\n"
                "Вы можете снова подписаться в любое время через меню сигналов или выполнив /start.\n\n"
                "Спасибо за использование наших сигналов! 🙏",
                reply_markup=self._create_signals_menu(False),
                parse_mode=ParseMode.HTML
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
                        parse_mode=ParseMode.HTML
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
            
            welcome_text = """🤖 <b>Bybit Trading Bot v3.1.1</b>

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
            elif any(word in user_text for word in ['сигнал', 'сигналы', 'уведомления', 'подписка']):
                builder = InlineKeyboardBuilder()
                builder.add(InlineKeyboardButton(
                    text="🚨 Торговые сигналы",
                    callback_data="signals_menu"
                ))
                
                await message.answer(
                    "🚨 Хотите настроить торговые сигналы?\n"
                    "<i>Сигналы генерируются через StrategyOrchestrator v3.1.1 с AI</i>",
                    reply_markup=builder.as_markup(),
                    parse_mode=ParseMode.HTML
                )
            elif any(word in user_text for word in ['помощь', 'справка', 'help']):
                await self.help_command(message)
            else:
                response_text = """🤖 Я анализирую рынок криптовалют и фьючерсов, отправляю торговые сигналы с AI!

🆕 <b>Версия 3.1.1 - Multi-Strategy + AI Edition</b>

При /start вы автоматически подписываетесь на сигналы!

Используйте кнопки меню или команды:
/start - главное меню и автоподписка
/help - справка

Или просто напишите:
- "анализ" для AI анализа рынка (+ 3 стратегии)
- "сигналы" для настройки уведомлений
- "помощь" для подробной информации"""
                
                keyboard = self._create_main_menu()
                await message.answer(response_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                
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
