import logging
import json
from openai import AsyncOpenAI
from config import Config

logger = logging.getLogger(__name__)

class OpenAIAnalyzer:
    """Анализатор рыночных данных с помощью OpenAI"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.OPENAI_MODEL
    
    async def analyze_market(self, market_data: dict) -> str:
        """Анализ рыночных данных с помощью GPT"""
        try:
            # Формируем промпт для анализа
            prompt = self._create_analysis_prompt(market_data)
            
            logger.info("Отправляю запрос к OpenAI для анализа")
            
            # Отправляем запрос к OpenAI
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt()
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            analysis = response.choices[0].message.content
            logger.info("Анализ получен от OpenAI")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Ошибка при анализе данных через OpenAI: {e}")
            return self._get_fallback_analysis(market_data)
    
    def _get_system_prompt(self) -> str:
        """Системный промпт для ИИ агента"""
        return """
Ты профессиональный криптоаналитик с многолетним опытом анализа рынка биткоина.

Твоя задача:
1. Проанализировать предоставленные рыночные данные BTC/USDT с Bybit
2. Дать краткий и понятный анализ текущей ситуации
3. Указать ключевые уровни поддержки/сопротивления если возможно
4. Дать общее мнение о краткосрочном тренде (1-3 дня)
5. Упомянуть важные показатели (объем, волатильность, открытый интерес)

Стиль ответа:
- Используй эмодзи для наглядности
- Пиши кратко и по существу
- Избегай финансовых советов, только анализ данных
- Формат: не более 500 символов
- Добавь предупреждение о рисках в конце

НЕ давай инвестиционные советы, только анализ данных!
        """
    
    def _create_analysis_prompt(self, market_data: dict) -> str:
        """Создание промпта с рыночными данными"""
        try:
            # Извлекаем ключевые данные
            current_price = market_data.get('current_price', 0)
            price_change = market_data.get('price_change_24h', 0)
            volume_24h = market_data.get('volume_24h', 0)
            high_24h = market_data.get('high_24h', 0)
            low_24h = market_data.get('low_24h', 0)
            open_interest = market_data.get('open_interest', 0)
            hourly_stats = market_data.get('hourly_data', {})
            
            prompt = f"""
Проанализируй следующие рыночные данные для BTC/USDT:

📊 ТЕКУЩИЕ ПОКАЗАТЕЛИ:
• Цена: ${current_price:,.2f}
• Изменение за 24ч: {price_change:+.2f}%
• Максимум 24ч: ${high_24h:,.2f}
• Минимум 24ч: ${low_24h:,.2f}
• Объем 24ч: {volume_24h:,.0f} BTC
• Открытый интерес: {open_interest:,.0f}

📈 СТАТИСТИКА ЗА 24 ЧАСА:
• Тренд: {hourly_stats.get('price_trend', 'неизвестно')}
• Средняя цена: ${hourly_stats.get('avg_price_24h', 0):,.2f}
• Волатильность: {hourly_stats.get('price_volatility', 0):.2f}%
• Средний объем/час: {hourly_stats.get('avg_hourly_volume', 0):,.0f}

Дай краткий анализ этих данных с фокусом на:
1. Текущее движение цены
2. Активность рынка (объем)
3. Краткосрочные перспективы
4. Ключевые уровни (если видны)
            """
            
            return prompt
            
        except Exception as e:
            logger.error(f"Ошибка создания промпта: {e}")
            return f"Проанализируй рыночные данные BTC/USDT: {json.dumps(market_data, indent=2)}"
    
    def _get_fallback_analysis(self, market_data: dict) -> str:
        """Резервный анализ при ошибке OpenAI"""
        try:
            current_price = market_data.get('current_price', 0)
            price_change = market_data.get('price_change_24h', 0)
            volume_24h = market_data.get('volume_24h', 0)
            
            trend_emoji = "🟢" if price_change > 0 else "🔴" if price_change < 0 else "🔶"
            
            return f"""
{trend_emoji} *Текущая ситуация BTC/USDT*

💰 Цена: ${current_price:,.2f}
📊 Изменение: {price_change:+.2f}%
📈 Объем 24ч: {volume_24h:,.0f} BTC

⚠️ *Автоматический анализ недоступен*
Данные получены с Bybit API.

_Это не инвестиционный совет. Торговля криптовалютами связана с высокими рисками._
            """
            
        except Exception as e:
            logger.error(f"Ошибка создания резервного анализа: {e}")
            return """
❌ *Ошибка анализа*

Не удалось проанализировать данные.
Попробуйте позже.

_Торговля криптовалютами связана с высокими рисками._
            """
