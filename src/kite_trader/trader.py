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
    """Wrapper class for Zerodha Kite API operations."""
    
    def __init__(self):
        """Initialize the Kite trader with API credentials."""
        self.logger = logging.getLogger(__name__)
        
        # Load credentials from environment variables
        self.api_key = os.getenv('KITE_API_KEY')
        self.api_secret = os.getenv('KITE_API_SECRET')
        self.access_token = os.getenv('KITE_ACCESS_TOKEN')
        
        if not self.api_key:
            self.logger.warning("KITE_API_KEY not found in environment variables")
        
        self.kite = None
        self._initialize_connection()
    
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
                    order_type: str = "MARKET", product: str = "MIS",
                    price: Optional[float] = None) -> Optional[str]:
        """
        Place an order.
        
        Args:
            symbol: Trading symbol
            transaction_type: BUY or SELL
            quantity: Number of shares
            order_type: MARKET, LIMIT, SL, SL-M
            product: CNC (delivery), MIS (intraday), NRML (normal)
            price: Price for limit orders
        
        Returns:
            Order ID if successful, None otherwise
        """
        try:
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
            self.logger.info(f"Order placed: {order_id} - {transaction_type} {quantity} {symbol}")
            return order_id
            
        except Exception as e:
            self.logger.error(f"Failed to place order: {str(e)}")
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
