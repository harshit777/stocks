#!/usr/bin/env python3
"""
Daily model training for the paper-trading period (run after market close).

Retrains the offline gradient-boosting model on the latest candles and appends
the result to data/paper/training_history.json. The online (per-trade) model is
updated separately during the trading session.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

DEFAULT_SYMBOLS = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK',
                   'SBIN', 'AXISBANK', 'WIPRO', 'LT', 'BAJFINANCE']
HISTORY = 'data/paper/training_history.json'


def main() -> int:
    from src.kite_trader.trader import KiteTrader
    from src.ml.model_trainer import ModelTrainer
    from src.utils.paper_report import update_summary

    symbols = [s.strip() for s in os.getenv('TRAIN_SYMBOLS', '').split(',') if s.strip()] \
        or DEFAULT_SYMBOLS
    lookback = int(os.getenv('TRAIN_LOOKBACK_DAYS', '180'))

    trader = KiteTrader()   # market data only; this script never places orders
    if not trader.is_connected():
        print('Cannot connect to Zerodha — check KITE_ACCESS_TOKEN.')
        return 1

    meta = ModelTrainer(trader).run(symbols=symbols, lookback_days=lookback, n_cv_folds=5)

    history = []
    if os.path.exists(HISTORY):
        with open(HISTORY) as f:
            history = json.load(f)
    history.append({k: meta.get(k) for k in
                    ('trained_at', 'n_samples', 'cv_accuracy_mean', 'cv_auc_mean',
                     'cv_precision', 'cv_recall', 'positive_rate')})
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, 'w') as f:
        json.dump(history[-60:], f, indent=2)

    update_summary()
    print(f"[{datetime.now():%F %T}] trained on {meta['n_samples']} samples, "
          f"CV accuracy {meta['cv_accuracy_mean']:.1%}, AUC {meta['cv_auc_mean']:.3f}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
