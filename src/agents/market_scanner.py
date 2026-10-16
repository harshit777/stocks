"""
Agent 1: MarketScanner

Responsibility: Build the tradeable watchlist for the day.

Runs ONCE at market open (9:15–9:25 AM IST).

Scoring pipeline (6 signals, all derived from market data today):

  1. volume_surge   — today's volume vs 20-day avg (are institutions active?)
  2. gap_abs        — abs(today open - yesterday close) / yesterday close
                      gap-up AND gap-down stocks move big intraday
  3. day_range_pct  — (high - low) / low so far today (momentum already present)
  4. price_momentum — (ltp - open) / open  — direction of move post-open
  5. atr_pct        — 5-day ATR / ltp  — tradeable volatility (not just noise)
  6. sentiment      — news headline score if NEWSAPI_KEY set, else 0.5 neutral

Composite score = weighted sum (weights below). Pure price/volume signals —
no fundamental data, no P/E, no analyst ratings — these don't move intraday.
"""
import logging
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

from ..ai_modules.sentiment_analyzer import SentimentAnalyzer


# Fallback if scan completely fails
_FALLBACK_SYMBOLS = [
    'TATASTEEL', 'SBIN', 'ICICIBANK', 'AXISBANK',
    'WIPRO', 'ITC', 'INFY', 'TCS', 'RELIANCE', 'HDFCBANK',
]

# Composite score weights — must sum to 1.0
_W_VOL_SURGE   = 0.30   # volume surge is the strongest "something is happening" signal
_W_GAP         = 0.20   # gap stocks have built-in momentum
_W_DAY_RANGE   = 0.20   # range already expanding = trend day, not chop day
_W_MOMENTUM    = 0.15   # direction of post-open move
_W_ATR         = 0.10   # need volatility for R/R to work
_W_SENTIMENT   = 0.05   # news is weak signal, tiebreaker only

# After volume filter, enrich only this many candidates (limits API calls)
_ENRICH_TOP_N  = 20


