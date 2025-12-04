"""
Market Calendar Utility

Detects market holidays and trading sessions for NSE.
"""
from datetime import datetime, date
from typing import List, Set
import logging


class MarketCalendar:
    """
    NSE market calendar with holiday detection.
    
    Features:
    - NSE trading holidays for 2025
    - Weekend detection
    - Market hours validation
    """
    
    # NSE Holidays for 2025 (updated annually)
    NSE_HOLIDAYS_2025 = {
        date(2025, 1, 26): "Republic Day",
        date(2025, 3, 14): "Mahashivratri",
        date(2025, 3, 31): "Id-Ul-Fitr (Ramadan Eid)",
        date(2025, 4, 10): "Mahavir Jayanti",
        date(2025, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
        date(2025, 4, 18): "Good Friday",
        date(2025, 5, 1): "Maharashtra Day",
        date(2025, 6, 7): "Bakri Id",
        date(2025, 8, 15): "Independence Day",
        date(2025, 8, 27): "Ganesh Chaturthi",
        date(2025, 10, 2): "Mahatma Gandhi Jayanti",
        date(2025, 10, 21): "Dussehra",
        date(2025, 10, 22): "Diwali-Laxmi Pujan",
        date(2025, 10, 23): "Diwali-Balipratipada",
        date(2025, 11, 5): "Guru Nanak Jayanti",
        date(2025, 12, 25): "Christmas",
    }
    
    def __init__(self):
        """Initialize market calendar."""
        self.logger = logging.getLogger(__name__)
        self.holidays = self.NSE_HOLIDAYS_2025.copy()
    
    def is_trading_day(self, check_date: date = None) -> bool:
        """
        Check if given date is a trading day.
        
        Args:
            check_date: Date to check (defaults to today)
        
        Returns:
            True if trading day, False if weekend or holiday
        """
        if check_date is None:
            check_date = date.today()
        
        # Check if weekend (Saturday=5, Sunday=6)
        if check_date.weekday() >= 5:
            return False
        
        # Check if holiday
        if check_date in self.holidays:
            return False
        
        return True
    
    def is_holiday(self, check_date: date = None) -> bool:
        """
        Check if given date is a market holiday.
        
        Args:
            check_date: Date to check (defaults to today)
        
        Returns:
            True if holiday, False otherwise
        """
        if check_date is None:
            check_date = date.today()
        
        return check_date in self.holidays
    
    def get_holiday_name(self, check_date: date = None) -> str:
        """
        Get holiday name for given date.
        
        Args:
            check_date: Date to check (defaults to today)
        
        Returns:
            Holiday name or None if not a holiday
        """
        if check_date is None:
            check_date = date.today()
        
        return self.holidays.get(check_date)
    
    def next_trading_day(self, from_date: date = None) -> date:
        """
        Get next trading day after given date.
        
        Args:
            from_date: Starting date (defaults to today)
        
        Returns:
            Next trading day
        """
        if from_date is None:
            from_date = date.today()
        
        check_date = from_date
        max_iterations = 30  # Prevent infinite loop
        
        for _ in range(max_iterations):
            check_date = date.fromordinal(check_date.toordinal() + 1)
            if self.is_trading_day(check_date):
                return check_date
        
        # Fallback (should never reach here)
        return check_date
    
    def get_market_status(self) -> dict:
        """
        Get current market status.
        
        Returns:
            Dict with market status information
        """
        now = datetime.now()
        today = now.date()
        
        is_trading_day = self.is_trading_day(today)
        is_weekend = today.weekday() >= 5
        is_holiday = self.is_holiday(today)
        
        # Market hours (IST): 9:15 AM - 3:30 PM
        current_time = now.hour * 60 + now.minute
        market_open_time = 9 * 60 + 15  # 9:15 AM
        market_close_time = 15 * 60 + 30  # 3:30 PM
        
        is_market_hours = market_open_time <= current_time <= market_close_time
        
        status = {
            'is_trading_day': is_trading_day,
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'holiday_name': self.get_holiday_name(today),
            'is_market_hours': is_market_hours and is_trading_day,
            'current_time': now.strftime('%Y-%m-%d %H:%M:%S'),
            'next_trading_day': self.next_trading_day(today).isoformat() if not is_trading_day else None
        }
        
        return status
    
    def should_trade_now(self) -> tuple:
        """
        Check if trading should be active right now.
        
        Returns:
            (should_trade: bool, reason: str)
        """
        status = self.get_market_status()
        
        if not status['is_trading_day']:
            if status['is_weekend']:
                return False, f"Weekend - next trading day: {status['next_trading_day']}"
            elif status['is_holiday']:
                return False, f"Market holiday: {status['holiday_name']} - next trading day: {status['next_trading_day']}"
        
        if not status['is_market_hours']:
            return False, "Outside market hours (9:15 AM - 3:30 PM IST)"
        
        return True, "Market is open for trading"
    
    def add_custom_holiday(self, holiday_date: date, name: str):
        """
        Add custom holiday to calendar.
        
        Args:
            holiday_date: Date of holiday
            name: Holiday name
        """
        self.holidays[holiday_date] = name
        self.logger.info(f"Added custom holiday: {name} on {holiday_date}")
    
    def get_all_holidays(self, year: int = None) -> dict:
        """
        Get all holidays for given year.
        
        Args:
            year: Year to filter (defaults to current year)
        
        Returns:
            Dict of holidays for the year
        """
        if year is None:
            year = date.today().year
        
        return {d: name for d, name in self.holidays.items() if d.year == year}
