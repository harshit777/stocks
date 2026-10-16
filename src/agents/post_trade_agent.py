"""
Agent 6: PostTradeAgent

Responsibility: End-of-day accounting, capital recovery, and AI learning.

Does three jobs:
  1. Intraday: callback on every fill → update P&L log, feed trade outcome
               back into SignalEngine for psychology guard
  2. End of day: record results in CapitalRecoveryManager, save AI models,
                 print summary
  3. Learning: store trade outcomes so future sessions improve signal weighting
               (groundwork — actual sklearn training is a future upgrade)

All of this was scattered across live_trade.py, capital_manager.py, and
AIIntradayStrategy._save_ai_models(). Centralised here.
"""
import json
import logging
import os
from datetime import datetime, date
from typing import Dict, List, Optional

from ..utils.capital_manager import CapitalRecoveryManager


class PostTradeAgent:
    """
    Handles all post-fill and end-of-day bookkeeping.
    """

    def __init__(
        self,
        capital_manager: CapitalRecoveryManager,
        signal_engine,          # SignalEngine — circular import avoided via duck typing
        data_dir: str = 'data',
    ):
        self.capital_manager = capital_manager
        self.signal_engine = signal_engine
        self.data_dir = data_dir
        self.logger = logging.getLogger(__name__)

        os.makedirs(data_dir, exist_ok=True)

        # Intraday P&L accumulator
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.daily_wins: int = 0
        self.daily_losses: int = 0
        self.trade_log: List[Dict] = []
        self.peak_capital: float = 0.0
        self.max_drawdown: float = 0.0
        self._starting_capital: float = 0.0

    # ------------------------------------------------------------------
    # Called at market open
    # ------------------------------------------------------------------

    def start_day(self, starting_capital: float):
        """Reset intraday accumulators."""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.trade_log.clear()
        self._starting_capital = starting_capital
        self.peak_capital = starting_capital
        self.max_drawdown = 0.0
        self.logger.info(f"PostTradeAgent: new day — starting capital ₹{starting_capital:,.2f}")

    # ------------------------------------------------------------------
    # Called after every confirmed fill (registered as ExecutionAgent callback)
    # ------------------------------------------------------------------

    def on_fill(self, symbol: str, transaction_type: str,
                quantity: int, fill_price: float, pnl: Optional[float]):
        """
        ExecutionAgent callback — fires after every confirmed order fill.
        """
        record = {
            'timestamp':        datetime.now().isoformat(),
            'symbol':           symbol,
            'transaction_type': transaction_type,
            'quantity':         quantity,
            'fill_price':       fill_price,
            'pnl':              pnl,
        }
        self.trade_log.append(record)

        if transaction_type == 'BUY':
            # Snapshot the indicators at entry so the online model learns from them
            try:
                self.signal_engine.record_entry(symbol, fill_price)
            except Exception as e:
                self.logger.debug(f"PostTradeAgent: record_entry error: {e}")

        if transaction_type == 'SELL' and pnl is not None:
            self.daily_pnl += pnl
            self.daily_trades += 1

            if pnl > 0:
                self.daily_wins += 1
                self.logger.info(f"PostTradeAgent: WIN ₹{pnl:+.2f} on {symbol}")
            else:
                self.daily_losses += 1
                self.logger.warning(f"PostTradeAgent: LOSS ₹{pnl:+.2f} on {symbol}")

            # Feed outcome back into SignalEngine psychology guard
            try:
                self.signal_engine.record_trade_outcome(
                    symbol=symbol,
                    signal='SELL',
                    entry_price=fill_price,
                    quantity=quantity,
                    pnl=pnl,
                )
            except Exception as e:
                self.logger.debug(f"PostTradeAgent: psychology callback error: {e}")

            # Update max drawdown
            current_capital = self._starting_capital + self.daily_pnl
            if current_capital > self.peak_capital:
                self.peak_capital = current_capital
            drawdown = self.peak_capital - current_capital
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown

        self._save_trade_log()

    # ------------------------------------------------------------------
    # Called at market close (3:30 PM or after square-off)
    # ------------------------------------------------------------------

    def end_day(self, used_capital: float = 0.0):
        """
        Record end-of-day results and persist everything.

        Args:
            used_capital: Peak capital deployed today (for utilisation stats)
        """
        today = date.today().isoformat()
        win_rate = (self.daily_wins / self.daily_trades * 100) if self.daily_trades > 0 else 0

        self.logger.info("=" * 70)
        self.logger.info("📊 END OF DAY SUMMARY")
        self.logger.info("=" * 70)
        self.logger.info(f"Date:            {today}")
        self.logger.info(f"Starting Capital: ₹{self._starting_capital:,.2f}")
        self.logger.info(f"Daily P&L:        ₹{self.daily_pnl:+,.2f}")
        self.logger.info(f"Trades:           {self.daily_trades} "
                         f"({self.daily_wins}W / {self.daily_losses}L)")
        self.logger.info(f"Win Rate:         {win_rate:.1f}%")
        self.logger.info(f"Max Drawdown:     ₹{self.max_drawdown:.2f}")
        self.logger.info("=" * 70)

        # Capital moves by what we'd actually keep: P&L minus brokerage, STT and other charges
        costs = 0.0
        try:
            from ..utils.paper_report import round_trips
            costs = sum(t['costs'] for t in round_trips(self.trade_log))
        except Exception as e:
            self.logger.warning(f"PostTradeAgent: cost calculation failed, using gross P&L: {e}")
        net_pnl = self.daily_pnl - costs
        self.logger.info(f"Charges:          ₹{costs:.2f} → net P&L ₹{net_pnl:+,.2f}")

        # Record in capital recovery manager
        self.capital_manager.record_day_end(
            daily_pnl=net_pnl,
            trades_count=self.daily_trades,
            used_capital=used_capital,
        )

        # Tomorrow's capital
        perf = self.capital_manager.get_performance_summary()
        self.logger.info(f"Tomorrow's capital: ₹{perf['current_capital']:,.2f}")
        self.logger.info(f"All-time win rate:  {perf['win_rate']:.1f}%")
        self.logger.info(f"Total P&L:          ₹{perf['total_pnl']:+,.2f}")

        # Persist AI models
        try:
            self.signal_engine.save_models()
            self.logger.info("PostTradeAgent: AI models saved")
        except Exception as e:
            self.logger.error(f"PostTradeAgent: model save failed: {e}")

    # ------------------------------------------------------------------
    # Intraday status
    # ------------------------------------------------------------------

    def intraday_status(self) -> Dict:
        """Return current session stats for logging."""
        return {
            'daily_pnl':     self.daily_pnl,
            'daily_trades':  self.daily_trades,
            'daily_wins':    self.daily_wins,
            'daily_losses':  self.daily_losses,
            'max_drawdown':  self.max_drawdown,
            'win_rate':      (self.daily_wins / self.daily_trades * 100)
                             if self.daily_trades > 0 else 0,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_trade_log(self):
        path = os.path.join(self.data_dir, f"trades_{date.today().isoformat()}.json")
        try:
            with open(path, 'w') as f:
                json.dump(self.trade_log, f, indent=2)
        except Exception as e:
            self.logger.error(f"PostTradeAgent: trade log save failed: {e}")
