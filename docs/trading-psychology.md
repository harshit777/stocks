# Trading Psychology & Emotional Control

## Overview

The AI Base strategy now includes comprehensive **Trading Psychology Guards** that actively prevent emotional trading and enforce disciplined decision-making. This addresses one of the most critical aspects of successful trading: managing fear, greed, and other psychological biases.

## Key Psychological Biases Addressed

### 1. **Fear Prevention**
- **Cooldown Period After Losses**: 15-minute mandatory break after each loss
- **Gradual Position Size Recovery**: Reduces position size by 15% per consecutive loss (up to 40% reduction)
- **Max Drawdown Protection**: Stops all trading at 5% daily drawdown
- **Coaching Message**: "Take a deep breath. Losses are part of trading. Trust your system."

### 2. **Greed Prevention**
- **Daily Trade Limit**: Maximum 5 trades per day to prevent overtrading
- **Profit Target Enforcement**: Automatically triggers exit when profit target is reached
- **Position Size Caps**: Never exceed 10% of capital per position
- **Coaching Message**: "More trades ≠ more profit. Quality over quantity."

### 3. **Revenge Trading Prevention**
- **Consecutive Loss Limit**: Mandatory break after 3 consecutive losses
- **Forced Cooldown**: System blocks all trades until emotional state resets
- **Coaching Message**: "Step away from the terminal. Trading to 'get back at the market' only leads to more losses."

### 4. **Overconfidence Prevention**
- **Win Streak Detection**: Identifies when trader is on winning streak
- **Position Size Reduction**: Reduces size by 10% after 3+ consecutive wins (up to 30% reduction)
- **Reality Check**: Reminds trader that past performance doesn't guarantee future results
- **Coaching Message**: "Winning streak is great, but don't get cocky. Markets are unpredictable."

### 5. **FOMO (Fear of Missing Out) Prevention**
- **Signal Confirmation Window**: Requires 5-minute signal persistence before trading
- **No Impulse Trades**: Blocks trades on signals that just appeared
- **Patience Enforcement**: Only trades on confirmed opportunities
- **Coaching Message**: "Patience is a virtue. If it's a real opportunity, it will still be there after confirmation."

### 6. **Loss Aversion Management**
- **Automatic Stop-Loss Enforcement**: No emotional hesitation when stop-loss is hit
- **Emotion-Free Exit**: System exits position automatically at predefined stop-loss
- **Capital Protection**: "Stop-loss is protecting your capital" messaging

## Implementation Details

### Psychology Guard Configuration

```python
TradingPsychologyGuard(
    max_daily_trades=5,              # Prevents overtrading
    max_consecutive_losses=3,        # Blocks revenge trading
    cooldown_after_loss=15,          # Minutes to wait after loss
    reduce_size_after_wins=3,        # Reduce size after N wins
    max_drawdown_pct=0.05,           # 5% max daily drawdown
    fomo_prevention_window=5         # Signal confirmation window
)
```

### Integration Points

#### 1. **Signal Generation**
```python
def _combine_signals(self, symbol, base_signal, ai_signal):
    # Get raw signal from AI + base strategy
    raw_signal = self._get_raw_combined_signal(...)
    
    # Psychology guard has VETO power
    psych_check = self.psychology_guard.should_allow_trade(...)
    
    if not psych_check['allowed']:
        # Trade BLOCKED - log reason and coaching
        return None
    
    return raw_signal
```

#### 2. **Position Sizing**
```python
def calculate_position_size(self, symbol, signal):
    base_size = super().calculate_position_size(...)
    
    # Apply psychological adjustment
    psych_adj = psychology_guard.should_allow_trade(...).get('adjustment')
    
    # Reduced size during fear/overconfidence
    adjusted_size = base_size * psych_adj
```

