"""
Unit Tests for Production Trading Components

Tests for:
- Error handler and retry logic
- Rate limiter
- Cost calculator
- Order manager
- Position reconciler
"""
import unittest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.error_handler import (
    retry_with_backoff, CircuitBreaker, classify_error,
    CircuitBreakerOpenError, PermanentError
)
from src.utils.rate_limiter import RateLimiter
from src.utils.cost_calculator import CostCalculator


class TestErrorHandler(unittest.TestCase):
    """Test error handling utilities."""
    
    def test_classify_error_network(self):
        """Test network error classification."""
        error = Exception("Connection timeout")
        is_retryable, category = classify_error(error)
        self.assertTrue(is_retryable)
        self.assertEqual(category, "network_error")
    
    def test_classify_error_auth(self):
        """Test authentication error classification."""
        error = Exception("Invalid token")
        is_retryable, category = classify_error(error)
        self.assertFalse(is_retryable)
        self.assertEqual(category, "authentication_error")
    
    def test_classify_error_insufficient_funds(self):
        """Test insufficient funds error classification."""
        error = Exception("Insufficient margin")
        is_retryable, category = classify_error(error)
        self.assertFalse(is_retryable)
        self.assertEqual(category, "insufficient_funds")
    
    def test_retry_with_backoff_success(self):
        """Test retry decorator with successful call."""
        call_count = [0]
        
        @retry_with_backoff(max_retries=3, initial_delay=0.1)
        def flaky_function():
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("temporary failure")
            return "success"
        
        result = flaky_function()
        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 2)
    
    def test_retry_with_backoff_permanent_error(self):
        """Test retry decorator with permanent error."""
        @retry_with_backoff(max_retries=3)
        def permanent_fail():
            raise Exception("Invalid token")
        
        with self.assertRaises(PermanentError):
            permanent_fail()
    
    def test_circuit_breaker_opens(self):
        """Test circuit breaker opens after failures."""
        breaker = CircuitBreaker(failure_threshold=3, timeout=60)
        
        def failing_func():
            raise Exception("error")
        
        # Trigger failures
        for _ in range(3):
            try:
                breaker.call(failing_func)
            except:
                pass
        
        # Circuit should be open
        self.assertEqual(breaker.state, "OPEN")
        
        # Next call should raise CircuitBreakerOpenError
        with self.assertRaises(CircuitBreakerOpenError):
            breaker.call(failing_func)
    
    def test_circuit_breaker_closes_on_success(self):
        """Test circuit breaker closes after successful call."""
        breaker = CircuitBreaker(failure_threshold=3, timeout=1)
        
        call_count = [0]
        
        def sometimes_fails():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("error")
            return "success"
        
        # Trigger 2 failures
        for _ in range(2):
            try:
                breaker.call(sometimes_fails)
            except:
                pass
        
        # Should still be closed
        self.assertEqual(breaker.state, "CLOSED")
        
        # Successful call
        result = breaker.call(sometimes_fails)
        self.assertEqual(result, "success")
        self.assertEqual(breaker.failure_count, 0)


