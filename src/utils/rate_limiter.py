"""
Rate Limiter for API Calls

Implements token bucket algorithm to enforce rate limits.
Zerodha Kite API limit: 3 requests per second
"""
import time
import logging
import threading
from typing import Optional
from collections import deque
from datetime import datetime


class RateLimiter:
    """
    Token bucket rate limiter with request queuing.
    
    Ensures API calls don't exceed specified rate limit.
    """
    
    def __init__(self, requests_per_second: float = 3.0, burst_size: Optional[int] = None):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_second: Maximum requests allowed per second
            burst_size: Maximum burst capacity (defaults to rate * 2)
        """
        self.rate = requests_per_second
        self.burst_size = burst_size or int(requests_per_second * 2)
        self.tokens = float(self.burst_size)
        self.last_update = time.time()
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        
        # Request tracking
        self.request_times = deque(maxlen=100)
        self.total_requests = 0
        self.rejected_requests = 0
    
    def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens to make request.
        
        Args:
            tokens: Number of tokens to acquire (default: 1)
            timeout: Maximum time to wait for tokens (None = wait forever)
        
        Returns:
            True if tokens acquired, False if timeout
        """
        start_time = time.time()
        
        while True:
            with self.lock:
                self._refill_tokens()
                
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    self.total_requests += 1
                    self.request_times.append(time.time())
                    return True
                
                # Calculate wait time
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.rate
            
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    self.rejected_requests += 1
                    self.logger.warning(
                        f"Rate limit timeout after {elapsed:.2f}s "
                        f"(needed {tokens} tokens, have {self.tokens:.2f})"
                    )
                    return False
                
                # Don't wait longer than remaining timeout
                wait_time = min(wait_time, timeout - elapsed)
            
            # Wait for tokens to refill
            time.sleep(wait_time)
    
    def try_acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens without waiting.
        
        Args:
            tokens: Number of tokens to acquire
        
        Returns:
            True if tokens acquired, False if not available
        """
        with self.lock:
            self._refill_tokens()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                self.total_requests += 1
                self.request_times.append(time.time())
                return True
            
            self.rejected_requests += 1
            return False
    
    def _refill_tokens(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update
        
        # Add tokens based on rate
        new_tokens = elapsed * self.rate
        self.tokens = min(self.burst_size, self.tokens + new_tokens)
        self.last_update = now
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        with self.lock:
            # Calculate recent rate (last 10 seconds)
            now = time.time()
            recent_requests = sum(1 for t in self.request_times if now - t <= 10.0)
            recent_rate = recent_requests / 10.0
            
            return {
                'total_requests': self.total_requests,
                'rejected_requests': self.rejected_requests,
                'current_tokens': self.tokens,
                'max_tokens': self.burst_size,
                'configured_rate': self.rate,
                'recent_rate_10s': recent_rate,
                'utilization': (recent_rate / self.rate * 100) if self.rate > 0 else 0
            }
    
    def reset(self):
        """Reset rate limiter to initial state."""
        with self.lock:
            self.tokens = float(self.burst_size)
            self.last_update = time.time()
            self.total_requests = 0
            self.rejected_requests = 0
            self.request_times.clear()


class PriorityRateLimiter(RateLimiter):
    """
    Rate limiter with priority queue support.
    
    Higher priority requests get processed first.
    """
    
    def __init__(self, requests_per_second: float = 3.0, burst_size: Optional[int] = None):
        super().__init__(requests_per_second, burst_size)
        self.priority_queue = []  # List of (priority, timestamp, callback)
    
    def acquire_with_priority(
        self, 
        priority: int = 0, 
        tokens: int = 1, 
        timeout: Optional[float] = None
    ) -> bool:
        """
        Acquire tokens with priority.
        
        Args:
            priority: Request priority (higher = more important)
            tokens: Number of tokens needed
            timeout: Maximum wait time
        
        Returns:
            True if acquired, False if timeout
        """
        # For simplicity, just use regular acquire
        # In production, implement proper priority queue
        return self.acquire(tokens, timeout)


# Global rate limiter instance
_global_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(requests_per_second: float = 3.0) -> RateLimiter:
    """
    Get or create global rate limiter instance.
    
    Args:
        requests_per_second: Rate limit (default: 3 for Zerodha)
    
    Returns:
        Global RateLimiter instance
    """
    global _global_rate_limiter
    
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter(requests_per_second)
    
    return _global_rate_limiter


def rate_limited(func):
    """
    Decorator to rate limit function calls.
    
    Example:
        @rate_limited
        def fetch_quote(symbol):
            return kite.quote(symbol)
    """
    def wrapper(*args, **kwargs):
        limiter = get_rate_limiter()
        limiter.acquire()
        return func(*args, **kwargs)
    
    return wrapper
