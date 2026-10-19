"""
PredictionLedger — holds the ML model to account.

Every few passes the model's prediction for a symbol is written down. Later the
market answers (same exit rules as a real trade: +target, -stop, or a timeout
judged net of costs). Each answered prediction does two things:

  1. It is returned to the caller so the online model can learn from it
     (far more feedback than the 1-2 real trades a day).
  2. It goes on a rolling scoreboard that compares the model with the dumbest
     possible forecaster ("always say the base rate"). A model that cannot beat
     that over enough predictions is BENCHED: SignalEngine drops its vote. It
     keeps predicting in the background and returns once it beats the baseline.
"""
from __future__ import annotations

import json
import logging
import os
from collections import deque
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

LEDGER_PATH = os.path.join('data/ml', 'prediction_ledger.json')
_MAX_WEIGHT = 5.0


def reward_weight(prob: Optional[float], label: int, traded: bool = False) -> float:
    """
    How hard one outcome should push the model.
    A confident wrong call is punished harder than a mild one, a confident right call
    is rewarded, and a real trade counts double a shadow prediction. Bounded so one
    sample can never dominate.
    """
    w = 1.0 if prob is None else 1.0 + 2.0 * abs(label - float(prob))
    if traded:
        w *= 2.0
    return min(w, _MAX_WEIGHT)


class PredictionLedger:
    def __init__(self, path: str = LEDGER_PATH, target_pct: float = 0.025,
                 stop_pct: float = 0.015, horizon: int = 30, sample_every: int = 5,
                 window: int = 300, min_judge: int = 100, gate: float = 0.55):
        self.path = path
        self.target_pct = target_pct
        self.stop_pct = stop_pct
        self.horizon = horizon            # passes before an unresolved prediction times out
        self.sample_every = sample_every  # record one prediction per symbol every N passes
        self.window = window
        self.min_judge = min_judge        # answered predictions needed before judging
        self.gate = gate                  # probability the live signal treats as "confident"
        self._pending: Dict[str, List[dict]] = {}
        self._passes: Dict[str, int] = {}
        self._done: deque = deque(maxlen=window)    # (prob, label)
        self.total = 0
        self.benched = False
        self._load()
        self._refresh()

    # ------------------------------------------------------------------ #

    def observe(self, symbol: str, price: float, vec: Optional[np.ndarray],
                prob: Optional[float]) -> List[dict]:
        """
        Call once per symbol per pass with the current price and the model's output.
        Returns predictions that were answered on this pass:
            [{'vec', 'prob', 'label'}]
        """
        n = self._passes[symbol] = self._passes.get(symbol, 0) + 1
        answered, keep = [], []
        for p in self._pending.get(symbol, []):
            p['age'] += 1
            label = self._label(p, price)
            if label is None:
                keep.append(p)
                continue
            answered.append({'vec': p['vec'], 'prob': p['prob'], 'label': label})
            self._done.append((p['prob'], label))
            self.total += 1
        if vec is not None and prob is not None and price > 0 and n % self.sample_every == 0:
            keep.append({'vec': vec.copy(), 'prob': float(prob), 'price': float(price), 'age': 0})
        self._pending[symbol] = keep
        if answered:
            self._refresh()
        return answered

    def _label(self, p: dict, price: float) -> Optional[int]:
        ret = price / p['price'] - 1.0
        if ret >= self.target_pct:
            return 1
        if ret <= -self.stop_pct:
            return 0
        if p['age'] >= self.horizon:
            return 1 if ret - self._round_trip_cost_pct(p['price']) > 0 else 0
        return None

    @staticmethod
    def _round_trip_cost_pct(price: float) -> float:
        from ..utils.cost_calculator import get_cost_calculator
        qty = max(1, int(10_000 / price))
        c = get_cost_calculator().calculate_round_trip_cost(price, price, qty)
        return c['total_costs'] / (price * qty)

    # ------------------------------------------------------------------ #

    def summary(self) -> Dict:
        n = len(self._done)
        out = {'answered': self.total, 'window': n, 'min_judge': self.min_judge,
               'benched': self.benched, 'brier': None, 'baseline_brier': None,
               'skill': None, 'hit_rate': None, 'base_rate': None,
               'confident_n': 0, 'confident_win_rate': None}
        if n == 0:
            return out
        probs = np.array([d[0] for d in self._done], dtype=float)
        labels = np.array([d[1] for d in self._done], dtype=float)
        base = float(labels.mean())
        brier = float(np.mean((probs - labels) ** 2))
        baseline = base * (1.0 - base)
        conf = probs >= self.gate
        out.update(
            brier=round(brier, 4), baseline_brier=round(baseline, 4),
            skill=round(baseline - brier, 4),
            hit_rate=round(float(np.mean((probs >= 0.5) == (labels == 1))), 4),
            base_rate=round(base, 4), confident_n=int(conf.sum()),
            confident_win_rate=round(float(labels[conf].mean()), 4) if conf.any() else None,
        )
        return out

    def _refresh(self) -> None:
        s = self.summary_core()
        was = self.benched
        self.benched = s
        if self.benched and not was:
            logger.warning("🪑 ML model BENCHED: it is not beating the base-rate forecaster. "
                           "Its vote is removed from signals; it keeps predicting and can return.")
        elif was and not self.benched:
            logger.info("✅ ML model back in play: it beats the base-rate forecaster again.")

    def summary_core(self) -> bool:
        """True when there is enough evidence AND the model is worse than the baseline."""
        if len(self._done) < self.min_judge:
            return False
        probs = np.array([d[0] for d in self._done], dtype=float)
        labels = np.array([d[1] for d in self._done], dtype=float)
        base = float(labels.mean())
        return float(np.mean((probs - labels) ** 2)) > base * (1.0 - base)

    # ------------------------------------------------------------------ #

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, 'w') as f:
                json.dump({'total': self.total, 'done': list(self._done)}, f)
        except Exception as e:
            logger.error(f"PredictionLedger.save failed: {e}")

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                d = json.load(f)
            self._done.extend((float(p), int(l)) for p, l in d.get('done', []))
            self.total = int(d.get('total', len(self._done)))
        except Exception as e:
            logger.warning(f"PredictionLedger: could not load prior state: {e}")
