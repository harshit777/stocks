"""
PaperBroker — simulated order execution on top of a real KiteTrader.

Market data (quotes, candles, profile) is delegated to the wrapped trader.
Anything that could place, modify or cancel a REAL order is handled here
and never reaches Zerodha. The raw Kite client and the OrderManager are not
reachable through this object at all.
"""
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Attributes that could be used to bypass the simulation and hit the real broker.
_BLOCKED = frozenset({'kite', 'order_manager'})


class PaperBroker:
    trading_mode = 'paper'

    def __init__(self, trader):
        self._trader = trader
        self._lock = threading.Lock()
        self._positions: Dict[str, Dict] = {}   # symbol -> {quantity, average_price}
        self._orders: List[Dict] = []
        self._seq = 0

    # ------------------------------------------------------------------
    # Simulated order API
    # ------------------------------------------------------------------

    def place_order(self, symbol: str, transaction_type: str, quantity: int,
                    order_type: str = "LIMIT", product: str = "MIS",
                    price: Optional[float] = None, verify_execution=None) -> Optional[str]:
        """Fill instantly at the given limit price (or LTP if none)."""
        if quantity <= 0 or transaction_type not in ('BUY', 'SELL'):
            logger.error(f"PaperBroker: rejected {transaction_type} {quantity} {symbol}")
            return None

        fill = price
        if not fill:
            ltp = self._trader.get_ltp([symbol]).get(f"NSE:{symbol}", 0)
            fill = ltp if ltp > 0 else None
        if not fill:
            logger.error(f"PaperBroker: no price available for {symbol}")
            return None

        with self._lock:
            self._seq += 1
            order_id = f"PAPER-{datetime.now():%Y%m%d}-{self._seq:04d}"
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
            self._orders.append({
                'order_id': order_id, 'tradingsymbol': symbol,
                'transaction_type': transaction_type, 'quantity': quantity,
                'price': fill, 'status': 'COMPLETE',
                'timestamp': datetime.now().isoformat(),
            })

        logger.info(f"PaperBroker: {transaction_type} {quantity} {symbol} @ ₹{fill:.2f} [{order_id}]")
        return order_id

    def cancel_order(self, order_id: str, variety: str = "regular") -> bool:
        return True   # paper orders fill instantly; nothing to cancel

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
