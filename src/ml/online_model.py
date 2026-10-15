"""
OnlineModel — adapts after every trade fill via incremental learning.

Why this exists:
  Markets change regime (trending → ranging → volatile) throughout the day
  and across weeks. An offline model trained on historical data has stale
  weights by afternoon. OnlineModel runs `partial_fit` after every
  closed trade, continuously updating its view of "what works today."

Architecture:
  - Primary:  GBM offline model (model.joblib) — high accuracy, slow to update
  - Adapter:  SGDClassifier (logistic) — updates in microseconds per sample
  - Blend:    final_score = α × gbm_score + (1-α) × sgd_score
    α starts at 0.9 (trust offline) and shifts to 0.7 after 50 online trades
    (trust online more once it has enough signal)

Usage:
    om = OnlineModel()
    # at inference:
    score = om.predict_proba(feature_vector)   # 0–1, probability of win
    # after a trade closes:
    om.update(feature_vector_at_entry, label)  # 1=win, 0=loss
    om.save()                                  # persists online weights
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

import joblib
import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler

from .feature_engine import FeatureEngine, FEATURE_NAMES, N_FEATURES
from .model_trainer import load_model, MODEL_DIR

logger = logging.getLogger(__name__)

ONLINE_MODEL_PATH = os.path.join(MODEL_DIR, 'online_model.joblib')
ONLINE_META_PATH  = os.path.join(MODEL_DIR, 'online_meta.json')

# SGD blend weight — how much to trust the online model
_ALPHA_INITIAL   = 0.90   # 90% offline, 10% online
_ALPHA_MATURE    = 0.70   # 70% offline, 30% online (after 50 trades)
_MATURE_THRESHOLD = 50


class OnlineModel:
    """
    Blends the offline GBM model with an incremental SGD adapter.

    Thread-safe for reads (predict). Updates should only happen
    from the PostTradeAgent callback (single-threaded).
    """

    def __init__(self):
        self._offline_pipe = None       # loaded lazily
        self._offline_meta = None
        self._scaler   = StandardScaler()
        self._sgd      = SGDClassifier(
            loss='log_loss',            # gives predict_proba
            learning_rate='adaptive',
            eta0=0.01,
            penalty='l2',
            alpha=1e-4,
            random_state=42,
            warm_start=True,
        )
        self._sgd_fitted   = False
        self._n_updates    = 0
        self._scaler_fitted = False

        # Buffer for first-batch fit (SGD needs at least 2 classes before partial_fit)
        self._warmup_X = []
        self._warmup_y = []
        self._warmup_done = False

        self._load()
        logger.info(f"OnlineModel init: {self._n_updates} prior updates")

    # ------------------------------------------------------------------
    # Inference — called from SignalEngine on every tick
    # ------------------------------------------------------------------

    def predict_proba(self, feature_vec: np.ndarray) -> float:
        """
        Return probability (0–1) that the next trade will be profitable.
        Uses blend of offline GBM + online SGD.
        Returns 0.5 if no model is available yet.
        """
        if feature_vec is None or len(feature_vec) != N_FEATURES:
            return 0.5

        x = feature_vec.reshape(1, -1).astype(np.float32)

        # Offline score
        offline_score = 0.5
        pipe, _ = load_model()
        if pipe is not None:
            try:
                offline_score = float(pipe.predict_proba(x)[0, 1])
            except Exception:
                pass

        # Online score (only if fitted)
        online_score = offline_score
        if self._sgd_fitted and self._scaler_fitted:
            try:
                x_scaled = self._scaler.transform(x)
                online_score = float(self._sgd.predict_proba(x_scaled)[0, 1])
            except Exception:
                pass

        # Blend
        alpha = _ALPHA_INITIAL if self._n_updates < _MATURE_THRESHOLD else _ALPHA_MATURE
        return alpha * offline_score + (1.0 - alpha) * online_score

    def should_trade(self, feature_vec: np.ndarray, threshold: float = 0.55) -> bool:
        """Return True if model thinks this trade has >threshold win probability."""
        return self.predict_proba(feature_vec) >= threshold

    # ------------------------------------------------------------------
    # Online update — called after every closed trade
    # ------------------------------------------------------------------

    def update(self, feature_vec: np.ndarray, label: int) -> None:
        """
        Incrementally update the SGD adapter with one new sample.

        Args:
            feature_vec: 20-float array (same order as FEATURE_NAMES)
            label:       1 = trade was profitable, 0 = loss
        """
        if feature_vec is None or len(feature_vec) != N_FEATURES:
            return
        if label not in (0, 1):
            return

        x = feature_vec.astype(np.float32).reshape(1, -1)

        if not self._warmup_done:
            # Buffer until we have both classes
            self._warmup_X.append(x[0])
            self._warmup_y.append(int(label))
            if len(set(self._warmup_y)) == 2 and len(self._warmup_y) >= 10:
                X_w = np.stack(self._warmup_X).astype(np.float32)
                y_w = np.array(self._warmup_y, dtype=np.int8)
                self._scaler.fit(X_w)
                self._scaler_fitted = True
                X_scaled = self._scaler.transform(X_w)
                self._sgd.fit(X_scaled, y_w)
                self._sgd_fitted = True
                self._warmup_done = True
                self._n_updates  += len(y_w)
                logger.info(f"OnlineModel: warmup complete with {len(y_w)} samples")
                self._warmup_X.clear()
                self._warmup_y.clear()
            return

        # Incremental update
        try:
            x_scaled = self._scaler.transform(x)
            self._sgd.partial_fit(x_scaled, [int(label)], classes=[0, 1])
            self._n_updates += 1

            if self._n_updates % 10 == 0:
                logger.info(f"OnlineModel: {self._n_updates} updates, "
                            f"blend_alpha={_ALPHA_INITIAL if self._n_updates < _MATURE_THRESHOLD else _ALPHA_MATURE}")
        except Exception as e:
            logger.error(f"OnlineModel.update failed: {e}")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Save SGD weights + scaler to disk."""
        if not self._sgd_fitted:
            return
        try:
            os.makedirs(MODEL_DIR, exist_ok=True)
            joblib.dump({'sgd': self._sgd, 'scaler': self._scaler,
                         'n_updates': self._n_updates,
                         'warmup_done': self._warmup_done}, ONLINE_MODEL_PATH)
            with open(ONLINE_META_PATH, 'w') as f:
                json.dump({'n_updates': self._n_updates,
                           'saved_at': datetime.now().isoformat()}, f)
        except Exception as e:
            logger.error(f"OnlineModel.save failed: {e}")

    def _load(self) -> None:
        """Restore SGD state from disk if available."""
        if not os.path.exists(ONLINE_MODEL_PATH):
            return
        try:
            d = joblib.load(ONLINE_MODEL_PATH)
            self._sgd         = d['sgd']
            self._scaler      = d['scaler']
            self._n_updates   = d.get('n_updates', 0)
            self._warmup_done = d.get('warmup_done', True)
            self._sgd_fitted  = True
            self._scaler_fitted = True
            logger.info(f"OnlineModel: loaded {self._n_updates} prior updates")
        except Exception as e:
            logger.warning(f"OnlineModel: could not load prior state: {e}")

    @property
    def n_updates(self) -> int:
        return self._n_updates

    @property
    def is_mature(self) -> bool:
        return self._n_updates >= _MATURE_THRESHOLD