class MarketScanner:
    """
    Builds today's watchlist dynamically.

    Step 1 — Batch quote call: filter the full universe by price + volume.
    Step 2 — Enrich shortlist: fetch 25 daily candles per symbol to compute
             gap %, volume surge ratio, and 5-day ATR. (~20 API calls, fast.)
    Step 3 — Score & rank: composite 6-signal score.
    Step 4 — Sentiment re-rank: optional newsapi.org boost.
    """

    def __init__(
        self,
        trader,
        max_symbols: int = 10,
        min_price: float = 50.0,
        min_volume: int = 500_000,
        sentiment_boost: bool = True,
        candidate_pool: Optional[List[str]] = None,
        capital: Optional[float] = None,
        max_position_pct: float = 0.15,
        min_shares: int = 3,
        slippage: float = 0.003,
    ):
        """
        capital:          trading capital. When given, only stocks we can easily trade
                          are shortlisted: `min_shares` shares must fit inside
                          capital * max_position_pct (same cap RiskGate enforces).
                          None disables the filter.
        max_position_pct: per-stock cap, keep equal to RiskGate.max_position_pct
        min_shares:       smallest position worth taking; 1 share makes P&L chunky
                          and leaves no room to size by risk
        slippage:         RiskGate pays limit = ltp * (1 + slippage)
        """
        self.trader          = trader
        self.max_symbols     = max_symbols
        self.min_price       = min_price
        self.min_volume      = min_volume
        self.max_price: Optional[float] = (
            capital * max_position_pct / (min_shares * (1 + slippage))
            if capital else None
        )
        self.sentiment_boost = sentiment_boost
        self.sentiment_analyzer = SentimentAnalyzer()
        self.logger = logging.getLogger(__name__)
        self.candidate_pool = candidate_pool or _DEFAULT_CANDIDATE_POOL
        self._last_scan: List[str] = []
        self._last_scan_time: Optional[datetime] = None
        self._last_scores: List[Dict] = []   # for dashboard introspection

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> List[str]:
        """
        Run the full scan and return an ordered watchlist for today.
        Falls back to _FALLBACK_SYMBOLS on any API failure.
        """
        # Inject today's NSE bulk/block deal symbols — institutional moves
        self._inject_bulk_deal_symbols()

        self.logger.info(
            f"MarketScanner: scanning {len(self.candidate_pool)} candidates..."
        )
        try:
            shortlist = self._initial_filter()
        except Exception as e:
            self.logger.error(f"MarketScanner initial filter failed: {e}. Using fallback.")
            return self._use_fallback()

        if not shortlist:
            self.logger.warning("No symbols passed initial filter. Using fallback.")
            return self._use_fallback()

        try:
            scored = self._enrich_and_score(shortlist)
        except Exception as e:
            self.logger.error(f"MarketScanner enrich failed: {e}. Using volume-only ranking.")
            scored = shortlist  # already sorted by volume

        if self.sentiment_boost:
            try:
                scored = self._apply_sentiment(scored)
            except Exception as e:
                self.logger.debug(f"Sentiment boost failed (non-fatal): {e}")

        result = [c['symbol'] for c in scored[:self.max_symbols]]
        self._last_scan      = result
        self._last_scan_time = datetime.now()
        self._last_scores    = scored[:self.max_symbols]

        for c in self._last_scores:
            self.logger.info(
                f"  {c['symbol']:12s}  score={c.get('composite_score', 0):.3f}"
                f"  vol_surge={c.get('vol_surge', 0):.1f}x"
                f"  gap={c.get('gap_pct', 0)*100:+.2f}%"
                f"  range={c.get('day_range_pct', 0)*100:.2f}%"
                f"  mom={c.get('price_momentum', 0)*100:+.2f}%"
            )
        self.logger.info(
            f"MarketScanner: selected {len(result)}: {', '.join(result)}"
        )
        return result

    def get_last_scan(self) -> List[str]:
        return self._last_scan or _FALLBACK_SYMBOLS[:self.max_symbols]

    def get_last_scores(self) -> List[Dict]:
        """Return the scored candidates from the last scan (for dashboard)."""
        return self._last_scores

    def market_conditions(self) -> Dict:
        """
        Read today's market regime and India VIX at startup.

        Returns a dict used by the startup sequence to scale RiskGate params:
          {
            'regime':        'trending' | 'choppy' | 'unknown',
            'skip_day':      bool,   True if Nifty 30-min range < 0.4% → high chop risk
            'vix':           float,  India VIX (or None if unavailable)
            'stop_loss_mult':float,  1.0 normal, 1.5 if VIX > 20
            'size_mult':     float,  1.0 normal, 0.7 if VIX > 20 or choppy
            'nifty_range_pct':float, Nifty first-30-min H-L range as % of open
          }

        Called at 9:45 AM (after 30 min of Nifty trading).
        ponytail: NSE VIX symbol is 'INDIA VIX' on NSE — may need token lookup;
                  falls back gracefully to neutral if quote fails.
        """
        result = {
            'regime': 'unknown', 'skip_day': False,
            'vix': None, 'stop_loss_mult': 1.0, 'size_mult': 1.0,
            'nifty_range_pct': 0.0,
        }
        try:
            # ── Nifty opening range (regime detection) ──
            # Quote Nifty 50 index — NSE symbol is 'NIFTY 50'
            nifty_q = self.trader.get_quote(['NIFTY 50'])
            nq = nifty_q.get('NSE:NIFTY 50') or nifty_q.get('NSE:NIFTY50') or {}
            if nq:
                ohlc  = nq.get('ohlc', {})
                n_open = ohlc.get('open', 0)
                n_high = nq.get('ohlc', {}).get('high', n_open)
                n_low  = nq.get('ohlc', {}).get('low',  n_open)
                if n_open > 0:
                    range_pct = (n_high - n_low) / n_open
                    result['nifty_range_pct'] = round(range_pct, 4)
                    if range_pct < 0.004:   # < 0.4% → choppy day
                        result['regime']    = 'choppy'
                        result['skip_day']  = True
                        result['size_mult'] = 0.5   # halve size on choppy days
                        self.logger.warning(
                            f"⚠️  Nifty 30-min range {range_pct:.2%} < 0.4% → CHOPPY DAY. "
                            f"Position sizes halved."
                        )
                    else:
                        result['regime'] = 'trending'
                        self.logger.info(
                            f"✓ Nifty range {range_pct:.2%} → trending day"
                        )
        except Exception as e:
            self.logger.debug(f"Nifty regime check failed (non-fatal): {e}")

        try:
            # ── India VIX ──
            vix_q = self.trader.get_quote(['INDIA VIX'])
            vq = vix_q.get('NSE:INDIA VIX') or {}
            vix = vq.get('last_price', 0)
            if vix > 0:
                result['vix'] = round(vix, 2)
                if vix > 20:
                    result['stop_loss_mult'] = 1.5   # wider stops needed in high-fear
                    result['size_mult']      = min(result['size_mult'], 0.7)
                    self.logger.warning(
                        f"⚠️  India VIX={vix:.1f} > 20 → stop_loss ×1.5, size ×0.7"
                    )
                else:
                    self.logger.info(f"✓ India VIX={vix:.1f} (normal)")
        except Exception as e:
            self.logger.debug(f"VIX fetch failed (non-fatal): {e}")

        return result

    # ------------------------------------------------------------------
    # Bulk/block deal injection
    # ------------------------------------------------------------------

    def _inject_bulk_deal_symbols(self):
        """
        Fetch today's NSE bulk and block deal symbols and add any not already
        in the candidate pool. These are the stocks institutions are moving
        TODAY — highest-quality intraday candidates.

        NSE public API — no auth required, but subject to rate limits/changes.
        ponytail: NSE may change this endpoint; if it fails we log and continue.
        """
        import urllib.request, json as _json
        urls = [
            'https://www.nseindia.com/api/block-deal',
            'https://www.nseindia.com/api/bulk-deal',
        ]
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
            'Referer': 'https://www.nseindia.com/',
        }
        new_symbols = []
        for url in urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as r:
                    data = _json.loads(r.read())
                for item in data.get('data', []):
                    sym = item.get('symbol') or item.get('Symbol') or item.get('scrips', '')
                    sym = sym.strip().upper()
                    if sym and sym not in self.candidate_pool:
                        new_symbols.append(sym)
                        self.candidate_pool.append(sym)
            except Exception as e:
                self.logger.debug(f"Bulk/block deal fetch failed (non-fatal): {e}")

        if new_symbols:
            self.logger.info(
                f"MarketScanner: injected {len(new_symbols)} bulk/block deal symbols: "
                f"{', '.join(new_symbols[:10])}"
            )

    # ------------------------------------------------------------------
    # Step 1 — batch quote, filter by price + volume
    # ------------------------------------------------------------------

    def _initial_filter(self) -> List[Dict]:
        """
        One batch quote call → filter → sort by raw volume.
        Returns top _ENRICH_TOP_N candidates.
        """
        quotes = self.trader.get_quote(self.candidate_pool)
        if not quotes:
            return []

        candidates = []
        too_expensive = []
        for symbol in self.candidate_pool:
            q = quotes.get(f"NSE:{symbol}")
            if not q:
                continue
            ltp    = q.get('last_price', 0)
            volume = q.get('volume', 0)
            if ltp < self.min_price or volume < self.min_volume:
                continue
            if self.max_price is not None and ltp > self.max_price:
                too_expensive.append(symbol)
                continue

            ohlc = q.get('ohlc', {})
            candidates.append({
                'symbol':         symbol,
                'ltp':            ltp,
                'volume':         volume,
                'open_today':     ohlc.get('open', ltp),
                'high_today':     ohlc.get('high', ltp),
                'low_today':      ohlc.get('low',  ltp),
                'prev_close':     ohlc.get('close', ltp),  # Kite: ohlc.close = prev close
                # enriched fields — filled in step 2
                'avg_volume_20d': 0.0,
                'atr5':           0.0,
                'vol_surge':      1.0,
                'gap_pct':        0.0,
                'day_range_pct':  0.0,
                'price_momentum': 0.0,
                'composite_score': 0.0,
                'sentiment_score': 0.5,
            })

        if too_expensive:
            self.logger.info(
                f"MarketScanner: skipped {len(too_expensive)} stocks above "
                f"₹{self.max_price:,.0f} (too expensive for our capital): "
                f"{', '.join(too_expensive)}"
            )
        candidates.sort(key=lambda x: x['volume'], reverse=True)
        return candidates[:_ENRICH_TOP_N]

    # ------------------------------------------------------------------
    # Step 2 — enrich: daily candles → gap, vol surge, ATR
    # ------------------------------------------------------------------

    def _enrich_and_score(self, candidates: List[Dict]) -> List[Dict]:
        """
        For each candidate fetch 25 daily candles → compute enrichment signals.
        Then score and sort.
        """
        to_date   = datetime.now()
        from_date = to_date - timedelta(days=35)   # ~25 trading days

        for c in candidates:
            symbol = c['symbol']
            try:
                candles = self.trader.get_historical_data(
                    symbol=symbol,
                    from_date=from_date,
                    to_date=to_date,
                    interval='day',
                )
                if candles and len(candles) >= 2:
                    closes  = [float(x.get('close',  0)) for x in candles]
                    volumes = [float(x.get('volume', 0)) for x in candles]
                    highs   = [float(x.get('high',   0)) for x in candles]
                    lows    = [float(x.get('low',    0)) for x in candles]

                    # Yesterday's close (last completed day)
                    prev_close = closes[-1] if closes else c['prev_close']
                    c['prev_close'] = prev_close

                    # 20-day avg volume (exclude today — candles[-1] is yesterday)
                    avg_vol = sum(volumes[-20:]) / max(len(volumes[-20:]), 1)
                    c['avg_volume_20d'] = avg_vol
                    c['vol_surge'] = (c['volume'] / avg_vol) if avg_vol > 0 else 1.0

                    # 5-day ATR
                    tr_vals = []
                    for i in range(max(0, len(candles) - 5), len(candles)):
                        h = highs[i]; l = lows[i]; pc = closes[i - 1] if i > 0 else closes[i]
                        tr_vals.append(max(h - l, abs(h - pc), abs(l - pc)))
                    c['atr5'] = sum(tr_vals) / len(tr_vals) if tr_vals else 0.0

            except Exception as e:
                self.logger.debug(f"Enrich failed for {symbol}: {e}")

            # Compute intraday signals from today's quote data
            prev   = c['prev_close']
            open_  = c['open_today']
            high   = c['high_today']
            low    = c['low_today']
            ltp    = c['ltp']

            safe_prev  = prev  if prev  > 0 else ltp
            safe_low   = low   if low   > 0 else ltp
            safe_open  = open_ if open_ > 0 else ltp
            safe_ltp   = ltp   if ltp   > 0 else 1.0

            c['gap_pct']        = (open_ - safe_prev)  / safe_prev   # + = gap-up, - = gap-down
            c['day_range_pct']  = (high  - safe_low)   / safe_low    # range expanded so far
            c['price_momentum'] = (ltp   - safe_open)  / safe_open   # direction post-open
            c['atr_pct']        = c['atr5'] / safe_ltp               # normalised volatility

        # Score
        for c in candidates:
            # vol_surge: cap at 5x to avoid single outlier dominating
            vol_norm  = min(c['vol_surge'], 5.0) / 5.0
            # gap: abs gap — both gap-up and gap-down stocks move
            gap_norm  = min(abs(c['gap_pct']), 0.05) / 0.05           # cap at 5%
            # range: cap at 3%
            range_norm = min(c['day_range_pct'], 0.03) / 0.03
            # momentum: abs (we don't care direction here, RiskGate filters that)
            mom_norm  = min(abs(c['price_momentum']), 0.02) / 0.02    # cap at 2%
            # ATR: cap at 2%
            atr_norm  = min(c['atr_pct'], 0.02) / 0.02
            # sentiment already 0–1
            sent_norm = c['sentiment_score']

            c['composite_score'] = (
                _W_VOL_SURGE * vol_norm  +
                _W_GAP       * gap_norm  +
                _W_DAY_RANGE * range_norm +
                _W_MOMENTUM  * mom_norm  +
                _W_ATR       * atr_norm  +
                _W_SENTIMENT * sent_norm
            )

        candidates.sort(key=lambda x: x['composite_score'], reverse=True)
        return candidates

    # ------------------------------------------------------------------
    # Step 3 — optional news sentiment re-rank
    # ------------------------------------------------------------------

    def _apply_sentiment(self, candidates: List[Dict]) -> List[Dict]:
        """Fetch headlines for each candidate and fold score into composite."""
        newsapi_key = os.getenv('NEWSAPI_KEY')
        for c in candidates:
            if newsapi_key:
                headlines = self._fetch_headlines(c['symbol'], newsapi_key)
                result    = self.sentiment_analyzer.analyze_news_headlines(
                    headlines, c['symbol']
                )
                c['sentiment_score'] = (result.get('score', 0.0) + 1.0) / 2.0
            else:
                c['sentiment_score'] = 0.5

            # Re-compute composite with updated sentiment (small weight, minor re-rank)
            c['composite_score'] += _W_SENTIMENT * (c['sentiment_score'] - 0.5)

        candidates.sort(key=lambda x: x['composite_score'], reverse=True)
        return candidates

    def _fetch_headlines(self, symbol: str, api_key: str) -> List[str]:
        """Fetch top 5 headlines from newsapi.org."""
        try:
            import urllib.request, json as _json
            url = (
                f"https://newsapi.org/v2/everything"
                f"?q={symbol}+NSE&language=en&pageSize=5&sortBy=publishedAt"
                f"&apiKey={api_key}"
            )
            with urllib.request.urlopen(url, timeout=3) as r:
                data = _json.loads(r.read())
            return [a.get('title', '') for a in data.get('articles', [])]
        except Exception as e:
            self.logger.debug(f"News fetch failed for {symbol}: {e}")
            return []

    def _use_fallback(self) -> List[str]:
        self._last_scan = _FALLBACK_SYMBOLS[:self.max_symbols]
        return self._last_scan


