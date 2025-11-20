#!/bin/bash
# Project Reorganization Script
# Moves files to proper folder structure
# Generated: 2025-11-15

set -e

PROJECT_DIR="/Users/harshit/dev/go/src/github.com/stocks"
BACKUP_FILE="backup_before_reorg_$(date +%Y%m%d_%H%M%S).tar.gz"

echo "=================================================="
echo "Project Reorganization Script"
echo "=================================================="
echo ""

cd "$PROJECT_DIR"

# Create backup
echo "📦 Creating backup..."
tar -czf "$BACKUP_FILE" \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  . 2>/dev/null || true

if [ -f "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "✅ Backup created: $BACKUP_FILE ($BACKUP_SIZE)"
else
    echo "❌ Backup failed! Aborting."
    exit 1
fi

echo ""
echo "=================================================="
echo "PHASE 1: Create New Directory Structure"
echo "=================================================="

# Create main directories
mkdir -p docs
mkdir -p scripts
mkdir -p data/ai_data
mkdir -p data/logs
mkdir -p config
mkdir -p deployment
mkdir -p tests
mkdir -p backups
mkdir -p archive/cleanup_scripts
mkdir -p archive/old_logs
mkdir -p src/web/templates
mkdir -p src/web/static

echo "✅ Created new directory structure"

echo ""
echo "=================================================="
echo "PHASE 2: Move Documentation Files"
echo "=================================================="

# Move and rename documentation
[ -f "START_HERE.md" ] && mv START_HERE.md docs/getting-started.md && echo "  📄 START_HERE.md → docs/getting-started.md"
[ -f "COMPLETE_SYSTEM_GUIDE.md" ] && mv COMPLETE_SYSTEM_GUIDE.md docs/complete-guide.md && echo "  📄 COMPLETE_SYSTEM_GUIDE.md → docs/complete-guide.md"
[ -f "INTRADAY_STRATEGY.md" ] && mv INTRADAY_STRATEGY.md docs/strategy-guide.md && echo "  📄 INTRADAY_STRATEGY.md → docs/strategy-guide.md"
[ -f "PAPER_TRADING_GUIDE.md" ] && mv PAPER_TRADING_GUIDE.md docs/paper-trading.md && echo "  📄 PAPER_TRADING_GUIDE.md → docs/paper-trading.md"
[ -f "TRADING_PSYCHOLOGY.md" ] && mv TRADING_PSYCHOLOGY.md docs/trading-psychology.md && echo "  📄 TRADING_PSYCHOLOGY.md → docs/trading-psychology.md"

echo "✅ Documentation moved to docs/"

echo ""
echo "=================================================="
echo "PHASE 3: Move Script Files"
echo "=================================================="

# Move and rename scripts
[ -f "ai_paper_trader.py" ] && mv ai_paper_trader.py scripts/paper_trade.py && echo "  🐍 ai_paper_trader.py → scripts/paper_trade.py"
[ -f "train_ai_historical.py" ] && mv train_ai_historical.py scripts/train_ai.py && echo "  🐍 train_ai_historical.py → scripts/train_ai.py"
[ -f "get_access_token.py" ] && mv get_access_token.py scripts/get_token.py && echo "  🐍 get_access_token.py → scripts/get_token.py"

# Move shell scripts
[ -f "deploy.sh" ] && mv deploy.sh scripts/ && echo "  📜 deploy.sh → scripts/"
[ -f "start_app.sh" ] && mv start_app.sh scripts/ && echo "  📜 start_app.sh → scripts/"
[ -f "run_ai_system.sh" ] && mv run_ai_system.sh scripts/ && echo "  📜 run_ai_system.sh → scripts/"
[ -f "manage_scheduler.sh" ] && mv manage_scheduler.sh scripts/ && echo "  📜 manage_scheduler.sh → scripts/"
[ -f "test-local.sh" ] && mv test-local.sh scripts/ && echo "  📜 test-local.sh → scripts/"

echo "✅ Scripts moved to scripts/"

echo ""
echo "=================================================="
echo "PHASE 4: Move Web Dashboard Files"
echo "=================================================="

# Move app.py to src/web/
[ -f "app.py" ] && mv app.py src/web/ && echo "  🌐 app.py → src/web/"

# Move dashboard.html to templates
[ -f "dashboard.html" ] && mv dashboard.html src/web/templates/ && echo "  📄 dashboard.html → src/web/templates/"

# Move templates and static directories
if [ -d "templates" ] && [ "$(ls -A templates)" ]; then
    cp -r templates/* src/web/templates/ 2>/dev/null || true
    rm -rf templates
    echo "  📁 templates/ → src/web/templates/"
fi

if [ -d "static" ] && [ "$(ls -A static)" ]; then
    cp -r static/* src/web/static/ 2>/dev/null || true
    rm -rf static
    echo "  📁 static/ → src/web/static/"
fi

# Create __init__.py for web module
touch src/web/__init__.py

echo "✅ Web files moved to src/web/"

echo ""
echo "=================================================="
echo "PHASE 5: Move Data Files"
echo "=================================================="

# Move ai_data contents
if [ -d "ai_data" ]; then
    cp -r ai_data/* data/ai_data/ 2>/dev/null || true
    rm -rf ai_data
    echo "  📊 ai_data/ → data/ai_data/"
fi

# Move logs
if [ -d "logs" ]; then
    cp -r logs/* data/logs/ 2>/dev/null || true
    rm -rf logs
    echo "  📋 logs/ → data/logs/"
fi

echo "✅ Data files moved to data/"

echo ""
echo "=================================================="
echo "PHASE 6: Move Deployment Files"
echo "=================================================="

[ -f "Dockerfile" ] && mv Dockerfile deployment/ && echo "  🐳 Dockerfile → deployment/"
[ -f ".dockerignore" ] && mv .dockerignore deployment/ && echo "  📄 .dockerignore → deployment/"
[ -f "cloudbuild.yaml" ] && mv cloudbuild.yaml deployment/ && echo "  ☁️  cloudbuild.yaml → deployment/"
[ -f "cloudrun.yaml" ] && mv cloudrun.yaml deployment/ && echo "  ☁️  cloudrun.yaml → deployment/"

echo "✅ Deployment files moved to deployment/"

echo ""
echo "=================================================="
echo "PHASE 7: Move Configuration Files"
echo "=================================================="

# Create .env.example in config
if [ -f ".env" ]; then
    # Create example (without sensitive data)
    cat > config/.env.example << 'EOF'
# Zerodha Kite API Credentials
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
KITE_ACCESS_TOKEN=your_access_token_here

# Zerodha Login Credentials
ZERODHA_USER_ID=your_user_id
ZERODHA_PASSWORD=your_password
ZERODHA_PIN=your_pin

# Trading Configuration
MAX_POSITION_SIZE_PCT=0.1
ENABLE_PAPER_TRADING=true

# Strategy Configuration
RSI_PERIOD=14
RSI_OVERSOLD=30
RSI_OVERBOUGHT=70
MOMENTUM_THRESHOLD=0.02
MOMENTUM_LOOKBACK_DAYS=5

# Logging
LOG_LEVEL=INFO
EOF
    echo "  ⚙️  Created config/.env.example"
fi

# Move config directory if it exists
if [ -d "config" ] && [ "$(ls -A config 2>/dev/null | grep -v '.env.example')" ]; then
    echo "  ⚙️  config/ already exists"
fi

echo "✅ Configuration files organized"

echo ""
echo "=================================================="
echo "PHASE 8: Archive Old Files"
echo "=================================================="

# Move cleanup files to archive
[ -f "CLEANUP_ANALYSIS.md" ] && mv CLEANUP_ANALYSIS.md archive/cleanup_scripts/ && echo "  📦 CLEANUP_ANALYSIS.md → archive/"
[ -f "CLEANUP_SUMMARY.md" ] && mv CLEANUP_SUMMARY.md archive/cleanup_scripts/ && echo "  📦 CLEANUP_SUMMARY.md → archive/"
[ -f "cleanup_project.sh" ] && mv cleanup_project.sh archive/cleanup_scripts/ && echo "  📦 cleanup_project.sh → archive/"

# Move old backups
mv backup_before_cleanup_*.tar.gz backups/ 2>/dev/null || true
mv logs_archive_*.tar.gz archive/old_logs/ 2>/dev/null || true

# Move test output log
[ -f "test_output.log" ] && mv test_output.log archive/ && echo "  📄 test_output.log → archive/"

echo "✅ Old files archived"

echo ""
echo "=================================================="
echo "PHASE 9: Create __init__.py Files"
echo "=================================================="

# Ensure all packages have __init__.py
touch tests/__init__.py
touch src/web/__init__.py

echo "✅ Package files created"

echo ""
echo "=================================================="
echo "PHASE 10: Create .gitkeep Files"
echo "=================================================="

# Create .gitkeep for empty directories
touch backups/.gitkeep
touch tests/.gitkeep

echo "✅ .gitkeep files created"

echo ""
echo "=================================================="
echo "REORGANIZATION COMPLETE!"
echo "=================================================="
echo ""
echo "📊 New Structure:"
echo "  docs/          - All documentation (5 files)"
echo "  scripts/       - Executable scripts (8+ files)"
echo "  src/           - Core source code (organized modules)"
echo "  data/          - AI data and logs"
echo "  config/        - Configuration files"
echo "  deployment/    - Docker and cloud configs"
echo "  tests/         - Test files (empty, ready for tests)"
echo "  backups/       - Backup files"
echo "  archive/       - Old/temporary files"
echo ""
echo "✅ Root directory is now clean and organized!"
echo ""
echo "⚠️  IMPORTANT: Update imports in scripts/"
echo "   Run the fix_imports.sh script next"
echo ""
echo "Backup saved: $BACKUP_FILE"
echo ""
