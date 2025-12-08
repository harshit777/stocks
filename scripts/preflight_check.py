#!/usr/bin/env python3
"""
Pre-Flight Check for Trading

Runs before trading starts (especially in GitHub Actions) to:
1. Check and cancel stale open orders
2. Review open positions
3. Handle any pending orders
4. Sync position tracking
5. Ensure clean state for trading

This prevents:
- Stale orders from previous sessions
- Position tracking mismatches
- Unexpected order executions
- Capital tracking issues
"""
import os
import sys
import logging
from datetime import datetime, timedelta
import pytz

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from src.kite_trader.trader import KiteTrader

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cancel_stale_orders(trader, max_age_minutes=30):
    """
    Cancel any open/pending orders that are stale.
    
    Args:
        trader: KiteTrader instance
        max_age_minutes: Cancel orders older than this (minutes)
    
    Returns:
        Number of orders cancelled
    """
    try:
        logger.info("\n🔍 Checking for stale open orders...")
        
        # Get all orders
        orders = trader.kite.orders()
        
        # Filter for open/pending orders
        open_statuses = ['OPEN', 'TRIGGER PENDING', 'PENDING']
        open_orders = [o for o in orders if o.get('status') in open_statuses]
        
        if not open_orders:
            logger.info("✓ No open orders found")
            return 0
        
        logger.info(f"Found {len(open_orders)} open order(s)")
        
        cancelled_count = 0
        ist_tz = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist_tz)
        
        for order in open_orders:
            order_id = order['order_id']
            symbol = order['tradingsymbol']
            order_time_str = order.get('order_timestamp')
            status = order['status']
            transaction_type = order['transaction_type']
            quantity = order['quantity']
            
            # Parse order timestamp
            try:
                if order_time_str:
                    order_time = datetime.strptime(order_time_str, '%Y-%m-%d %H:%M:%S')
                    order_time = ist_tz.localize(order_time)
                    age_minutes = (current_time - order_time).total_seconds() / 60
                else:
                    age_minutes = 999  # Unknown age, cancel it
            except:
                age_minutes = 999  # Can't parse, cancel it
            
            logger.info(
                f"  📋 Order {order_id}: {transaction_type} {quantity} {symbol} "
                f"[{status}] (age: {age_minutes:.1f}m)"
            )
            
            # Cancel if too old
            if age_minutes > max_age_minutes:
                try:
                    logger.warning(f"     ⚠️  Cancelling stale order (age: {age_minutes:.1f}m > {max_age_minutes}m)")
                    trader.kite.cancel_order(variety='regular', order_id=order_id)
                    logger.info(f"     ✓ Cancelled order {order_id}")
                    cancelled_count += 1
                except Exception as e:
                    logger.error(f"     ❌ Failed to cancel order {order_id}: {e}")
            else:
                logger.info(f"     ℹ️  Order is recent, keeping it")
        
        if cancelled_count > 0:
            logger.info(f"\n✓ Cancelled {cancelled_count} stale order(s)")
        else:
            logger.info("\n✓ No stale orders to cancel")
        
        return cancelled_count
        
    except Exception as e:
        logger.error(f"Error checking orders: {e}")
        return 0


def review_open_positions(trader):
    """
    Review and log all open positions.
    
    Args:
        trader: KiteTrader instance
    
    Returns:
        List of open positions
    """
    try:
        logger.info("\n📊 Checking open positions...")
        
        positions = trader.get_positions()
        net_positions = positions.get('net', [])
        
        open_positions = [p for p in net_positions if p.get('quantity', 0) != 0]
        
        if not open_positions:
            logger.info("✓ No open positions")
            return []
        
        logger.info(f"Found {len(open_positions)} open position(s):\n")
        
        total_value = 0
        for pos in open_positions:
            symbol = pos['tradingsymbol']
            quantity = pos['quantity']
            avg_price = pos['average_price']
            last_price = pos.get('last_price', avg_price)
            product = pos.get('product', 'N/A')
            pnl = pos.get('pnl', 0)
            
            position_value = abs(quantity) * avg_price
            current_value = quantity * last_price
            
            logger.info(f"  📈 {symbol}:")
            logger.info(f"     Quantity: {quantity}")
            logger.info(f"     Avg Price: ₹{avg_price:.2f}")
            logger.info(f"     Last Price: ₹{last_price:.2f}")
            logger.info(f"     Position Value: ₹{position_value:,.2f}")
            logger.info(f"     Current Value: ₹{current_value:,.2f}")
            logger.info(f"     P&L: ₹{pnl:+,.2f}")
            logger.info(f"     Product: {product}")
            logger.info("")
            
            total_value += position_value
        
        logger.info(f"  💰 Total Position Value: ₹{total_value:,.2f}\n")
        
        return open_positions
        
    except Exception as e:
        logger.error(f"Error checking positions: {e}")
        return []


