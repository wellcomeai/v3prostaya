# backtesting/report_generator.py

import logging
from typing import Dict, Any, List, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Генератор интерактивных HTML отчетов с SPA архитектурой"""
    
    # 📈 Криптовалюты (Bybit)
    CRYPTO_SYMBOLS = [
        "BTCUSDT",
        "ETHUSDT", 
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "DOGEUSDT",
        "DOTUSDT",
        "MATICUSDT",
        "LINKUSDT"
    ]
    
    # 🛢️ Фьючерсы (YFinance)
    FUTURES_SYMBOLS = [
        "MCL=F",  # Micro WTI Crude Oil
        "MGC=F",  # Micro Gold
        "MES=F",  # Micro E-mini S&P 500
        "MNQ=F"   # Micro E-mini Nasdaq 100
    ]
    
    # 📊 Интервалы для криптовалют (все доступные)
    CRYPTO_INTERVALS = [
        {"value": "1m", "label": "1 минута"},
        {"value": "3m", "label": "3 минуты"},
        {"value": "5m", "label": "5 минут"},
        {"value": "15m", "label": "15 минут"},
        {"value": "30m", "label": "30 минут"},
        {"value": "1h", "label": "1 час"},
        {"value": "2h", "label": "2 часа"},
        {"value": "4h", "label": "4 часа"},
        {"value": "6h", "label": "6 часов"},
        {"value": "12h", "label": "12 часов"},
        {"value": "1d", "label": "1 день"},
        {"value": "1w", "label": "1 неделя"}
    ]
    
    # 🛢️ Интервалы для фьючерсов (ограничены API)
    FUTURES_INTERVALS = [
        {"value": "1m", "label": "1 минута (макс. 7 дней)"},
        {"value": "5m", "label": "5 минут (макс. 60 дней)"},
        {"value": "15m", "label": "15 минут (макс. 60 дней)"},
        {"value": "30m", "label": "30 минут (макс. 60 дней)"},
        {"value": "1h", "label": "1 час (макс. 2 года)"},
        {"value": "1d", "label": "1 день"},
        {"value": "1w", "label": "1 неделя"}
    ]
    
    # ⚠️ Проблемные комбинации
    LIMITED_DATA_WARNINGS = {
        "MCL=F": {
            "intervals": ["1d", "1w"],
            "message": "⚠️ Для этой пары нет торговых данных за длительный период."
        }
    }
    
    @staticmethod
    def generate_dashboard_html() -> str:
        """Генерирует HTML страницу с интерактивным дашбордом"""
        logger.info("📊 Генерация расширенного дашборда...")
        
        # Генерация опций
        crypto_options = "\n".join([f'<option value="{s}">{s}</option>' for s in ReportGenerator.CRYPTO_SYMBOLS])
        futures_options = "\n".join([f'<option value="{s}">{s}</option>' for s in ReportGenerator.FUTURES_SYMBOLS])
        crypto_interval_options = "\n".join([
            f'<option value="{i["value"]}" {"selected" if i["value"]=="1h" else ""}>{i["label"]}</option>' 
            for i in ReportGenerator.CRYPTO_INTERVALS
        ])
        futures_interval_options = "\n".join([
            f'<option value="{i["value"]}" {"selected" if i["value"]=="1h" else ""}>{i["label"]}</option>' 
            for i in ReportGenerator.FUTURES_INTERVALS
        ])
        
        # Стратегии
        strategy_options = ""
        default_description = "Выберите стратегию для бэктестинга"
        
        try:
            from strategies import get_available_strategies
            available_strategies = get_available_strategies()
            
            if available_strategies:
                for idx, (key, info) in enumerate(available_strategies.items()):
                    selected = 'selected' if idx == 0 else ''
                    description = info.get('description', 'Описание недоступно')
                    name = info.get('name', key.title())
                    strategy_options += f'<option value="{key}" {selected} data-description="{description}">{name}</option>\n'
                    if idx == 0:
                        default_description = description
            else:
                strategy_options = '<option value="momentum" data-description="Импульсная торговая стратегия">Momentum Strategy</option>\n'
                default_description = "Импульсная торговая стратегия"
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки стратегий: {e}")
            strategy_options = '<option value="momentum" data-description="Импульсная торговая стратегия">Momentum Strategy</option>\n'
            default_description = "Импульсная торговая стратегия"
        
        warnings_json = json.dumps(ReportGenerator.LIMITED_DATA_WARNINGS)
        
        html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Расширенная Панель Бэктестинга - Trading Bot</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0f0f1e 0%, #1a1a2e 100%);
            color: #e0e0e0;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1900px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 30px 20px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        h1 {{
            font-size: 2.8em;
            background: linear-gradient(45deg, #00d4ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
            font-weight: 700;
        }}
        
        .subtitle {{
            color: #888;
            font-size: 1.2em;
            font-weight: 300;
        }}
        
        .control-panel {{
            background: rgba(255, 255, 255, 0.05);
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 30px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .control-panel h2 {{
            margin-bottom: 25px;
            color: #00d4ff;
            font-size: 1.6em;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .controls-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }}
        
        .control-group {{
            display: flex;
            flex-direction: column;
        }}
        
        .control-group label {{
            font-weight: 600;
            margin-bottom: 10px;
            color: #aaa;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .control-group select,
        .control-group input {{
            padding: 14px 18px;
            background: rgba(30, 30, 45, 0.9);
            border: 2px solid rgba(255, 255, 255, 0.15);
            border-radius: 10px;
            color: #fff;
            font-size: 1.05em;
            transition: all 0.3s ease;
            cursor: pointer;
        }}
        
        .control-group select {{
            appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1L6 6L11 1' stroke='%2300d4ff' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 15px center;
            padding-right: 45px;
        }}
        
        .control-group select:hover,
        .control-group input:hover {{
            border-color: #00d4ff;
            background: rgba(30, 30, 45, 1);
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0, 212, 255, 0.2);
        }}
        
        .control-group select:focus,
        .control-group input:focus {{
            outline: none;
            border-color: #00ff88;
            box-shadow: 0 0 20px rgba(0, 255, 136, 0.4);
        }}
        
        .warning-box {{
            display: none;
            padding: 15px 20px;
            background: rgba(255, 152, 0, 0.1);
            border-left: 4px solid #ff9800;
            border-radius: 8px;
            margin-top: 15px;
            color: #ffb74d;
            font-size: 0.95em;
        }}
        
        .warning-box.active {{
            display: block;
            animation: fadeIn 0.3s ease-out;
        }}
        
        .strategy-description {{
            margin-top: 8px;
            padding: 10px 15px;
            background: rgba(0, 212, 255, 0.1);
            border-left: 3px solid #00d4ff;
            border-radius: 5px;
            font-size: 0.9em;
            color: #aaa;
        }}
        
        .button-group {{
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }}
        
        .btn {{
            padding: 14px 35px;
            border: none;
            border-radius: 10px;
            font-size: 1.05em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .btn-primary {{
            background: linear-gradient(135deg, #00d4ff, #00ff88);
            color: #000;
            box-shadow: 0 4px 15px rgba(0, 255, 136, 0.3);
        }}
        
        .btn-primary:hover {{
            transform: translateY(-3px);
            box-shadow: 0 6px 25px rgba(0, 255, 136, 0.5);
        }}
        
        .btn-secondary {{
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            border: 2px solid rgba(255, 255, 255, 0.2);
        }}
        
        .btn-secondary:hover {{
            background: rgba(255, 255, 255, 0.15);
            border-color: rgba(255, 255, 255, 0.3);
            transform: translateY(-2px);
        }}
        
        .btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }}
        
        /* 🆕 Chart Controls */
        .chart-controls {{
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            padding: 15px 20px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 10px;
            margin-bottom: 15px;
        }}
        
        .checkbox-group {{
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
        }}
        
        .checkbox-group input[type="checkbox"] {{
            width: 20px;
            height: 20px;
            cursor: pointer;
            accent-color: #00d4ff;
        }}
        
        .checkbox-group label {{
            cursor: pointer;
            font-size: 0.95em;
            user-select: none;
        }}
        
        .welcome-screen {{
            background: rgba(255, 255, 255, 0.03);
            padding: 80px 40px;
            border-radius: 15px;
            text-align: center;
            border: 2px dashed rgba(255, 255, 255, 0.2);
        }}
        
        .welcome-screen.hidden {{
            display: none;
        }}
        
        .welcome-icon {{
            font-size: 5em;
            margin-bottom: 20px;
        }}
        
        .welcome-screen h3 {{
            font-size: 2em;
            color: #00d4ff;
            margin-bottom: 15px;
        }}
        
        .welcome-screen p {{
            font-size: 1.2em;
            color: #888;
            margin-bottom: 10px;
        }}
        
        .loader {{
            display: none;
            text-align: center;
            padding: 80px 40px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 15px;
            border: 2px solid rgba(0, 212, 255, 0.3);
        }}
        
        .loader.active {{
            display: block;
        }}
        
        .spinner {{
            border: 5px solid rgba(255, 255, 255, 0.1);
            border-top: 5px solid #00d4ff;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            animation: spin 1s linear infinite;
            margin: 0 auto 25px;
        }}
        
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        
        .loader-text {{
            color: #00d4ff;
            font-size: 1.3em;
            font-weight: 500;
            margin-bottom: 10px;
        }}
        
        .results-container {{
            display: none;
        }}
        
        .results-container.active {{
            display: block;
        }}
        
        .period-info {{
            background: rgba(255, 255, 255, 0.05);
            padding: 20px 25px;
            border-radius: 12px;
            margin-bottom: 25px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .period-info div {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 1.05em;
        }}
        
        .period-info strong {{
            color: #00d4ff;
        }}
        
        .metrics {{
            background: rgba(255, 255, 255, 0.05);
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 30px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .metrics h2 {{
            margin-bottom: 25px;
            color: #00d4ff;
            font-size: 1.6em;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
        }}
        
        .metric-card {{
            background: rgba(255, 255, 255, 0.03);
            padding: 25px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
        }}
        
        .metric-card:hover {{
            transform: translateY(-5px);
            border-color: #00d4ff;
            box-shadow: 0 8px 25px rgba(0, 212, 255, 0.3);
        }}
        
        .metric-label {{
            font-size: 0.9em;
            color: #888;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
        }}
        
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #fff;
        }}
        
        .metric-value.positive {{
            color: #00ff88;
        }}
        
        .metric-value.negative {{
            color: #ff4444;
        }}
        
        .pnl-highlight {{
            grid-column: span 2;
            background: linear-gradient(135deg, rgba(0, 212, 255, 0.15), rgba(0, 255, 136, 0.15));
            border: 2px solid;
            position: relative;
            overflow: hidden;
        }}
        
        .pnl-highlight::before {{
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
            animation: shimmer 3s infinite;
        }}
        
        @keyframes shimmer {{
            100% {{ left: 100%; }}
        }}
        
        .pnl-highlight .metric-value {{
            font-size: 2.8em;
        }}
        
        .chart-container {{
            background: rgba(255, 255, 255, 0.05);
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 25px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .chart-title {{
            font-size: 1.4em;
            color: #00d4ff;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        /* 🆕 Trades Table */
        .trades-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            font-size: 0.9em;
        }}
        
        .trades-table th {{
            background: rgba(0, 212, 255, 0.1);
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid rgba(0, 212, 255, 0.3);
            color: #00d4ff;
        }}
        
        .trades-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}
        
        .trades-table tr:hover {{
            background: rgba(255, 255, 255, 0.03);
        }}
        
        .trades-table .positive {{
            color: #00ff88;
        }}
        
        .trades-table .negative {{
            color: #ff4444;
        }}
        
        .error-message {{
            background: rgba(255, 68, 68, 0.1);
            border: 2px solid #ff4444;
            padding: 20px 25px;
            border-radius: 12px;
            margin-bottom: 25px;
            display: none;
        }}
        
        .error-message.active {{
            display: block;
        }}
        
        .error-message h3 {{
            color: #ff4444;
            margin-bottom: 10px;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .animated {{
            animation: fadeIn 0.5s ease-out;
        }}
        
        @media (max-width: 768px) {{
            h1 {{ font-size: 2em; }}
            .controls-grid {{ grid-template-columns: 1fr; }}
            .metrics-grid {{ grid-template-columns: 1fr; }}
            .pnl-highlight {{ grid-column: span 1; }}
        }}
        
        ::-webkit-scrollbar {{
            width: 10px;
        }}
        
        ::-webkit-scrollbar-track {{
            background: rgba(255, 255, 255, 0.05);
        }}
        
        ::-webkit-scrollbar-thumb {{
            background: rgba(0, 212, 255, 0.5);
            border-radius: 5px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="animated">
            <h1>🎯 Расширенная Панель Бэктестинга</h1>
            <p class="subtitle">Продвинутый Анализ с Индикаторами и Детальной Статистикой</p>
        </header>
        
        <div class="control-panel animated">
            <h2>⚙️ Конфигурация Бэктестинга</h2>
            
            <div class="controls-grid">
                <div class="control-group">
                    <label for="assetTypeSelect">🎯 Тип актива</label>
                    <select id="assetTypeSelect" onchange="updateAssetType()">
                        <option value="crypto" selected>📈 Криптовалюта</option>
                        <option value="futures">🛢️ Фьючерсы</option>
                    </select>
                </div>
                
                <div class="control-group">
                    <label for="symbolSelect" id="symbolLabel">📊 Торговая пара</label>
                    <select id="symbolSelect" onchange="checkDataWarning()">
                        {crypto_options}
                    </select>
                </div>
                
                <div class="control-group">
                    <label for="intervalSelect">⏰ Таймфрейм</label>
                    <select id="intervalSelect" onchange="checkDataWarning()">
                        {crypto_interval_options}
                    </select>
                </div>
                
                <div class="control-group">
                    <label for="strategySelect">🎯 Стратегия</label>
                    <select id="strategySelect" onchange="updateStrategyDescription()">
                        {strategy_options}
                    </select>
                    <div class="strategy-description" id="strategyDescription">
                        {default_description}
                    </div>
                </div>
                
                <div class="control-group">
                    <label for="capitalInput">💰 Начальный капитал ($)</label>
                    <input type="number" id="capitalInput" value="10000" min="100" step="100">
                </div>
            </div>
            
            <div class="warning-box" id="dataWarning"></div>
            
            <div class="button-group">
                <button class="btn btn-primary" id="runBacktestBtn" onclick="runBacktest()">
                    <span>🚀</span>
                    <span>Запустить Бэктест</span>
                </button>
                <button class="btn btn-secondary" id="exportBtn" onclick="exportResults()" disabled>
                    <span>💾</span>
                    <span>Экспорт</span>
                </button>
                <button class="btn btn-secondary" id="shareBtn" onclick="shareReport()" disabled>
                    <span>🔗</span>
                    <span>Поделиться</span>
                </button>
            </div>
        </div>
        
        <div class="welcome-screen" id="welcomeScreen">
            <div class="welcome-icon">📊</div>
            <h3>Добро пожаловать в Расширенную Панель</h3>
            <p>✅ Японские свечи + индикаторы MA/EMA</p>
            <p>✅ График объема и просадки</p>
            <p>✅ Детальная таблица сделок</p>
            <p>✅ Сравнение с Buy & Hold</p>
            <p style="margin-top: 20px; color: #666;">💡 Нажмите "Запустить Бэктест" для начала</p>
        </div>
        
        <div class="loader" id="loader">
            <div class="spinner"></div>
            <div class="loader-text">🔄 Выполняется Бэктестинг...</div>
        </div>
        
        <div class="error-message" id="errorMessage">
            <h3>❌ Ошибка</h3>
            <p id="errorText"></p>
        </div>
        
        <div class="results-container" id="resultsContainer">
            <div class="period-info animated" id="periodInfo"></div>
            
            <div class="metrics animated">
                <h2>📊 Метрики Производительности</h2>
                <div class="metrics-grid" id="metricsGrid"></div>
            </div>
            
            <div class="chart-container animated">
                <div class="chart-title">🕯️ Цена, Индикаторы и Сигналы</div>
                <div class="chart-controls">
                    <div class="checkbox-group">
                        <input type="checkbox" id="showBuyEntries" checked onchange="updateChartVisibility()">
                        <label for="showBuyEntries">▲ Покупки</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" id="showSellEntries" checked onchange="updateChartVisibility()">
                        <label for="showSellEntries">▼ Продажи</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" id="showWinningExits" checked onchange="updateChartVisibility()">
                        <label for="showWinningExits">● Прибыльные выходы</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" id="showLosingExits" checked onchange="updateChartVisibility()">
                        <label for="showLosingExits">● Убыточные выходы</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" id="showMA20" checked onchange="updateChartVisibility()">
                        <label for="showMA20">━ MA(20)</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" id="showEMA50" checked onchange="updateChartVisibility()">
                        <label for="showEMA50">━ EMA(50)</label>
                    </div>
                </div>
                <div id="priceChart" style="width: 100%; height: 700px;"></div>
            </div>
            
            <div class="chart-container animated">
                <div class="chart-title">💰 Кривая Капитала vs Buy & Hold</div>
                <div id="equityChart" style="width: 100%; height: 350px;"></div>
            </div>
            
            <div class="chart-container animated">
                <div class="chart-title">📉 График Просадки</div>
                <div id="drawdownChart" style="width: 100%; height: 300px;"></div>
            </div>
            
            <div class="chart-container animated">
                <div class="chart-title">📊 Распределение PnL</div>
                <div id="pnlHistChart" style="width: 100%; height: 350px;"></div>
            </div>
            
            <div class="chart-container animated">
                <div class="chart-title">📋 Детальная Таблица Сделок</div>
                <div style="overflow-x: auto;">
                    <table class="trades-table" id="tradesTable">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Вход</th>
                                <th>Выход</th>
                                <th>Тип</th>
                                <th>Цена входа</th>
                                <th>Цена выхода</th>
                                <th>PnL ($)</th>
                                <th>PnL (%)</th>
                                <th>Длительность</th>
                            </tr>
                        </thead>
                        <tbody id="tradesTableBody">
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentBacktestData = null;
        let priceChartInstance = null;
        
        const ASSET_CONFIG = {{
            crypto: {{
                symbols: {json.dumps([s for s in ReportGenerator.CRYPTO_SYMBOLS])},
                intervals: {json.dumps([i["value"] for i in ReportGenerator.CRYPTO_INTERVALS])},
                intervalLabels: {json.dumps({i["value"]: i["label"] for i in ReportGenerator.CRYPTO_INTERVALS})}
            }},
            futures: {{
                symbols: {json.dumps([s for s in ReportGenerator.FUTURES_SYMBOLS])},
                intervals: {json.dumps([i["value"] for i in ReportGenerator.FUTURES_INTERVALS])},
                intervalLabels: {json.dumps({i["value"]: i["label"] for i in ReportGenerator.FUTURES_INTERVALS})}
            }}
        }};
        
        const DATA_WARNINGS = {warnings_json};
        
        function updateAssetType() {{
            const assetType = document.getElementById('assetTypeSelect').value;
            const symbolSelect = document.getElementById('symbolSelect');
            const intervalSelect = document.getElementById('intervalSelect');
            const symbolLabel = document.getElementById('symbolLabel');
            
            symbolLabel.innerHTML = assetType === 'crypto' ? '📊 Торговая пара' : '🛢️ Фьючерсный контракт';
            
            symbolSelect.innerHTML = '';
            ASSET_CONFIG[assetType].symbols.forEach(symbol => {{
                const option = document.createElement('option');
                option.value = symbol;
                option.textContent = symbol;
                symbolSelect.appendChild(option);
            }});
            
            intervalSelect.innerHTML = '';
            ASSET_CONFIG[assetType].intervals.forEach(interval => {{
                const option = document.createElement('option');
                option.value = interval;
                option.textContent = ASSET_CONFIG[assetType].intervalLabels[interval];
                if (interval === '1h') option.selected = true;
                intervalSelect.appendChild(option);
            }});
            
            checkDataWarning();
        }}
        
        function checkDataWarning() {{
            const symbol = document.getElementById('symbolSelect').value;
            const interval = document.getElementById('intervalSelect').value;
            const warningBox = document.getElementById('dataWarning');
            
            if (DATA_WARNINGS[symbol] && DATA_WARNINGS[symbol].intervals.includes(interval)) {{
                warningBox.innerHTML = `<strong>⚠️ Ограничение данных</strong>${{DATA_WARNINGS[symbol].message}}`;
                warningBox.classList.add('active');
            }} else {{
                warningBox.classList.remove('active');
            }}
        }}
        
        function updateStrategyDescription() {{
            const select = document.getElementById('strategySelect');
            const description = select.options[select.selectedIndex].getAttribute('data-description');
            document.getElementById('strategyDescription').textContent = description || 'Описание недоступно';
        }}
        
        async function runBacktest() {{
            const assetType = document.getElementById('assetTypeSelect').value;
            const symbol = document.getElementById('symbolSelect').value;
            const interval = document.getElementById('intervalSelect').value;
            const strategy = document.getElementById('strategySelect').value;
            const capital = parseFloat(document.getElementById('capitalInput').value);
            
            if (capital < 100) {{
                showError('Начальный капитал должен быть не менее $100');
                return;
            }}
            
            hideError();
            document.getElementById('welcomeScreen').classList.add('hidden');
            document.getElementById('resultsContainer').classList.remove('active');
            document.getElementById('loader').classList.add('active');
            document.getElementById('runBacktestBtn').disabled = true;
            document.getElementById('exportBtn').disabled = true;
            document.getElementById('shareBtn').disabled = true;
            
            try {{
                const response = await fetch('/backtest/run', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        asset_type: assetType,
                        symbol: symbol,
                        interval: interval,
                        strategy: strategy,
                        initial_capital: capital
                    }})
                }});
                
                if (!response.ok) {{
                    const error = await response.json();
                    throw new Error(error.message || 'Ошибка бэктестинга');
                }}
                
                const data = await response.json();
                currentBacktestData = data;
                
                displayResults(data);
                updateURL(assetType, symbol, interval, strategy, capital);
                
                document.getElementById('exportBtn').disabled = false;
                document.getElementById('shareBtn').disabled = false;
                
            }} catch (error) {{
                console.error('Error:', error);
                showError(error.message);
            }} finally {{
                document.getElementById('loader').classList.remove('active');
                document.getElementById('runBacktestBtn').disabled = false;
            }}
        }}
        
        function displayResults(data) {{
            document.getElementById('resultsContainer').classList.add('active');
            
            // Period Info
            document.getElementById('periodInfo').innerHTML = `
                <div><strong>📅 Период:</strong> <span>${{data.start_date}} — ${{data.end_date}}</span></div>
                <div><strong>⏱️ Длительность:</strong> <span>${{data.duration_days}} дней</span></div>
                <div><strong>📊 Сделок:</strong> <span>${{data.total_trades}}</span></div>
                <div><strong>🎯 Символ:</strong> <span>${{data.symbol}} (${{data.interval}})</span></div>
                <div><strong>🧠 Стратегия:</strong> <span>${{data.strategy_name || 'Momentum'}}</span></div>
            `;
            
            // Metrics with Buy & Hold
            const pnlColor = data.total_pnl > 0 ? '#00ff88' : '#ff4444';
            const pnlClass = data.total_pnl > 0 ? 'positive' : 'negative';
            const pnlEmoji = data.total_pnl > 0 ? '📈' : '📉';
            const bhClass = data.buy_hold_pnl_percent > 0 ? 'positive' : 'negative';
            
            document.getElementById('metricsGrid').innerHTML = `
                <div class="metric-card pnl-highlight" style="border-color: ${{pnlColor}};">
                    <div class="metric-label">${{pnlEmoji}} Стратегия PnL</div>
                    <div class="metric-value ${{pnlClass}}">
                        $${{data.total_pnl.toLocaleString('ru-RU', {{minimumFractionDigits: 2}})}}
                        <span style="font-size: 0.5em;">(${{data.total_pnl_percent > 0 ? '+' : ''}}${{data.total_pnl_percent.toFixed(2)}}%)</span>
                    </div>
                </div>
                
                <div class="metric-card" style="border-color: ${{data.buy_hold_pnl_percent > 0 ? '#00ff88' : '#ff4444'}};">
                    <div class="metric-label">📊 Buy & Hold PnL</div>
                    <div class="metric-value ${{bhClass}}">
                        $${{data.buy_hold_pnl.toLocaleString('ru-RU', {{minimumFractionDigits: 2}})}}
                        <span style="font-size: 0.5em;">(${{data.buy_hold_pnl_percent > 0 ? '+' : ''}}${{data.buy_hold_pnl_percent.toFixed(2)}}%)</span>
                    </div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Начальный Капитал</div>
                    <div class="metric-value">$${{data.initial_capital.toLocaleString('ru-RU')}}</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Конечный Капитал</div>
                    <div class="metric-value">$${{data.final_capital.toLocaleString('ru-RU', {{minimumFractionDigits: 2}})}}</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Процент Побед</div>
                    <div class="metric-value positive">${{data.win_rate.toFixed(1)}}%</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Фактор Прибыли</div>
                    <div class="metric-value ${{data.profit_factor > 1 ? 'positive' : 'negative'}}">
                        ${{data.profit_factor.toFixed(2)}}
                    </div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Макс. Просадка</div>
                    <div class="metric-value negative">${{data.max_drawdown.toFixed(2)}}%</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Прибыльных Сделок</div>
                    <div class="metric-value positive">${{data.winning_trades}}</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Убыточных Сделок</div>
                    <div class="metric-value negative">${{data.losing_trades}}</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Средняя Прибыль</div>
                    <div class="metric-value positive">$${{data.avg_win.toFixed(2)}}</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Средний Убыток</div>
                    <div class="metric-value negative">$${{Math.abs(data.avg_loss).toFixed(2)}}</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Наибольшая Прибыль</div>
                    <div class="metric-value positive">$${{data.largest_win.toFixed(2)}}</div>
                </div>
            `;
            
            renderPriceChart(data);
            renderEquityChart(data);
            renderDrawdownChart(data);
            renderPnLHistogram(data);
            renderTradesTable(data);
            
            document.getElementById('resultsContainer').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        }}
        
        function renderPriceChart(data) {{
            const traces = [];
            
            // Candlesticks
            traces.push({{
                type: 'candlestick',
                x: data.price_times,
                open: data.candles_open,
                high: data.candles_high,
                low: data.candles_low,
                close: data.candles_close,
                name: 'Цена',
                visible: true,
                increasing: {{ line: {{ color: '#00ff88', width: 1 }}, fillcolor: 'rgba(0, 255, 136, 0.3)' }},
                decreasing: {{ line: {{ color: '#ff4444', width: 1 }}, fillcolor: 'rgba(255, 68, 68, 0.3)' }},
                hoverinfo: 'x+y'
            }});
            
            // MA(20)
            if (data.ma20) {{
                traces.push({{
                    x: data.price_times,
                    y: data.ma20,
                    mode: 'lines',
                    name: 'MA(20)',
                    line: {{ color: '#ffa500', width: 2 }},
                    visible: true,
                    hovertemplate: 'MA(20): %{{y:,.2f}}<extra></extra>'
                }});
            }}
            
            // EMA(50)
            if (data.ema50) {{
                traces.push({{
                    x: data.price_times,
                    y: data.ema50,
                    mode: 'lines',
                    name: 'EMA(50)',
                    line: {{ color: '#9c27b0', width: 2 }},
                    visible: true,
                    hovertemplate: 'EMA(50): %{{y:,.2f}}<extra></extra>'
                }});
            }}
            
            // Buy entries
            if (data.buy_entries.length > 0) {{
                traces.push({{
                    x: data.buy_entries.map(t => t.time),
                    y: data.buy_entries.map(t => t.price),
                    mode: 'markers',
                    name: 'Покупка',
                    visible: true,
                    marker: {{ color: '#00ff88', size: 14, symbol: 'triangle-up', line: {{ width: 2, color: '#000' }} }},
                    hovertemplate: 'Покупка: %{{y:,.2f}}<extra></extra>'
                }});
            }}
            
            // Sell entries
            if (data.sell_entries.length > 0) {{
                traces.push({{
                    x: data.sell_entries.map(t => t.time),
                    y: data.sell_entries.map(t => t.price),
                    mode: 'markers',
                    name: 'Продажа',
                    visible: true,
                    marker: {{ color: '#ff4444', size: 14, symbol: 'triangle-down', line: {{ width: 2, color: '#000' }} }},
                    hovertemplate: 'Продажа: %{{y:,.2f}}<extra></extra>'
                }});
            }}
            
            // Winning exits
            if (data.winning_exits.length > 0) {{
                traces.push({{
                    x: data.winning_exits.map(t => t.time),
                    y: data.winning_exits.map(t => t.price),
                    mode: 'markers',
                    name: 'Прибыльный Выход',
                    visible: true,
                    marker: {{ color: '#00ff88', size: 10, symbol: 'circle', line: {{ width: 1, color: '#fff' }} }},
                    customdata: data.winning_exits.map(t => t.pnl_percent),
                    hovertemplate: 'Выход: %{{y:,.2f}}<br>PnL: +%{{customdata:.2f}}%<extra></extra>'
                }});
            }}
            
            // Losing exits
            if (data.losing_exits.length > 0) {{
                traces.push({{
                    x: data.losing_exits.map(t => t.time),
                    y: data.losing_exits.map(t => t.price),
                    mode: 'markers',
                    name: 'Убыточный Выход',
                    visible: true,
                    marker: {{ color: '#ff4444', size: 10, symbol: 'circle', line: {{ width: 1, color: '#fff' }} }},
                    customdata: data.losing_exits.map(t => t.pnl_percent),
                    hovertemplate: 'Выход: %{{y:,.2f}}<br>PnL: %{{customdata:.2f}}%<extra></extra>'
                }});
            }}
            
            const layout = {{
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(255,255,255,0.02)',
                font: {{ color: '#e0e0e0' }},
                xaxis: {{ title: 'Время', gridcolor: 'rgba(255,255,255,0.1)', rangeslider: {{ visible: false }} }},
                yaxis: {{ title: 'Цена (USDT)', gridcolor: 'rgba(255,255,255,0.1)' }},
                hovermode: 'x unified',
                showlegend: true,
                legend: {{ bgcolor: 'rgba(0,0,0,0.5)', bordercolor: 'rgba(255,255,255,0.2)', borderwidth: 1 }},
                margin: {{ t: 20, b: 50, l: 60, r: 20 }}
            }};
            
            const config = {{ displayModeBar: true, displaylogo: false }};
            
            Plotly.newPlot('priceChart', traces, layout, config);
            priceChartInstance = {{ data: traces, layout: layout }};
        }}
        
        function updateChartVisibility() {{
            if (!priceChartInstance) return;
            
            const visibility = {{
                'Цена': true,
                'MA(20)': document.getElementById('showMA20').checked,
                'EMA(50)': document.getElementById('showEMA50').checked,
                'Покупка': document.getElementById('showBuyEntries').checked,
                'Продажа': document.getElementById('showSellEntries').checked,
                'Прибыльный Выход': document.getElementById('showWinningExits').checked,
                'Убыточный Выход': document.getElementById('showLosingExits').checked
            }};
            
            const update = {{
                visible: priceChartInstance.data.map(trace => visibility[trace.name] !== false)
            }};
            
            Plotly.restyle('priceChart', update);
        }}
        
        function renderEquityChart(data) {{
            const strategyColor = data.total_pnl > 0 ? '#00ff88' : '#ff4444';
            const strategyFill = data.total_pnl > 0 ? 'rgba(0, 255, 136, 0.1)' : 'rgba(255, 68, 68, 0.1)';
            
            const traces = [
                {{
                    x: data.equity_times,
                    y: data.equity_values,
                    mode: 'lines',
                    name: 'Стратегия',
                    fill: 'tozeroy',
                    fillcolor: strategyFill,
                    line: {{ color: strategyColor, width: 2 }},
                    hovertemplate: 'Стратегия: $%{{y:,.2f}}<extra></extra>'
                }},
                {{
                    x: data.buy_hold_times,
                    y: data.buy_hold_values,
                    mode: 'lines',
                    name: 'Buy & Hold',
                    line: {{ color: '#00d4ff', width: 2, dash: 'dash' }},
                    hovertemplate: 'Buy & Hold: $%{{y:,.2f}}<extra></extra>'
                }}
            ];
            
            const layout = {{
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(255,255,255,0.02)',
                font: {{ color: '#e0e0e0' }},
                xaxis: {{ title: 'Время', gridcolor: 'rgba(255,255,255,0.1)' }},
                yaxis: {{ title: 'Капитал ($)', gridcolor: 'rgba(255,255,255,0.1)' }},
                hovermode: 'x unified',
                showlegend: true,
                legend: {{ bgcolor: 'rgba(0,0,0,0.5)', bordercolor: 'rgba(255,255,255,0.2)', borderwidth: 1 }},
                margin: {{ t: 20, b: 50, l: 60, r: 20 }}
            }};
            
            const config = {{ displayModeBar: true, displaylogo: false }};
            Plotly.newPlot('equityChart', traces, layout, config);
        }}
        
        function renderDrawdownChart(data) {{
            const trace = {{
                x: data.drawdown_times,
                y: data.drawdown_values,
                mode: 'lines',
                name: 'Просадка',
                fill: 'tozeroy',
                fillcolor: 'rgba(255, 68, 68, 0.2)',
                line: {{ color: '#ff4444', width: 2 }},
                hovertemplate: 'Просадка: %{{y:.2f}}%<extra></extra>'
            }};
            
            const layout = {{
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(255,255,255,0.02)',
                font: {{ color: '#e0e0e0' }},
                xaxis: {{ title: 'Время', gridcolor: 'rgba(255,255,255,0.1)' }},
                yaxis: {{ title: 'Просадка (%)', gridcolor: 'rgba(255,255,255,0.1)' }},
                hovermode: 'x unified',
                showlegend: false,
                margin: {{ t: 20, b: 50, l: 60, r: 20 }}
            }};
            
            const config = {{ displayModeBar: true, displaylogo: false }};
            Plotly.newPlot('drawdownChart', [trace], layout, config);
        }}
        
        function renderPnLHistogram(data) {{
            const trace = {{
                x: data.pnl_distribution,
                type: 'histogram',
                name: 'PnL',
                marker: {{
                    color: data.pnl_distribution.map(v => v > 0 ? '#00ff88' : '#ff4444')
                }},
                hovertemplate: 'PnL: $%{{x:.2f}}<br>Сделок: %{{y}}<extra></extra>'
            }};
            
            const layout = {{
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(255,255,255,0.02)',
                font: {{ color: '#e0e0e0' }},
                xaxis: {{ title: 'PnL ($)', gridcolor: 'rgba(255,255,255,0.1)' }},
                yaxis: {{ title: 'Количество сделок', gridcolor: 'rgba(255,255,255,0.1)' }},
                showlegend: false,
                margin: {{ t: 20, b: 50, l: 60, r: 20 }}
            }};
            
            const config = {{ displayModeBar: true, displaylogo: false }};
            Plotly.newPlot('pnlHistChart', [trace], layout, config);
        }}
        
        function renderTradesTable(data) {{
            const tbody = document.getElementById('tradesTableBody');
            tbody.innerHTML = '';
            
            if (!data.trades_list || data.trades_list.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: #888;">Нет сделок</td></tr>';
                return;
            }}
            
            data.trades_list.forEach((trade, idx) => {{
                const row = document.createElement('tr');
                const pnlClass = trade.pnl > 0 ? 'positive' : 'negative';
                
                row.innerHTML = `
                    <td>${{idx + 1}}</td>
                    <td>${{new Date(trade.entry_time).toLocaleString('ru-RU')}}</td>
                    <td>${{trade.exit_time ? new Date(trade.exit_time).toLocaleString('ru-RU') : 'Открыта'}}</td>
                    <td>${{trade.side}}</td>
                    <td>$${{trade.entry_price.toFixed(2)}}</td>
                    <td>$${{trade.exit_price ? trade.exit_price.toFixed(2) : '-'}}</td>
                    <td class="${{pnlClass}}">$${{trade.pnl.toFixed(2)}}</td>
                    <td class="${{pnlClass}}">${{trade.pnl_percent > 0 ? '+' : ''}}${{trade.pnl_percent.toFixed(2)}}%</td>
                    <td>${{trade.duration || '-'}}</td>
                `;
                tbody.appendChild(row);
            }});
        }}
        
        function exportResults() {{
            if (!currentBacktestData) return;
            const dataStr = JSON.stringify(currentBacktestData, null, 2);
            const blob = new Blob([dataStr], {{ type: 'application/json' }});
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `backtest_${{currentBacktestData.symbol}}_${{currentBacktestData.interval}}_${{new Date().toISOString().split('T')[0]}}.json`;
            link.click();
            URL.revokeObjectURL(url);
        }}
        
        function shareReport() {{
            const url = window.location.href;
            if (navigator.share) {{
                navigator.share({{ title: 'Отчет о Бэктестинге', url: url }}).catch(err => console.log(err));
            }} else {{
                navigator.clipboard.writeText(url).then(() => alert('✅ Ссылка скопирована!'));
            }}
        }}
        
        function updateURL(assetType, symbol, interval, strategy, capital) {{
            const url = new URL(window.location.href);
            url.searchParams.set('asset_type', assetType);
            url.searchParams.set('symbol', symbol);
            url.searchParams.set('interval', interval);
            url.searchParams.set('strategy', strategy);
            url.searchParams.set('capital', capital);
            window.history.pushState({{}}, '', url);
        }}
        
        function showError(message) {{
            document.getElementById('errorText').textContent = message;
            document.getElementById('errorMessage').classList.add('active');
            setTimeout(() => document.getElementById('errorMessage').classList.remove('active'), 5000);
        }}
        
        function hideError() {{
            document.getElementById('errorMessage').classList.remove('active');
        }}
        
        document.addEventListener('keydown', function(e) {{
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {{
                e.preventDefault();
                runBacktest();
            }}
        }});
        
        window.addEventListener('DOMContentLoaded', function() {{
            updateStrategyDescription();
            
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.has('asset_type')) {{
                document.getElementById('assetTypeSelect').value = urlParams.get('asset_type');
                updateAssetType();
            }}
            if (urlParams.has('symbol')) document.getElementById('symbolSelect').value = urlParams.get('symbol');
            if (urlParams.has('interval')) document.getElementById('intervalSelect').value = urlParams.get('interval');
            if (urlParams.has('strategy')) {{
                document.getElementById('strategySelect').value = urlParams.get('strategy');
                updateStrategyDescription();
            }}
            if (urlParams.has('capital')) document.getElementById('capitalInput').value = urlParams.get('capital');
            
            checkDataWarning();
            
            if (urlParams.has('symbol') && urlParams.has('interval')) {{
                setTimeout(() => runBacktest(), 500);
            }}
        }});
    </script>
</body>
</html>
"""
        
        return html
    
    @staticmethod
    def generate_backtest_json(result) -> Dict[str, Any]:
        """Генерирует JSON данные для клиента с расширенными метриками"""
        logger.info("📊 Генерация расширенных JSON данных...")
        
        try:
            # OHLC данные
            price_times = [c["open_time"] for c in result.candles_data]
            candles_open = [float(c["open"]) for c in result.candles_data]
            candles_high = [float(c["high"]) for c in result.candles_data]
            candles_low = [float(c["low"]) for c in result.candles_data]
            candles_close = [float(c["close"]) for c in result.candles_data]
            
            # Индикаторы MA(20) и EMA(50)
            ma20 = ReportGenerator._calculate_ma(candles_close, 20)
            ema50 = ReportGenerator._calculate_ema(candles_close, 50)
            
            # Торговые сигналы
            buy_entries = []
            sell_entries = []
            winning_exits = []
            losing_exits = []
            trades_list = []
            pnl_distribution = []
            
            for trade in result.trades:
                entry_time_str = trade.entry_time.isoformat() if hasattr(trade.entry_time, 'isoformat') else str(trade.entry_time)
                entry_data = {"time": entry_time_str, "price": float(trade.entry_price)}
                
                if trade.side == "BUY":
                    buy_entries.append(entry_data)
                else:
                    sell_entries.append(entry_data)
                
                if not trade.is_open and trade.exit_time:
                    exit_time_str = trade.exit_time.isoformat() if hasattr(trade.exit_time, 'isoformat') else str(trade.exit_time)
                    exit_data = {"time": exit_time_str, "price": float(trade.exit_price), "pnl_percent": float(trade.pnl_percent)}
                    
                    if trade.pnl > 0:
                        winning_exits.append(exit_data)
                    else:
                        losing_exits.append(exit_data)
                    
                    # Для таблицы и гистограммы
                    pnl_distribution.append(float(trade.pnl))
                    
                    duration = (trade.exit_time - trade.entry_time).total_seconds() / 3600 if hasattr(trade.exit_time, 'total_seconds') else 0
                    trades_list.append({
                        "entry_time": entry_time_str,
                        "exit_time": exit_time_str,
                        "side": trade.side,
                        "entry_price": float(trade.entry_price),
                        "exit_price": float(trade.exit_price),
                        "pnl": float(trade.pnl),
                        "pnl_percent": float(trade.pnl_percent),
                        "duration": f"{duration:.1f}h"
                    })
            
            # Equity curve
            equity_times = [e["timestamp"] for e in result.equity_curve]
            equity_values = [e["equity"] for e in result.equity_curve]
            
            # Buy & Hold расчет
            initial_price = candles_close[0]
            final_price = candles_close[-1]
            buy_hold_final = result.initial_capital * (final_price / initial_price)
            buy_hold_pnl = buy_hold_final - result.initial_capital
            buy_hold_pnl_percent = (buy_hold_pnl / result.initial_capital) * 100
            
            buy_hold_times = price_times
            buy_hold_values = [result.initial_capital * (price / initial_price) for price in candles_close]
            
            # Drawdown расчет
            drawdown_times = equity_times
            drawdown_values = []
            peak = equity_values[0]
            for equity in equity_values:
                if equity > peak:
                    peak = equity
                dd = ((peak - equity) / peak) * 100 if peak > 0 else 0
                drawdown_values.append(-dd)
            
            json_data = {
                "status": "success",
                "symbol": result.candles_data[0]["symbol"] if result.candles_data else "UNKNOWN",
                "interval": result.candles_data[0]["interval"] if result.candles_data else "UNKNOWN",
                "start_date": result.start_time.strftime('%Y-%m-%d') if hasattr(result.start_time, 'strftime') else str(result.start_time),
                "end_date": result.end_time.strftime('%Y-%m-%d') if hasattr(result.end_time, 'strftime') else str(result.end_time),
                "duration_days": result.duration_days,
                "strategy_name": "Momentum Strategy",
                
                # Метрики стратегии
                "initial_capital": float(result.initial_capital),
                "final_capital": float(result.final_capital),
                "total_pnl": float(result.total_pnl),
                "total_pnl_percent": float(result.total_pnl_percent),
                "win_rate": float(result.win_rate),
                "profit_factor": float(result.profit_factor),
                "max_drawdown": float(result.max_drawdown),
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "avg_win": float(result.avg_win),
                "avg_loss": float(result.avg_loss),
                "largest_win": float(result.largest_win),
                "largest_loss": float(result.largest_loss),
                
                # Buy & Hold метрики
                "buy_hold_pnl": float(buy_hold_pnl),
                "buy_hold_pnl_percent": float(buy_hold_pnl_percent),
                "buy_hold_times": buy_hold_times,
                "buy_hold_values": buy_hold_values,
                
                # OHLC + индикаторы
                "price_times": price_times,
                "candles_open": candles_open,
                "candles_high": candles_high,
                "candles_low": candles_low,
                "candles_close": candles_close,
                "ma20": ma20,
                "ema50": ema50,
                
                # Торговые сигналы
                "buy_entries": buy_entries,
                "sell_entries": sell_entries,
                "winning_exits": winning_exits,
                "losing_exits": losing_exits,
                
                # Дополнительные данные
                "equity_times": equity_times,
                "equity_values": equity_values,
                "drawdown_times": drawdown_times,
                "drawdown_values": drawdown_values,
                "pnl_distribution": pnl_distribution,
                "trades_list": trades_list
            }
            
            logger.info("✅ Расширенные JSON данные готовы")
            logger.debug(f"   • Свечей: {len(candles_close)}")
            logger.debug(f"   • Сделок: {len(trades_list)}")
            logger.debug(f"   • Buy&Hold PnL: {buy_hold_pnl_percent:+.2f}%")
            
            return json_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации JSON: {e}")
            raise
    
    @staticmethod
    def _calculate_ma(prices: List[float], period: int) -> List[float]:
        """Рассчитывает простую скользящую среднюю (MA)"""
        ma = []
        for i in range(len(prices)):
            if i < period - 1:
                ma.append(None)
            else:
                ma.append(sum(prices[i-period+1:i+1]) / period)
        return ma
    
    @staticmethod
    def _calculate_ema(prices: List[float], period: int) -> List[float]:
        """Рассчитывает экспоненциальную скользящую среднюю (EMA)"""
        ema = []
        multiplier = 2 / (period + 1)
        
        # Первое значение EMA = SMA
        sma = sum(prices[:period]) / period
        ema.append(None if len(prices) < period else sma)
        
        for i in range(1, len(prices)):
            if i < period - 1:
                ema.append(None)
            elif i == period - 1:
                ema.append(sma)
            else:
                ema_value = (prices[i] - ema[i-1]) * multiplier + ema[i-1]
                ema.append(ema_value)
        
        return ema
    
    @staticmethod
    def generate_html_report(result, current_params: Optional[Dict[str, Any]] = None) -> str:
        """DEPRECATED"""
        logger.warning("⚠️ generate_html_report() deprecated")
        return ReportGenerator.generate_dashboard_html()


__all__ = ["ReportGenerator"]
