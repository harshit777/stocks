"""
Trading Psychology Module

Manages emotional control and prevents common psychological trading biases:
- Fear: Prevents panic selling and missed opportunities
- Greed: Prevents overtrading and excessive position sizes
- Revenge trading: Blocks trades after consecutive losses
- Overconfidence: Reduces position sizing after winning streaks
- FOMO: Validates that trades meet objective criteria
- Loss aversion: Enforces stop-losses without hesitation
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from enum import Enum


class EmotionalState(Enum):
    """Emotional states that can affect trading."""
    NEUTRAL = "neutral"
    FEARFUL = "fearful"
    GREEDY = "greedy"
    REVENGE = "revenge"
    OVERCONFIDENT = "overconfident"
    FOMO = "fomo"


class TradingPsychologyGuard:
    """
    Guards against psychological biases and emotional trading.
    Enforces discipline and objective decision-making.
    """
    
    def __init__(self,
                 max_daily_trades: int = 5,
                 max_consecutive_losses: int = 3,
                 cooldown_after_loss: int = 15,  # minutes
                 reduce_size_after_wins: int = 3,
                 max_drawdown_pct: float = 0.05,  # 5% max daily drawdown
                 fomo_prevention_window: int = 5):  # minutes
        """
        Initialize psychology guard.
        
        Args:
            max_daily_trades: Maximum trades per day (prevents overtrading)
            max_consecutive_losses: Max losses before forced break
            cooldown_after_loss: Minutes to wait after a loss
            reduce_size_after_wins: Reduce size after N consecutive wins
            max_drawdown_pct: Maximum daily drawdown before stopping
            fomo_prevention_window: Minutes price must sustain before trading
        """
        self.max_daily_trades = max_daily_trades
        self.max_consecutive_losses = max_consecutive_losses
        self.cooldown_after_loss = cooldown_after_loss
        self.reduce_size_after_wins = reduce_size_after_wins
        self.max_drawdown_pct = max_drawdown_pct
        self.fomo_prevention_window = fomo_prevention_window
        
        self.logger = logging.getLogger(__name__)
        
        # Track trading statistics
        self.daily_trades = 0
        self.daily_start_capital = 0
        self.current_capital = 0
        
        # Track consecutive results
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        
        # Track recent trades
        self.recent_trades: List[Dict] = []
        self.last_trade_time = None
        self.last_loss_time = None
        
        # Current emotional state
        self.current_state = EmotionalState.NEUTRAL
        
        # Signal tracking for FOMO prevention
        self.signal_first_seen = {}
        
        self.logger.info(
            f"Trading Psychology Guard initialized - "
            f"max_daily_trades={max_daily_trades}, "
            f"max_consecutive_losses={max_consecutive_losses}"
        )
    
    def reset_daily_stats(self, starting_capital: float):
        """Reset daily statistics at market open."""
        self.daily_trades = 0
        self.daily_start_capital = starting_capital
        self.current_capital = starting_capital
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.recent_trades.clear()
        self.last_trade_time = None
        self.last_loss_time = None
        self.current_state = EmotionalState.NEUTRAL
        self.signal_first_seen.clear()
        
        self.logger.info(f"Daily stats reset - Starting capital: ₹{starting_capital:,.2f}")
    
    def update_capital(self, new_capital: float):
        """Update current capital after trades."""
        self.current_capital = new_capital
    
    def should_allow_trade(self, symbol: str, signal: str, 
                          ai_confidence: float) -> Dict[str, any]:
        """
        Check if trade should be allowed based on psychological factors.
        
        Returns:
            Dict with 'allowed' (bool), 'reason' (str), 'adjustment' (float)
        """
        checks = []
        
        # 1. Check daily trade limit (prevents overtrading/greed)
        if self.daily_trades >= self.max_daily_trades:
            self.current_state = EmotionalState.GREEDY
            return {
                'allowed': False,
                'reason': f"Daily trade limit reached ({self.max_daily_trades}). Prevents overtrading.",
                'adjustment': 0.0,
                'emotional_state': self.current_state.value
            }
        
        # 2. Check consecutive losses (prevents revenge trading)
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.current_state = EmotionalState.REVENGE
            return {
                'allowed': False,
                'reason': f"{self.consecutive_losses} consecutive losses. Taking mandatory break to reset.",
                'adjustment': 0.0,
                'emotional_state': self.current_state.value
            }
        
        # 3. Check cooldown period after loss (prevents emotional reaction)
        if self.last_loss_time:
            minutes_since_loss = (datetime.now() - self.last_loss_time).total_seconds() / 60
            if minutes_since_loss < self.cooldown_after_loss:
                self.current_state = EmotionalState.FEARFUL
                return {
                    'allowed': False,
                    'reason': f"Cooldown period active ({self.cooldown_after_loss - minutes_since_loss:.1f} min remaining). Prevents fear-based trading.",
                    'adjustment': 0.0,
                    'emotional_state': self.current_state.value
                }
        
        # 4. Check daily drawdown (prevents catastrophic losses)
        if self.daily_start_capital > 0:
            daily_pnl_pct = (self.current_capital - self.daily_start_capital) / self.daily_start_capital
            if daily_pnl_pct < -self.max_drawdown_pct:
                self.current_state = EmotionalState.FEARFUL
                return {
                    'allowed': False,
                    'reason': f"Max daily drawdown reached ({daily_pnl_pct:.2%}). Stopping to preserve capital.",
                    'adjustment': 0.0,
                    'emotional_state': self.current_state.value
                }
        
        # 5. FOMO prevention - signal must persist
        signal_key = f"{symbol}_{signal}"
        now = datetime.now()
        
        if signal_key not in self.signal_first_seen:
            self.signal_first_seen[signal_key] = now
            self.current_state = EmotionalState.FOMO
            return {
                'allowed': False,
                'reason': f"FOMO prevention: Signal just appeared. Waiting {self.fomo_prevention_window} min for confirmation.",
                'adjustment': 0.0,
                'emotional_state': self.current_state.value
            }
        
        minutes_since_signal = (now - self.signal_first_seen[signal_key]).total_seconds() / 60
        if minutes_since_signal < self.fomo_prevention_window:
            self.current_state = EmotionalState.FOMO
            return {
                'allowed': False,
                'reason': f"FOMO prevention: Signal needs {self.fomo_prevention_window - minutes_since_signal:.1f} more min of confirmation.",
                'adjustment': 0.0,
                'emotional_state': self.current_state.value
            }
        
        # 6. Calculate position size adjustment based on win/loss streak
        adjustment = self._calculate_psychological_adjustment()
        
        # Determine emotional state
        if self.consecutive_losses > 0:
            self.current_state = EmotionalState.FEARFUL
        elif self.consecutive_wins >= self.reduce_size_after_wins:
            self.current_state = EmotionalState.OVERCONFIDENT
        else:
            self.current_state = EmotionalState.NEUTRAL
        
        return {
            'allowed': True,
            'reason': "All psychological checks passed",
            'adjustment': adjustment,
            'emotional_state': self.current_state.value,
            'streak': {
                'wins': self.consecutive_wins,
                'losses': self.consecutive_losses
            }
        }
    
    def _calculate_psychological_adjustment(self) -> float:
        """
        Calculate position size adjustment based on psychological state.
        
        Returns:
            Multiplier for position size (0.5 to 1.0)
        """
        # After consecutive wins, reduce size (combat overconfidence)
        if self.consecutive_wins >= self.reduce_size_after_wins:
            reduction = min(0.3, (self.consecutive_wins - self.reduce_size_after_wins) * 0.1)
            self.logger.info(
                f"Overconfidence guard: {self.consecutive_wins} consecutive wins. "
                f"Reducing position size by {reduction:.1%}"
            )
            return 1.0 - reduction
        
        # After losses, also reduce size (rebuild confidence gradually)
        if self.consecutive_losses > 0:
            reduction = min(0.4, self.consecutive_losses * 0.15)
            self.logger.info(
                f"Fear guard: {self.consecutive_losses} consecutive losses. "
                f"Reducing position size by {reduction:.1%}"
            )
            return 1.0 - reduction
        
        return 1.0  # Normal position size
    
    def record_trade(self, symbol: str, signal: str, entry_price: float,
                    quantity: int, profit_loss: Optional[float] = None):
        """
        Record a trade for psychological tracking.
        
        Args:
            symbol: Trading symbol
            signal: BUY or SELL
            entry_price: Entry price
            quantity: Position size
            profit_loss: Realized P&L (if closing trade)
        """
        trade_record = {
            'timestamp': datetime.now(),
            'symbol': symbol,
            'signal': signal,
            'entry_price': entry_price,
            'quantity': quantity,
            'profit_loss': profit_loss
        }
        
        self.recent_trades.append(trade_record)
        self.daily_trades += 1
        self.last_trade_time = datetime.now()
        
        # Update consecutive counters if P&L is known
        if profit_loss is not None:
            if profit_loss > 0:
                self.consecutive_wins += 1
                self.consecutive_losses = 0
                self.logger.info(f"WIN: Consecutive wins: {self.consecutive_wins}")
            else:
                self.consecutive_losses += 1
                self.consecutive_wins = 0
                self.last_loss_time = datetime.now()
                self.logger.warning(f"LOSS: Consecutive losses: {self.consecutive_losses}")
        
        # Clear signal tracking after trade
        signal_key = f"{symbol}_{signal}"
        if signal_key in self.signal_first_seen:
            del self.signal_first_seen[signal_key]
    
    def enforce_stop_loss(self, symbol: str, entry_price: float,
                         current_price: float, stop_loss_pct: float) -> Dict[str, any]:
        """
        Enforce stop-loss without emotional hesitation.
        
        Returns:
            Dict with 'should_exit' (bool), 'reason' (str)
        """
        loss_pct = (current_price - entry_price) / entry_price
        
        if loss_pct <= -stop_loss_pct:
            return {
                'should_exit': True,
                'reason': f"Stop-loss triggered: {loss_pct:.2%} loss (limit: {stop_loss_pct:.2%})",
                'loss_pct': loss_pct,
                'message': "Emotion-free exit: Stop-loss is protecting your capital."
            }
        
        return {
            'should_exit': False,
            'reason': "Within acceptable loss range",
            'loss_pct': loss_pct
        }
    
    def should_take_profit(self, symbol: str, entry_price: float,
                          current_price: float, target_profit_pct: float) -> Dict[str, any]:
        """
        Prevent greed by enforcing profit targets.
        
        Returns:
            Dict with 'should_exit' (bool), 'reason' (str)
        """
        profit_pct = (current_price - entry_price) / entry_price
        
        # Enforce profit taking when target is reached
        if profit_pct >= target_profit_pct:
            return {
                'should_exit': True,
                'reason': f"Profit target reached: {profit_pct:.2%} (target: {target_profit_pct:.2%})",
                'profit_pct': profit_pct,
                'message': "Greed prevention: Lock in profits at target."
            }
        
        # Warning if profit is substantial but not at target
        if profit_pct >= target_profit_pct * 0.8:
            return {
                'should_exit': False,
                'reason': "Near profit target",
                'profit_pct': profit_pct,
                'message': f"Close to target ({profit_pct:.2%}). Consider trailing stop."
            }
        
        return {
            'should_exit': False,
            'reason': "Target not reached",
            'profit_pct': profit_pct
        }
    
    def get_discipline_report(self) -> Dict:
        """
        Get a report on trading discipline and psychological state.
        
        Returns:
            Dict with discipline metrics
        """
        if self.daily_start_capital > 0:
            daily_return = (self.current_capital - self.daily_start_capital) / self.daily_start_capital
        else:
            daily_return = 0
        
        return {
            'emotional_state': self.current_state.value,
            'daily_trades': self.daily_trades,
            'max_daily_trades': self.max_daily_trades,
            'trades_remaining': max(0, self.max_daily_trades - self.daily_trades),
            'consecutive_wins': self.consecutive_wins,
            'consecutive_losses': self.consecutive_losses,
            'daily_return_pct': daily_return * 100,
            'max_drawdown_pct': self.max_drawdown_pct * 100,
            'drawdown_remaining': (self.max_drawdown_pct + daily_return) * 100 if daily_return < 0 else self.max_drawdown_pct * 100,
            'in_cooldown': self.last_loss_time and (datetime.now() - self.last_loss_time).total_seconds() < self.cooldown_after_loss * 60,
            'recent_trades_count': len(self.recent_trades),
            'discipline_score': self._calculate_discipline_score()
        }
    
    def _calculate_discipline_score(self) -> float:
        """
        Calculate a discipline score (0-100) based on adherence to rules.
        
        Returns:
            Discipline score (0-100)
        """
        score = 100.0
        
        # Penalize for approaching limits
        if self.daily_trades > self.max_daily_trades * 0.8:
            score -= 20
        
        if self.consecutive_losses > self.max_consecutive_losses * 0.5:
            score -= 30
        
        if self.consecutive_wins > self.reduce_size_after_wins:
            score -= 10  # Small penalty for not being cautious
        
        if self.current_capital < self.daily_start_capital * (1 - self.max_drawdown_pct * 0.5):
            score -= 25
        
        return max(0.0, min(100.0, score))
    
    def get_emotional_coaching(self) -> str:
        """
        Get coaching message based on current emotional state.
        
        Returns:
            Coaching message
        """
        if self.current_state == EmotionalState.FEARFUL:
            return (
                "🧘 FEAR DETECTED: Take a deep breath. Losses are part of trading. "
                "Your strategy has rules for a reason. Trust your system."
            )
        elif self.current_state == EmotionalState.GREEDY:
            return (
                "⚠️ GREED WARNING: You've hit your daily trade limit. "
                "More trades ≠ more profit. Quality over quantity."
            )
        elif self.current_state == EmotionalState.REVENGE:
            return (
                "🛑 REVENGE TRADING BLOCKED: Step away from the terminal. "
                "Trading to 'get back at the market' only leads to more losses."
            )
        elif self.current_state == EmotionalState.OVERCONFIDENT:
            return (
                "🎯 OVERCONFIDENCE CHECK: Winning streak is great, but don't get cocky. "
                "Markets are unpredictable. Stick to your position sizing rules."
            )
        elif self.current_state == EmotionalState.FOMO:
            return (
                "⏸️ FOMO PREVENTION: Patience is a virtue. If it's a real opportunity, "
                "it will still be there after confirmation."
            )
        else:
            return (
                "✅ NEUTRAL STATE: You're trading with discipline. "
                "Keep following your plan objectively."
            )
