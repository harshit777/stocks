"""
Agent 5: PositionMonitor

Responsibility: Watch every open position and trigger exits when needed.

Runs every iteration (every 2 minutes) against live quotes.

Exit triggers (checked in priority order):
  1. Stop-loss hit            — immediate exit, no hesitation (uses TradingPsychologyGuard)
  2. Trailing stop tightened  — ratchets stop up as price rises
  3. Target reached           — locks in profit at day_high (or target_multiplier × entry)
  4. Time stop                — close if position held > max_hold_minutes
  5. Signal reversal          — SignalEngine says SELL while we're long

Does NOT place orders directly — calls ExecutionAgent.execute().
"""
import logging
from typing import Dict, Optional
from datetime import datetime

from .execution_agent import ExecutionAgent, Position
from .risk_gate import RiskGate, RiskDecision
from ..ai_modules.trading_psychology import TradingPsychologyGuard


class PositionMonitor:
    """
    Monitors open positions and triggers exits via ExecutionAgent.
    """

    def __init__(
        self,
        execution_agent: ExecutionAgent,
        risk_gate: RiskGate,
        trader,
        stop_loss_pct: float = 0.015,
        target_pct: float = 0.025,          # 2.5% profit target
        trailing_stop_activation: float = 0.01,  # activate trailing stop at 1% profit
        trailing_stop_distance: float = 0.008,   # trail 0.8% below peak
        max_hold_minutes: int = 90,              # never hold > 90 min intraday
    ):
        self.execution = execution_agent
        self.risk_gate = risk_gate
        self.trader = trader
        self.stop_loss_pct = stop_loss_pct
        self.target_pct = target_pct
        self.trailing_stop_activation = trailing_stop_activation
        self.trailing_stop_distance = trailing_stop_distance
        self.max_hold_minutes = max_hold_minutes
        self.logger = logging.getLogger(__name__)

        # Track peak price per position for trailing stop
        self._peak_price: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Main loop call
    # ------------------------------------------------------------------

    def monitor(self, signal_overrides: Optional[Dict[str, Optional[str]]] = None) -> Dict[str, str]:
        """
        Check all open positions and exit any that hit a trigger.

        Args:
            signal_overrides: Optional dict of symbol → signal from SignalEngine.
                              If SignalEngine says 'SELL' on an open long, we close.

        Returns:
            Dict of symbol → exit_reason for positions that were closed.
        """
        signal_overrides = signal_overrides or {}
        exits = {}

        positions = self.execution.all_positions()
        if not positions:
            return exits

        # Batch quote for all open symbols in ONE call
        symbols = list(positions.keys())
        try:
            quotes = self.trader.get_quote(symbols)
        except Exception as e:
            self.logger.error(f"PositionMonitor: quote fetch failed: {e}")
            return exits

        for symbol, pos in positions.items():
            key = f"NSE:{symbol}"
            current_price = quotes.get(key, {}).get('last_price', 0)
            if current_price <= 0:
                continue

            reason = self._check_exit(symbol, pos, current_price,
                                       signal_overrides.get(symbol))
            if reason:
                self._exit(symbol, pos, current_price, reason)
                exits[symbol] = reason

        return exits

    # ------------------------------------------------------------------
    # Exit trigger evaluation
    # ------------------------------------------------------------------

    def _check_exit(
        self,
        symbol: str,
        pos: Position,
        current_price: float,
        signal_override: Optional[str],
    ) -> Optional[str]:
        """
        Return exit reason string if position should be closed, else None.
        """
        entry = pos.avg_price

        # 1. Stop-loss (hard floor — no debate)
        if current_price <= pos.stop_price:
            loss_pct = (current_price - entry) / entry
            return f"Stop-loss: {loss_pct:.2%} loss (limit {self.stop_loss_pct:.2%})"

        # 2. Update trailing stop
        self._update_trailing_stop(symbol, pos, current_price)

        # 3. Target reached
        profit_pct = (current_price - entry) / entry
        if profit_pct >= self.target_pct:
            return f"Target reached: {profit_pct:.2%} profit"

        # 4. Time stop
        hold_minutes = (datetime.now() - pos.entry_time).total_seconds() / 60
        if hold_minutes >= self.max_hold_minutes:
            return f"Time stop: held {hold_minutes:.0f} min (max {self.max_hold_minutes})"

        # 5. SignalEngine reversal
        if signal_override == 'SELL':
            return "Signal reversal: SignalEngine says SELL"

        return None

    def _update_trailing_stop(self, symbol: str, pos: Position, current_price: float):
        """
        Ratchet stop-loss upward as price climbs.
        Only activates once position is profitable by trailing_stop_activation %.
        """
        entry = pos.avg_price
        profit_pct = (current_price - entry) / entry

        if profit_pct < self.trailing_stop_activation:
            return  # not yet profitable enough to trail

        # Track peak
        peak = self._peak_price.get(symbol, current_price)
        if current_price > peak:
            self._peak_price[symbol] = current_price
            peak = current_price

        # New trailing stop = peak - trail distance
        new_stop = peak * (1 - self.trailing_stop_distance)

        if new_stop > pos.stop_price:
            old_stop = pos.stop_price
            pos.stop_price = new_stop
            self.logger.debug(
                f"PositionMonitor: {symbol} trailing stop "
                f"₹{old_stop:.2f} → ₹{new_stop:.2f} (peak=₹{peak:.2f})"
            )

    # ------------------------------------------------------------------
    # Exit execution
    # ------------------------------------------------------------------

    def _exit(self, symbol: str, pos: Position, current_price: float, reason: str):
        """Place the exit order via ExecutionAgent."""
        self.logger.info(f"PositionMonitor: exiting {symbol} — {reason}")
        limit_price = round(current_price * (1 - 0.003), 2)
        decision = RiskDecision(
            approved=True,
            quantity=pos.quantity,
            limit_price=limit_price,
            reason=reason,
        )
        success = self.execution.execute(symbol, decision, 'SELL')
        if success:
            self._peak_price.pop(symbol, None)
        else:
            self.logger.error(
                f"PositionMonitor: exit order FAILED for {symbol} — manual action required"
            )

    def reset_daily(self):
        """Clear tracking state at start of new day."""
        self._peak_price.clear()
