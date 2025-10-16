# openai_integration.py
import logging
import json
from openai import AsyncOpenAI
from config import Config
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class OpenAIAnalyzer:
    """
    Анализатор рыночных данных с использованием OpenAI API
    
    Версия: 2.0 - Интегрирована с SignalManager для AI обогащения сигналов
    
    Основные функции:
    1. Анализ рыночных данных с учетом торговых сигналов
    2. Генерация контекстно-зависимого анализа
    3. Безопасная обработка ошибок с fallback
    4. Детальное логирование для отладки
    """

    def __init__(self):
        self.api_key = Config.OPENAI_API_KEY
        self.model = Config.OPENAI_MODEL  # например "gpt-5" или "gpt-4"
        
        logger.info("🤖 OpenAIAnalyzer инициализирован")
        logger.info(f"   • Модель: {self.model}")
        logger.info(f"   • API Key: {'✅ Настроен' if self.api_key else '❌ Отсутствует'}")

    async def analyze_market(self, market_data: Dict) -> str:
        """
        Анализ рыночных данных с использованием OpenAI API
        
        Args:
            market_data: Словарь с рыночными данными и контекстом сигнала:
                - current_price: Текущая цена
                - price_change_24h: Изменение за 24ч (%)
                - volume_24h: Объем за 24ч
                - high_24h, low_24h: Максимум/минимум 24ч
                - price_change_1m, price_change_5m: Краткосрочные изменения
                - signal_type: Тип сигнала (BUY/SELL/etc)
                - signal_strength: Сила сигнала (0-1)
                - signal_confidence: Уверенность (0-1)
                - strategy_name: Название стратегии
                - signal_reasons: Список причин сигнала
                - hourly_data: Почасовая статистика
                
        Returns:
            str: Текстовый AI анализ рынка
        """
        prompt = self._create_analysis_prompt(market_data).strip()
        
        logger.info("📤 Отправка запроса к OpenAI API...")
        logger.debug(f"Промпт длина: {len(prompt)} символов")

        try:
            # Контекстный менеджер гарантирует закрытие HTTP ресурсов
            async with AsyncOpenAI(api_key=self.api_key) as client:
                # Правильный формат input - список сообщений
                response = await client.responses.create(
                    model=self.model,
                    input=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_output_tokens=500
                )

            # Детальное логирование ответа
            logger.debug(f"Response status: {response.status if hasattr(response, 'status') else 'N/A'}")
            logger.debug(f"Response model: {response.model if hasattr(response, 'model') else 'N/A'}")
            
            # Метод 1: Извлечение через output_text (приоритетный)
            if hasattr(response, 'output_text') and response.output_text:
                analysis = response.output_text.strip()
                if analysis:
                    logger.info(f"✅ AI анализ получен через output_text ({len(analysis)} символов)")
                    return analysis

            # Метод 2: Извлечение через output (fallback)
            logger.debug("output_text пуст, пробуем извлечь из response.output")
            
            if hasattr(response, 'output') and response.output:
                analysis = ""
                for item in response.output:
                    # Пропускаем reasoning items
                    if hasattr(item, 'type') and item.type == 'reasoning':
                        logger.debug("Пропускаем reasoning item")
                        continue
                    
                    # Извлекаем текст из message items
                    if hasattr(item, 'type') and item.type == 'message':
                        logger.debug("Найден message item")
                        if hasattr(item, 'content') and item.content:
                            for content in item.content:
                                if hasattr(content, 'type') and content.type == 'output_text':
                                    if hasattr(content, 'text') and content.text:
                                        analysis += content.text
                                        logger.debug(f"Добавлен текст из content ({len(content.text)} символов)")
                
                if analysis.strip():
                    logger.info(f"✅ AI анализ получен через output ({len(analysis)} символов)")
                    return analysis.strip()

            # Если ничего не получилось - используем fallback
            logger.warning("⚠️ Не удалось извлечь текст из OpenAI response")
            logger.debug(f"Response dump: {response.model_dump() if hasattr(response, 'model_dump') else 'N/A'}")
            
            return self._get_fallback_analysis(market_data)

        except Exception as e:
            logger.error(f"❌ Ошибка при анализе данных через OpenAI: {e}", exc_info=True)
            return self._get_fallback_analysis(market_data)

    def _create_analysis_prompt(self, market_data: dict) -> str:
        """
        Создание промпта с рыночными данными и контекстом сигнала
        
        Args:
            market_data: Словарь с рыночными данными
            
        Returns:
            str: Отформатированный промпт для OpenAI
        """
        try:
            # ========== Безопасное извлечение данных ==========
            
            # Основные показатели (обязательные)
            current_price = market_data.get('current_price', 0)
            price_change_24h = market_data.get('price_change_24h', 0)
            volume_24h = market_data.get('volume_24h', 0)
            high_24h = market_data.get('high_24h', current_price if current_price > 0 else 0)
            low_24h = market_data.get('low_24h', current_price if current_price > 0 else 0)
            open_interest = market_data.get('open_interest', 0)
            
            # Краткосрочные изменения (опциональные)
            price_change_1m = market_data.get('price_change_1m', 0)
            price_change_5m = market_data.get('price_change_5m', 0)
            
            # Контекст торгового сигнала (опциональные)
            signal_type = market_data.get('signal_type', 'N/A')
            signal_strength = market_data.get('signal_strength', 0)
            signal_confidence = market_data.get('signal_confidence', 0)
            strategy_name = market_data.get('strategy_name', 'Unknown')
            signal_reasons = market_data.get('signal_reasons', [])
            
            # Почасовая статистика (опциональная)
            hourly_stats = market_data.get('hourly_data', {})
            
            # ========== Формирование промпта ==========
            
            prompt = f"""Ты профессиональный криптоаналитик с многолетним опытом анализа рынка биткоина.

🚨 КОНТЕКСТ ТОРГОВОГО СИГНАЛА:
- Тип сигнала: {signal_type}
- Сила сигнала: {signal_strength:.2f} (0.0 - 1.0)
- Уверенность: {signal_confidence:.2f} (0.0 - 1.0)
- Стратегия: {strategy_name}

Проанализируй следующие рыночные данные для BTC/USDT:

📊 ТЕКУЩИЕ ПОКАЗАТЕЛИ:
- Цена: ${current_price:,.2f}
- Изменение за 1 мин: {price_change_1m:+.2f}%
- Изменение за 5 мин: {price_change_5m:+.2f}%
- Изменение за 24ч: {price_change_24h:+.2f}%
- Максимум 24ч: ${high_24h:,.2f}
- Минимум 24ч: ${low_24h:,.2f}
- Объем 24ч: {volume_24h:,.0f} BTC
- Открытый интерес: {open_interest:,.0f}"""

            # Добавляем причины сигнала если есть
            if signal_reasons and len(signal_reasons) > 0:
                prompt += "\n\n🔍 ПРИЧИНЫ СИГНАЛА:\n"
                for i, reason in enumerate(signal_reasons[:3], 1):  # Максимум 3 причины
                    prompt += f"{i}. {reason}\n"

            # Добавляем почасовую статистику если есть
            if hourly_stats:
                prompt += f"""
📈 СТАТИСТИКА ЗА 24 ЧАСА:
- Тренд: {hourly_stats.get('price_trend', 'неизвестно')}
- Средняя цена: ${hourly_stats.get('avg_price_24h', 0):,.2f}
- Волатильность: {hourly_stats.get('price_volatility', 0):.2f}%
- Средний объем/час: {hourly_stats.get('avg_hourly_volume', 0):,.0f}"""

            # Финальная инструкция
            prompt += """

Дай краткий и честный анализ (не более 600 символов) с учетом полученного торгового сигнала:

1) **Подтверждение сигнала**: Подтверждается ли сигнал текущими рыночными данными?
2) **Текущее движение**: Анализ краткосрочного (1-5 мин) и среднесрочного (24ч) движения цены
3) **Активность рынка**: Оценка объемов и активности участников
4) **Краткосрочные перспективы**: Ожидаемое движение на 1-3 дня
5) **Ключевые уровни**: Важные уровни поддержки/сопротивления (если видны)

❗ ВАЖНО:
- НЕ давай инвестиционных советов или рекомендаций к действию
- Предоставь только объективную аналитику
- Обязательно добавь короткое предупреждение о рисках в конце
- Используй простой язык без сложных терминов"""
            
            logger.debug(f"✅ Промпт создан успешно ({len(prompt)} символов)")
            return prompt
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания промпта: {e}")
            # Минимальный fallback промпт
            return f"""Проанализируй рыночные данные BTC/USDT:
Цена: ${market_data.get('current_price', 0):,.2f}
Изменение 24ч: {market_data.get('price_change_24h', 0):+.2f}%
Дай краткий анализ текущей ситуации."""

    def _get_fallback_analysis(self, market_data: dict) -> str:
        """
        Резервный анализ при ошибке OpenAI
        
        Генерирует базовый анализ на основе имеющихся данных без использования AI.
        
        Args:
            market_data: Словарь с рыночными данными
            
        Returns:
            str: Резервное сообщение с анализом
        """
        try:
            # Безопасное извлечение данных
            current_price = market_data.get('current_price', 0)
            price_change_24h = market_data.get('price_change_24h', 0)
            price_change_1m = market_data.get('price_change_1m', 0)
            price_change_5m = market_data.get('price_change_5m', 0)
            volume_24h = market_data.get('volume_24h', 0)
            high_24h = market_data.get('high_24h', current_price)
            low_24h = market_data.get('low_24h', current_price)
            
            signal_type = market_data.get('signal_type', 'N/A')
            signal_strength = market_data.get('signal_strength', 0)
            strategy_name = market_data.get('strategy_name', 'Unknown')

            # Определяем направление тренда на основе изменений
            if price_change_24h > 5:
                trend = "🟢 *Сильный рост*"
                trend_desc = "Рынок показывает уверенное восходящее движение с сильным импульсом"
            elif price_change_24h > 2:
                trend = "🟢 *Рост*"
                trend_desc = "Умеренное восходящее движение, рынок в позитивном настроении"
            elif price_change_24h > -2:
                trend = "🔶 *Стабильность*"
                trend_desc = "Рынок торгуется в боковом диапазоне, консолидация"
            elif price_change_24h > -5:
                trend = "🔴 *Снижение*"
                trend_desc = "Умеренное нисходящее движение, коррекция"
            else:
                trend = "🔴 *Сильное снижение*"
                trend_desc = "Рынок показывает значительную коррекцию"

            # Анализ краткосрочной динамики
            short_term = ""
            if abs(price_change_1m) > 1 or abs(price_change_5m) > 2:
                if price_change_5m > 0:
                    short_term = "Наблюдается краткосрочный импульс роста."
                else:
                    short_term = "Видна краткосрочная коррекция."
            else:
                short_term = "Краткосрочная динамика стабильна."

            # Оценка волатильности
            price_range = high_24h - low_24h
            volatility_pct = (price_range / current_price) * 100 if current_price > 0 else 0
            
            if volatility_pct > 5:
                volatility_desc = "высокая волатильность"
            elif volatility_pct > 3:
                volatility_desc = "умеренная волатильность"
            else:
                volatility_desc = "низкая волатильность"

            # Оценка подтверждения сигнала
            signal_confirmation = ""
            if signal_type in ['BUY', 'STRONG_BUY']:
                if price_change_24h > 0 and price_change_5m > 0:
                    signal_confirmation = "✅ Сигнал на покупку подтверждается восходящим движением."
                elif price_change_24h < 0:
                    signal_confirmation = "⚠️ Сигнал на покупку поступил на фоне снижения - будьте осторожны."
                else:
                    signal_confirmation = "🔶 Рынок в консолидации, сигнал требует подтверждения."
            elif signal_type in ['SELL', 'STRONG_SELL']:
                if price_change_24h < 0 and price_change_5m < 0:
                    signal_confirmation = "✅ Сигнал на продажу подтверждается нисходящим движением."
                elif price_change_24h > 0:
                    signal_confirmation = "⚠️ Сигнал на продажу поступил на фоне роста - оцените риски."
                else:
                    signal_confirmation = "🔶 Рынок в консолидации, сигнал требует подтверждения."

            # Формируем итоговое сообщение
            fallback_message = f"""
{trend}

💰 *Текущая цена:* ${current_price:,.2f}

📊 *Изменения:*
- 1 минута: {price_change_1m:+.2f}%
- 5 минут: {price_change_5m:+.2f}%
- 24 часа: {price_change_24h:+.2f}%

📈 *Диапазон 24ч:* ${low_24h:,.2f} - ${high_24h:,.2f}
📉 *Волатильность:* {volatility_pct:.2f}% ({volatility_desc})
💼 *Объем 24ч:* {volume_24h:,.0f} BTC

🔍 *Анализ сигнала:*
- Стратегия: {strategy_name}
- Тип: {signal_type}
- Сила: {signal_strength:.2f}

{signal_confirmation}

📌 *Краткий вывод:*
{trend_desc}. {short_term} За последние 24 часа волатильность составила {volatility_pct:.1f}%.

⚠️ *AI-анализ временно недоступен*
Представлен автоматический анализ на основе рыночных данных в реальном времени.

_❗ Это не инвестиционный совет. Торговля криптовалютами связана с высокими рисками. Всегда проводите собственное исследование (DYOR) перед принятием торговых решений._
            """
            
            logger.info("ℹ️ Использован резервный анализ (fallback)")
            return fallback_message.strip()
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка создания резервного анализа: {e}")
            # Минимальный fallback на случай полного краха
            return """
❌ *Ошибка анализа*

Не удалось проанализировать рыночные данные.
Попробуйте повторить запрос через несколько минут.

_⚠️ Торговля криптовалютами связана с высокими рисками. Всегда будьте осторожны и используйте риск-менеджмент._
            """

    async def comprehensive_market_analysis(self, analysis_data: Dict) -> str:
        """
        Комплексный анализ рынка с учетом всех доступных данных
        
        Args:
            analysis_data: Полный набор данных для анализа:
                - symbol: торговый символ
                - current_price, price_change_24h, volume_24h...
                - trend, volatility, atr
                - key_levels: список ключевых уровней
                - strategies_opinions: мнения всех стратегий
                
        Returns:
            str: Подробный AI анализ рынка
        """
        prompt = self._create_comprehensive_analysis_prompt(analysis_data).strip()
        
        # ✅ ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ
        logger.info("=" * 80)
        logger.info("🔍 ДАННЫЕ ДЛЯ OPENAI:")
        logger.info(f"Symbol: {analysis_data.get('symbol', 'N/A')}")
        logger.info(f"Current Price: ${analysis_data.get('current_price', 0):,.2f}")
        logger.info(f"Price Change 24h: {analysis_data.get('price_change_24h', 0):+.2f}%")
        logger.info(f"Trend: {analysis_data.get('trend', 'N/A')}")
        logger.info(f"Volatility: {analysis_data.get('volatility', 'N/A')}")
        logger.info(f"ATR: {analysis_data.get('atr', 0):.2f}")
        logger.info(f"Key Levels: {len(analysis_data.get('key_levels', []))} levels")
        logger.info(f"Strategies Opinions: {len(analysis_data.get('strategies_opinions', []))} opinions")
        logger.info("-" * 80)
        logger.info(f"PROMPT LENGTH: {len(prompt)} characters")
        logger.info("PROMPT PREVIEW (first 500 chars):")
        logger.info(prompt[:500])
        logger.info("=" * 80)
        
        logger.info(f"📤 Отправка комплексного анализа для {analysis_data.get('symbol', 'N/A')}...")
        logger.debug(f"Промпт длина: {len(prompt)} символов")
        
        try:
            async with AsyncOpenAI(api_key=self.api_key) as client:
                response = await client.responses.create(
                    model=self.model,
                    input=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_output_tokens=800  # Больше токенов для детального анализа
                )
            
            # Извлекаем текст (как в analyze_market)
            if hasattr(response, 'output_text') and response.output_text:
                analysis = response.output_text.strip()
                if analysis:
                    logger.info(f"✅ Комплексный AI анализ получен ({len(analysis)} символов)")
                    return analysis
            
            if hasattr(response, 'output') and response.output:
                analysis = ""
                for item in response.output:
                    if hasattr(item, 'type') and item.type == 'reasoning':
                        continue
                    
                    if hasattr(item, 'type') and item.type == 'message':
                        if hasattr(item, 'content') and item.content:
                            for content in item.content:
                                if hasattr(content, 'type') and content.type == 'output_text':
                                    if hasattr(content, 'text') and content.text:
                                        analysis += content.text
                
                if analysis.strip():
                    logger.info(f"✅ Комплексный AI анализ получен через output ({len(analysis)} символов)")
                    return analysis.strip()
            
            logger.warning("⚠️ Не удалось извлечь текст из OpenAI response")
            return self._get_comprehensive_fallback_analysis(analysis_data)
            
        except Exception as e:
            logger.error(f"❌ Ошибка комплексного анализа через OpenAI: {e}", exc_info=True)
            return self._get_comprehensive_fallback_analysis(analysis_data)

    def _create_comprehensive_analysis_prompt(self, analysis_data: dict) -> str:
        """
        Создание промпта для комплексного анализа
        
        Args:
            analysis_data: Полный набор данных
            
        Returns:
            str: Промпт для OpenAI
        """
        try:
            # Извлекаем данные
            symbol = analysis_data.get('symbol', 'N/A')
            current_price = analysis_data.get('current_price', 0)
            price_change_24h = analysis_data.get('price_change_24h', 0)
            volume_24h = analysis_data.get('volume_24h', 0)
            high_24h = analysis_data.get('high_24h', current_price)
            low_24h = analysis_data.get('low_24h', current_price)
            
            trend = analysis_data.get('trend', 'NEUTRAL')
            volatility = analysis_data.get('volatility', 'MEDIUM')
            atr = analysis_data.get('atr', 0)
            
            key_levels = analysis_data.get('key_levels', [])
            strategies_opinions = analysis_data.get('strategies_opinions', [])
            
            prompt = f"""Ты профессиональный криптоаналитик с многолетним опытом комплексного анализа рынка.

📊 ПРОВЕДИ ДЕТАЛЬНЫЙ АНАЛИЗ для {symbol}:

💰 РЫНОЧНЫЕ ДАННЫЕ:
- Цена: ${current_price:,.2f}
- Изменение 24ч: {price_change_24h:+.2f}%
- Максимум 24ч: ${high_24h:,.2f}
- Минимум 24ч: ${low_24h:,.2f}
- Объем 24ч: {volume_24h:,.0f}

📈 ТЕХНИЧЕСКИЙ АНАЛИЗ:
- Тренд: {trend}
- Волатильность: {volatility}
- ATR: {atr:.2f}"""

            # Добавляем ключевые уровни
            if key_levels:
                prompt += "\n\n🎯 КЛЮЧЕВЫЕ УРОВНИ:\n"
                for i, level in enumerate(key_levels[:5], 1):
                    level_type = level.get('type', 'support')
                    level_price = level.get('price', 0)
                    prompt += f"{i}. {level_type.capitalize()}: ${level_price:,.2f}\n"
            
            # Добавляем мнения стратегий
            if strategies_opinions:
                prompt += "\n\n🤖 МНЕНИЯ ТОРГОВЫХ СТРАТЕГИЙ:\n"
                for i, strategy in enumerate(strategies_opinions, 1):
                    name = strategy.get('name', 'Unknown')
                    opinion = strategy.get('opinion', 'NEUTRAL')
                    confidence = strategy.get('confidence', 0)
                    reasoning = strategy.get('reasoning', 'Нет данных')
                    
                    prompt += f"{i}. **{name}**\n"
                    prompt += f"   Мнение: {opinion}\n"
                    prompt += f"   Уверенность: {confidence:.0%}\n"
                    prompt += f"   Обоснование: {reasoning}\n\n"
            
            prompt += """
📝 ЗАДАЧА:
Дай детальный анализ (650-800 символов) по следующей структуре:

1) **Текущая ситуация** (2-3 предложения)
   - Что происходит на рынке прямо сейчас?
   - Какие главные силы сейчас действуют?

2) **Согласованность сигналов** (2-3 предложения)
   - Согласуются ли мнения стратегий?
   - Подтверждается ли техническим анализом?
   - Есть ли противоречия?

3) **Ключевые уровни** (2-3 предложения)
   - Какие уровни наиболее важны сейчас?
   - Что произойдет при пробое/отбое?

4) **Перспективы на 1-3 дня** (2-3 предложения)
   - Наиболее вероятный сценарий
   - Альтернативный сценарий (если есть)

5) **На что обратить внимание** (1-2 предложения)
   - Ключевые факторы риска
   - Важные события

❗ ТРЕБОВАНИЯ:
- Используй простой язык, избегай сложных терминов
- Будь конкретным - указывай цены и уровни
- НЕ давай прямых торговых рекомендаций
- В конце обязательно добавь короткое предупреждение о рисках (1 предложение)
- Пиши четко и структурировано
"""
            
            logger.debug(f"✅ Промпт для комплексного анализа создан ({len(prompt)} символов)")
            return prompt
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания промпта: {e}")
            # Минимальный fallback промпт
            return f"""Проанализируй рынок {analysis_data.get('symbol', 'N/A')}:
Цена: ${analysis_data.get('current_price', 0):,.2f}
Изменение 24ч: {analysis_data.get('price_change_24h', 0):+.2f}%
Дай краткий анализ текущей ситуации и перспектив."""

    def _get_comprehensive_fallback_analysis(self, analysis_data: dict) -> str:
        """
        Резервный комплексный анализ при ошибке OpenAI
        
        Args:
            analysis_data: Данные для анализа
            
        Returns:
            str: Резервный анализ
        """
        try:
            symbol = analysis_data.get('symbol', 'N/A')
            current_price = analysis_data.get('current_price', 0)
            price_change_24h = analysis_data.get('price_change_24h', 0)
            trend = analysis_data.get('trend', 'NEUTRAL')
            volatility = analysis_data.get('volatility', 'MEDIUM')
            
            strategies_opinions = analysis_data.get('strategies_opinions', [])
            
            # Подсчитываем консенсус
            bullish = sum(1 for s in strategies_opinions if s.get('opinion') == 'BULLISH')
            bearish = sum(1 for s in strategies_opinions if s.get('opinion') == 'BEARISH')
            neutral = sum(1 for s in strategies_opinions if s.get('opinion') == 'NEUTRAL')
            total = len(strategies_opinions)
            
            # Определяем общее мнение
            if total > 0:
                if bullish > total * 0.6:
                    consensus = "🟢 Большинство стратегий настроены бычьи"
                elif bearish > total * 0.6:
                    consensus = "🔴 Большинство стратегий настроены медвежье"
                else:
                    consensus = "🔶 Мнения стратегий разделились"
            else:
                consensus = "🔶 Недостаточно данных от стратегий"
            
            # Анализ тренда
            if trend == "BULLISH":
                trend_desc = "📈 Рынок находится в восходящем тренде"
            elif trend == "BEARISH":
                trend_desc = "📉 Рынок находится в нисходящем тренде"
            else:
                trend_desc = "↔️ Рынок в боковом движении"
            
            # Анализ волатильности
            if volatility == "HIGH":
                vol_desc = "⚡ Высокая волатильность создает как возможности, так и риски"
            elif volatility == "MEDIUM":
                vol_desc = "🔄 Умеренная волатильность, нормальные условия для торговли"
            else:
                vol_desc = "😴 Низкая волатильность, рынок в спокойном состоянии"
            
            fallback = f"""**ТЕКУЩАЯ СИТУАЦИЯ**

{symbol} торгуется на уровне ${current_price:,.2f} с изменением {price_change_24h:+.2f}% за последние 24 часа. {trend_desc}. {vol_desc}.

**СОГЛАСОВАННОСТЬ СИГНАЛОВ**

{consensus}. Из {total} активных стратегий: {bullish} видят возможности для роста, {bearish} указывают на риски снижения, {neutral} занимают нейтральную позицию.

**ПЕРСПЕКТИВЫ**

В краткосрочной перспективе (1-3 дня) ожидается продолжение текущей динамики с учетом наблюдаемого тренда. Ключевым фактором будет реакция рынка на текущие уровни поддержки и сопротивления.

**НА ЧТО ОБРАТИТЬ ВНИМАНИЕ**

Следите за изменением объемов торгов и реакцией цены на ключевые уровни. При {'высокой' if volatility == 'HIGH' else 'умеренной'} волатильности особенно важен строгий риск-менеджмент.

⚠️ **AI-анализ временно недоступен.** Представлен автоматический анализ на основе технических данных и мнений торговых стратегий.

❗ _Данный анализ предоставлен исключительно в информационных целях и не является инвестиционным советом. Торговля криптовалютами связана с высокими рисками потери капитала._
"""
            
            logger.info("ℹ️ Использован резервный комплексный анализ")
            return fallback.strip()
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания резервного анализа: {e}")
            return """
❌ **Ошибка анализа**

Не удалось провести комплексный анализ рынка.
Попробуйте повторить запрос через несколько минут.

_⚠️ Торговля криптовалютами связана с высокими рисками._
"""

    def test_connection(self) -> bool:
        """
        Тестирование подключения к OpenAI API
        
        Returns:
            bool: True если подключение работает
        """
        try:
            if not self.api_key:
                logger.error("❌ OpenAI API key не настроен")
                return False
            
            logger.info("🔍 Тестирование подключения к OpenAI...")
            # Простой тест с минимальным промптом
            import asyncio
            test_data = {
                'current_price': 50000,
                'price_change_24h': 2.5,
                'volume_24h': 25000
            }
            
            result = asyncio.run(self.analyze_market(test_data))
            
            if result and len(result) > 50:
                logger.info("✅ Подключение к OpenAI работает")
                return True
            else:
                logger.warning("⚠️ OpenAI вернул пустой или слишком короткий ответ")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования OpenAI: {e}")
            return False

    def get_stats(self) -> dict:
        """
        Возвращает статистику работы анализатора
        
        Returns:
            dict: Статистика использования
        """
        return {
            "model": self.model,
            "api_key_configured": bool(self.api_key),
            "api_key_length": len(self.api_key) if self.api_key else 0
        }

    def __str__(self):
        """Строковое представление"""
        return f"OpenAIAnalyzer(model={self.model}, api_configured={bool(self.api_key)})"

    def __repr__(self):
        """Подробное представление"""
        return f"OpenAIAnalyzer(model='{self.model}', api_key={'✓' if self.api_key else '✗'})"


# Экспорт
__all__ = ["OpenAIAnalyzer"]

logger.info("✅ OpenAI Integration module loaded (v2.0 - SignalManager compatible)")
