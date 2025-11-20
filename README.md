# AI-Powered Trading System for Zerodha Kite

An intelligent, AI-driven paper trading system that learns from market patterns and continuously improves its trading decisions.

## ✨ Features

- 🤖 **AI-Powered Strategy**: Machine learning-based pattern recognition and prediction
- 📊 **Multiple AI Modules**:
  - Pattern Recognition: Detects candlestick patterns and learns success rates
  - Sentiment Analysis: Analyzes market mood and momentum
  - Predictive Model: Multi-timeframe price predictions
  - Psychology Guard: Emotion-free decision making
- 💰 **Paper Trading**: Test with virtual money using real market data
- 🎯 **Risk Management**: Intelligent position sizing and stop-loss management
- 📝 **Comprehensive Logging**: Detailed tracking of all trades and AI decisions
- ⚙️ **Production Ready**: Clean, professional codebase with proper structure

## 📁 Project Structure

```
stocks/
├── README.md                  # Project overview
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (not in git)
├── .gitignore                 # Git ignore rules
├──
├── docs/                      # 📚 All documentation
│   ├── getting-started.md     # Quick start guide
│   ├── complete-guide.md      # Full system documentation
│   ├── strategy-guide.md      # Trading strategy details
│   ├── paper-trading.md       # Paper trading guide
│   └── trading-psychology.md  # Psychology insights
│
├── scripts/                   # 🚀 Executable scripts
│   ├── paper_trade.py         # Main paper trading script
│   ├── train_ai.py            # AI training script
│   ├── get_token.py           # Token generation
│   ├── run_paper_trading.sh   # Quick launcher
│   ├── train_model.sh         # Training launcher
│   └── run_dashboard.sh       # Dashboard launcher
│
├── src/                       # 💻 Core source code
│   ├── ai_modules/            # AI components
│   │   ├── pattern_recognition.py
│   │   ├── sentiment_analyzer.py
│   │   ├── predictive_model.py
│   │   └── trading_psychology.py
│   ├── kite_trader/           # Zerodha API integration
│   │   └── trader.py
│   ├── paper_trading/         # Paper trading engine
│   │   └── paper_trader.py
│   ├── strategies/            # Trading strategies
│   │   ├── base_strategy.py
│   │   ├── ai_intraday_strategy.py
│   │   └── intraday_high_low_strategy.py
│   ├── utils/                 # Utilities
│   │   ├── config.py
│   │   └── logger.py
│   └── web/                   # Web dashboard
│       ├── app.py
│       ├── templates/
│       └── static/
│
├── data/                      # 📊 Data storage
│   ├── ai_data/               # AI models & state
│   └── logs/                  # Application logs
│
├── config/                    # ⚙️ Configuration
│   └── .env.example           # Environment template
│
├── deployment/                # 🚀 Deployment configs
│   ├── Dockerfile
│   └── cloudbuild.yaml
│
├── tests/                     # 🧪 Test files
├── backups/                   # 💾 Backup files
└── archive/                   # 📦 Old/temporary files
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
python3 -m pip install --user -r requirements.txt
```

### 2. Configure API Credentials

