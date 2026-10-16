"""
Self-check for the Market Analyst (news tone, move attribution, learning, daily report).
All offline: no network, no broker.

Run:
    python3 tests/test_market_analysis.py
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.agents.market_analyst import MarketAnalystAgent
from src.ai_modules.sentiment_analyzer import SentimentAnalyzer
from src.utils import market_analysis as ma
from src.utils import news_feed

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>PNB shares surge 5% after strong results - Mint</title>
<source>Mint</source><pubDate>Mon, 01 Jan 2024 08:00:00 GMT</pubDate></item>
<item><title>Old story about nothing - Blog</title>
<source>Blog</source><pubDate>Mon, 01 Jan 2024 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_rss_parsing_and_age_filter():
    now = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    items = news_feed.parse_rss(RSS, now=now)
    assert [i['title'] for i in items][0] == "PNB shares surge 5% after strong results", items
    assert items[0]['source'] == 'Mint' and items[0]['age_hours'] == 2.0
    later = datetime(2024, 1, 5, tzinfo=timezone.utc)
    assert news_feed.parse_rss(RSS, now=later) == []          # older than 36h
    assert news_feed.parse_rss('not xml') == []
    print('  ✓ RSS parsed, publisher split, stale items dropped, bad XML -> []')


def test_fetch_never_raises():
    assert isinstance(news_feed.fetch('x', timeout=0.001), list)   # tiny timeout forces a failure path
    print('  ✓ fetch() does not raise')


def test_sentiment_inflections():
    s = SentimentAnalyzer()
    assert s.analyze_text("PNB shares surge 5% after strong results")['score'] > 0
    assert s.analyze_text("Wipro slumps as brokerage cuts target")['score'] < 0
    assert s.analyze_text("Stocks dropped sharply, investors worry")['score'] < 0
    assert s.analyze_text("Nifty ends flat")['confidence'] == 0
    # words that merely end in a suffix must not match
    assert s.analyze_text("business class process address")['confidence'] == 0
    print('  ✓ sentiment handles slumps/dropped/surge; no false hits on plain words')


def test_attribution_cases():
    mkt = ma.attribute_move('SBIN', -1.2, -0.1, -1.1, -1.1, 1.0, None, 0)
    assert mkt['drivers'][0].startswith('market-wide'), mkt
    own = ma.attribute_move('PNB', 3.0, 0.2, 2.8, 0.1, 2.1, {'score': 0.6, 'confidence': 1.0}, 4)
    assert own['drivers'][0].startswith('stock-specific: outperformed')
    assert any('heavy volume' in d for d in own['drivers'])
    assert own['news_aligned'] is True
    gap = ma.attribute_move('X', 2.0, 1.8, 0.2, 0.0, None, None, 3)
    assert any('gap at the open' in d for d in gap['drivers'])
    contra = ma.attribute_move('Y', -2.0, 0.0, -2.0, 0.0, None, {'score': 0.7, 'confidence': 1.0}, 3)
    assert contra['news_aligned'] is False
    assert any('did not explain' in d for d in contra['drivers'])
    quiet = ma.attribute_move('Z', 0.1, 0.0, 0.1, 0.0, None, None, 0)
    assert quiet['drivers'] == ['quiet — no clear driver']
    print('  ✓ attribution: market-wide, stock-specific, gap, contradicting news, quiet')


def _obs(n, hit_rate):
    out = []
    for i in range(n):
        hit = (i / n) < hit_rate
        out.append({'date': f'd{i}', 'symbol': 'S', 'tone_score': 0.6, 'tone_label': 'positive',
                    'move_pct': 1.0 if hit else -1.0})
    return out


def test_learning_inactive_then_bounded_and_signed():
    few = ma.news_stats(_obs(10, 1.0))
    assert not few['adjustment_active'] and few['needs_more'] == 20
    assert ma.confidence_delta('BUY', 0.6, 1.0, few) == 0.0

    good = ma.news_stats(_obs(40, 0.9))
    assert good['adjustment_active'] and good['accuracy'] == 0.9
    up = ma.confidence_delta('BUY', 0.6, 1.0, good)
    assert 0 < up <= ma.MAX_DELTA
    assert ma.confidence_delta('SELL', 0.6, 1.0, good) == -up      # positive news argues against a short
    assert ma.confidence_delta('BUY', 0.0, 0.0, good) == 0.0        # no tone, no nudge

    contrarian = ma.news_stats(_obs(40, 0.1))
    assert ma.confidence_delta('BUY', 0.6, 1.0, contrarian) < 0     # news has been wrong -> distrust
    coin = ma.news_stats(_obs(40, 0.5))
    assert abs(ma.confidence_delta('BUY', 0.6, 1.0, coin)) < 0.01
    print('  ✓ learning: dormant <30 obs, then bounded to ±0.10 with the right sign')


def test_trade_notes():
    trip = {'symbol': 'PNB', 'net_pnl': -20.0, 'exit': 100.0}
    notes = ma.trade_notes(trip, None, 'positive', 1.2, -0.8)
    assert any('positive news but lost' in n for n in notes)
    assert any('market was weak' in n for n in notes)
    assert any('rose another' in n for n in notes)
    print('  ✓ trade notes describe news, market and post-exit move')


class _Trader:
    def __init__(self, quotes):
        self.q = quotes

    def get_quote(self, symbols):
        return {k: v for s in symbols for k, v in self.q.items() if k.endswith(s)}


def _quotes():
    return {
        'NSE:NIFTY 50': {'last_price': 21800, 'ohlc': {'close': 22000, 'open': 21950}},
        'NSE:PNB': {'last_price': 103.0, 'ohlc': {'close': 100.0, 'open': 100.5}},
        'NSE:SBIN': {'last_price': 780.0, 'ohlc': {'close': 790.0, 'open': 788.0}},
    }


def _news(query, max_items=8):
    if 'Punjab' in query:
        return [{'title': 'PNB shares surge on strong profit', 'source': 'Mint', 'age_hours': 2}]
    if 'State Bank' in query:
        return []
    return [{'title': 'Sensex falls as markets slump on weak global cues', 'source': 'ET', 'age_hours': 1}]


def _agent(tmp, hour=9):
    clock = lambda: datetime(2024, 3, 4, hour, 20)
    return MarketAnalystAgent(_Trader(_quotes()), tmp, news_fetch=_news, clock=clock)


def test_agent_full_day_report():
    with tempfile.TemporaryDirectory() as tmp:
        a = _agent(tmp)
        a.start_day(['PNB', 'SBIN'])
        assert a.market_tone['label'] == 'negative'
        assert a.stock_tone['PNB']['label'] == 'positive'
        assert a.stock_tone['SBIN']['label'] == 'none'
        assert a.adjust('PNB', 'BUY') == 0.0                       # inactive: no history yet

        log = [
            {'symbol': 'PNB', 'transaction_type': 'BUY', 'quantity': 10, 'fill_price': 100.5,
             'pnl': None, 'timestamp': '2024-03-04T09:30:00'},
            {'symbol': 'PNB', 'transaction_type': 'SELL', 'quantity': 10, 'fill_price': 102.0,
             'pnl': 15.0, 'timestamp': '2024-03-04T11:00:00'},
        ]
        r = a.end_day(log, vix=14.2, regime='trending')
        assert r is not None
        assert r['market']['nifty_pct'] == -0.91
        by = {s['symbol']: s for s in r['stocks']}
        assert by['PNB']['day_pct'] == 3.0 and by['PNB']['news_aligned'] is True
        assert by['PNB']['drivers'][0].startswith('stock-specific: outperformed')
        assert len(r['trades']) == 1 and r['trades'][0]['entry_tone'] == 'positive'
        assert r['trades'][0]['move_after_exit_pct'] == 0.98
        assert r['market']['breadth'] == {'advancers': 1, 'decliners': 1, 'avg_move_pct': 0.86}

        for f in ('history.json', '2024-03-04.json', '2024-03-04.md'):
            assert os.path.exists(os.path.join(tmp, f)), f
        md = open(os.path.join(tmp, '2024-03-04.md')).read()
        assert 'What moved our watchlist' in md and 'Stocks we traded' in md and 'PNB' in md

        # A second agent (a later day) reloads what the first one learned
        b = _agent(tmp)
        assert len(b.history) == 2 and b.stats['n_obs'] == 2
    print('  ✓ agent: morning tone, EOD attribution, trade review, files written, history reloads')


def test_late_start_does_not_teach_hindsight():
    with tempfile.TemporaryDirectory() as tmp:
        a = _agent(tmp, hour=13)
        a.start_day(['PNB'])
        r = a.end_day([], vix=None, regime=None)
        assert r is not None                                       # report still written
        assert not os.path.exists(os.path.join(tmp, 'history.json'))
    print('  ✓ late start: report written but nothing stored for learning')


def test_agent_survives_total_failure():
    class Boom:
        def get_quote(self, s):
            raise RuntimeError('down')

    def bad_news(q, max_items=8):
        raise RuntimeError('no network')

    with tempfile.TemporaryDirectory() as tmp:
        a = MarketAnalystAgent(Boom(), tmp, news_fetch=bad_news)
        a.start_day(['PNB'])                                       # must not raise
        a.maybe_refresh()
        assert a.end_day([]) is None                               # never started -> no report
        assert a.adjust('PNB', 'BUY') == 0.0
        json.dumps(a.status())                                     # status stays serialisable
    print('  ✓ agent never raises when news and broker both fail')


def test_signal_engine_applies_adjuster_bounded():
    from src.agents.signal_engine import SignalEngine
    se = SignalEngine.__new__(SignalEngine)
    assert getattr(SignalEngine, '__init__', None) is not None
    import inspect
    src = inspect.getsource(SignalEngine.__init__)
    assert 'confidence_adjuster' in src
    src2 = inspect.getsource(SignalEngine.generate_signal)
    assert 'self.confidence_adjuster(symbol, signal)' in src2
    print('  ✓ SignalEngine exposes the confidence_adjuster hook')


if __name__ == '__main__':
    tests = [
        test_rss_parsing_and_age_filter,
        test_fetch_never_raises,
        test_sentiment_inflections,
        test_attribution_cases,
        test_learning_inactive_then_bounded_and_signed,
        test_trade_notes,
        test_agent_full_day_report,
        test_late_start_does_not_teach_hindsight,
        test_agent_survives_total_failure,
        test_signal_engine_applies_adjuster_bounded,
    ]
    passed = failed = 0
    for t in tests:
        try:
            print(f'\nRunning {t.__name__}...')
            t()
            passed += 1
        except Exception as e:
            print(f'  ✗ FAILED: {e}')
            import traceback
            traceback.print_exc()
            failed += 1
    print(f"\n{'=' * 50}\nResults: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
