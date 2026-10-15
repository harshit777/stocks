"""
Backtester — vectorised replay of IntradayHighLowStrategy on historical 5m data.

Design decisions for millisecond-grade trading:
  - All indicator maths done on numpy arrays, not per-row Python
  - Real costs via CostCalculator on every round-trip
  - Walk-forward split: never look ahead (no future data leaks)
  - Produces TradeRecord list used by ModelTrainer as labelled dataset
  - Parameter sweep via grid search so you find the best thresholds
    before touching live capital

Usage:
    bt = Backtester(candles_5m, symbol='SBIN')
    report = bt.run()
    print(report.summary())
    # or sweep params
    best = Backtester.parameter_sweep(candles_5m, 'SBIN')
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from itertools import product
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..utils.cost_calculator import get_cost_calculator

logger = logging.getLogger(__name__)


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class Candle:
    """Single OHLCV candle (5-minute)."""
    ts: datetime        # candle open timestamp
    open: float
    high: float
    low: float
    close: float
    volume: int
    # derived — filled by Backtester._compute_arrays
    day_high: float = 0.0
    day_low:  float = 0.0

@dataclass
class TradeRecord:
    """One complete round-trip trade — becomes one ML training sample."""
    symbol:       str
    entry_ts:     datetime
    exit_ts:      datetime
    entry_price:  float
    exit_price:   float
    quantity:     int
    gross_pnl:    float
    net_pnl:      float          # after costs
    costs:        float
    exit_reason:  str            # 'target'|'stop_loss'|'eod'|'time_stop'
    # features at entry — used directly as ML training row
    features:     Dict[str, float] = field(default_factory=dict)
    label:        int = 0        # 1 = profitable, 0 = loss

@dataclass
class BacktestReport:
    symbol:           str
    params:           Dict
    total_trades:     int
    wins:             int
    losses:           int
    win_rate:         float
    gross_pnl:        float
    net_pnl:          float
    total_costs:      float
    avg_win:          float
    avg_loss:         float
    profit_factor:    float
    max_drawdown:     float
    sharpe:           float
    expectancy:       float      # avg net P&L per trade
    trades:           List[TradeRecord] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"[{self.symbol}] trades={self.total_trades} "
            f"win={self.win_rate:.1%} net_pnl=₹{self.net_pnl:+.2f} "
            f"expectancy=₹{self.expectancy:+.2f} "
            f"max_dd=₹{self.max_drawdown:.2f} sharpe={self.sharpe:.2f} "
            f"params={self.params}"
        )

    def to_dict(self) -> Dict:
        d = asdict(self)
        # Convert datetime objects for JSON serialisation
        for t in d['trades']:
            t['entry_ts'] = t['entry_ts'].isoformat() if isinstance(t['entry_ts'], datetime) else t['entry_ts']
            t['exit_ts']  = t['exit_ts'].isoformat()  if isinstance(t['exit_ts'],  datetime) else t['exit_ts']
        return d


# ── Core Backtester ────────────────────────────────────────────────────────────

class Backtester:
    """
    Replays IntradayHighLowStrategy logic on historical 5-minute candles.

    All indicator computation is vectorised over the full candle array.
    The per-candle loop only applies entry/exit logic — O(n) but lean.
    """

    # Default parameters — mirror live_trade_v2.py settings
    DEFAULT_PARAMS = dict(
        buy_threshold=0.20,
        sell_threshold=0.80,
        stop_loss_pct=0.015,
        target_pct=0.025,
        trailing_stop_activation=0.010,
        trailing_stop_distance=0.008,
        max_hold_candles=45,      # 45 × 5min = 225 min = 3h45m
        min_profit_margin=0.020,
        risk_reward_min=3.0,
        max_position_pct=0.15,
        capital=10_000.0,         # virtual capital for sizing
    )

    def __init__(
        self,
        candles: List[Dict],      # list of dicts from kite.historical_data()
        symbol:  str,
        params:  Optional[Dict] = None,
    ):
        self.symbol = symbol
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}
        self.cost_calc = get_cost_calculator()

        # Convert kite dicts → Candle objects, annotate day high/low
        self._candles: List[Candle] = self._parse_candles(candles)
        # Pre-compute all indicator arrays (vectorised)
        self._arrs: Dict[str, np.ndarray] = self._compute_arrays()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> BacktestReport:
        """Run one backtest with self.params. Returns BacktestReport."""
        trades = self._simulate()
        return self._build_report(trades)

    @staticmethod
    def parameter_sweep(
        candles: List[Dict],
        symbol: str,
        grid: Optional[Dict] = None,
    ) -> Tuple[BacktestReport, List[BacktestReport]]:
        """
        Grid-search over parameter combinations.
        Returns (best_report, all_reports) sorted by net_pnl descending.

        Walk-forward safe: uses only first 70% of candles for sweep,
        then validates best params on remaining 30%.
        """
        if grid is None:
            grid = dict(
                buy_threshold =[0.15, 0.20, 0.25],
                sell_threshold=[0.75, 0.80, 0.85],
                stop_loss_pct =[0.010, 0.015, 0.020],
                target_pct    =[0.020, 0.025, 0.030],
            )

        # Split: 70% in-sample / 30% out-of-sample
        split = int(len(candles) * 0.70)
        train_candles = candles[:split]
        test_candles  = candles[split:]

        keys  = list(grid.keys())
        vals  = list(grid.values())
        all_reports: List[BacktestReport] = []

        for combo in product(*vals):
            params = dict(zip(keys, combo))
            bt = Backtester(train_candles, symbol, params)
            rpt = bt.run()
            if rpt.total_trades >= 5:   # skip param sets with too few trades
                all_reports.append(rpt)

        if not all_reports:
            # Fallback: run with defaults on full dataset
            bt = Backtester(candles, symbol)
            return bt.run(), []

        all_reports.sort(key=lambda r: r.net_pnl, reverse=True)
        best_params = all_reports[0].params

        # Out-of-sample validation
        bt_oos = Backtester(test_candles, symbol, best_params)
        oos_report = bt_oos.run()
        logger.info(
            f"Sweep [{symbol}]: best in-sample {all_reports[0].summary()}\n"
            f"  OOS validation: {oos_report.summary()}"
        )
        return oos_report, all_reports

    # ------------------------------------------------------------------
    # Parse & vectorise
    # ------------------------------------------------------------------

    def _parse_candles(self, raw: List[Dict]) -> List[Candle]:
        """Convert Kite API dicts → Candle objects, annotate day high/low."""
        candles = []
        for r in raw:
            ts = r.get('date') or r.get('timestamp')
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            candles.append(Candle(
                ts=ts, open=float(r['open']), high=float(r['high']),
                low=float(r['low']), close=float(r['close']),
                volume=int(r.get('volume', 0)),
            ))

        # Annotate each candle with the running day high/low
        # (what the strategy actually sees at that point in time)
        day_h = day_l = None
        prev_date = None
        for c in candles:
            d = c.ts.date()
            if d != prev_date:
                day_h = c.high
                day_l = c.low
                prev_date = d
            else:
                day_h = max(day_h, c.high)
                day_l = min(day_l, c.low)
            c.day_high = day_h
            c.day_low  = day_l

        return candles

    def _compute_arrays(self) -> Dict[str, np.ndarray]:
        """
        Compute ALL indicator arrays over the full candle set — one pass.
        Every array is float32 (half memory, same precision for trading).
        """
        n = len(self._candles)
        close  = np.array([c.close  for c in self._candles], dtype=np.float32)
        high   = np.array([c.high   for c in self._candles], dtype=np.float32)
        low    = np.array([c.low    for c in self._candles], dtype=np.float32)
        volume = np.array([c.volume for c in self._candles], dtype=np.float32)
        dh     = np.array([c.day_high for c in self._candles], dtype=np.float32)
        dl     = np.array([c.day_low  for c in self._candles], dtype=np.float32)

        # Price position in day range (0=at low, 1=at high) — core strategy signal
        day_range  = np.where(dh - dl > 0, dh - dl, np.float32(1e-6))
        price_pos  = np.clip((close - dl) / day_range, 0, 1)

        # RSI(14) — vectorised
        rsi = self._vec_rsi(close, 14)

        # EMA fast/slow
        ema9  = self._vec_ema(close, 9)
        ema21 = self._vec_ema(close, 21)

        # MACD line = EMA12 - EMA26, signal = EMA9 of macd
        ema12 = self._vec_ema(close, 12)
        ema26 = self._vec_ema(close, 26)
        macd  = ema12 - ema26
        macd_sig = self._vec_ema(macd, 9)
        macd_hist = macd - macd_sig

        # Bollinger Bands (20, 2σ)
        bb_mid   = self._vec_sma(close, 20)
        bb_std   = self._vec_rolling_std(close, 20)
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_pct   = np.where(bb_upper - bb_lower > 0,
                            (close - bb_lower) / (bb_upper - bb_lower), np.float32(0.5))

        # ATR(14) — volatility
        tr    = self._vec_atr(high, low, close, 14)
        atr_pct = np.where(close > 0, tr / close, np.float32(0))

        # Volume ratio (current vol / 20-bar avg vol)
        vol_avg  = self._vec_sma(volume, 20)
        vol_ratio = np.where(vol_avg > 0, volume / vol_avg, np.float32(1))

        # Day range % (how wide is today's range)
        day_range_pct = np.where(dl > 0, day_range / dl, np.float32(0))

        # Returns (1-bar, 5-bar)
        ret1 = np.concatenate([[np.float32(0)],
                                (close[1:] - close[:-1]) / np.maximum(close[:-1], 1e-6)])
        ret5 = np.concatenate([np.zeros(5, dtype=np.float32),
                                (close[5:] - close[:-5]) / np.maximum(close[:-5], 1e-6)])

        return dict(
            close=close, high=high, low=low, volume=volume,
            dh=dh, dl=dl, price_pos=price_pos,
            rsi=rsi, ema9=ema9, ema21=ema21,
            macd=macd, macd_sig=macd_sig, macd_hist=macd_hist,
            bb_pct=bb_pct, bb_mid=bb_mid,
            atr_pct=atr_pct, vol_ratio=vol_ratio,
            day_range_pct=day_range_pct, ret1=ret1, ret5=ret5,
        )

    # ------------------------------------------------------------------
    # Simulation loop
    # ------------------------------------------------------------------

    def _simulate(self) -> List[TradeRecord]:
        p          = self.params
        candles    = self._candles
        arrs       = self._arrs
        n          = len(candles)
        trades: List[TradeRecord] = []

        # position state
        in_position  = False
        entry_idx    = 0
        entry_price  = 0.0
        stop_price   = 0.0
        target_price = 0.0
        quantity     = 0
        peak_price   = 0.0

        for i in range(30, n):   # need 30 bars of warmup for indicators
            c   = candles[i]
            pos = float(arrs['price_pos'][i])

            # ── intraday boundary ──
            cur_date  = c.ts.date()
            day_close = (c.ts.hour == 15 and c.ts.minute >= 20)

            if in_position:
                ltp = c.close

                # Update trailing stop
                if ltp > peak_price:
                    peak_price = ltp
                if ltp >= entry_price * (1 + p['trailing_stop_activation']):
                    new_stop = peak_price * (1 - p['trailing_stop_distance'])
                    stop_price = max(stop_price, new_stop)

                # Exit checks (priority order)
                reason = None
                exit_price = ltp

                if ltp <= stop_price:
                    reason = 'stop_loss'
                elif ltp >= target_price:
                    reason = 'target'
                elif (i - entry_idx) >= p['max_hold_candles']:
                    reason = 'time_stop'
                elif day_close:
                    reason = 'eod'
                elif pos >= p['sell_threshold']:
                    reason = 'sell_signal'

                if reason:
                    gross = (exit_price - entry_price) * quantity
                    cost  = self._cost(entry_price, exit_price, quantity)
                    net   = gross - cost
                    features = self._extract_features(entry_idx)
                    trades.append(TradeRecord(
                        symbol=self.symbol,
                        entry_ts=candles[entry_idx].ts,
                        exit_ts=c.ts,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        quantity=quantity,
                        gross_pnl=round(gross, 4),
                        net_pnl=round(net, 4),
                        costs=round(cost, 4),
                        exit_reason=reason,
                        features=features,
                        label=1 if net > 0 else 0,
                    ))
                    in_position = False

            # ── entry ──
            if not in_position and not day_close:
                if pos <= p['buy_threshold']:
                    dh = float(arrs['dh'][i])
                    dl = float(arrs['dl'][i])
                    if dh > 0 and dl > 0:
                        potential_profit = dh - c.close
                        potential_loss   = c.close * p['stop_loss_pct']
                        rr = potential_profit / potential_loss if potential_loss > 0 else 0

                        profit_margin = potential_profit / c.close if c.close > 0 else 0

                        if (rr >= p['risk_reward_min'] and
                                profit_margin >= p['min_profit_margin']):
                            quantity    = max(1, int(p['capital'] * p['max_position_pct'] / c.close))
                            entry_price = c.close
                            stop_price  = entry_price * (1 - p['stop_loss_pct'])
                            target_price= dh
                            peak_price  = entry_price
                            entry_idx   = i
                            in_position = True

        # Force-close any open position at end of dataset
        if in_position and len(candles) > entry_idx:
            ltp  = candles[-1].close
            gross = (ltp - entry_price) * quantity
            cost  = self._cost(entry_price, ltp, quantity)
            net   = gross - cost
            features = self._extract_features(entry_idx)
            trades.append(TradeRecord(
                symbol=self.symbol,
                entry_ts=candles[entry_idx].ts, exit_ts=candles[-1].ts,
                entry_price=entry_price, exit_price=ltp, quantity=quantity,
                gross_pnl=round(gross, 4), net_pnl=round(net, 4),
                costs=round(cost, 4), exit_reason='dataset_end',
                features=features, label=1 if net > 0 else 0,
            ))

        return trades

    def _extract_features(self, idx: int) -> Dict[str, float]:
        """Return all indicator values at bar idx as a flat dict."""
        a = self._arrs
        return {k: float(a[k][idx]) for k in a}

    def _cost(self, buy_price: float, sell_price: float, qty: int) -> float:
        rt = self.cost_calc.calculate_round_trip_cost(buy_price, sell_price, qty, 'MIS')
        return float(rt['total_costs'])

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _build_report(self, trades: List[TradeRecord]) -> BacktestReport:
        if not trades:
            return BacktestReport(
                symbol=self.symbol, params=self.params,
                total_trades=0, wins=0, losses=0, win_rate=0,
                gross_pnl=0, net_pnl=0, total_costs=0,
                avg_win=0, avg_loss=0, profit_factor=0,
                max_drawdown=0, sharpe=0, expectancy=0, trades=[],
            )

        net_pnls  = np.array([t.net_pnl  for t in trades], dtype=np.float64)
        wins      = net_pnls[net_pnls > 0]
        losses    = net_pnls[net_pnls <= 0]

        # Drawdown — peak-to-trough on cumulative P&L
        cum  = np.cumsum(net_pnls)
        peak = np.maximum.accumulate(cum)
        dd   = peak - cum
        max_dd = float(dd.max()) if len(dd) > 0 else 0.0

        # Sharpe — annualised using 252 trading days × ~75 5m bars
        pnl_std = float(net_pnls.std()) if len(net_pnls) > 1 else 1e-9
        sharpe  = (float(net_pnls.mean()) / pnl_std) * np.sqrt(252 * 75) if pnl_std > 0 else 0

        gross_sum = float(sum(t.gross_pnl for t in trades))
        total_c   = float(sum(t.costs     for t in trades))

        pf = float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float('inf')

        return BacktestReport(
            symbol=self.symbol, params=self.params,
            total_trades=len(trades),
            wins=int(len(wins)), losses=int(len(losses)),
            win_rate=len(wins) / len(trades),
            gross_pnl=round(gross_sum, 2),
            net_pnl=round(float(net_pnls.sum()), 2),
            total_costs=round(total_c, 2),
            avg_win=round(float(wins.mean()), 2) if len(wins) > 0 else 0,
            avg_loss=round(float(losses.mean()), 2) if len(losses) > 0 else 0,
            profit_factor=round(pf, 3),
            max_drawdown=round(max_dd, 2),
            sharpe=round(sharpe, 3),
            expectancy=round(float(net_pnls.mean()), 4),
            trades=trades,
        )

    # ------------------------------------------------------------------
    # Vectorised indicator helpers — pure numpy, no pandas
    # ------------------------------------------------------------------

    @staticmethod
    def _vec_ema(arr: np.ndarray, period: int) -> np.ndarray:
        """EMA via single-pass loop (unavoidable). O(n), minimal allocations."""
        out = np.empty_like(arr)
        k   = 2.0 / (period + 1)
        out[0] = arr[0]
        for i in range(1, len(arr)):
            out[i] = arr[i] * k + out[i - 1] * (1.0 - k)
        return out

    @staticmethod
    def _vec_sma(arr: np.ndarray, period: int) -> np.ndarray:
        """Simple moving average via cumsum trick — O(n), one allocation."""
        cs  = np.cumsum(np.concatenate([[0.0], arr]))
        out = np.empty_like(arr)
        out[:period - 1] = arr[:period - 1]   # warmup
        out[period - 1:] = (cs[period:] - cs[:len(arr) - period + 1]) / period
        return out

    @staticmethod
    def _vec_rolling_std(arr: np.ndarray, period: int) -> np.ndarray:
        """Rolling std via two-pass SMA trick."""
        sma    = Backtester._vec_sma(arr, period)
        sq_sma = Backtester._vec_sma(arr ** 2, period)
        var    = np.maximum(sq_sma - sma ** 2, 0)
        return np.sqrt(var)

    @staticmethod
    def _vec_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
        """RSI via Wilder's smoothing — fully vectorised over gains/losses."""
        delta = np.diff(close, prepend=close[0])
        gain  = np.where(delta > 0, delta, 0.0).astype(np.float32)
        loss  = np.where(delta < 0, -delta, 0.0).astype(np.float32)
        avg_g = Backtester._vec_ema(gain, period)
        avg_l = Backtester._vec_ema(loss, period)
        rs    = np.where(avg_l > 0, avg_g / avg_l, np.float32(100))
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _vec_atr(high: np.ndarray, low: np.ndarray,
                 close: np.ndarray, period: int = 14) -> np.ndarray:
        """Average True Range."""
        prev_c = np.concatenate([[close[0]], close[:-1]])
        tr = np.maximum(high - low,
             np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)))
        return Backtester._vec_ema(tr, period)
