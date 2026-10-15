#!/bin/bash
# ─────────────────────────────────────────────
#  start.sh — start the trading dashboard
#  Usage: ./start.sh
# ─────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

PY="python3"

# ── 1. Check .env ─────────────────────────────
if [ ! -f ".env" ]; then
  echo "⚠️  .env not found — creating from example"
  cp config/.env.example .env
  echo "👉  Edit .env and add your KITE credentials, then re-run."
  exit 1
fi

# ── 2. Quick dep check ────────────────────────
$PY -c "import fastapi, uvicorn, kiteconnect, sklearn" 2>/dev/null || {
  echo "📦  Installing dependencies..."
  $PY -m pip install -q -r requirements.txt
}

# ── 3. Auto-refresh Kite access token ─────────
echo "🔑  Refreshing Kite access token..."
if $PY kite_auth.py; then
  echo "✓  Token updated"
else
  echo "⚠️  Token refresh failed — using existing token (may be expired)"
fi

# ── 4. Make sure data dirs exist ─────────────
mkdir -p data/logs data/ml data/capital

# ── 5. Launch ─────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  🚀  Trading Dashboard"
echo "  📊  http://localhost:8000/live-trading"
echo "  Press Ctrl+C to stop"
echo "══════════════════════════════════════════"
echo ""

$PY -m uvicorn src.web.app:app --host 0.0.0.0 --port 8000 --reload
