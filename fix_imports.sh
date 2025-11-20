#!/bin/bash
# Fix Imports After Reorganization
# Updates path references in moved scripts
# Generated: 2025-11-15

set -e

PROJECT_DIR="/Users/harshit/dev/go/src/github.com/stocks"

echo "=================================================="
echo "Fix Imports Script"
echo "=================================================="
echo ""

cd "$PROJECT_DIR"

echo "Fixing imports in scripts/..."

# Fix scripts/paper_trade.py
if [ -f "scripts/paper_trade.py" ]; then
    echo "  📝 Fixing scripts/paper_trade.py"
    
    # Add sys.path insert at the top (after imports)
    sed -i.bak '1,/^from dotenv import load_dotenv/s/from dotenv import load_dotenv/import sys\nimport os\n\n# Add project root to path\nPROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nsys.path.insert(0, PROJECT_ROOT)\n\nfrom dotenv import load_dotenv/' scripts/paper_trade.py
    
    # Update data directory paths
    sed -i.bak "s/'ai_data'/'data\/ai_data'/g" scripts/paper_trade.py
    sed -i.bak "s/logs\/paper_trading_/data\/logs\/paper_trading_/g" scripts/paper_trade.py
    
    rm scripts/paper_trade.py.bak
    echo "  ✅ Fixed scripts/paper_trade.py"
fi

# Fix scripts/train_ai.py
if [ -f "scripts/train_ai.py" ]; then
    echo "  📝 Fixing scripts/train_ai.py"
    
    # Add sys.path insert at the top
    sed -i.bak '1,/^from dotenv import load_dotenv/s/from dotenv import load_dotenv/import sys\nimport os\n\n# Add project root to path\nPROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nsys.path.insert(0, PROJECT_ROOT)\n\nfrom dotenv import load_dotenv/' scripts/train_ai.py
    
    # Update data directory paths
    sed -i.bak "s/'ai_data'/'data\/ai_data'/g" scripts/train_ai.py
    sed -i.bak "s/logs\/ai_training_/data\/logs\/ai_training_/g" scripts/train_ai.py
    
    rm scripts/train_ai.py.bak
    echo "  ✅ Fixed scripts/train_ai.py"
fi

# Fix scripts/get_token.py
if [ -f "scripts/get_token.py" ]; then
    echo "  📝 Fixing scripts/get_token.py"
    
    # Add sys.path insert
    sed -i.bak '1,/^import/s/^import/import sys\nimport os\n\n# Add project root to path\nPROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nsys.path.insert(0, PROJECT_ROOT)\n\nimport/' scripts/get_token.py
    
    rm scripts/get_token.py.bak 2>/dev/null || true
    echo "  ✅ Fixed scripts/get_token.py"
fi

# Fix src/web/app.py
if [ -f "src/web/app.py" ]; then
    echo "  📝 Fixing src/web/app.py"
    
    # Update template and static paths
    sed -i.bak 's/templates=/templates=os.path.join(os.path.dirname(__file__), "templates")/g' src/web/app.py
    sed -i.bak 's/directory="static"/directory=os.path.join(os.path.dirname(__file__), "static")/g' src/web/app.py
    
    # Update data paths
    sed -i.bak "s/'ai_data'/'data\/ai_data'/g" src/web/app.py
    sed -i.bak "s/logs\//data\/logs\//g" src/web/app.py
    
    rm src/web/app.py.bak
    echo "  ✅ Fixed src/web/app.py"
fi

# Fix shell scripts
for script in scripts/*.sh; do
    if [ -f "$script" ]; then
        echo "  📝 Fixing $script"
        
        # Update python script paths
        sed -i.bak 's/python3 ai_paper_trader.py/python3 scripts\/paper_trade.py/g' "$script"
        sed -i.bak 's/python3 train_ai_historical.py/python3 scripts\/train_ai.py/g' "$script"
        sed -i.bak 's/python3 get_access_token.py/python3 scripts\/get_token.py/g' "$script"
        sed -i.bak 's/python3 app.py/python3 -m src.web.app/g' "$script"
        
        rm "$script.bak" 2>/dev/null || true
    fi
done

echo "  ✅ Fixed shell scripts"

# Fix paper trading state path references
if [ -f "src/paper_trading/paper_trader.py" ]; then
    echo "  📝 Fixing src/paper_trading/paper_trader.py"
    
    # Already uses data_dir parameter, just document the change
    echo "  ℹ️  PaperTrader uses data_dir parameter (OK)"
fi

# Fix AI modules path references
for module in src/ai_modules/*.py; do
    if [ -f "$module" ] && grep -q "'ai_data'" "$module"; then
        echo "  📝 Fixing $module"
        sed -i.bak "s/'ai_data'/'data\/ai_data'/g" "$module"
        rm "$module.bak"
        echo "  ✅ Fixed $module"
    fi
done

echo ""
echo "=================================================="
echo "Creating Helper Scripts"
echo "=================================================="

# Create run_paper_trading.sh helper
cat > scripts/run_paper_trading.sh << 'EOF'
#!/bin/bash
# Quick launch script for paper trading
cd "$(dirname "$0")/.."
python3 scripts/paper_trade.py
EOF
chmod +x scripts/run_paper_trading.sh
echo "  ✅ Created scripts/run_paper_trading.sh"

# Create run_dashboard.sh helper
cat > scripts/run_dashboard.sh << 'EOF'
#!/bin/bash
# Quick launch script for dashboard
cd "$(dirname "$0")/.."
python3 -m src.web.app
EOF
chmod +x scripts/run_dashboard.sh
echo "  ✅ Created scripts/run_dashboard.sh"

# Create train_model.sh helper
cat > scripts/train_model.sh << 'EOF'
#!/bin/bash
# Quick launch script for AI training
cd "$(dirname "$0")/.."
python3 scripts/train_ai.py
EOF
chmod +x scripts/train_model.sh
echo "  ✅ Created scripts/train_model.sh"

echo ""
echo "=================================================="
echo "IMPORT FIXES COMPLETE!"
echo "=================================================="
echo ""
echo "✅ All imports updated for new structure"
echo ""
echo "Quick launch commands:"
echo "  ./scripts/run_paper_trading.sh  - Start paper trading"
echo "  ./scripts/train_model.sh        - Train AI models"
echo "  ./scripts/run_dashboard.sh      - Start web dashboard"
echo ""
echo "Or from root directory:"
echo "  python3 scripts/paper_trade.py"
echo "  python3 scripts/train_ai.py"
echo "  python3 -m src.web.app"
echo ""
