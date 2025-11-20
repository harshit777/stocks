"""
AI Pattern Recognition Module

Analyzes price patterns, identifies trends, and learns from historical data.
Uses machine learning to recognize candlestick patterns, support/resistance levels,
and trend formations.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import logging
from collections import deque
import json
import os


class PatternRecognizer:
    """
    AI-powered pattern recognition for technical analysis.
    Identifies candlestick patterns, trends, and support/resistance levels.
    """
    
    def __init__(self, lookback_periods: int = 100):
        """
        Initialize pattern recognizer.
        
        Args:
            lookback_periods: Number of periods to analyze for patterns
        """
        self.logger = logging.getLogger(__name__)
        self.lookback_periods = lookback_periods
        
        # Pattern database - stores successful patterns
        self.pattern_db = {
            'bullish': [],
            'bearish': [],
            'neutral': []
        }
        
        # Historical data cache
        self.price_history = {}
        
        # Pattern success rates
        self.pattern_success_rates = {}
        
        self.logger.info("Pattern Recognizer initialized")
    
    def update_price_history(self, symbol: str, candle: Dict):
        """
        Update price history for a symbol.
        
        Args:
            symbol: Trading symbol
            candle: OHLCV data dict with keys: open, high, low, close, volume
        """
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.lookback_periods)
        
        self.price_history[symbol].append({
            'timestamp': datetime.now(),
            'open': candle['open'],
            'high': candle['high'],
            'low': candle['low'],
            'close': candle['close'],
            'volume': candle.get('volume', 0)
        })
    
    def detect_candlestick_patterns(self, symbol: str) -> Dict[str, float]:
        """
        Detect candlestick patterns and their confidence scores.
        
        Returns:
            Dict with pattern names and confidence scores (0-1)
        """
        if symbol not in self.price_history or len(self.price_history[symbol]) < 3:
            return {}
        
        history = list(self.price_history[symbol])
        patterns = {}
        
        # Get last 3 candles
        prev2 = history[-3] if len(history) >= 3 else None
        prev = history[-2] if len(history) >= 2 else None
        current = history[-1]
        
        # Bullish patterns
        if prev and current:
            # Hammer (bullish reversal)
            if self._is_hammer(current):
                patterns['hammer'] = 0.7
            
            # Bullish engulfing
            if self._is_bullish_engulfing(prev, current):
                patterns['bullish_engulfing'] = 0.8
            
            # Morning star (requires 3 candles)
            if prev2 and self._is_morning_star(prev2, prev, current):
                patterns['morning_star'] = 0.85
        
        # Bearish patterns
        if prev and current:
            # Shooting star (bearish reversal)
            if self._is_shooting_star(current):
                patterns['shooting_star'] = 0.7
            
            # Bearish engulfing
            if self._is_bearish_engulfing(prev, current):
                patterns['bearish_engulfing'] = 0.8
            
            # Evening star (requires 3 candles)
            if prev2 and self._is_evening_star(prev2, prev, current):
                patterns['evening_star'] = 0.85
        
        return patterns
    
    def _is_hammer(self, candle: Dict) -> bool:
        """Check if candle is a hammer pattern."""
        body = abs(candle['close'] - candle['open'])
        lower_shadow = min(candle['open'], candle['close']) - candle['low']
        upper_shadow = candle['high'] - max(candle['open'], candle['close'])
        
        # Hammer: small body, long lower shadow, small upper shadow
        return (lower_shadow > 2 * body and 
                upper_shadow < body * 0.3 and
                body > 0)
    
    def _is_shooting_star(self, candle: Dict) -> bool:
        """Check if candle is a shooting star pattern."""
        body = abs(candle['close'] - candle['open'])
        lower_shadow = min(candle['open'], candle['close']) - candle['low']
        upper_shadow = candle['high'] - max(candle['open'], candle['close'])
        
        # Shooting star: small body, long upper shadow, small lower shadow
        return (upper_shadow > 2 * body and 
                lower_shadow < body * 0.3 and
                body > 0)
    
    def _is_bullish_engulfing(self, prev: Dict, current: Dict) -> bool:
        """Check if pattern is bullish engulfing."""
        prev_bearish = prev['close'] < prev['open']
        current_bullish = current['close'] > current['open']
        
        # Current candle engulfs previous bearish candle
        return (prev_bearish and current_bullish and
                current['open'] < prev['close'] and
                current['close'] > prev['open'])
    
    def _is_bearish_engulfing(self, prev: Dict, current: Dict) -> bool:
        """Check if pattern is bearish engulfing."""
        prev_bullish = prev['close'] > prev['open']
        current_bearish = current['close'] < current['open']
        
        # Current candle engulfs previous bullish candle
        return (prev_bullish and current_bearish and
                current['open'] > prev['close'] and
                current['close'] < prev['open'])
    
    def _is_morning_star(self, first: Dict, second: Dict, third: Dict) -> bool:
        """Check if pattern is morning star (bullish reversal)."""
        first_bearish = first['close'] < first['open']
        second_small = abs(second['close'] - second['open']) < abs(first['close'] - first['open']) * 0.3
        third_bullish = third['close'] > third['open']
        
        return (first_bearish and second_small and third_bullish and
                third['close'] > (first['open'] + first['close']) / 2)
    
    def _is_evening_star(self, first: Dict, second: Dict, third: Dict) -> bool:
        """Check if pattern is evening star (bearish reversal)."""
        first_bullish = first['close'] > first['open']
        second_small = abs(second['close'] - second['open']) < abs(first['close'] - first['open']) * 0.3
        third_bearish = third['close'] < third['open']
        
        return (first_bullish and second_small and third_bearish and
                third['close'] < (first['open'] + first['close']) / 2)
    
    def identify_support_resistance(self, symbol: str) -> Dict[str, List[float]]:
        """
        Identify support and resistance levels using price clusters.
        
        Returns:
            Dict with 'support' and 'resistance' lists of price levels
        """
        if symbol not in self.price_history or len(self.price_history[symbol]) < 20:
            return {'support': [], 'resistance': []}
        
        history = list(self.price_history[symbol])
        
        # Extract highs and lows
        highs = [candle['high'] for candle in history]
        lows = [candle['low'] for candle in history]
        
        # Find resistance levels (price peaks)
        resistance = self._find_price_levels(highs, is_resistance=True)
        
        # Find support levels (price troughs)
        support = self._find_price_levels(lows, is_resistance=False)
        
        return {
            'support': sorted(support),
            'resistance': sorted(resistance, reverse=True)
        }
    
    def _find_price_levels(self, prices: List[float], is_resistance: bool) -> List[float]:
        """Find significant price levels using local maxima/minima."""
        if len(prices) < 10:
            return []
        
        levels = []
        window = 5
        
        for i in range(window, len(prices) - window):
            if is_resistance:
                # Find local maxima
                if prices[i] == max(prices[i-window:i+window+1]):
                    levels.append(prices[i])
            else:
                # Find local minima
                if prices[i] == min(prices[i-window:i+window+1]):
                    levels.append(prices[i])
        
        # Cluster nearby levels
        if not levels:
            return []
        
        clustered = []
        current_cluster = [levels[0]]
        threshold = np.mean(prices) * 0.005  # 0.5% clustering threshold
        
        for level in levels[1:]:
            if abs(level - np.mean(current_cluster)) < threshold:
                current_cluster.append(level)
            else:
                clustered.append(np.mean(current_cluster))
                current_cluster = [level]
        
        if current_cluster:
            clustered.append(np.mean(current_cluster))
        
        return clustered[:5]  # Return top 5 levels
    
    def detect_trend(self, symbol: str) -> Dict[str, any]:
        """
        Detect current trend using moving averages and price action.
        
        Returns:
            Dict with trend direction, strength, and confidence
        """
        if symbol not in self.price_history or len(self.price_history[symbol]) < 20:
            return {'direction': 'neutral', 'strength': 0, 'confidence': 0}
        
        history = list(self.price_history[symbol])
        closes = [candle['close'] for candle in history]
        
        # Calculate moving averages
        ma_short = np.mean(closes[-10:])  # 10-period MA
        ma_medium = np.mean(closes[-20:])  # 20-period MA
        ma_long = np.mean(closes[-50:]) if len(closes) >= 50 else ma_medium
        
        current_price = closes[-1]
        
        # Determine trend direction
        if ma_short > ma_medium > ma_long and current_price > ma_short:
            direction = 'uptrend'
            strength = min((ma_short - ma_long) / ma_long * 100, 10) / 10  # 0-1 scale
        elif ma_short < ma_medium < ma_long and current_price < ma_short:
            direction = 'downtrend'
            strength = min((ma_long - ma_short) / ma_long * 100, 10) / 10
        else:
            direction = 'neutral'
            strength = 0
        
        # Calculate trend confidence based on consistency
        price_changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        if direction == 'uptrend':
            positive_moves = sum(1 for change in price_changes[-20:] if change > 0)
            confidence = positive_moves / 20
        elif direction == 'downtrend':
            negative_moves = sum(1 for change in price_changes[-20:] if change < 0)
            confidence = negative_moves / 20
        else:
            confidence = 0.5
        
        return {
            'direction': direction,
            'strength': strength,
            'confidence': confidence,
            'ma_short': ma_short,
            'ma_medium': ma_medium,
            'ma_long': ma_long
        }
    
    def calculate_volatility(self, symbol: str) -> float:
        """
        Calculate historical volatility.
        
        Returns:
            Volatility as standard deviation of returns
        """
        if symbol not in self.price_history or len(self.price_history[symbol]) < 20:
            return 0.0
        
        history = list(self.price_history[symbol])
        closes = [candle['close'] for candle in history]
        
        # Calculate returns
        returns = [(closes[i] - closes[i-1]) / closes[i-1] 
                   for i in range(1, len(closes))]
        
        # Return standard deviation (volatility)
        return float(np.std(returns))
    
    def learn_from_pattern(self, pattern_type: str, success: bool):
        """
        Update pattern success rates based on trade outcomes.
        
        Args:
            pattern_type: Name of the pattern
            success: Whether the trade was successful
        """
        if pattern_type not in self.pattern_success_rates:
            self.pattern_success_rates[pattern_type] = {
                'successes': 0,
                'failures': 0,
                'rate': 0.5
            }
        
        if success:
            self.pattern_success_rates[pattern_type]['successes'] += 1
        else:
            self.pattern_success_rates[pattern_type]['failures'] += 1
        
        total = (self.pattern_success_rates[pattern_type]['successes'] + 
                self.pattern_success_rates[pattern_type]['failures'])
        
        self.pattern_success_rates[pattern_type]['rate'] = (
            self.pattern_success_rates[pattern_type]['successes'] / total
        )
        
        self.logger.info(
            f"Pattern {pattern_type} success rate updated: "
            f"{self.pattern_success_rates[pattern_type]['rate']:.2%}"
        )
    
    def get_pattern_confidence(self, pattern_type: str) -> float:
        """
        Get learned confidence for a pattern type.
        
        Returns:
            Confidence score (0-1) based on historical success
        """
        if pattern_type in self.pattern_success_rates:
            return self.pattern_success_rates[pattern_type]['rate']
        return 0.5  # Default 50% confidence for unknown patterns
    
    def save_patterns(self, filepath: str):
        """Save learned patterns to file."""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.pattern_success_rates, f, indent=2)
            self.logger.info(f"Patterns saved to {filepath}")
        except Exception as e:
            self.logger.error(f"Error saving patterns: {e}")
    
    def load_patterns(self, filepath: str):
        """Load learned patterns from file."""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    self.pattern_success_rates = json.load(f)
                self.logger.info(f"Patterns loaded from {filepath}")
        except Exception as e:
            self.logger.error(f"Error loading patterns: {e}")
