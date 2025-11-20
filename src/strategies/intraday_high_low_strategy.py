"""
Intraday High-Low Trading Strategy

This strategy analyzes intraday highs and lows to determine optimal buy/sell points
based on profit margins and risk-reward ratios.

Logic:
1. Track intraday high, low, and current price
2. Calculate support/resistance levels from highs/lows
3. Determine buy zones near support (lows)
4. Determine sell zones near resistance (highs)
5. Use profit margin to ensure trades meet minimum profit targets
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from .base_strategy import BaseStrategy


class IntradayHighLowStrategy(BaseStrategy):
    """
    Intraday trading strategy based on high/low analysis with margin calculations.
    
    Key Concepts:
    - Buy near lows (support) with margin for profit
    - Sell near highs (resistance) to capture gains
    - Risk-reward ratio ensures profitable trades
    """
    
    def __init__(self, 
                 trader,
                 symbols: List[str],
                 min_profit_margin: float = 0.01,  # 1% minimum profit
                 buy_threshold: float = 0.3,       # Buy when price is in lower 30% of range
                 sell_threshold: float = 0.7,      # Sell when price is in upper 70% of range
                 risk_reward_ratio: float = 2.0,   # Target 2x reward for 1x risk
                 max_position_pct: float = 0.1,    # 10% of capital per position
                 stop_loss_pct: float = 0.02,      # 2% stop loss
                 name: str = "IntradayHighLowStrategy"):
        """
        Initialize the intraday high-low strategy.
        
        Args:
            trader: KiteTrader instance
            symbols: List of trading symbols
            min_profit_margin: Minimum profit margin required (0.01 = 1%)
            buy_threshold: Price position threshold to trigger buy (0-1)
            sell_threshold: Price position threshold to trigger sell (0-1)
            risk_reward_ratio: Minimum risk-reward ratio for trades
            max_position_pct: Maximum position size as % of capital
            stop_loss_pct: Stop loss percentage from entry price
            name: Strategy name
        """
        super().__init__(trader, symbols, name)
        
        self.min_profit_margin = min_profit_margin
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.risk_reward_ratio = risk_reward_ratio
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        
        # Track intraday metrics for each symbol
        self.intraday_data = {}
        self.entry_prices = {}  # Track entry prices for profit calculation
        
        self.logger.info(f"Initialized {name} with min_profit_margin={min_profit_margin}, "
                        f"risk_reward={risk_reward_ratio}")
    
    def update_intraday_data(self, symbol: str, market_data: Dict):
        """
        Update intraday high, low, and price data for a symbol.
        
        Args:
            symbol: Trading symbol
            market_data: Market data from quote API
        """
        symbol_key = f"NSE:{symbol}"
        
        if symbol_key not in market_data:
            self.logger.warning(f"No data for {symbol_key}")
            return
        
        quote = market_data[symbol_key]
        current_price = quote.get('last_price', 0)
        
        # Get OHLC data
        ohlc = quote.get('ohlc', {})
        day_high = ohlc.get('high', current_price)
        day_low = ohlc.get('low', current_price)
        open_price = ohlc.get('open', current_price)
        
        # Initialize or update intraday data
        if symbol not in self.intraday_data:
            self.intraday_data[symbol] = {
                'high': day_high,
                'low': day_low,
                'open': open_price,
                'last_update': datetime.now()
            }
        else:
            # Update high and low if needed
            self.intraday_data[symbol]['high'] = max(self.intraday_data[symbol]['high'], day_high)
            self.intraday_data[symbol]['low'] = min(self.intraday_data[symbol]['low'], day_low)
            self.intraday_data[symbol]['last_update'] = datetime.now()
    
    def calculate_price_position(self, symbol: str, current_price: float) -> float:
        """
        Calculate where current price sits in the day's range (0 to 1).
        
        0 = at day's low (support)
        1 = at day's high (resistance)
        0.5 = midpoint
        
        Args:
            symbol: Trading symbol
            current_price: Current price
            
        Returns:
            Price position ratio (0-1)
        """
        if symbol not in self.intraday_data:
            return 0.5  # Default to midpoint if no data
        
        day_high = self.intraday_data[symbol]['high']
        day_low = self.intraday_data[symbol]['low']
        
        if day_high == day_low:
            return 0.5  # No range yet
        
        # Calculate position in range
        position = (current_price - day_low) / (day_high - day_low)
        return max(0.0, min(1.0, position))  # Clamp to 0-1
    
    def calculate_profit_potential(self, symbol: str, current_price: float, 
                                   signal: str) -> Dict:
        """
        Calculate profit potential for a trade.
        
        Args:
            symbol: Trading symbol
            current_price: Current price
            signal: BUY or SELL
            
        Returns:
            Dict with profit metrics
        """
        if symbol not in self.intraday_data:
            return {'valid': False}
        
        day_high = self.intraday_data[symbol]['high']
        day_low = self.intraday_data[symbol]['low']
        
        if signal == "BUY":
            # For buy: target is day high, stop loss below current
            target_price = day_high
            stop_loss_price = current_price * (1 - self.stop_loss_pct)
            
            potential_profit = target_price - current_price
            potential_loss = current_price - stop_loss_price
            
            profit_margin = (potential_profit / current_price) if current_price > 0 else 0
            risk_reward = (potential_profit / potential_loss) if potential_loss > 0 else 0
            
            return {
                'valid': True,
                'entry': current_price,
                'target': target_price,
                'stop_loss': stop_loss_price,
                'profit_potential': potential_profit,
                'loss_potential': potential_loss,
                'profit_margin': profit_margin,
                'risk_reward': risk_reward
            }
        
        elif signal == "SELL":
            # For sell (exit long position): calculate realized profit
            entry_price = self.entry_prices.get(symbol, current_price)
            profit = current_price - entry_price
            profit_margin = (profit / entry_price) if entry_price > 0 else 0
            
            return {
                'valid': True,
                'entry': entry_price,
                'exit': current_price,
                'profit': profit,
                'profit_margin': profit_margin,
                'risk_reward': 0  # Already in position
            }
        
        return {'valid': False}
    
    def analyze(self, symbol: str, market_data: Dict) -> Optional[str]:
        """
        Analyze market data and generate trading signal.
        
        Buy Logic:
        1. Price is in lower range (near support/low)
        2. Profit potential meets minimum margin
        3. Risk-reward ratio is favorable
        4. No existing position
        
        Sell Logic:
        1. Price is in upper range (near resistance/high)
        2. Profit margin target achieved
        3. Have existing position
        
        Args:
            symbol: Trading symbol
            market_data: Market data from API
            
        Returns:
            'BUY', 'SELL', or None
        """
        # Update intraday tracking
        self.update_intraday_data(symbol, market_data)
        
        symbol_key = f"NSE:{symbol}"
        if symbol_key not in market_data:
            return None
        
        quote = market_data[symbol_key]
        current_price = quote.get('last_price', 0)
        
        if current_price <= 0:
            return None
        
        # Calculate price position in day's range
        price_position = self.calculate_price_position(symbol, current_price)
        
        has_position = self.has_position(symbol)
        
        # BUY LOGIC: Price near lows, good profit potential
        if not has_position and price_position <= self.buy_threshold:
            # Calculate profit potential
            profit_metrics = self.calculate_profit_potential(symbol, current_price, "BUY")
            
            if not profit_metrics['valid']:
                return None
            
            # Check if trade meets criteria
            profit_margin_ok = profit_metrics['profit_margin'] >= self.min_profit_margin
            risk_reward_ok = profit_metrics['risk_reward'] >= self.risk_reward_ratio
            
            if profit_margin_ok and risk_reward_ok:
                self.logger.info(
                    f"{symbol} BUY signal: price={current_price:.2f}, "
                    f"position={price_position:.2%}, "
                    f"profit_margin={profit_metrics['profit_margin']:.2%}, "
                    f"risk_reward={profit_metrics['risk_reward']:.2f}, "
                    f"target={profit_metrics['target']:.2f}, "
                    f"stop_loss={profit_metrics['stop_loss']:.2f}"
                )
                
                # Store entry price for later profit calculation
                self.entry_prices[symbol] = current_price
                
                return "BUY"
            else:
                self.logger.debug(
                    f"{symbol} BUY rejected: profit_margin={profit_metrics['profit_margin']:.2%} "
                    f"(need {self.min_profit_margin:.2%}), "
                    f"risk_reward={profit_metrics['risk_reward']:.2f} "
                    f"(need {self.risk_reward_ratio:.2f})"
                )
        
        # SELL LOGIC: Price near highs, profit target reached
        elif has_position and price_position >= self.sell_threshold:
            # Calculate actual profit
            profit_metrics = self.calculate_profit_potential(symbol, current_price, "SELL")
            
            if not profit_metrics['valid']:
                return None
            
            # Check if profit target is met
            if profit_metrics['profit_margin'] >= self.min_profit_margin:
                self.logger.info(
                    f"{symbol} SELL signal: price={current_price:.2f}, "
                    f"position={price_position:.2%}, "
                    f"entry={profit_metrics['entry']:.2f}, "
                    f"profit={profit_metrics['profit']:.2f}, "
                    f"profit_margin={profit_metrics['profit_margin']:.2%}"
                )
                
                # Clear entry price
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]
                
                return "SELL"
            else:
                self.logger.debug(
                    f"{symbol} SELL rejected: profit_margin={profit_metrics['profit_margin']:.2%} "
                    f"(need {self.min_profit_margin:.2%})"
                )
        
        return None
    
    def calculate_position_size(self, symbol: str, signal: str) -> int:
        """
        Calculate position size based on available capital and risk management.
        
        Args:
            symbol: Trading symbol
            signal: Trading signal (BUY/SELL)
            
        Returns:
            Number of shares to trade
        """
        try:
            # For SELL, check if we have a position first
            if signal == "SELL":
                position_qty = abs(self.get_position_quantity(symbol))
                if position_qty == 0:
                    self.logger.debug(f"{symbol}: No position to sell")
                    return 0
                return position_qty
            
            # Get available margin - works with both real trader and paper trading wrapper
            if hasattr(self.trader, 'margins'):
                margins = self.trader.margins()
            elif hasattr(self.trader, 'kite') and hasattr(self.trader.kite, 'margins'):
                margins = self.trader.kite.margins()
            else:
                self.logger.error(f"Cannot get margins for {symbol} - trader has no margins() method")
                return 0
            
            available_cash = margins.get('equity', {}).get('available', {}).get('cash', 0)
            
            if available_cash <= 0:
                self.logger.warning(f"No available cash for {symbol}")
                return 0
            
            # Get current price
            try:
                ltp_data = self.trader.get_ltp([symbol])
                current_price = ltp_data.get(f"NSE:{symbol}", 0)
            except Exception as e:
                self.logger.error(f"Error getting LTP for {symbol}: {e}")
                # Fallback to quote
                try:
                    quotes = self.trader.get_quote([symbol])
                    current_price = quotes.get(f"NSE:{symbol}", {}).get('last_price', 0)
                except:
                    current_price = 0
            
            if current_price <= 0:
                return 0
            
            # For BUY, calculate based on available capital
            max_investment = available_cash * self.max_position_pct
            quantity = int(max_investment / current_price)
            
            # Ensure minimum lot size (typically 1 for stocks)
            quantity = max(1, quantity)
            
            self.logger.info(
                f"{symbol} position size: {quantity} shares at ₹{current_price:.2f} "
                f"= ₹{quantity * current_price:.2f} "
                f"({(quantity * current_price / available_cash * 100):.1f}% of capital)"
            )
            
            return quantity
            
        except Exception as e:
            self.logger.error(f"Error calculating position size for {symbol}: {str(e)}")
            return 0
    
    def get_strategy_metrics(self) -> Dict:
        """
        Get current strategy metrics and performance.
        
        Returns:
            Dict with strategy metrics
        """
        metrics = {
            'strategy_name': self.name,
            'symbols_tracked': len(self.symbols),
            'active_positions': len([s for s in self.positions if self.positions[s]['quantity'] != 0]),
            'intraday_data': {}
        }
        
        for symbol in self.symbols:
            if symbol in self.intraday_data:
                data = self.intraday_data[symbol]
                day_range = data['high'] - data['low']
                metrics['intraday_data'][symbol] = {
                    'high': data['high'],
                    'low': data['low'],
                    'range': day_range,
                    'range_pct': (day_range / data['low'] * 100) if data['low'] > 0 else 0
                }
        
        return metrics
    
    def reset_daily_data(self):
        """
        Reset intraday data at start of new trading day.
        Call this at market open.
        """
        self.intraday_data.clear()
        self.entry_prices.clear()
        self.logger.info("Daily data reset for new trading day")
