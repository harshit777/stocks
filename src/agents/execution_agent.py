"""
Agent 4: ExecutionAgent

Responsibility: Place orders and maintain the ONE authoritative position book.

This is the only place in the system that calls trader.place_order().
No other agent, strategy, or wrapper touches the broker API for orders.

Eliminates the dual-position-book problem: BaseStrategy.positions and
LiveTradingWrapper.positions no longer exist as parallel books.
This agent IS the book.

On every fill:
  - Updates internal position book
  - Notifies RiskGate (capital accounting)
  - Notifies SignalEngine (trade outcome for psychology guard)
  - Notifies PostTradeAgent (P&L logging)
"""
import logging
import threading
from typing import Dict, List, Optional, Callable
from datetime import datetime

from ..kite_trader.order_manager import OrderManager
from .risk_gate import RiskDecision


class Position:
    """Single open position."""
    __slots__ = ('symbol', 'quantity', 'avg_price', 'invested', 'entry_time', 'stop_price')

    def __init__(self, symbol: str, quantity: int, avg_price: float,
                 stop_price: float):
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price
        self.invested = avg_price * quantity
        self.entry_time = datetime.now()
        self.stop_price = stop_price

    def unrealised_pnl(self, current_price: float) -> float:
        return (current_price - self.avg_price) * self.quantity

    def pnl_pct(self, current_price: float) -> float:
        return (current_price - self.avg_price) / self.avg_price if self.avg_price > 0 else 0.0


