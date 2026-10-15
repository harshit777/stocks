#!/usr/bin/env python3
"""
Modern Portfolio Dashboard with FastAPI
Dark theme with sleek design inspired by modern analytics platforms
"""
import os
import warnings
warnings.filterwarnings('ignore', message='.*NotOpenSSLWarning.*')
warnings.filterwarnings('ignore', category=Warning, module='urllib3')
from datetime import datetime, timedelta
from typing import Dict, List
from collections import deque
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import pytz
import threading
import json

# Load environment — .env lives at project root (two levels up from src/web/)
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(env_path, override=True)

app = FastAPI(title="Portfolio Dashboard")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# In-memory storage for portfolio history (last 2 hours)
portfolio_history = deque(maxlen=240)  # 2 hours at 30-second intervals = 240 points

# In-memory storage for AI training status
training_status = {
    'state': 'idle',  # idle, running, completed, error
    'progress': 0,
    'current_step': '',
    'stats': {
        'total_candles': 0,
        'patterns_detected': 0,
        'predictions_made': 0,
        'successful_predictions': 0
    },
    'error': None
}
training_history = []
training_thread = None

# Paper trading state
paper_trading_status = {
    'state': 'idle',  # idle, running, stopped, error
    'start_time': None,
    'iterations': 0,
    'last_update': None,
    'error': None
}
paper_trading_thread = None
paper_trading_logs = deque(maxlen=100)  # Keep last 100 log entries

# ── ML training state ─────────────────────────────────────────────────────────
ml_train_status = {
    'state': 'idle',       # idle | running | completed | error
    'progress': 0,
    'step': '',
    'error': None,
    'metadata': None,      # populated on completion
}
ml_train_thread = None

# ── Live trading agent state ──────────────────────────────────────────────────
live_trading_status = {
    'state': 'idle',          # idle | running | stopping | stopped | error
    'start_time': None,
    'iteration': 0,
    'last_update': None,
    'error': None,
    'mode': 'paper',          # paper | live
}
live_trading_logs: deque = deque(maxlen=500)
live_trading_thread = None

# Shared agent state written by the background thread, read by API
live_agent_state: Dict = {
    'watchlist': [],
    'watchlist_scores': [],  # [{symbol, composite_score, vol_surge, gap_pct, day_range_pct, price_momentum}]
    'signals': {},           # symbol → 'BUY'/'SELL'/None
    'positions': {},         # symbol → {qty, avg_price, unrealised_pnl, pnl_pct}
    'risk': {
        'available_capital': 0, 'used_capital': 0,
        'daily_pnl': 0, 'halted': False, 'halt_reason': '',
        'open_positions': 0, 'trades_today': 0,
    },
    'post_trade': {
        'daily_pnl': 0, 'daily_trades': 0,
        'daily_wins': 0, 'daily_losses': 0, 'win_rate': 0,
    },
    'pnl_history': deque(maxlen=180),  # (timestamp, pnl) — 6 hrs @ 2-min ticks
}


def get_trader():
    """Get KiteTrader instance"""
    try:
        from src.kite_trader.trader import KiteTrader
        trader = KiteTrader()
        if trader.is_connected():
            return trader
        return None
    except Exception as e:
        print(f"Error initializing trader: {e}")
        return None


@app.get("/")
async def home(request: Request):
    """Render main dashboard"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/holdings")
async def holdings(request: Request):
    """Render holdings page"""
    return templates.TemplateResponse("holdings.html", {"request": request})


@app.get("/positions")
async def positions(request: Request):
    """Render positions page"""
    return templates.TemplateResponse("positions.html", {"request": request})


@app.get("/dashboard")
async def dashboard_page(request: Request):
    """Render dashboard page"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/funds")
async def funds_page(request: Request):
    """Render funds page"""
    return templates.TemplateResponse("funds.html", {"request": request})


@app.get("/ai-training")
async def ai_training_page(request: Request):
    """Render AI training page"""
    return templates.TemplateResponse("ai_training_integrated.html", {"request": request})


@app.get("/api/portfolio-data")
async def get_portfolio_data() -> Dict:
    """Get portfolio data formatted for dashboard.html"""
    trader = get_trader()
    
    if not trader:
        return {
            "error": "Unable to connect to Zerodha"
        }
    
    try:
        holdings = trader.get_holdings()
        positions = trader.get_positions()
        
        # Process holdings
        holdings_list = []
        total_value = 0
        total_pnl = 0
        total_invested = 0
        
        for holding in holdings:
            qty = holding.get('quantity', 0)
            if qty <= 0:
                continue
            
            avg = holding.get('average_price', 0)
            ltp = holding.get('last_price', 0)
            pnl = holding.get('pnl', 0)
            value = qty * ltp
            invested = qty * avg
            
            total_value += value
            total_pnl += pnl
            total_invested += invested
            
            holdings_list.append({
                'symbol': holding.get('tradingsymbol', 'N/A'),
                'quantity': int(qty),
                'avg_price': round(avg, 2),
                'last_price': round(ltp, 2),
                'current_value': round(value, 2),
                'pnl': round(pnl, 2),
                'pnl_percent': round((pnl / invested * 100) if invested > 0 else 0, 2)
            })
        
        # Sort by value
        holdings_list.sort(key=lambda x: x['current_value'], reverse=True)
        
        # Calculate metrics
        total_pnl_percent = (total_pnl / total_invested * 100) if total_invested > 0 else 0
        
        # Process positions
        positions_list = []
        for pos in positions.get('net', []):
            qty = pos.get('quantity', 0)
            if qty == 0:
                continue
            
            positions_list.append({
                'symbol': pos.get('tradingsymbol', 'N/A'),
                'quantity': int(qty),
                'avg_price': round(pos.get('average_price', 0), 2),
                'last_price': round(pos.get('last_price', 0), 2),
                'pnl': round(pos.get('pnl', 0), 2),
                'type': 'Short' if qty < 0 else 'Long'
            })
        
        # Format response for dashboard.html expectations
        return {
            "holdings": {
                "total_value": round(total_value, 2),
                "total_pnl": round(total_pnl, 2),
                "total_pnl_percent": round(total_pnl_percent, 2),
                "count": len(holdings_list),
                "holdings": holdings_list
            },
            "positions": positions_list
        }
    
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/portfolio")
async def get_portfolio() -> Dict:
    """Get portfolio data"""
    trader = get_trader()
    
    if not trader:
        return {
            "success": False,
            "message": "Unable to connect to Zerodha",
            "data": None
        }
    
    try:
        holdings = trader.get_holdings()
        positions = trader.get_positions()
        
        current_time = datetime.now()
        
        # Process holdings
        holdings_list = []
        total_value = 0
        total_pnl = 0
        total_invested = 0
        
        for holding in holdings:
            qty = holding.get('quantity', 0)
            if qty <= 0:
                continue
            
            avg = holding.get('average_price', 0)
            ltp = holding.get('last_price', 0)
            pnl = holding.get('pnl', 0)
            value = qty * ltp
            invested = qty * avg
            
            total_value += value
            total_pnl += pnl
            total_invested += invested
            
            holdings_list.append({
                'symbol': holding.get('tradingsymbol', 'N/A'),
                'quantity': int(qty),
                'avg_price': round(avg, 2),
                'ltp': round(ltp, 2),
                'value': round(value, 2),
                'invested': round(invested, 2),
                'pnl': round(pnl, 2),
                'pnl_percent': round((pnl / invested * 100) if invested > 0 else 0, 2)
            })
        
        # Sort by value
        holdings_list.sort(key=lambda x: x['value'], reverse=True)
        
        # Calculate metrics
        total_pnl_percent = (total_pnl / total_invested * 100) if total_invested > 0 else 0
        gainers = len([h for h in holdings_list if h['pnl'] > 0])
        losers = len([h for h in holdings_list if h['pnl'] < 0])
        
        # Store in history for time-series tracking
        portfolio_history.append({
            'timestamp': current_time.isoformat(),
            'value': round(total_value, 2),
            'pnl': round(total_pnl, 2),
            'pnl_percent': round(total_pnl_percent, 2)
        })
        
        # Clean up old data (older than 2 hours)
        cutoff_time = current_time - timedelta(hours=2)
        while portfolio_history and datetime.fromisoformat(portfolio_history[0]['timestamp']) < cutoff_time:
            portfolio_history.popleft()
        
        # Process positions
        positions_list = []
        for pos in positions.get('net', []):
            qty = pos.get('quantity', 0)
            if qty == 0:
                continue
            
            positions_list.append({
                'symbol': pos.get('tradingsymbol', 'N/A'),
                'quantity': int(qty),
                'avg_price': round(pos.get('average_price', 0), 2),
                'ltp': round(pos.get('last_price', 0), 2),
                'pnl': round(pos.get('pnl', 0), 2),
                'type': 'Short' if qty < 0 else 'Long'
            })
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "summary": {
                    "total_value": round(total_value, 2),
                    "total_invested": round(total_invested, 2),
                    "total_pnl": round(total_pnl, 2),
                    "total_pnl_percent": round(total_pnl_percent, 2),
                    "holdings_count": len(holdings_list),
                    "positions_count": len(positions_list),
                    "gainers": gainers,
                    "losers": losers
                },
                "holdings": holdings_list,
                "positions": positions_list
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "data": None
        }


