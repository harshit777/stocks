#!/bin/bash
# Startup script for the trading app

echo "🚀 Starting Trading App..."
echo ""

# Activate virtual environment
source venv/bin/activate

# Check if access token needs refresh
echo "📝 Checking Zerodha connection..."
python3 main.py 2>&1 | grep -q "Incorrect.*access_token"

if [ $? -eq 0 ]; then
    echo "⚠️  Access token expired. Please refresh it:"
    echo ""
    echo "   Run: python3 scripts/get_token.py"
    echo "   Or:  python3 auto_login.py"
    echo ""
    exit 1
fi

# Start the app
echo "✅ Starting FastAPI app..."
echo ""
echo "Dashboard will be available at: http://0.0.0.0:8000"
echo ""

venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 --reload
