"""
Market & news analysis — pure functions (no network, no broker).

  attribute_move      why did a stock move today? (market vs stock-specific, gap,
                      volume, did the news tone line up)
  news_stats          how well did the morning news tone predict each stock's direction,
                      measured over every observation we have stored
  confidence_delta    small, bounded nudge to a signal's confidence learned from those
                      stats; zero until there are enough observations
  build_report / render_md   the daily report

Everything is heuristic and honest about it: attribution is "what coincided with the
move", not proof of cause. Beta is assumed to be 1 against Nifty.
"""
import json
import os
from typing import Dict, List, Optional

TONE_THRESHOLD = 0.2        # |keyword score| needed to call a headline set positive/negative
MIN_DECISIVE_OBS = 30       # observations with a clear tone and a clear move before learning acts
MAX_DELTA = 0.10            # largest confidence nudge, either direction
MAX_OBSERVATIONS = 2000


def _sgn(x: float) -> int:
    return (x > 0) - (x < 0)


def tone_label(score: Optional[float], confidence: Optional[float]) -> str:
    if score is None or not confidence:
        return 'none'
    if score >= TONE_THRESHOLD:
        return 'positive'
    if score <= -TONE_THRESHOLD:
        return 'negative'
    return 'neutral'


# ----------------------------------------------------------------------
# Attribution
# ----------------------------------------------------------------------

def attribute_move(symbol: str, day_pct: float, gap_pct: float, intraday_pct: float,
                   market_pct: float, vol_ratio: Optional[float] = None,
                   tone: Optional[Dict] = None, n_headlines: int = 0) -> Dict:
    """All percentages are in percent (1.5 means +1.5%). `tone` = {'score','confidence'}."""
    residual = day_pct - market_pct
    drivers: List[str] = []

    if abs(market_pct) >= 0.4 and abs(residual) < max(0.5, 0.5 * abs(day_pct)):
        drivers.append(f"market-wide move (Nifty {market_pct:+.2f}%)")
    elif abs(residual) >= 1.0:
        drivers.append(f"stock-specific: {'outperformed' if residual > 0 else 'underperformed'} "
                       f"Nifty by {abs(residual):.2f}%")

    if abs(gap_pct) >= 1.0 and abs(gap_pct) >= 0.6 * abs(day_pct):
        drivers.append(f"gap at the open ({gap_pct:+.2f}%) — overnight news or global cues")
    elif abs(intraday_pct) >= 1.0:
        drivers.append(f"intraday move after the open ({intraday_pct:+.2f}%)")

    if vol_ratio is not None and vol_ratio >= 1.5:
        drivers.append(f"heavy volume ({vol_ratio:.1f}x the 20-day average)")

    score = (tone or {}).get('score')
    label = tone_label(score, (tone or {}).get('confidence'))
    aligned = None
    if label in ('positive', 'negative') and abs(day_pct) >= 0.5:
        aligned = (label == 'positive') == (day_pct > 0)
        drivers.append(f"news tone {label}, " + ("consistent with the move" if aligned else
                       "but the price went the other way — news did not explain it"))
    elif n_headlines == 0 and abs(day_pct) >= 0.5:
        drivers.append("no notable news found")

    if not drivers:
        drivers.append("quiet — no clear driver")

    return {
        'symbol': symbol,
        'day_pct': round(day_pct, 2), 'market_pct': round(market_pct, 2),
        'residual_pct': round(residual, 2), 'gap_pct': round(gap_pct, 2),
        'intraday_pct': round(intraday_pct, 2),
        'vol_ratio': round(vol_ratio, 2) if vol_ratio is not None else None,
        'news_tone': label, 'news_score': round(score, 2) if score is not None else None,
        'news_aligned': aligned, 'drivers': drivers,
        'summary': f"{symbol} {day_pct:+.2f}%: " + "; ".join(drivers),
    }


# ----------------------------------------------------------------------
# Learning
# ----------------------------------------------------------------------

def news_stats(observations: List[Dict]) -> Dict:
    """
    observations: [{'date','symbol','tone_score','tone_label','move_pct'}], where tone is
    the one captured at the START of the day (so it cannot have been written about the move).
    """
    by_label: Dict[str, List[float]] = {}
    hits = decisive = 0
    for o in observations:
        by_label.setdefault(o.get('tone_label', 'none'), []).append(o.get('move_pct', 0.0))
        if o.get('tone_label') in ('positive', 'negative') and abs(o.get('move_pct', 0.0)) >= 0.3:
            decisive += 1
            if (o['tone_label'] == 'positive') == (o['move_pct'] > 0):
                hits += 1
    return {
        'n_obs': len(observations),
        'n_decisive': decisive,
        'accuracy': round(hits / decisive, 3) if decisive else None,
        'avg_move_by_tone': {k: round(sum(v) / len(v), 2) for k, v in by_label.items()},
        'count_by_tone': {k: len(v) for k, v in by_label.items()},
        'adjustment_active': decisive >= MIN_DECISIVE_OBS,
        'needs_more': max(0, MIN_DECISIVE_OBS - decisive),
    }


def confidence_delta(signal: str, tone_score: Optional[float], tone_conf: Optional[float],
                     stats: Dict) -> float:
    """Additive change to a signal's confidence, within +/-MAX_DELTA. 0 until enough data."""
    if not stats.get('adjustment_active') or stats.get('accuracy') is None:
        return 0.0
    label = tone_label(tone_score, tone_conf)
    if label not in ('positive', 'negative') or signal not in ('BUY', 'SELL'):
        return 0.0
    edge = max(-1.0, min(1.0, (stats['accuracy'] - 0.5) * 2.0))   # <0: news has been contrarian
    direction = 1 if label == 'positive' else -1
    want = 1 if signal == 'BUY' else -1
    return max(-MAX_DELTA, min(MAX_DELTA, MAX_DELTA * edge * direction * want))


