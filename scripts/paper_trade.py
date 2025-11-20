#!/usr/bin/env python3
"""
AI-Powered Paper Trading

Tests AI trading strategy with virtual money and real market data.
- No real money at risk
- AI learns from actual market conditions
- Track performance metrics
- Analyze patterns and success rates
"""
import os
import time
import logging
from datetime import datetime
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'data/logs/paper_trading_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MockKite:
    """Mock Kite object that redirects margins() to paper trading."""
    
    def __init__(self, real_kite, paper_trader):
        self._real_kite = real_kite
        self._paper_trader = paper_trader
    
    def margins(self):
        """Return paper trading margins instead of real account."""
        return {
            'equity': {
                'available': {
                    'cash': self._paper_trader.available_capital
                }
            }
        }
    
    def __getattr__(self, name):
        """Delegate all other methods to real kite."""
        return getattr(self._real_kite, name)


class PaperTradingWrapper:
    """
    Wrapper that intercepts real trades and simulates them with paper trading.
    """
    
    def __init__(self, real_trader, paper_trader):
        self.real_trader = real_trader
        self.paper_trader = paper_trader
        self.kite = MockKite(real_trader.kite, paper_trader)  # Mock kite for paper trading
        self.logger = logging.getLogger(__name__)
        self._market_data_cache = {}
    
    def place_order(self, symbol=None, transaction_type=None, quantity=None,
                   order_type="MARKET", product="MIS", price=None, 
                   tradingsymbol=None, exchange=None, variety=None, **kwargs):
        """Intercept order and execute in paper trading."""
        
        # Handle both calling conventions
        if tradingsymbol:
            symbol = tradingsymbol
        if not exchange:
            exchange = "NSE"
        
        # Get current price from market data
        symbol_key = f"{exchange}:{symbol}"
        
        if symbol_key not in self._market_data_cache:
            try:
                quotes = self.real_trader.get_quote([symbol])
                if symbol_key in quotes:
                    current_price = quotes[symbol_key].get('last_price', price or 0)
                else:
                    current_price = price or 0
            except Exception as e:
                self.logger.error(f"Failed to get price for {symbol}: {e}")
                current_price = price or 0
        else:
            current_price = self._market_data_cache.get(symbol_key, {}).get('last_price', price or 0)
        
        # Execute in paper trading
        result = self.paper_trader.execute_order(
            symbol=symbol,
            transaction_type=transaction_type,
            quantity=quantity,
            price=current_price
        )
        
        # Return order_id for compatibility
        if result['status'] == 'COMPLETE':
            return result['order_id']
        else:
            return None
    
    def get_quote(self, symbols):
        """Get real market quotes."""
        quotes = self.real_trader.get_quote(symbols)
        self._market_data_cache.update(quotes)
        return quotes
    
    def get_ltp(self, symbols):
        """Get last traded price for given symbols."""
        try:
            return self.real_trader.get_ltp(symbols)
        except Exception as e:
            self.logger.error(f"Error getting LTP: {e}")
            # Fallback to get_quote if get_ltp fails
            try:
                quotes = self.get_quote(symbols)
                ltp_data = {}
                for symbol in symbols:
                    symbol_key = f"NSE:{symbol}"
                    if symbol_key in quotes:
                        ltp_data[symbol_key] = quotes[symbol_key].get('last_price', 0)
                return ltp_data
            except Exception as e2:
                self.logger.error(f"Error in LTP fallback: {e2}")
                return {}
    
    def margins(self):
        """Get margins for paper trading (returns virtual capital)."""
        return {
            'equity': {
                'available': {
                    'cash': self.paper_trader.available_capital
                }
            }
        }
    
    def quote(self, instruments):
        """Alias for get_quote for compatibility."""
        return self.get_quote(instruments)
    
    def get_positions(self):
        """Get paper trading positions."""
        return {'net': self.paper_trader.get_positions()}
    
    def positions(self):
        """Alias for get_positions for compatibility."""
        return self.get_positions()
    
    def is_connected(self):
        """Check if connected to real market data."""
        return self.real_trader.is_connected()
    
    def get_profile(self):
        """Get profile from real trader."""
        return self.real_trader.get_profile()
    
    def profile(self):
        """Alias for get_profile for compatibility."""
        return self.get_profile()


