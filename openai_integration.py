# openai_integration.py
import logging
import json
from openai import AsyncOpenAI
from config import Config
from typing import Dict

logger = logging.getLogger(__name__)

class OpenAIAnalyzer:
    """Анализатор рыночных данных с использованием GPT-5 (Responses API)."""

    def __init__(self):
        self.api_key = Config.OPENAI_API_KEY
        self.model = Config.OPENAI_MODEL  # например "gpt-5" или "gpt-5-mini"

    async def analyze_market(self, market_data: Dict) -> str:
        """Анализ рыночных данных с использованием Responses API (GPT-5)."""
        prompt = self._create_analysis_prompt(market_data).strip()
        logger.info("Отправляю запрос к OpenAI (Responses API) для анализа")

        try:
            # Контекстный менеджер гарантирует закрытие HTTP ресурсов
            async with AsyncOpenAI(api_key=self.api_key) as client:
                # ✅ Правильный формат input - список сообщений, а не строка
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

            # Детальное логирование для отладки
            logger.info(f"Response status: {response.status if hasattr(response, 'status') else 'N/A'}")
            logger.info(f"Response model: {response.model if hasattr(response, 'model') else 'N/A'}")
            
            # Логируем output_text
            if hasattr(response, 'output_text'):
                logger.info(f"output_text exists: {response.output_text is not None}, value: '{response.output_text}'")
            
            # Логируем структуру output
            if hasattr(response, 'output') and response.output:
                logger.info(f"output exists, length: {len(response.output)}")
                for idx, item in enumerate(response.output):
                    logger.info(f"output[{idx}] type: {item.type if hasattr(item, 'type') else 'no type'}")
                    if hasattr(item, 'content'):
                        logger.info(f"output[{idx}] has content: {item.content is not None}")
                        if item.content:
                            logger.info(f"output[{idx}] content length: {len(item.content)}")
                            for c_idx, c in enumerate(item.content):
                                logger.info(f"output[{idx}].content[{c_idx}]: {c}")

            # ✅ Метод 1: Простое извлечение через output_text
            if hasattr(response, 'output_text') and response.output_text:
                analysis = response.output_text.strip()
                if analysis:
                    logger.info(f"✅ Анализ получен через output_text, длина: {len(analysis)} символов")
                    return analysis

            # Метод 2: Извлечение через output
            logger.info("output_text пуст, пробуем извлечь из response.output")
            
            if hasattr(response, 'output') and response.output:
                analysis = ""
                for item in response.output:
                    # Пропускаем reasoning items
                    if hasattr(item, 'type') and item.type == 'reasoning':
                        logger.info(f"Пропускаем reasoning item")
                        continue
                    
                    # Извлекаем текст из message items
                    if hasattr(item, 'type') and item.type == 'message':
                        logger.info(f"Найден message item")
                        if hasattr(item, 'content') and item.content:
                            for content in item.content:
                                logger.info(f"Content item: type={getattr(content, 'type', 'no type')}")
                                if hasattr(content, 'type') and content.type == 'output_text':
                                    if hasattr(content, 'text') and content.text:
                                        analysis += content.text
                                        logger.info(f"Добавлен текст, длина: {len(content.text)}")
                
                if analysis.strip():
                    logger.info(f"✅ Анализ получен через output, длина: {len(analysis)} символов")
                    return analysis.strip()

            # Если ничего не получилось - логируем полный response для отладки
            logger.error("Не удалось извлечь текст. Полный response:")
            logger.error(f"response.model_dump(): {response.model_dump() if hasattr(response, 'model_dump') else 'N/A'}")
            
            return self._get_fallback_analysis(market_data)

        except Exception as e:
            logger.error(f"Ошибка при анализе данных через OpenAI: {e}", exc_info=True)
            return self._get_fallback_analysis(market_data)

    def _create_analysis_prompt(self, market_data: dict) -> str:
        """Создание промпта с рыночными данными."""
        try:
            current_price = market_data.get('current_price', 0)
            price_change = market_data.get('price_change_24h', 0)
            volume_24h = market_data.get('volume_24h', 0)
            high_24h = market_data.get('high_24h', 0)
            low_24h = market_data.get('low_24h', 0)
            open_interest = market_data.get('open_interest', 0)
            hourly_stats = market_data.get('hourly_data', {})

            prompt = f"""Ты профессиональный криптоаналитик с многолетним опытом анализа рынка биткоина.

Проанализируй следующие рыночные данные для BTC/USDT:

📊 ТЕКУЩИЕ ПОКАЗАТЕЛИ:
- Цена: ${current_price:,.2f}
- Изменение за 24ч: {price_change:+.2f}%
- Максимум 24ч: ${high_24h:,.2f}
- Минимум 24ч: ${low_24h:,.2f}
- Объем 24ч: {volume_24h:,.0f} BTC
- Открытый интерес: {open_interest:,.0f}

📈 СТАТИСТИКА ЗА 24 ЧАСА:
- Тренд: {hourly_stats.get('price_trend', 'неизвестно')}
- Средняя цена: ${hourly_stats.get('avg_price_24h', 0):,.2f}
- Волатильность: {hourly_stats.get('price_volatility', 0):.2f}%
- Средний объем/час: {hourly_stats.get('avg_hourly_volume', 0):,.0f}

Дай краткий и честный анализ (не более 600 символов) с фокусом на:
1) Текущее движение цены
2) Активность рынка (объем)
3) Краткосрочные перспективы (1-3 дня)
4) Ключевые уровни поддержки/сопротивления (если видны)

Не давай инвестиционных советов — только аналитика. 
Добавь короткое предупреждение о рисках в конце."""
            
            return prompt
        except Exception as e:
            logger.error(f"Ошибка создания промпта: {e}")
            return f"Проанализируй рыночные данные BTC/USDT: {json.dumps(market_data, indent=2)}"

    def _get_fallback_analysis(self, market_data: dict) -> str:
        """Резервный анализ при ошибке OpenAI."""
        try:
            current_price = market_data.get('current_price', 0)
            price_change = market_data.get('price_change_24h', 0)
            volume_24h = market_data.get('volume_24h', 0)
            high_24h = market_data.get('high_24h', 0)
            low_24h = market_data.get('low_24h', 0)

            # Определяем направление тренда
            if price_change > 2:
                trend = "🟢 *Сильный рост*"
                trend_desc = "Рынок показывает уверенное восходящее движение"
            elif price_change > 0:
                trend = "🟢 *Рост*"
                trend_desc = "Умеренное восходящее движение"
            elif price_change > -2:
                trend = "🔶 *Стабильность*"
                trend_desc = "Рынок торгуется в боковом диапазоне"
            elif price_change > -5:
                trend = "🔴 *Снижение*"
                trend_desc = "Умеренное нисходящее движение"
            else:
                trend = "🔴 *Сильное снижение*"
                trend_desc = "Рынок показывает значительную коррекцию"

            # Оценка волатильности
            price_range = high_24h - low_24h
            volatility_pct = (price_range / current_price) * 100 if current_price > 0 else 0

            return f"""
{trend}

💰 *Текущая цена:* ${current_price:,.2f}
📊 *Изменение 24ч:* {price_change:+.2f}%
📈 *Диапазон 24ч:* ${low_24h:,.2f} - ${high_24h:,.2f}
📉 *Волатильность:* {volatility_pct:.2f}%
💼 *Объем 24ч:* {volume_24h:,.0f} BTC

📌 *Краткий анализ:*
{trend_desc}. Волатильность за последние 24 часа составляет {volatility_pct:.1f}%.

⚠️ *Автоматический AI-анализ временно недоступен*
Данные получены с Bybit API в реальном времени.

_Это не инвестиционный совет. Торговля криптовалютами связана с высокими рисками. Всегда проводите собственное исследование перед принятием торговых решений._
            """
        except Exception as e:
            logger.error(f"Ошибка создания резервного анализа: {e}")
            return """
❌ *Ошибка анализа*

Не удалось проанализировать рыночные данные.
Попробуйте повторить запрос через несколько минут.

_Торговля криптовалютами связана с высокими рисками._
            """
