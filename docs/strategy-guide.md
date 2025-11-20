# Intraday High-Low Trading Strategy

## Overview

The Intraday High-Low Strategy is designed for day trading (intraday) by analyzing a stock's daily high and low prices to determine optimal buy and sell points. The strategy focuses on profit margins and risk-reward ratios to ensure profitable trades.

## Core Concept

### Price Position in Daily Range

The strategy calculates where the current price sits relative to the day's high and low:

```
Price Position = (Current Price - Day Low) / (Day High - Day Low)

- Position = 0.0 (0%):   Price at day's low (support level)
- Position = 0.5 (50%):  Price at midpoint
- Position = 1.0 (100%): Price at day's high (resistance level)
```

## Trading Logic

### Buy Signal Conditions

A BUY signal is generated when **ALL** conditions are met:

1. **No Existing Position**: Not currently holding the stock
2. **Price Near Support**: Current price position ≤ buy_threshold (default: 30%)
3. **Profit Margin Met**: Potential profit ≥ min_profit_margin (default: 1%)
4. **Risk-Reward Favorable**: Risk-reward ratio ≥ target ratio (default: 2.0)

**Example Buy Scenario:**
```
Stock: RELIANCE
Day High: ₹2,500
Day Low: ₹2,450
Current Price: ₹2,460

Price Position = (2,460 - 2,450) / (2,500 - 2,450) = 0.2 (20%)
✓ Position 20% < 30% threshold

Target (day high): ₹2,500
Profit Potential: ₹2,500 - ₹2,460 = ₹40
Profit Margin: ₹40 / ₹2,460 = 1.63%
✓ Profit margin 1.63% > 1% minimum

Stop Loss (2% below): ₹2,460 × 0.98 = ₹2,410.80
Loss Potential: ₹2,460 - ₹2,410.80 = ₹49.20
Risk-Reward: ₹40 / ₹49.20 = 0.81
✗ Risk-reward 0.81 < 2.0 minimum
→ NO BUY (risk-reward not favorable)
```

### Sell Signal Conditions

A SELL signal is generated when **ALL** conditions are met:

1. **Have Existing Position**: Currently holding the stock
2. **Price Near Resistance**: Current price position ≥ sell_threshold (default: 70%)
3. **Profit Target Met**: Actual profit margin ≥ min_profit_margin (default: 1%)

**Example Sell Scenario:**
```
Stock: RELIANCE
Entry Price: ₹2,460
Day High: ₹2,500
Current Price: ₹2,490

Price Position = (2,490 - 2,450) / (2,500 - 2,450) = 0.8 (80%)
✓ Position 80% > 70% threshold

Profit: ₹2,490 - ₹2,460 = ₹30
Profit Margin: ₹30 / ₹2,460 = 1.22%
✓ Profit margin 1.22% > 1% minimum

→ SELL (take profit)
```

## Configuration Parameters

### Strategy Parameters

| Parameter | Default | Description | Example Values |
|-----------|---------|-------------|----------------|
| `min_profit_margin` | 0.01 (1%) | Minimum profit target | Conservative: 0.02 (2%)<br>Aggressive: 0.005 (0.5%) |
| `buy_threshold` | 0.3 (30%) | Price position to trigger buy | Conservative: 0.2 (20%)<br>Aggressive: 0.4 (40%) |
| `sell_threshold` | 0.7 (70%) | Price position to trigger sell | Conservative: 0.8 (80%)<br>Aggressive: 0.6 (60%) |
| `risk_reward_ratio` | 2.0 | Minimum reward/risk ratio | Conservative: 3.0<br>Aggressive: 1.5 |
| `max_position_pct` | 0.1 (10%) | Max capital per position | Conservative: 0.05 (5%)<br>Aggressive: 0.15 (15%) |
| `stop_loss_pct` | 0.02 (2%) | Stop loss from entry | Tight: 0.01 (1%)<br>Loose: 0.03 (3%) |

### Conservative vs Aggressive Settings

**Conservative (Lower Risk, Lower Returns):**
```python
strategy = IntradayHighLowStrategy(
    trader=trader,
    symbols=symbols,
    min_profit_margin=0.02,      # 2% profit target
    buy_threshold=0.2,            # Buy in lower 20%
    sell_threshold=0.8,           # Sell in upper 80%
    risk_reward_ratio=3.0,        # 3:1 reward/risk
    max_position_pct=0.05,        # 5% per position
    stop_loss_pct=0.015           # 1.5% stop loss
)
```

**Aggressive (Higher Risk, Higher Returns):**
```python
strategy = IntradayHighLowStrategy(
    trader=trader,
    symbols=symbols,
    min_profit_margin=0.005,     # 0.5% profit target
    buy_threshold=0.4,            # Buy in lower 40%
    sell_threshold=0.6,           # Sell in upper 60%
    risk_reward_ratio=1.5,        # 1.5:1 reward/risk
    max_position_pct=0.15,        # 15% per position
    stop_loss_pct=0.025           # 2.5% stop loss
)
```

## Position Sizing

Position size is calculated automatically based on available capital:

```
Maximum Investment = Available Cash × max_position_pct
Quantity = Floor(Maximum Investment / Current Price)
```

**Example:**
```
Available Capital: ₹100,000
max_position_pct: 0.1 (10%)
Current Price: ₹2,460

Max Investment = ₹100,000 × 0.1 = ₹10,000
Quantity = ₹10,000 / ₹2,460 = 4.06 → 4 shares
Actual Investment = 4 × ₹2,460 = ₹9,840
```

## Complete Trading Example

### Scenario: Trading RELIANCE

