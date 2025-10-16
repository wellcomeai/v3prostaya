"""
Market Analyzer - Модуль для комплексного анализа рынка

Объединяет данные из:
- DataSourceAdapter (рыночные данные)
- TechnicalAnalysisContextManager (технический анализ)
- StrategyOrchestrator (мнения стратегий)
- OpenAI (AI анализ)

Version: 1.0.0
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StrategyOpinion:
    """Мнение одной стратегии"""
    strategy_name: str
    opinion: str  # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float  # 0.0 - 1.0
    reasoning: str
    signal_strength: float  # 0.0 - 1.0
    key_points: List[str] = field(default_factory=list)


@dataclass
class MarketAnalysisReport:
    """Полный отчет анализа рынка"""
    symbol: str
    timestamp: datetime
    
    # Рыночные данные
    current_price: float
    price_change_24h: float
    volume_24h: float
    high_24h: float
    low_24h: float
    
    # Технический анализ
    key_levels: List[Dict[str, Any]]
    atr_value: float
    volatility: str  # "LOW", "MEDIUM", "HIGH"
    trend: str  # "BULLISH", "BEARISH", "NEUTRAL"
    
    # Мнения стратегий
    strategies_opinions: Dict[str, StrategyOpinion]
    
    # AI анализ
    ai_analysis: str
    
    # Общий вердикт
    overall_sentiment: str  # "BULLISH", "BEARISH", "NEUTRAL", "MIXED"
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    
    def to_telegram_message(self) -> str:
        """Форматирует отчет для Telegram"""
        # Эмодзи для тренда
        trend_emoji = {
            "BULLISH": "🟢",
            "BEARISH": "🔴",
            "NEUTRAL": "🔶",
            "MIXED": "⚪"
        }
        
        message = f"""📊 **АНАЛИЗ РЫНКА {self.symbol}**

💰 **Текущая цена:** ${self.current_price:,.2f}
📈 **Изменение 24ч:** {self.price_change_24h:+.2f}%
📊 **Объем 24ч:** {self.volume_24h:,.0f}
📉 **Диапазон:** ${self.low_24h:,.2f} - ${self.high_24h:,.2f}

🔍 **ТЕХНИЧЕСКИЙ АНАЛИЗ**
• Тренд: {trend_emoji.get(self.trend, '🔶')} {self.trend}
• Волатильность: {self.volatility}
• ATR: {self.atr_value:.2f}

