"""
Agent 3: RiskGate

Responsibility: APPROVE or REJECT every proposed trade before it touches the market.

This is the most important agent. All the signal quality in the world means nothing
if you size wrong or trade when you shouldn't. Every rupee lost here is permanent.

Checks (in order — fail fast):
  1. Trading not halted (daily loss limit, broker health)
  2. Capital available for this trade
  3. Maximum concurrent positions not exceeded
  4. Position size is valid (≥1 share, within max_position_pct)
  5. Trade is profitable AFTER all costs (brokerage, STT, GST, stamp duty)
     — uses CostCalculator.get_breakeven_price()
  6. Risk/reward is acceptable given current stop-loss
  7. No existing position in same symbol (no averaging down)

Returns:
  RiskDecision(approved=True, quantity=N, limit_price=P)  — go ahead
  RiskDecision(approved=False, reason=str)                 — blocked
"""
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict
from datetime import datetime

from ..utils.cost_calculator import get_cost_calculator
from ..utils.capital_manager import CapitalRecoveryManager


@dataclass
class RiskDecision:
    approved: bool
    quantity: int = 0
    limit_price: float = 0.0
    reason: str = ''
    cost_breakdown: Dict = field(default_factory=dict)


class RiskGate:
    """
    Single chokepoint for all trade approvals.

    Thread-safe: uses a lock so concurrent signal processing can't
    double-allocate capital.
    """

    def __init__(
        self,
        max_capital: float,
        max_daily_loss: float,
        max_position_pct: float = 0.15,   # ponytail: kept as hard cap; primary sizing is ATR-based
        max_concurrent_positions: int = 4,
        stop_loss_pct: float = 0.015,
        target_pct: float = 0.025,        # must match PositionMonitor.target_pct exactly
        min_risk_reward: float = 3.0,
        risk_per_trade_pct: float = 0.01, # risk exactly 1% of capital per trade
        slippage: float = 0.003,
    ):
        """
        Args:
            max_capital:               Total capital available today (₹)
            max_daily_loss:            Halt threshold — daily loss in ₹
            max_position_pct:          Hard-cap % of capital per position (ATR sizing is primary)
            max_concurrent_positions:  Max open positions at one time
            stop_loss_pct:             Stop-loss % from entry (must match PositionMonitor)
            target_pct:                Profit target % — MUST match PositionMonitor.target_pct
            min_risk_reward:           Minimum reward:risk ratio required
            risk_per_trade_pct:        Fraction of capital to risk per trade (ATR sizing)
            slippage:                  Buffer added to limit price
        """
        self.max_capital = max_capital
        self.max_daily_loss = max_daily_loss
        self.max_position_pct = max_position_pct
        self.max_concurrent_positions = max_concurrent_positions
        self.stop_loss_pct = stop_loss_pct
        self.target_pct = target_pct
        self.min_risk_reward = min_risk_reward
        self.risk_per_trade_pct = risk_per_trade_pct
        self.slippage = slippage

        self.cost_calculator = get_cost_calculator()
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

        # Runtime state
        self.used_capital: float = 0.0
        self.daily_pnl: float = 0.0
        self.open_positions: Dict[str, Dict] = {}   # symbol → {qty, avg_price, invested}
        self.halted: bool = False
        self.halt_reason: str = ''
        self.trades_today: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        symbol: str,
        signal: str,
        current_price: float,
        day_high: float,
        day_low: float,
    ) -> RiskDecision:
        """
        Evaluate whether a proposed trade should be approved.

        Args:
            symbol:        NSE symbol
            signal:        'BUY' or 'SELL'
            current_price: Latest LTP
            day_high:      Today's high (for risk/reward calc)
            day_low:       Today's low

        Returns:
            RiskDecision
        """
        with self._lock:
            return self._evaluate(symbol, signal, current_price, day_high, day_low)

    def evaluate_short(
        self,
        symbol: str,
        current_price: float,
        day_high: float,
        day_low: float,
    ) -> RiskDecision:
        """
        Evaluate a SHORT (SELL-to-open) entry on MIS.

        Mirror of the BUY evaluation: same sizing, same R/R gate, reversed direction.
        Stop is ABOVE entry (price rises = loss). Target is entry × (1 - target_pct).

        Only called when SignalEngine says SELL and we have NO open position.
        """
        with self._lock:
            if self.halted:
                return RiskDecision(False, reason=f"Trading halted: {self.halt_reason}")

            if symbol in self.open_positions:
                return RiskDecision(False, reason=f"{symbol}: already have position (no double short)")

            if len(self.open_positions) >= self.max_concurrent_positions:
                return RiskDecision(False, reason=f"Max concurrent positions reached")

            # ATR-based sizing — same formula, stop is above entry for shorts
            limit_price  = round(current_price * (1 - self.slippage), 2)   # sell slightly below
            stop_price   = round(limit_price   * (1 + self.stop_loss_pct), 2)  # buy back if rises
            stop_distance = stop_price - limit_price
            if stop_distance <= 0:
                return RiskDecision(False, reason=f"{symbol}: degenerate short stop distance")

            rupee_risk = self.available_capital * self.risk_per_trade_pct
            quantity = int(rupee_risk / stop_distance)
            max_qty_by_pct = int(self.available_capital * self.max_position_pct / limit_price)
            quantity = min(quantity, max_qty_by_pct)
            if quantity < 1:
                return RiskDecision(False,
                    reason=f"Insufficient capital for short: {symbol} @ ₹{limit_price:.2f}")

            trade_value = limit_price * quantity
            if trade_value > self.available_capital:
                return RiskDecision(False,
                    reason=f"Capital insufficient for short: need ₹{trade_value:.2f}")

            target_price = round(limit_price * (1 - self.target_pct), 2)
            potential_profit = limit_price - target_price
            potential_loss   = stop_price  - limit_price
            rr = potential_profit / potential_loss if potential_loss > 0 else 0
            if rr < self.min_risk_reward:
                return RiskDecision(False,
                    reason=f"{symbol}: short R/R {rr:.2f} < minimum {self.min_risk_reward:.2f}")

            self.logger.info(
                f"✅ RiskGate APPROVED SHORT: SELL {quantity} {symbol} @ ₹{limit_price:.2f} "
                f"| R/R={rr:.2f} | stop=₹{stop_price:.2f} | target=₹{target_price:.2f}"
            )
            return RiskDecision(
                approved=True, quantity=quantity, limit_price=limit_price,
                reason="Short entry approved",
            )

    def record_fill(self, symbol: str, transaction_type: str,
                    quantity: int, fill_price: float):
        """
        Call this AFTER an order is confirmed filled.
        Updates capital allocation and position book.
        """
        with self._lock:
            trade_value = fill_price * quantity

            if transaction_type == 'BUY':
                if symbol in self.open_positions and self.open_positions[symbol].get('side') == 'SHORT':
                    # BUY-to-close a short — record P&L (short profits when price falls)
                    pos = self.open_positions[symbol]
                    pnl = (pos['avg_price'] - fill_price) * quantity
                    self.daily_pnl += pnl
                    self.used_capital -= pos['invested'] * (quantity / pos['quantity'])
                    remaining = pos['quantity'] - quantity
                    if remaining <= 0:
                        del self.open_positions[symbol]
                    else:
                        pos['quantity'] = remaining
                        pos['invested'] = pos['avg_price'] * remaining
                else:
                    # BUY-to-open a long
                    self.used_capital += trade_value
                    self.trades_today += 1
                    self.open_positions[symbol] = {
                        'quantity':   quantity,
                        'avg_price':  fill_price,
                        'invested':   trade_value,
                        'entry_time': datetime.now(),
                        'side':       'LONG',
                    }

            elif transaction_type == 'SELL':
                if symbol in self.open_positions and self.open_positions[symbol].get('side') == 'LONG':
                    # SELL-to-close a long
                    pos = self.open_positions[symbol]
                    pnl = (fill_price - pos['avg_price']) * quantity
                    self.daily_pnl += pnl
                    self.used_capital -= pos['invested'] * (quantity / pos['quantity'])
                    remaining = pos['quantity'] - quantity
                    if remaining <= 0:
                        del self.open_positions[symbol]
                    else:
                        pos['quantity'] = remaining
                        pos['invested'] = pos['avg_price'] * remaining
                elif symbol not in self.open_positions:
                    # SELL-to-open a short
                    self.used_capital += trade_value
                    self.trades_today += 1
                    self.open_positions[symbol] = {
                        'quantity':   quantity,
                        'avg_price':  fill_price,
                        'invested':   trade_value,
                        'entry_time': datetime.now(),
                        'side':       'SHORT',
                    }

            # Halt on daily loss breach (checked after any closing trade)
            if self.daily_pnl < -self.max_daily_loss:
                self.halted = True
                self.halt_reason = (
                    f"Daily loss limit hit: ₹{self.daily_pnl:.2f} < -₹{self.max_daily_loss:.2f}"
                )
                self.logger.error(f"🛑 RiskGate: {self.halt_reason}")

    def release_halt(self):
        """Manual override — use only after reviewing positions."""
        with self._lock:
            self.halted = False
            self.halt_reason = ''
            self.logger.warning("RiskGate: halt released manually")

    def reset_daily(self, new_capital: float):
        """Call at market open each day."""
        with self._lock:
            self.max_capital = new_capital
            self.used_capital = 0.0
            self.daily_pnl = 0.0
            self.open_positions.clear()
            self.halted = False
            self.halt_reason = ''
            self.trades_today = 0
            self.logger.info(f"RiskGate: daily reset — available capital ₹{new_capital:,.2f}")

    @property
    def available_capital(self) -> float:
        return max(0.0, self.max_capital - self.used_capital)

    def status(self) -> Dict:
        with self._lock:
            return {
                'halted':              self.halted,
                'halt_reason':         self.halt_reason,
                'max_capital':         self.max_capital,
                'used_capital':        self.used_capital,
                'available_capital':   self.available_capital,
                'daily_pnl':           self.daily_pnl,
                'open_positions':      len(self.open_positions),
                'trades_today':        self.trades_today,
            }

    # ------------------------------------------------------------------
    # Internal evaluation (already inside lock)
    # ------------------------------------------------------------------

    def _evaluate(
        self,
        symbol: str,
        signal: str,
        current_price: float,
        day_high: float,
        day_low: float,
    ) -> RiskDecision:

        # 1. Hard halt
        if self.halted:
            return RiskDecision(False, reason=f"Trading halted: {self.halt_reason}")

        # 2. SELL close-long check — only if we're already long
        if signal == 'SELL':
            if symbol not in self.open_positions:
                return RiskDecision(False, reason=f"{symbol}: no open position to sell")
            pos = self.open_positions[symbol]
            qty = pos['quantity']
            limit = round(current_price * (1 - self.slippage), 2)
            return RiskDecision(True, quantity=qty, limit_price=limit,
                                reason="SELL approved")

        # 3. BUY checks
        # 3a. Already in this symbol — no averaging down
        if symbol in self.open_positions:
            return RiskDecision(False, reason=f"{symbol}: already have open position (no averaging)")

        # 3b. Max concurrent positions
        if len(self.open_positions) >= self.max_concurrent_positions:
            return RiskDecision(False,
                reason=f"Max concurrent positions reached ({self.max_concurrent_positions})")

        # 3c. ATR-based position sizing — risk exactly risk_per_trade_pct of capital
        #     qty = (capital × risk_pct) / (entry - stop)
        #     This normalises exposure across all stocks regardless of price level.
        limit_price  = round(current_price * (1 + self.slippage), 2)
        stop_price   = round(limit_price * (1 - self.stop_loss_pct), 2)
        stop_distance = limit_price - stop_price
        if stop_distance <= 0:
            return RiskDecision(False, reason=f"{symbol}: degenerate stop distance")

        rupee_risk = self.available_capital * self.risk_per_trade_pct
        quantity = int(rupee_risk / stop_distance)

        # Hard cap: never exceed max_position_pct of capital in one stock
        max_qty_by_pct = int(self.available_capital * self.max_position_pct / limit_price)
        quantity = min(quantity, max_qty_by_pct)

        if quantity < 1:
            return RiskDecision(False,
                reason=f"Insufficient capital: ₹{self.available_capital:.2f} → 0 shares "
                       f"of {symbol} @ ₹{limit_price:.2f} (stop_dist=₹{stop_distance:.2f})")

        trade_value = limit_price * quantity

        # 3d. Capital check
        if trade_value > self.available_capital:
            return RiskDecision(False,
                reason=f"Capital insufficient: need ₹{trade_value:.2f}, have ₹{self.available_capital:.2f}")

        # 3e. Cost breakeven check
        breakeven = self.cost_calculator.get_breakeven_price(limit_price, quantity, 'MIS')
        # Use the SAME target as PositionMonitor to avoid R/R approval/exit mismatch
        target_price = round(limit_price * (1 + self.target_pct), 2)
        if target_price <= breakeven:
            return RiskDecision(False,
                reason=f"{symbol}: target ₹{target_price:.2f} ≤ breakeven ₹{breakeven:.2f} after costs")

        # 3f. Risk/reward check — now consistent with actual exit target
        potential_profit = target_price - limit_price
        potential_loss   = limit_price - stop_price
        rr = potential_profit / potential_loss
        if rr < self.min_risk_reward:
            return RiskDecision(False,
                reason=f"{symbol}: R/R {rr:.2f} < minimum {self.min_risk_reward:.2f}")

        # All checks passed
        cost_info = self.cost_calculator.calculate_total_cost(
            limit_price, quantity, 'BUY', 'MIS'
        )
        self.logger.info(
            f"✅ RiskGate APPROVED: BUY {quantity} {symbol} @ ₹{limit_price:.2f} "
            f"| R/R={rr:.2f} | cost=₹{cost_info['total_cost']:.2f} "
            f"| breakeven=₹{breakeven:.2f} | target=₹{target_price:.2f}"
        )
        return RiskDecision(
            approved=True,
            quantity=quantity,
            limit_price=limit_price,
            reason="All risk checks passed",
            cost_breakdown=cost_info,
        )
