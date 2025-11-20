#!/bin/bash
################################################################################
# AI Trading System - Complete Workflow Script
# 
# This script runs the entire AI trading workflow step by step:
# 1. Environment verification
# 2. System testing
# 3. Historical data training
# 4. Paper trading
# 5. Performance monitoring
#
# Author: AI Trading System
# Date: $(date +%Y-%m-%d)
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_step() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}📍 STEP $1: $2${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# Print header
clear
echo -e "${CYAN}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║         🤖 AI TRADING SYSTEM - COMPLETE WORKFLOW 🤖          ║
║                                                               ║
║   Automated Trading with Pattern Recognition & ML             ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo ""
log_info "Starting AI Trading System workflow..."
echo ""

# Step 0: Environment Check
log_step 0 "Environment Verification"

log_info "Checking Python version..."
python3 --version
if [ $? -ne 0 ]; then
    log_error "Python3 not found. Please install Python 3.8+"
    exit 1
fi
log_success "Python3 is available"

log_info "Checking virtual environment..."
if [ ! -d "venv" ]; then
    log_warning "Virtual environment not found. Creating one..."
    python3 -m venv venv
    log_success "Virtual environment created"
else
    log_success "Virtual environment exists"
fi

log_info "Activating virtual environment..."
source venv/bin/activate
log_success "Virtual environment activated"

log_info "Checking required directories..."
mkdir -p logs ai_data
log_success "Directories ready: logs/, ai_data/"

log_info "Checking .env file..."
if [ ! -f ".env" ]; then
    log_error ".env file not found!"
    log_info "Please create .env file with your Zerodha credentials"
    exit 1
fi
log_success ".env file exists"

log_info "Installing/Updating dependencies..."
pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    log_error "Failed to install dependencies"
    exit 1
fi
log_success "All dependencies installed"

echo ""
read -p "$(echo -e ${GREEN}✓ Environment ready! Press ENTER to continue...${NC})"

# Step 1: System Testing
log_step 1 "System Testing - Verify All Modules"

log_info "Running comprehensive system tests..."
echo ""

python test_ai_strategy.py

if [ $? -ne 0 ]; then
    log_error "System tests failed!"
    log_info "Please fix the errors before continuing"
    exit 1
fi

log_success "All system tests passed!"
echo ""
read -p "$(echo -e ${GREEN}✓ System verified! Press ENTER to continue to training...${NC})"

# Step 2: Historical Training
log_step 2 "AI Historical Training"

log_info "Training AI on historical market data..."
log_info "This will:"
log_info "  • Fetch 60 days of historical data from Zerodha"
log_info "  • Train pattern recognition models"
log_info "  • Train sentiment analysis"
log_info "  • Build predictive models"
log_info "  • Validate predictions"
echo ""

read -p "$(echo -e ${YELLOW}Continue with training? This may take 5-10 minutes [y/N]: ${NC})" -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_warning "Training skipped. You can run it later with: python train_ai_historical.py"
else
    echo ""
    log_info "Starting AI training..."
    python train_ai_historical.py
    
    if [ $? -ne 0 ]; then
        log_error "Training failed!"
        exit 1
    fi
    
    log_success "AI training completed!"
    
    # Show training results
    echo ""
    log_info "Training Results:"
    if [ -f "ai_data/training_stats.json" ]; then
        echo -e "${CYAN}"
        cat ai_data/training_stats.json | python3 -m json.tool 2>/dev/null || cat ai_data/training_stats.json
        echo -e "${NC}"
    fi
fi

echo ""
read -p "$(echo -e ${GREEN}✓ Training complete! Press ENTER to continue...${NC})"

# Step 3: Paper Trading Setup
log_step 3 "Paper Trading Configuration"

log_info "Paper Trading Setup:"
log_info "  • Initial Capital: ₹100,000 (virtual)"
log_info "  • Position Size: 8% per trade"
log_info "  • AI Confidence: 60%"
log_info "  • Risk: ZERO (virtual money only)"
echo ""

log_info "Paper trading will:"
log_info "  ✓ Use REAL market data from Zerodha"
log_info "  ✓ Execute trades with VIRTUAL money"
log_info "  ✓ Track performance metrics"
log_info "  ✓ Continue AI learning"
echo ""

read -p "$(echo -e ${YELLOW}Ready to start paper trading? [y/N]: ${NC})" -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_warning "Paper trading skipped."
    log_info "You can start it later with: python ai_paper_trader.py"
    echo ""
    log_step "FINAL" "Setup Complete!"
    log_success "All systems are ready!"
    echo ""
    log_info "Next steps:"
    echo "  1. Start paper trading: python ai_paper_trader.py"
    echo "  2. Monitor in another terminal: python monitor_ai.py"
    echo "  3. View logs: tail -f logs/paper_trading_\$(date +%Y%m%d).log"
    exit 0
fi

# Step 4: Start Paper Trading
log_step 4 "Starting Paper Trading"

log_info "Launching AI Paper Trading System..."
echo ""
log_warning "IMPORTANT: Keep this terminal open during market hours"
log_info "Market hours: 9:15 AM - 3:30 PM IST (Mon-Fri)"
echo ""
log_info "To monitor in another terminal, run:"
log_info "  $ python monitor_ai.py"
log_info "  $ tail -f logs/paper_trading_\$(date +%Y%m%d).log"
echo ""
log_info "To stop paper trading: Press Ctrl+C"
echo ""

read -p "$(echo -e ${GREEN}Press ENTER to start paper trading...${NC})"
echo ""

# Run paper trader
python ai_paper_trader.py

# This point is reached when paper trader is stopped
echo ""
log_info "Paper trading session ended"

# Step 5: Performance Summary
log_step 5 "Performance Summary"

log_info "Generating performance report..."
echo ""

if [ -f "ai_data/paper_trading_state.json" ]; then
    log_success "Paper Trading Results:"
    echo -e "${CYAN}"
    cat ai_data/paper_trading_state.json | python3 -m json.tool 2>/dev/null | head -50
    echo -e "${NC}"
fi

echo ""
log_info "Recent trades from logs:"
if ls logs/paper_trading_*.log 1> /dev/null 2>&1; then
    echo -e "${CYAN}"
    grep "PAPER TRADE" logs/paper_trading_*.log | tail -10 || log_warning "No trades found yet"
    echo -e "${NC}"
fi

echo ""
log_success "Session complete!"
echo ""

# Final recommendations
log_step "FINAL" "Next Steps & Recommendations"

echo ""
log_info "📊 Review Your Results:"
echo "  • Check paper trading state: cat ai_data/paper_trading_state.json | python -m json.tool"
echo "  • View pattern success: cat ai_data/patterns.json | python -m json.tool"
echo "  • Review today's trades: grep 'PAPER TRADE' logs/paper_trading_\$(date +%Y%m%d).log"
echo ""

log_info "🎯 Performance Targets:"
echo "  Week 1: Win rate 50-55% (Learning phase)"
echo "  Week 2: Win rate 55-65% (Pattern recognition)"
echo "  Week 3+: Win rate 65-75% (Optimized)"
echo ""

log_info "⚙️  Optimization:"
echo "  • Run training weekly: python train_ai_historical.py"
echo "  • Monitor daily: python monitor_ai.py"
echo "  • Adjust confidence in ai_paper_trader.py if needed"
echo ""

log_info "⚠️  Before Live Trading:"
echo "  • Paper trade for minimum 2 weeks"
echo "  • Achieve 60%+ win rate consistently"
echo "  • Test in different market conditions"
echo "  • Start with 10-20% of planned capital"
echo ""

log_success "AI Trading System is fully operational! 🚀"
echo ""
log_info "For help, see: QUICK_START.md, AI_WORKFLOW.md, PAPER_TRADING_GUIDE.md"
echo ""