def main():
    """Run the AI-powered paper trading."""
    
    from src.kite_trader.trader import KiteTrader
    from src.strategies.ai_intraday_strategy import AIIntradayStrategy
    from src.paper_trading.paper_trader import PaperTrader
    
    # Initialize components
    logger.info("=" * 70)
    logger.info("🎯 AI PAPER TRADING - Learning Mode")
    logger.info("=" * 70)
    logger.info("📊 Using REAL market data with VIRTUAL money")
    logger.info("🤖 AI will learn from simulated trades")
    logger.info("=" * 70)
    
    # Connect to real market data
    real_trader = KiteTrader()
    
    if not real_trader.is_connected():
        logger.error("Failed to connect to Zerodha for market data. Check credentials.")
        return
    
    logger.info("✓ Connected to Zerodha for REAL market data")
    
    # Initialize paper trading with ₹100,000 virtual capital
    paper_trader = PaperTrader(initial_capital=100000.0, data_dir='data/ai_data')
    
    # Create wrapper that intercepts trades
    trading_wrapper = PaperTradingWrapper(real_trader, paper_trader)
    
    # Show paper trading summary
    summary = paper_trader.get_performance_summary()
    logger.info("\n💰 Virtual Account Status:")
    logger.info(f"  Initial Capital: ₹{summary['initial_capital']:,.2f}")
    logger.info(f"  Current Capital: ₹{summary['current_capital']:,.2f}")
    logger.info(f"  Available: ₹{summary['available_capital']:,.2f}")
    logger.info(f"  Total Return: ₹{summary['total_return']:+,.2f} ({summary['total_return_pct']:+.2f}%)")
    logger.info(f"  Total Trades: {summary['total_trades']}")
    if summary['total_trades'] > 0:
        logger.info(f"  Win Rate: {summary['win_rate']:.1f}%")
        logger.info(f"  Avg Win: ₹{summary['avg_win']:,.2f}")
        logger.info(f"  Avg Loss: ₹{summary['avg_loss']:,.2f}")
    
    # Get current holdings from paper trading state
    current_holdings = set()
    invalid_symbols_removed = []
    try:
        import json
        import re
        state_file = os.path.join('data/ai_data', 'paper_trading_state.json')
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                state = json.load(f)
                # Filter out invalid symbols (must be alphanumeric only, no emojis)
                all_holdings = state.get('positions', {}).keys()
                current_holdings = set(
                    symbol for symbol in all_holdings 
                    if re.match(r'^[A-Z0-9]+$', symbol)
                )
                if current_holdings:
                    logger.info(f"✓ Found {len(current_holdings)} valid holdings: {', '.join(sorted(current_holdings))}")
                invalid_holdings = set(all_holdings) - current_holdings
                if invalid_holdings:
                    logger.warning(f"⚠️  Skipped {len(invalid_holdings)} invalid symbols: {', '.join(sorted(invalid_holdings))}")
                    invalid_symbols_removed = list(invalid_holdings)
                    # Clean up the state file by removing invalid positions
                    if invalid_holdings:
                        state['positions'] = {k: v for k, v in state.get('positions', {}).items() if k not in invalid_holdings}
                        with open(state_file, 'w') as fw:
                            json.dump(state, fw, indent=2)
                        logger.info(f"🧹 Cleaned {len(invalid_holdings)} invalid symbols from paper trading state")
    except Exception as e:
        logger.warning(f"Could not load holdings from paper trading state: {e}")
    
    # Define base watchlist stocks to trade
    base_symbols = [
        'RELIANCE',    # Reliance Industries
        'TCS',         # Tata Consultancy Services
        'INFY',        # Infosys
        'HDFCBANK',    # HDFC Bank
        'ICICIBANK',   # ICICI Bank
        'SBIN',        # State Bank of India
        'BHARTIARTL',  # Bharti Airtel
        'ITC',         # ITC Limited
        'WIPRO',       # Wipro
        'LT',          # Larsen & Toubro
        'AXISBANK',    # Axis Bank
        'KOTAKBANK',   # Kotak Mahindra Bank
        'HINDUNILVR',  # Hindustan Unilever
        'MARUTI',      # Maruti Suzuki
        'BAJFINANCE',  # Bajaj Finance
        'ASIANPAINT',  # Asian Paints
        'TITAN',       # Titan Company
        'NESTLEIND',   # Nestle India
        'ULTRACEMCO',  # UltraTech Cement
        'SUNPHARMA',   # Sun Pharma
        'TATASTEEL',   # Tata Steel
        'POWERGRID',   # Power Grid Corporation
        'NTPC',        # NTPC Limited
        'ONGC',        # Oil and Natural Gas Corporation
        'COALINDIA',   # Coal India
        'TECHM',       # Tech Mahindra
        'HCLTECH',     # HCL Technologies
        'DIVISLAB',    # Divi's Laboratories
        'DRREDDY',     # Dr. Reddy's Laboratories
        'CIPLA',       # Cipla
        'BAJAJFINSV',  # Bajaj Finserv
        'M&M',         # Mahindra & Mahindra
        'TATAMOTORS',  # Tata Motors
        'ADANIPORTS',  # Adani Ports
        'JSWSTEEL',    # JSW Steel
        'HINDALCO',    # Hindalco Industries
        'GRASIM',      # Grasim Industries
        'BRITANNIA',   # Britannia Industries
        'SHREECEM',    # Shree Cement
        'EICHERMOT',   # Eicher Motors
        'HEROMOTOCO',  # Hero MotoCorp
        'BPCL',        # Bharat Petroleum
        'IOC'          # Indian Oil Corporation
    ]
    
    # Combine base symbols with current holdings (no duplicates)
    symbols = list(set(base_symbols) | current_holdings)
    symbols.sort()  # Sort for consistent ordering
    
    logger.info(f"\n🔍 Initial symbol list: {len(symbols)} symbols")
    
    # Create AI-enhanced strategy with paper trading wrapper
    logger.info("\n🤖 Initializing AI Strategy...")
    strategy = AIIntradayStrategy(
        trader=trading_wrapper,  # Use paper trading wrapper
        symbols=symbols,
        min_profit_margin=0.015,       # 1.5% minimum profit
        buy_threshold=0.25,            # Buy in lower 25% of range
        sell_threshold=0.75,           # Sell in upper 75% of range
        risk_reward_ratio=2.5,         # 2.5:1 reward/risk
        max_position_pct=0.08,         # 8% of capital per position
        stop_loss_pct=0.02,            # 2% stop loss
        ai_confidence_threshold=0.6,   # 60% AI confidence minimum
        name="AI_PaperTrader"
    )
    
    logger.info(f"✓ AI Strategy initialized with {len(symbols)} symbols")
    
    # Validate symbols to ensure they can get quote data
    logger.info("\n🔍 Validating symbols...")
    valid_symbols = strategy.validate_symbols(symbols)
    if len(valid_symbols) < len(symbols):
        removed_count = len(symbols) - len(valid_symbols)
        logger.warning(f"⚠️  Removed {removed_count} symbols that couldn't fetch quotes")
        strategy.symbols = valid_symbols
        symbols = valid_symbols
    
    logger.info(f"\n✓ Active trading symbols: {len(symbols)}")
    logger.info(f"  - Trading Mode: PAPER TRADING (Virtual Money)")
    logger.info(f"  - Base Strategy: High/Low with profit validation")
    logger.info(f"  - AI Enhancement: Pattern + Sentiment + Prediction")
    logger.info(f"  - AI Confidence Threshold: 60%")
    
    # Market hours (IST)
    market_open = 9 * 60 + 15      # 9:15 AM
    market_close = 15 * 60 + 30    # 3:30 PM
    
    iteration_count = 0
    check_interval = 60  # Check every 60 seconds
    
    logger.info("\n🚀 Starting AI Paper Trading Loop...")
    logger.info(f"Market hours: 9:15 AM - 3:30 PM IST")
    logger.info(f"Check interval: {check_interval} seconds")
    logger.info("=" * 70)
    
    try:
        while True:
            current_time = datetime.now()
            current_minutes = current_time.hour * 60 + current_time.minute
            
            # Check if market is open
            is_weekday = current_time.weekday() < 5
            is_market_hours = market_open <= current_minutes <= market_close
            
            if is_weekday and is_market_hours:
                iteration_count += 1
                logger.info(f"\n{'='*70}")
                logger.info(f"🤖 Paper Trading Iteration {iteration_count} - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"{'='*70}")
                
                # Run strategy iteration (AI analyzes and paper trades)
                logger.info(f"Running strategy iteration for {len(symbols)} symbols...")
                strategy.run_iteration()
                logger.info(f"Strategy iteration complete")
                
                # Get current prices for P&L calculation
                try:
                    quotes = trading_wrapper.get_quote(symbols)
                    current_prices = {
                        s: quotes.get(f"NSE:{s}", {}).get('last_price', 0)
                        for s in symbols
                    }
                except Exception as e:
                    logger.error(f"Failed to get quotes: {e}")
                    current_prices = {}
                
                # Update portfolio value
                portfolio_value = paper_trader.get_portfolio_value(current_prices)
                paper_trader.current_capital = portfolio_value
                
                # Display paper trading performance
                summary = paper_trader.get_performance_summary()
                logger.info(f"\n💰 Virtual Portfolio:")
                logger.info(f"  Total Value: ₹{portfolio_value:,.2f}")
                logger.info(f"  Available Cash: ₹{summary['available_capital']:,.2f}")
                logger.info(f"  Total P&L: ₹{summary['total_return']:+,.2f} ({summary['total_return_pct']:+.2f}%)")
                logger.info(f"  Active Positions: {summary['active_positions']}")
                
                if summary['total_trades'] > 0:
                    logger.info(f"\n📊 Trading Statistics:")
                    logger.info(f"  Total Trades: {summary['total_trades']}")
                    logger.info(f"  Winning Trades: {summary['winning_trades']} ({summary['win_rate']:.1f}%)")
                    logger.info(f"  Losing Trades: {summary['losing_trades']}")
                    logger.info(f"  Avg Win: ₹{summary['avg_win']:,.2f}")
                    logger.info(f"  Avg Loss: ₹{summary['avg_loss']:,.2f}")
                    if summary['profit_factor'] != float('inf'):
                        logger.info(f"  Profit Factor: {summary['profit_factor']:.2f}")
                
                # Display AI metrics
                ai_metrics = strategy.get_ai_metrics()
                logger.info(f"\n🧠 AI Performance:")
                logger.info(f"  AI Trades: {ai_metrics['total_trades']}")
                if ai_metrics['total_trades'] > 0:
                    logger.info(f"  AI Success Rate: {ai_metrics['success_rate']:.2%}")
                logger.info(f"  Prediction Accuracy: {ai_metrics['prediction_accuracy']:.2%}")
                
                # Show active paper positions with live P&L
                if paper_trader.positions:
                    logger.info(f"\n💼 Active Virtual Positions:")
                    for symbol, pos in paper_trader.positions.items():
                        current_price = current_prices.get(symbol, pos['avg_price'])
                        pnl_data = paper_trader.get_position_pnl(symbol, current_price)
                        pnl_emoji = "🟢" if pnl_data['pnl'] > 0 else "🔴" if pnl_data['pnl'] < 0 else "⚪"
                        logger.info(
                            f"  {pnl_emoji} {symbol}: {pnl_data['quantity']} @ ₹{pnl_data['avg_price']:.2f} "
                            f"(Current: ₹{current_price:.2f}, P&L: ₹{pnl_data['pnl']:+,.2f} / {pnl_data['pnl_pct']:+.2f}%)"
                        )
                
                # Save models periodically
                if iteration_count % 10 == 0:
                    logger.info("\n💾 Saving AI models and paper trading state...")
                    strategy._save_ai_models()
                    paper_trader._save_state()
                
                # Remove symbols failing to get quote data (every 20 iterations)
                if iteration_count % 20 == 0:
                    removed = strategy.remove_failing_symbols(failure_threshold=20)
                    if removed:
                        logger.info(f"🧹 Cleaned up {len(removed)} symbols that couldn't fetch quotes")
                        # Update symbols list to reflect changes
                        symbols = strategy.symbols
            
            elif is_weekday and current_minutes < market_open:
                wait_minutes = market_open - current_minutes
                logger.info(f"\n⏰ Market opens at 9:15 AM. Waiting {wait_minutes} minutes...")
                logger.info(f"   Current time: {current_time.strftime('%H:%M')}")
                
                if current_minutes < market_open - 60:
                    strategy.reset_daily_data()
                    # Get current prices for position closing
                    try:
                        quotes = trading_wrapper.get_quote(symbols)
                        current_prices = {
                            s: quotes.get(f"NSE:{s}", {}).get('last_price', 0)
                            for s in symbols
                        }
                    except Exception as e:
                        logger.error(f"Failed to get prices for EOD: {e}")
                        current_prices = {}
                    paper_trader.reset_daily(current_prices)
                    logger.info("   Daily data reset completed.")
                    time.sleep(300)  # Check every 5 minutes
                    continue
            
            elif is_weekday and current_minutes > market_close:
                logger.info("\n" + "=" * 70)
                logger.info("📊 PAPER TRADING - END OF DAY SUMMARY")
                logger.info("=" * 70)
                
                # Final summary
                summary = paper_trader.get_performance_summary()
                ai_metrics = strategy.get_ai_metrics()
                
                logger.info(f"\n💰 Final Portfolio Value:")
                logger.info(f"  Total Value: ₹{summary['current_capital']:,.2f}")
                logger.info(f"  Day's P&L: ₹{summary['total_return']:+,.2f} ({summary['total_return_pct']:+.2f}%)")
                logger.info(f"  Available Cash: ₹{summary['available_capital']:,.2f}")
                
                if summary['total_trades'] > 0:
                    logger.info(f"\n📈 Today's Trading Performance:")
                    logger.info(f"  Total Trades: {summary['total_trades']}")
                    logger.info(f"  Win Rate: {summary['win_rate']:.1f}%")
                    logger.info(f"  Avg Win: ₹{summary['avg_win']:,.2f}")
                    logger.info(f"  Avg Loss: ₹{summary['avg_loss']:,.2f}")
                    logger.info(f"  Profit Factor: {summary['profit_factor']:.2f}")
                
                logger.info(f"\n🤖 AI Learning Progress:")
                logger.info(f"  Total AI Trades: {ai_metrics['total_trades']}")
                logger.info(f"  Prediction Accuracy: {ai_metrics['prediction_accuracy']:.2%}")
                
                # Save final state
                strategy._save_ai_models()
                paper_trader._save_state()
                
                logger.info("\n✅ Paper trading session complete. AI models saved.")
                logger.info("💡 Review logs and adjust strategy as needed.")
                logger.info("=" * 70)
                
                # Wait until next trading day
                logger.info("\n⏸️  Market closed. Waiting for next trading day...")
                time.sleep(3600)  # Check every hour
                continue
            
            else:
                # Weekend
                logger.info(f"\n📅 Weekend - Market closed. Next session: Monday 9:15 AM")
                time.sleep(3600)  # Check every hour
                continue
            
            # Sleep until next check
            time.sleep(check_interval)
    
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Paper trading interrupted by user")
    
    except Exception as e:
        logger.error(f"\n❌ Error in paper trading: {e}", exc_info=True)
    
    finally:
        # Save final state
        logger.info("\n💾 Saving final state...")
        strategy._save_ai_models()
        paper_trader._save_state()
        
        # Final summary
        summary = paper_trader.get_performance_summary()
        logger.info("\n" + "=" * 70)
        logger.info("📊 PAPER TRADING SESSION SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total Iterations: {iteration_count}")
        logger.info(f"Final Capital: ₹{summary['current_capital']:,.2f}")
        logger.info(f"Total Return: ₹{summary['total_return']:+,.2f} ({summary['total_return_pct']:+.2f}%)")
        logger.info(f"Total Trades: {summary['total_trades']}")
        if summary['total_trades'] > 0:
            logger.info(f"Win Rate: {summary['win_rate']:.1f}%")
        logger.info("=" * 70)
        logger.info("\n✅ Paper trading session ended. Check logs for details.")


if __name__ == "__main__":
    main()
