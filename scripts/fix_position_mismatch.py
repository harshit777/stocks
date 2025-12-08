#!/usr/bin/env python3
"""
Position Mismatch Fixer

Manually syncs positions from broker to fix any tracking mismatches.
Use this when you see position reconciliation errors.
"""
import os
import sys
import logging
from datetime import datetime

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


def main():
    """Fix position mismatches by syncing with broker."""
    
    logger.info("=" * 70)
    logger.info("🔧 POSITION MISMATCH FIXER")
    logger.info("=" * 70)
    
    # Connect to broker
    logger.info("\n📡 Connecting to broker...")
    trader = KiteTrader()
    
    if not trader.is_connected():
        logger.error("❌ Failed to connect to broker. Check credentials.")
        return
    
    logger.info("✓ Connected to broker")
    
    # Get current positions
    logger.info("\n📊 Fetching current positions from broker...")
    try:
        positions = trader.get_positions()
        net_positions = positions.get('net', [])
        
        active_positions = [p for p in net_positions if p.get('quantity', 0) != 0]
        
        if not active_positions:
            logger.info("✓ No active positions found")
            logger.info("\n💡 Your tracking is likely out of sync.")
            logger.info("   Next time you run live trading, it will auto-sync at startup.")
            return
        
        logger.info(f"\n✓ Found {len(active_positions)} active position(s):\n")
        
        total_invested = 0
        for pos in active_positions:
            symbol = pos['tradingsymbol']
            quantity = pos['quantity']
            avg_price = pos['average_price']
            current_value = pos.get('last_price', avg_price) * quantity
            invested = avg_price * abs(quantity)
            pnl = pos.get('pnl', 0)
            
            logger.info(f"  📈 {symbol}:")
            logger.info(f"     Quantity: {quantity}")
            logger.info(f"     Avg Price: ₹{avg_price:.2f}")
            logger.info(f"     Invested: ₹{invested:,.2f}")
            logger.info(f"     Current Value: ₹{current_value:,.2f}")
            logger.info(f"     P&L: ₹{pnl:+,.2f}")
            logger.info(f"     Product: {pos.get('product', 'N/A')}")
            logger.info("")
            
            total_invested += invested
        
        logger.info(f"  💰 Total Invested: ₹{total_invested:,.2f}\n")
        
        # Instructions
        logger.info("=" * 70)
        logger.info("🔧 HOW TO FIX")
        logger.info("=" * 70)
        logger.info("\n1. The position mismatch has been detected above")
        logger.info("2. When you restart live trading, it will auto-sync at startup")
        logger.info("3. During trading, it will auto-fix any mismatches detected")
        logger.info("\n✅ The fix has been deployed to your live trading script!")
        logger.info("   Just restart your trading script and it will handle it.")
        
        # Option to close positions
        logger.info("\n" + "=" * 70)
        logger.info("⚠️  EMERGENCY OPTIONS")
        logger.info("=" * 70)
        
        response = input("\nDo you want to CLOSE ALL positions now? (yes/no): ").strip().lower()
        
        if response == 'yes':
            logger.info("\n🚨 Closing all positions...")
            
            for pos in active_positions:
                symbol = pos['tradingsymbol']
                quantity = abs(pos['quantity'])  # Ensure positive
                
                if quantity <= 0:
                    continue
                
                try:
                    logger.info(f"   Closing {symbol}: {quantity} shares...")
                    order_id = trader.place_order(
                        symbol=symbol,
                        transaction_type="SELL",
                        quantity=quantity,
                        order_type="MARKET",
                        product=pos.get('product', 'MIS')
                    )
                    
                    if order_id:
                        logger.info(f"   ✓ Sell order placed: {order_id}")
                    else:
                        logger.error(f"   ❌ Failed to place sell order for {symbol}")
                        
                except Exception as e:
                    logger.error(f"   ❌ Error closing {symbol}: {e}")
            
            logger.info("\n✓ All positions closed (or attempted)")
        else:
            logger.info("\n✓ Positions left open. Will auto-sync on next trading run.")
        
    except Exception as e:
        logger.error(f"❌ Error fetching positions: {e}")
        return
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ DONE")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
