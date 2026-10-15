"""
ModelTrainer — offline ML model trainer for intraday signal generation.

Pipeline:
  1. Fetch 6 months of 5m candles from Kite for each symbol in watchlist
  2. Run Backtester → get list of TradeRecord with 20 features + label
  3. Walk-forward cross-validation (no lookahead) → honest accuracy estimate
  4. Train final model on full dataset
  5. Save model.joblib + metadata.json

Model choice:
  GradientBoostingClassifier (sklearn) — same algorithm as XGBoost/LightGBM,
  pure Python install, works on Python 3.9 system install without libomp.
  Ensemble with RandomForest for stability.
  Final prediction = weighted average of both classifiers.

Label definition:
  1 = trade was net profitable (after all costs)
  0 = trade was a loss

Feature vector: 20 floats from FeatureEngine.FEATURE_NAMES
  (price_pos, rsi14, ema_cross, macd_hist, bb_pct, atr_pct, vol_ratio,
   day_range_pct, ret1, ret5, ret1_abs, high_breakout, low_proximity,
   candle_body, upper_wick, lower_wick, vol_price_trend, rsi_ob, rsi_os,
   dist_to_target)

Output files (data/ml/):
  model.joblib       — trained Pipeline(scaler + ensemble)
  metadata.json      — accuracy, feature importances, training date, params
  training_log.txt   — full walk-forward CV results per fold
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.metrics import (accuracy_score, classification_report,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .backtester import Backtester, TradeRecord
from .feature_engine import FeatureEngine, FEATURE_NAMES, N_FEATURES, MODEL_VERSION

logger = logging.getLogger(__name__)

MODEL_DIR   = 'data/ml'
MODEL_PATH  = os.path.join(MODEL_DIR, 'model.joblib')
META_PATH   = os.path.join(MODEL_DIR, 'metadata.json')
LOG_PATH    = os.path.join(MODEL_DIR, 'training_log.txt')


# ── Model factory ──────────────────────────────────────────────────────────────

def _build_pipeline() -> Pipeline:
    """
    Build sklearn Pipeline: StandardScaler → Voting ensemble.

    GBM: 300 shallow trees, learning rate 0.05 (robust, not overfit).
    RF:  200 trees, max_depth 6.
    VotingClassifier: soft vote (average probabilities).
    """
    gbm = GradientBoostingClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        min_samples_leaf=20,    # regularise: each leaf needs 20 samples
        subsample=0.8,
        random_state=42,
    )
    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=6,
        min_samples_leaf=15,
        max_features='sqrt',
        random_state=42,
        n_jobs=-1,
    )
    ensemble = VotingClassifier(
        estimators=[('gbm', gbm), ('rf', rf)],
        voting='soft',
        weights=[0.6, 0.4],     # GBM slightly preferred — lower variance
    )
    return Pipeline([
        ('scaler', StandardScaler()),
        ('model',  ensemble),
    ])


# ── Trainer ────────────────────────────────────────────────────────────────────

class ModelTrainer:
    """
    Trains, validates, and saves the trading signal ML model.

    Usage:
        trainer = ModelTrainer(trader)
        trainer.run(symbols=['SBIN','TCS','INFY'], lookback_days=180)
    """

    def __init__(self, trader, model_dir: str = MODEL_DIR, progress_cb=None):
        """
        Args:
            trader:       KiteTrader instance (needs get_historical_data)
            model_dir:    Directory to save model + metadata
            progress_cb:  Optional callable(pct: int, msg: str) for UI progress
        """
        self.trader      = trader
        self.model_dir   = model_dir
        self.progress_cb = progress_cb or (lambda pct, msg: None)
        os.makedirs(model_dir, exist_ok=True)
        self._log_lines: List[str] = []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(
        self,
        symbols: List[str],
        lookback_days: int = 180,
        n_cv_folds: int = 5,
    ) -> Dict:
        """
        Full training pipeline.

        Returns metadata dict (also saved to metadata.json).
        """
        start = time.perf_counter()
        self._log(f"Training start — {len(symbols)} symbols, {lookback_days} days, {n_cv_folds} CV folds")
        self.progress_cb(2, 'Fetching historical candles...')

        # ── Step 1: Fetch data + backtest → get labelled trade records ──
        all_X: List[np.ndarray] = []
        all_y: List[np.ndarray] = []
        bt_summaries: List[Dict] = []
        symbols_done = 0

        for symbol in symbols:
            self._log(f"\n── {symbol} ──")
            try:
                candles = self._fetch_candles(symbol, lookback_days)
                if len(candles) < 200:
                    self._log(f"  SKIP: only {len(candles)} candles (need ≥200)")
                    continue

                # Parameter sweep finds best thresholds per symbol
                self.progress_cb(
                    5 + int(40 * symbols_done / len(symbols)),
                    f'Backtesting {symbol}...'
                )
                best_rpt, all_rpts = Backtester.parameter_sweep(candles, symbol)
                bt_summaries.append({
                    'symbol': symbol,
                    'candles': len(candles),
                    'best_params': best_rpt.params,
                    'oos_net_pnl': best_rpt.net_pnl,
                    'oos_win_rate': best_rpt.win_rate,
                    'oos_trades': best_rpt.total_trades,
                    'oos_sharpe': best_rpt.sharpe,
                    'oos_expectancy': best_rpt.expectancy,
                })
                self._log(f"  {best_rpt.summary()}")

                # Extract features from trade records
                X_sym, y_sym = self._trades_to_arrays(best_rpt.trades)
                if len(X_sym) >= 10:
                    all_X.append(X_sym)
                    all_y.append(y_sym)
                    self._log(f"  Features: {len(X_sym)} samples, "
                              f"{int(y_sym.sum())} profitable / {int((1-y_sym).sum())} loss")

            except Exception as e:
                self._log(f"  ERROR: {e}")
                logger.error(f"ModelTrainer: {symbol} failed: {e}", exc_info=True)

            symbols_done += 1

        if not all_X:
            raise RuntimeError("No training data — check Kite connection and symbol list")

        X = np.vstack(all_X).astype(np.float32)
        y = np.concatenate(all_y).astype(np.int8)
        self._log(f"\nTotal samples: {len(X)} | positive rate: {y.mean():.1%}")
        self.progress_cb(50, f'Training model on {len(X)} samples...')

        # ── Step 2: Walk-forward CV ──
        cv_results = self._walk_forward_cv(X, y, n_cv_folds)
        self.progress_cb(75, 'Walk-forward CV complete. Fitting final model...')

        # ── Step 3: Final model on full data ──
        pipeline = _build_pipeline()
        pipeline.fit(X, y)

        # ── Step 4: Feature importances from GBM sub-model ──
        try:
            gbm_model = pipeline.named_steps['model'].estimators_[0][1]   # GBM
            importances = dict(zip(FEATURE_NAMES, gbm_model.feature_importances_.tolist()))
        except Exception:
            importances = {}

        # ── Step 5: Save ──
        joblib.dump(pipeline, MODEL_PATH)
        elapsed = time.perf_counter() - start

        metadata = {
            'model_version':    MODEL_VERSION,
            'trained_at':       datetime.now().isoformat(),
            'symbols':          symbols,
            'lookback_days':    lookback_days,
            'n_samples':        len(X),
            'positive_rate':    round(float(y.mean()), 4),
            'cv_accuracy_mean': round(cv_results['accuracy_mean'], 4),
            'cv_accuracy_std':  round(cv_results['accuracy_std'],  4),
            'cv_auc_mean':      round(cv_results['auc_mean'],      4),
            'cv_precision':     round(cv_results['precision_mean'], 4),
            'cv_recall':        round(cv_results['recall_mean'],    4),
            'feature_importances': importances,
            'backtest_summaries':  bt_summaries,
            'training_seconds':    round(elapsed, 1),
            'model_path':          MODEL_PATH,
        }

        with open(META_PATH, 'w') as f:
            json.dump(metadata, f, indent=2)
        with open(LOG_PATH, 'w') as f:
            f.write('\n'.join(self._log_lines))

        self.progress_cb(100, f'Done. CV accuracy={metadata["cv_accuracy_mean"]:.1%}')
        self._log(f"\n✅ Model saved to {MODEL_PATH}")
        self._log(f"   CV accuracy: {metadata['cv_accuracy_mean']:.1%} ± {metadata['cv_accuracy_std']:.1%}")
        self._log(f"   CV AUC:      {metadata['cv_auc_mean']:.3f}")
        self._log(f"   Training time: {elapsed:.1f}s")

        logger.info(f"ModelTrainer complete. {metadata}")
        return metadata

    # ------------------------------------------------------------------
    # Walk-forward cross-validation
    # ------------------------------------------------------------------

    def _walk_forward_cv(self, X: np.ndarray, y: np.ndarray, n_folds: int) -> Dict:
        """
        TimeSeriesSplit — future data never leaks into training fold.
        Returns dict of mean metrics across folds.
        """
        tscv = TimeSeriesSplit(n_splits=n_folds)
        accs, aucs, precs, recs = [], [], [], []

        self._log(f"\nWalk-forward CV ({n_folds} folds):")
        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_tr, X_te = X[train_idx], X[test_idx]
            y_tr, y_te = y[train_idx], y[test_idx]

            if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
                continue   # skip folds with only one class

            pipe = _build_pipeline()
            pipe.fit(X_tr, y_tr)
            y_pred  = pipe.predict(X_te)
            y_prob  = pipe.predict_proba(X_te)[:, 1]

            acc  = accuracy_score(y_te, y_pred)
            auc  = roc_auc_score(y_te, y_prob)
            prec = precision_score(y_te, y_pred, zero_division=0)
            rec  = recall_score(y_te, y_pred, zero_division=0)

            accs.append(acc); aucs.append(auc)
            precs.append(prec); recs.append(rec)
            self._log(f"  fold {fold+1}: acc={acc:.3f} auc={auc:.3f} "
                      f"prec={prec:.3f} rec={rec:.3f}  "
                      f"(train={len(X_tr)}, test={len(X_te)})")

        return dict(
            accuracy_mean  = float(np.mean(accs))  if accs  else 0.5,
            accuracy_std   = float(np.std(accs))   if accs  else 0.0,
            auc_mean       = float(np.mean(aucs))  if aucs  else 0.5,
            precision_mean = float(np.mean(precs)) if precs else 0.5,
            recall_mean    = float(np.mean(recs))  if recs  else 0.5,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_candles(self, symbol: str, days: int) -> List[Dict]:
        """Fetch 5m historical candles from Kite."""
        to_date   = datetime.now()
        from_date = to_date - timedelta(days=days)
        candles   = self.trader.get_historical_data(
            symbol=symbol, from_date=from_date,
            to_date=to_date, interval='5minute',
        )
        self._log(f"  Fetched {len(candles)} 5m candles for {symbol}")
        return candles

    def _trades_to_arrays(
        self, trades: List[TradeRecord]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert trade records to (X, y) numpy arrays.
        X: (n_trades, 20) float32 — features at trade entry
        y: (n_trades,)    int8    — 1=win, 0=loss
        """
        rows = []
        labels = []
        fe = FeatureEngine()

        for t in trades:
            if not t.features:
                continue
            # Build vector from stored feature dict (same order as FEATURE_NAMES)
            try:
                row = np.array([t.features.get(f, 0.0) for f in FEATURE_NAMES],
                               dtype=np.float32)
                if np.any(np.isnan(row)) or np.any(np.isinf(row)):
                    continue
                rows.append(row)
                labels.append(t.label)
            except Exception:
                continue

        if not rows:
            return np.empty((0, N_FEATURES), dtype=np.float32), np.empty(0, dtype=np.int8)

        return np.stack(rows), np.array(labels, dtype=np.int8)

    def _log(self, msg: str):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f"[{ts}] {msg}"
        self._log_lines.append(line)
        logger.info(msg)


# ── Model loader — used at inference time ──────────────────────────────────────

_cached_pipeline: Optional[Pipeline] = None
_cached_meta: Optional[Dict] = None


def load_model() -> Tuple[Optional[Pipeline], Optional[Dict]]:
    """
    Load trained model + metadata. Cached — safe to call every iteration.
    Returns (None, None) if no model has been trained yet.
    """
    global _cached_pipeline, _cached_meta

    if _cached_pipeline is not None:
        return _cached_pipeline, _cached_meta

    if not os.path.exists(MODEL_PATH):
        return None, None

    try:
        _cached_pipeline = joblib.load(MODEL_PATH)
        with open(META_PATH) as f:
            _cached_meta = json.load(f)
        logger.info(f"Model loaded: accuracy={_cached_meta.get('cv_accuracy_mean'):.1%} "
                    f"trained={_cached_meta.get('trained_at','?')[:10]}")
        return _cached_pipeline, _cached_meta
    except Exception as e:
        logger.error(f"Model load failed: {e}")
        return None, None


def invalidate_model_cache():
    """Call after retraining to force reload on next inference."""
    global _cached_pipeline, _cached_meta
    _cached_pipeline = None
    _cached_meta = None
