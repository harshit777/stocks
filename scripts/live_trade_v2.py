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

Required env vars (config/.env):
  KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN
  TRADING_MODE=live
  MAX_LIVE_CAPITAL=1000
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

os.makedirs('data/logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s — %(message)s',
    handlers=[
        logging.FileHandler(
            f"data/logs/live_{datetime.now().strftime('%Y%m%d')}.log"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger('main')

# Keep the last log lines in memory so they can be published in status.json
_log_tail: deque = deque(maxlen=60)


class _TailHandler(logging.Handler):
    def emit(self, record):
        _log_tail.append(f"{datetime.now().strftime('%H:%M:%S')} {record.levelname} {record.getMessage()}")


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


def _write_status(state, iteration, risk_gate, post_trade, execution, trader,
                  signals, watchlist):
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
                'avg_price': round(pos.avg_price, 2), 'ltp': round(ltp, 2),
                'pnl': round(pos.unrealised_pnl(ltp), 2),
                'stop_price': round(pos.stop_price, 2),
            })
        snapshot = {
            'state': state,
            'updated_at': datetime.now(IST).isoformat(),
            'iteration': iteration,
            'risk': risk_gate.status(),
            'post_trade': post_trade.intraday_status(),
            'positions': positions,
            'watchlist': list(watchlist or []),
            'signals': {k: v for k, v in (signals or {}).items() if v},
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
    if os.getenv('TRADING_MODE') != 'live':
        logger.error("TRADING_MODE must be 'live'. Exiting for safety.")
        return

    max_initial_capital = float(os.getenv('MAX_LIVE_CAPITAL', '1000'))
    max_daily_loss      = float(os.getenv('MAX_DAILY_LOSS', str(max_initial_capital * 0.10)))

    logger.info("=" * 70)
    logger.info("⚠️  LIVE INTRADAY TRADING — REAL MONEY")
    logger.info(f"   Capital: ₹{max_initial_capital:,.0f} | Max loss: ₹{max_daily_loss:,.0f}")
    logger.info("=" * 70)

    # ------------------------------------------------------------------ #
    # 1. Imports (deferred so env is loaded first)                        #
    # ------------------------------------------------------------------ #
    from src.kite_trader.trader import KiteTrader
    from src.utils.capital_manager import CapitalRecoveryManager
    from src.utils.broker_health import BrokerHealthMonitor
    from src.utils.market_calendar import MarketCalendar

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
    trader = KiteTrader(enable_order_manager=True, enable_rate_limiter=True)
    if not trader.is_connected():
        logger.error("Cannot connect to Zerodha — check KITE_ACCESS_TOKEN. Exiting.")
        return

    logger.info("✓ Connected to Zerodha")

    capital_manager = CapitalRecoveryManager(max_initial_capital=max_initial_capital)
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
        min_risk_reward=3.0,
        risk_per_trade_pct=0.01,    # risk 1% of capital per trade
    )

    execution = ExecutionAgent(trader, stop_loss_pct=0.015)

    # MarketScanner runs first; symbols will be populated below
    signal_engine = SignalEngine(
        trader=trader,
        symbols=[],         # filled after scan
        min_profit_margin=0.02,
        buy_threshold=0.20,
        sell_threshold=0.80,
        risk_reward_ratio=3.0,
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
        data_dir='data',
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

    logger.info("⏳ Waiting for market open (9:15 AM IST)...")
    signals = {}

    try:
        while True:
            if _stop_requested():
                logger.warning("🛑 Stop requested — squaring off and exiting")
                break

            now = datetime.now(IST)
            mins = now.hour * 60 + now.minute
            is_trading_day = market_calendar.is_trading_day(now.date())

            # ---- Weekend / Holiday ---- #
            if not is_trading_day:
                logger.info(f"Market closed ({now.strftime('%A')}). Exiting.")
                break

            # ---- Before market open ---- #
            if mins < MARKET_OPEN:
                wait = MARKET_OPEN - mins
                logger.info(f"Market opens in {wait} min. Sleeping...")
                _write_status('waiting', iteration, risk_gate, post_trade,
                              execution, trader, signals, signal_engine.symbols)
                _sleep(min(wait * 60, 60))
                continue

            # ---- After market close ---- #
            if mins > MARKET_CLOSE:
                logger.info("Market closed.")
                _end_of_day(post_trade, execution, risk_gate,
                            signal_engine, position_monitor)
                break

            # ---- Startup (runs once at market open) ---- #
            if not startup_done:
                _startup(
                    scanner, signal_engine, risk_gate,
                    execution, post_trade, position_monitor,
                    available_capital, trader,
                )
                ticker.start()   # WebSocket up after startup so credentials are valid
                startup_done = True

            # ---- Square-off time ---- #
            if mins >= SQUARE_OFF and not squared_off:
                logger.info("⏰ 3:20 PM — squaring off all positions")
                execution.square_off_all(reason="EOD square-off")
                squared_off = True
                time.sleep(10)
                continue

            if mins >= SQUARE_OFF:
                break   # square-off done — finish now instead of idling to 3:30 PM

            # ---- Broker health check ---- #
            health = broker_health.check_health()
            if health['should_halt']:
                logger.error(
                    f"🚨 Broker unreachable ({health['consecutive_failures']}x). Halting."
                )
                risk_gate.halted = True
                risk_gate.halt_reason = "Broker API unreachable"
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

            # Step B: new entry signals
            if not risk_gate.halted:
                for symbol, signal in signals.items():
                    if execution.has_position(symbol):
                        continue   # already in — monitor handles exit
                    if signal not in ('BUY', 'SELL'):
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
                            execution.execute(symbol, decision, 'BUY')
                            ticker.update_symbols(list(execution.all_positions().keys()))
                        else:
                            logger.debug(f"RiskGate blocked BUY {symbol}: {decision.reason}")

                    elif signal == 'SELL':
                        # Short entry — opens a new short position via MIS
                        decision = risk_gate.evaluate_short(symbol, ltp, day_high, day_low)
                        if decision.approved:
                            execution.execute(symbol, decision, 'SELL')
                            ticker.update_symbols(list(execution.all_positions().keys()))
                        else:
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
                          execution, trader, signals, signal_engine.symbols)
            _sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)

    finally:
        logger.info("Saving final state...")
        try:
            ticker.stop()
            _end_of_day(post_trade, execution, risk_gate,
                        signal_engine, position_monitor)
        except Exception as e:
            logger.error(f"Final cleanup error: {e}")
        _write_status('stopped' if _stop_requested() else 'ended', iteration,
                      risk_gate, post_trade, execution, trader, signals,
                      signal_engine.symbols)


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


if __name__ == '__main__':
    main()
