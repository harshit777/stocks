"""
Configuration management for the trading bot.
"""
import os
from typing import Any, Optional


class Config:
    """Configuration class to manage environment variables and settings."""
    
    # Kite API Settings
    KITE_API_KEY: str = os.getenv('KITE_API_KEY', '')
    KITE_API_SECRET: str = os.getenv('KITE_API_SECRET', '')
    KITE_ACCESS_TOKEN: str = os.getenv('KITE_ACCESS_TOKEN', '')
    
    # Trading Settings
    MAX_POSITION_SIZE_PCT: float = float(os.getenv('MAX_POSITION_SIZE_PCT', '0.1'))
    ENABLE_PAPER_TRADING: bool = os.getenv('ENABLE_PAPER_TRADING', 'true').lower() == 'true'
    
    # Strategy Settings
    RSI_PERIOD: int = int(os.getenv('RSI_PERIOD', '14'))
    RSI_OVERSOLD: float = float(os.getenv('RSI_OVERSOLD', '30'))
    RSI_OVERBOUGHT: float = float(os.getenv('RSI_OVERBOUGHT', '70'))
    
    MOMENTUM_THRESHOLD: float = float(os.getenv('MOMENTUM_THRESHOLD', '0.02'))
    MOMENTUM_LOOKBACK_DAYS: int = int(os.getenv('MOMENTUM_LOOKBACK_DAYS', '5'))
    
    # Logging
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def load_from_file(cls, filepath: str):
        """
        Load configuration from a .env file.
        
        Args:
            filepath: Path to the .env file
        """
        if not os.path.exists(filepath):
            return
        
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate that required configuration is present.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        if not cls.KITE_API_KEY:
            print("Error: KITE_API_KEY is not set")
            return False
        
        if not cls.KITE_API_SECRET:
            print("Warning: KITE_API_SECRET is not set (required for authentication)")
        
        return True
    
    @classmethod
    def print_config(cls):
        """Print current configuration (hiding sensitive data)."""
        print("=== Current Configuration ===")
        print(f"KITE_API_KEY: {'*' * 10 if cls.KITE_API_KEY else 'Not set'}")
        print(f"KITE_API_SECRET: {'*' * 10 if cls.KITE_API_SECRET else 'Not set'}")
        print(f"KITE_ACCESS_TOKEN: {'*' * 10 if cls.KITE_ACCESS_TOKEN else 'Not set'}")
        print(f"MAX_POSITION_SIZE_PCT: {cls.MAX_POSITION_SIZE_PCT}")
        print(f"ENABLE_PAPER_TRADING: {cls.ENABLE_PAPER_TRADING}")
        print(f"RSI_PERIOD: {cls.RSI_PERIOD}")
        print(f"RSI_OVERSOLD: {cls.RSI_OVERSOLD}")
        print(f"RSI_OVERBOUGHT: {cls.RSI_OVERBOUGHT}")
        print(f"MOMENTUM_THRESHOLD: {cls.MOMENTUM_THRESHOLD}")
        print(f"MOMENTUM_LOOKBACK_DAYS: {cls.MOMENTUM_LOOKBACK_DAYS}")
        print(f"LOG_LEVEL: {cls.LOG_LEVEL}")
