"""
Paper Trading Module

Simulates real trades with virtual money to:
- Test strategies without risking capital
- Allow AI to learn from real market data
- Track performance metrics
- Analyze trade patterns
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
import os


class PaperTrader:
    """
    Simulates trading with virtual money using real market data.
    """
    
    def __init__(self, initial_capital: float = 100000.0, data_dir: str = 'ai_data'):
        """
        Initialize paper trader.
        
        Args:
            initial_capital: Starting virtual capital (default: ₹100,000)
            data_dir: Directory to store paper trading data
        """
        self.logger = logging.getLogger(__name__)
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # Account state
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.available_capital = initial_capital
        
        # Portfolio
        self.positions: Dict[str, Dict] = {}  # symbol -> position info
        self.closed_positions: List[Dict] = []
        
        # Trade history
        self.trade_history: List[Dict] = []
        self.daily_pnl: Dict[str, float] = {}  # date -> pnl
        
        # Performance metrics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        
        # Daily statistics tracking
        self.daily_stats: List[Dict] = []  # List of daily trading statistics
        
        # Load previous session if exists
        self._load_state()
        
        self.logger.info(f"Paper Trading initialized with ₹{initial_capital:,.2f} virtual capital")
    
    def execute_order(self, symbol: str, transaction_type: str, quantity: int, 
                     price: float, order_type: str = "MARKET") -> Dict:
        """
        Simulate order execution.
        
        Args:
            symbol: Stock symbol
            transaction_type: 'BUY' or 'SELL'
            quantity: Number of shares
            price: Execution price
            order_type: Order type (default: MARKET)
            
        Returns:
            Order result with execution details
        """
        timestamp = datetime.now()
        trade_value = quantity * price
        
        # Simulate brokerage (₹20 per trade)
        brokerage = 20.0
        
        if transaction_type == 'BUY':
            required_capital = trade_value + brokerage
            
            if required_capital > self.available_capital:
                self.logger.warning(
                    f"Insufficient virtual capital for {symbol}: "
                    f"Required ₹{required_capital:,.2f}, Available ₹{self.available_capital:,.2f}"
                )
                return {
                    'status': 'REJECTED',
                    'reason': 'Insufficient capital',
                    'symbol': symbol
                }
            
            # Execute BUY
            self.available_capital -= required_capital
            
            if symbol in self.positions:
                # Average up position
                old_qty = self.positions[symbol]['quantity']
                old_price = self.positions[symbol]['avg_price']
                new_qty = old_qty + quantity
                new_avg = ((old_qty * old_price) + (quantity * price)) / new_qty
                
                self.positions[symbol]['quantity'] = new_qty
                self.positions[symbol]['avg_price'] = new_avg
                self.positions[symbol]['invested'] += trade_value
            else:
                # New position
                self.positions[symbol] = {
                    'quantity': quantity,
                    'avg_price': price,
                    'invested': trade_value,
                    'entry_time': timestamp,
                    'entry_price': price
                }
            
            trade_record = {
                'timestamp': timestamp.isoformat(),
                'symbol': symbol,
                'type': 'BUY',
                'quantity': quantity,
                'price': price,
                'value': trade_value,
                'brokerage': brokerage,
                'capital_after': self.available_capital,
                'portfolio_value': self.get_portfolio_value({symbol: price})
            }
            
            self.logger.info(
                f"📝 PAPER TRADE: BUY {quantity} {symbol} @ ₹{price:.2f} "
                f"(Total: ₹{trade_value:,.2f} + ₹{brokerage} brokerage)"
            )
        
        else:  # SELL
            if symbol not in self.positions:
                self.logger.warning(f"No position to sell for {symbol}")
                return {
                    'status': 'REJECTED',
                    'reason': 'No position',
                    'symbol': symbol
                }
            
            position = self.positions[symbol]
            if quantity > position['quantity']:
                self.logger.warning(
                    f"Insufficient quantity for {symbol}: "
                    f"Tried to sell {quantity}, have {position['quantity']}"
                )
                return {
                    'status': 'REJECTED',
                    'reason': 'Insufficient quantity',
                    'symbol': symbol
                }
            
            # Execute SELL
            sell_value = trade_value - brokerage
            self.available_capital += sell_value
            
            # Calculate P&L
            entry_price = position['entry_price']
            pnl = (price - entry_price) * quantity
            pnl_pct = ((price - entry_price) / entry_price) * 100
            
            # Update metrics
            self.total_trades += 1
            if pnl > 0:
                self.winning_trades += 1
                self.total_profit += pnl
            else:
                self.losing_trades += 1
                self.total_loss += abs(pnl)
            
            # Update position
            position['quantity'] -= quantity
            
            # Close position if fully sold
            if position['quantity'] == 0:
                holding_period = (timestamp - position['entry_time']).total_seconds() / 60  # minutes
                closed_position = {
                    'symbol': symbol,
                    'entry_price': entry_price,
                    'exit_price': price,
                    'quantity': quantity,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'holding_period_minutes': holding_period,
                    'entry_time': position['entry_time'].isoformat(),
                    'exit_time': timestamp.isoformat()
                }
                self.closed_positions.append(closed_position)
                del self.positions[symbol]
            
            trade_record = {
                'timestamp': timestamp.isoformat(),
                'symbol': symbol,
                'type': 'SELL',
                'quantity': quantity,
                'price': price,
                'value': sell_value,
                'brokerage': brokerage,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'capital_after': self.available_capital,
                'portfolio_value': self.get_portfolio_value({symbol: price})
            }
            
            pnl_emoji = "🟢" if pnl > 0 else "🔴"
            self.logger.info(
                f"📝 PAPER TRADE: SELL {quantity} {symbol} @ ₹{price:.2f} "
                f"{pnl_emoji} P&L: ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)"
            )
        
        # Record trade
        self.trade_history.append(trade_record)
        
        # Update daily P&L
        today = timestamp.strftime('%Y-%m-%d')
        if today not in self.daily_pnl:
            self.daily_pnl[today] = 0.0
        if transaction_type == 'SELL':
            self.daily_pnl[today] += pnl
        
        # Save state
        self._save_state()
        
        return {
            'status': 'COMPLETE',
            'order_id': f"PAPER_{timestamp.strftime('%Y%m%d%H%M%S')}_{symbol}",
            'symbol': symbol,
            'transaction_type': transaction_type,
            'quantity': quantity,
            'price': price,
            'timestamp': timestamp.isoformat()
        }
    
    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """
        Calculate total portfolio value.
        
        Args:
            current_prices: Dict of symbol -> current price
            
        Returns:
            Total portfolio value (cash + positions)
        """
        positions_value = 0.0
        for symbol, position in self.positions.items():
            current_price = current_prices.get(symbol, position['avg_price'])
            positions_value += position['quantity'] * current_price
        
        return self.available_capital + positions_value
    
    def get_position_pnl(self, symbol: str, current_price: float) -> Dict:
        """
        Get P&L for a specific position.
        
        Args:
            symbol: Stock symbol
            current_price: Current market price
            
        Returns:
            Position P&L details
        """
        if symbol not in self.positions:
            return {'pnl': 0, 'pnl_pct': 0}
        
        position = self.positions[symbol]
        pnl = (current_price - position['avg_price']) * position['quantity']
        pnl_pct = ((current_price - position['avg_price']) / position['avg_price']) * 100
        
        return {
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'quantity': position['quantity'],
            'avg_price': position['avg_price'],
            'current_price': current_price,
            'invested': position['invested']
        }
    
    def get_performance_summary(self) -> Dict:
        """
        Get comprehensive performance summary.
        
        Returns:
            Performance metrics and statistics
        """
        total_return = self.current_capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100
        
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        avg_win = self.total_profit / self.winning_trades if self.winning_trades > 0 else 0
        avg_loss = self.total_loss / self.losing_trades if self.losing_trades > 0 else 0
        profit_factor = self.total_profit / self.total_loss if self.total_loss > 0 else float('inf')
        
        return {
            'initial_capital': self.initial_capital,
            'current_capital': self.current_capital,
            'available_capital': self.available_capital,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'total_profit': self.total_profit,
            'total_loss': self.total_loss,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'active_positions': len(self.positions),
            'closed_positions': len(self.closed_positions)
        }
    
    def reset_daily(self, current_prices: Dict[str, float] = None):
        """
        Reset for new trading day - Close all positions (intraday trading).
        
        Args:
            current_prices: Dictionary of symbol -> current price for position closing
        """
        today = datetime.now().strftime('%Y-%m-%d')
        self.logger.info(f"Paper Trading: End of day reset for {today}")
        
        # Calculate today's statistics before closing
        day_trades = 0
        day_wins = 0
        day_losses = 0
        day_pnl = self.daily_pnl.get(today, 0.0)
        starting_capital = self.current_capital - day_pnl
        
        # Count today's trades
        for trade in reversed(self.trade_history):
            trade_date = datetime.fromisoformat(trade['timestamp']).strftime('%Y-%m-%d')
            if trade_date != today:
                break
            if trade['type'] == 'SELL':
                day_trades += 1
                if trade.get('pnl', 0) > 0:
                    day_wins += 1
                else:
                    day_losses += 1
        
        # Force close all open positions at end of day (intraday trading)
        if self.positions:
            self.logger.warning(f"Paper Trading: Closing {len(self.positions)} open positions at EOD")
            
            positions_to_close = list(self.positions.keys())
            for symbol in positions_to_close:
                position = self.positions[symbol]
                quantity = position['quantity']
                
                # Use current price if available, otherwise use avg price
                if current_prices and symbol in current_prices:
                    close_price = current_prices[symbol]
                else:
                    close_price = position['avg_price']
                    self.logger.warning(f"No current price for {symbol}, using avg price {close_price:.2f}")
                
                # Force sell at market close
                self.logger.info(f"EOD: Force closing {quantity} {symbol} @ ₹{close_price:.2f}")
                result = self.execute_order(
                    symbol=symbol,
                    transaction_type='SELL',
                    quantity=quantity,
                    price=close_price
                )
                
                if result['status'] == 'COMPLETE':
                    self.logger.info(f"EOD: Successfully closed {symbol}")
        
        # Save daily statistics
        daily_stat = {
            'date': today,
            'starting_capital': round(starting_capital, 2),
            'ending_capital': round(self.current_capital, 2),
            'pnl': round(day_pnl, 2),
            'trades': day_trades,
            'wins': day_wins,
            'losses': day_losses,
            'win_rate': round((day_wins / day_trades * 100) if day_trades > 0 else 0, 2)
        }
        self.daily_stats.append(daily_stat)
        
        self.logger.info(f"EOD Summary: PNL: ₹{day_pnl:,.2f}, Trades: {day_trades}, Win Rate: {daily_stat['win_rate']:.1f}%")
        
        # Save state with updated stats
        self._save_state()
    
    def _save_state(self):
        """Save paper trading state to disk."""
        state = {
            'initial_capital': self.initial_capital,
            'current_capital': self.current_capital,
            'available_capital': self.available_capital,
            'positions': {
                symbol: {
                    **pos,
                    'entry_time': pos['entry_time'].isoformat() if isinstance(pos['entry_time'], datetime) else pos['entry_time']
                }
                for symbol, pos in self.positions.items()
            },
            'closed_positions': self.closed_positions,
            'trade_history': self.trade_history[-100:],  # Keep last 100 trades
            'daily_pnl': self.daily_pnl,
            'daily_stats': self.daily_stats,  # Save daily statistics
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'total_profit': self.total_profit,
            'total_loss': self.total_loss,
            'last_updated': datetime.now().isoformat()
        }
        
        state_file = os.path.join(self.data_dir, 'paper_trading_state.json')
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def _load_state(self):
        """Load paper trading state from disk."""
        state_file = os.path.join(self.data_dir, 'paper_trading_state.json')
        
        if not os.path.exists(state_file):
            return
        
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
            
            self.current_capital = state.get('current_capital', self.initial_capital)
            self.available_capital = state.get('available_capital', self.initial_capital)
            
            # Load positions
            for symbol, pos in state.get('positions', {}).items():
                pos['entry_time'] = datetime.fromisoformat(pos['entry_time'])
                self.positions[symbol] = pos
            
            self.closed_positions = state.get('closed_positions', [])
            self.trade_history = state.get('trade_history', [])
            self.daily_pnl = state.get('daily_pnl', {})
            self.daily_stats = state.get('daily_stats', [])  # Load daily statistics
            self.total_trades = state.get('total_trades', 0)
            self.winning_trades = state.get('winning_trades', 0)
            self.losing_trades = state.get('losing_trades', 0)
            self.total_profit = state.get('total_profit', 0.0)
            self.total_loss = state.get('total_loss', 0.0)
            
            self.logger.info(f"Loaded paper trading state: {self.total_trades} trades, ₹{self.current_capital:,.2f} capital")
        
        except Exception as e:
            self.logger.error(f"Failed to load paper trading state: {e}")
    
    def get_positions(self) -> List[Dict]:
        """Get current positions (compatible with Kite API format)."""
        positions = []
        for symbol, pos in self.positions.items():
            positions.append({
                'tradingsymbol': symbol,
                'quantity': pos['quantity'],
                'average_price': pos['avg_price'],
                'pnl': 0,  # Would need current price to calculate
                'product': 'MIS',  # Intraday
                'exchange': 'NSE'
            })
        return positions
