"""
PaperBroker — simulated order execution on top of a real KiteTrader.

Market data (quotes, candles, profile) is delegated to the wrapped trader.
Anything that could place, modify or cancel a REAL order is handled here
and never reaches Zerodha. The raw Kite client and the OrderManager are not
reachable through this object at all.

Fills follow how a limit order behaves on the exchange:
  - a BUY fills against the sell side of the order book (best ask first, walking up
    through the levels for a larger order); a SELL fills against the buy side
  - it fills at the price actually available, which may be better than the limit,
    never worse
  - if the market is beyond the limit (the price ran away, or fell through a sell
    limit) the order does not fill; it is re-checked for `fill_wait` seconds and then
    cancelled, like an order that times out
  - if the order book isn't available, the last traded price is used under the same rule
  - a small adverse move (`slippage_bps`, default 5 = 0.05%) is applied to every fill as a
    stand-in for the latency between seeing a price and the order reaching the exchange.
    This is an assumption, not a measurement; it never pushes a fill past the limit.

Not modelled: partial fills (an order the visible book can't cover is not filled),
queue position, margin/leverage, and broker rejections.
"""
import logging
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Attributes that could be used to bypass the simulation and hit the real broker.
_BLOCKED = frozenset({'kite', 'order_manager'})


class PaperBroker:
    trading_mode = 'paper'

    def __init__(self, trader, fill_wait: float = 6.0, poll_interval: float = 2.0,
                 sleep: Callable[[float], None] = time.sleep, slippage_bps: float = 5.0):
        self._trader = trader
        self._slip = slippage_bps / 10_000.0
        self._lock = threading.Lock()
        self._positions: Dict[str, Dict] = {}   # symbol -> {quantity, average_price}
        self._orders: List[Dict] = []
        self._fills: Dict[str, float] = {}      # order_id -> price actually received
        self._seq = 0
        self._fill_wait = fill_wait
        self._poll = max(poll_interval, 0.1)
        self._sleep = sleep

    # ------------------------------------------------------------------
    # Fill model
    # ------------------------------------------------------------------

    def _fill_price(self, symbol: str, side: str, qty: int,
                    limit: Optional[float]) -> Optional[float]:
        """Price we would receive right now, or None if the market is beyond the limit."""
        q = self._trader.get_quote([symbol]).get(f"NSE:{symbol}", {})
        ltp = q.get('last_price') or 0
        book = (q.get('depth') or {}).get('sell' if side == 'BUY' else 'buy') or []
        levels = [(float(l['price']), int(l.get('quantity', 0))) for l in book
                  if l.get('price', 0) > 0 and l.get('quantity', 0) > 0]

        if levels:
            levels.sort(reverse=(side == 'SELL'))        # best price first
            taken, cost = 0, 0.0
            for price, avail in levels:
                if limit and ((side == 'BUY' and price > limit) or
                              (side == 'SELL' and price < limit)):
                    break
                n = min(qty - taken, avail)
                taken += n
                cost += n * price
                if taken >= qty:
                    return self._with_slippage(side, cost / qty, limit)
            return None                                   # book within the limit can't cover it

        if ltp > 0 and (not limit or (side == 'BUY' and ltp <= limit)
                        or (side == 'SELL' and ltp >= limit)):
            return self._with_slippage(side, float(ltp), limit)
        return None

    def _with_slippage(self, side: str, price: float, limit: Optional[float]) -> float:
        adj = price * (1 + self._slip) if side == 'BUY' else price * (1 - self._slip)
        if limit:                                         # a limit order never fills past its limit
            adj = min(adj, limit) if side == 'BUY' else max(adj, limit)
        return round(adj, 2)

    # ------------------------------------------------------------------
    # Simulated order API
    # ------------------------------------------------------------------

    def place_order(self, symbol: str, transaction_type: str, quantity: int,
                    order_type: str = "LIMIT", product: str = "MIS",
                    price: Optional[float] = None, verify_execution=None) -> Optional[str]:
        """Fill like a limit order would; returns None if it did not fill in time."""
        if quantity <= 0 or transaction_type not in ('BUY', 'SELL'):
            logger.error(f"PaperBroker: rejected {transaction_type} {quantity} {symbol}")
            return None

        limit = price if (price and order_type != 'MARKET') else None
        tries = int(self._fill_wait / self._poll) + 1
        fill = None
        for i in range(tries):
            fill = self._fill_price(symbol, transaction_type, quantity, limit)
            if fill or i == tries - 1:
                break
            self._sleep(self._poll)

        with self._lock:
            self._seq += 1
            order_id = f"PAPER-{datetime.now():%Y%m%d}-{self._seq:04d}"
            if not fill:
                self._orders.append({
                    'order_id': order_id, 'tradingsymbol': symbol,
                    'transaction_type': transaction_type, 'quantity': quantity,
                    'price': limit, 'status': 'CANCELLED',
                    'timestamp': datetime.now().isoformat(),
                })
                logger.warning(
                    f"PaperBroker: {transaction_type} {quantity} {symbol} limit "
                    f"₹{limit} did NOT fill within {self._fill_wait:.0f}s — cancelled [{order_id}]")
                return None

            pos = self._positions.get(symbol, {'quantity': 0, 'average_price': 0.0})
            if transaction_type == 'BUY':
                new_qty = pos['quantity'] + quantity
                pos['average_price'] = (
                    (pos['average_price'] * pos['quantity'] + fill * quantity) / new_qty
                    if new_qty else 0.0
                )
                pos['quantity'] = new_qty
            else:
                pos['quantity'] -= quantity
            if pos['quantity'] == 0:
                self._positions.pop(symbol, None)
            else:
                self._positions[symbol] = pos
            self._fills[order_id] = fill
            self._orders.append({
                'order_id': order_id, 'tradingsymbol': symbol,
                'transaction_type': transaction_type, 'quantity': quantity,
                'price': fill, 'status': 'COMPLETE',
                'timestamp': datetime.now().isoformat(),
            })

        logger.info(f"PaperBroker: {transaction_type} {quantity} {symbol} @ ₹{fill:.2f} "
                    f"(limit ₹{limit}) [{order_id}]")
        return order_id

    def get_fill_price(self, order_id: str) -> Optional[float]:
        """Price actually received for a completed order."""
        with self._lock:
            return self._fills.get(order_id)

    def cancel_order(self, order_id: str, variety: str = "regular") -> bool:
        return True   # paper orders are filled or cancelled before place_order returns

    def get_orders(self) -> List[Dict]:
        with self._lock:
            return list(self._orders)

    def get_positions(self) -> Dict:
        """Same shape as KiteTrader.get_positions()."""
        with self._lock:
            net = [{'tradingsymbol': s, 'quantity': p['quantity'],
                    'average_price': p['average_price']}
                   for s, p in self._positions.items()]
        return {'net': net, 'day': list(net)}

    # ------------------------------------------------------------------
    # Everything else (quotes, candles, profile, credentials) is read-only
    # market access and goes to the real trader.
    # ------------------------------------------------------------------

    def __getattr__(self, name):
        if name == '_trader' or name in _BLOCKED:
            raise AttributeError(name)
        return getattr(self._trader, name)
