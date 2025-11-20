#!/usr/bin/env python3
"""
Modern Portfolio Dashboard with FastAPI
Dark theme with sleek design inspired by modern analytics platforms
"""
import os
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

# Load environment
env_path = os.path.join(os.path.dirname(__file__), '.env')
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
templates = Jinja2Templates(directory="templates")

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


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 Portfolio Dashboard Starting...")
    print("📊 Access at: http://localhost:8000")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True, log_level="info")
