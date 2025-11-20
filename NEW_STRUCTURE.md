# New Professional Folder Structure

## 🎯 Design Goals
- Clean root directory (only essential files)
- Logical grouping of related files
- Industry-standard naming conventions
- Easy to navigate and understand
- Scalable for future growth

## 📁 Proposed Structure

```
stocks/
├── README.md                   # Project overview
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (gitignored)
├── .gitignore                 # Git ignore rules
│
├── docs/                      # 📚 All documentation
│   ├── README.md              # Documentation index
│   ├── getting-started.md     # Quick start (renamed START_HERE.md)
│   ├── complete-guide.md      # Full guide (renamed COMPLETE_SYSTEM_GUIDE.md)
│   ├── strategy-guide.md      # Strategy details (renamed INTRADAY_STRATEGY.md)
│   ├── paper-trading.md       # Paper trading (renamed PAPER_TRADING_GUIDE.md)
│   ├── trading-psychology.md  # Psychology (renamed TRADING_PSYCHOLOGY.md)
│   └── architecture.md        # System architecture (new)
│
├── scripts/                   # 🚀 Executable scripts
│   ├── paper_trade.py         # Main paper trading (renamed ai_paper_trader.py)
│   ├── train_ai.py            # AI training (renamed train_ai_historical.py)
│   ├── get_token.py           # Token utility (renamed get_access_token.py)
│   ├── run_dashboard.py       # Dashboard runner (renamed app.py)
│   ├── deploy.sh              # Deployment script
│   ├── start_app.sh           # App starter
│   ├── run_ai_system.sh       # Complete workflow
│   └── manage_scheduler.sh    # Scheduler management
│
├── src/                       # 💻 Core source code
│   ├── __init__.py
│   ├── ai_modules/            # AI components
│   │   ├── __init__.py
│   │   ├── pattern_recognition.py
│   │   ├── predictive_model.py
│   │   ├── sentiment_analyzer.py
│   │   └── trading_psychology.py
│   ├── kite_trader/           # Zerodha integration
│   │   ├── __init__.py
│   │   └── trader.py
│   ├── paper_trading/         # Paper trading engine
│   │   ├── __init__.py
│   │   └── paper_trader.py
│   ├── strategies/            # Trading strategies
│   │   ├── __init__.py
│   │   ├── base_strategy.py
│   │   ├── ai_intraday_strategy.py
│   │   └── intraday_high_low_strategy.py
│   ├── utils/                 # Utilities
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── logger.py
│   └── web/                   # Web dashboard (new folder)
│       ├── __init__.py
│       ├── app.py             # FastAPI app
│       ├── templates/         # HTML templates
│       └── static/            # CSS, JS, images
│
├── data/                      # 📊 Data storage
│   ├── ai_data/               # AI models & state (renamed from ai_data/)
│   │   ├── model.json
│   │   ├── patterns.json
│   │   ├── sentiment.json
│   │   ├── training_stats.json
│   │   └── paper_trading_state.json
│   └── logs/                  # Application logs (moved from root)
│       ├── paper_trading_*.log
│       └── ai_training_*.log
│
├── config/                    # ⚙️ Configuration files
│   ├── .env.example           # Example environment file
│   └── symbols.json           # Trading symbols list (new)
│
├── deployment/                # 🚀 Deployment configs
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── cloudbuild.yaml
│   └── cloudrun.yaml
│
├── tests/                     # 🧪 Test files (empty now, for future)
│   └── __init__.py
│
├── backups/                   # 💾 Backup files (new)
│   └── .gitkeep
│
└── archive/                   # 📦 Old/temp files (new)
    ├── cleanup_scripts/
    │   ├── cleanup_project.sh
    │   ├── CLEANUP_ANALYSIS.md
    │   └── CLEANUP_SUMMARY.md
    └── old_logs/
        └── logs_archive_*.tar.gz
```

## 📋 File Movements

### Root → docs/
- START_HERE.md → docs/getting-started.md
- COMPLETE_SYSTEM_GUIDE.md → docs/complete-guide.md
- INTRADAY_STRATEGY.md → docs/strategy-guide.md
- PAPER_TRADING_GUIDE.md → docs/paper-trading.md
- TRADING_PSYCHOLOGY.md → docs/trading-psychology.md

### Root → scripts/
- ai_paper_trader.py → scripts/paper_trade.py
- train_ai_historical.py → scripts/train_ai.py
- get_access_token.py → scripts/get_token.py
- app.py → scripts/run_dashboard.py (or src/web/app.py)
- *.sh scripts → scripts/

### Root → data/
- ai_data/ → data/ai_data/
- logs/ → data/logs/

### Root → deployment/
- Dockerfile → deployment/
- .dockerignore → deployment/
- cloudbuild.yaml → deployment/
- cloudrun.yaml → deployment/

### Root → archive/
- CLEANUP_*.md → archive/cleanup_scripts/
- cleanup_project.sh → archive/cleanup_scripts/
- logs_archive_*.tar.gz → archive/old_logs/
- backup_before_cleanup_*.tar.gz → backups/

### Web files → src/web/
- templates/ → src/web/templates/
- static/ → src/web/static/
- dashboard.html → src/web/templates/dashboard.html

## 🔧 Files to Update

After moving, these files need path updates:

1. **scripts/paper_trade.py** - Update imports from root to proper paths
2. **scripts/train_ai.py** - Update data paths
3. **scripts/run_dashboard.py** - Update template/static paths
4. **All scripts/** - Add sys.path.insert for src/ imports
5. **src/web/app.py** - Update template/static folder paths

## 🎯 Final Root Directory

After reorganization, root will only have:
```
stocks/
├── README.md
├── requirements.txt
├── .env
├── .gitignore
├── docs/
├── scripts/
├── src/
├── data/
├── config/
├── deployment/
├── tests/
├── backups/
└── archive/
```

**Clean, professional, and organized! ✨**

## 🚀 Benefits

1. **Clean Root** - Only essential files visible
2. **Clear Purpose** - Each folder has specific role
3. **Easy Navigation** - Find files quickly
4. **Standard Layout** - Follows Python project conventions
5. **Scalable** - Easy to add new features
6. **Professional** - Ready for production/sharing
