"""
Agent 7 — Market Analyst.

  morning   reads news for the market and for each watchlist stock and records the tone
            BEFORE prices move (so it cannot be an after-the-fact explanation)
  intraday  every ~30 min logs Nifty's move next to the market-news tone
  evening   explains what moved each stock (market vs stock-specific, gap, volume, news),
            reviews the trades we took, writes the daily report, and stores
            (morning tone, day's move) pairs so the system can learn whether news tone
            has actually predicted direction

Learning: after enough observations, `adjust()` nudges a signal's confidence by at most
+/-0.10 according to how reliable the news tone has been. Before that it returns 0, so
it cannot change early results.

Nothing here may break trading: every public method catches its own errors, and all
network calls are short and happen at startup, every ~30 min, and at end of day only.
"""
import logging
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

from src.ai_modules.sentiment_analyzer import SentimentAnalyzer
from src.utils import market_analysis as ma
from src.utils import news_feed

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 1800
LEARN_IF_STARTED_BEFORE = 10 * 60      # minutes since midnight; later starts aren't "before the move"
MAX_HEADLINES_SHOWN = 5


def _quote(quotes: Dict, *keys) -> Dict:
    for k in keys:
        if quotes.get(k):
            return quotes[k]
    return {}


class MarketAnalystAgent:
    def __init__(self, trader, analysis_dir: str,
                 news_fetch: Callable = news_feed.fetch,
                 sentiment: Optional[SentimentAnalyzer] = None,
                 clock: Callable[[], datetime] = datetime.now):
        self.trader = trader
        self.analysis_dir = analysis_dir
        self._fetch = news_fetch
        self._sent = sentiment or SentimentAnalyzer()
        self._clock = clock

        self.history: List[Dict] = ma.load_history(analysis_dir)
        self.stats: Dict = ma.news_stats(self.history)

        self.symbols: List[str] = []
        self.stock_tone: Dict[str, Dict] = {}      # symbol -> {score, confidence, label, n, top}
        self.market_tone: Dict = {'score': 0.0, 'confidence': 0.0, 'label': 'none', 'n': 0}
        self.market_headlines: List[Dict] = []
        self.timeline: List[Dict] = []
        self._last_refresh = 0.0
        self._started = False
        self._early = False

    # ------------------------------------------------------------------ #
    # News -> tone
    # ------------------------------------------------------------------ #

    def _score_headlines(self, items: List[Dict]) -> Dict:
        scored = []
        for it in items:
            r = self._sent.analyze_text(it['title'])
            scored.append({**it, 'score': round(r['score'], 2) if r['confidence'] else 0.0,
                           'has_signal': bool(r['confidence'])})
        informative = [s['score'] for s in scored if s['has_signal']]
        score = sum(informative) / len(informative) if informative else 0.0
        confidence = min(1.0, len(informative) / 3.0)
        return {'score': round(score, 3), 'confidence': round(confidence, 2),
                'label': ma.tone_label(score, confidence), 'n': len(items),
                'headlines': scored}

    def _market_news(self):
        tone = self._score_headlines(self._fetch(news_feed.MARKET_QUERY, max_items=10))
        self.market_headlines = tone.pop('headlines')
        self.market_tone = tone

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start_day(self, symbols: List[str]):
        """Capture the morning tone. Call once, right after the watchlist is chosen."""
        try:
            self.symbols = list(symbols)
            self._market_news()
            self.stock_tone = {}
            for sym in self.symbols:
                tone = self._score_headlines(self._fetch(news_feed.query_for(sym), max_items=6))
                heads = tone.pop('headlines')
                tone['top'] = heads[0]['title'] if heads else None
                tone['headlines'] = [{'title': h['title'], 'source': h.get('source', ''),
                                      'score': h['score']} for h in heads[:3]]
                self.stock_tone[sym] = tone
            self._started = True
            now = self._clock()
            self._early = now.hour * 60 + now.minute < LEARN_IF_STARTED_BEFORE
            self._last_refresh = time.time()
            self._timeline_point()
            logger.info("📰 Market news: %s (%d headlines) | watchlist tone: %s",
                        self.market_tone['label'], self.market_tone['n'],
                        ', '.join(f"{s}:{t['label']}" for s, t in self.stock_tone.items()))
        except Exception as e:
            logger.warning(f"Market analyst start failed (non-fatal): {e}")

    def maybe_refresh(self):
        """Cheap to call every loop; does work at most every REFRESH_SECONDS."""
        if not self._started or time.time() - self._last_refresh < REFRESH_SECONDS:
            return
        self._last_refresh = time.time()
        try:
            self._market_news()
            self._timeline_point()
        except Exception as e:
            logger.debug(f"Market analyst refresh failed: {e}")

    def _nifty(self) -> Dict:
        q = self.trader.get_quote(['NIFTY 50'])
        return _quote(q, 'NSE:NIFTY 50', 'NSE:NIFTY50')

    def _timeline_point(self):
        nq = self._nifty()
        prev = (nq.get('ohlc') or {}).get('close') or 0
        ltp = nq.get('last_price') or 0
        pct = round((ltp - prev) / prev * 100, 2) if prev and ltp else None
        self.timeline.append({'time': self._clock().strftime('%H:%M'), 'nifty_pct': pct,
                              'market_tone': self.market_tone['score']})

    # ------------------------------------------------------------------ #
    # Learning hook (used by SignalEngine)
    # ------------------------------------------------------------------ #

    def adjust(self, symbol: str, signal: str) -> float:
        try:
            t = self.stock_tone.get(symbol)
            if not t:
                return 0.0
            return ma.confidence_delta(signal, t['score'], t['confidence'], self.stats)
        except Exception:
            return 0.0

    # ------------------------------------------------------------------ #
    # End of day
    # ------------------------------------------------------------------ #

    def end_day(self, trade_log: List[Dict], vix: Optional[float] = None,
                regime: Optional[str] = None, vol_ratios: Optional[Dict] = None) -> Optional[Dict]:
        """Explain the day, store observations, write the report. Returns the report."""
        try:
            if not self._started:
                return None
            day = self._clock().date().isoformat()
            vol_ratios = vol_ratios or {}

            self._timeline_point()
            nq = self._nifty()
            n_prev = (nq.get('ohlc') or {}).get('close') or 0
            nifty_pct = ((nq.get('last_price', 0) - n_prev) / n_prev * 100) if n_prev else 0.0

            quotes = self.trader.get_quote(self.symbols) if self.symbols else {}
            stocks, closes = [], {}
            for sym in self.symbols:
                q = quotes.get(f'NSE:{sym}') or {}
                ltp = q.get('last_price') or 0
                ohlc = q.get('ohlc') or {}
                prev, opn = ohlc.get('close') or 0, ohlc.get('open') or 0
                if not (ltp and prev):
                    continue
                closes[sym] = ltp
                tone = self.stock_tone.get(sym, {})
                a = ma.attribute_move(
                    sym, (ltp - prev) / prev * 100,
                    ((opn - prev) / prev * 100) if opn else 0.0,
                    ((ltp - opn) / opn * 100) if opn else 0.0,
                    nifty_pct, vol_ratios.get(sym), tone, tone.get('n', 0))
                a['headlines'] = tone.get('headlines', [])
                stocks.append(a)

            by_symbol = {s['symbol']: s for s in stocks}
            trades = []
            from src.utils.paper_report import round_trips
            for trip in round_trips(trade_log):
                sym = trip['symbol']
                tone_label = self.stock_tone.get(sym, {}).get('label', 'none')
                after = ((closes[sym] - trip['exit']) / trip['exit'] * 100
                         if sym in closes and trip['exit'] else None)
                trades.append({
                    **trip, 'entry_tone': tone_label,
                    'move_after_exit_pct': round(after, 2) if after is not None else None,
                    'notes': ma.trade_notes(trip, by_symbol.get(sym), tone_label,
                                            after, nifty_pct),
                })

            # Store (morning tone, day move) pairs. Only when the news was read early:
            # a late start means the tone may already reflect the move (hindsight).
            if self._early:
                self.history = [o for o in self.history if o.get('date') != day]
                for s in stocks:
                    t = self.stock_tone.get(s['symbol'], {})
                    self.history.append({'date': day, 'symbol': s['symbol'],
                                         'tone_score': t.get('score'),
                                         'tone_label': t.get('label', 'none'),
                                         'move_pct': s['day_pct']})
                self.stats = ma.news_stats(self.history)
                ma.save_history(self.analysis_dir, self.history)

            market = {
                'nifty_pct': round(nifty_pct, 2), 'vix': vix, 'regime': regime,
                'tone': {k: self.market_tone[k] for k in ('label', 'score', 'n')},
                'headlines': [{'title': h['title'], 'source': h.get('source', ''),
                               'score': h['score']}
                              for h in self.market_headlines[:MAX_HEADLINES_SHOWN]],
                'timeline': self.timeline,
            }
            report = ma.build_report(day, market, stocks, trades, self.stats)
            path = ma.write_report(self.analysis_dir, report)
            logger.info(f"📰 Market analysis written: {path} "
                        f"(Nifty {nifty_pct:+.2f}%, news {self.market_tone['label']})")
            return report
        except Exception as e:
            logger.warning(f"Market analysis failed (non-fatal): {e}")
            return None

    # ------------------------------------------------------------------ #
    # Live status for the status page
    # ------------------------------------------------------------------ #

    def status(self) -> Dict:
        return {
            'market_tone': {k: self.market_tone.get(k) for k in ('label', 'score', 'n')},
            'headlines': [{'title': h['title'], 'source': h.get('source', ''), 'score': h['score']}
                          for h in self.market_headlines[:MAX_HEADLINES_SHOWN]],
            'stocks': {s: {'label': t['label'], 'score': t['score'], 'n': t['n'], 'top': t.get('top')}
                       for s, t in self.stock_tone.items()},
            'timeline': self.timeline[-12:],
            'learning': self.stats,
        }
