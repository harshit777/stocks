#!/bin/bash
# Project Cleanup Script
# Generated: 2025-11-15
# 
# This script removes unused files and cleans up the project structure
# A backup is created before any removal

set -e  # Exit on error

PROJECT_DIR="/Users/harshit/dev/go/src/github.com/stocks"
BACKUP_FILE="backup_before_cleanup_$(date +%Y%m%d_%H%M%S).tar.gz"

echo "=================================================="
echo "Project Cleanup Script"
echo "=================================================="
echo ""

# Change to project directory
cd "$PROJECT_DIR"

# Create backup first
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
    echo "❌ Backup failed! Aborting cleanup."
    exit 1
fi

echo ""
echo "=================================================="
echo "PHASE 1: Remove Python Cache"
echo "=================================================="

# Remove __pycache__ directories
PYCACHE_COUNT=$(find . -type d -name "__pycache__" | wc -l | tr -d ' ')
if [ "$PYCACHE_COUNT" -gt 0 ]; then
    echo "Removing $PYCACHE_COUNT __pycache__ directories..."
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    echo "✅ Removed Python cache directories"
else
    echo "✅ No __pycache__ directories found"
fi

# Remove .pyc files
PYC_COUNT=$(find . -name "*.pyc" -type f | wc -l | tr -d ' ')
if [ "$PYC_COUNT" -gt 0 ]; then
    echo "Removing $PYC_COUNT .pyc files..."
    find . -name "*.pyc" -type f -delete 2>/dev/null || true
    echo "✅ Removed .pyc files"
else
    echo "✅ No .pyc files found"
fi

echo ""
echo "=================================================="
echo "PHASE 2: Archive Old Logs"
echo "=================================================="

# Archive logs older than 7 days
LOG_DIR="logs"
if [ -d "$LOG_DIR" ]; then
    OLD_LOGS=$(find "$LOG_DIR" -name "*.log" -type f -mtime +7 | wc -l | tr -d ' ')
    if [ "$OLD_LOGS" -gt 0 ]; then
        echo "Archiving $OLD_LOGS logs older than 7 days..."
        mkdir -p logs_archive
        find "$LOG_DIR" -name "*.log" -type f -mtime +7 -exec mv {} logs_archive/ \; 2>/dev/null || true
        
        # Compress archive
        if [ -d "logs_archive" ] && [ "$(ls -A logs_archive)" ]; then
            tar -czf "logs_archive_$(date +%Y%m%d).tar.gz" logs_archive/
            rm -rf logs_archive/
            echo "✅ Old logs archived to logs_archive_$(date +%Y%m%d).tar.gz"
        fi
    else
        echo "✅ No old logs to archive"
    fi
fi

echo ""
echo "=================================================="
echo "PHASE 3: Remove Test & Debug Scripts"
echo "=================================================="

# Test and debug scripts to remove
TEST_FILES=(
    "test_ai_strategy.py"
    "test_fixes.py"
    "test_get_ltp_extensive.py"
    "test_model_learning.py"
    "test_psychology_guard.py"
    "test_symbol_removal.py"
    "test_symbol_validation.py"
    "debug_no_trades.py"
    "verify_symbol_update.py"
)

REMOVED_COUNT=0
for file in "${TEST_FILES[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        echo "  ❌ Removed: $file"
        REMOVED_COUNT=$((REMOVED_COUNT + 1))
    fi
done

echo "✅ Removed $REMOVED_COUNT test/debug scripts"

echo ""
echo "=================================================="
echo "PHASE 4: Remove Utility Scripts"
echo "=================================================="

# Utility scripts (rarely needed)
UTILITY_FILES=(
    "clean_invalid_symbols.py"
    "force_remove_failing_symbols.py"
    "close_paper_positions.py"
    "list_portfolio.py"
    "auto_login.py"
)

REMOVED_COUNT=0
for file in "${UTILITY_FILES[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        echo "  ❌ Removed: $file"
        REMOVED_COUNT=$((REMOVED_COUNT + 1))
    fi
done

echo "✅ Removed $REMOVED_COUNT utility scripts"

echo ""
echo "=================================================="
echo "PHASE 5: Remove Duplicate Entry Points"
echo "=================================================="