1. Get your API credentials from [Zerodha Kite Connect](https://developers.kite.trade/)
2. Copy the example config:
   ```bash
   cp config/.env.example .env
   ```
3. Edit `.env` with your credentials:
   ```env
   KITE_API_KEY=your_api_key_here
   KITE_API_SECRET=your_api_secret_here
   ZERODHA_USER_ID=your_user_id
   ZERODHA_PASSWORD=your_password
   ZERODHA_PIN=your_pin
   ```

### 3. Generate Access Token

```bash
python3 scripts/get_token.py
```

Follow the prompts to login and generate your access token.

### 4. Train the AI Models

```bash
python3 scripts/train_ai.py
# Or use the helper:
./scripts/train_model.sh
```

This will train the AI on 60 days of historical data (takes 5-10 minutes).

### 5. Start Paper Trading

```bash
python3 scripts/paper_trade.py
# Or use the helper:
./scripts/run_paper_trading.sh
```

The system will start trading with ₹100,000 virtual money using real market data!

## Usage

### Basic Usage

Edit `main.py` to configure your trading strategies:

```python
from src.kite_trader.trader import KiteTrader
from src.strategies.strategy_manager import StrategyManager

# Initialize trader
trader = KiteTrader()

# Create strategy manager
strategy_manager = StrategyManager(trader)

# Add momentum strategy
strategy_manager.add_strategy(
    'momentum',
    symbols=['RELIANCE', 'TCS', 'INFY'],
    momentum_threshold=0.02,  # 2% momentum
    lookback_days=5
)

# Add RSI strategy
strategy_manager.add_strategy(
    'rsi',
    symbols=['SBIN', 'HDFCBANK'],
    rsi_period=14,
    oversold_threshold=30,
    overbought_threshold=70
)

# Run the strategies
strategy_manager.run(interval_seconds=60)  # Check every 60 seconds
```

### Run the Bot

```bash
python main.py
```

## Trading Strategies

### 1. Momentum Strategy

Trades based on price momentum over a lookback period.

**Logic:**
- **BUY**: When momentum > threshold and no position
- **SELL**: When momentum < -threshold and have position

**Parameters:**
- `momentum_threshold`: Minimum momentum to trigger trade (default: 0.02 = 2%)
- `lookback_days`: Days to look back for momentum calculation (default: 5)
- `max_position_pct`: Max position size as % of capital (default: 0.1 = 10%)

### 2. RSI Strategy

Trades based on Relative Strength Index (RSI) indicator.

**Logic:**
- **BUY**: When RSI < oversold threshold (default: 30)
- **SELL**: When RSI > overbought threshold (default: 70)

**Parameters:**
- `rsi_period`: Period for RSI calculation (default: 14)
- `oversold_threshold`: RSI level to trigger buy (default: 30)
- `overbought_threshold`: RSI level to trigger sell (default: 70)
- `max_position_pct`: Max position size as % of capital (default: 0.1)

## Creating Custom Strategies

Extend the `BaseStrategy` class to create your own strategies:

```python
from src.strategies.base_strategy import BaseStrategy

class MyCustomStrategy(BaseStrategy):
    def analyze(self, symbol: str, market_data: dict) -> Optional[str]:
        # Implement your logic here
        # Return 'BUY', 'SELL', or None
        pass
    
    def calculate_position_size(self, symbol: str, signal: str) -> int:
        # Implement position sizing logic
        return quantity
```

## Configuration

All configuration is managed via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `KITE_API_KEY` | Your Kite API key | Required |
| `KITE_API_SECRET` | Your Kite API secret | Required |
| `KITE_ACCESS_TOKEN` | Your access token | Optional |
| `MAX_POSITION_SIZE_PCT` | Max position size (%) | 0.1 |
| `RSI_PERIOD` | RSI calculation period | 14 |
| `RSI_OVERSOLD` | RSI oversold threshold | 30 |
| `RSI_OVERBOUGHT` | RSI overbought threshold | 70 |
| `MOMENTUM_THRESHOLD` | Momentum trigger threshold | 0.02 |
| `MOMENTUM_LOOKBACK_DAYS` | Momentum lookback period | 5 |
| `LOG_LEVEL` | Logging level | INFO |

## Risk Management

⚠️ **Important Safety Features:**

1. **Position Sizing**: Automatically calculates position size based on available capital
2. **Maximum Position Limit**: Default 10% of capital per position
3. **Paper Trading**: Enable `ENABLE_PAPER_TRADING=true` for testing
4. **Stop Loss**: Implement in your custom strategies
5. **Logging**: All trades and decisions are logged

## Logging

Logs are stored in the `logs/` directory with daily rotation:
- Console output: INFO level
- File output: DEBUG level with full details
- File format: `trading_YYYYMMDD.log`

## Testing

⚠️ **Before live trading:**

1. Test with paper trading enabled
2. Start with small position sizes
3. Monitor logs carefully
4. Verify strategy logic with historical data

## API Limits

Zerodha Kite has rate limits:
- 3 requests per second
- Keep iteration intervals reasonable (60+ seconds recommended)

## Disclaimer

⚠️ **Trading involves significant risk. This bot is for educational purposes.**

- Always test thoroughly before live trading
- Start with small amounts
- Monitor your positions regularly
- Understand the risks involved
- Past performance doesn't guarantee future results

## Support

For issues with:
- **Kite API**: Check [Kite Connect Documentation](https://kite.trade/docs/connect/v3/)
- **Bot Issues**: Review logs in `logs/` directory
- **Strategy Questions**: Understand technical indicators before implementing

## License

MIT License - Use at your own risk

## Contributing

Feel free to:
- Add new strategies
- Improve risk management
- Add technical indicators
- Enhance logging and monitoring
