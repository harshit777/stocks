"""
Zerodha Kite API trader implementation.
Handles authentication, order placement, and market data fetching.
"""
import os
import logging
from typing import Dict, List, Optional
from kiteconnect import KiteConnect
from datetime import datetime, timedelta


class KiteTrader:
    """Wrapper class for Zerodha Kite API operations with production features."""
    
    def __init__(self, enable_order_manager: bool = False, enable_rate_limiter: bool = True):
        """Initialize the Kite trader with API credentials.
        
        Args:
            enable_order_manager: Use OrderManager for verified execution
            enable_rate_limiter: Enable API rate limiting (3 req/sec)
        """
        self.logger = logging.getLogger(__name__)
        
        # Load credentials from environment variables
        self.api_key = os.getenv('KITE_API_KEY')
        self.api_secret = os.getenv('KITE_API_SECRET')
        self.access_token = os.getenv('KITE_ACCESS_TOKEN')
        
        # Trading mode
        self.trading_mode = os.getenv('TRADING_MODE', 'paper')  # paper/dry-run/live
        
        if not self.api_key:
            self.logger.warning("KITE_API_KEY not found in environment variables")
        
        self.kite = None
        self._initialize_connection()
        
        # Initialize production components
        self.order_manager = None
        self.rate_limiter = None
        self.position_reconciler = None
        
        if enable_order_manager and self.trading_mode == 'live':
            from .order_manager import OrderManager
            self.order_manager = OrderManager(
                self,
                order_timeout=int(os.getenv('ORDER_TIMEOUT', '30')),
                poll_interval=1.0
            )
            self.logger.info("OrderManager enabled for production trading")
        
        if enable_rate_limiter:
            from ..utils.rate_limiter import get_rate_limiter
            self.rate_limiter = get_rate_limiter(
                requests_per_second=float(os.getenv('RATE_LIMIT', '3.0'))
            )
            self.logger.info("Rate limiter enabled (3 req/sec)")
        
        # Initialize position reconciler
        from .position_reconciler import PositionReconciler
        self.position_reconciler = PositionReconciler(self, tolerance=0.01)
        
        # Cost calculator
        from ..utils.cost_calculator import get_cost_calculator
        self.cost_calculator = get_cost_calculator()
    
    def _initialize_connection(self):
        """Initialize connection to Zerodha Kite."""
        try:
            if not self.api_key:
                self.logger.error("API key is required for connection")
                return
            
            self.kite = KiteConnect(api_key=self.api_key)
            
            if self.access_token:
                self.kite.set_access_token(self.access_token)
                self.logger.info("Kite connection initialized with access token")
            else:
                self.logger.warning("Access token not found. You'll need to login manually.")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize Kite connection: {str(e)}")
    
    def is_connected(self) -> bool:
        """Check if connected to Kite API."""
        if not self.kite or not self.access_token:
            return False
        
        try:
            self.kite.profile()
            return True
        except Exception as e:
            self.logger.error(f"Connection check failed: {str(e)}")
            return False
    
    def get_login_url(self) -> Optional[str]:
        """Get the login URL for manual authentication."""
        if not self.kite:
            return None
        return self.kite.login_url()
    
    def set_access_token_from_request(self, request_token: str):
        """Generate and set access token from request token."""
        try:
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            self.logger.info("Access token set successfully")
            return self.access_token
        except Exception as e:
            self.logger.error(f"Failed to set access token: {str(e)}")
            return None
    
    def get_quote(self, symbols: List[str]) -> Dict:
        """Get current quotes for given symbols."""
        try:
            # Format symbols as "EXCHANGE:SYMBOL"
            formatted_symbols = [f"NSE:{symbol}" for symbol in symbols]
            quotes = self.kite.quote(formatted_symbols)
            return quotes
        except Exception as e:
            self.logger.error(f"Failed to fetch quotes: {str(e)}")
            return {}
    
    def get_ltp(self, symbols: List[str]) -> Dict[str, float]:
        """Get last traded price for given symbols."""
        try:
            formatted_symbols = [f"NSE:{symbol}" for symbol in symbols]
            ltp_data = self.kite.ltp(formatted_symbols)
            return {k: v['last_price'] for k, v in ltp_data.items()}
        except Exception as e:
            self.logger.error(f"Failed to fetch LTP: {str(e)}")
            return {}
    
    def get_historical_data(self, symbol: str, from_date: datetime, 
                           to_date: datetime, interval: str = "day") -> List[Dict]:
        """
        Get historical data for a symbol.
        
        Args:
            symbol: Trading symbol
            from_date: Start date
            to_date: End date
            interval: Candle interval (minute, day, 3minute, 5minute, 10minute, etc.)
        """
        try:
            # You'll need to get instrument token from instruments list
            # This is a simplified version
            instruments = self.kite.instruments("NSE")
            instrument_token = None
            
            for inst in instruments:
                if inst['tradingsymbol'] == symbol:
                    instrument_token = inst['instrument_token']
                    break
            
            if not instrument_token:
                self.logger.error(f"Instrument token not found for {symbol}")
                return []
            
            historical_data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval
            )
            return historical_data
        except Exception as e:
            self.logger.error(f"Failed to fetch historical data: {str(e)}")
            return []
    
    def place_order(self, symbol: str, transaction_type: str, quantity: int,
                    order_type: str = "LIMIT", product: str = "MIS",
                    price: Optional[float] = None, verify_execution: bool = None) -> Optional[str]:
        """
        Place an order with smart execution and optional verification.
        
        Args:
            symbol: Trading symbol
            transaction_type: BUY or SELL
            quantity: Number of shares
            order_type: LIMIT (recommended), MARKET, SL, SL-M
            product: CNC (delivery), MIS (intraday), NRML (normal)
            price: Price for limit orders (auto-calculated if None)
            verify_execution: Wait for execution confirmation (default: True for live trading)
        
        Returns:
            Order ID if successful, None otherwise
        """
        # Apply rate limiting
        if self.rate_limiter:
            self.rate_limiter.acquire()
        
        # Determine if we should verify execution
        if verify_execution is None:
            verify_execution = (self.trading_mode == 'live' and self.order_manager is not None)
        
        try:
            # Smart price calculation for LIMIT orders
            if order_type == "LIMIT" and price is None:
                price = self._calculate_limit_price(symbol, transaction_type)
                if not price:
                    self.logger.error(f"Failed to calculate limit price for {symbol}")
                    return None
            
            # Use order manager for verified execution in live trading
            if verify_execution and self.order_manager:
                result = self.order_manager.place_and_verify_order(
                    symbol=symbol,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    order_type=order_type,
                    product=product,
                    price=price
                )
                if result['status'] == 'COMPLETE':
                    self.logger.info(
                        f"✓ Order executed: {transaction_type} {result['filled_quantity']} {symbol} "
                        f"@ ₹{result['average_price']:.2f}"
                    )
                    return result['order_id']
                else:
                    self.logger.error(f"Order failed: {result.get('message', 'Unknown error')}")
                    return None
            
            # Standard order placement (no verification)
            order_params = {
                'tradingsymbol': symbol,
                'exchange': 'NSE',
                'transaction_type': transaction_type,
                'quantity': quantity,
                'order_type': order_type,
                'product': product,
                'variety': 'regular'
            }
            
            if order_type == "LIMIT" and price:
                order_params['price'] = price
            
            order_id = self.kite.place_order(**order_params)
            self.logger.info(f"Order placed: {order_id} - {transaction_type} {quantity} {symbol} @ ₹{price or 'MARKET'}")
            return order_id
            
        except Exception as e:
            self.logger.error(f"Failed to place order: {str(e)}")
            return None
    
    def _calculate_limit_price(self, symbol: str, transaction_type: str) -> Optional[float]:
        """
        Calculate limit price with slippage buffer.
        
        Args:
            symbol: Trading symbol
            transaction_type: BUY or SELL
        
        Returns:
            Limit price with slippage buffer
        """
        try:
            # Get current LTP
            ltp_data = self.get_ltp([symbol])
            ltp = ltp_data.get(f"NSE:{symbol}", 0)
            
            if ltp <= 0:
                return None
            
            # Apply slippage buffer
            slippage = float(os.getenv('SLIPPAGE_TOLERANCE', '0.003'))  # 0.3% default
            
            if transaction_type == "BUY":
                # Buy slightly above LTP to ensure execution
                limit_price = ltp * (1 + slippage)
            else:  # SELL
                # Sell slightly below LTP to ensure execution
                limit_price = ltp * (1 - slippage)
            
            # Round to 2 decimal places
            limit_price = round(limit_price, 2)
            
            self.logger.debug(
                f"Calculated limit price for {transaction_type} {symbol}: "
                f"LTP=₹{ltp:.2f}, Limit=₹{limit_price:.2f}"
            )
            
            return limit_price
            
        except Exception as e:
            self.logger.error(f"Error calculating limit price: {e}")
            return None
    
    def get_positions(self) -> Dict:
        """Get current positions."""
        try:
            positions = self.kite.positions()
            return positions
        except Exception as e:
            self.logger.error(f"Failed to fetch positions: {str(e)}")
            return {'net': [], 'day': []}
    
    def get_orders(self) -> List[Dict]:
        """Get all orders for the day."""
        try:
            orders = self.kite.orders()
            return orders
        except Exception as e:
            self.logger.error(f"Failed to fetch orders: {str(e)}")
            return []
    
    def cancel_order(self, order_id: str, variety: str = "regular") -> bool:
        """Cancel an order."""
        try:
            self.kite.cancel_order(variety=variety, order_id=order_id)
            self.logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel order: {str(e)}")
            return False
    
    def get_margins(self) -> Dict:
        """Get account margins."""
        try:
            margins = self.kite.margins()
            return margins
        except Exception as e:
            self.logger.error(f"Failed to fetch margins: {str(e)}")
            return {}
    
    def get_holdings(self) -> List[Dict]:
        """Get all holdings (stocks held in delivery)."""
        try:
            holdings = self.kite.holdings()
            return holdings
        except Exception as e:
            self.logger.error(f"Failed to fetch holdings: {str(e)}")
            return []
