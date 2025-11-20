"""
AI Sentiment Analysis Module

Analyzes news, social media, and market sentiment using NLP.
Provides sentiment scores that influence trading decisions.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import deque
import re
import json
import os


class SentimentAnalyzer:
    """
    Analyzes market sentiment from news and social media.
    Uses NLP and keyword analysis to gauge market mood.
    """
    
    def __init__(self):
        """Initialize sentiment analyzer."""
        self.logger = logging.getLogger(__name__)
        
        # Sentiment keywords (positive and negative)
        self.positive_keywords = {
            'bullish', 'rally', 'surge', 'gain', 'profit', 'growth', 'strong',
            'buy', 'upgrade', 'positive', 'beat', 'outperform', 'boom',
            'recovery', 'optimistic', 'breakout', 'soar', 'jump', 'climb'
        }
        
        self.negative_keywords = {
            'bearish', 'decline', 'loss', 'weak', 'sell', 'downgrade', 'negative',
            'miss', 'underperform', 'crash', 'recession', 'pessimistic',
            'plunge', 'drop', 'fall', 'tumble', 'slump', 'fear', 'concern'
        }
        
        # Sentiment history for each symbol
        self.sentiment_history = {}
        
        # Sentiment scores cache
        self.sentiment_cache = {}
        
        self.logger.info("Sentiment Analyzer initialized")
    
    def analyze_text(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment from text using keyword matching.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dict with sentiment score and confidence
        """
        if not text:
            return {'score': 0.0, 'confidence': 0.0}
        
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        
        # Count positive and negative keywords
        positive_count = sum(1 for word in words if word in self.positive_keywords)
        negative_count = sum(1 for word in words if word in self.negative_keywords)
        
        total_sentiment_words = positive_count + negative_count
        
        if total_sentiment_words == 0:
            return {'score': 0.0, 'confidence': 0.0}
        
        # Calculate sentiment score (-1 to 1)
        sentiment_score = (positive_count - negative_count) / total_sentiment_words
        
        # Confidence based on number of sentiment words found
        confidence = min(total_sentiment_words / 10, 1.0)  # Max confidence at 10+ keywords
        
        return {
            'score': sentiment_score,
            'confidence': confidence,
            'positive_words': positive_count,
            'negative_words': negative_count
        }
    
    def get_market_sentiment(self, symbol: str) -> Dict[str, float]:
        """
        Get overall market sentiment for a symbol.
        
        In production, this would fetch from:
        - News APIs (NewsAPI, Bloomberg, etc.)
        - Twitter/Social media APIs
        - Financial news sources
        
        For now, returns simulated sentiment based on price action.
        
        Returns:
            Dict with sentiment score and confidence
        """
        # In production, you would integrate with:
        # - NewsAPI: https://newsapi.org/
        # - Twitter API for stock mentions
        # - Reddit WSB sentiment
        # - Financial news aggregators
        
        # For now, return neutral sentiment with note to integrate real APIs
        return {
            'score': 0.0,  # -1 (bearish) to 1 (bullish)
            'confidence': 0.5,
            'source': 'simulated',
            'timestamp': datetime.now()
        }
    
    def update_sentiment(self, symbol: str, price_change: float, volume_change: float = 0.0):
        """
        Update sentiment based on price and volume action.
        
        This provides a basic sentiment signal based on market behavior.
        
        Args:
            symbol: Trading symbol
            price_change: Percentage price change
            volume_change: Percentage volume change (default: 0.0 if not available)
        """
        if symbol not in self.sentiment_history:
            self.sentiment_history[symbol] = deque(maxlen=20)
        
        # Only process significant price changes to reduce noise
        # Ignore very small moves (< 0.1% for intraday)
        if abs(price_change) < 0.1:
            return
        
        # Calculate sentiment from price action
        # Strong price move with high volume = strong sentiment
        price_sentiment = max(min(price_change / 2, 1.0), -1.0)  # Normalize to -1 to 1
        
        # Volume factor - only apply if volume data is available and meaningful
        if volume_change > 0:
            volume_factor = min(volume_change / 50, 2.0)  # Volume amplifier
        else:
            volume_factor = 0.0  # No volume amplification if data not available
        
        combined_sentiment = price_sentiment * (1 + volume_factor * 0.5)
        combined_sentiment = max(min(combined_sentiment, 1.0), -1.0)
        
        self.sentiment_history[symbol].append({
            'timestamp': datetime.now(),
            'score': combined_sentiment,
            'price_change': price_change,
            'volume_change': volume_change
        })
        
        # Update cache
        self.sentiment_cache[symbol] = {
            'current': combined_sentiment,
            'average': self._calculate_average_sentiment(symbol),
            'trend': self._calculate_sentiment_trend(symbol)
        }
    
    def _calculate_average_sentiment(self, symbol: str) -> float:
        """
        Calculate average sentiment over recent history with exponential decay.
        Recent sentiment matters more than older sentiment.
        """
        if symbol not in self.sentiment_history or not self.sentiment_history[symbol]:
            return 0.0
        
        scores = [entry['score'] for entry in self.sentiment_history[symbol]]
        
        # Apply exponential weighting - recent data matters more
        # weights: [0.5^(n-1), 0.5^(n-2), ..., 0.5^1, 0.5^0]
        # Most recent gets weight 1.0, previous 0.5, etc.
        weights = [0.5 ** i for i in range(len(scores) - 1, -1, -1)]
        
        if sum(weights) == 0:
            return 0.0
        
        weighted_avg = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        return weighted_avg
    
    def _calculate_sentiment_trend(self, symbol: str) -> str:
        """Determine if sentiment is improving, declining, or stable."""
        if symbol not in self.sentiment_history or len(self.sentiment_history[symbol]) < 10:
            return 'neutral'
        
        recent_scores = [entry['score'] for entry in list(self.sentiment_history[symbol])[-10:]]
        older_scores = [entry['score'] for entry in list(self.sentiment_history[symbol])[-20:-10]]
        
        recent_avg = sum(recent_scores) / len(recent_scores)
        older_avg = sum(older_scores) / len(older_scores) if older_scores else 0
        
        diff = recent_avg - older_avg
        
        if diff > 0.1:
            return 'improving'
        elif diff < -0.1:
            return 'declining'
        else:
            return 'stable'
    
    def get_sentiment_score(self, symbol: str) -> Dict[str, any]:
        """
        Get comprehensive sentiment score for a symbol.
        
        Returns:
            Dict with current score, average, trend, and confidence
        """
        if symbol not in self.sentiment_cache:
            return {
                'current': 0.0,
                'average': 0.0,
                'trend': 'neutral',
                'confidence': 0.0
            }
        
        cache = self.sentiment_cache[symbol]
        history_len = len(self.sentiment_history.get(symbol, []))
        confidence = min(history_len / 20, 1.0)  # Full confidence after 20 data points
        
        return {
            'current': cache['current'],
            'average': cache['average'],
            'trend': cache['trend'],
            'confidence': confidence
        }
    
    def get_sentiment_signal(self, symbol: str) -> Optional[str]:
        """
        Get trading signal based on sentiment.
        
        Returns:
            'BUY', 'SELL', or None
        """
        sentiment = self.get_sentiment_score(symbol)
        
        # Require higher minimum confidence for better quality signals
        if sentiment['confidence'] < 0.7:
            return None
        
        # Strong bullish sentiment + improving trend (increased threshold)
        if sentiment['current'] > 0.6 and sentiment['trend'] == 'improving':
            return 'BUY'
        
        # Strong bearish sentiment + declining trend (increased threshold)
        elif sentiment['current'] < -0.6 and sentiment['trend'] == 'declining':
            return 'SELL'
        
        return None
    
    def analyze_news_headlines(self, headlines: List[str], symbol: str) -> Dict[str, float]:
        """
        Analyze multiple news headlines for a symbol.
        
        Args:
            headlines: List of news headlines
            symbol: Trading symbol
            
        Returns:
            Aggregated sentiment analysis
        """
        if not headlines:
            return {'score': 0.0, 'confidence': 0.0}
        
        sentiments = []
        for headline in headlines:
            sentiment = self.analyze_text(headline)
            if sentiment['confidence'] > 0.1:  # Only consider meaningful results
                sentiments.append(sentiment)
        
        if not sentiments:
            return {'score': 0.0, 'confidence': 0.0}
        
        # Calculate weighted average
        total_weight = sum(s['confidence'] for s in sentiments)
        weighted_score = sum(s['score'] * s['confidence'] for s in sentiments) / total_weight
        
        # Average confidence
        avg_confidence = sum(s['confidence'] for s in sentiments) / len(sentiments)
        
        return {
            'score': weighted_score,
            'confidence': avg_confidence,
            'headlines_analyzed': len(sentiments)
        }
    
    def get_fear_greed_index(self, symbol: str) -> float:
        """
        Calculate a simplified fear/greed index (0-100).
        
        0 = Extreme Fear (oversold, good buying opportunity)
        50 = Neutral
        100 = Extreme Greed (overbought, consider selling)
        
        Returns:
            Fear/greed score (0-100)
        """
        sentiment = self.get_sentiment_score(symbol)
        
        # Convert sentiment score (-1 to 1) to fear/greed (0 to 100)
        # -1 (bearish) = 0 (extreme fear)
        # 0 (neutral) = 50
        # 1 (bullish) = 100 (extreme greed)
        
        fear_greed = (sentiment['average'] + 1) * 50
        return max(0, min(100, fear_greed))
    
    def should_trade_based_on_sentiment(self, symbol: str, signal: str) -> bool:
        """
        Determine if sentiment supports the trading signal.
        
        Args:
            symbol: Trading symbol
            signal: Proposed trading signal ('BUY' or 'SELL')
            
        Returns:
            True if sentiment supports the trade
        """
        sentiment = self.get_sentiment_score(symbol)
        
        # Require minimum confidence
        if sentiment['confidence'] < 0.3:
            return True  # Don't block trades if no sentiment data
        
        if signal == 'BUY':
            # Support buy if sentiment is neutral to positive
            return sentiment['current'] > -0.3
        
        elif signal == 'SELL':
            # Support sell if sentiment is neutral to negative
            # Or if sentiment is declining (take profits)
            return sentiment['current'] < 0.3 or sentiment['trend'] == 'declining'
        
        return True
    
    def get_sentiment_adjustment(self, symbol: str) -> float:
        """
        Get sentiment adjustment factor for position sizing.
        
        Returns:
            Multiplier (0.5 to 1.5) to adjust position size based on sentiment
        """
        sentiment = self.get_sentiment_score(symbol)
        
        if sentiment['confidence'] < 0.3:
            return 1.0  # No adjustment if low confidence
        
        # Strong positive sentiment + improving = increase position (up to 1.5x)
        if sentiment['current'] > 0.5 and sentiment['trend'] == 'improving':
            return 1.0 + (sentiment['current'] * 0.5)
        
        # Strong negative sentiment = decrease position (down to 0.5x)
        elif sentiment['current'] < -0.3:
            return max(0.5, 1.0 + sentiment['current'])
        
        return 1.0
    
    def save_sentiment_data(self, filepath: str):
        """Save sentiment history to file."""
        try:
            data = {
                symbol: list(history)
                for symbol, history in self.sentiment_history.items()
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            self.logger.info(f"Sentiment data saved to {filepath}")
        except Exception as e:
            self.logger.error(f"Error saving sentiment data: {e}")
    
    def load_sentiment_data(self, filepath: str):
        """Load sentiment history from file."""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                for symbol, history in data.items():
                    self.sentiment_history[symbol] = deque(history, maxlen=20)
                self.logger.info(f"Sentiment data loaded from {filepath}")
        except Exception as e:
            self.logger.error(f"Error loading sentiment data: {e}")
