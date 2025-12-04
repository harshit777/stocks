"""
Broker Health Check Utility

Monitors broker API health and prevents trading during downtime.
"""
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional


class BrokerHealthMonitor:
    """
    Monitors broker API health and detects downtime.
    
    Features:
    - Periodic health checks
    - Failure tracking
    - Automatic back-off on repeated failures
    - Trading halt on extended downtime
    """
    
    def __init__(
        self,
        trader,
        check_interval: int = 60,  # Check every minute
        failure_threshold: int = 3,  # Halt after 3 consecutive failures
        backoff_multiplier: float = 2.0
    ):
        """
        Initialize broker health monitor.
        
        Args:
            trader: KiteTrader instance
            check_interval: Seconds between health checks
            failure_threshold: Consecutive failures before halting
            backoff_multiplier: Multiplier for exponential backoff
        """
        self.trader = trader
        self.check_interval = check_interval
        self.failure_threshold = failure_threshold
        self.backoff_multiplier = backoff_multiplier
        
        self.logger = logging.getLogger(__name__)
        
        # Health tracking
        self.consecutive_failures = 0
        self.last_check_time = None
        self.last_success_time = None
        self.is_healthy = True
        self.current_backoff = check_interval
        
        # Failure history
        self.failure_history = []
        self.max_history = 100
    
    def check_health(self) -> Dict:
        """
        Check broker API health.
        
        Returns:
            Dict with health status:
            {
                'is_healthy': bool,
                'consecutive_failures': int,
                'last_error': str or None,
                'next_check_in': int (seconds),
                'should_halt': bool
            }
        """
        now = datetime.now()
        
        # Check if enough time has passed since last check
        if self.last_check_time:
            time_since_last = (now - self.last_check_time).total_seconds()
            if time_since_last < self.current_backoff:
                return {
                    'is_healthy': self.is_healthy,
                    'consecutive_failures': self.consecutive_failures,
                    'last_error': None,
                    'next_check_in': int(self.current_backoff - time_since_last),
                    'should_halt': self.consecutive_failures >= self.failure_threshold
                }
        
        # Perform health check
        try:
            # Try to fetch profile as a health check
            profile = self.trader.get_profile()
            
            if profile and profile.get('user_id'):
                # Success
                self.is_healthy = True
                self.consecutive_failures = 0
                self.last_success_time = now
                self.current_backoff = self.check_interval  # Reset backoff
                
                self.logger.debug("Broker health check: OK")
                
                return {
                    'is_healthy': True,
                    'consecutive_failures': 0,
                    'last_error': None,
                    'next_check_in': self.check_interval,
                    'should_halt': False
                }
            else:
                # Empty response
                raise Exception("Empty profile response")
        
        except Exception as e:
            # Failure
            self.consecutive_failures += 1
            error_msg = str(e)
            
            # Record failure
            self.failure_history.append({
                'time': now,
                'error': error_msg,
                'consecutive': self.consecutive_failures
            })
            
            # Trim history
            if len(self.failure_history) > self.max_history:
                self.failure_history = self.failure_history[-self.max_history:]
            
            # Update health status
            if self.consecutive_failures >= self.failure_threshold:
                self.is_healthy = False
                self.logger.error(
                    f"🚨 Broker health check FAILED {self.consecutive_failures} times: {error_msg}"
                )
                self.logger.error(
                    f"🛑 Broker appears to be down. Trading should be halted."
                )
            else:
                self.logger.warning(
                    f"⚠️  Broker health check failed ({self.consecutive_failures}/{self.failure_threshold}): {error_msg}"
                )
            
            # Apply exponential backoff
            self.current_backoff = min(
                self.current_backoff * self.backoff_multiplier,
                300  # Max 5 minutes
            )
            
            return {
                'is_healthy': False,
                'consecutive_failures': self.consecutive_failures,
                'last_error': error_msg,
                'next_check_in': int(self.current_backoff),
                'should_halt': self.consecutive_failures >= self.failure_threshold
            }
        
        finally:
            self.last_check_time = now
    
    def get_status(self) -> Dict:
        """Get current health status without performing check."""
        return {
            'is_healthy': self.is_healthy,
            'consecutive_failures': self.consecutive_failures,
            'last_check': self.last_check_time.isoformat() if self.last_check_time else None,
            'last_success': self.last_success_time.isoformat() if self.last_success_time else None,
            'recent_failures': len([f for f in self.failure_history if (datetime.now() - f['time']).total_seconds() < 3600])
        }
    
    def reset(self):
        """Reset health monitor (e.g., after manual broker reconnection)."""
        self.consecutive_failures = 0
        self.is_healthy = True
        self.current_backoff = self.check_interval
        self.logger.info("Broker health monitor reset")