# Duplicate/old entry points
DUPLICATE_FILES=(
    "ai_intraday_trader.py"
    "intraday_trader_example.py"
    "main.py"
    "dashboard.py"
    "monitor_ai.py"
)

REMOVED_COUNT=0
for file in "${DUPLICATE_FILES[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        echo "  ❌ Removed: $file"
        REMOVED_COUNT=$((REMOVED_COUNT + 1))
    fi
done

echo "✅ Removed $REMOVED_COUNT duplicate scripts"

echo ""
echo "=================================================="
echo "PHASE 6: Remove Unused Strategies"
echo "=================================================="

# Remove non-AI strategies
STRATEGY_FILES=(
    "src/strategies/momentum_strategy.py"
    "src/strategies/rsi_strategy.py"
    "src/strategies/strategy_manager.py"
)

REMOVED_COUNT=0
for file in "${STRATEGY_FILES[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        echo "  ❌ Removed: $file"
        REMOVED_COUNT=$((REMOVED_COUNT + 1))
    fi
done

echo "✅ Removed $REMOVED_COUNT unused strategy files"

echo ""
echo "=================================================="
echo "PHASE 7: Remove Historical Documentation"
echo "=================================================="

# Historical fix/implementation summaries
HISTORY_DOCS=(
    "AI_MODEL_FIX_SUMMARY.md"
    "FIX_SUMMARY.md"
    "PAPER_TRADING_FIX.md"
    "SYMBOL_VALIDATION_FIX.md"
    "SYMBOL_UPDATE_SUMMARY.md"
    "IMPLEMENTATION_SUMMARY.md"
    "PSYCHOLOGY_IMPROVEMENT_SUMMARY.md"
    "PAPER_TRADING_UI_UPDATE.md"
    "EOD_POSITION_CLEARING.md"
)

REMOVED_COUNT=0
for file in "${HISTORY_DOCS[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        echo "  ❌ Removed: $file"
        REMOVED_COUNT=$((REMOVED_COUNT + 1))
    fi
done

echo "✅ Removed $REMOVED_COUNT historical docs"

echo ""
echo "=================================================="
echo "PHASE 8: Remove Duplicate Documentation"
echo "=================================================="

# Duplicate/overlapping guides
DUPLICATE_DOCS=(
    "QUICK_START.md"
    "QUICKSTART_INTRADAY.md"
    "AI_WORKFLOW.md"
    "AI_COMMANDS.md"
    "PSYCHOLOGY_QUICK_REF.md"
    "AI_TRAINING_STOCK_PERFORMANCE.md"
    "STOCK_PERFORMANCE_MOCKUP.md"
    "SYMBOL_REMOVAL_GUIDE.md"
    "DEPLOYMENT.md"
    "NEXT_STEPS_COMPLETE.md"
    "TEST_RESULTS.md"
    "QUICK_REFERENCE.md"
    "AI_TRADING_SYSTEM.md"
)

REMOVED_COUNT=0
for file in "${DUPLICATE_DOCS[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        echo "  ❌ Removed: $file"
        REMOVED_COUNT=$((REMOVED_COUNT + 1))
    fi
done

echo "✅ Removed $REMOVED_COUNT duplicate docs"

echo ""
echo "=================================================="
echo "CLEANUP COMPLETE!"
echo "=================================================="
echo ""
echo "📊 Summary:"
echo "  - Backup saved: $BACKUP_FILE"
echo "  - Python cache cleaned"
echo "  - Old logs archived"
echo "  - Unused scripts removed"
echo "  - Documentation consolidated"
echo ""
echo "📁 Core files remaining:"
echo "  - ai_paper_trader.py (main entry point)"
echo "  - train_ai_historical.py (AI training)"
echo "  - get_access_token.py (token utility)"
echo "  - app.py (dashboard & monitoring)"
echo "  - src/ directory (core modules)"
echo "  - 6 essential documentation files"
echo ""
echo "✅ Project structure is now clean!"
echo ""
echo "To verify, run:"
echo "  ls -la"
echo "  ls -la src/"
echo ""
echo "To restore if needed:"
echo "  tar -xzf $BACKUP_FILE"
echo ""
