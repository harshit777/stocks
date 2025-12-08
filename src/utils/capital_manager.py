"""
Capital Recovery Manager

Automatically adjusts trading capital based on daily performance:
- Reduces capital after losses
- Gradually recovers capital after profits
- Maintains capital history
- Enforces maximum capital limit
"""
import json
import os
import logging
from datetime import datetime, date
from typing import Dict, Optional
from pathlib import Path


class CapitalRecoveryManager:
    """
    Manages capital allocation with automatic recovery mechanism.
    
    Rules:
    1. Start with max_initial_capital (e.g., ₹1,000)
    2. After a losing day: Reduce next day's capital by the loss amount
    3. After a profitable day: Recover capital gradually, never exceed max_initial_capital
    4. Track capital history for analysis
    """
    
    def __init__(self, max_initial_capital: float, data_dir: str = 'data/capital'):
        """
        Initialize capital recovery manager.
        
        Args:
            max_initial_capital: Maximum capital available (your ₹1,000 limit)
            data_dir: Directory to store capital history
        """
        self.max_initial_capital = max_initial_capital
        self.data_dir = data_dir
        self.capital_file = os.path.join(data_dir, 'capital_history.json')
        self.logger = logging.getLogger(__name__)
        
        # Create data directory
        os.makedirs(data_dir, exist_ok=True)
        
        # Load capital history
        self.history = self._load_history()
        
        # Calculate today's available capital
        self.current_available_capital = self._calculate_available_capital()
        
        self.logger.info(
            f"Capital Recovery Manager initialized - "
            f"Max: ₹{max_initial_capital:,.2f}, "
            f"Available Today: ₹{self.current_available_capital:,.2f}"
        )
    
    def _load_history(self) -> Dict:
        """Load capital history from file."""
        if os.path.exists(self.capital_file):
            try:
                with open(self.capital_file, 'r') as f:
                    history = json.load(f)
                self.logger.info(f"Loaded capital history: {len(history.get('daily_records', []))} days")
                return history
            except Exception as e:
                self.logger.error(f"Error loading capital history: {e}")
                return self._create_empty_history()
        else:
            self.logger.info("No capital history found. Creating new history.")
            return self._create_empty_history()
    
    def _create_empty_history(self) -> Dict:
        """Create empty history structure."""
        return {
            'max_initial_capital': self.max_initial_capital,
            'daily_records': [],
            'total_pnl': 0.0,
            'total_trades': 0,
            'winning_days': 0,
            'losing_days': 0
        }
    
    def _save_history(self):
        """Save capital history to file."""
        try:
            with open(self.capital_file, 'w') as f:
                json.dump(self.history, f, indent=2, default=str)
            self.logger.info("Capital history saved")
        except Exception as e:
            self.logger.error(f"Error saving capital history: {e}")
    
    def _calculate_available_capital(self) -> float:
        """
        Calculate available capital for today based on historical performance.
        
        Logic:
        - If this is the first day, use max_initial_capital
        - Otherwise, start with previous day's ending capital
        - Ending capital = starting capital + daily P&L
        - Never exceed max_initial_capital
        """
        today = date.today().isoformat()
        
        # Check if we already have a record for today
        for record in reversed(self.history['daily_records']):
            if record['date'] == today:
                return record['starting_capital']
        
        # No record for today - calculate from yesterday
        if not self.history['daily_records']:
            # First day ever
            return self.max_initial_capital
        
        # Get the most recent day's ending capital
        last_record = self.history['daily_records'][-1]
        last_ending_capital = last_record.get('ending_capital', self.max_initial_capital)
        
        # Never exceed max initial capital (recovery cap)
        available = min(last_ending_capital, self.max_initial_capital)
        
        self.logger.info(
            f"Calculated available capital from last day: "
            f"₹{last_ending_capital:,.2f} -> ₹{available:,.2f} "
            f"(last day P&L: ₹{last_record.get('daily_pnl', 0):+.2f})"
        )
        
        return available
    
    def get_available_capital(self) -> float:
        """Get the capital available for trading today."""
        return self.current_available_capital
    
    def record_day_end(self, daily_pnl: float, trades_count: int = 0, 
                       used_capital: float = 0.0):
        """
        Record end-of-day results and calculate next day's capital.
        
        Args:
            daily_pnl: Total profit/loss for the day
            trades_count: Number of trades executed
            used_capital: Capital that was actively used in trades
        """
        today = date.today().isoformat()
        
        # Calculate ending capital
        ending_capital = self.current_available_capital + daily_pnl
        
        # Ensure ending capital doesn't go below zero
        ending_capital = max(0, ending_capital)
        
        # Create day record
        day_record = {
            'date': today,
            'starting_capital': self.current_available_capital,
            'ending_capital': ending_capital,
            'daily_pnl': daily_pnl,
            'pnl_pct': (daily_pnl / self.current_available_capital * 100) if self.current_available_capital > 0 else 0,
            'trades_count': trades_count,
            'used_capital': used_capital,
            'capital_utilization_pct': (used_capital / self.current_available_capital * 100) if self.current_available_capital > 0 else 0
        }
        
        # Check if we already have a record for today (update it)
        updated = False
        for i, record in enumerate(self.history['daily_records']):
            if record['date'] == today:
                self.history['daily_records'][i] = day_record
                updated = True
                break
        
        if not updated:
            self.history['daily_records'].append(day_record)
        
        # Update summary statistics
        self.history['total_pnl'] = sum(r['daily_pnl'] for r in self.history['daily_records'])
        self.history['total_trades'] += trades_count
        
        if daily_pnl > 0:
            self.history['winning_days'] = sum(1 for r in self.history['daily_records'] if r['daily_pnl'] > 0)
        elif daily_pnl < 0:
            self.history['losing_days'] = sum(1 for r in self.history['daily_records'] if r['daily_pnl'] < 0)
        
        # Save to file
        self._save_history()
        
        # Log the update
        self.logger.info("=" * 70)
        self.logger.info("📊 END OF DAY - CAPITAL RECOVERY REPORT")
        self.logger.info("=" * 70)
        self.logger.info(f"Date: {today}")
        self.logger.info(f"Starting Capital: ₹{self.current_available_capital:,.2f}")
        self.logger.info(f"Daily P&L: ₹{daily_pnl:+,.2f} ({day_record['pnl_pct']:+.2f}%)")
        self.logger.info(f"Ending Capital: ₹{ending_capital:,.2f}")
        self.logger.info(f"Max Initial Capital: ₹{self.max_initial_capital:,.2f}")
        
        if ending_capital < self.current_available_capital:
            deficit = self.current_available_capital - ending_capital
            self.logger.warning(f"⚠️  Capital Reduced: -₹{deficit:.2f}")
            self.logger.warning(f"Tomorrow's Budget: ₹{ending_capital:,.2f}")
        elif ending_capital > self.current_available_capital:
            gain = ending_capital - self.current_available_capital
            capped_capital = min(ending_capital, self.max_initial_capital)
            recovery = capped_capital - self.current_available_capital
            self.logger.info(f"✅ Capital Recovered: +₹{recovery:.2f}")
            self.logger.info(f"Tomorrow's Budget: ₹{capped_capital:,.2f}")
            if ending_capital > self.max_initial_capital:
                excess = ending_capital - self.max_initial_capital
                self.logger.info(f"💡 Capital capped at max limit (excess: ₹{excess:.2f})")
        
        self.logger.info(f"Total Trades Today: {trades_count}")
        self.logger.info(f"Capital Utilization: {day_record['capital_utilization_pct']:.1f}%")
        self.logger.info("=" * 70)
        
        return ending_capital
    
    def get_performance_summary(self) -> Dict:
        """Get overall performance summary."""
        if not self.history['daily_records']:
            return {
                'total_days': 0,
                'total_pnl': 0,
                'avg_daily_pnl': 0,
                'winning_days': 0,
                'losing_days': 0,
                'win_rate': 0,
                'current_capital': self.current_available_capital,
                'max_capital': self.max_initial_capital,
                'capital_recovery_pct': 100.0
            }
        
        total_days = len(self.history['daily_records'])
        winning_days = self.history['winning_days']
        losing_days = self.history['losing_days']
        total_pnl = self.history['total_pnl']
        
        return {
            'total_days': total_days,
            'total_pnl': total_pnl,
            'avg_daily_pnl': total_pnl / total_days if total_days > 0 else 0,
            'winning_days': winning_days,
            'losing_days': losing_days,
            'win_rate': (winning_days / total_days * 100) if total_days > 0 else 0,
            'current_capital': self.current_available_capital,
            'max_capital': self.max_initial_capital,
            'capital_recovery_pct': (self.current_available_capital / self.max_initial_capital * 100) if self.max_initial_capital > 0 else 0,
            'total_trades': self.history.get('total_trades', 0)
        }
    
    def get_recent_history(self, days: int = 7) -> list:
        """Get recent trading history."""
        return self.history['daily_records'][-days:] if self.history['daily_records'] else []
    
    def get_recovery_status(self) -> Dict:
        """
        Get capital recovery status.
        
        Returns info about how much capital needs to be recovered.
        """
        capital_deficit = self.max_initial_capital - self.current_available_capital
        
        if capital_deficit <= 0:
            status = "full_capital"
            message = "✅ Trading with full capital"
        elif capital_deficit < self.max_initial_capital * 0.1:
            status = "minor_recovery"
            message = f"⚡ Near full recovery (₹{capital_deficit:.2f} to go)"
        elif capital_deficit < self.max_initial_capital * 0.5:
            status = "moderate_recovery"
            message = f"🔄 Recovering capital (₹{capital_deficit:.2f} deficit)"
        else:
            status = "major_recovery"
            message = f"⚠️  Major recovery needed (₹{capital_deficit:.2f} deficit)"
        
        return {
            'status': status,
            'message': message,
            'current_capital': self.current_available_capital,
            'max_capital': self.max_initial_capital,
            'capital_deficit': capital_deficit,
            'recovery_pct': (self.current_available_capital / self.max_initial_capital * 100) if self.max_initial_capital > 0 else 0
        }
    
    def force_reset_capital(self, new_capital: Optional[float] = None):
        """
        Force reset capital to a specific amount or max initial capital.
        Use with caution - for manual intervention only.
        
        Args:
            new_capital: New capital amount (defaults to max_initial_capital)
        """
        new_amount = new_capital if new_capital is not None else self.max_initial_capital
        self.current_available_capital = new_amount
        
        today = date.today().isoformat()
        self.history['daily_records'].append({
            'date': today,
            'starting_capital': new_amount,
            'ending_capital': new_amount,
            'daily_pnl': 0.0,
            'pnl_pct': 0.0,
            'trades_count': 0,
            'used_capital': 0.0,
            'capital_utilization_pct': 0.0,
            'note': 'Manual capital reset'
        })
        
        self._save_history()
        
        self.logger.warning(f"⚠️  MANUAL CAPITAL RESET: ₹{new_amount:,.2f}")