class TestRateLimiter(unittest.TestCase):
    """Test rate limiter."""
    
    def test_rate_limiter_allows_within_limit(self):
        """Test rate limiter allows requests within limit."""
        limiter = RateLimiter(requests_per_second=10.0)
        
        # Should allow immediate requests
        self.assertTrue(limiter.try_acquire())
        self.assertTrue(limiter.try_acquire())
    
    def test_rate_limiter_blocks_over_limit(self):
        """Test rate limiter blocks requests over limit."""
        limiter = RateLimiter(requests_per_second=2.0, burst_size=2)
        
        # Consume all tokens
        self.assertTrue(limiter.try_acquire())
        self.assertTrue(limiter.try_acquire())
        
        # Should be blocked
        self.assertFalse(limiter.try_acquire())
    
    def test_rate_limiter_refills_tokens(self):
        """Test rate limiter refills tokens over time."""
        limiter = RateLimiter(requests_per_second=5.0, burst_size=2)
        
        # Consume tokens
        limiter.try_acquire()
        limiter.try_acquire()
        
        # Wait for refill
        time.sleep(0.5)  # Should refill ~2.5 tokens
        
        # Should be able to acquire again
        self.assertTrue(limiter.try_acquire())
    
    def test_rate_limiter_acquire_waits(self):
        """Test rate limiter acquire waits for tokens."""
        limiter = RateLimiter(requests_per_second=5.0, burst_size=1)
        
        # Consume token
        limiter.acquire()
        
        # Next acquire should wait
        start = time.time()
        limiter.acquire()
        elapsed = time.time() - start
        
        # Should have waited ~0.2 seconds (1/5 rate)
        self.assertGreater(elapsed, 0.15)
    
    def test_rate_limiter_stats(self):
        """Test rate limiter statistics."""
        limiter = RateLimiter(requests_per_second=10.0)
        
        limiter.try_acquire()
        limiter.try_acquire()
        
        stats = limiter.get_stats()
        self.assertEqual(stats['total_requests'], 2)
        self.assertGreaterEqual(stats['current_tokens'], 0)


class TestCostCalculator(unittest.TestCase):
    """Test cost calculator."""
    
    def setUp(self):
        self.calculator = CostCalculator()
    
    def test_brokerage_intraday(self):
        """Test brokerage calculation for intraday."""
        # Small trade: 0.03% = 1.5
        brokerage = self.calculator.calculate_brokerage(5000, "MIS")
        self.assertAlmostEqual(brokerage, 1.5, places=2)
        
        # Large trade: should be ₹20 (min of 20 or 0.03%)
        brokerage = self.calculator.calculate_brokerage(100000, "MIS")
        self.assertEqual(brokerage, 20.0)  # min(20, 30) = 20
    
    def test_brokerage_delivery(self):
        """Test brokerage calculation for delivery."""
        brokerage = self.calculator.calculate_brokerage(50000, "CNC")
        self.assertEqual(brokerage, 0.0)  # Free at Zerodha
    
    def test_stt_intraday(self):
        """Test STT calculation for intraday."""
        # Buy: no STT
        stt = self.calculator.calculate_stt(10000, "BUY", "MIS")
        self.assertEqual(stt, 0.0)
        
        # Sell: 0.025%
        stt = self.calculator.calculate_stt(10000, "SELL", "MIS")
        self.assertEqual(stt, 2.5)
    
    def test_total_cost_buy(self):
        """Test total cost calculation for buy order."""
        costs = self.calculator.calculate_total_cost(
            price=1000,
            quantity=10,
            transaction_type="BUY",
            product="MIS"
        )
        
        self.assertEqual(costs['trade_value'], 10000)
        self.assertGreater(costs['total_cost'], 0)  # Has costs
        self.assertIn('brokerage', costs)
        self.assertIn('stt', costs)
        self.assertIn('gst', costs)
        self.assertIn('stamp_duty', costs)
    
    def test_total_cost_sell(self):
        """Test total cost calculation for sell order."""
        costs = self.calculator.calculate_total_cost(
            price=1000,
            quantity=10,
            transaction_type="SELL",
            product="MIS"
        )
        
        self.assertEqual(costs['trade_value'], 10000)
        self.assertGreater(costs['stt'], 0)  # Should have STT
        self.assertEqual(costs['stamp_duty'], 0)  # No stamp duty on sell
    
    def test_round_trip_cost(self):
        """Test round trip cost calculation."""
        costs = self.calculator.calculate_round_trip_cost(
            buy_price=1450,
            sell_price=1470,
            quantity=10,
            product="MIS"
        )
        
        self.assertEqual(costs['buy_value'], 14500)
        self.assertEqual(costs['sell_value'], 14700)
        self.assertEqual(costs['gross_profit'], 200)
        self.assertLess(costs['net_profit'], costs['gross_profit'])  # Costs reduce profit
        self.assertGreater(costs['total_costs'], 0)  # Has costs
    
    def test_breakeven_price(self):
        """Test breakeven price calculation."""
        breakeven = self.calculator.get_breakeven_price(
            buy_price=1000,
            quantity=10,
            product="MIS"
        )
        
        # Breakeven should be slightly above buy price
        self.assertGreater(breakeven, 1000)
        self.assertLess(breakeven, 1010)  # Should be reasonable


