#!/usr/bin/env python3
"""
Live Intraday Trading — Agent Architecture
==========================================

6 agents, each with one job:

  Agent 1 — MarketScanner     Build today's watchlist dynamically (volume + news)
  Agent 2 — SignalEngine      Generate BUY/SELL signals (fixed bugs, real candles)
  Agent 3 — RiskGate          Approve/reject every trade (capital, cost, R/R)
  Agent 4 — ExecutionAgent    Place orders, own the ONE position book
  Agent 5 — PositionMonitor   Watch positions, trigger stop-loss/trailing/target
  Agent 6 — PostTradeAgent    EOD accounting, capital recovery, AI model save

Loop cadence: every 2 minutes during 9:15–3:20 IST on NSE trading days.
Square-off:   3:20 PM — all positions closed before broker auto-squareoff.

Modes (TRADING_MODE):
  paper (default)  Simulated fills via PaperBroker. No order ever reaches Zerodha.
                   Writes a daily report to data/paper/reports/. PAPER_CAPITAL sets
                   the virtual capital (default 50000); PAPER_MAX_DAYS caps the run.
  live             Real money. Refuses to start unless LIVE_TRADING_APPROVED=yes.

Short selling is OFF unless ENABLE_SHORTS=true (ExecutionAgent does not yet track
SELL-to-open positions, so a short would never be covered by the position monitor).

Required env vars (config/.env):
  KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN
  MAX_LIVE_CAPITAL=1000       (live only)
  MAX_DAILY_LOSS=100          (default 10% of capital)
  NEWSAPI_KEY=<optional>      enables news sentiment boost in MarketScanner
"""
import os
import sys
import json
import time
import logging
from collections import deque
from datetime import datetime

import pytz
from dotenv import load_dotenv

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

# Anything other than an explicit "live" is paper: unknown values never trade real money.
MODE       = 'live' if os.getenv('TRADING_MODE') == 'live' else 'paper'
PAPER      = MODE == 'paper'
DATA_ROOT  = 'data/paper' if PAPER else 'data'
ENABLE_SHORTS   = os.getenv('ENABLE_SHORTS', 'false').lower() == 'true'
PAPER_MAX_DAYS  = int(os.getenv('PAPER_MAX_DAYS', '10'))

# Entry-quality gates. The exit rules are a fixed +2.5% target / -1.5% stop, i.e. at
# best 1.67:1, so a 3:1 minimum in RiskGate rejects every trade. Paper mode uses
# gates that can actually pass, so the 10-day run produces a win rate; live keeps
# the strict original values until they are reviewed.
MIN_RISK_REWARD          = 1.5 if PAPER else 3.0   # RiskGate
SIGNAL_RISK_REWARD       = 2.0 if PAPER else 3.0   # SignalEngine: day-high target vs stop
SIGNAL_MIN_PROFIT_MARGIN = 0.01 if PAPER else 0.02