#### 3. **Trade Execution**
```python
def execute_signal(self, symbol, signal):
    # Record trade for psychology tracking
    psychology_guard.record_trade(symbol, signal, entry_price, quantity)
    
    # Execute the trade
    super().execute_signal(...)
```

#### 4. **Position Exit**
```python
def update_position(self, symbol, transaction_type, quantity):
    if transaction_type == 'SELL':
        profit_loss = calculate_pnl(...)
        
        # Update psychology guard with outcome
        psychology_guard.record_trade(..., profit_loss)
        psychology_guard.update_capital(current_capital)
```

## Emotional States

The system tracks and responds to six emotional states:

| State | Trigger | Action | Coaching |
|-------|---------|--------|----------|
| **NEUTRAL** | Default state | Normal trading | "You're trading with discipline" |
| **FEARFUL** | After losses | Reduce position size, cooldown | "Losses are part of trading" |
| **GREEDY** | Approaching trade limit | Block new trades | "Quality over quantity" |
| **REVENGE** | 3+ consecutive losses | Complete trading halt | "Step away from terminal" |
| **OVERCONFIDENT** | 3+ consecutive wins | Reduce position size | "Don't get cocky" |
| **FOMO** | New signal appeared | Require confirmation | "Patience is a virtue" |

## Discipline Metrics

### Real-Time Monitoring

```python
discipline_report = psychology_guard.get_discipline_report()

{
    'emotional_state': 'neutral',
    'daily_trades': 2,
    'max_daily_trades': 5,
    'trades_remaining': 3,
    'consecutive_wins': 1,
    'consecutive_losses': 0,
    'daily_return_pct': 2.3,
    'max_drawdown_pct': 5.0,
    'drawdown_remaining': 5.0,
    'in_cooldown': False,
    'discipline_score': 95.0  # 0-100 score
}
```

### Discipline Score Calculation

- **100**: Perfect discipline
- **-20**: Approaching daily trade limit (>80%)
- **-30**: Multiple consecutive losses (>50% of max)
- **-10**: Not being cautious after wins
- **-25**: Approaching max drawdown (>50%)

## Stop-Loss & Profit Target Enforcement

### Automatic Stop-Loss
```python
stop_loss_check = psychology_guard.enforce_stop_loss(
    symbol, entry_price, current_price, stop_loss_pct=0.02
)

if stop_loss_check['should_exit']:
    # Emotion-free exit - NO HESITATION
    # Message: "Stop-loss is protecting your capital"
    exit_position(symbol)
```

### Profit Target Enforcement
```python
profit_check = psychology_guard.should_take_profit(
    symbol, entry_price, current_price, target_profit_pct=0.03
)

if profit_check['should_exit']:
    # Greed prevention - LOCK IN PROFITS
    # Message: "Lock in profits at target"
    exit_position(symbol)
```

## Benefits

### 1. **Eliminates Emotional Decisions**
- All decisions based on predefined rules
- No "gut feeling" trades
- System enforces discipline automatically

### 2. **Protects Capital**
- Hard stops on drawdowns
- Forced breaks after losses
- Position sizing adjusts to risk state

### 3. **Prevents Common Mistakes**
- No revenge trading after losses
- No overtrading during winning streaks
- No FOMO-driven impulsive trades

### 4. **Builds Consistency**
- Standardized decision-making
- Repeatable process
- Objective performance metrics

### 5. **Improves Long-Term Results**
- Preserves capital during drawdowns
- Compounds gains sustainably
- Reduces catastrophic losses

## Usage Example

```python
# Initialize strategy with psychology guard
strategy = AIIntradayStrategy(
    trader=kite_trader,
    symbols=['RELIANCE', 'TCS'],
    ai_confidence_threshold=0.6
)

# Reset daily stats at market open
strategy.reset_daily_data()

# During trading
signal = strategy.analyze(symbol, market_data)

# Psychology guard automatically:
# 1. Checks if trade is allowed
# 2. Adjusts position size based on emotional state
# 3. Records trade outcomes
# 4. Provides coaching when needed

# Get discipline report
metrics = strategy.get_ai_metrics()
print(metrics['psychology'])
```

