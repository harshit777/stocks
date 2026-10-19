"""
FeatureEngine — computes the 20 OHLCV features used by the ML model.

Critical design constraints:
  - SAME code runs offline (training) and online (live inference)
    → zero train/serve skew, the #1 source of silent ML bugs
  - All maths on numpy arrays — no pandas, no object allocation per call
  - Online path keeps a fixed-length deque of raw candles; inference
    reads the last N bars from that deque in <50 µs
  - Feature names are stable constants — model .joblib stores them;
    if you add a feature, bump MODEL_VERSION so old files are rejected

Features (20 total):
    price_pos        price position in today's high/low range (0–1)
    rsi14            RSI(14) of 5m closes
    ema9_21_cross    (EMA9 - EMA21) / close  — trend direction
    macd_hist        MACD histogram normalised by close
    bb_pct           Bollinger %B (0=lower band, 1=upper band)
    atr_pct          ATR(14) / close  — volatility
    vol_ratio        current volume / 20-bar avg volume
    day_range_pct    today's H-L range / day low
    ret1             1-bar return
    ret5             5-bar return
    ret1_abs         abs(ret1)  — recent volatility signal
    high_breakout    close == day high in last 3 bars (binary)
    low_proximity    (close - day_low) / day_low
    candle_body      abs(close - open) / (high - low + 1e-6)
    upper_wick       (high - max(open,close)) / (high - low + 1e-6)
    lower_wick       (min(open,close) - low) / (high - low + 1e-6)
    vol_price_trend  (vol_ratio - 1) * sign(ret1)  — volume-confirmed move
    rsi_ob           rsi14 > 70  (overbought flag)
    rsi_os           rsi14 < 30  (oversold flag)
    dist_to_target   (day_high - close) / close  — remaining upside
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

MODEL_VERSION = 1
FEATURE_NAMES: List[str] = [
    'price_pos', 'rsi14', 'ema9_21_cross', 'macd_hist',
    'bb_pct', 'atr_pct', 'vol_ratio', 'day_range_pct',
    'ret1', 'ret5', 'ret1_abs',
    'high_breakout', 'low_proximity',
    'candle_body', 'upper_wick', 'lower_wick',
    'vol_price_trend', 'rsi_ob', 'rsi_os', 'dist_to_target',
]
N_FEATURES = len(FEATURE_NAMES)   # 20

# Minimum bars of history required before features are valid
MIN_BARS = 30


class FeatureEngine:
    """
    Computes features for one symbol from a rolling candle history.

    Offline usage:
        fe = FeatureEngine()
        X = fe.from_backtester_arrays(arrs)   # shape (n_bars, 20)

    Online usage (live trading, per-tick):
        fe = FeatureEngine()
        fe.update(candle_dict)                 # called every 2-min tick
        vec = fe.latest_vector()               # shape (20,) or None
    """

    def __init__(self, maxlen: int = 200):
        # Rolling deque for online inference
        self._buf: deque = deque(maxlen=maxlen)

    # ------------------------------------------------------------------
    # Online path — called once per candle during live trading
    # ------------------------------------------------------------------

    def update(self, candle: Dict) -> None:
        """Push one new candle into the rolling buffer."""
        self._buf.append({
            'open':     float(candle.get('open', 0)),
            'high':     float(candle.get('high', 0)),
            'low':      float(candle.get('low', 0)),
            'close':    float(candle.get('close', 0)),
            'volume':   float(candle.get('volume', 0)),
            'day_high': float(candle.get('day_high', candle.get('high', 0))),
            'day_low':  float(candle.get('day_low',  candle.get('low', 0))),
        })

    def latest_vector(self) -> Optional[np.ndarray]:
        """
        Return feature vector for the most recent bar, or None if not enough data.
        Shape: (20,) float32.
        """
        if len(self._buf) < MIN_BARS:
            return None
        arrs = self._buf_to_arrays()
        X = self._compute_feature_matrix(arrs)
        return X[-1]   # last row

    def seed(self, candles: List[Dict]) -> None:
        """Bulk-load historical candles into the buffer (at startup)."""
        for c in candles:
            self.update(c)

    # ------------------------------------------------------------------
    # Offline path — called by ModelTrainer from Backtester arrays
    # ------------------------------------------------------------------

    def from_backtester_arrays(self, arrs: Dict[str, np.ndarray]) -> np.ndarray:
        """
        Build full (n_bars, 20) feature matrix from Backtester's pre-computed arrays.
        Valid rows start at index MIN_BARS.

        Returns float32 array shape (n_valid, 20) where n_valid = n - MIN_BARS.
        """
        return self._compute_feature_matrix(arrs)[MIN_BARS:]

    # ------------------------------------------------------------------
    # Core computation — same for both paths
    # ------------------------------------------------------------------

    def _compute_feature_matrix(self, arrs: Dict[str, np.ndarray]) -> np.ndarray:
        """
        Build (n, 20) float32 matrix from indicator arrays.
        All operations are vectorised numpy — no Python loops.
        """
        n      = len(arrs['close'])
        close  = arrs['close'].astype(np.float32)
        high   = arrs['high'].astype(np.float32)
        low    = arrs['low'].astype(np.float32)
        open_  = arrs.get('open', close).astype(np.float32)
        volume = arrs['volume'].astype(np.float32)
        dh     = arrs['dh'].astype(np.float32)
        dl     = arrs['dl'].astype(np.float32)

        eps = np.float32(1e-6)
        safe_close = np.maximum(close, eps)
        candle_range = np.maximum(high - low, eps)

        # ── 1. price_pos ──
        day_range  = np.maximum(dh - dl, eps)
        price_pos  = np.clip((close - dl) / day_range, 0, 1)

        # ── 2. rsi14 ──
        rsi14 = arrs.get('rsi', self._rsi(close, 14))
        rsi14_n = rsi14 / 100.0   # normalise 0–1

        # ── 3. ema9_21_cross ──
        ema9  = arrs.get('ema9',  self._ema(close, 9))
        ema21 = arrs.get('ema21', self._ema(close, 21))
        ema_cross = (ema9 - ema21) / safe_close

        # ── 4. macd_hist (normalised) ──
        macd_hist = arrs.get('macd_hist', np.zeros(n, dtype=np.float32))
        macd_hist_n = macd_hist / safe_close

        # ── 5. bb_pct ──
        bb_pct = np.clip(arrs.get('bb_pct', np.full(n, 0.5, dtype=np.float32)), 0, 1)

        # ── 6. atr_pct ──
        atr_pct = np.clip(arrs.get('atr_pct', np.zeros(n, dtype=np.float32)), 0, 0.1)

        # ── 7. vol_ratio ──
        vol_ratio = np.clip(arrs.get('vol_ratio', np.ones(n, dtype=np.float32)), 0, 10)

        # ── 8. day_range_pct ──
        day_range_pct = np.clip(arrs.get('day_range_pct',
                                         day_range / np.maximum(dl, eps)), 0, 0.2)

        # ── 9. ret1 ──
        ret1 = arrs.get('ret1', np.concatenate([[np.float32(0)],
                         (close[1:] - close[:-1]) / safe_close[:-1]]))
        ret1 = np.clip(ret1, -0.05, 0.05)

        # ── 10. ret5 ──
        ret5 = arrs.get('ret5', np.concatenate([np.zeros(5, dtype=np.float32),
                         (close[5:] - close[:-5]) / np.maximum(close[:-5], eps)]))
        ret5 = np.clip(ret5, -0.10, 0.10)

        # ── 11. ret1_abs ──
        ret1_abs = np.abs(ret1)

        # ── 12. high_breakout — close == day_high in last 3 bars ──
        at_dh = (close >= dh * 0.999).astype(np.float32)
        high_breakout = np.zeros(n, dtype=np.float32)
        for k in range(3):
            high_breakout[k:] += at_dh[:n-k]
        high_breakout = np.clip(high_breakout, 0, 1)

        # ── 13. low_proximity ──
        low_proximity = np.clip((close - dl) / np.maximum(dl, eps), 0, 0.05)

        # ── 14. candle_body ──
        candle_body = np.abs(close - open_) / candle_range

        # ── 15. upper_wick ──
        upper_wick = (high - np.maximum(open_, close)) / candle_range

        # ── 16. lower_wick ──
        lower_wick = (np.minimum(open_, close) - low) / candle_range

        # ── 17. vol_price_trend ──
        vol_price_trend = np.clip((vol_ratio - 1.0) * np.sign(ret1), -5, 5)

        # ── 18. rsi_ob ──
        rsi_ob = (rsi14 > 70).astype(np.float32)

        # ── 19. rsi_os ──
        rsi_os = (rsi14 < 30).astype(np.float32)

        # ── 20. dist_to_target ──
        dist_to_target = np.clip((dh - close) / safe_close, 0, 0.10)

        X = np.column_stack([
            price_pos, rsi14_n, ema_cross, macd_hist_n,
            bb_pct, atr_pct, vol_ratio, day_range_pct,
            ret1, ret5, ret1_abs,
            high_breakout, low_proximity,
            candle_body, upper_wick, lower_wick,
            vol_price_trend, rsi_ob, rsi_os, dist_to_target,
        ]).astype(np.float32)

        assert X.shape[1] == N_FEATURES, f"expected {N_FEATURES} features, got {X.shape[1]}"
        return X

    # ------------------------------------------------------------------
    # Buffer → arrays conversion (online path)
    # ------------------------------------------------------------------

    def _buf_to_arrays(self) -> Dict[str, np.ndarray]:
        """Convert rolling deque to indicator arrays for _compute_feature_matrix."""
        buf = list(self._buf)
        close  = np.array([c['close']    for c in buf], dtype=np.float32)
        high   = np.array([c['high']     for c in buf], dtype=np.float32)
        low    = np.array([c['low']      for c in buf], dtype=np.float32)
        open_  = np.array([c['open']     for c in buf], dtype=np.float32)
        volume = np.array([c['volume']   for c in buf], dtype=np.float32)
        dh     = np.array([c['day_high'] for c in buf], dtype=np.float32)
        dl     = np.array([c['day_low']  for c in buf], dtype=np.float32)

        eps = np.float32(1e-6)
        ema9  = self._ema(close, 9)
        ema21 = self._ema(close, 21)
        ema12 = self._ema(close, 12)
        ema26 = self._ema(close, 26)
        macd  = ema12 - ema26
        macd_sig  = self._ema(macd, 9)
        macd_hist = macd - macd_sig
        bb_mid    = self._sma(close, 20)
        bb_std    = self._rolling_std(close, 20)
        bb_upper  = bb_mid + 2 * bb_std
        bb_lower  = bb_mid - 2 * bb_std
        with np.errstate(divide='ignore', invalid='ignore'):   # np.where evaluates both branches
            bb_pct = np.where(bb_upper - bb_lower > 0,
                              (close - bb_lower) / (bb_upper - bb_lower), np.float32(0.5))
        tr     = self._true_range(high, low, close)
        atr    = self._ema(tr, 14)
        atr_pct = np.where(close > 0, atr / close, np.float32(0))
        vol_avg = self._sma(volume, 20)
        vol_ratio = np.where(vol_avg > 0, volume / vol_avg, np.float32(1))
        day_range = np.maximum(dh - dl, eps)
        day_range_pct = np.where(dl > 0, day_range / dl, np.float32(0))
        ret1 = np.concatenate([[np.float32(0)],
                               (close[1:] - close[:-1]) / np.maximum(close[:-1], eps)])
        ret5 = np.concatenate([np.zeros(5, dtype=np.float32),
                               (close[5:] - close[:-5]) / np.maximum(close[:-5], eps)])
        rsi = self._rsi(close, 14)

        return dict(
            close=close, high=high, low=low, open=open_, volume=volume,
            dh=dh, dl=dl, ema9=ema9, ema21=ema21,
            macd_hist=macd_hist, bb_pct=bb_pct,
            atr_pct=atr_pct, vol_ratio=vol_ratio, day_range_pct=day_range_pct,
            ret1=ret1, ret5=ret5, rsi=rsi,
        )

    # ------------------------------------------------------------------
    # Minimal numpy indicator implementations (same as Backtester)
    # ------------------------------------------------------------------

    @staticmethod
    def _ema(arr: np.ndarray, p: int) -> np.ndarray:
        out = np.empty_like(arr, dtype=np.float32)
        k   = np.float32(2.0 / (p + 1))
        out[0] = arr[0]
        for i in range(1, len(arr)):
            out[i] = arr[i] * k + out[i-1] * (1.0 - k)
        return out

    @staticmethod
    def _sma(arr: np.ndarray, p: int) -> np.ndarray:
        cs  = np.cumsum(np.concatenate([[np.float32(0)], arr]))
        out = np.empty_like(arr, dtype=np.float32)
        out[:p-1] = arr[:p-1]
        out[p-1:] = (cs[p:] - cs[:len(arr)-p+1]) / p
        return out

    @staticmethod
    def _rolling_std(arr: np.ndarray, p: int) -> np.ndarray:
        sma    = FeatureEngine._sma(arr, p)
        sq_sma = FeatureEngine._sma(arr ** 2, p)
        return np.sqrt(np.maximum(sq_sma - sma ** 2, 0))

    @staticmethod
    def _rsi(close: np.ndarray, p: int = 14) -> np.ndarray:
        delta = np.diff(close, prepend=close[0])
        gain  = np.where(delta > 0, delta, np.float32(0))
        loss  = np.where(delta < 0, -delta, np.float32(0))
        avg_g = FeatureEngine._ema(gain, p)
        avg_l = FeatureEngine._ema(loss, p)
        with np.errstate(divide='ignore', invalid='ignore'):
            rs = np.where(avg_l > 0, avg_g / avg_l, np.float32(100))
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        prev_c = np.concatenate([[close[0]], close[:-1]])
        return np.maximum(high - low,
               np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)))
