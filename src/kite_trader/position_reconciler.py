"""
Position Reconciliation Service

Ensures tracked positions match broker's actual positions.
Detects and alerts on discrepancies.
"""
import logging
from typing import Dict, List, Tuple
from datetime import datetime

from ..utils.error_handler import PositionMismatchError, retry_with_backoff


class PositionReconciler:
    """
    Reconciles positions between trading system and broker.
    
    Features:
    - Periodic position sync
    - Discrepancy detection
    - Auto-correction or alerts
    - Realized P&L tracking
    """
    
    def __init__(self, kite_trader, tolerance: float = 0.01):
        """
        Initialize position reconciler.
        
        Args:
            kite_trader: KiteTrader instance
            tolerance: Price tolerance for matching (1% default)
        """
        self.kite = kite_trader
        self.tolerance = tolerance
        self.logger = logging.getLogger(__name__)
        
        # Tracking
        self.last_sync_time = None
        self.discrepancies_found = []
        self.sync_count = 0
    
    @retry_with_backoff(max_retries=2)
    def reconcile_positions(self, tracked_positions: Dict[str, Dict]) -> Dict:
        """
        Reconcile tracked positions with broker positions.
        
        Args:
            tracked_positions: Dict of symbol -> position info
                {
                    'RELIANCE': {
                        'quantity': 10,
                        'average_price': 1450.00,
                        'product': 'MIS'
                    },
                    ...
                }
        
        Returns:
            Reconciliation result:
            {
                'status': 'OK'/'MISMATCH',
                'matched': int,
                'mismatched': int,
                'discrepancies': List[Dict],
                'broker_positions': List[Dict]
            }
        """
        self.logger.info("Starting position reconciliation...")
        
        # Fetch broker positions
        broker_positions = self._fetch_broker_positions()
        
        if not broker_positions:
            self.logger.warning("No broker positions fetched, skipping reconciliation")
            return {
                'status': 'SKIPPED',
                'matched': 0,
                'mismatched': 0,
                'discrepancies': [],
                'broker_positions': []
            }
        
        # Convert broker positions to dict for easy lookup
        broker_pos_dict = {
            pos['tradingsymbol']: pos 
            for pos in broker_positions 
            if pos.get('quantity', 0) != 0
        }
        
        # Find discrepancies
        discrepancies = []
        matched_count = 0
        
        # Check tracked positions exist in broker
        for symbol, tracked_pos in tracked_positions.items():
            broker_pos = broker_pos_dict.get(symbol)
            
            if not broker_pos:
                # Position exists in system but not in broker
                discrepancy = {
                    'symbol': symbol,
                    'type': 'MISSING_IN_BROKER',
                    'tracked_quantity': tracked_pos.get('quantity', 0),
                    'broker_quantity': 0,
                    'tracked_price': tracked_pos.get('average_price', 0),
                    'broker_price': 0,
                    'timestamp': datetime.now().isoformat()
                }
                discrepancies.append(discrepancy)
                self.logger.error(
                    f"Position mismatch: {symbol} exists in system ({tracked_pos['quantity']}) "
                    f"but not in broker"
                )
                continue
            
            # Compare quantities
            tracked_qty = tracked_pos.get('quantity', 0)
            broker_qty = broker_pos.get('quantity', 0)
            
            if tracked_qty != broker_qty:
                discrepancy = {
                    'symbol': symbol,
                    'type': 'QUANTITY_MISMATCH',
                    'tracked_quantity': tracked_qty,
                    'broker_quantity': broker_qty,
                    'difference': broker_qty - tracked_qty,
                    'timestamp': datetime.now().isoformat()
                }
                discrepancies.append(discrepancy)
                self.logger.error(
                    f"Quantity mismatch: {symbol} - "
                    f"tracked: {tracked_qty}, broker: {broker_qty}"
                )
                continue
            
            # Compare average prices (with tolerance)
            tracked_price = tracked_pos.get('average_price', 0)
            broker_price = broker_pos.get('average_price', 0)
            
            if not self._prices_match(tracked_price, broker_price):
                discrepancy = {
                    'symbol': symbol,
                    'type': 'PRICE_MISMATCH',
                    'tracked_price': tracked_price,
                    'broker_price': broker_price,
                    'difference_pct': ((broker_price - tracked_price) / tracked_price * 100) if tracked_price > 0 else 0,
                    'timestamp': datetime.now().isoformat()
                }
                discrepancies.append(discrepancy)
                self.logger.warning(
                    f"Price mismatch: {symbol} - "
                    f"tracked: ₹{tracked_price:.2f}, broker: ₹{broker_price:.2f}"
                )
                continue
            
            # Positions match
            matched_count += 1
            self.logger.debug(f"Position matched: {symbol}")
        
        # Check for positions in broker but not in system
        for symbol, broker_pos in broker_pos_dict.items():
            if symbol not in tracked_positions:
                discrepancy = {
                    'symbol': symbol,
                    'type': 'MISSING_IN_SYSTEM',
                    'tracked_quantity': 0,
                    'broker_quantity': broker_pos.get('quantity', 0),
                    'broker_price': broker_pos.get('average_price', 0),
                    'timestamp': datetime.now().isoformat()
                }
                discrepancies.append(discrepancy)
                self.logger.error(
                    f"Position mismatch: {symbol} exists in broker ({broker_pos['quantity']}) "
                    f"but not in system"
                )
        
        # Store discrepancies
        if discrepancies:
            self.discrepancies_found.extend(discrepancies)
        
        # Update tracking
        self.last_sync_time = datetime.now()
        self.sync_count += 1
        
        result = {
            'status': 'OK' if not discrepancies else 'MISMATCH',
            'matched': matched_count,
            'mismatched': len(discrepancies),
            'discrepancies': discrepancies,
            'broker_positions': broker_positions,
            'sync_time': self.last_sync_time.isoformat()
        }
        
        # Log summary
        if discrepancies:
            self.logger.error(
                f"Position reconciliation FAILED: {matched_count} matched, "
                f"{len(discrepancies)} mismatched"
            )
        else:
            self.logger.info(
                f"Position reconciliation OK: {matched_count} positions matched"
            )
        
        return result
    
    def _fetch_broker_positions(self) -> List[Dict]:
        """Fetch current positions from broker."""
        try:
            positions = self.kite.get_positions()
            # Return net positions (day + overnight)
            return positions.get('net', [])
        except Exception as e:
            self.logger.error(f"Error fetching broker positions: {e}")
            return []
    
    def _prices_match(self, price1: float, price2: float) -> bool:
        """
        Check if two prices match within tolerance.
        
        Args:
            price1: First price
            price2: Second price
        
        Returns:
            True if prices match within tolerance
        """
        if price1 == 0 or price2 == 0:
            return price1 == price2
        
        diff_pct = abs(price1 - price2) / price1
        return diff_pct <= self.tolerance
    
    def get_stats(self) -> Dict:
        """Get reconciliation statistics."""
        return {
            'total_syncs': self.sync_count,
            'last_sync': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'total_discrepancies': len(self.discrepancies_found),
            'recent_discrepancies': self.discrepancies_found[-10:] if self.discrepancies_found else []
        }
    
    def clear_discrepancies(self):
        """Clear discrepancy history."""
        self.discrepancies_found.clear()
        self.logger.info("Discrepancy history cleared")