class TestOrderManager(unittest.TestCase):
    """Test order manager (with mocked KiteTrader)."""
    
    def setUp(self):
        from src.kite_trader.order_manager import OrderManager
        self.mock_trader = Mock()
        self.order_manager = OrderManager(
            self.mock_trader,
            order_timeout=5,
            poll_interval=0.5
        )
    
    def test_order_manager_initialization(self):
        """Test order manager initializes correctly."""
        self.assertEqual(self.order_manager.order_timeout, 5)
        self.assertEqual(self.order_manager.poll_interval, 0.5)
        self.assertEqual(len(self.order_manager.active_orders), 0)
    
    def test_get_stats(self):
        """Test order manager statistics."""
        stats = self.order_manager.get_stats()
        self.assertIn('total_orders', stats)
        self.assertIn('successful_orders', stats)
        self.assertIn('failed_orders', stats)
        self.assertIn('success_rate', stats)


class TestPositionReconciler(unittest.TestCase):
    """Test position reconciler (with mocked KiteTrader)."""
    
    def setUp(self):
        from src.kite_trader.position_reconciler import PositionReconciler
        self.mock_trader = Mock()
        self.reconciler = PositionReconciler(self.mock_trader, tolerance=0.01)
    
    def test_reconciler_initialization(self):
        """Test position reconciler initializes correctly."""
        self.assertEqual(self.reconciler.tolerance, 0.01)
        self.assertIsNone(self.reconciler.last_sync_time)
        self.assertEqual(self.reconciler.sync_count, 0)
    
    def test_prices_match_within_tolerance(self):
        """Test price matching within tolerance."""
        # Prices within 1% should match
        self.assertTrue(self.reconciler._prices_match(1000, 1005))
        self.assertTrue(self.reconciler._prices_match(1000, 995))
        
        # Prices outside 1% should not match
        self.assertFalse(self.reconciler._prices_match(1000, 1020))
        self.assertFalse(self.reconciler._prices_match(1000, 980))
    
    def test_reconcile_matching_positions(self):
        """Test reconciliation with matching positions."""
        # Mock broker positions
        self.mock_trader.get_positions.return_value = {
            'net': [
                {
                    'tradingsymbol': 'RELIANCE',
                    'quantity': 10,
                    'average_price': 1450.0
                }
            ]
        }
        
        # Tracked positions
        tracked = {
            'RELIANCE': {
                'quantity': 10,
                'average_price': 1450.0,
                'product': 'MIS'
            }
        }
        
        result = self.reconciler.reconcile_positions(tracked)
        self.assertEqual(result['status'], 'OK')
        self.assertEqual(result['matched'], 1)
        self.assertEqual(result['mismatched'], 0)
    
    def test_reconcile_quantity_mismatch(self):
        """Test reconciliation detects quantity mismatch."""
        self.mock_trader.get_positions.return_value = {
            'net': [
                {
                    'tradingsymbol': 'RELIANCE',
                    'quantity': 10,
                    'average_price': 1450.0
                }
            ]
        }
        
        tracked = {
            'RELIANCE': {
                'quantity': 5,  # Mismatch
                'average_price': 1450.0
            }
        }
        
        result = self.reconciler.reconcile_positions(tracked)
        self.assertEqual(result['status'], 'MISMATCH')
        self.assertEqual(result['mismatched'], 1)
        self.assertEqual(len(result['discrepancies']), 1)
        self.assertEqual(result['discrepancies'][0]['type'], 'QUANTITY_MISMATCH')


def run_tests():
    """Run all tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestRateLimiter))
    suite.addTests(loader.loadTestsFromTestCase(TestCostCalculator))
    suite.addTests(loader.loadTestsFromTestCase(TestOrderManager))
    suite.addTests(loader.loadTestsFromTestCase(TestPositionReconciler))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return success status
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