os.makedirs('data/logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s — %(message)s',
    handlers=[
        logging.FileHandler(
            f"data/logs/{MODE}_{datetime.now().strftime('%Y%m%d')}.log"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger('main')

# Keep the last log lines in memory so they can be published in status.json
_log_tail: deque = deque(maxlen=60)
# (time, pnl) points for the P&L curve on the status page
_pnl_history: deque = deque(maxlen=400)


class _TailHandler(logging.Handler):
    def emit(self, record):
        msg = record.getMessage().strip()
        if not msg:
            return
        _log_tail.append({
            'time': datetime.now().strftime('%H:%M:%S'),
            'level': 'WARN' if record.levelname == 'WARNING' else record.levelname,
            'message': msg.replace('\n', ' ')[:300],
        })


logging.getLogger().addHandler(_TailHandler())

IST = pytz.timezone('Asia/Kolkata')
MARKET_OPEN    = 9 * 60 + 15   # 9:15 AM
# 3:20 PM by default. GitHub-hosted jobs are capped at 6h, so the workflow sets
# SQUARE_OFF_MINUTES=900 (3:00 PM) to finish a 9:15 AM start inside the cap.
SQUARE_OFF     = int(os.getenv('SQUARE_OFF_MINUTES', 15 * 60 + 20))
MARKET_CLOSE   = 15 * 60 + 30  # 3:30 PM
CHECK_INTERVAL = 120            # seconds between iterations
STATUS_FILE    = 'data/status.json'
STOP_FILE      = 'data/STOP'    # created by the CI publisher when a stop is requested


def _stop_requested() -> bool:
    return os.path.exists(STOP_FILE)


def _sleep(seconds: float):
    """Sleep in short slices so a stop request is noticed within ~5 seconds."""
    end = time.time() + seconds
    while time.time() < end and not _stop_requested():
        time.sleep(min(5, max(0, end - time.time())))


def _ml_block(signal_engine):
    """Offline-model metadata plus online-model progress, for the ML panel."""
    ml = {}
    try:
        with open('data/ml/metadata.json') as f:
            meta = json.load(f)
        ml = {k: meta.get(k) for k in ('cv_accuracy_mean', 'cv_auc_mean',
                                       'n_samples', 'trained_at', 'feature_importances')}
    except Exception:
        pass
    try:
        ml['online_updates'] = signal_engine.get_ml_status().get('online_updates')
    except Exception:
        pass
    return ml


def _write_status(state, iteration, risk_gate, post_trade, execution, trader,
                  signals, watchlist, scanner=None, signal_engine=None):
    """Dump a snapshot for the read-only status page. Never raises."""
    try:
        positions = []
        open_pos = execution.all_positions()
        quotes = {}
        if open_pos:
            try:
                quotes = trader.get_quote(list(open_pos.keys()))
            except Exception:
                pass
        for sym, pos in open_pos.items():
            ltp = quotes.get(f'NSE:{sym}', {}).get('last_price', pos.avg_price)
            positions.append({
                'symbol': sym, 'qty': pos.quantity,
                'avg_price': round(pos.avg_price, 2),
                'current_price': round(ltp, 2),
                'unrealised_pnl': round(pos.unrealised_pnl(ltp), 2),
                'pnl_pct': round(pos.pnl_pct(ltp) * 100, 2),
                'stop_price': round(pos.stop_price, 2),
                'entry_time': pos.entry_time.strftime('%H:%M:%S'),
            })
        post = post_trade.intraday_status()
        if state == 'running':
            _pnl_history.append({'time': datetime.now(IST).strftime('%H:%M'),
                                 'pnl': round(post['daily_pnl'], 2)})
        scores = []
        if scanner is not None:
            keys = ('symbol', 'composite_score', 'vol_surge', 'gap_pct',
                    'day_range_pct', 'price_momentum', 'atr_pct')
            scores = [{k: round(v, 4) if isinstance(v, float) else v
                       for k, v in s.items() if k in keys}
                      for s in scanner.get_last_scores()]
        snapshot = {
            'state': state,
            'mode': MODE,
            'updated_at': datetime.now(IST).isoformat(),
            'iteration': iteration,
            'risk': risk_gate.status(),
            'post_trade': post,
            'positions': positions,
            'watchlist': list(watchlist or []),
            'watchlist_scores': scores,
            'signals': {k: v for k, v in (signals or {}).items() if v},
            'pnl_history': list(_pnl_history),
            'ml': _ml_block(signal_engine),
            'log': list(_log_tail),
        }
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        tmp = STATUS_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(snapshot, f, default=str)
        os.replace(tmp, STATUS_FILE)
    except Exception as e:
        logger.debug(f"status write failed: {e}")


def main():
    # ------------------------------------------------------------------ #
    # 0. Safety gate                                                       #
    # ------------------------------------------------------------------ #
    if MODE == 'live' and os.getenv('LIVE_TRADING_APPROVED') != 'yes':
        logger.error("Live trading is NOT approved (LIVE_TRADING_APPROVED != 'yes'). Exiting.")
        sys.exit(2)

    if PAPER:
        os.environ['TRADING_MODE'] = 'paper'   # KiteTrader reads this at construction
        from src.utils.paper_report import completed_days, todays_report_complete
        if todays_report_complete():
            logger.info("Today's paper session is already recorded. Nothing to do.")
            return
        done = completed_days()
        if done >= PAPER_MAX_DAYS:
            logger.info(f"Paper-trading period finished ({done}/{PAPER_MAX_DAYS} days). Exiting.")
            return
        max_initial_capital = float(os.getenv('PAPER_CAPITAL', '50000'))
        max_daily_loss      = max_initial_capital * 0.10
        logger.info("=" * 70)
        logger.info(f"📝 PAPER TRADING — simulated fills, no real orders (day {done + 1} of {PAPER_MAX_DAYS})")
        logger.info(f"   Virtual capital: ₹{max_initial_capital:,.0f} | Max loss: ₹{max_daily_loss:,.0f}"
                    f" | Shorts: {'on' if ENABLE_SHORTS else 'off'}")
        logger.info("=" * 70)
    else:
        max_initial_capital = float(os.getenv('MAX_LIVE_CAPITAL', '1000'))
        max_daily_loss      = float(os.getenv('MAX_DAILY_LOSS', str(max_initial_capital * 0.10)))
        logger.info("=" * 70)
        logger.info("⚠️  LIVE INTRADAY TRADING — REAL MONEY")
        logger.info(f"   Capital: ₹{max_initial_capital:,.0f} | Max loss: ₹{max_daily_loss:,.0f}"
                    f" | Shorts: {'on' if ENABLE_SHORTS else 'off'}")
        logger.info("=" * 70)

    # ------------------------------------------------------------------ #
    # 1. Imports (deferred so env is loaded first)                        #
    # ------------------------------------------------------------------ #
    from src.kite_trader.trader import KiteTrader
    from src.utils.capital_manager import CapitalRecoveryManager
    from src.utils.broker_health import BrokerHealthMonitor
    from src.utils.market_calendar import MarketCalendar
    from src.kite_trader.paper_broker import PaperBroker

    from src.agents.market_scanner   import MarketScanner
    from src.agents.signal_engine    import SignalEngine
    from src.agents.risk_gate        import RiskGate
    from src.agents.execution_agent  import ExecutionAgent
    from src.agents.position_monitor import PositionMonitor
    from src.agents.post_trade_agent import PostTradeAgent
    from src.kite_trader.ticker      import PositionTicker

    # ------------------------------------------------------------------ #
    # 2. Infrastructure                                                    #
    # ------------------------------------------------------------------ #
    real_trader = KiteTrader(enable_order_manager=not PAPER, enable_rate_limiter=True)
    if not real_trader.is_connected():
        logger.error("Cannot connect to Zerodha — check KITE_ACCESS_TOKEN. Exiting.")
        return

    logger.info("✓ Connected to Zerodha (market data)")
    # In paper mode every agent gets the PaperBroker: quotes/candles are real,
    # orders are simulated, and the real order API is not reachable from it.
    trader = PaperBroker(real_trader) if PAPER else real_trader

    capital_manager = CapitalRecoveryManager(
        max_initial_capital=max_initial_capital,
        data_dir=f'{DATA_ROOT}/capital',
    )
    available_capital = capital_manager.get_available_capital()
    recovery = capital_manager.get_recovery_status()
    logger.info(f"✓ Capital today: ₹{available_capital:,.2f} | {recovery['message']}")

    broker_health = BrokerHealthMonitor(trader, check_interval=120, failure_threshold=3)
    market_calendar = MarketCalendar()

    # ------------------------------------------------------------------ #
    # 3. Agents                                                            #
    # ------------------------------------------------------------------ #
    scanner = MarketScanner(trader, max_symbols=10, min_price=50.0, min_volume=500_000)

    risk_gate = RiskGate(
        max_capital=available_capital,
        max_daily_loss=max_daily_loss,
        max_position_pct=0.15,
        max_concurrent_positions=4,
        stop_loss_pct=0.015,
        target_pct=0.025,           # kept in sync with PositionMonitor.target_pct
        min_risk_reward=MIN_RISK_REWARD,
        risk_per_trade_pct=0.01,    # risk 1% of capital per trade
    )

    execution = ExecutionAgent(trader, stop_loss_pct=0.015)

    # MarketScanner runs first; symbols will be populated below
    signal_engine = SignalEngine(
        trader=trader,
        symbols=[],         # filled after scan
        min_profit_margin=SIGNAL_MIN_PROFIT_MARGIN,
        buy_threshold=0.20,
        sell_threshold=0.80,
        risk_reward_ratio=SIGNAL_RISK_REWARD,
        max_position_pct=0.15,
        stop_loss_pct=0.015,
        confidence_threshold=0.55,
    )

    position_monitor = PositionMonitor(
        execution_agent=execution,
        risk_gate=risk_gate,
        trader=trader,
        stop_loss_pct=0.015,
        target_pct=0.025,
        trailing_stop_activation=0.010,
        trailing_stop_distance=0.008,
        max_hold_minutes=90,
    )

    post_trade = PostTradeAgent(
        capital_manager=capital_manager,
        signal_engine=signal_engine,
        data_dir=DATA_ROOT,
    )

    # Wire ExecutionAgent → RiskGate + PostTradeAgent callbacks
    execution.register_on_fill(
        lambda sym, typ, qty, price, pnl:
            risk_gate.record_fill(sym, typ, qty, price)
    )
    execution.register_on_fill(post_trade.on_fill)

    # WebSocket ticker — real-time stop monitoring (non-fatal if unavailable)
    ticker = PositionTicker(trader, position_monitor, execution)
    # Re-subscribe whenever a fill happens so new positions are watched instantly
    def _on_fill_update_ticker(sym, typ, qty, price, pnl):
        open_syms = list(execution.all_positions().keys())
        ticker.update_symbols(open_syms)
    execution.register_on_fill(_on_fill_update_ticker)

    # ------------------------------------------------------------------ #
    # 4. Wait for market open; do startup work when it opens              #
    # ------------------------------------------------------------------ #
    startup_done = False
    squared_off  = False
    last_reconcile = None
    iteration = 0

    # Daily-report bookkeeping
    funnel = {'buy_signals': 0, 'sell_signals': 0, 'shorts_skipped': 0,
              'approved': 0, 'blocked': 0, 'executed': 0}
    exit_counts: dict = {}
    end_reason = 'not started'
    completed_normally = False
    start_mins = None

    logger.info("⏳ Waiting for market open (9:15 AM IST)...")
    signals = {}

    try:
        while True:
            if _stop_requested():
                logger.warning("🛑 Stop requested — squaring off and exiting")
                end_reason = 'stopped by user'
                break

            now = datetime.now(IST)
            mins = now.hour * 60 + now.minute
            is_trading_day = market_calendar.is_trading_day(now.date())

            # ---- Weekend / Holiday ---- #
            if not is_trading_day:
                logger.info(f"Market closed ({now.strftime('%A')}). Exiting.")
                end_reason = 'not a trading day'
                break

            # ---- Before market open ---- #
            if mins < MARKET_OPEN:
                wait = MARKET_OPEN - mins
                logger.info(f"Market opens in {wait} min. Sleeping...")
                _write_status('waiting', iteration, risk_gate, post_trade,
                              execution, trader, signals, signal_engine.symbols,
                              scanner, signal_engine)
                _sleep(min(wait * 60, 60))
                continue

            # ---- After market close ---- #
            if mins > MARKET_CLOSE:
                logger.info("Market closed.")
                end_reason = 'market closed'
                break   # end-of-day accounting runs once, in `finally`

            # ---- Startup (runs once at market open) ---- #
            if not startup_done:
                _startup(
                    scanner, signal_engine, risk_gate,
                    execution, post_trade, position_monitor,
                    available_capital, trader,
                )
                ticker.start()   # WebSocket up after startup so credentials are valid
                startup_done = True
                start_mins = mins
                end_reason = 'interrupted'

            # ---- Square-off time ---- #
            if mins >= SQUARE_OFF and not squared_off:
                logger.info("⏰ Square-off time — closing all positions")
                n_open = len(execution.all_positions())
                if n_open:
                    exit_counts['EOD square-off'] = exit_counts.get('EOD square-off', 0) + n_open
                execution.square_off_all(reason="EOD square-off")
                squared_off = True
                time.sleep(10)
                continue

            if mins >= SQUARE_OFF:
                completed_normally = True
                end_reason = 'square-off reached'
                break   # square-off done — finish now instead of idling to 3:30 PM

            # ---- Broker health check ---- #
            health = broker_health.check_health()
            if health['should_halt']:
                logger.error(
                    f"🚨 Broker unreachable ({health['consecutive_failures']}x). Halting."
                )
                risk_gate.halted = True
                risk_gate.halt_reason = "Broker API unreachable"
                end_reason = 'broker unreachable'
                break
            if not health['is_healthy']:
                logger.warning("⚠️  Broker health check failed — skipping iteration")
                _sleep(CHECK_INTERVAL)
                continue

            # ---- Main iteration ---- #
            iteration += 1
            logger.info(
                f"\n{'─'*70}\n"
                f"  Iteration {iteration} — {now.strftime('%H:%M:%S IST')}\n"
                f"{'─'*70}"
            )

            # Step A: monitor positions first (stop-loss / trailing)
            signals = signal_engine.run_iteration()
            exits = position_monitor.monitor(signal_overrides=signals)
            if exits:
                logger.info(f"Exits this iteration: {exits}")
                for reason in exits.values():
                    key = str(reason).split(':')[0]
                    exit_counts[key] = exit_counts.get(key, 0) + 1

            # Step B: new entry signals
            if not risk_gate.halted:
                for symbol, signal in signals.items():
                    if execution.has_position(symbol):
                        continue   # already in — monitor handles exit
                    if signal not in ('BUY', 'SELL'):
                        continue

                    funnel['buy_signals' if signal == 'BUY' else 'sell_signals'] += 1
                    if signal == 'SELL' and not ENABLE_SHORTS:
                        funnel['shorts_skipped'] += 1
                        continue

                    # One quote call covers both BUY and SHORT evaluation
                    quote = trader.get_quote([symbol])
                    q = quote.get(f"NSE:{symbol}", {})
                    ltp      = q.get('last_price', 0)
                    day_high = q.get('ohlc', {}).get('high', ltp)
                    day_low  = q.get('ohlc', {}).get('low', ltp)

                    if signal == 'BUY':
                        decision = risk_gate.evaluate(symbol, 'BUY', ltp, day_high, day_low)
                        if decision.approved:
                            funnel['approved'] += 1
                            if execution.execute(symbol, decision, 'BUY'):
                                funnel['executed'] += 1
                            ticker.update_symbols(list(execution.all_positions().keys()))
                        else:
                            funnel['blocked'] += 1
                            logger.debug(f"RiskGate blocked BUY {symbol}: {decision.reason}")

                    elif signal == 'SELL':
                        # Short entry — opens a new short position via MIS
                        decision = risk_gate.evaluate_short(symbol, ltp, day_high, day_low)
                        if decision.approved:
                            funnel['approved'] += 1
                            if execution.execute(symbol, decision, 'SELL'):
                                funnel['executed'] += 1
                            ticker.update_symbols(list(execution.all_positions().keys()))
                        else:
                            funnel['blocked'] += 1
                            logger.debug(f"RiskGate blocked SHORT {symbol}: {decision.reason}")

            # Step C: periodic broker reconciliation (every 10 minutes)
            if (last_reconcile is None or
                    (datetime.now(IST) - last_reconcile).total_seconds() >= 600):
                execution.sync_from_broker()
                last_reconcile = datetime.now(IST)

            # Step D: status log
            rs = risk_gate.status()
            ps = post_trade.intraday_status()
            logger.info(
                f"💰 Capital: ₹{rs['available_capital']:,.2f} avail | "
                f"₹{rs['used_capital']:,.2f} used | "
                f"P&L: ₹{ps['daily_pnl']:+,.2f} | "
                f"Positions: {rs['open_positions']} | "
                f"Trades: {ps['daily_trades']} ({ps['daily_wins']}W/{ps['daily_losses']}L)"
            )

            # Step E: save models every 5 iterations
            if iteration % 5 == 0:
                signal_engine.save_models()

            _write_status('running', iteration, risk_gate, post_trade,
                          execution, trader, signals, signal_engine.symbols,
                          scanner, signal_engine)
            _sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        end_reason = 'interrupted'

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        end_reason = f'error: {e}'

    finally:
        logger.info("Saving final state...")
        try:
            ticker.stop()
            # Only do accounting for a session that actually started; otherwise a
            # holiday/weekend/early-stop run would record a bogus zero day.
            if startup_done:
                _end_of_day(post_trade, execution, risk_gate,
                            signal_engine, position_monitor)
                if PAPER:
                    # A day counts toward the paper-trading total only if it ran to
                    # square-off and was not a last-minute start.
                    complete = completed_normally and start_mins is not None and start_mins <= 12 * 60
                    if completed_normally and not complete:
                        end_reason = 'late start'
                    _write_paper_report(post_trade, risk_gate, execution, signal_engine,
                                        available_capital, funnel, exit_counts,
                                        complete, end_reason)
        except Exception as e:
            logger.error(f"Final cleanup error: {e}")
        _write_status('stopped' if _stop_requested() else 'ended', iteration,
                      risk_gate, post_trade, execution, trader, signals,
                      signal_engine.symbols, scanner, signal_engine)


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _startup(scanner, signal_engine, risk_gate, execution,
             post_trade, position_monitor, available_capital, trader):
    """One-time startup sequence at market open."""
    logger.info("\n🚀 Market open — running startup sequence")

    # 1. Scan for today's watchlist
    symbols = scanner.scan()
    signal_engine.symbols = symbols
    signal_engine.base_strategy.symbols = symbols
    logger.info(f"✓ Watchlist: {', '.join(symbols)}")

    # 2. Seed historical candles so multi-timeframe analysis is real
    logger.info("Seeding historical candle data...")
    signal_engine.seed_historical_data(days=5)

    # 3. Sync any overnight positions from broker
    execution.sync_from_broker()

    # 4. Reset daily state
    risk_gate.reset_daily(available_capital)
    signal_engine.reset_daily(available_capital)
    position_monitor.reset_daily()
    post_trade.start_day(available_capital)

    # 5. Market regime + VIX check (run at 9:45 AM after 30 min of Nifty data)
    #    Scales RiskGate stop_loss_pct and risk_per_trade_pct for today's conditions.
    cond = scanner.market_conditions()
    if cond['skip_day']:
        logger.warning(
            f"⚠️  Choppy-day regime detected (Nifty range {cond['nifty_range_pct']:.2%}). "
            f"Position sizes halved — only high-conviction signals will size up."
        )
    risk_gate.stop_loss_pct   = round(risk_gate.stop_loss_pct  * cond['stop_loss_mult'], 4)
    risk_gate.risk_per_trade_pct = round(risk_gate.risk_per_trade_pct * cond['size_mult'],   4)
    logger.info(
        f"✓ Market conditions: regime={cond['regime']} vix={cond['vix']} "
        f"→ stop={risk_gate.stop_loss_pct:.3f} risk_per_trade={risk_gate.risk_per_trade_pct:.3f}"
    )

    logger.info("✓ Startup complete")


def _end_of_day(post_trade, execution, risk_gate, signal_engine, position_monitor):
    """End-of-day cleanup and recording."""
    logger.info("\n📊 End of day — final cleanup")

    # Ensure all positions are closed
    if execution.all_positions():
        logger.warning("Positions still open at EOD — force closing")
        execution.square_off_all(reason="Force EOD close")
        time.sleep(5)

    rs = risk_gate.status()
    post_trade.end_day(used_capital=rs['used_capital'])
    signal_engine.save_models()
    try:
        signal_engine._online_model.save()   # persist the incremental model too
    except Exception as e:
        logger.warning(f"Online model save failed: {e}")


def _write_paper_report(post_trade, risk_gate, execution, signal_engine,
                        starting_capital, funnel, exit_counts, complete, end_reason):
    """Write today's paper-trading report (JSON + Markdown) and refresh SUMMARY.md."""
    from src.utils.paper_report import build_daily_report, write_daily_report
    try:
        ml = signal_engine.get_ml_status()
    except Exception:
        ml = {}
    report = build_daily_report(
        day=datetime.now(IST).date().isoformat(),
        trade_log=post_trade.trade_log,
        funnel=funnel,
        exits=exit_counts,
        starting_capital=starting_capital,
        max_drawdown=post_trade.max_drawdown,
        mode=MODE,
        complete=complete,
        end_reason=end_reason,
        open_positions=len(execution.all_positions()),
        ml_status=ml,
    )
    path = write_daily_report(report)
    wr = report['win_rate_gross_pct']
    wn = report['win_rate_net_pct']
    logger.info(
        f"📝 Paper report {path}: {report['closed_trades']} trades, "
        f"win rate {'n/a' if wr is None else f'{wr}%'} gross / "
        f"{'n/a' if wn is None else f'{wn}%'} net, net P&L ₹{report['net_pnl']:+,.2f}, "
        f"{'counts toward' if complete else 'does NOT count toward'} the {PAPER_MAX_DAYS}-day total"
    )


if __name__ == '__main__':
    main()
