#!/usr/bin/env python3
"""
Test Capital Recovery Mechanism

Simulates multiple trading days to demonstrate how capital adjusts
based on daily profits and losses.
"""
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.capital_manager import CapitalRecoveryManager


def simulate_trading_days():
    """Simulate a week of trading with wins and losses."""
    
    print("=" * 70)
    print("CAPITAL RECOVERY MECHANISM - SIMULATION")
    print("=" * 70)
    print()
    
    # Initialize with ₹1,000 max capital
    manager = CapitalRecoveryManager(max_initial_capital=1000.0, data_dir='data/capital_test')
    
    # Simulate 7 days of trading
    scenarios = [
        ("Day 1", 50.0, 3),    # Win ₹50
        ("Day 2", -80.0, 5),   # Lose ₹80
        ("Day 3", -30.0, 4),   # Lose ₹30 (capital reduced further)
        ("Day 4", 40.0, 2),    # Win ₹40 (recovering)
        ("Day 5", 60.0, 3),    # Win ₹60 (more recovery)
        ("Day 6", -20.0, 2),   # Lose ₹20
        ("Day 7", 80.0, 4),    # Win ₹80 (back to full capital)
    ]
    
    for day, pnl, trades in scenarios:
        print(f"\n{'='*70}")
        print(f"{day}: Starting Capital = ₹{manager.get_available_capital():,.2f}")
        print(f"{'='*70}")
        
        # Show recovery status
        recovery = manager.get_recovery_status()
        print(f"Status: {recovery['message']}")
        print(f"Recovery: {recovery['recovery_pct']:.1f}%")
        
        # Record the day's results
        print(f"\nTrading Results: P&L = ₹{pnl:+.2f}, Trades = {trades}")
        ending_capital = manager.record_day_end(daily_pnl=pnl, trades_count=trades)
        
        # Reinitialize for next day (simulating new day startup)
        manager = CapitalRecoveryManager(max_initial_capital=1000.0, data_dir='data/capital_test')
    
    # Final summary
    print(f"\n{'='*70}")
    print("FINAL PERFORMANCE SUMMARY")
    print(f"{'='*70}")
    
    summary = manager.get_performance_summary()
    print(f"\nTotal Trading Days: {summary['total_days']}")
    print(f"Total P&L: ₹{summary['total_pnl']:+,.2f}")
    print(f"Average Daily P&L: ₹{summary['avg_daily_pnl']:+,.2f}")
    print(f"Winning Days: {summary['winning_days']}")
    print(f"Losing Days: {summary['losing_days']}")
    print(f"Win Rate: {summary['win_rate']:.1f}%")
    print(f"\nCurrent Capital: ₹{summary['current_capital']:,.2f}")
    print(f"Max Capital: ₹{summary['max_capital']:,.2f}")
    print(f"Capital Recovery: {summary['capital_recovery_pct']:.1f}%")
    
    # Show recent history
    print(f"\n{'='*70}")
    print("RECENT TRADING HISTORY")
    print(f"{'='*70}")
    
    history = manager.get_recent_history(days=7)
    print(f"\n{'Date':<12} {'Start':>10} {'P&L':>10} {'End':>10} {'Recovery':>10}")
    print("-" * 70)
    for record in history:
        print(f"{record['date']:<12} "
              f"₹{record['starting_capital']:>8,.0f} "
              f"₹{record['daily_pnl']:>+8,.0f} "
              f"₹{record['ending_capital']:>8,.0f} "
              f"{record['pnl_pct']:>+8.1f}%")
    
    print(f"\n{'='*70}")
    print("KEY INSIGHTS:")
    print(f"{'='*70}")
    print("1. After Day 2 loss (-₹80), Day 3 started with reduced capital")
    print("2. Consecutive losses further reduced available capital")
    print("3. Profitable days gradually recovered capital")
    print("4. Capital never exceeded the initial ₹1,000 limit")
    print("5. This protects you from risking more than your initial budget")
    print(f"{'='*70}")


if __name__ == "__main__":
    simulate_trading_days()