## Logging Examples

### Trade Allowed (Neutral State)
```
✅ NEUTRAL STATE: You're trading with discipline. Keep following your plan objectively.
RELIANCE: All psychological checks passed
RELIANCE position size: 10 -> 10 (psychology: 1.00x)
```

### Trade Blocked (Fear - Cooldown)
```
🧘 FEAR DETECTED: Take a deep breath. Losses are part of trading. Your strategy has rules for a reason.
RELIANCE: Trade BLOCKED by psychology guard - Cooldown period active (12.3 min remaining). Prevents fear-based trading.
```

### Trade Blocked (Greed - Over-Limit)
```
⚠️ GREED WARNING: You've hit your daily trade limit. More trades ≠ more profit. Quality over quantity.
TCS: Trade BLOCKED by psychology guard - Daily trade limit reached (5). Prevents overtrading.
```

### Trade Blocked (Revenge)
```
🛑 REVENGE TRADING BLOCKED: Step away from the terminal. Trading to 'get back at the market' only leads to more losses.
INFY: Trade BLOCKED by psychology guard - 3 consecutive losses. Taking mandatory break to reset.
```

### Position Size Reduction (Overconfidence)
```
🎯 OVERCONFIDENCE CHECK: Winning streak is great, but don't get cocky. Markets are unpredictable.
Overconfidence guard: 4 consecutive wins. Reducing position size by 10.0%
RELIANCE position size: 10 -> 9 (psychology: 0.90x)
```

### FOMO Prevention
```
⏸️ FOMO PREVENTION: Patience is a virtue. If it's a real opportunity, it will still be there after confirmation.
TCS: Trade BLOCKED by psychology guard - FOMO prevention: Signal needs 3.2 more min of confirmation.
```

## Best Practices

1. **Review Discipline Report Daily**: Check your emotional state and discipline score
2. **Honor the System**: When trade is blocked, DON'T try to override it
3. **Learn from Patterns**: Review which emotional states trigger most often
4. **Adjust Parameters**: Fine-tune based on your psychology (stricter if needed)
5. **Take Breaks Seriously**: Use cooldown periods to step away completely
6. **Celebrate Discipline**: High discipline score is as important as profits

## Configuration Recommendations

### Conservative (Risk-Averse)
```python
TradingPsychologyGuard(
    max_daily_trades=3,              # Fewer trades
    max_consecutive_losses=2,        # Lower tolerance
    cooldown_after_loss=30,          # Longer break
    reduce_size_after_wins=2,        # Earlier reduction
    max_drawdown_pct=0.03,           # 3% max
    fomo_prevention_window=10        # Longer confirmation
)
```

### Aggressive (Risk-Tolerant)
```python
TradingPsychologyGuard(
    max_daily_trades=8,              # More trades
    max_consecutive_losses=5,        # Higher tolerance
    cooldown_after_loss=10,          # Shorter break
    reduce_size_after_wins=5,        # Later reduction
    max_drawdown_pct=0.08,           # 8% max
    fomo_prevention_window=3         # Shorter confirmation
)
```

### Default (Balanced)
```python
TradingPsychologyGuard(
    max_daily_trades=5,
    max_consecutive_losses=3,
    cooldown_after_loss=15,
    reduce_size_after_wins=3,
    max_drawdown_pct=0.05,
    fomo_prevention_window=5
)
```

## Conclusion

The Trading Psychology Guard transforms the AI Base strategy from a technical trading system into a **psychologically robust trading system**. It doesn't just tell you what to trade—it protects you from your own emotional biases and enforces the discipline necessary for long-term success.

**Remember**: The best trading strategy is worthless if you can't execute it with discipline. This system ensures you stay disciplined, even when emotions run high.
