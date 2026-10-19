"""
Self-check for paper mode.

  - PaperBroker never reaches the real order API and hides the raw Kite client
  - Daily report: round trips, gross vs net win rate, completed-day counting
  - live_trade_v2 refuses to run live without LIVE_TRADING_APPROVED=yes

Run:
    python3 tests/test_paper_mode.py
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.kite_trader.paper_broker import PaperBroker
from src.utils import paper_report


def _candle(i: int) -> dict:
    base = 100 + i * 0.1 + (i % 7) * 0.3
    return {'open': base, 'high': base + 1.5, 'low': base - 1.0,
            'close': base + (0.4 if i % 2 else -0.4), 'volume': 100_000 + i * 700}


class _FakeKite:
    def __init__(self):
        self.real_orders = 0

    def place_order(self, **kw):
        self.real_orders += 1
        return 'REAL'


class _FakeTrader:
    def __init__(self):
        self.kite = _FakeKite()
        self.order_manager = object()
        self.api_key = 'k'

    def get_ltp(self, symbols):
        return {f'NSE:{s}': 100.0 for s in symbols}

    def get_quote(self, symbols):
        return {f'NSE:{s}': {'last_price': 100.0} for s in symbols}


def test_paper_broker_never_places_real_orders():
    t = _FakeTrader()
    pb = PaperBroker(t, fill_wait=0)
    oid = pb.place_order('SBIN', 'BUY', 10, price=100.5)
    assert oid and oid.startswith('PAPER-')
    assert t.kite.real_orders == 0
    assert pb.get_positions()['net'][0]['quantity'] == 10
    pb.place_order('SBIN', 'SELL', 10, price=99.0)          # marketable sell limit
    assert pb.get_positions()['net'] == []
    assert t.kite.real_orders == 0
    print('  ✓ orders simulated, real API untouched')


def test_paper_broker_hides_raw_client():
    pb = PaperBroker(_FakeTrader())
    for name in ('kite', 'order_manager'):
        try:
            getattr(pb, name)
        except AttributeError:
            continue
        raise AssertionError(f'{name} must not be reachable through PaperBroker')
    assert pb.get_quote(['SBIN'])['NSE:SBIN']['last_price'] == 100.0   # data still works
    assert pb.api_key == 'k'
    print('  ✓ kite/order_manager blocked, market data delegated')


def test_daily_report_math():
    log = [
        {'timestamp': 't1', 'symbol': 'A', 'transaction_type': 'BUY',  'quantity': 10, 'fill_price': 100.0, 'pnl': None},
        {'timestamp': 't2', 'symbol': 'A', 'transaction_type': 'SELL', 'quantity': 10, 'fill_price': 110.0, 'pnl': 100.0},   # big win
        {'timestamp': 't3', 'symbol': 'B', 'transaction_type': 'BUY',  'quantity': 10, 'fill_price': 100.0, 'pnl': None},
        {'timestamp': 't4', 'symbol': 'B', 'transaction_type': 'SELL', 'quantity': 10, 'fill_price': 100.01, 'pnl': 0.1},    # gross win, net loss
        {'timestamp': 't5', 'symbol': 'C', 'transaction_type': 'BUY',  'quantity': 10, 'fill_price': 100.0, 'pnl': None},
        {'timestamp': 't6', 'symbol': 'C', 'transaction_type': 'SELL', 'quantity': 10, 'fill_price': 95.0, 'pnl': -50.0},     # loss
    ]
    r = paper_report.build_daily_report(
        '2026-01-05', log, {'buy_signals': 3}, {'Target reached': 1}, 10000.0, 50.0,
        'paper', True, 'square-off reached', 0)
    assert r['closed_trades'] == 3
    assert r['wins_gross'] == 2 and r['wins_net'] == 1
    assert r['win_rate_gross_pct'] == 66.7 and r['win_rate_net_pct'] == 33.3
    assert r['net_pnl'] < r['gross_pnl']                      # costs are subtracted
    assert 'Win rate (after costs): 33.3%' in paper_report.render_daily_md(r)
    print('  ✓ gross 66.7% vs net 33.3%, costs deducted')


def test_empty_day_is_na_not_zero():
    r = paper_report.build_daily_report('2026-01-06', [], {}, {}, 10000.0, 0.0,
                                        'paper', True, 'square-off reached', 0)
    assert r['closed_trades'] == 0 and r['win_rate_gross_pct'] is None
    assert 'n/a' in paper_report.render_daily_md(r)
    print('  ✓ no trades -> win rate n/a')


def test_completed_day_counting_and_idempotence():
    with tempfile.TemporaryDirectory() as d:
        def rep(day, complete):
            return paper_report.build_daily_report(day, [], {}, {}, 1.0, 0.0, 'paper', complete, 'x', 0)
        paper_report.write_daily_report(rep('2026-01-05', True), d)
        paper_report.write_daily_report(rep('2026-01-06', False), d)   # incomplete: not counted
        paper_report.write_daily_report(rep('2026-01-07', True), d)
        paper_report.write_daily_report(rep('2026-01-07', True), d)    # same day again: overwritten, not double counted
        assert paper_report.completed_days(d) == 2
        assert paper_report.todays_report_complete(d, '2026-01-07')
        assert not paper_report.todays_report_complete(d, '2026-01-06')
        assert 'day 2 of 10' in open(os.path.join(d, 'SUMMARY.md')).read()
    print('  ✓ only complete days count, reruns do not double count')


def test_live_requires_approval():
    env = {k: v for k, v in os.environ.items() if k != 'LIVE_TRADING_APPROVED'}
    env['TRADING_MODE'] = 'live'
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'live_trade_v2.py')],
                       env=env, cwd=tempfile.mkdtemp(), capture_output=True, text=True, timeout=60)
    assert p.returncode == 2, (p.returncode, p.stderr[-300:])
    assert 'NOT approved' in (p.stdout + p.stderr)
    print('  ✓ live mode exits 2 without LIVE_TRADING_APPROVED=yes')


def test_unknown_mode_falls_back_to_paper():
    env = dict(os.environ, TRADING_MODE='LIVE ')   # typo / wrong case must never mean live
    code = ("import sys; sys.argv=['x']; sys.path.insert(0, %r);"
            "import importlib.util as u;"
            "s=u.spec_from_file_location('v2', %r); m=u.module_from_spec(s); s.loader.exec_module(m);"
            "print(m.MODE)") % (ROOT, os.path.join(ROOT, 'scripts', 'live_trade_v2.py'))
    p = subprocess.run([sys.executable, '-c', code], env=env, cwd=tempfile.mkdtemp(),
                       capture_output=True, text=True, timeout=60)
    assert p.stdout.strip().splitlines()[-1] == 'paper', (p.stdout, p.stderr[-300:])
    print("  ✓ TRADING_MODE='LIVE ' is treated as paper")


def _engine_with_spy():
    """SignalEngine with a recording OnlineModel; no network, no disk writes."""
    from src.agents.signal_engine import SignalEngine
    from src.ml.feature_engine import FeatureEngine

    class _Spy:
        n_updates = 1
        is_mature = False
        def __init__(self): self.calls = []
        def update(self, vec, label, weight=1.0): self.calls.append((vec.copy(), label))
        def save(self): pass

    se = SignalEngine(trader=_FakeTrader(), symbols=['A'])
    se._online_model = _Spy()
    fe = FeatureEngine()
    for i in range(80):
        fe.update(_candle(i))
    se._feature_engines['A'] = fe
    return se, fe


def test_online_model_learns_from_entry_features_and_net_label():
    se, fe = _engine_with_spy()
    entry_vec = fe.latest_vector().copy()
    se.record_entry('A', 100.0)
    for i in range(80, 90):                      # market moves on before the exit
        fe.update(_candle(i * 3))
    assert not np.allclose(fe.latest_vector(), entry_vec)

    # +0.01/share gross on 10 shares = +0.10, smaller than round-trip costs -> label 0
    se.record_trade_outcome('A', 'SELL', 100.01, 10, pnl=0.10)
    vec, label = se._online_model.calls[-1]
    assert np.allclose(vec, entry_vec), 'must train on entry features, not exit features'
    assert label == 0, 'tiny gross win that costs wipe out must be a loss'

    se.record_entry('A', 100.0)
    se.record_trade_outcome('A', 'SELL', 110.0, 10, pnl=100.0)
    assert se._online_model.calls[-1][1] == 1
    print('  ✓ trains on entry features; label is profit after costs')


def test_online_model_skips_positions_it_did_not_open():
    se, _ = _engine_with_spy()
    se.record_trade_outcome('A', 'SELL', 105.0, 10, pnl=50.0)    # no record_entry
    assert se._online_model.calls == []
    se.record_entry('A', 100.0)
    se.record_trade_outcome('A', 'SELL', 101.0, 10, pnl=10.0)
    se.record_trade_outcome('A', 'SELL', 101.0, 10, pnl=10.0)    # duplicate close: entry already consumed
    assert len(se._online_model.calls) == 1
    print('  ✓ untracked / duplicate closes are ignored')


def test_post_trade_agent_snapshots_entry_on_buy():
    from src.agents.post_trade_agent import PostTradeAgent
    seen = []

    class _SE:
        def record_entry(self, symbol, price): seen.append((symbol, price))
        def record_trade_outcome(self, **kw): pass

    with tempfile.TemporaryDirectory() as d:
        pta = PostTradeAgent(capital_manager=None, signal_engine=_SE(), data_dir=d)
        pta.start_day(1000.0)
        pta.on_fill('A', 'BUY', 5, 100.0, None)
        pta.on_fill('A', 'SELL', 5, 101.0, 5.0)
    assert seen == [('A', 100.0)]
    print('  ✓ BUY fill triggers the entry snapshot, SELL does not')


def test_scanner_skips_stocks_too_expensive_for_capital():
    from src.agents.market_scanner import MarketScanner

    prices = {'PNB': 105.0, 'WIPRO': 250.0, 'ITC': 450.0, 'SBIN': 800.0, 'INFY': 1500.0, 'TCS': 3500.0}

    class _T:
        def get_quote(self, syms):
            return {f'NSE:{s}': {'last_price': p, 'volume': 5_000_000,
                                 'ohlc': {'open': p, 'high': p, 'low': p, 'close': p}}
                    for s, p in prices.items() if s in syms}

    pool = list(prices)
    capped = MarketScanner(_T(), candidate_pool=pool, capital=10000, max_position_pct=0.15, min_shares=3)
    got = {c['symbol'] for c in capped._initial_filter()}
    # 10000 * 15% / (3 * 1.003) = ~498.5 per share
    assert 498 < capped.max_price < 499, capped.max_price
    assert got == {'PNB', 'WIPRO', 'ITC'}, got

    # every stock it keeps must actually pass the RiskGate sizing with >= 3 shares
    from src.agents.risk_gate import RiskGate
    for s in got:
        g = RiskGate(max_capital=10000, max_daily_loss=1000, max_position_pct=0.15, max_concurrent_positions=4,
                     stop_loss_pct=0.015, target_pct=0.025, min_risk_reward=1.5, risk_per_trade_pct=0.01)
        g.reset_daily(10000)
        d = g.evaluate(s, 'BUY', prices[s], prices[s] * 1.03, prices[s] * 0.98)
        assert d.approved and d.quantity >= 3, (s, d)

    off = MarketScanner(_T(), candidate_pool=pool)           # no capital -> filter disabled
    assert {c['symbol'] for c in off._initial_filter()} == set(pool)
    print('  ✓ scanner keeps only stocks where >= 3 shares fit the per-stock cap')


def test_paper_gates_can_approve_a_trade_and_live_stays_strict():
    """Exit rules are +2.5% / -1.5% (best 1.67:1). A 3:1 RiskGate minimum rejects everything."""
    from src.agents.risk_gate import RiskGate

    def gate(rr):
        g = RiskGate(max_capital=10000, max_daily_loss=1000, max_position_pct=0.15,
                     max_concurrent_positions=4, stop_loss_pct=0.015, target_pct=0.025,
                     min_risk_reward=rr, risk_per_trade_pct=0.01)
        g.reset_daily(10000)
        return g

    code = lambda mode: ("import sys,importlib.util as u;sys.path.insert(0,%r);"
                         "s=u.spec_from_file_location('v2',%r);m=u.module_from_spec(s);s.loader.exec_module(m);"
                         "print(m.MIN_RISK_REWARD, m.SIGNAL_RISK_REWARD, m.SIGNAL_MIN_PROFIT_MARGIN)"
                         ) % (ROOT, os.path.join(ROOT, 'scripts', 'live_trade_v2.py'))
    out = {}
    for mode in ('paper', 'live'):
        p = subprocess.run([sys.executable, '-c', code(mode)], env=dict(os.environ, TRADING_MODE=mode),
                           cwd=tempfile.mkdtemp(), capture_output=True, text=True, timeout=60)
        out[mode] = [float(x) for x in p.stdout.strip().splitlines()[-1].split()]
    assert out['live'] == [3.0, 3.0, 0.02], out
    assert out['paper'][0] <= 1.5

    ok = gate(out['paper'][0]).evaluate('PNB', 'BUY', 105.0, 108.0, 102.0)
    assert ok.approved and ok.quantity >= 1, ok
    assert not gate(3.0).evaluate('PNB', 'BUY', 105.0, 108.0, 102.0).approved
    print('  ✓ paper gates approve a normal trade; live keeps 3:1 / 2%')


def test_broker_health_check_works_through_paper_broker():
    """BrokerHealthMonitor probes get_profile(); KiteTrader must have it and PaperBroker must forward it."""
    from src.kite_trader.trader import KiteTrader
    from src.utils.broker_health import BrokerHealthMonitor

    assert hasattr(KiteTrader, 'get_profile')

    class _Kite:
        def profile(self): return {'user_id': 'AB1234'}

    real = KiteTrader.__new__(KiteTrader)      # skip network/credential setup
    real.kite = _Kite()
    health = BrokerHealthMonitor(PaperBroker(real), check_interval=0, failure_threshold=3).check_health()
    assert health['is_healthy'] and not health['should_halt'], health
    print('  ✓ health check passes through PaperBroker -> KiteTrader.get_profile')


def test_status_json_has_dashboard_fields():
    """status.json carries everything docs/status/index.html renders."""
    code = r'''
import sys, json, datetime, importlib.util as u
sys.path.insert(0, %r)
s = u.spec_from_file_location('v2', %r); m = u.module_from_spec(s); s.loader.exec_module(m)
from src.agents.execution_agent import Position

class Exec:
    def all_positions(self):
        return {'AAA': Position('AAA', 5, 100.0, 98.5)}
class Trader:
    def get_quote(self, syms): return {'NSE:AAA': {'last_price': 102.0}}
class Risk:
    def status(self): return {'available_capital': 500.0, 'used_capital': 500.0, 'halted': False}
class Post:
    def intraday_status(self):
        return {'daily_pnl': 12.5, 'daily_trades': 1, 'daily_wins': 1, 'daily_losses': 0, 'win_rate': 100.0}
class Scanner:
    def get_last_scores(self):
        return [{'symbol': 'AAA', 'composite_score': 0.61234567, 'vol_surge': 2.0, 'gap_pct': 0.01,
                 'day_range_pct': 0.02, 'secret_internal': 1}]
class Eng:
    def get_ml_status(self): return {'online_updates': 7}

import logging
logging.getLogger('t').warning('careful')
m._write_status('running', 3, Risk(), Post(), Exec(), Trader(), {'AAA': 'BUY', 'BBB': None},
                ['AAA', 'BBB'], Scanner(), Eng())
d = json.load(open('data/status.json'))
p = d['positions'][0]
assert p['current_price'] == 102.0 and p['unrealised_pnl'] == 10.0 and p['pnl_pct'] == 2.0, p
assert {'qty', 'avg_price', 'stop_price', 'entry_time'} <= set(p), p
assert d['watchlist_scores'][0]['composite_score'] == 0.6123 and 'secret_internal' not in d['watchlist_scores'][0]
assert d['pnl_history'][-1]['pnl'] == 12.5, d['pnl_history']
assert d['signals'] == {'AAA': 'BUY'}
assert d['ml']['online_updates'] == 7
assert any(l['level'] == 'WARN' and l['message'] == 'careful' for l in d['log']), d['log']
print('ok')
''' % (ROOT, os.path.join(ROOT, 'scripts', 'live_trade_v2.py'))
    p = subprocess.run([sys.executable, '-c', code], cwd=tempfile.mkdtemp(),
                       capture_output=True, text=True, timeout=60)
    assert p.stdout.strip().endswith('ok'), (p.stdout[-300:], p.stderr[-600:])
    print('  ✓ status.json has positions, scores, P&L history, ML block and structured log')


def test_market_calendar_knows_2026_nse_holidays():
    from datetime import date
    from src.utils.market_calendar import MarketCalendar
    cal = MarketCalendar()
    assert not cal.is_trading_day(date(2026, 10, 20)), "Dussehra"
    assert not cal.is_trading_day(date(2026, 11, 10)), "Diwali-Balipratipada"
    assert not cal.is_trading_day(date(2026, 12, 25)), "Christmas"
    assert cal.is_trading_day(date(2026, 10, 19)) and cal.is_trading_day(date(2026, 10, 21))
    assert not cal.is_trading_day(date(2026, 10, 17)), "Saturday"
    assert cal.next_trading_day(date(2026, 10, 19)) == date(2026, 10, 21)   # skips Dussehra
    print('  \u2713 2026 holidays recognised; Dussehra skipped, neighbours trade')


def test_paper_capital_compounds_net_of_costs_and_live_stays_capped():
    from datetime import date
    from src.utils.capital_manager import CapitalRecoveryManager

    def day(mgr_dir, growth, pnl, d):
        m = CapitalRecoveryManager(10_000, data_dir=mgr_dir, allow_growth=growth)
        start = m.get_available_capital()
        m.history['daily_records'] = [r for r in m.history['daily_records'] if r['date'] != d]
        # simulate "today" being `d` by writing the record the way record_day_end does
        m.history['daily_records'].append({'date': d, 'starting_capital': start,
                                           'ending_capital': max(0, start + pnl), 'daily_pnl': pnl})
        m._save_history()
        return start, CapitalRecoveryManager(10_000, data_dir=mgr_dir, allow_growth=growth).get_available_capital()

    with tempfile.TemporaryDirectory() as d:        # paper: wins add, losses cut, compounding
        s1, nxt = day(d, True, +200.0, '2000-01-01'); assert (s1, nxt) == (10_000, 10_200), (s1, nxt)
        s2, nxt = day(d, True, -500.0, '2000-01-02'); assert (s2, nxt) == (10_200, 9_700), (s2, nxt)
        s3, nxt = day(d, True, +1_000.0, '2000-01-03'); assert (s3, nxt) == (9_700, 10_700), (s3, nxt)
    with tempfile.TemporaryDirectory() as d:        # live: profit never raises the budget above the cap
        s1, nxt = day(d, False, +200.0, '2000-01-01'); assert nxt == 10_000, nxt
        s2, nxt = day(d, False, -500.0, '2000-01-02'); assert nxt == 9_500, nxt
    print('  \u2713 paper compounds (+200, -500, +1000 -> 10,700); live is capped at the starting budget')


def test_day_end_books_net_pnl_after_charges():
    from src.agents.post_trade_agent import PostTradeAgent
    from src.utils.capital_manager import CapitalRecoveryManager

    class _SE:
        def record_entry(self, *a): pass
        def record_trade_outcome(self, **kw): pass
        def save_models(self): pass

    with tempfile.TemporaryDirectory() as d:
        cm = CapitalRecoveryManager(10_000, data_dir=d + '/cap', allow_growth=True)
        pta = PostTradeAgent(capital_manager=cm, signal_engine=_SE(), data_dir=d)
        pta.start_day(10_000.0)
        pta.on_fill('PNB', 'BUY', 10, 100.0, None)
        pta.on_fill('PNB', 'SELL', 10, 102.0, 20.0)         # gross +20
        pta.end_day()
        rec = cm.history['daily_records'][-1]
        costs = paper_report.round_trips(pta.trade_log)[0]['costs']
        assert 0 < costs < 20
        assert abs(rec['daily_pnl'] - (20.0 - costs)) < 0.01, rec
        assert abs(rec['ending_capital'] - (10_000 + 20.0 - costs)) < 0.01
    print(f'  \u2713 day end books net P&L (gross 20.00 - charges {costs:.2f}), not gross')


class _Book:
    """Quote source whose price and order book we control."""
    def __init__(self, ltp, asks=None, bids=None):
        self.kite = _FakeKite(); self.order_manager = object(); self.api_key = 'k'
        self.ltp, self.asks, self.bids = ltp, asks, bids
        self.polls = 0

    def get_quote(self, symbols):
        self.polls += 1
        q = {'last_price': self.ltp}
        if self.asks is not None or self.bids is not None:
            q['depth'] = {'sell': self.asks or [], 'buy': self.bids or []}
        return {f'NSE:{s}': q for s in symbols}


def _lvl(price, qty):
    return {'price': price, 'quantity': qty, 'orders': 1}


def test_paper_buy_fills_at_available_price_not_the_limit():
    t = _Book(100.0, asks=[_lvl(100.10, 50), _lvl(100.30, 50)], bids=[_lvl(99.9, 50)])
    pb = PaperBroker(t, fill_wait=0, slippage_bps=0)
    oid = pb.place_order('X', 'BUY', 10, price=100.5)          # limit 100.5, market 100.10
    assert pb.get_fill_price(oid) == 100.10, pb.get_fill_price(oid)
    assert pb.get_positions()['net'][0]['average_price'] == 100.10
    print('  \u2713 buy filled at the ask (100.10), better than the 100.50 limit')


def test_paper_buy_does_not_fill_when_price_ran_away():
    t = _Book(101.0, asks=[_lvl(101.0, 500)], bids=[_lvl(100.9, 500)])
    pb = PaperBroker(t, fill_wait=4, poll_interval=2, sleep=lambda s: None, slippage_bps=0)
    assert pb.place_order('X', 'BUY', 10, price=100.5) is None   # market above the limit
    assert pb.get_positions()['net'] == []
    assert [o['status'] for o in pb.get_orders()] == ['CANCELLED']
    assert t.polls == 4, t.polls                                 # 1 band check + 3 fill polls
    print('  \u2713 buy limit below a rising market is re-checked, then cancelled; no position')


def test_paper_order_fills_if_price_comes_back_within_the_wait():
    class Drift(_Book):
        def get_quote(self, symbols):
            self.ltp = 101.0 if self.polls < 1 else 100.2
            return super().get_quote(symbols)
    t = Drift(101.0)
    pb = PaperBroker(t, fill_wait=6, poll_interval=2, sleep=lambda s: None, slippage_bps=0)
    oid = pb.place_order('X', 'BUY', 10, price=100.5)
    assert oid and pb.get_fill_price(oid) == 100.2
    print('  \u2713 order that could not fill at first fills when the price returns inside the wait')


def test_paper_sell_walks_the_book_and_gap_down_stop_fills_lower():
    bids = [_lvl(99.0, 4), _lvl(98.5, 6), _lvl(98.0, 100)]
    t = _Book(99.0, asks=[_lvl(99.2, 100)], bids=bids)
    pb = PaperBroker(t, fill_wait=0, slippage_bps=0)
    pb.place_order('X', 'BUY', 10, price=99.5)
    oid = pb.place_order('X', 'SELL', 10, price=98.0)            # 4 @ 99.0, 6 @ 98.5
    assert pb.get_fill_price(oid) == round((4 * 99.0 + 6 * 98.5) / 10, 2) == 98.7
    # a fall straight through the sell limit: nothing within the limit -> not filled
    t2 = _Book(95.0, asks=[_lvl(95.2, 100)], bids=[_lvl(95.0, 100)])
    pb2 = PaperBroker(t2, fill_wait=0, slippage_bps=0)
    pb2._positions['X'] = {'quantity': 10, 'average_price': 100.0}
    assert pb2.place_order('X', 'SELL', 10, price=98.0) is None
    assert pb2.get_positions()['net'][0]['quantity'] == 10       # still holding
    print('  \u2713 sell walks the bid levels (98.70); a fall through the limit does not fill')


def test_paper_book_too_thin_for_the_order_does_not_fill():
    t = _Book(100.0, asks=[_lvl(100.0, 3)], bids=[_lvl(99.9, 3)])
    pb = PaperBroker(t, fill_wait=0, slippage_bps=0)
    assert pb.place_order('X', 'BUY', 10, price=100.5) is None
    print('  \u2713 visible liquidity (3 shares) cannot absorb a 10-share order -> no fill')


def test_paper_slippage_never_passes_the_limit():
    t = _Book(100.0, asks=[_lvl(100.0, 100)], bids=[_lvl(99.9, 100)])
    pb = PaperBroker(t, fill_wait=0, slippage_bps=5)
    assert pb.get_fill_price(pb.place_order('X', 'BUY', 10, price=100.5)) == 100.05
    assert pb.get_fill_price(pb.place_order('X', 'SELL', 10, price=99.0)) == 99.85
    tight = PaperBroker(_Book(100.0, asks=[_lvl(100.0, 100)]), fill_wait=0, slippage_bps=50)
    assert tight.get_fill_price(tight.place_order('X', 'BUY', 5, price=100.1)) == 100.1   # capped at limit
    print('  \u2713 5 bps slippage applied (100.05 / 99.85) and capped at the limit')


def test_execution_agent_books_the_real_fill_and_handles_no_fill():
    from src.agents.execution_agent import ExecutionAgent
    from src.agents.risk_gate import RiskDecision
    t = _Book(100.0, asks=[_lvl(100.10, 500)], bids=[_lvl(99.9, 500)])
    ex = ExecutionAgent(PaperBroker(t, fill_wait=0, slippage_bps=0), stop_loss_pct=0.015)
    assert ex.execute('X', RiskDecision(True, quantity=10, limit_price=100.5, reason='t'), 'BUY')
    pos = ex.get_position('X')
    assert pos.avg_price == 100.10, pos.avg_price                 # not the 100.50 limit
    t.ltp, t.asks, t.bids = 105.0, [_lvl(105.0, 500)], [_lvl(104.9, 500)]
    assert not ex.execute('Y', RiskDecision(True, quantity=10, limit_price=100.5, reason='t'), 'BUY')
    assert ex.get_position('Y') is None                           # unfilled order creates no position
    print('  \u2713 ExecutionAgent books the true fill (100.10) and ignores an unfilled order')


def test_exit_not_double_sold_and_unfilled_exit_retries():
    from src.agents.execution_agent import ExecutionAgent
    from src.agents.position_monitor import PositionMonitor
    t = _Book(100.0, asks=[_lvl(100.0, 500)], bids=[_lvl(99.9, 500)])
    ex = ExecutionAgent(PaperBroker(t, fill_wait=0, slippage_bps=0), stop_loss_pct=0.015)
    ex._record_fill('X', 'BUY', 10, 100.0)
    ex.trader._positions['X'] = {'quantity': 10, 'average_price': 100.0}
    pm = PositionMonitor(ex, risk_gate=None, trader=t, stop_loss_pct=0.015)
    pos = ex.get_position('X')
    pm._exit('X', pos, 99.9, 'stop')
    assert ex.get_position('X') is None
    n = len(ex.order_history)
    pm._exit('X', pos, 99.9, 'stop again')                       # the race loser must do nothing
    assert len(ex.order_history) == n
    # an exit that cannot fill leaves the position open so the next check retries it
    t2 = _Book(90.0, asks=[_lvl(90.1, 500)], bids=[_lvl(90.0, 500)])
    ex2 = ExecutionAgent(PaperBroker(t2, fill_wait=0, slippage_bps=0), stop_loss_pct=0.015)
    ex2._record_fill('X', 'BUY', 10, 100.0)
    ex2.trader._positions['X'] = {'quantity': 10, 'average_price': 100.0}
    PositionMonitor(ex2, None, t2)._exit('X', ex2.get_position('X'), 100.0, 'stale price')
    assert ex2.get_position('X') is not None
    print('  \u2713 a second exit is ignored; an unfilled exit leaves the position open to retry')


def test_square_off_retries_until_filled():
    from src.agents.execution_agent import ExecutionAgent
    class Falling(_Book):
        def get_quote(self, symbols):
            self.ltp -= 1.0 if self.polls < 3 else 0
            self.bids = [_lvl(self.ltp - 3.0 if self.polls < 2 else self.ltp, 500)]
            self.asks = [_lvl(self.ltp + 0.1, 500)]
            return super().get_quote(symbols)
    t = Falling(100.0)
    ex = ExecutionAgent(PaperBroker(t, fill_wait=0, slippage_bps=0), stop_loss_pct=0.015)
    ex._record_fill('X', 'BUY', 10, 100.0)
    ex.trader._positions['X'] = {'quantity': 10, 'average_price': 100.0}
    ex.square_off_all('test')
    assert ex.get_position('X') is None, 'square-off must keep trying until it fills'
    print('  \u2713 square-off re-quotes and retries when the first exit misses')


def test_fast_position_check_uses_open_positions_only():
    import importlib.util
    os.environ['TRADING_MODE'] = 'paper'
    spec = importlib.util.spec_from_file_location('lt', os.path.join(ROOT, 'scripts', 'live_trade_v2.py'))
    lt = importlib.util.module_from_spec(spec); spec.loader.exec_module(lt)
    lt.FAST_CHECK = 0.01
    calls = []

    class PM:
        def monitor(self, signal_overrides=None):
            calls.append(1); return {}
    class Ex:
        def __init__(self, held): self.held = held
        def all_positions(self): return {'X': 1} if self.held else {}
    from datetime import datetime
    midday = lambda: datetime(2026, 1, 5, 11, 0)
    lt._watch_positions(0.1, PM(), Ex(False), {}, now_fn=midday)
    assert calls == [], 'no open position -> no quote calls'
    lt._watch_positions(0.1, PM(), Ex(True), {}, now_fn=midday)
    assert len(calls) >= 3, len(calls)
    n = len(calls)
    lt._watch_positions(0.1, PM(), Ex(True), {}, now_fn=lambda: datetime(2026, 1, 5, 15, 25))
    assert len(calls) == n, 'after square-off time the main loop owns exits'
    print(f'  \u2713 fast check idle with no positions; {len(calls)} checks in 0.1s with one open')


class _BandBook(_Book):
    def __init__(self, ltp, lo, hi, **kw):
        super().__init__(ltp, **kw)
        self.lo, self.hi = lo, hi

    def get_quote(self, symbols):
        out = super().get_quote(symbols)
        for q in out.values():
            if self.lo is not None:
                q['lower_circuit_limit'], q['upper_circuit_limit'] = self.lo, self.hi
        return out


def test_circuit_band_rejects_orders_priced_outside_it():
    t = _BandBook(100.0, 90.0, 110.0, asks=[_lvl(100.1, 500)], bids=[_lvl(99.9, 500)])
    pb = PaperBroker(t, fill_wait=0, slippage_bps=0)
    assert pb.place_order('X', 'BUY', 5, price=110.5) is None           # above upper circuit
    assert pb.place_order('X', 'SELL', 5, price=89.0) is None           # below lower circuit
    o = pb.get_orders()
    assert [x['status'] for x in o] == ['REJECTED', 'REJECTED'] and 'circuit band' in o[0]['status_message']
    assert pb.get_positions()['net'] == []
    assert pb.place_order('X', 'BUY', 5, price=100.5)                    # inside the band: fine
    print('  \u2713 orders priced outside the circuit band are REJECTED; inside is accepted')


def test_circuit_rejection_is_immediate_not_retried():
    t = _BandBook(100.0, 90.0, 110.0, asks=[_lvl(100.1, 500)])
    waited = []
    pb = PaperBroker(t, fill_wait=10, poll_interval=2, sleep=waited.append, slippage_bps=0)
    assert pb.place_order('X', 'BUY', 5, price=120.0) is None
    assert waited == [], 'a rejection must not wait like an unfilled limit order'
    print('  \u2713 rejection is immediate (no waiting)')


def test_stock_locked_at_circuit_has_nothing_to_trade_against():
    # locked at the upper circuit: no sellers, only bids; a buy within the band cannot fill
    t = _BandBook(110.0, 90.0, 110.0, asks=[], bids=[_lvl(110.0, 90_000)])
    pb = PaperBroker(t, fill_wait=0, slippage_bps=0)
    assert pb.place_order('X', 'BUY', 5, price=110.0) is None
    # lower-circuit lock: exit is possible only at the circuit price, nobody buys
    t2 = _BandBook(90.0, 90.0, 110.0, asks=[_lvl(90.0, 90_000)], bids=[])
    pb2 = PaperBroker(t2, fill_wait=0, slippage_bps=0)
    pb2._positions['X'] = {'quantity': 5, 'average_price': 100.0}
    assert pb2.place_order('X', 'SELL', 5, price=90.0) is None
    assert pb2.get_positions()['net'][0]['quantity'] == 5               # stuck in the position
    print('  \u2713 locked at a circuit: no counter-side, so no fill (a real trapped position)')


def test_fill_never_lands_outside_the_band_even_with_slippage():
    t = _BandBook(109.99, 90.0, 110.0, asks=[_lvl(109.99, 500)], bids=[_lvl(109.9, 500)])
    pb = PaperBroker(t, fill_wait=0, slippage_bps=50)                    # 0.5% would be 110.54
    oid = pb.place_order('X', 'BUY', 5, price=111.0)                     # limit above band -> rejected
    assert oid is None
    oid = pb.place_order('X', 'BUY', 5, price=110.0)
    assert pb.get_fill_price(oid) == 110.0
    # book levels outside the band are ignored
    t2 = _BandBook(100.0, 90.0, 110.0, asks=[_lvl(111.0, 500), _lvl(100.2, 3)], bids=[_lvl(99.9, 500)])
    assert PaperBroker(t2, fill_wait=0, slippage_bps=0).place_order('X', 'BUY', 10, price=112.0) is None
    print('  \u2713 fills are clamped inside the band; out-of-band book levels are ignored')


def test_missing_circuit_fields_do_not_block_trading():
    t = _BandBook(100.0, None, None, asks=[_lvl(100.1, 500)], bids=[_lvl(99.9, 500)])
    pb = PaperBroker(t, fill_wait=0, slippage_bps=0)
    assert pb.place_order('X', 'BUY', 5, price=100.5)
    z = _BandBook(100.0, 0, 0, asks=[_lvl(100.1, 500)])
    assert PaperBroker(z, fill_wait=0, slippage_bps=0).place_order('X', 'BUY', 5, price=100.5)
    print('  \u2713 quote without circuit limits (or zeros) trades normally')


def test_entry_scan_reports_why_nothing_was_bought():
    import logging
    from src.agents.signal_engine import SignalEngine
    from src.strategies.intraday_high_low_strategy import IntradayHighLowStrategy

    class _T:
        def __init__(self, qs):
            self.qs = qs

        def get_quote(self, syms):
            return {f'NSE:{s}': self.qs[s] for s in syms}

    def q(price, high, low):
        return {'last_price': price, 'ohlc': {'open': price, 'high': high, 'low': low}, 'volume': 1}

    # FLAT: near its low but only 1% below the high.  ROOMY: near its low, 5% below the high.
    # MID: mid-range.
    qs = {'FLAT': q(100.2, 101.2, 100.0), 'ROOMY': q(100.5, 105.5, 100.0), 'MID': q(102.0, 104.0, 100.0)}
    t = _T(qs)
    se = SignalEngine.__new__(SignalEngine)
    se.trader, se.symbols = t, list(qs)
    se.logger = logging.getLogger('scan_test')
    se.base_strategy = IntradayHighLowStrategy(
        trader=t, symbols=list(qs), min_profit_margin=0.01, buy_threshold=0.20,
        sell_threshold=0.80, risk_reward_ratio=2.0, stop_loss_pct=0.015)
    se.generate_signal = lambda sym, md: (se.base_strategy.update_intraday_data(sym, md), None)[1]
    se._passes = 0

    records = []

    class _H(logging.Handler):
        def emit(self, r):
            records.append(r.getMessage())

    se.logger.addHandler(_H())
    se.logger.setLevel(logging.INFO)
    assert se.run_iteration() == {'FLAT': None, 'ROOMY': None, 'MID': None}
    line = [m for m in records if m.startswith('Entry scan')]
    assert len(line) == 1, records
    line = line[0]
    assert '3 symbols' in line and 'buy zone (<=20% of day range): 2' in line, line
    assert 'room >=3.0% to day high: 1' in line, line          # only ROOMY clears 2.0 x 1.5%
    assert 'signals: 0' in line and 'FLAT' in line and 'ROOMY' in line, line

    # No data at all -> no line, no crash
    records.clear()
    se.symbols, t.qs = ['GONE'], {}
    t.get_quote = lambda syms: {}
    se.run_iteration()
    assert not [m for m in records if m.startswith('Entry scan')]
    print('  \u2713 entry scan line says how many symbols were in the buy zone and had room')

def test_reward_is_bigger_for_confident_mistakes_and_bounded():
    from src.ml.prediction_ledger import reward_weight
    assert reward_weight(0.9, 0) > reward_weight(0.6, 0) > reward_weight(0.5, 0)   # confident miss hurts most
    assert reward_weight(0.9, 1) < reward_weight(0.9, 0)                           # being right is a smaller nudge
    assert reward_weight(0.6, 0, traded=True) == 2 * reward_weight(0.6, 0)         # a real trade counts double
    assert reward_weight(None, 1) == 1.0 and reward_weight(0.0, 1, traded=True) <= 5.0
    print('  \u2713 reward/punishment scales with confidence, real trades count more, and it is capped')


def _vec():
    return np.arange(20, dtype=np.float32)


def test_ledger_answers_predictions_with_target_stop_and_timeout():
    from src.ml.prediction_ledger import PredictionLedger
    d = tempfile.mkdtemp()
    L = PredictionLedger(path=d + '/l.json', sample_every=1, horizon=3)
    L.observe('X', 100.0, _vec(), 0.7)                      # prediction made at 100
    assert L.observe('X', 102.6, None, None)[0]['label'] == 1      # +2.6% -> target hit
    L.observe('X', 100.0, _vec(), 0.7)
    assert L.observe('X', 98.0, None, None)[0]['label'] == 0       # -2% -> stop hit
    L.observe('X', 100.0, _vec(), 0.7)
    assert L.observe('X', 100.1, None, None) == []                  # still open
    assert L.observe('X', 100.1, None, None) == []
    out = L.observe('X', 100.1, None, None)                         # timeout: +0.1% is eaten by costs
    assert out and out[0]['label'] == 0, out
    print('  \u2713 predictions are answered by target, stop or a cost-aware timeout')


def test_ledger_benches_a_model_that_loses_to_the_base_rate_and_lets_it_return():
    from src.ml.prediction_ledger import PredictionLedger
    d = tempfile.mkdtemp()
    L = PredictionLedger(path=d + '/l.json', window=200, min_judge=50)
    for i in range(60):                                     # confidently wrong half the time
        L._done.append((0.9, i % 2))
    L._refresh()
    assert L.benched and L.summary()['skill'] < 0
    for i in range(200):                                    # then genuinely informative
        L._done.append((0.8, 1) if i % 2 else (0.2, 0))
    L._refresh()
    assert not L.benched and L.summary()['skill'] > 0
    few = PredictionLedger(path=d + '/f.json', min_judge=50)
    for _ in range(10):
        few._done.append((0.9, 0))
    few._refresh()
    assert not few.benched                                  # not enough evidence to judge yet
    print('  \u2713 model is benched only with enough evidence, and returns when it beats the baseline')


def test_ledger_survives_restart():
    from src.ml.prediction_ledger import PredictionLedger
    p = tempfile.mkdtemp() + '/l.json'
    a = PredictionLedger(path=p)
    a._done.extend([(0.6, 1), (0.4, 0)])
    a.total = 2
    a.save()
    b = PredictionLedger(path=p)
    assert b.total == 2 and len(b._done) == 2
    open(p, 'w').write('{broken')
    assert PredictionLedger(path=p).total == 0              # corrupt file never crashes the bot
    print('  \u2713 scoreboard persists across days; a corrupt file is ignored')


def test_online_model_weights_samples_and_signal_engine_learns_from_shadow_predictions():
    from src.ml.online_model import OnlineModel
    from src.ml.prediction_ledger import PredictionLedger
    rng = np.random.default_rng(1)
    om = OnlineModel()
    om._warmup_done = False
    om._warmup_X, om._warmup_y, om._warmup_w = [], [], []
    for i in range(30):
        om.update(rng.normal(size=20).astype(np.float32), i % 2, weight=3.0)
    assert om._sgd_fitted and om.n_updates >= 10

    se, fe = _engine_with_spy()
    se.ledger = PredictionLedger(path=tempfile.mkdtemp() + '/l.json', sample_every=1, horizon=2)
    calls = []
    se._online_model.update = lambda v, l, weight=1.0: calls.append((l, weight))
    se._latest_prob['A'] = 0.9
    se._judge_predictions('A', 100.0)                # records a 90% win prediction
    se._judge_predictions('A', 97.0)                 # market stops it out -> confident miss
    assert calls and calls[0][0] == 0 and calls[0][1] > 2.5, calls
    print('  \u2713 shadow predictions teach the model, and a confident miss is punished hard')


def test_benched_model_loses_its_vote_but_keeps_predicting():
    from src.ml.prediction_ledger import PredictionLedger
    se, fe = _engine_with_spy()
    se._online_model.predict_proba = lambda v: 0.9
    se.ledger = PredictionLedger(path=tempfile.mkdtemp() + '/l.json')
    assert se._score_prediction('A') is not None
    se.ledger.benched = True
    assert se._score_prediction('A') is None          # no vote while benched
    assert se._latest_prob['A'] == 0.9                # but it is still being graded
    assert 'scoreboard' in se.get_ml_status()
    print('  \u2713 benched model is silent in signals yet still graded')


def test_component_check_explains_silent_components_without_changing_signals():
    import logging
    from src.agents.signal_engine import SignalEngine

    se, fe = _engine_with_spy()
    records = []

    class _H(logging.Handler):
        def emit(self, r):
            records.append(r.getMessage())

    se.logger.addHandler(_H())
    se.logger.setLevel(logging.INFO)
    scores = {'breakout': 1.0, 'pattern': None, 'trend': None, 'sentiment': None, 'prediction': -0.26}

    # Two passes with the same candle open (a day-candle quote) -> flagged as static.
    candle = {'open': 100.0, 'high': 104.0, 'low': 99.0, 'close': 101.0, 'volume': 1}
    se._diagnose('A', candle, scores)
    se._diagnose('A', {**candle, 'close': 101.5}, scores)
    assert se._diag['A']['open_static'] is True
    se._log_components()
    line = [m for m in records if m.startswith('Component check')][0]
    assert 'breakout 1, pattern 0, trend 0, sentiment 0, ML 1' in line, line
    assert 'under 8 recorded moves' in line and 'lack history' in line, line
    assert 'candle open unchanged since last pass: 1/1' in line, line

    # A real bar-by-bar feed changes its open -> not static.
    se._diagnose('A', {**candle, 'open': 101.0}, scores)
    assert se._diag['A']['open_static'] is False

    # Diagnostics must never raise, even on garbage input, and never touch the scores.
    before = dict(scores)
    se._diagnose('A', {}, scores)
    assert scores == before
    SignalEngine._log_components(type('E', (), {'_diag': {}, 'logger': se.logger})())   # empty: silent
    print('  \u2713 component check reports why trend/sentiment/pattern are silent and is read-only')




if __name__ == '__main__':
    tests = [
        test_paper_broker_never_places_real_orders,
        test_paper_broker_hides_raw_client,
        test_daily_report_math,
        test_empty_day_is_na_not_zero,
        test_completed_day_counting_and_idempotence,
        test_live_requires_approval,
        test_unknown_mode_falls_back_to_paper,
        test_online_model_learns_from_entry_features_and_net_label,
        test_online_model_skips_positions_it_did_not_open,
        test_post_trade_agent_snapshots_entry_on_buy,
        test_scanner_skips_stocks_too_expensive_for_capital,
        test_paper_gates_can_approve_a_trade_and_live_stays_strict,
        test_broker_health_check_works_through_paper_broker,
        test_status_json_has_dashboard_fields,
        test_market_calendar_knows_2026_nse_holidays,
        test_paper_capital_compounds_net_of_costs_and_live_stays_capped,
        test_day_end_books_net_pnl_after_charges,
        test_paper_buy_fills_at_available_price_not_the_limit,
        test_paper_buy_does_not_fill_when_price_ran_away,
        test_paper_order_fills_if_price_comes_back_within_the_wait,
        test_paper_sell_walks_the_book_and_gap_down_stop_fills_lower,
        test_paper_book_too_thin_for_the_order_does_not_fill,
        test_paper_slippage_never_passes_the_limit,
        test_execution_agent_books_the_real_fill_and_handles_no_fill,
        test_exit_not_double_sold_and_unfilled_exit_retries,
        test_square_off_retries_until_filled,
        test_fast_position_check_uses_open_positions_only,
        test_circuit_band_rejects_orders_priced_outside_it,
        test_circuit_rejection_is_immediate_not_retried,
        test_stock_locked_at_circuit_has_nothing_to_trade_against,
        test_fill_never_lands_outside_the_band_even_with_slippage,
        test_missing_circuit_fields_do_not_block_trading,
        test_entry_scan_reports_why_nothing_was_bought,
        test_reward_is_bigger_for_confident_mistakes_and_bounded,
        test_ledger_answers_predictions_with_target_stop_and_timeout,
        test_ledger_benches_a_model_that_loses_to_the_base_rate_and_lets_it_return,
        test_ledger_survives_restart,
        test_online_model_weights_samples_and_signal_engine_learns_from_shadow_predictions,
        test_benched_model_loses_its_vote_but_keeps_predicting,
        test_component_check_explains_silent_components_without_changing_signals,
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
