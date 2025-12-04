"""
Order Management System for Production Trading

Features:
- Order status tracking and verification
- Timeout handling with automatic cancellation
- Execution confirmation
- Order history and failure tracking
"""
import time
import logging
from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum

from ..utils.error_handler import (
    OrderError, OrderRejectedError, OrderTimeoutError,
    retry_with_backoff
)


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class OrderManager:
    """
    Manages order lifecycle from placement to completion.
    
    Handles:
    - Order placement with verification
    - Status polling
    - Timeout and cancellation
    - Execution confirmation
    """
    
    def __init__(
        self,
        kite_trader,
        order_timeout: int = 30,
        poll_interval: float = 1.0,
        max_poll_attempts: int = 30
    ):
        """
        Initialize order manager.
        
        Args:
            kite_trader: KiteTrader instance
            order_timeout: Maximum seconds to wait for order completion
            poll_interval: Seconds between status polls
            max_poll_attempts: Maximum number of status polls
        """
        self.kite = kite_trader
        self.order_timeout = order_timeout
        self.poll_interval = poll_interval
        self.max_poll_attempts = max_poll_attempts
        self.logger = logging.getLogger(__name__)
        
        # Order tracking
        self.active_orders: Dict[str, Dict] = {}  # order_id -> order_info
        self.order_history: List[Dict] = []
        self.failed_orders: List[Dict] = []
    
    def place_and_verify_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "LIMIT",
        product: str = "MIS",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> Dict:
        """
        Place order and verify execution.
        
        Args:
            symbol: Trading symbol
            transaction_type: BUY or SELL
            quantity: Number of shares
            order_type: MARKET or LIMIT
            product: MIS or CNC
            price: Limit price (required for LIMIT orders)
            trigger_price: Trigger price for stop loss orders
        
        Returns:
            Dict with order result:
            {
                'status': 'COMPLETE'/'REJECTED'/'TIMEOUT',
                'order_id': str,
                'filled_quantity': int,
                'average_price': float,
                'message': str
            }
        
        Raises:
            OrderRejectedError: If order is rejected
            OrderTimeoutError: If order doesn't complete within timeout
        """
        self.logger.info(
            f"Placing {order_type} {transaction_type} order: "
            f"{quantity} {symbol} @ {price or 'MARKET'}"
        )
        
        # Place order
        order_id = self._place_order(
            symbol, transaction_type, quantity,
            order_type, product, price, trigger_price
        )
        
        if not order_id:
            raise OrderError(f"Failed to place order for {symbol}")
        
        # Track order
        order_info = {
            'order_id': order_id,
            'symbol': symbol,
            'transaction_type': transaction_type,
            'quantity': quantity,
            'order_type': order_type,
            'product': product,
            'price': price,
            'placed_at': datetime.now(),
            'status': OrderStatus.PENDING
        }
        self.active_orders[order_id] = order_info
        
        # Wait for order completion
        try:
            result = self._wait_for_order_completion(order_id)
            self.order_history.append({**order_info, **result})
            return result
        
        except OrderTimeoutError as e:
            self.logger.error(f"Order {order_id} timed out, attempting to cancel")
            self._cancel_order(order_id)
            self.failed_orders.append(order_info)
            raise
        
        except OrderRejectedError as e:
            self.logger.error(f"Order {order_id} rejected: {e}")
            self.failed_orders.append(order_info)
            raise
        
        finally:
            # Remove from active orders
            if order_id in self.active_orders:
                del self.active_orders[order_id]
    
    @retry_with_backoff(max_retries=2, initial_delay=0.5)
    def _place_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        product: str,
        price: Optional[float],
        trigger_price: Optional[float]
    ) -> Optional[str]:
        """Place order with retry logic."""
        try:
            order_id = self.kite.place_order(
                symbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=order_type,
                product=product,
                price=price
            )
            return order_id
        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            raise
    
    def _wait_for_order_completion(self, order_id: str) -> Dict:
        """
        Poll order status until completion or timeout.
        
        Returns:
            Order result dict
        
        Raises:
            OrderTimeoutError: If order doesn't complete
            OrderRejectedError: If order is rejected
        """
        start_time = time.time()
        attempts = 0
        
        while attempts < self.max_poll_attempts:
            # Check timeout
            if time.time() - start_time > self.order_timeout:
                raise OrderTimeoutError(
                    f"Order {order_id} timed out after {self.order_timeout}s"
                )
            
            # Get order status
            order_status = self._get_order_status(order_id)
            
            if not order_status:
                attempts += 1
                time.sleep(self.poll_interval)
                continue
            
            status = order_status.get('status', 'UNKNOWN')
            
            # Order complete
            if status == 'COMPLETE':
                self.logger.info(
                    f"Order {order_id} completed: "
                    f"{order_status.get('filled_quantity', 0)} @ "
                    f"₹{order_status.get('average_price', 0):.2f}"
                )
                return {
                    'status': 'COMPLETE',
                    'order_id': order_id,
                    'filled_quantity': order_status.get('filled_quantity', 0),
                    'average_price': order_status.get('average_price', 0),
                    'message': 'Order executed successfully'
                }
            
            # Order rejected
            elif status in ['REJECTED', 'CANCELLED']:
                error_msg = order_status.get('status_message', 'Unknown reason')
                raise OrderRejectedError(
                    f"Order {order_id} {status}: {error_msg}"
                )
            
            # Order still pending/open
            elif status in ['PENDING', 'OPEN', 'TRIGGER PENDING']:
                self.logger.debug(f"Order {order_id} status: {status}")
                attempts += 1
                time.sleep(self.poll_interval)
            
            else:
                self.logger.warning(f"Unknown order status: {status}")
                attempts += 1
                time.sleep(self.poll_interval)
        
        # Max attempts reached
        raise OrderTimeoutError(
            f"Order {order_id} status unknown after {attempts} attempts"
        )
    
    @retry_with_backoff(max_retries=2, initial_delay=0.5)
    def _get_order_status(self, order_id: str) -> Optional[Dict]:
        """
        Get order status from broker.
        
        Returns:
            Order details dict or None
        """
        try:
            orders = self.kite.get_orders()
            for order in orders:
                if order.get('order_id') == order_id:
                    return order
            
            self.logger.warning(f"Order {order_id} not found in orders list")
            return None
        
        except Exception as e:
            self.logger.error(f"Error fetching order status: {e}")
            return None
    
    def _cancel_order(self, order_id: str) -> bool:
        """
        Cancel pending order.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            True if cancelled successfully
        """
        try:
            result = self.kite.cancel_order(order_id)
            self.logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def get_active_orders(self) -> List[Dict]:
        """Get list of currently active orders."""
        return list(self.active_orders.values())
    
    def get_order_history(self, limit: int = 50) -> List[Dict]:
        """
        Get recent order history.
        
        Args:
            limit: Maximum number of orders to return
        
        Returns:
            List of recent orders
        """
        return self.order_history[-limit:]
    
    def get_failed_orders(self) -> List[Dict]:
        """Get list of failed orders."""
        return self.failed_orders
    
    def get_stats(self) -> Dict:
        """
        Get order management statistics.
        
        Returns:
            Dict with stats
        """
        total_orders = len(self.order_history)
        failed_orders = len(self.failed_orders)
        success_rate = ((total_orders - failed_orders) / total_orders * 100) if total_orders > 0 else 0
        
        return {
            'total_orders': total_orders,
            'successful_orders': total_orders - failed_orders,
            'failed_orders': failed_orders,
            'success_rate': round(success_rate, 2),
            'active_orders': len(self.active_orders)
        }