# ------------------------------------------------------------------
# Default candidate pool — Nifty 50 + high-volume mid-caps
# ponytail: static list; upgrade path = kite.instruments() filtered by
#           market_cap > 5000Cr + avg_volume_30d > 1M (requires instruments dump)
# ------------------------------------------------------------------
_DEFAULT_CANDIDATE_POOL = [
    # Nifty 50
    'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
    'HINDUNILVR', 'SBIN', 'BHARTIARTL', 'KOTAKBANK', 'LT',
    'AXISBANK', 'ASIANPAINT', 'MARUTI', 'TITAN', 'BAJFINANCE',
    'WIPRO', 'ULTRACEMCO', 'ONGC', 'NTPC', 'POWERGRID',
    'SUNPHARMA', 'TATAMOTORS', 'TATASTEEL', 'INDUSINDBK', 'TECHM',
    'HCLTECH', 'ADANIENT', 'ADANIPORTS', 'ITC', 'JSWSTEEL',
    'GRASIM', 'BPCL', 'DRREDDY', 'EICHERMOT', 'HEROMOTOCO',
    'BRITANNIA', 'CIPLA', 'DIVISLAB', 'NESTLEIND', 'APOLLOHOSP',
    'TATACONSUM', 'BAJAJFINSV', 'HINDALCO', 'COALINDIA', 'M&M',
    'SBILIFE', 'HDFCLIFE', 'UPL', 'SHREECEM', 'PIDILITIND',
    # High-volume mid-caps with strong intraday moves
    'YESBANK', 'PNB', 'BANKBARODA', 'SAIL', 'IRCTC',
    'ZOMATO', 'NYKAA', 'POLICYBZR', 'DMART', 'TRENT',
    'ABFRL', 'MUTHOOTFIN', 'CHOLAFIN', 'LTIM', 'PERSISTENT',
    'ASTRAL', 'DEEPAKNTR', 'CANBK', 'FEDERALBNK', 'IDFCFIRSTB',
]
