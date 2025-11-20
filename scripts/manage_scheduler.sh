#!/bin/bash
# Script to manage the Zerodha Kite token refresh scheduler

PLIST_PATH="$HOME/Library/LaunchAgents/com.zerodha.kite.tokenrefresh.plist"
LOG_DIR="$HOME/dev/go/src/github.com/stocks/logs"

case "$1" in
    start)
        echo "Starting token refresh scheduler..."
        launchctl load "$PLIST_PATH"
        echo "✓ Scheduler started (runs daily at 8:45 AM)"
        ;;
    stop)
        echo "Stopping token refresh scheduler..."
        launchctl unload "$PLIST_PATH"
        echo "✓ Scheduler stopped"
        ;;
    status)
        echo "Checking scheduler status..."
        if launchctl list | grep -q "com.zerodha.kite.tokenrefresh"; then
            echo "✓ Scheduler is RUNNING"
            echo ""
            echo "Next run: Daily at 8:45 AM"
        else
            echo "✗ Scheduler is NOT running"
        fi
        ;;
    logs)
        echo "Recent logs:"
        echo "─────────────────────────────────────────────────"
        tail -n 20 "$LOG_DIR/token_refresh.log" 2>/dev/null || echo "No logs yet"
        ;;
    test)
        echo "Running token refresh manually..."
        cd "$HOME/dev/go/src/github.com/stocks"
        source venv/bin/activate && python auto_login.py
        ;;
    *)
        echo "Usage: $0 {start|stop|status|logs|test}"
        echo ""
        echo "Commands:"
        echo "  start   - Enable automatic token refresh"
        echo "  stop    - Disable automatic token refresh"
        echo "  status  - Check if scheduler is running"
        echo "  logs    - View recent logs"
        echo "  test    - Run token refresh manually"
        exit 1
        ;;
esac