🎯 **КЛЮЧЕВЫЕ УРОВНИ:**"""
        
        # Добавляем уровни
        for level in self.key_levels[:3]:  # Максимум 3 уровня
            message += f"\n• {level['type']}: ${level['price']:,.2f}"
        
        message += "\n\n🤖 **МНЕНИЯ СТРАТЕГИЙ:**\n"
        
        # Добавляем мнения стратегий
        for strategy_name, opinion in self.strategies_opinions.items():
            emoji = {
                "BULLISH": "🟢",
                "BEARISH": "🔴",
                "NEUTRAL": "🔶"
            }.get(opinion.opinion, "🔶")
            
            message += f"\n{emoji} **{strategy_name}**"
            message += f"\n   Мнение: {opinion.opinion}"
            message += f"\n   Уверенность: {opinion.confidence:.0%}"
            message += f"\n   {opinion.reasoning}\n"
        
        message += f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"\n🤖 **AI АНАЛИЗ**\n\n{self.ai_analysis}"
        message += f"\n\n━━━━━━━━━━━━━━━━━━━━━━"
        message += f"\n\n📌 **ОБЩИЙ ВЕРДИКТ**"
        message += f"\n• Настроение: {trend_emoji.get(self.overall_sentiment, '🔶')} {self.overall_sentiment}"
        message += f"\n• Уровень риска: {self.risk_level}"
        message += f"\n\n⚠️ _Это аналитическая информация, а не инвестиционный совет!_"
        message += f"\n📅 {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        
        return message


class MarketAnalyzer:
    """
    Комплексный анализатор рынка
    
    Объединяет данные из всех источников для создания полного анализа
    """
    
    def __init__(
        self,
        data_source_adapter,
        ta_context_manager,
        openai_analyzer,
        strategy_orchestrator
    ):
        """
        Args:
            data_source_adapter: DataSourceAdapter для получения рыночных данных
            ta_context_manager: TechnicalAnalysisContextManager для TA
            openai_analyzer: OpenAIAnalyzer для AI анализа
            strategy_orchestrator: StrategyOrchestrator для мнений стратегий
        """
        self.data_source_adapter = data_source_adapter
        self.ta_context_manager = ta_context_manager
        self.openai_analyzer = openai_analyzer
        self.strategy_orchestrator = strategy_orchestrator
        
        # Статистика
        self.stats = {
            "analyses_completed": 0,
            "analyses_failed": 0,
            "last_analysis_time": None
        }
        
        logger.info("🔬 MarketAnalyzer инициализирован")
    
    async def analyze_symbol(self, symbol: str) -> Optional[MarketAnalysisReport]:
        """
        Выполняет комплексный анализ символа
        
        Args:
            symbol: Торговый символ (например "BTCUSDT")
            
        Returns:
            MarketAnalysisReport или None при ошибке
        """
        try:
            logger.info(f"🔬 Начинаю анализ {symbol}...")
            
            # ========== ШАГ 1: Получаем рыночные данные ==========
            logger.debug("📊 Получение market snapshot...")
            market_snapshot = await self.data_source_adapter.get_market_snapshot(symbol)
            
            if not market_snapshot:
                logger.error(f"❌ Не удалось получить данные для {symbol}")
                self.stats["analyses_failed"] += 1
                return None
            
            logger.debug(f"✅ Market snapshot: ${market_snapshot.current_price:.2f}")
            
            # ========== ШАГ 2: Получаем технический анализ ==========
            logger.debug("🧠 Получение технического анализа...")
            ta_context = await self.ta_context_manager.get_context(symbol)
            
            # Извлекаем ключевые уровни
            key_levels = []
            for level in ta_context.levels_d1[:5]:  # Топ-5 уровней
                key_levels.append({
                    "type": level.get("type", "support"),
                    "price": float(level.get("price", 0)),
                    "strength": level.get("strength", 0)
                })
            
            # ATR и волатильность
            atr_value = 0.0
            if ta_context.atr_data and "atr_d1" in ta_context.atr_data:
                atr_value = ta_context.atr_data["atr_d1"]
            
            # Определяем волатильность
            volatility_pct = (market_snapshot.high_24h - market_snapshot.low_24h) / market_snapshot.current_price * 100
            if volatility_pct > 5:
                volatility = "HIGH"
            elif volatility_pct > 3:
                volatility = "MEDIUM"
            else:
                volatility = "LOW"
            
            # Определяем тренд
            if market_snapshot.price_change_24h > 2:
                trend = "BULLISH"
            elif market_snapshot.price_change_24h < -2:
                trend = "BEARISH"
            else:
                trend = "NEUTRAL"
            
            logger.debug(f"✅ TA: тренд={trend}, волатильность={volatility}")
            
            # ========== ШАГ 3: Получаем мнения стратегий ==========
            logger.debug("🎭 Получение мнений стратегий...")
            strategies_opinions = await self._get_strategies_opinions(symbol, market_snapshot, ta_context)
            
            logger.debug(f"✅ Получено {len(strategies_opinions)} мнений стратегий")
            
            # ========== ШАГ 4: Формируем данные для OpenAI ==========
            logger.debug("🤖 Подготовка данных для AI...")
            ai_input_data = self._prepare_ai_input(
                market_snapshot,
                ta_context,
                strategies_opinions,
                key_levels,
                atr_value,
                volatility,
                trend
            )
            
            # ========== ШАГ 5: Получаем AI анализ ==========
            logger.debug("🤖 Запрос AI анализа...")
            ai_analysis = await self.openai_analyzer.comprehensive_market_analysis(ai_input_data)
            
            logger.debug(f"✅ AI анализ получен ({len(ai_analysis)} символов)")
            
            # ========== ШАГ 6: Определяем общий вердикт ==========
            overall_sentiment = self._calculate_overall_sentiment(strategies_opinions, trend)
            risk_level = self._calculate_risk_level(volatility, strategies_opinions)
            
            # ========== ШАГ 7: Формируем отчет ==========
            report = MarketAnalysisReport(
                symbol=symbol,
                timestamp=datetime.now(),
                current_price=market_snapshot.current_price,
                price_change_24h=market_snapshot.price_change_24h,
                volume_24h=market_snapshot.volume_24h,
                high_24h=market_snapshot.high_24h,
                low_24h=market_snapshot.low_24h,
                key_levels=key_levels,
                atr_value=atr_value,
                volatility=volatility,
                trend=trend,
                strategies_opinions=strategies_opinions,
                ai_analysis=ai_analysis,
                overall_sentiment=overall_sentiment,
                risk_level=risk_level
            )
            
            self.stats["analyses_completed"] += 1
            self.stats["last_analysis_time"] = datetime.now()
            
            logger.info(f"✅ Анализ {symbol} завершен: {overall_sentiment}, риск={risk_level}")
            
            return report
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats["analyses_failed"] += 1
            return None
    
    async def _get_strategies_opinions(
        self,
        symbol: str,
        market_snapshot,
        ta_context
    ) -> Dict[str, StrategyOpinion]:
        """Получает мнения всех стратегий"""
        opinions = {}
        
        try:
            # Получаем все активные стратегии
            if not self.strategy_orchestrator.strategy_instances:
                logger.warning("⚠️ Нет активных стратегий для анализа")
                return opinions
            
            for name, instance in self.strategy_orchestrator.strategy_instances.items():
                try:
                    # Используем метод analyze_market_opinion стратегии
                    opinion_data = await instance.strategy.analyze_market_opinion(
                        market_snapshot,
                        ta_context
                    )
                    
                    if opinion_data:
                        opinions[name] = StrategyOpinion(
                            strategy_name=name,
                            opinion=opinion_data.get("opinion", "NEUTRAL"),
                            confidence=opinion_data.get("confidence", 0.5),
                            reasoning=opinion_data.get("reasoning", "Нет данных"),
                            signal_strength=opinion_data.get("signal_strength", 0.0),
                            key_points=opinion_data.get("key_points", [])
                        )
                    
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить мнение {name}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения мнений стратегий: {e}")
        
        return opinions
    
    def _prepare_ai_input(
        self,
        market_snapshot,
        ta_context,
        strategies_opinions: Dict[str, StrategyOpinion],
        key_levels: List[Dict],
        atr_value: float,
        volatility: str,
        trend: str
    ) -> Dict[str, Any]:
        """Подготавливает данные для отправки в OpenAI"""
        
        # Форматируем мнения стратегий для AI
        strategies_summary = []
        for name, opinion in strategies_opinions.items():
            strategies_summary.append({
                "name": name,
                "opinion": opinion.opinion,
                "confidence": opinion.confidence,
                "reasoning": opinion.reasoning
            })
        
        return {
            # Рыночные данные
            "symbol": market_snapshot.symbol,
            "current_price": market_snapshot.current_price,
            "price_change_1m": getattr(market_snapshot, "price_change_1m", 0),
            "price_change_5m": getattr(market_snapshot, "price_change_5m", 0),
            "price_change_24h": market_snapshot.price_change_24h,
            "volume_24h": market_snapshot.volume_24h,
            "high_24h": market_snapshot.high_24h,
            "low_24h": market_snapshot.low_24h,
            
            # Технический анализ
            "trend": trend,
            "volatility": volatility,
            "atr": atr_value,
            "key_levels": key_levels,
            
            # Мнения стратегий
            "strategies_opinions": strategies_summary,
            
            # Контекст
            "analysis_type": "comprehensive_market_analysis"
        }
    
    def _calculate_overall_sentiment(
        self,
        strategies_opinions: Dict[str, StrategyOpinion],
        trend: str
    ) -> str:
        """Вычисляет общее настроение рынка"""
        
        if not strategies_opinions:
            return trend
        
        # Подсчитываем голоса
        bullish_count = sum(1 for op in strategies_opinions.values() if op.opinion == "BULLISH")
        bearish_count = sum(1 for op in strategies_opinions.values() if op.opinion == "BEARISH")
        neutral_count = sum(1 for op in strategies_opinions.values() if op.opinion == "NEUTRAL")
        
        total = len(strategies_opinions)
        
        # Если больше 60% за один вариант - четкое мнение
        if bullish_count / total > 0.6:
            return "BULLISH"
        elif bearish_count / total > 0.6:
            return "BEARISH"
        elif neutral_count / total > 0.6:
            return "NEUTRAL"
        else:
            return "MIXED"
    
    def _calculate_risk_level(
        self,
        volatility: str,
        strategies_opinions: Dict[str, StrategyOpinion]
    ) -> str:
        """Вычисляет уровень риска"""
        
        # Базовый риск от волатильности
        risk_score = 0
        
        if volatility == "HIGH":
            risk_score += 3
        elif volatility == "MEDIUM":
            risk_score += 2
        else:
            risk_score += 1
        
        # Добавляем риск от разброса мнений стратегий
        if strategies_opinions:
            opinions_list = [op.opinion for op in strategies_opinions.values()]
            unique_opinions = len(set(opinions_list))
            
            if unique_opinions >= 3:  # Все разные
                risk_score += 2
            elif unique_opinions == 2:
                risk_score += 1
        
        # Финальная оценка
        if risk_score >= 5:
            return "HIGH"
        elif risk_score >= 3:
            return "MEDIUM"
        else:
            return "LOW"
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику"""
        return {
            **self.stats,
            "last_analysis_formatted": self.stats["last_analysis_time"].isoformat() if self.stats["last_analysis_time"] else None
        }


__all__ = ["MarketAnalyzer", "MarketAnalysisReport", "StrategyOpinion"]

logger.info("✅ Market Analyzer module loaded (v1.0.0)")