**Market Open (9:15 AM)**
- Open: ₹2,475
- Initial High: ₹2,475
- Initial Low: ₹2,475

**10:30 AM - Price drops to ₹2,450**
- High: ₹2,480
- Low: ₹2,450
- Current: ₹2,450
- Position: (2,450 - 2,450) / (2,480 - 2,450) = 0% ✓
- At day's low - BUY signal considered
- Profit potential: 2,480 - 2,450 = ₹30 (1.22%) ✓
- Risk-reward checked and favorable ✓
- **→ BUY 4 shares @ ₹2,450**

**12:00 PM - Price rises to ₹2,485**
- High: ₹2,490
- Low: ₹2,445
- Current: ₹2,485
- Position: (2,485 - 2,445) / (2,490 - 2,445) = 88.9% ✓
- Near day's high
- Profit: 2,485 - 2,450 = ₹35 (1.43%) ✓
- **→ SELL 4 shares @ ₹2,485**

**Result:**
- Gross Profit: ₹35 × 4 = ₹140
- Profit %: 1.43%
- Trade Duration: 1.5 hours

## Real-World Profit Calculation

### Example with Multiple Trades

**Capital: ₹100,000**
**Position Size: 10% (₹10,000 per trade)**

| Stock | Entry | Exit | Qty | Profit/Loss | Margin % | Notes |
|-------|-------|------|-----|-------------|----------|-------|
| RELIANCE | ₹2,450 | ₹2,485 | 4 | +₹140 | +1.43% | Near low → high |
| TCS | ₹3,200 | ₹3,245 | 3 | +₹135 | +1.41% | Near low → high |
| INFY | ₹1,450 | ₹1,440 | 6 | -₹60 | -0.69% | Stop loss hit |
| HDFCBANK | ₹1,600 | ₹1,625 | 6 | +₹150 | +1.56% | Near low → high |

**Summary:**
- Total Trades: 4
- Winning Trades: 3 (75%)
- Losing Trades: 1 (25%)
- Gross Profit: ₹365
- Return on Capital: 0.365%
- Daily Target: 0.5% (achieved if ≥ ₹500/day on ₹100k)

### Compounding Effect

Starting with ₹100,000 and targeting 0.5% daily profit:

| Day | Capital | Target Profit | Cumulative |
|-----|---------|---------------|------------|
| 1 | ₹100,000 | ₹500 | ₹100,500 |
| 5 | ₹102,013 | ₹510 | ₹102,523 |
| 10 | ₹105,114 | ₹526 | ₹105,640 |
| 20 | ₹110,494 | ₹552 | ₹111,046 |

*Note: This assumes consistent profits, which is not realistic. Factor in losing days.*

## Best Practices

### Stock Selection
Choose stocks with:
- High liquidity (easy to buy/sell)
- Good intraday volatility (2-4% daily range)
- Regular trading volume
- Examples: RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK

### Timing
- **Best Hours**: 10:00 AM - 2:30 PM (avoid first and last hour volatility)
- **Market Open**: Wait 30-45 minutes for range to establish
- **Market Close**: Square off all positions by 3:15 PM

### Risk Management
1. Never risk more than 2% of capital per trade
2. Set stop-loss orders immediately after entry
3. Don't average down losing positions
4. Take profits at target, don't be greedy
5. Maximum 3-5 positions at once

### Monitoring
- Check positions every 15-30 minutes
- Monitor stop losses closely
- Be ready to manually exit if needed
- Track daily P&L and adjust strategy

## Usage Example

```python
from src.kite_trader.trader import KiteTrader
from src.strategies.intraday_high_low_strategy import IntradayHighLowStrategy

# Initialize
trader = KiteTrader()
strategy = IntradayHighLowStrategy(
    trader=trader,
    symbols=['RELIANCE', 'TCS', 'INFY'],
    min_profit_margin=0.015,      # 1.5% target
    buy_threshold=0.25,           # Buy in lower 25%
    sell_threshold=0.75,          # Sell in upper 75%
    risk_reward_ratio=2.5,        # 2.5:1 reward/risk
    max_position_pct=0.08,        # 8% per position
    stop_loss_pct=0.02            # 2% stop loss
)

# Run
strategy.run_iteration()  # Analyzes all symbols and executes trades

# Get metrics
metrics = strategy.get_strategy_metrics()
print(f"Active positions: {metrics['active_positions']}")
```

Or use the example script:
```bash
python intraday_trader_example.py
```

## Limitations and Risks

### Strategy Limitations
- Works best in trending markets
- Less effective in sideways/choppy markets
- Requires established daily range (wait 30-60 min after open)
- Not suitable for low-volatility stocks
- Requires active monitoring

### Market Risks
- Gap ups/downs can trigger stop losses
- News events can cause sudden moves
- Low liquidity can cause slippage
- Brokerage and taxes eat into profits

### Technical Risks
- API connection issues
- Order execution delays
- Data feed problems
- Strategy bugs

## Testing Recommendations

1. **Backtest First**: Test on historical data
2. **Paper Trade**: Use virtual money for 1-2 weeks
3. **Small Capital**: Start with ₹10,000-25,000
4. **Single Stock**: Trade one stock until consistent
5. **Track Everything**: Log all trades and analyze

## Support and Maintenance

- Check logs in `logs/` directory
- Monitor strategy metrics regularly
- Adjust parameters based on performance
- Reset daily data each trading day

## Disclaimer

⚠️ **This strategy is for educational purposes only.**

- Trading involves substantial risk of loss
- Past performance doesn't guarantee future results
- Always do your own research
- Only trade with money you can afford to lose
- Consider consulting a financial advisor