# ----------------------------------------------------------------------
# Trades
# ----------------------------------------------------------------------

def trade_notes(trip: Dict, attribution: Optional[Dict], entry_tone: str,
                after_exit_pct: Optional[float], market_pct: float) -> List[str]:
    notes = []
    win = trip['net_pnl'] > 0
    if entry_tone == 'negative':
        notes.append("entered against negative news" + (" and still won" if win else ""))
    elif entry_tone == 'positive':
        notes.append("entered with positive news" + ("" if win else " but lost"))
    elif entry_tone == 'none':
        notes.append("no news found at entry")
    if not win and market_pct <= -0.4:
        notes.append(f"market was weak (Nifty {market_pct:+.2f}%)")
    if win and market_pct >= 0.4:
        notes.append(f"helped by a strong market (Nifty {market_pct:+.2f}%)")
    if after_exit_pct is not None and abs(after_exit_pct) >= 0.5:
        if after_exit_pct > 0:
            notes.append(f"price rose another {after_exit_pct:.2f}% after we exited"
                         + (" (exit was early)" if win else ""))
        else:
            notes.append(f"price fell a further {abs(after_exit_pct):.2f}% after we exited")
    if attribution and attribution['drivers'] and attribution['drivers'][0].startswith('stock-specific'):
        notes.append(attribution['drivers'][0])
    return notes


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------

def build_report(day: str, market: Dict, stocks: List[Dict], trades: List[Dict],
                 stats: Dict) -> Dict:
    moves = [s['day_pct'] for s in stocks]
    breadth = {
        'advancers': sum(1 for m in moves if m > 0.05),
        'decliners': sum(1 for m in moves if m < -0.05),
        'avg_move_pct': round(sum(moves) / len(moves), 2) if moves else None,
    }
    return {'date': day, 'market': {**market, 'breadth': breadth},
            'stocks': stocks, 'trades': trades, 'learning': stats}


def _p(v, suffix='%') -> str:
    return 'n/a' if v is None else f"{v:+.2f}{suffix}"


def render_md(r: Dict) -> str:
    m = r['market']
    tone = m.get('tone', {})
    lines = [
        f"# Market & news analysis — {r['date']}", '',
        f"- Nifty: **{_p(m.get('nifty_pct'))}**, India VIX: {m.get('vix', 'n/a')}, regime: {m.get('regime', 'n/a')}",
        f"- Market news tone: **{tone.get('label', 'none')}** "
        f"(score {tone.get('score', 0):+.2f}, {tone.get('n', 0)} headlines)",
        f"- Our watchlist: {m['breadth']['advancers']} up, {m['breadth']['decliners']} down, "
        f"average {_p(m['breadth']['avg_move_pct'])}",
    ]
    if m.get('timeline'):
        lines += ['', '**How news tone and the market moved through the day**', '',
                  '| Time | Nifty | Market news tone |', '|---|---:|---:|']
        for t in m['timeline']:
            lines.append(f"| {t['time']} | {_p(t.get('nifty_pct'))} | {t.get('market_tone', 0):+.2f} |")
    if m.get('headlines'):
        lines += ['', '**Top market headlines**', '']
        lines += [f"- {h['title']} ({h.get('source', '')}) — tone {h.get('score', 0):+.1f}"
                  for h in m['headlines'][:5]]
    if r['stocks']:
        lines += ['', '**What moved our watchlist**', '']
        lines += [f"- {s['summary']}" for s in r['stocks']]
    if r['trades']:
        lines += ['', '**Stocks we traded**', '',
                  '| Symbol | Net P&L | News at entry | After exit | Notes |', '|---|---:|---|---:|---|']
        for t in r['trades']:
            lines.append(f"| {t['symbol']} | {t['net_pnl']:+.2f} | {t['entry_tone']} | "
                         f"{_p(t.get('move_after_exit_pct'))} | {'; '.join(t['notes'])} |")
    else:
        lines += ['', '**Stocks we traded**: none today.']
    ls = r['learning']
    lines += ['', '**Learning**', '',
              f"- {ls['n_obs']} stock-days observed; {ls['n_decisive']} had a clear news tone and a clear move.",
              (f"- Morning news tone predicted the day's direction {ls['accuracy'] * 100:.0f}% of the time."
               if ls['accuracy'] is not None else "- Not enough data yet to say whether news tone predicts direction."),
              ("- Confidence adjustment from news: ACTIVE (max ±0.10)." if ls['adjustment_active']
               else f"- Confidence adjustment from news: inactive until {ls['needs_more']} more decisive observations.")]
    return '\n'.join(lines) + '\n'


# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------

def load_history(analysis_dir: str) -> List[Dict]:
    try:
        with open(os.path.join(analysis_dir, 'history.json')) as f:
            return json.load(f).get('observations', [])
    except Exception:
        return []


def save_history(analysis_dir: str, observations: List[Dict]):
    os.makedirs(analysis_dir, exist_ok=True)
    with open(os.path.join(analysis_dir, 'history.json'), 'w') as f:
        json.dump({'observations': observations[-MAX_OBSERVATIONS:]}, f)


def write_report(analysis_dir: str, report: Dict) -> str:
    os.makedirs(analysis_dir, exist_ok=True)
    path = os.path.join(analysis_dir, f"{report['date']}.json")
    with open(path, 'w') as f:
        json.dump(report, f, indent=2)
    with open(os.path.join(analysis_dir, f"{report['date']}.md"), 'w') as f:
        f.write(render_md(report))
    return path
