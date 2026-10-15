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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.kite_trader.paper_broker import PaperBroker
from src.utils import paper_report


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


if __name__ == '__main__':
    tests = [
        test_paper_broker_never_places_real_orders,
        test_paper_broker_hides_raw_client,
        test_daily_report_math,
        test_empty_day_is_na_not_zero,
        test_completed_day_counting_and_idempotence,
        test_live_requires_approval,
        test_unknown_mode_falls_back_to_paper,
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