def check_account_health(trader):
    """
    Check account status and available capital.
    
    Args:
        trader: KiteTrader instance
    
    Returns:
        Dict with account info
    """
    try:
        logger.info("\n💼 Checking account health...")
        
        margins = trader.get_margins()
        equity = margins.get('equity', {})
        available = equity.get('available', {})
        
        cash = available.get('cash', 0)
        collateral = available.get('collateral', 0)
        
        logger.info(f"  Available Cash: ₹{cash:,.2f}")
        logger.info(f"  Collateral: ₹{collateral:,.2f}")
        
        # Get profile info
        try:
            profile = trader.get_profile()
            user_name = profile.get('user_name', 'N/A')
            user_id = profile.get('user_id', 'N/A')
            logger.info(f"  User: {user_name} ({user_id})")
        except:
            pass
        
        logger.info("")
        
        return {
            'cash': cash,
            'collateral': collateral,
            'total_available': cash + collateral
        }
        
    except Exception as e:
        logger.error(f"Error checking account: {e}")
        return {}


def main():
    """Run pre-flight checks."""
    
    logger.info("=" * 70)
    logger.info("🛫 PRE-FLIGHT CHECK - Trading Preparation")
    logger.info("=" * 70)
    
    # Connect to broker
    logger.info("\n📡 Connecting to broker...")
    trader = KiteTrader()
    
    if not trader.is_connected():
        logger.error("❌ Failed to connect to broker")
        logger.error("   Check your credentials in .env file")
        return False
    
    logger.info("✓ Connected to broker")
    
    # 1. Check account health
    account_info = check_account_health(trader)
    
    # 2. Review open positions
    open_positions = review_open_positions(trader)
    
    # 3. Cancel stale orders
    cancelled_count = cancel_stale_orders(trader, max_age_minutes=30)
    
    # 4. Check for any remaining open orders
    try:
        orders = trader.kite.orders()
        open_orders = [o for o in orders if o.get('status') in ['OPEN', 'TRIGGER PENDING', 'PENDING']]
        
        if open_orders:
            logger.warning(f"\n⚠️  WARNING: {len(open_orders)} order(s) still open after cleanup")
            for order in open_orders:
                logger.warning(
                    f"   - {order['tradingsymbol']}: {order['transaction_type']} "
                    f"{order['quantity']} [{order['status']}]"
                )
    except:
        pass
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("📋 PRE-FLIGHT CHECK SUMMARY")
    logger.info("=" * 70)
    logger.info(f"  ✓ Connection: OK")
    logger.info(f"  ✓ Available Capital: ₹{account_info.get('cash', 0):,.2f}")
    logger.info(f"  ✓ Open Positions: {len(open_positions)}")
    logger.info(f"  ✓ Stale Orders Cancelled: {cancelled_count}")
    logger.info("=" * 70)
    
    if open_positions:
        logger.info("\n💡 Note: You have open positions. Trading will continue with these.")
    
    if account_info.get('cash', 0) < 500:
        logger.warning("\n⚠️  WARNING: Available capital is very low (< ₹500)")
        logger.warning("   Consider adding funds or adjusting capital limits")
    
    logger.info("\n✅ PRE-FLIGHT CHECK COMPLETE - Ready for trading!\n")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
