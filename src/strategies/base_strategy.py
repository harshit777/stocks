"""
Base strategy class that all trading strategies should inherit from.
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from datetime import datetime


class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""
    
    def __init__(self, trader, symbols: List[str], name: str = "BaseStrategy"):
        """
        Initialize the strategy.
        
        Args:
            trader: KiteTrader instance
            symbols: List of trading symbols to monitor
            name: Strategy name
        """
        self.trader = trader
        self.symbols = symbols
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.positions = {}  # Track current positions
        self.signals = {}  # Track generated signals
    
    @abstractmethod
    def analyze(self, symbol: str, market_data: Dict) -> Optional[str]:
        """
        Analyze market data and generate trading signal.
        
        Args:
            symbol: Trading symbol
            market_data: Market data including price, volume, etc.
        
        Returns:
            'BUY', 'SELL', or None
        """
        pass
    
    @abstractmethod
    def calculate_position_size(self, symbol: str, signal: str) -> int:
        """
        Calculate position size based on risk management rules.
        
        Args:
            symbol: Trading symbol
            signal: Trading signal (BUY/SELL)
        
        Returns:
            Number of shares to trade
        """
        pass
    
    def execute_signal(self, symbol: str, signal: str):
        """
        Execute a trading signal.
        
        Args:
            symbol: Trading symbol
            signal: Trading signal (BUY/SELL)
        """
        try:
            quantity = self.calculate_position_size(symbol, signal)
            
            if quantity <= 0:
                self.logger.warning(f"Invalid position size for {symbol}: {quantity}")
                return
            
            # Place the order
            order_id = self.trader.place_order(
                symbol=symbol,
                transaction_type=signal,
                quantity=quantity,
                order_type="MARKET",
                product="MIS"  # Intraday
            )
            
            if order_id:
                self.logger.info(f"Order executed: {signal} {quantity} {symbol} - Order ID: {order_id}")
                self.update_position(symbol, signal, quantity)
            else:
                self.logger.error(f"Failed to execute order for {symbol}")
                
        except Exception as e:
            self.logger.error(f"Error executing signal for {symbol}: {str(e)}")
    
    def update_position(self, symbol: str, transaction_type: str, quantity: int):
        """Update internal position tracking."""
        if symbol not in self.positions:
            self.positions[symbol] = {'quantity': 0, 'last_action': None}
        
        if transaction_type == "BUY":
            self.positions[symbol]['quantity'] += quantity
        elif transaction_type == "SELL":
            self.positions[symbol]['quantity'] -= quantity
        
        self.positions[symbol]['last_action'] = transaction_type
        self.positions[symbol]['timestamp'] = datetime.now()
    
    def has_position(self, symbol: str) -> bool:
        """Check if we have an open position in the symbol."""
        return symbol in self.positions and self.positions[symbol]['quantity'] != 0
    
    def get_position_quantity(self, symbol: str) -> int:
        """Get current position quantity for a symbol."""
        if symbol in self.positions:
            return self.positions[symbol]['quantity']
        return 0
    
    def run_iteration(self):
        """Run one iteration of the strategy for all symbols."""
        # Track symbols with consecutive failures to reduce log spam
        if not hasattr(self, '_symbol_failures'):
            self._symbol_failures = {}  # symbol -> consecutive failure count
        
        self.logger.debug(f"Starting iteration for {len(self.symbols)} symbols: {', '.join(self.symbols[:5])}...")
        
        for symbol in self.symbols:
            try:
                # Fetch market data
                quote = self.trader.get_quote([symbol])
                
                if not quote:
                    # Track consecutive failures
                    self._symbol_failures[symbol] = self._symbol_failures.get(symbol, 0) + 1
                    
                    # Only log warning every 10 attempts to reduce spam
                    if self._symbol_failures[symbol] == 1 or self._symbol_failures[symbol] % 10 == 0:
                        self.logger.warning(
                            f"No quote data for {symbol} (attempt {self._symbol_failures[symbol]})"
                        )
                    continue
                
                # Validate that the symbol key exists in quote data
                symbol_key = f"NSE:{symbol}"
                if symbol_key not in quote and f"BSE:{symbol}" not in quote:
                    # Track consecutive failures
                    self._symbol_failures[symbol] = self._symbol_failures.get(symbol, 0) + 1
                    
                    # Only log warning every 10 attempts
                    if self._symbol_failures[symbol] == 1 or self._symbol_failures[symbol] % 10 == 0:
                        self.logger.warning(
                            f"No quote data for {symbol} (attempt {self._symbol_failures[symbol]})"
                        )
                    continue
                
                # Success - reset failure count
                if symbol in self._symbol_failures:
                    del self._symbol_failures[symbol]
                
                # Analyze and generate signal
                signal = self.analyze(symbol, quote)
                
                if signal:
                    self.logger.info(f"Signal generated for {symbol}: {signal}")
                    self.execute_signal(symbol, signal)
                    
            except Exception as e:
                self.logger.error(f"Error in iteration for {symbol}: {str(e)}")
    
    def reset_symbol_failures(self):
        """Reset the failure counts for all symbols to retry fetching quotes."""
        if hasattr(self, '_symbol_failures'):
            self._symbol_failures.clear()
            self.logger.info("Reset symbol failure tracking")
    
    def get_failing_symbols(self):
        """Get symbols that are currently failing with their failure counts."""
        if hasattr(self, '_symbol_failures'):
            return self._symbol_failures.copy()
        return {}
    
    def remove_failing_symbols(self, failure_threshold: int = 20):
        """
        Remove symbols that have failed to get quote data consistently.
        
        Args:
            failure_threshold: Number of consecutive failures before removing symbol
        
        Returns:
            List of symbols that were removed
        """
        if not hasattr(self, '_symbol_failures'):
            return []
        
        symbols_to_remove = [
            symbol for symbol, count in self._symbol_failures.items()
            if count >= failure_threshold
        ]
        
        if symbols_to_remove:
            self.logger.warning(
                f"Removing {len(symbols_to_remove)} symbols with {failure_threshold}+ failures: "
                f"{', '.join(symbols_to_remove)}"
            )
            
            # Remove from symbol list
            self.symbols = [s for s in self.symbols if s not in symbols_to_remove]
            
            # Remove from failure tracking
            for symbol in symbols_to_remove:
                del self._symbol_failures[symbol]
            
            self.logger.info(f"Active symbols remaining: {len(self.symbols)}")
        
        return symbols_to_remove
    
    def validate_symbols(self, symbols_to_check: list) -> list:
        """
        Validate symbols by checking if they can get quote data.
        
        Args:
            symbols_to_check: List of symbols to validate
        
        Returns:
            List of valid symbols that successfully returned quote data
        """
        valid_symbols = []
        invalid_symbols = []
        
        self.logger.info(f"Validating {len(symbols_to_check)} symbols...")
        
        for symbol in symbols_to_check:
            try:
                quote = self.trader.get_quote([symbol])
                symbol_key = f"NSE:{symbol}"
                
                if quote and (symbol_key in quote or f"BSE:{symbol}" in quote):
                    valid_symbols.append(symbol)
                else:
                    invalid_symbols.append(symbol)
            except Exception as e:
                self.logger.debug(f"Failed to validate {symbol}: {e}")
                invalid_symbols.append(symbol)
        
        if invalid_symbols:
            self.logger.warning(
                f"Found {len(invalid_symbols)} symbols without quote data: "
                f"{', '.join(invalid_symbols)}"
            )
        
        self.logger.info(f"Validated {len(valid_symbols)}/{len(symbols_to_check)} symbols")
        return valid_symbols
    
    def cleanup(self):
        """Cleanup operations, close positions, etc."""
        self.logger.info(f"Cleaning up strategy: {self.name}")
        if hasattr(self, '_symbol_failures') and self._symbol_failures:
            failing = ', '.join(f"{sym}({count})" for sym, count in sorted(self._symbol_failures.items()))
            self.logger.info(f"Symbols with quote failures: {failing}")
        # Implement cleanup logic as needed
