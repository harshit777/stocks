"""
Enhanced Error Handling for Production Trading

Provides:
- Retry decorator with exponential backoff
- Circuit breaker pattern for API failures
- Error classification and handling strategies
"""
import time
import logging
from functools import wraps
from typing import Callable, Optional, Tuple, Type
from datetime import datetime, timedelta


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation
    - OPEN: Too many failures, reject requests
    - HALF_OPEN: Testing if service recovered
    """
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before trying again (HALF_OPEN)
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
        self.logger = logging.getLogger(__name__)
    
    def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
                self.logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is OPEN. Too many failures. "
                    f"Wait {self.timeout}s before retry."
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        return datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout)
    
    def _on_success(self):
        """Handle successful call."""
        if self.state == "HALF_OPEN":
            self.logger.info("Circuit breaker recovered, returning to CLOSED state")
        self.failure_count = 0
        self.state = "CLOSED"
    
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.logger.error(
                f"Circuit breaker OPEN after {self.failure_count} failures"
            )


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class RetryableError(Exception):
    """Base class for errors that should trigger retry."""
    pass


class PermanentError(Exception):
    """Base class for errors that should NOT trigger retry."""
    pass


def classify_error(error: Exception) -> Tuple[bool, str]:
    """
    Classify error as transient (retryable) or permanent.
    
    Returns:
        (is_retryable, error_category)
    """
    error_str = str(error).lower()
    
    # Network/Connection errors - retryable
    if any(term in error_str for term in [
        'timeout', 'connection', 'network', 'unreachable',
        'temporary', 'unavailable', 'rate limit'
    ]):
        return True, "network_error"
    
    # API errors - check specific cases
    if 'invalid token' in error_str or 'authentication' in error_str:
        return False, "authentication_error"
    
    if 'insufficient funds' in error_str or 'margin' in error_str:
        return False, "insufficient_funds"
    
    if 'invalid symbol' in error_str or 'not found' in error_str:
        return False, "invalid_input"
    
    # Server errors (5xx) - retryable
    if '500' in error_str or '502' in error_str or '503' in error_str:
        return True, "server_error"
    
    # Client errors (4xx) - generally not retryable
    if '400' in error_str or '403' in error_str or '404' in error_str:
        return False, "client_error"
    
    # Default: treat unknown errors as retryable with caution
    return True, "unknown_error"


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry
        max_delay: Maximum delay between retries
        retryable_exceptions: Tuple of exception types to retry
    
    Example:
        @retry_with_backoff(max_retries=3, initial_delay=1.0)
        def fetch_quote(symbol):
            return kite.quote(symbol)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    # Check if error is retryable
                    is_retryable, error_category = classify_error(e)
                    
                    if not is_retryable:
                        logger.error(
                            f"{func.__name__} failed with permanent error "
                            f"({error_category}): {e}"
                        )
                        raise PermanentError(f"{error_category}: {e}") from e
                    
                    if attempt == max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} retries: {e}"
                        )
                        raise
                    
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay:.1f}s. Error: {e}"
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
            
            return None  # Should never reach here
        
        return wrapper
    return decorator


def safe_execute(
    func: Callable,
    *args,
    default_return=None,
    log_error: bool = True,
    error_message: Optional[str] = None,
    **kwargs
):
    """
    Execute function safely with error handling.
    
    Args:
        func: Function to execute
        default_return: Value to return on error
        log_error: Whether to log the error
        error_message: Custom error message
        *args, **kwargs: Arguments to pass to function
    
    Returns:
        Function result or default_return on error
    """
    logger = logging.getLogger(func.__module__)
    
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_error:
            msg = error_message or f"Error executing {func.__name__}"
            logger.error(f"{msg}: {e}", exc_info=True)
        return default_return


class RateLimitError(RetryableError):
    """Raised when rate limit is exceeded."""
    pass


class OrderError(Exception):
    """Base class for order-related errors."""
    pass


class OrderRejectedError(OrderError):
    """Raised when order is rejected by broker."""
    pass


class OrderTimeoutError(OrderError):
    """Raised when order doesn't complete within timeout."""
    pass


class PositionMismatchError(Exception):
    """Raised when positions don't match between system and broker."""
    pass