@app.get("/api/chart-data")
async def get_chart_data() -> Dict:
    """Get data formatted for charts"""
    trader = get_trader()
    
    if not trader:
        return {"success": False, "data": None}
    
    try:
        holdings = trader.get_holdings()
        
        chart_data = {
            "allocation": [],
            "pnl_breakdown": [],
            "performance": []
        }
        
        for holding in holdings:
            qty = holding.get('quantity', 0)
            if qty <= 0:
                continue
            
            symbol = holding.get('tradingsymbol', 'N/A')
            value = qty * holding.get('last_price', 0)
            pnl = holding.get('pnl', 0)
            avg = holding.get('average_price', 0)
            pnl_percent = (pnl / (qty * avg) * 100) if (qty * avg) > 0 else 0
            
            chart_data["allocation"].append({
                "name": symbol,
                "value": round(value, 2)
            })
            
            chart_data["pnl_breakdown"].append({
                "name": symbol,
                "value": round(pnl, 2),
                "percent": round(pnl_percent, 2)
            })
            
            chart_data["performance"].append({
                "symbol": symbol,
                "returns": round(pnl_percent, 2),
                "invested": round(qty * avg, 2),
                "current": round(value, 2)
            })
        
        # Sort
        chart_data["allocation"].sort(key=lambda x: x['value'], reverse=True)
        chart_data["pnl_breakdown"].sort(key=lambda x: x['value'], reverse=True)
        chart_data["performance"].sort(key=lambda x: x['returns'], reverse=True)
        
        return {
            "success": True,
            "data": chart_data
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "data": None
        }


