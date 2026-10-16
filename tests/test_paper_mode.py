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
    pb = PaperBroker(t)
    oid = pb.place_order('SBIN', 'BUY', 10, price=100.0)
    assert oid and oid.startswith('PAPER-')
    assert t.kite.real_orders == 0
    assert pb.get_positions()['net'][0]['quantity'] == 10
    pb.place_order('SBIN', 'SELL', 10, price=101.0)
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
        def __init__(self): self.calls = []
        def update(self, vec, label): self.calls.append((vec.copy(), label))
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
