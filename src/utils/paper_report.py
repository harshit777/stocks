"""
Daily paper-trading report.

One JSON + one Markdown file per trading day under data/paper/reports/, plus a
cumulative data/paper/SUMMARY.md. The headline number is the win rate: the
percentage of closed round trips that made money, both before costs (gross)
and after brokerage/STT/charges (net).
"""
import json
import os
from datetime import date
from typing import Dict, List, Optional

BASE_DIR = 'data/paper'


def _reports_dir(base_dir: str) -> str:
    return os.path.join(base_dir, 'reports')


def _round_trip_cost(entry: float, exit_: float, qty: int) -> float:
    from .cost_calculator import get_cost_calculator
    calc = get_cost_calculator()
    return (calc.calculate_total_cost(entry, qty, 'BUY')['total_cost']
            + calc.calculate_total_cost(exit_, qty, 'SELL')['total_cost'])


def round_trips(trade_log: List[Dict]) -> List[Dict]:
    """Pair BUY fills with the SELL fills that close them."""
    lots: Dict[str, tuple] = {}   # symbol -> (qty, avg_price)
    trips: List[Dict] = []
    for t in trade_log:
        sym, qty, px = t['symbol'], t['quantity'], t['fill_price']
        if t['transaction_type'] == 'BUY':
            q, a = lots.get(sym, (0, 0.0))
            lots[sym] = (q + qty, (a * q + px * qty) / (q + qty))
        elif t['transaction_type'] == 'SELL' and sym in lots and t.get('pnl') is not None:
            q, a = lots[sym]
            sq = min(qty, q)
            gross = (px - a) * sq
            cost = _round_trip_cost(a, px, sq)
            trips.append({
                'symbol': sym, 'time': t.get('timestamp'), 'qty': sq,
                'entry': round(a, 2), 'exit': round(px, 2),
                'gross_pnl': round(gross, 2), 'costs': round(cost, 2),
                'net_pnl': round(gross - cost, 2),
            })
            if q - sq <= 0:
                del lots[sym]
            else:
                lots[sym] = (q - sq, a)
    return trips


def _stats(trips: List[Dict]) -> Dict:
    n = len(trips)
    gross_wins = [t for t in trips if t['gross_pnl'] > 0]
    net_wins = [t for t in trips if t['net_pnl'] > 0]
    loss_total = -sum(t['gross_pnl'] for t in trips if t['gross_pnl'] < 0)
    win_total = sum(t['gross_pnl'] for t in gross_wins)
    return {
        'closed_trades': n,
        'wins_gross': len(gross_wins),
        'losses_gross': n - len(gross_wins),
        'wins_net': len(net_wins),
        'win_rate_gross_pct': round(100 * len(gross_wins) / n, 1) if n else None,
        'win_rate_net_pct': round(100 * len(net_wins) / n, 1) if n else None,
        'gross_pnl': round(sum(t['gross_pnl'] for t in trips), 2),
        'costs': round(sum(t['costs'] for t in trips), 2),
        'net_pnl': round(sum(t['net_pnl'] for t in trips), 2),
        'avg_win': round(win_total / len(gross_wins), 2) if gross_wins else None,
        'avg_loss': round(-loss_total / (n - len(gross_wins)), 2) if n - len(gross_wins) else None,
        'profit_factor': round(win_total / loss_total, 2) if loss_total > 0 else None,
    }


def build_daily_report(day: str, trade_log: List[Dict], funnel: Dict, exits: Dict,
                       starting_capital: float, max_drawdown: float, mode: str,
                       complete: bool, end_reason: str, open_positions: int,
                       ml_status: Optional[Dict] = None) -> Dict:
    trips = round_trips(trade_log)
    return {
        'date': day,
        'mode': mode,
        'complete': complete,          # counts toward the paper-trading day limit
        'end_reason': end_reason,
        'starting_capital': round(starting_capital, 2),
        'max_drawdown': round(max_drawdown, 2),
        'open_positions_at_close': open_positions,
        'signals': funnel,
        'exits_by_reason': exits,
        'ml': ml_status or {},
        **_stats(trips),
        'round_trips': trips,
    }


def _pct(v) -> str:
    return 'n/a' if v is None else f'{v:.1f}%'