@app.get("/api/historical/{symbol}")
async def get_historical_data(symbol: str, timeframe: str = "1d") -> Dict:
    """Get historical data for a symbol with different timeframes
    
    Args:
        symbol: Stock symbol
        timeframe: Time period - "1d" (intraday), "7d" (7 days), "1m" (1 month), "3m" (3 months)
    """
    trader = get_trader()
    
    if not trader:
        return {
            "success": False,
            "message": "Unable to connect to Zerodha",
            "data": None
        }
    
    try:
        from datetime import datetime, timedelta
        
        to_date = datetime.now()
        
        # Determine date range and interval based on timeframe
        if timeframe == "7d":
            # 7 days of daily data
            from_date = to_date - timedelta(days=7)
            interval = "day"
            time_format = '%b %d'  # e.g., "Jan 15"
        elif timeframe == "1m":
            # 1 month of daily data
            from_date = to_date - timedelta(days=30)
            interval = "day"
            time_format = '%b %d'
        elif timeframe == "3m":
            # 3 months of daily data
            from_date = to_date - timedelta(days=90)
            interval = "day"
            time_format = '%b %d'
        else:  # "1d" - intraday
            # Get intraday data for today (9:15 AM to current time)
            from_date = to_date.replace(hour=9, minute=15, second=0, microsecond=0)
            
            # If it's before market open, use previous trading day
            if to_date.hour < 9 or (to_date.hour == 9 and to_date.minute < 15):
                from_date = from_date - timedelta(days=1)
                to_date = from_date.replace(hour=15, minute=30, second=0, microsecond=0)
            
            interval = "5minute"
            time_format = '%H:%M'
        
        # Fetch historical data
        historical = trader.get_historical_data(
            symbol=symbol,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
        
        if not historical:
            return {
                "success": False,
                "message": "No historical data available",
                "data": None
            }
        
        # Format data for chart
        chart_data = []
        # Assume data from Zerodha is in IST, convert to local timezone
        ist = pytz.timezone('Asia/Kolkata')
        local_tz = datetime.now().astimezone().tzinfo
        
        for record in historical:
            date_obj = record.get('date')
            if date_obj:
                # If date_obj is naive (no timezone), assume it's IST
                if date_obj.tzinfo is None:
                    date_obj = ist.localize(date_obj)
                # Convert to local timezone
                date_obj_local = date_obj.astimezone(local_tz)
                
                chart_data.append({
                    "time": date_obj_local.strftime(time_format),
                    "date": date_obj_local.isoformat(),
                    "open": round(record.get('open', 0), 2),
                    "high": round(record.get('high', 0), 2),
                    "low": round(record.get('low', 0), 2),
                    "close": round(record.get('close', 0), 2),
                    "volume": record.get('volume', 0)
                })
        
        return {
            "success": True,
            "timeframe": timeframe,
            "data": chart_data
        }
    
    except Exception as e:
        print(f"Error fetching historical data for {symbol} ({timeframe}): {e}")
        return {
            "success": False,
            "message": str(e),
            "data": None
        }


@app.get("/api/portfolio-history")
async def get_portfolio_history() -> Dict:
    """Get portfolio value history (last 2 hours)"""
    if not portfolio_history:
        return {
            "success": True,
            "data": []
        }
    
    return {
        "success": True,
        "data": list(portfolio_history)
    }


@app.get("/api/live/{symbol}")
async def get_live_data(symbol: str) -> Dict:
    """Get live intraday data for a symbol (last 2 minutes with real-time updates)
    
    Args:
        symbol: Stock symbol
    """
    trader = get_trader()
    
    if not trader:
        return {
            "success": False,
            "message": "Unable to connect to Zerodha",
            "data": None
        }
    
    try:
        from datetime import datetime, timedelta
        
        to_date = datetime.now()
        
        # Get last 10 minutes of data based on current time
        # Using 1-minute interval means we need 10 data points (10 minutes / 1 minute)
        from_date = to_date - timedelta(minutes=10)
        
        # If it's before market open, use previous trading day's last 10 minutes
        if to_date.hour < 9 or (to_date.hour == 9 and to_date.minute < 15):
            # Use previous trading day's closing time
            to_date = to_date.replace(hour=15, minute=30, second=0, microsecond=0) - timedelta(days=1)
            from_date = to_date - timedelta(minutes=10)
        elif to_date.hour >= 15 and to_date.minute > 30:
            # After market close, use last 10 minutes of trading session
            to_date = to_date.replace(hour=15, minute=30, second=0, microsecond=0)
            from_date = to_date - timedelta(minutes=10)
        
        # Use 1-minute interval for live data (smallest available from Zerodha)
        interval = "minute"
        time_format = '%H:%M'
        
        # Fetch historical data for last 10 minutes
        historical = trader.get_historical_data(
            symbol=symbol,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
        
        if not historical:
            return {
                "success": False,
                "message": "No live data available",
                "data": None
            }
        
        # Format data for chart - last 10 minutes with 1-minute intervals
        chart_data = []
        # Assume data from Zerodha is in IST, convert to local timezone
        ist = pytz.timezone('Asia/Kolkata')
        local_tz = datetime.now().astimezone().tzinfo
        
        for record in historical:
            date_obj = record.get('date')
            if date_obj:
                # If date_obj is naive (no timezone), assume it's IST
                if date_obj.tzinfo is None:
                    date_obj = ist.localize(date_obj)
                # Convert to local timezone
                date_obj_local = date_obj.astimezone(local_tz)
                
                chart_data.append({
                    "time": date_obj_local.strftime(time_format),
                    "date": date_obj_local.isoformat(),
                    "open": round(record.get('open', 0), 2),
                    "high": round(record.get('high', 0), 2),
                    "low": round(record.get('low', 0), 2),
                    "close": round(record.get('close', 0), 2),
                    "volume": record.get('volume', 0)
                })
        
        return {
            "success": True,
            "timeframe": "live",
            "interval": "1min",
            "data": chart_data,
            "last_updated": datetime.now().isoformat(),
            "from_time": from_date.strftime('%H:%M'),
            "to_time": to_date.strftime('%H:%M')
        }
    
    except Exception as e:
        print(f"Error fetching live data for {symbol}: {e}")
        return {
            "success": False,
            "message": str(e),
            "data": None
        }


@app.get("/api/charts/holdings-pie")
async def get_holdings_pie_chart() -> Dict:
    """Get Plotly-formatted pie chart data for holdings allocation"""
    trader = get_trader()
    
    if not trader:
        return JSONResponse(
            status_code=503,
            content={"error": "Unable to connect to Zerodha"}
        )
    
    try:
        holdings = trader.get_holdings()
        
        labels = []
        values = []
        
        for holding in holdings:
            qty = holding.get('quantity', 0)
            if qty <= 0:
                continue
            
            symbol = holding.get('tradingsymbol', 'N/A')
            value = qty * holding.get('last_price', 0)
            
            labels.append(symbol)
            values.append(round(value, 2))
        
        if not labels:
            return JSONResponse(
                status_code=404,
                content={"error": "No holdings data available"}
            )
        
        # Create Plotly pie chart data
        plotly_data = {
            "data": [{
                "type": "pie",
                "labels": labels,
                "values": values,
                "hole": 0.4,
                "marker": {
                    "colors": ['#667eea', '#764ba2', '#f093fb', '#4facfe', '#00f2fe',
                              '#43e97b', '#38f9d7', '#fa709a', '#fee140', '#30cfd0'],
                    "line": {"color": "white", "width": 2}
                },
                "textposition": "inside",
                "textinfo": "label+percent",
                "hovertemplate": "<b>%{label}</b><br>Value: ₹%{value:,.2f}<br>Share: %{percent}<extra></extra>"
            }],
            "layout": {
                "title": {
                    "text": "Portfolio Allocation",
                    "font": {"size": 18, "color": "#667eea", "family": "Arial"}
                },
                "height": 400,
                "showlegend": True,
                "legend": {"orientation": "h", "yanchor": "bottom", "y": -0.2, "xanchor": "center", "x": 0.5},
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)"
            }
        }
        
        return plotly_data
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/api/charts/pnl-bar")
async def get_pnl_bar_chart() -> Dict:
    """Get Plotly-formatted bar chart data for P&L breakdown"""
    trader = get_trader()
    
    if not trader:
        return JSONResponse(
            status_code=503,
            content={"error": "Unable to connect to Zerodha"}
        )
    
    try:
        holdings = trader.get_holdings()
        
        symbols = []
        pnl_values = []
        colors = []
        
        for holding in holdings:
            qty = holding.get('quantity', 0)
            if qty <= 0:
                continue
            
            symbol = holding.get('tradingsymbol', 'N/A')
            pnl = holding.get('pnl', 0)
            
            symbols.append(symbol)
            pnl_values.append(round(pnl, 2))
            colors.append('#10b981' if pnl >= 0 else '#ef4444')
        
        if not symbols:
            return JSONResponse(
                status_code=404,
                content={"error": "No holdings data available"}
            )
        
        # Sort by P&L descending
        sorted_data = sorted(zip(symbols, pnl_values, colors), key=lambda x: x[1], reverse=True)
        symbols, pnl_values, colors = zip(*sorted_data) if sorted_data else ([], [], [])
        
        # Create Plotly bar chart data
        plotly_data = {
            "data": [{
                "type": "bar",
                "x": list(symbols),
                "y": list(pnl_values),
                "marker": {
                    "color": list(colors),
                    "line": {"color": "white", "width": 1}
                },
                "text": [f"₹{val:,.2f}" for val in pnl_values],
                "textposition": "outside",
                "hovertemplate": "<b>%{x}</b><br>P&L: ₹%{y:,.2f}<extra></extra>"
            }],
            "layout": {
                "title": {
                    "text": "Stock-wise P&L",
                    "font": {"size": 18, "color": "#667eea", "family": "Arial"}
                },
                "height": 400,
                "showlegend": False,
                "xaxis": {
                    "title": "Stock",
                    "tickangle": -45
                },
                "yaxis": {
                    "title": "P&L (₹)",
                    "gridcolor": "rgba(128,128,128,0.2)"
                },
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(255,255,255,0.9)"
            }
        }
        
        return plotly_data
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.post("/api/ai-training/start")
async def start_ai_training(request: Request) -> Dict:
    """Start AI training in background thread"""
    global training_status, training_thread
    
    if training_status['state'] == 'running':
        return {
            "success": False,
            "message": "Training is already running"
        }
    
    try:
        data = await request.json()
        symbols = data.get('symbols', [])
        lookback_days = data.get('lookback_days', 60)
        
        if not symbols:
            return {
                "success": False,
                "message": "No symbols provided"
            }
        
        # Reset training status
        training_status['state'] = 'running'
        training_status['progress'] = 0
        training_status['current_step'] = 'Initializing...'
        training_status['stats'] = {
            'total_candles': 0,
            'patterns_detected': 0,
            'predictions_made': 0,
            'successful_predictions': 0,
            'stock_performance': {},  # Per-stock PNL, Investment, Trades
            'paper_trading': {}  # Paper trading summary
        }
        training_status['error'] = None
        
        # Start training in background
        training_thread = threading.Thread(
            target=run_training_background,
            args=(symbols, lookback_days)
        )
        training_thread.daemon = True
        training_thread.start()
        
        return {
            "success": True,
            "message": "Training started"
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


def run_training_background(symbols: List[str], lookback_days: int):
    """Run AI training in background thread"""
    global training_status, training_history
    
    try:
        from train_ai_historical import AIHistoricalTrainer
        
        trader = get_trader()
        if not trader:
            training_status['state'] = 'error'
            training_status['error'] = 'Unable to connect to Zerodha'
            return
        
        # Initialize trainer
        training_status['progress'] = 10
        training_status['current_step'] = 'Fetching historical data...'
        
        trainer = AIHistoricalTrainer(
            trader=trader,
            symbols=symbols,
            lookback_days=lookback_days
        )
        
        # Fetch data
        training_status['progress'] = 20
        trainer.fetch_historical_data()
        training_status['stats']['total_candles'] = trainer.training_stats['total_candles']
        
        # Train pattern recognition
        training_status['progress'] = 40
        training_status['current_step'] = 'Training pattern recognition...'
        trainer.train_pattern_recognition()
        training_status['stats']['patterns_detected'] = trainer.training_stats['patterns_detected']
        
        # Train sentiment analyzer
        training_status['progress'] = 60
        training_status['current_step'] = 'Training sentiment analyzer...'
        trainer.train_sentiment_analyzer()
        
        # Train predictive model
        training_status['progress'] = 80
        training_status['current_step'] = 'Training predictive model...'
        trainer.train_predictive_model()
        training_status['stats']['predictions_made'] = trainer.training_stats['predictions_made']
        training_status['stats']['successful_predictions'] = trainer.training_stats['successful_predictions']
        
        # Collect per-stock performance and paper trading summary
        try:
            import json
            from pathlib import Path
            paper_file = Path('ai_data/paper_trading_state.json')
            if paper_file.exists():
                with open(paper_file, 'r') as f:
                    paper_data = json.load(f)
                    
                # Extract paper trading summary
                training_status['stats']['paper_trading'] = {
                    'current_capital': paper_data.get('current_capital', 0),
                    'initial_capital': paper_data.get('initial_capital', 100000),
                    'available_capital': paper_data.get('available_capital', 0),
                    'total_trades': paper_data.get('total_trades', 0),
                    'winning_trades': paper_data.get('winning_trades', 0),
                    'losing_trades': paper_data.get('losing_trades', 0),
                    'active_positions': len(paper_data.get('positions', {}))
                }
                
                # Extract daily statistics
                training_status['stats']['daily_stats'] = paper_data.get('daily_stats', [])
                    
                # Process stock performance
                stock_performance = {}
                for symbol in symbols:
                    # Calculate investment and PNL for each symbol from positions and history
                    investment = 0
                    pnl = 0
                    trades = 0
                    
                    # Check active positions
                    if symbol in paper_data.get('positions', {}):
                        pos = paper_data['positions'][symbol]
                        qty = pos.get('quantity', 0)
                        avg_price = pos.get('avg_price', 0)
                        investment += abs(qty * avg_price)
                    
                    # Check trade history for this symbol
                    for trade in paper_data.get('trade_history', []):
                        if trade.get('symbol') == symbol:
                            trades += 1
                    
                    # Check closed positions for realized PNL
                    for closed_pos in paper_data.get('closed_positions', []):
                        if closed_pos.get('symbol') == symbol:
                            pnl += closed_pos.get('realized_pnl', 0)
                    
                    stock_performance[symbol] = {
                        'pnl': round(pnl, 2),
                        'investment': round(investment, 2),
                        'trades': trades,
                        'pnl_percent': round((pnl / investment * 100) if investment > 0 else 0, 2)
                    }
                
                training_status['stats']['stock_performance'] = stock_performance
        except Exception as e:
            print(f"Error loading paper trading data: {e}")
        
        # Save models
        training_status['progress'] = 95
        training_status['current_step'] = 'Saving trained models...'
        trainer.save_trained_models()
        
        # Complete
        training_status['progress'] = 100
        training_status['current_step'] = 'Training complete!'
        training_status['state'] = 'completed'
        
        # Add to history
        training_history.append({
            'timestamp': datetime.now().isoformat(),
            'symbols': symbols,
            'lookback_days': lookback_days,
            'stats': training_status['stats'].copy()
        })
        
        # Keep only last 10 training sessions
        if len(training_history) > 10:
            training_history.pop(0)
        
    except Exception as e:
        training_status['state'] = 'error'
        training_status['error'] = str(e)
        print(f"Training error: {e}")


@app.get("/api/ai-training/status")
async def get_training_status() -> Dict:
    """Get current training status"""
    return {
        "success": True,
        "status": training_status
    }


@app.get("/api/ai-training/history")
async def get_training_history() -> Dict:
    """Get training history"""
    return {
        "success": True,
        "history": training_history
    }


@app.post("/api/paper-trading/start")
async def start_paper_trading(request: Request) -> Dict:
    """Start paper trading in background thread"""
    global paper_trading_status, paper_trading_thread, paper_trading_logs
    
    if paper_trading_status['state'] == 'running':
        return {
            "success": False,
            "message": "Paper trading is already running"
        }
    
    try:
        data = await request.json()
        symbols = data.get('symbols', [
            'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK',
            'SBIN', 'BHARTIARTL', 'ITC', 'WIPRO', 'LT',
            'AXISBANK', 'KOTAKBANK', 'HINDUNILVR', 'MARUTI', 'BAJFINANCE',
            'ASIANPAINT', 'TITAN', 'NESTLEIND', 'ULTRACEMCO', 'SUNPHARMA',
            'TATASTEEL', 'POWERGRID', 'NTPC', 'ONGC', 'COALINDIA',
            'TECHM', 'HCLTECH', 'DIVISLAB', 'DRREDDY', 'CIPLA',
            'BAJAJFINSV', 'M&M', 'TATAMOTORS', 'ADANIPORTS', 'JSWSTEEL',
            'HINDALCO', 'GRASIM', 'BRITANNIA', 'SHREECEM', 'EICHERMOT',
            'HEROMOTOCO', 'BPCL', 'IOC'
        ])
        initial_capital = data.get('initial_capital', 100000.0)
        
        # Reset status
        paper_trading_status['state'] = 'running'
        paper_trading_status['start_time'] = datetime.now().isoformat()
        paper_trading_status['iterations'] = 0
        paper_trading_status['last_update'] = datetime.now().isoformat()
        paper_trading_status['error'] = None
        paper_trading_logs.clear()
        
        # Start paper trading in background
        paper_trading_thread = threading.Thread(
            target=run_paper_trading_background,
            args=(symbols, initial_capital)
        )
        paper_trading_thread.daemon = True
        paper_trading_thread.start()
        
        return {
            "success": True,
            "message": "Paper trading started"
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


@app.post("/api/paper-trading/stop")
async def stop_paper_trading() -> Dict:
    """Stop paper trading"""
    global paper_trading_status
    
    if paper_trading_status['state'] != 'running':
        return {
            "success": False,
            "message": "Paper trading is not running"
        }
    
    paper_trading_status['state'] = 'stopped'
    add_paper_trading_log('INFO', 'Paper trading stopped by user')
    
    return {
        "success": True,
        "message": "Paper trading stopped"
    }


@app.get("/api/paper-trading/status")
async def get_paper_trading_status() -> Dict:
    """Get current paper trading status"""
    try:
        # Load paper trading state from file
        from pathlib import Path
        paper_file = Path('ai_data/paper_trading_state.json')
        
        if paper_file.exists():
            with open(paper_file, 'r') as f:
                paper_data = json.load(f)
            
            return {
                "success": True,
                "status": paper_trading_status,
                "data": {
                    'initial_capital': paper_data.get('initial_capital', 100000),
                    'current_capital': paper_data.get('current_capital', 100000),
                    'available_capital': paper_data.get('available_capital', 100000),
                    'total_trades': paper_data.get('total_trades', 0),
                    'winning_trades': paper_data.get('winning_trades', 0),
                    'losing_trades': paper_data.get('losing_trades', 0),
                    'total_profit': paper_data.get('total_profit', 0),
                    'total_loss': paper_data.get('total_loss', 0),
                    'positions': paper_data.get('positions', {}),
                    'trade_history': paper_data.get('trade_history', [])[-20:],  # Last 20 trades
                    'daily_pnl': paper_data.get('daily_pnl', {}),
                    'daily_stats': paper_data.get('daily_stats', []),  # Daily accumulated statistics
                    'last_updated': paper_data.get('last_updated', None)
                }
            }
        else:
            return {
                "success": True,
                "status": paper_trading_status,
                "data": None
            }
    
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


@app.get("/api/paper-trading/logs")
async def get_paper_trading_logs() -> Dict:
    """Get paper trading logs"""
    return {
        "success": True,
        "logs": list(paper_trading_logs)
    }


def add_paper_trading_log(level: str, message: str):
    """Add a log entry to paper trading logs"""
    paper_trading_logs.append({
        'timestamp': datetime.now().isoformat(),
        'level': level,
        'message': message
    })


def run_paper_trading_background(symbols: list, initial_capital: float):
    """Run paper trading in background thread"""
    global paper_trading_status
    
    try:
        import time
        import logging
        from src.kite_trader.trader import KiteTrader
        from src.strategies.ai_intraday_strategy import AIIntradayStrategy
        from src.paper_trading.paper_trader import PaperTrader
        from ai_paper_trader import PaperTradingWrapper
        
        add_paper_trading_log('INFO', f'Starting paper trading with {len(symbols)} symbols')
        add_paper_trading_log('INFO', f'Initial capital: ₹{initial_capital:,.2f}')
        
        # Connect to real market data
        real_trader = KiteTrader()
        
        if not real_trader.is_connected():
            add_paper_trading_log('ERROR', 'Failed to connect to Zerodha')
            paper_trading_status['state'] = 'error'
            paper_trading_status['error'] = 'Failed to connect to Zerodha'
            return
        
        add_paper_trading_log('INFO', 'Connected to Zerodha for market data')
        
        # Initialize paper trader
        paper_trader = PaperTrader(initial_capital=initial_capital, data_dir='data/ai_data')
        trading_wrapper = PaperTradingWrapper(real_trader, paper_trader)
        
        # Create AI strategy
        strategy = AIIntradayStrategy(
            trader=trading_wrapper,
            symbols=symbols,
            min_profit_margin=0.015,
            buy_threshold=0.25,
            sell_threshold=0.75,
            risk_reward_ratio=2.5,
            max_position_pct=0.08,
            stop_loss_pct=0.02,
            ai_confidence_threshold=0.6,
            name="AI_PaperTrader"
        )
        
        add_paper_trading_log('INFO', 'AI strategy initialized')
        
        # Market hours (IST)
        market_open = 9 * 60 + 15      # 9:15 AM
        market_close = 15 * 60 + 30    # 3:30 PM
        check_interval = 60  # Check every 60 seconds
        
        while paper_trading_status['state'] == 'running':
            current_time = datetime.now()
            current_minutes = current_time.hour * 60 + current_time.minute
            
            # Check if market is open
            is_weekday = current_time.weekday() < 5
            is_market_hours = market_open <= current_minutes <= market_close
            
            if is_weekday and is_market_hours:
                paper_trading_status['iterations'] += 1
                paper_trading_status['last_update'] = datetime.now().isoformat()
                
                add_paper_trading_log('INFO', f'Iteration {paper_trading_status["iterations"]}')
                
                # Run strategy iteration
                strategy.run_iteration()
                
                # Get current prices and update portfolio
                try:
                    quotes = trading_wrapper.get_quote(symbols)
                    current_prices = {
                        s: quotes.get(f"NSE:{s}", {}).get('last_price', 0)
                        for s in symbols
                    }
                    portfolio_value = paper_trader.get_portfolio_value(current_prices)
                    paper_trader.current_capital = portfolio_value
                    
                    # Log summary
                    summary = paper_trader.get_performance_summary()
                    add_paper_trading_log(
                        'INFO',
                        f'Portfolio: ₹{portfolio_value:,.2f} | '
                        f'Trades: {summary["total_trades"]} | '
                        f'Win Rate: {summary["win_rate"]:.1f}% | '
                        f'Active: {summary["active_positions"]}'
                    )
                except Exception as e:
                    add_paper_trading_log('ERROR', f'Error updating portfolio: {str(e)}')
                
                # Save periodically
                if paper_trading_status['iterations'] % 10 == 0:
                    strategy._save_ai_models()
                    paper_trader._save_state()
                    add_paper_trading_log('INFO', 'Models and state saved')
            
            elif is_weekday and current_minutes < market_open:
                wait_minutes = market_open - current_minutes
                if paper_trading_status['iterations'] == 0:
                    add_paper_trading_log('INFO', f'Market opens in {wait_minutes} minutes')
                time.sleep(300)  # Check every 5 minutes
                continue
            
            elif is_weekday and current_minutes > market_close:
                add_paper_trading_log('INFO', 'Market closed - End of day')
                strategy._save_ai_models()
                paper_trader._save_state()
                paper_trading_status['state'] = 'stopped'
                break
            
            else:
                # Weekend
                if paper_trading_status['iterations'] == 0:
                    add_paper_trading_log('INFO', 'Weekend - Market closed')
                time.sleep(3600)  # Check every hour
                continue
            
            time.sleep(check_interval)
        
        add_paper_trading_log('INFO', 'Paper trading session ended')
        paper_trading_status['state'] = 'stopped'
    
    except Exception as e:
        add_paper_trading_log('ERROR', f'Paper trading error: {str(e)}')
        paper_trading_status['state'] = 'error'
        paper_trading_status['error'] = str(e)


@app.get("/api/funds")
async def get_funds() -> Dict:
    """Get funds and margin data"""
    trader = get_trader()
    
    if not trader:
        return {
            "success": False,
            "message": "Unable to connect to Zerodha",
            "data": None
        }
    
    try:
        margins = trader.get_margins()
        
        # Extract equity margin data
        equity = margins.get('equity', {})
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "available_cash": round(equity.get('available', {}).get('cash', 0), 2),
                "used_margin": round(equity.get('used', {}).get('debits', 0), 2),
                "available_margin": round(equity.get('available', {}).get('live_balance', 0), 2),
                "opening_balance": round(equity.get('net', 0), 2),
                "payin": round(equity.get('available', {}).get('intraday_payin', 0), 2),
                "collateral": round(equity.get('available', {}).get('collateral', 0), 2)
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "data": None
        }


# ── Live Trading Dashboard route & APIs ───────────────────────────────────────

@app.get("/live-trading")
async def live_trading_page(request: Request):
    return templates.TemplateResponse("live_trading.html", {"request": request})


@app.post("/api/live-trading/start")
async def start_live_trading(request: Request) -> Dict:
    global live_trading_status, live_trading_thread, live_trading_logs, live_agent_state
    if live_trading_status['state'] == 'running':
        return {"success": False, "message": "Already running"}
    try:
        data = await request.json()
        mode = data.get('mode', 'paper')          # 'paper' or 'live'
        capital = float(data.get('capital', 1000))

        live_trading_status.update({
            'state': 'running', 'mode': mode,
            'start_time': datetime.now().isoformat(),
            'iteration': 0, 'last_update': None, 'error': None,
        })
        live_trading_logs.clear()
        live_agent_state['pnl_history'].clear()

        live_trading_thread = threading.Thread(
            target=_run_live_trading_background,
            args=(mode, capital),
            daemon=True,
        )
        live_trading_thread.start()
        return {"success": True, "message": f"Started in {mode} mode"}
    except Exception as e:
        live_trading_status['state'] = 'error'
        live_trading_status['error'] = str(e)
        return {"success": False, "message": str(e)}


@app.post("/api/live-trading/stop")
async def stop_live_trading() -> Dict:
    global live_trading_status
    if live_trading_status['state'] != 'running':
        return {"success": False, "message": "Not running"}
    live_trading_status['state'] = 'stopping'
    _add_live_log('WARN', 'Stop requested by user — will halt after current iteration')
    return {"success": True, "message": "Stop signal sent"}


@app.get("/api/live-trading/state")
async def get_live_trading_state() -> Dict:
    """Full dashboard state — called every 5 s by the UI."""
    state = live_agent_state
    positions_list = []
    for sym, p in state['positions'].items():
        positions_list.append({
            'symbol': sym,
            'qty': p.get('qty', 0),
            'avg_price': p.get('avg_price', 0),
            'current_price': p.get('current_price', 0),
            'unrealised_pnl': p.get('unrealised_pnl', 0),
            'pnl_pct': p.get('pnl_pct', 0),
            'stop_price': p.get('stop_price', 0),
            'entry_time': p.get('entry_time', ''),
        })

    pnl_hist = list(state['pnl_history'])

    return {
        "status": live_trading_status,
        "watchlist": state['watchlist'],
        "watchlist_scores": state.get('watchlist_scores', []),
        "signals": state['signals'],
        "positions": positions_list,
        "risk": state['risk'],
        "post_trade": state['post_trade'],
        "pnl_history": pnl_hist,
    }


@app.get("/api/live-trading/logs")
async def get_live_trading_logs(since: int = 0) -> Dict:
    """Return logs newer than `since` (Unix ms). UI passes its last timestamp."""
    logs = list(live_trading_logs)
    if since:
        logs = [l for l in logs if l['ts'] > since]
    return {"logs": logs}


# ── Background runner ──────────────────────────────────────────────────────────

def _add_live_log(level: str, message: str):
    live_trading_logs.append({
        'ts': int(datetime.now().timestamp() * 1000),
        'time': datetime.now().strftime('%H:%M:%S'),
        'level': level,
        'message': message,
    })


def _run_live_trading_background(mode: str, capital: float):
    """
    Runs the 6-agent pipeline in a background thread.
    Writes state into live_agent_state so the API can serve it.
    Uses TRADING_MODE=paper override when mode=='paper' regardless of env.
    """
    import time as _time
    import os as _os

    global live_trading_status, live_agent_state

    try:
        # Force paper mode in env if requested from UI
        _os.environ['TRADING_MODE'] = mode
        _os.environ['MAX_LIVE_CAPITAL'] = str(capital)

        from src.kite_trader.trader  import KiteTrader
        from src.kite_trader.ticker  import PositionTicker
        from src.utils.capital_manager import CapitalRecoveryManager
        from src.utils.broker_health import BrokerHealthMonitor
        from src.utils.market_calendar import MarketCalendar
        from src.agents.market_scanner import MarketScanner
        from src.agents.signal_engine  import SignalEngine
        from src.agents.risk_gate      import RiskGate
        from src.agents.execution_agent import ExecutionAgent
        from src.agents.position_monitor import PositionMonitor
        from src.agents.post_trade_agent import PostTradeAgent
        import pytz as _pytz

        _add_live_log('INFO', f'Starting agents — mode={mode} capital=₹{capital:,.0f}')

        trader = KiteTrader(enable_order_manager=(mode == 'live'), enable_rate_limiter=True)
        if not trader.is_connected():
            raise RuntimeError("Cannot connect to Zerodha — check KITE_ACCESS_TOKEN")

        _add_live_log('INFO', '✓ Connected to Zerodha')

        IST = _pytz.timezone('Asia/Kolkata')
        MARKET_OPEN  = 9 * 60 + 15
        SQUARE_OFF   = 15 * 60 + 20
        MARKET_CLOSE = 15 * 60 + 30
        CHECK_SECS   = 120

        capital_manager = CapitalRecoveryManager(max_initial_capital=capital)
        available = capital_manager.get_available_capital()
        _add_live_log('INFO', f'Capital today: ₹{available:,.2f}')

        broker_health  = BrokerHealthMonitor(trader, check_interval=120, failure_threshold=3)
        calendar       = MarketCalendar()
        scanner        = MarketScanner(trader, max_symbols=10, min_price=50.0, min_volume=500_000)
        risk_gate      = RiskGate(
            max_capital=available, max_daily_loss=available * 0.10,
            max_position_pct=0.15, max_concurrent_positions=4,
            stop_loss_pct=0.015, target_pct=0.025,
            min_risk_reward=3.0, risk_per_trade_pct=0.01,
        )
        execution      = ExecutionAgent(trader, stop_loss_pct=0.015)
        signal_engine  = SignalEngine(
            trader=trader, symbols=[],
            min_profit_margin=0.02, buy_threshold=0.20, sell_threshold=0.80,
            risk_reward_ratio=3.0, max_position_pct=0.15,
            stop_loss_pct=0.015, confidence_threshold=0.55,
        )
        pos_monitor    = PositionMonitor(
            execution_agent=execution, risk_gate=risk_gate, trader=trader,
            stop_loss_pct=0.015, target_pct=0.025,
            trailing_stop_activation=0.010, trailing_stop_distance=0.008,
            max_hold_minutes=90,
        )
        post_trade     = PostTradeAgent(capital_manager=capital_manager,
                                        signal_engine=signal_engine, data_dir='data')

        # Wire callbacks
        execution.register_on_fill(lambda s, t, q, p, pnl: risk_gate.record_fill(s, t, q, p))
        execution.register_on_fill(post_trade.on_fill)

        # WebSocket ticker — re-subscribe on every fill so new positions are watched instantly
        ticker = PositionTicker(trader, pos_monitor, execution)
        def _ticker_fill_cb(s, t, q, p, pnl):
            ticker.update_symbols(list(execution.all_positions().keys()))
        execution.register_on_fill(_ticker_fill_cb)

        startup_done = False
        squared_off  = False
        last_sync    = None

        while live_trading_status['state'] == 'running':
            now  = datetime.now(IST)
            mins = now.hour * 60 + now.minute

            if not calendar.is_trading_day(now.date()):
                _add_live_log('INFO', f'Not a trading day ({now.strftime("%A")}). Waiting...')
                _time.sleep(300)
                continue

            if mins < MARKET_OPEN:
                wait = MARKET_OPEN - mins
                _add_live_log('INFO', f'Market opens in {wait} min')
                _time.sleep(min(wait * 60, 60))
                continue

            if mins > MARKET_CLOSE:
                _add_live_log('INFO', 'Market closed — ending session')
                break

            # ---- Startup ----
            if not startup_done:
                _add_live_log('INFO', '🚀 Market open — scanning watchlist...')
                symbols = scanner.scan()
                live_agent_state['watchlist'] = symbols
                live_agent_state['watchlist_scores'] = [
                    {k: round(v, 4) if isinstance(v, float) else v
                     for k, v in s.items()
                     if k in ('symbol','composite_score','vol_surge',
                              'gap_pct','day_range_pct','price_momentum','atr_pct')}
                    for s in scanner.get_last_scores()
                ]
                signal_engine.symbols = symbols
                signal_engine.base_strategy.symbols = symbols
                _add_live_log('INFO', f'Watchlist: {", ".join(symbols)}')

                _add_live_log('INFO', 'Seeding historical candle data...')
                signal_engine.seed_historical_data(days=5)

                execution.sync_from_broker()
                risk_gate.reset_daily(available)
                signal_engine.reset_daily(available)
                pos_monitor.reset_daily()
                post_trade.start_day(available)

                # Regime + VIX — scale stops/sizes for today's conditions
                cond = scanner.market_conditions()
                if cond['skip_day']:
                    _add_live_log('WARN',
                        f"⚠️ Choppy day (Nifty range {cond['nifty_range_pct']:.2%}) "
                        f"— position sizes halved")
                risk_gate.stop_loss_pct      = round(risk_gate.stop_loss_pct      * cond['stop_loss_mult'], 4)
                risk_gate.risk_per_trade_pct = round(risk_gate.risk_per_trade_pct * cond['size_mult'],      4)
                _add_live_log('INFO',
                    f"✓ regime={cond['regime']} vix={cond['vix']} "
                    f"stop={risk_gate.stop_loss_pct:.3f} size_pct={risk_gate.risk_per_trade_pct:.3f}")

                ticker.start()
                startup_done = True
                _add_live_log('INFO', '✓ Startup complete')

            # ---- Square-off ----
            if mins >= SQUARE_OFF and not squared_off:
                _add_live_log('WARN', '⏰ 3:20 PM — squaring off all positions')
                execution.square_off_all(reason='EOD square-off')
                squared_off = True
                _time.sleep(CHECK_SECS)
                continue

            if mins >= SQUARE_OFF:
                _time.sleep(60)
                continue

            # ---- Health check ----
            health = broker_health.check_health()
            if health['should_halt']:
                _add_live_log('ERROR', f'🚨 Broker unreachable — halting')
                risk_gate.halted = True
                break
            if not health['is_healthy']:
                _add_live_log('WARN', '⚠️ Broker health failed — skipping iteration')
                _time.sleep(CHECK_SECS)
                continue

            # ---- Iteration ----
            live_trading_status['iteration'] += 1
            live_trading_status['last_update'] = now.isoformat()
            iter_n = live_trading_status['iteration']
            _add_live_log('INFO', f'── Iteration {iter_n} {now.strftime("%H:%M:%S")} ──')

            signals = signal_engine.run_iteration()
            live_agent_state['signals'] = {k: v for k, v in signals.items() if v}

            exits = pos_monitor.monitor(signal_overrides=signals)
            for sym, reason in exits.items():
                _add_live_log('INFO', f'EXIT {sym}: {reason}')

            if not risk_gate.halted:
                for symbol, signal in signals.items():
                    if execution.has_position(symbol):
                        continue
                    if signal not in ('BUY', 'SELL'):
                        continue
                    q = trader.get_quote([symbol])
                    qd = q.get(f'NSE:{symbol}', {})
                    ltp      = qd.get('last_price', 0)
                    day_high = qd.get('ohlc', {}).get('high', ltp)
                    day_low  = qd.get('ohlc', {}).get('low', ltp)

                    if signal == 'BUY':
                        decision = risk_gate.evaluate(symbol, 'BUY', ltp, day_high, day_low)
                        if decision.approved:
                            _add_live_log('INFO',
                                f'BUY {symbol} {decision.quantity}@₹{decision.limit_price:.2f} | R/R ✓')
                            execution.execute(symbol, decision, 'BUY')
                        else:
                            _add_live_log('DEBUG', f'BLOCKED BUY {symbol}: {decision.reason}')

                    elif signal == 'SELL':
                        decision = risk_gate.evaluate_short(symbol, ltp, day_high, day_low)
                        if decision.approved:
                            _add_live_log('INFO',
                                f'SHORT {symbol} {decision.quantity}@₹{decision.limit_price:.2f} | R/R ✓')
                            execution.execute(symbol, decision, 'SELL')
                        else:
                            _add_live_log('DEBUG', f'BLOCKED SHORT {symbol}: {decision.reason}')

            # ---- Sync positions into shared state ----
            open_pos = execution.all_positions()
            pos_snapshot = {}
            if open_pos:
                syms_open = list(open_pos.keys())
                try:
                    qt = trader.get_quote(syms_open)
                    for sym, pos in open_pos.items():
                        ltp = qt.get(f'NSE:{sym}', {}).get('last_price', pos.avg_price)
                        pnl = pos.unrealised_pnl(ltp)
                        pos_snapshot[sym] = {
                            'qty': pos.quantity,
                            'avg_price': round(pos.avg_price, 2),
                            'current_price': round(ltp, 2),
                            'unrealised_pnl': round(pnl, 2),
                            'pnl_pct': round(pos.pnl_pct(ltp) * 100, 2),
                            'stop_price': round(pos.stop_price, 2),
                            'entry_time': pos.entry_time.strftime('%H:%M:%S'),
                        }
                except Exception:
                    pass
            live_agent_state['positions'] = pos_snapshot

            # ---- Sync risk + post-trade state ----
            rs = risk_gate.status()
            live_agent_state['risk'] = rs
            live_agent_state['post_trade'] = post_trade.intraday_status()
            live_agent_state['pnl_history'].append({
                'time': now.strftime('%H:%M'),
                'pnl': round(rs['daily_pnl'], 2),
            })

            # ---- Periodic broker reconcile ----
            if last_sync is None or (datetime.now(IST) - last_sync).total_seconds() >= 600:
                execution.sync_from_broker()
                last_sync = datetime.now(IST)

            # ---- Periodic model save ----
            if iter_n % 5 == 0:
                signal_engine.save_models()

            _time.sleep(CHECK_SECS)

        # End of session
        _add_live_log('INFO', 'Session ending — recording EOD...')
        ticker.stop()
        if execution.all_positions():
            execution.square_off_all('Session ended')
            _time.sleep(3)
        post_trade.end_day(used_capital=risk_gate.status()['used_capital'])
        signal_engine.save_models()
        _add_live_log('INFO', '✅ Session complete')

    except Exception as e:
        import traceback
        _add_live_log('ERROR', f'Fatal: {e}')
        _add_live_log('ERROR', traceback.format_exc())
        live_trading_status['state'] = 'error'
        live_trading_status['error'] = str(e)
        return

    live_trading_status['state'] = 'stopped'


# ── ML API routes ─────────────────────────────────────────────────────────────

@app.get("/api/model/status")
async def get_model_status() -> Dict:
    """Return current model metadata (or idle state if never trained)."""
    import os as _os
    try:
        from src.ml.model_trainer import META_PATH, MODEL_PATH
        if _os.path.exists(META_PATH):
            import json as _json
            with open(META_PATH) as f:
                meta = _json.load(f)
            return {"success": True, "trained": True, "metadata": meta,
                    "model_size_kb": round(_os.path.getsize(MODEL_PATH) / 1024, 1)}
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": True, "trained": False, "metadata": None}


@app.post("/api/train/run")
async def start_ml_training(request: Request) -> Dict:
    """Start ModelTrainer in a background thread."""
    global ml_train_status, ml_train_thread
    if ml_train_status['state'] == 'running':
        return {"success": False, "message": "Training already running"}
    try:
        body = await request.json()
        symbols = body.get('symbols', [
            'RELIANCE','TCS','INFY','HDFCBANK','ICICIBANK',
            'SBIN','AXISBANK','WIPRO','LT','BAJFINANCE',
        ])
        lookback_days = int(body.get('lookback_days', 180))
        n_folds = int(body.get('n_folds', 5))

        ml_train_status.update({'state': 'running', 'progress': 0,
                                 'step': 'Starting...', 'error': None, 'metadata': None})
        ml_train_thread = threading.Thread(
            target=_run_ml_training,
            args=(symbols, lookback_days, n_folds),
            daemon=True,
        )
        ml_train_thread.start()
        return {"success": True, "message": f"Training started for {len(symbols)} symbols"}
    except Exception as e:
        ml_train_status['state'] = 'error'
        ml_train_status['error'] = str(e)
        return {"success": False, "message": str(e)}


@app.get("/api/train/status")
async def get_ml_train_status() -> Dict:
    """Poll training progress (0-100) and current step."""
    return {"success": True, "status": ml_train_status}


@app.post("/api/backtest/run")
async def run_backtest(request: Request) -> Dict:
    """
    Run Backtester.parameter_sweep for a single symbol and return the summary.
    No background thread — fast enough to await (typically <5 s per symbol).
    """
    try:
        body = await request.json()
        symbol = body.get('symbol', '')
        lookback_days = int(body.get('lookback_days', 90))
        if not symbol:
            return {"success": False, "message": "symbol required"}

        trader = get_trader()
        if not trader:
            return {"success": False, "message": "Cannot connect to Zerodha"}

        from datetime import timedelta as _td
        from src.ml.backtester import Backtester
        to_date   = datetime.now()
        from_date = to_date - _td(days=lookback_days)
        candles   = trader.get_historical_data(
            symbol=symbol, from_date=from_date,
            to_date=to_date, interval='5minute',
        )
        if len(candles) < 200:
            return {"success": False,
                    "message": f"Only {len(candles)} candles — need ≥200"}

        best, _ = Backtester.parameter_sweep(candles, symbol)
        return {
            "success": True,
            "symbol": symbol,
            "candles": len(candles),
            "summary": best.summary(),
            "metrics": {
                "net_pnl":       round(best.net_pnl, 2),
                "win_rate":      round(best.win_rate, 4),
                "total_trades":  best.total_trades,
                "sharpe":        round(best.sharpe, 3),
                "expectancy":    round(best.expectancy, 2),
                "best_params":   best.params,
            }
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def _run_ml_training(symbols: list, lookback_days: int, n_folds: int):
    """Background thread: runs ModelTrainer.run() and writes progress into ml_train_status."""
    global ml_train_status
    try:
        trader = get_trader()
        if not trader:
            ml_train_status.update({'state': 'error', 'error': 'Cannot connect to Zerodha'})
            return

        def _progress(pct: int, msg: str):
            ml_train_status['progress'] = pct
            ml_train_status['step'] = msg

        from src.ml.model_trainer import ModelTrainer, invalidate_model_cache
        trainer = ModelTrainer(trader=trader, progress_cb=_progress)
        meta = trainer.run(symbols=symbols, lookback_days=lookback_days, n_cv_folds=n_folds)
        invalidate_model_cache()   # force reload on next inference
        ml_train_status.update({
            'state': 'completed', 'progress': 100,
            'step': f'Done. CV accuracy={meta["cv_accuracy_mean"]:.1%}',
            'metadata': meta,
        })
    except Exception as e:
        import traceback
        ml_train_status.update({'state': 'error', 'error': str(e) + '\n' + traceback.format_exc()})


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 Portfolio Dashboard Starting...")
    print("📊 Access at: http://localhost:8000")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True, log_level="info")
