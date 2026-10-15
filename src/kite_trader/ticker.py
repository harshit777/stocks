"""
KiteTicker WebSocket wrapper — real-time stop monitoring.

Subscribes to open position tickers and fires PositionMonitor._check_exit()
on every tick. Reduces stop-loss slippage from "up to 2 min late" to < 1 sec.

Usage (wired by live_trade_v2.py / app.py _startup):
    ticker = PositionTicker(trader, position_monitor, execution_agent)
    ticker.start()          # starts WebSocket thread
    ticker.update_symbols(['SBIN', 'TCS'])  # call when watchlist changes
    ticker.stop()           # called at EOD

Design:
  - One WebSocket thread (kiteconnect.KiteTicker)
  - on_ticks: for each tick, if symbol is an open position → check exit
  - on_connect: subscribes to current open positions
  - update_symbols: re-subscribes after new positions are opened
  - Non-fatal: if WebSocket fails, the 2-min polling loop still runs
  - ponytail: full/quote mode costs more API quota — using LTP mode only
               upgrade to QUOTE if bid/ask depth is needed later
"""
import logging
import threading
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class PositionTicker:
    """
    Thin wrapper around kiteconnect.KiteTicker that drives
    real-time stop monitoring for open positions.

    Thread lifecycle:
        start()  →  WebSocket thread runs, reconnects automatically
        stop()   →  closes WebSocket; blocks until thread exits (timeout=5s)
    """

    def __init__(self, trader, position_monitor, execution_agent):
        """
        Args:
            trader:           KiteTrader (must have .api_key and .access_token)
            position_monitor: PositionMonitor — _check_exit called per tick
            execution_agent:  ExecutionAgent — all_positions() for subscribe list
        """
        self.trader           = trader
        self.pos_monitor      = position_monitor
        self.execution        = execution_agent
        self._kws             = None
        self._thread: Optional[threading.Thread] = None
        self._subscribed: Set[int] = set()
        self._token_map: dict = {}   # instrument_token → symbol
        self._running = False

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def start(self):
        """Start the WebSocket thread. Non-blocking."""
        if self._running:
            return
        try:
            from kiteconnect import KiteTicker
        except ImportError:
            logger.warning("kiteconnect not available — WebSocket disabled, falling back to polling")
            return

        if not self.trader.api_key or not self.trader.access_token:
            logger.warning("Missing API credentials — WebSocket disabled")
            return

        self._kws = KiteTicker(self.trader.api_key, self.trader.access_token)
        self._kws.on_ticks   = self._on_ticks
        self._kws.on_connect = self._on_connect
        self._kws.on_close   = self._on_close
        self._kws.on_error   = self._on_error
        self._running = True
        self._thread = threading.Thread(
            target=self._kws.connect,
            kwargs={'threaded': True},
            daemon=True,
            name='KiteTicker',
        )
        self._thread.start()
        logger.info("PositionTicker: WebSocket started")

    def stop(self):
        """Stop the WebSocket gracefully."""
        self._running = False
        if self._kws:
            try:
                self._kws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("PositionTicker: stopped")

    def update_symbols(self, symbols: List[str]):
        """
        Re-subscribe to a new set of symbols.
        Call after new positions are opened or closed.
        """
        if not self._kws or not self._running:
            return
        tokens = []
        for sym in symbols:
            token = self.trader._get_instrument_token(sym)
            if token:
                tokens.append(token)
                self._token_map[token] = sym
        if tokens:
            self._kws.subscribe(tokens)
            self._kws.set_mode(self._kws.MODE_LTP, tokens)
            self._subscribed = set(tokens)
            logger.debug(f"PositionTicker: subscribed {len(tokens)} symbols")

    # ------------------------------------------------------------------
    # KiteTicker callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, ws, response):
        """Subscribe to all currently open position symbols on connect."""
        open_positions = self.execution.all_positions()
        if open_positions:
            self.update_symbols(list(open_positions.keys()))

    def _on_ticks(self, ws, ticks):
        """
        Called on every price tick for subscribed instruments.
        Fires stop/target check on open positions only.
        """
        if not self._running:
            return
        open_positions = self.execution.all_positions()
        if not open_positions:
            return

        for tick in ticks:
            token  = tick.get('instrument_token')
            symbol = self._token_map.get(token)
            if not symbol or symbol not in open_positions:
                continue

            ltp = tick.get('last_price', 0)
            if ltp <= 0:
                continue

            pos = open_positions[symbol]
            reason = self.pos_monitor._check_exit(symbol, pos, ltp, signal_override=None)
            if reason:
                logger.info(f"PositionTicker: EXIT trigger {symbol} @ ₹{ltp:.2f} — {reason}")
                self.pos_monitor._exit(symbol, pos, ltp, reason)
                # Unsubscribe closed position
                if token in self._subscribed:
                    try:
                        ws.unsubscribe([token])
                        self._subscribed.discard(token)
                    except Exception:
                        pass

    def _on_close(self, ws, code, reason):
        logger.warning(f"PositionTicker: WebSocket closed ({code}: {reason})")

    def _on_error(self, ws, code, reason):
        logger.error(f"PositionTicker: WebSocket error ({code}: {reason})")