class ExecutionAgent:
    """
    Places orders and owns the single source-of-truth position book.

    Thread-safe: uses a lock around position mutations and order dedup.
    """

    def __init__(self, trader, stop_loss_pct: float = 0.015):
        """
        Args:
            trader:         KiteTrader instance (must have order_manager set)
            stop_loss_pct:  Default stop-loss % for new positions
        """
        self.trader = trader
        self.stop_loss_pct = stop_loss_pct
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

        # THE position book — one dict, one truth
        self.positions: Dict[str, Position] = {}

        # Dedup: prevent placing same-direction order while one is pending
        self._pending: Dict[str, str] = {}   # symbol → 'BUY'/'SELL'

        # Callbacks — registered by other agents
        self._on_fill_callbacks: List[Callable] = []

        # Order history for review
        self.order_history: List[Dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_on_fill(self, callback: Callable):
        """
        Register a callback to be called after every confirmed fill.

        Signature: callback(symbol, transaction_type, quantity, fill_price, pnl)
        pnl is None for BUY fills; float for SELL fills.
        """
        self._on_fill_callbacks.append(callback)

    def execute(self, symbol: str, decision: RiskDecision, transaction_type: str) -> bool:
        """
        Place an order based on an approved RiskDecision.

        Args:
            symbol:           NSE trading symbol
            decision:         Approved RiskDecision from RiskGate
            transaction_type: 'BUY' or 'SELL'

        Returns:
            True if order filled, False otherwise
        """
        if not decision.approved:
            self.logger.warning(f"ExecutionAgent: called with rejected decision for {symbol}")
            return False

        with self._lock:
            # Dedup check
            if symbol in self._pending:
                if self._pending[symbol] == transaction_type:
                    self.logger.warning(
                        f"ExecutionAgent: duplicate {transaction_type} blocked for {symbol}"
                    )
                    return False
            self._pending[symbol] = transaction_type

        try:
            order_id = self.trader.place_order(
                symbol=symbol,
                transaction_type=transaction_type,
                quantity=decision.quantity,
                order_type='LIMIT',
                product='MIS',
                price=decision.limit_price,
                verify_execution=True,   # uses OrderManager — waits for COMPLETE status
            )

            if not order_id:
                self.logger.error(f"ExecutionAgent: order placement returned None for {symbol}")
                return False

            fill_price = decision.limit_price  # confirmed by OrderManager
            self._record_fill(symbol, transaction_type, decision.quantity, fill_price)
            return True

        except Exception as e:
            self.logger.error(f"ExecutionAgent: order failed for {symbol}: {e}")
            return False

        finally:
            with self._lock:
                self._pending.pop(symbol, None)

    def square_off_all(self, reason: str = 'EOD square-off'):
        """
        Close all open positions. Call at 3:20 PM or on halt.
        """
        self.logger.info(f"ExecutionAgent: squaring off all positions — {reason}")
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            try:
                # Get fresh price
                quotes = self.trader.get_quote([symbol])
                ltp = quotes.get(f"NSE:{symbol}", {}).get('last_price', pos.avg_price)
                limit = round(ltp * (1 - 0.003), 2)   # 0.3% below LTP

                decision = RiskDecision(
                    approved=True,
                    quantity=pos.quantity,
                    limit_price=limit,
                    reason=reason,
                )
                self.execute(symbol, decision, 'SELL')
            except Exception as e:
                self.logger.error(f"ExecutionAgent: square-off failed for {symbol}: {e}")

    # ------------------------------------------------------------------
    # Position book queries
    # ------------------------------------------------------------------

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions and self.positions[symbol].quantity > 0

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def all_positions(self) -> Dict[str, Position]:
        return dict(self.positions)

    def sync_from_broker(self):
        """
        Pull actual positions from Kite and reconcile.
        Call at startup and every 10 minutes.
        """
        try:
            broker = self.trader.get_positions()
            net = {p['tradingsymbol']: p for p in broker.get('net', [])
                   if p.get('quantity', 0) != 0}

            with self._lock:
                # Add/update positions found at broker but not tracked
                for symbol, bp in net.items():
                    qty = bp.get('quantity', 0)
                    avg = bp.get('average_price', 0)
                    if qty > 0 and avg > 0:
                        if symbol not in self.positions:
                            self.logger.warning(
                                f"ExecutionAgent sync: adding untracked position {symbol} {qty}@{avg}"
                            )
                            self.positions[symbol] = Position(
                                symbol, qty, avg,
                                stop_price=avg * (1 - self.stop_loss_pct)
                            )
                        else:
                            # Update qty/price to match broker
                            p = self.positions[symbol]
                            if p.quantity != qty:
                                self.logger.warning(
                                    f"ExecutionAgent sync: {symbol} qty {p.quantity}→{qty}"
                                )
                                p.quantity = qty
                                p.avg_price = avg

                # Remove positions we track that broker no longer has
                for symbol in list(self.positions.keys()):
                    if symbol not in net:
                        self.logger.warning(
                            f"ExecutionAgent sync: removing stale position {symbol}"
                        )
                        del self.positions[symbol]

            self.logger.info(
                f"ExecutionAgent sync: {len(self.positions)} positions in sync with broker"
            )
        except Exception as e:
            self.logger.error(f"ExecutionAgent sync failed: {e}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_fill(self, symbol: str, transaction_type: str,
                     quantity: int, fill_price: float):
        pnl: Optional[float] = None

        with self._lock:
            if transaction_type == 'BUY':
                self.positions[symbol] = Position(
                    symbol, quantity, fill_price,
                    stop_price=fill_price * (1 - self.stop_loss_pct)
                )
                self.logger.info(
                    f"✅ FILLED BUY: {quantity} {symbol} @ ₹{fill_price:.2f} "
                    f"| stop=₹{self.positions[symbol].stop_price:.2f}"
                )

            elif transaction_type == 'SELL' and symbol in self.positions:
                pos = self.positions[symbol]
                pnl = (fill_price - pos.avg_price) * quantity
                emoji = '🟢' if pnl >= 0 else '🔴'
                self.logger.info(
                    f"{emoji} FILLED SELL: {quantity} {symbol} @ ₹{fill_price:.2f} "
                    f"| entry=₹{pos.avg_price:.2f} | P&L=₹{pnl:+.2f}"
                )
                remaining = pos.quantity - quantity
                if remaining <= 0:
                    del self.positions[symbol]
                else:
                    pos.quantity = remaining

        # Record in history
        self.order_history.append({
            'timestamp':        datetime.now().isoformat(),
            'symbol':           symbol,
            'transaction_type': transaction_type,
            'quantity':         quantity,
            'fill_price':       fill_price,
            'pnl':              pnl,
        })

        # Notify all registered callbacks
        for cb in self._on_fill_callbacks:
            try:
                cb(symbol, transaction_type, quantity, fill_price, pnl)
            except Exception as e:
                self.logger.error(f"ExecutionAgent callback error: {e}")