def render_daily_md(r: Dict) -> str:
    sig = r.get('signals', {})
    lines = [
        f"# Paper trading report — {r['date']}",
        '',
        f"- Session: {'complete' if r['complete'] else 'INCOMPLETE'} ({r['end_reason']})",
        f"- Starting capital: ₹{r['starting_capital']:,.2f}",
        f"- **Win rate (before costs): {_pct(r['win_rate_gross_pct'])}** "
        f"({r['wins_gross']} of {r['closed_trades']} closed trades)",
        f"- **Win rate (after costs): {_pct(r['win_rate_net_pct'])}** "
        f"({r['wins_net']} of {r['closed_trades']})",
        f"- P&L: gross ₹{r['gross_pnl']:+,.2f}, costs ₹{r['costs']:,.2f}, **net ₹{r['net_pnl']:+,.2f}**",
        f"- Max drawdown: ₹{r['max_drawdown']:,.2f}",
        f"- Signals: {sig.get('buy_signals', 0)} BUY, {sig.get('sell_signals', 0)} SELL "
        f"→ {sig.get('approved', 0)} approved, {sig.get('blocked', 0)} blocked by risk gate, "
        f"{sig.get('executed', 0)} executed"
        + (f", {sig['shorts_skipped']} short entries skipped (shorts disabled)"
           if sig.get('shorts_skipped') else ''),
    ]
    if r.get('exits_by_reason'):
        lines.append('- Exits: ' + ', '.join(f"{k} ×{v}" for k, v in r['exits_by_reason'].items()))
    if r['round_trips']:
        lines += ['', '| Symbol | Qty | Entry | Exit | Gross | Costs | Net |',
                  '|---|---:|---:|---:|---:|---:|---:|']
        for t in r['round_trips']:
            lines.append(f"| {t['symbol']} | {t['qty']} | {t['entry']} | {t['exit']} | "
                         f"{t['gross_pnl']:+.2f} | {t['costs']:.2f} | {t['net_pnl']:+.2f} |")
    return '\n'.join(lines) + '\n'


def write_daily_report(report: Dict, base_dir: str = BASE_DIR) -> str:
    d = _reports_dir(base_dir)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{report['date']}.json")
    with open(path, 'w') as f:
        json.dump(report, f, indent=2)
    with open(os.path.join(d, f"{report['date']}.md"), 'w') as f:
        f.write(render_daily_md(report))
    update_summary(base_dir)
    return path


def load_reports(base_dir: str = BASE_DIR) -> List[Dict]:
    d = _reports_dir(base_dir)
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if name.endswith('.json'):
            try:
                with open(os.path.join(d, name)) as f:
                    out.append(json.load(f))
            except Exception:
                continue
    return out


def completed_days(base_dir: str = BASE_DIR) -> int:
    return sum(1 for r in load_reports(base_dir) if r.get('complete'))


def todays_report_complete(base_dir: str = BASE_DIR, today: Optional[str] = None) -> bool:
    today = today or date.today().isoformat()
    return any(r.get('date') == today and r.get('complete') for r in load_reports(base_dir))


def build_summary(base_dir: str = BASE_DIR, max_days: int = 10) -> str:
    reports = [r for r in load_reports(base_dir) if r.get('complete')]
    done = len(reports)
    lines = [f"# Paper trading summary — day {min(done, max_days)} of {max_days}", '']
    if done >= max_days:
        lines += ['**Paper-trading period finished.** Live trading stays off until you approve it.', '']

    trips = sum(r['closed_trades'] for r in reports)
    g_wins = sum(r['wins_gross'] for r in reports)
    n_wins = sum(r['wins_net'] for r in reports)
    lines += [
        '## Cumulative',
        f"- Closed trades: {trips}",
        f"- **Win rate (before costs): {_pct(100 * g_wins / trips if trips else None)}**",
        f"- **Win rate (after costs): {_pct(100 * n_wins / trips if trips else None)}**",
        f"- Gross P&L ₹{sum(r['gross_pnl'] for r in reports):+,.2f}, "
        f"costs ₹{sum(r['costs'] for r in reports):,.2f}, "
        f"net ₹{sum(r['net_pnl'] for r in reports):+,.2f}",
        '',
        '## By day',
        '| Day | Date | Trades | Win % (gross) | Win % (net) | Net P&L |',
        '|---:|---|---:|---:|---:|---:|',
    ]
    for i, r in enumerate(reports, 1):
        lines.append(f"| {i} | {r['date']} | {r['closed_trades']} | "
                     f"{_pct(r['win_rate_gross_pct'])} | {_pct(r['win_rate_net_pct'])} | "
                     f"₹{r['net_pnl']:+,.2f} |")

    hist_path = os.path.join(base_dir, 'training_history.json')
    if os.path.exists(hist_path):
        try:
            with open(hist_path) as f:
                hist = json.load(f)[-5:]
            lines += ['', '## Model training (latest runs)',
                      '| Trained at | Samples | CV accuracy | CV AUC |', '|---|---:|---:|---:|']
            for h in hist:
                lines.append(f"| {h['trained_at'][:16]} | {h['n_samples']} | "
                             f"{h['cv_accuracy_mean']:.1%} | {h['cv_auc_mean']:.3f} |")
        except Exception:
            pass
    return '\n'.join(lines) + '\n'


def update_summary(base_dir: str = BASE_DIR, max_days: Optional[int] = None) -> str:
    max_days = max_days or int(os.getenv('PAPER_MAX_DAYS', '10'))
    text = build_summary(base_dir, max_days)
    os.makedirs(base_dir, exist_ok=True)
    with open(os.path.join(base_dir, 'SUMMARY.md'), 'w') as f:
        f.write(text)
    return text
