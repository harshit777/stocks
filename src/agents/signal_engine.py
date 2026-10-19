"""
Agent 2: SignalEngine

Responsibility: Generate BUY / SELL / HOLD for every symbol every iteration.

ML integration (added after initial build):
  - FeatureEngine maintains a rolling 200-candle buffer per symbol
  - OnlineModel blends offline GBM (model.joblib) + live SGDClassifier
  - _score_prediction() is now ML inference, not heuristic RSI/MACD rules
  - OnlineModel.update() is called after every closed trade via record_trade_outcome()
  - If no model.joblib exists yet, _score_prediction returns None (excluded from blend)

Pipeline per symbol per iteration:
  1. Update intraday high/low tracker
  2. Update FeatureEngine rolling buffer with latest candle
  3. Check 15-min breakout condition (Chartink equivalent)
  4. Check candlestick patterns (PatternRecognizer)
  5. Check trend (PatternRecognizer)
  6. Check price-action sentiment (SentimentAnalyzer, per-symbol)
  7. ML inference: OnlineModel.predict_proba → score
  8. Combine with weights; return signal only if combined confidence ≥ threshold
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import numpy as np

from ..strategies.intraday_high_low_strategy import IntradayHighLowStrategy
from ..ai_modules.pattern_recognition import PatternRecognizer
from ..ai_modules.sentiment_analyzer import SentimentAnalyzer
from ..ai_modules.predictive_model import PredictiveModel
from ..ai_modules.trading_psychology import TradingPsychologyGuard
from ..ml.feature_engine import FeatureEngine
from ..ml.online_model import OnlineModel
from ..ml.prediction_ledger import PredictionLedger, reward_weight


class SignalEngine:
    """
    Generates trading signals for a list of symbols.

    Wraps IntradayHighLowStrategy (proven, working) and augments it with
    ML-backed prediction that replaces the heuristic PredictiveModel.
    """

    # Component weights — must sum to 1.0
    WEIGHTS = {
        'breakout':   0.35,   # High-low position in day range (most reliable)
        'pattern':    0.20,   # Candlestick patterns
        'trend':      0.20,   # EMA trend direction
        'sentiment':  0.10,   # Price-action sentiment (per-symbol, fixed)
        'prediction': 0.15,   # ML model (GBM offline + SGD online blend)
    }

    def __init__(
        self,
        trader,
        symbols: List[str],
        min_profit_margin: float = 0.02,
        buy_threshold: float = 0.20,
        sell_threshold: float = 0.80,
        risk_reward_ratio: float = 3.0,
        max_position_pct: float = 0.15,
        stop_loss_pct: float = 0.015,
        confidence_threshold: float = 0.55,
        ai_data_dir: str = 'data/ai_data',
    ):
        self.trader = trader
        self.symbols = symbols
        self.confidence_threshold = confidence_threshold
        self.confidence_adjuster = None     # optional callable(symbol, signal) -> float
        self.logger = logging.getLogger(__name__)

        # Base strategy handles intraday high/low breakout logic
        self.base_strategy = IntradayHighLowStrategy(
            trader=trader,
            symbols=symbols,
            min_profit_margin=min_profit_margin,
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            risk_reward_ratio=risk_reward_ratio,
            max_position_pct=max_position_pct,
            stop_loss_pct=stop_loss_pct,
        )

        # AI modules (heuristic layer — still used for pattern + trend + sentiment)
        self.pattern_recognizer = PatternRecognizer(lookback_periods=100)
        self.sentiment_analyzer = SentimentAnalyzer()
        self.predictive_model   = PredictiveModel()   # kept for seed_historical_data

        # ML layer — replaces heuristic prediction score
        self._feature_engines: Dict[str, FeatureEngine] = {}   # symbol → FeatureEngine
        self._online_model = OnlineModel()
        # Holds the model to account: every prediction is judged by what the market did next
        self.ledger = PredictionLedger(target_pct=0.025, stop_pct=stop_loss_pct)
        self._latest_prob: Dict[str, float] = {}      # symbol → model's latest win probability
        self._entry_prob: Dict[str, float] = {}       # symbol → probability when the position was opened
        self._passes = 0
        # symbol → (feature vector at entry, entry price) for the open position,
        # so the online model learns from what the signal saw when it bought.
        self._entry_features: Dict[str, Tuple[np.ndarray, float]] = {}

        # Psychology guard
        self.psychology_guard = TradingPsychologyGuard(
            max_daily_trades=10,
            max_consecutive_losses=3,
            cooldown_after_loss=15,
            reduce_size_after_wins=3,
            max_drawdown_pct=0.05,
            fomo_prevention_window=4,   # 4 min × 2-min loop = 2 iterations
        )

        self._import_models(ai_data_dir)

    # ------------------------------------------------------------------
    # Startup: seed AI modules with real historical candles
    # ------------------------------------------------------------------

    def seed_historical_data(self, days: int = 5):
        """
        Fetch real historical 5-min candles for each symbol and seed
        the PredictiveModel and PatternRecognizer.

        Call ONCE after market open before starting the main loop.
        Without this, multi-timeframe analysis runs on repeated snapshots.
        """
        from datetime import date
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        seeded = 0
        for symbol in self.symbols:
            try:
                candles = self.trader.get_historical_data(
                    symbol=symbol,
                    from_date=from_date,
                    to_date=to_date,
                    interval='5minute',
                )
                if not candles:
                    self.logger.warning(f"SignalEngine: no historical data for {symbol}")
                    continue

                if symbol not in self._feature_engines:
                    self._feature_engines[symbol] = FeatureEngine(maxlen=200)
                fe = self._feature_engines[symbol]

                # Track running day high/low for FeatureEngine (reset per calendar day)
                _day_high = _day_low = None
                _last_day = None

                for candle in candles:
                    c = {
                        'open':   candle.get('open', 0),
                        'high':   candle.get('high', 0),
                        'low':    candle.get('low', 0),
                        'close':  candle.get('close', 0),
                        'volume': candle.get('volume', 0),
                    }
                    self.pattern_recognizer.update_price_history(symbol, c)
                    self.predictive_model.update_timeframe_data(symbol, '5m', c)

                    # Seed FeatureEngine — compute running day H/L per date
                    cdate = candle.get('date')
                    cday  = cdate.date() if hasattr(cdate, 'date') else None
                    if cday != _last_day:
                        _day_high = c['high']; _day_low = c['low']; _last_day = cday
                    else:
                        if _day_high is not None:
                            _day_high = max(_day_high, c['high'])
                            _day_low  = min(_day_low,  c['low'])
                    fe.update({**c, 'day_high': _day_high or c['high'],
                                     'day_low':  _day_low  or c['low']})

                seeded += 1
            except Exception as e:
                self.logger.error(f"SignalEngine: seed failed for {symbol}: {e}")

        self.logger.info(
            f"SignalEngine: seeded historical data for {seeded}/{len(self.symbols)} symbols"
        )

    # ------------------------------------------------------------------
    # Main per-iteration call
    # ------------------------------------------------------------------

    def generate_signal(self, symbol: str, market_data: Dict) -> Optional[str]:
        """
        Generate a trading signal for one symbol.

        Args:
            symbol:      NSE trading symbol (e.g. 'SBIN')
            market_data: Result of trader.get_quote([symbol])

        Returns:
            'BUY', 'SELL', or None
        """
        symbol_key = f"NSE:{symbol}"
        if symbol_key not in market_data:
            return None

        quote = market_data[symbol_key]
        current_price = quote.get('last_price', 0)
        if current_price <= 0:
            return None

        ohlc = quote.get('ohlc', {})
        candle = {
            'open':   ohlc.get('open', current_price),
            'high':   ohlc.get('high', current_price),
            'low':    ohlc.get('low', current_price),
            'close':  current_price,
            'volume': quote.get('volume', 0),
        }

        # Update intraday high/low tracker
        self.base_strategy.update_intraday_data(symbol, market_data)

        # Update heuristic AI modules
        self.pattern_recognizer.update_price_history(symbol, candle)
        self.predictive_model.update_timeframe_data(symbol, '5m', candle)

        # Update FeatureEngine rolling buffer — annotate with day high/low
        if symbol not in self._feature_engines:
            self._feature_engines[symbol] = FeatureEngine(maxlen=200)
        intraday = self.base_strategy.intraday_data.get(symbol, {})
        candle_with_day = {
            **candle,
            'day_high': intraday.get('high', candle['high']),
            'day_low':  intraday.get('low',  candle['low']),
        }
        self._feature_engines[symbol].update(candle_with_day)

        # Update price-action sentiment (per-symbol, fixed bug)
        prev_close = self.base_strategy.intraday_data.get(symbol, {}).get(
            'prev_close', current_price
        )
        price_change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close > 0 else 0
        self.sentiment_analyzer.update_sentiment(symbol, price_change_pct)
        self.base_strategy.intraday_data.setdefault(symbol, {})['prev_close'] = current_price

        # Collect component signals
        scores: Dict[str, Optional[float]] = {
            'breakout':   self._score_breakout(symbol, market_data),
            'pattern':    self._score_patterns(symbol),
            'trend':      self._score_trend(symbol),
            'sentiment':  self._score_sentiment(symbol),   # fixed: uses `symbol`
            'prediction': self._score_prediction(symbol),
        }

        self._judge_predictions(symbol, current_price)

        signal, confidence = self._combine(scores)

        # Learned news-tone nudge (bounded, and zero until enough evidence exists)
        if signal and self.confidence_adjuster is not None:
            try:
                confidence += self.confidence_adjuster(symbol, signal)
            except Exception:
                pass

        if signal and confidence >= self.confidence_threshold:
            # Psychology guard — FOMO prevention, cooldown, daily limits
            psych = self.psychology_guard.should_allow_trade(symbol, signal, confidence)
            if not psych['allowed']:
                self.logger.info(
                    f"SignalEngine: {symbol} {signal} blocked by psychology: {psych['reason']}"
                )
                return None

            self.logger.info(
                f"SignalEngine: {symbol} → {signal} "
                f"(confidence={confidence:.2f}, scores={self._fmt(scores)})"
            )
            return signal

        return None

    def run_iteration(self) -> Dict[str, Optional[str]]:
        """
        Run one full iteration across all symbols.

        Returns dict of symbol → signal (None if no signal).
        """
        signals = {}
        looks = []   # (symbol, position in day range, room up to day high) for the scan summary
        for symbol in self.symbols:
            try:
                market_data = self.trader.get_quote([symbol])
                signals[symbol] = self.generate_signal(symbol, market_data)
                look = self._entry_look(symbol, market_data)
                if look:
                    looks.append(look)
            except Exception as e:
                self.logger.error(f"SignalEngine: error on {symbol}: {e}")
                signals[symbol] = None
        self._log_scan(looks, signals)
        self._passes += 1
        if self._passes % 5 == 0:
            self._log_scoreboard()
        return signals

    def _entry_look(self, symbol: str, market_data: Dict):
        """(symbol, position in day range, room to day high) — what the breakout gate sees."""
        price = market_data.get(f"NSE:{symbol}", {}).get('last_price', 0)
        data = self.base_strategy.intraday_data.get(symbol)
        if price <= 0 or not data:
            return None
        pos = self.base_strategy.calculate_price_position(symbol, price)
        return symbol, pos, (data['high'] - price) / price

    def _log_scan(self, looks, signals):
        """One INFO line per pass: why entries did or did not happen (rejections are DEBUG)."""
        if not looks:
            return
        s = self.base_strategy
        need = max(s.min_profit_margin, s.risk_reward_ratio * s.stop_loss_pct)
        in_zone = [l for l in looks if l[1] <= s.buy_threshold]
        roomy = [l for l in in_zone if l[2] >= need]
        nearest = sorted(looks, key=lambda l: l[1])[:3]
        self.logger.info(
            f"Entry scan: {len(looks)} symbols | in buy zone (<={s.buy_threshold:.0%} of day range): "
            f"{len(in_zone)} | with room >={need:.1%} to day high: {len(roomy)} | "
            f"signals: {sum(1 for v in signals.values() if v)} | "
            "lowest-in-range: " + ', '.join(f"{sym} {p:.0%} (room {r:.1%})" for sym, p, r in nearest)
        )

    def record_entry(self, symbol: str, entry_price: float):
        """Remember the feature vector at the moment a position is opened."""
        fe = self._feature_engines.get(symbol)
        vec = fe.latest_vector() if fe is not None else None
        if vec is not None:
            self._entry_features[symbol] = (vec.copy(), entry_price)
            prob = self._latest_prob.get(symbol)
            if prob is not None:
                self._entry_prob[symbol] = prob

    def record_trade_outcome(self, symbol: str, signal: str,
                             entry_price: float, quantity: int,
                             pnl: Optional[float] = None):
        """
        Propagate trade result into psychology guard AND online ML model.

        For a closing SELL, `entry_price` is the EXIT fill price (the argument
        name is historical) and `pnl` is the gross profit of the round trip.
        """
        self.psychology_guard.record_trade(symbol, signal, entry_price, quantity, pnl)

        # Online model update — only on a closing SELL, using the features seen at
        # ENTRY and the same label the offline model uses: profitable after costs.
        if signal == 'SELL' and pnl is not None:
            entry = self._entry_features.pop(symbol, None)
            if entry is None:
                return   # position not opened by this engine (e.g. synced): nothing to learn from
            feature_vec, buy_price = entry
            from ..utils.cost_calculator import get_cost_calculator
            calc = get_cost_calculator()
            costs = (calc.calculate_total_cost(buy_price, quantity, 'BUY')['total_cost']
                     + calc.calculate_total_cost(entry_price, quantity, 'SELL')['total_cost'])
            label = 1 if (pnl - costs) > 0 else 0
            prob = self._entry_prob.pop(symbol, None)
            # A real trade is the strongest feedback: a confident miss is punished hardest
            self._online_model.update(feature_vec, label,
                                      weight=reward_weight(prob, label, traded=True))
            self.logger.info(
                f"ML verdict {symbol}: predicted {'n/a' if prob is None else f'{prob:.0%}'} win, "
                f"trade {'WON' if label else 'LOST'} net of costs"
            )
            if self._online_model.n_updates % 5 == 0:
                self._online_model.save()

    def reset_daily(self, starting_capital: float):
        """Reset all intraday state at market open."""
        self.base_strategy.reset_daily_data()
        self.psychology_guard.reset_daily_stats(starting_capital)

    # ------------------------------------------------------------------
    # Component scorers — each returns float in [-1, 1] or None
    # None means "no data / skip this component"
    # ------------------------------------------------------------------

    def _score_breakout(self, symbol: str, market_data: Dict) -> Optional[float]:
        """High-low position in day range. Core of reel Method 3."""
        signal = self.base_strategy.analyze(symbol, market_data)
        if signal == 'BUY':
            return 1.0
        if signal == 'SELL':
            return -1.0
        return None

    def _score_patterns(self, symbol: str) -> Optional[float]:
        """Candlestick pattern score."""
        patterns = self.pattern_recognizer.detect_candlestick_patterns(symbol)
        if not patterns:
            return None

        bullish = sum(patterns.get(p, 0) for p in ['hammer', 'bullish_engulfing', 'morning_star'])
        bearish = sum(patterns.get(p, 0) for p in ['shooting_star', 'bearish_engulfing', 'evening_star'])

        if bullish > bearish and bullish > 0.6:
            return bullish
        if bearish > bullish and bearish > 0.6:
            return -bearish
        return None

    def _score_trend(self, symbol: str) -> Optional[float]:
        """Trend direction and strength."""
        trend = self.pattern_recognizer.detect_trend(symbol)
        if trend.get('confidence', 0) < 0.5:
            return None
        strength = trend.get('strength', 0)
        if trend.get('direction') == 'uptrend' and strength > 0.5:
            return strength
        if trend.get('direction') == 'downtrend' and strength > 0.5:
            return -strength
        return None

    def _score_sentiment(self, symbol: str) -> Optional[float]:
        """
        Price-action sentiment for THIS symbol.
        Bug fix: was reading self.sentiment_cache.keys()[0] (wrong symbol).
        """
        sent = self.sentiment_analyzer.get_sentiment_score(symbol)
        if sent.get('confidence', 0) < 0.4:
            return None
        score = sent.get('current', 0.0)
        return score if abs(score) > 0.2 else None

    def _score_prediction(self, symbol: str) -> Optional[float]:
        """
        ML model inference — GBM offline + SGD online blend.
        Returns float in [-1, 1] where +1 = strong buy, -1 = strong sell.
        Returns None if FeatureEngine has insufficient data (< 30 bars).
        """
        fe = self._feature_engines.get(symbol)
        if fe is None:
            return None
        vec = fe.latest_vector()
        if vec is None:
            return None   # not enough history yet

        prob = self._online_model.predict_proba(vec)   # 0–1 win probability
        self._latest_prob[symbol] = prob               # logged and judged even while benched
        if self.ledger.benched:
            return None    # the model is not beating the base rate: it does not get a vote
        # Map 0–1 probability to -1..+1 signal score
        # prob=0.5 → 0 (no signal), prob=0.7 → +0.4, prob=0.3 → -0.4
        score = (prob - 0.5) * 2.0
        return score if abs(score) > 0.1 else None

    def _judge_predictions(self, symbol: str, price: float):
        """Record this pass's prediction, and learn from earlier ones the market has now answered."""
        fe = self._feature_engines.get(symbol)
        vec = fe.latest_vector() if fe is not None else None
        prob = self._latest_prob.get(symbol) if vec is not None else None
        try:
            for a in self.ledger.observe(symbol, price, vec, prob):
                self._online_model.update(
                    a['vec'], a['label'], weight=reward_weight(a['prob'], a['label']))
        except Exception as e:
            self.logger.error(f"SignalEngine: prediction ledger error on {symbol}: {e}")

    def _log_scoreboard(self):
        s = self.ledger.summary()
        if not s['window']:
            self.logger.info("ML scoreboard: no predictions answered yet")
            return
        verdict = ('BENCHED' if s['benched'] else
                   'on probation' if s['window'] < s['min_judge'] else 'trusted')
        conf = ('n/a' if s['confident_win_rate'] is None
                else f"{s['confident_win_rate']:.0%} of {s['confident_n']}")
        self.logger.info(
            f"ML scoreboard [{verdict}]: {s['window']} answered | "
            f"error {s['brier']:.3f} vs always-guess-base-rate {s['baseline_brier']:.3f} "
            f"(skill {s['skill']:+.3f}) | right side {s['hit_rate']:.0%} | "
            f"base win rate {s['base_rate']:.0%} | when confident it won {conf}"
        )

    # ------------------------------------------------------------------
    # Signal combiner
    # ------------------------------------------------------------------

    def _combine(self, scores: Dict[str, Optional[float]]) -> Tuple[Optional[str], float]:
        """
        Weighted average of available component scores.

        Components with None score are excluded from both numerator
        and denominator — avoids diluting confidence when data is absent.
        """
        total_weight = 0.0
        weighted_sum = 0.0

        for component, score in scores.items():
            if score is None:
                continue
            w = self.WEIGHTS[component]
            weighted_sum += score * w
            total_weight += w

        if total_weight < 0.35:
            # Not enough data to make a call (< 35% of weights have signals)
            return None, 0.0

        avg = weighted_sum / total_weight
        confidence = abs(avg)

        if avg > 0.3:
            return 'BUY', confidence
        if avg < -0.3:
            return 'SELL', confidence
        return None, confidence

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fmt(self, scores: Dict) -> str:
        parts = []
        for k, v in scores.items():
            parts.append(f"{k}={'None' if v is None else f'{v:+.2f}'}")
        return ' | '.join(parts)

    def get_ml_status(self) -> Dict:
        """Return ML model status for dashboard display."""
        from ..ml.model_trainer import load_model
        _, meta = load_model()
        return {
            'online_updates':   self._online_model.n_updates,
            'online_mature':    self._online_model.is_mature,
            'scoreboard':       self.ledger.summary(),
            'offline_accuracy': meta.get('cv_accuracy_mean') if meta else None,
            'offline_trained':  meta.get('trained_at') if meta else None,
            'symbols_with_features': len(self._feature_engines),
        }

    def _import_models(self, ai_data_dir: str):
        """Load persisted AI model state if available."""
        import os, json
        pattern_file = os.path.join(ai_data_dir, 'patterns.json')
        sentiment_file = os.path.join(ai_data_dir, 'sentiment.json')
        model_file = os.path.join(ai_data_dir, 'model.json')
        self.pattern_recognizer.load_patterns(pattern_file)
        self.sentiment_analyzer.load_sentiment_data(sentiment_file)
        self.predictive_model.load_model(model_file)

    def save_models(self, ai_data_dir: str = 'data/ai_data'):
        """Persist AI model state to disk."""
        import os
        os.makedirs(ai_data_dir, exist_ok=True)
        self.pattern_recognizer.save_patterns(os.path.join(ai_data_dir, 'patterns.json'))
        self.sentiment_analyzer.save_sentiment_data(os.path.join(ai_data_dir, 'sentiment.json'))
        self.predictive_model.save_model(os.path.join(ai_data_dir, 'model.json'))
        self.ledger.save()
