"""
AI Predictive Model

Multi-timeframe analysis and machine learning for price prediction.
Analyzes 5-minute, 30-minute, 4-hour, and daily timeframes to generate
unified trading signals.
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import logging
import json
import os


class PredictiveModel:
    """
    ML-based predictive model for price forecasting.
    Combines multiple timeframes for coherent trading signals.
    """
    
    def __init__(self):
        """Initialize predictive model."""
        self.logger = logging.getLogger(__name__)
        
        # Multi-timeframe data storage
        self.timeframe_data = {
            '5m': {},    # 5-minute candles
            '30m': {},   # 30-minute candles
            '4h': {},    # 4-hour candles
            'daily': {}  # Daily candles
        }
        
        # Model parameters (learned from historical data)
        self.model_params = {}
        
        # Prediction history
        self.predictions = {}
        
        # Prediction accuracy tracking
        self.accuracy_stats = {
            'correct_predictions': 0,
            'total_predictions': 0,
            'accuracy_rate': 0.0
        }
        
        self.logger.info("Predictive Model initialized")
    
    def update_timeframe_data(self, symbol: str, timeframe: str, candle: Dict):
        """
        Update data for a specific timeframe.
        
        Args:
            symbol: Trading symbol
            timeframe: '5m', '30m', '4h', or 'daily'
            candle: OHLCV data
        """
        if timeframe not in self.timeframe_data:
            self.logger.warning(f"Invalid timeframe: {timeframe}")
            return
        
        if symbol not in self.timeframe_data[timeframe]:
            # Store different amounts based on timeframe
            maxlen = {'5m': 200, '30m': 100, '4h': 50, 'daily': 100}[timeframe]
            self.timeframe_data[timeframe][symbol] = deque(maxlen=maxlen)
        
        self.timeframe_data[timeframe][symbol].append({
            'timestamp': datetime.now(),
            'open': candle['open'],
            'high': candle['high'],
            'low': candle['low'],
            'close': candle['close'],
            'volume': candle.get('volume', 0)
        })
    
    def predict_price_movement(self, symbol: str) -> Dict[str, any]:
        """
        Predict next price movement using multi-timeframe analysis.
        
        Returns:
            Dict with direction, confidence, and target price
        """
        if not self._has_sufficient_data(symbol):
            return {'direction': 'neutral', 'confidence': 0.0, 'target': None}
        
        # Analyze each timeframe
        tf_signals = {}
        for timeframe in ['5m', '30m', '4h', 'daily']:
            tf_signals[timeframe] = self._analyze_timeframe(symbol, timeframe)
        
        # Combine signals with weights
        combined_signal = self._combine_timeframe_signals(tf_signals)
        
        # Calculate target price
        current_price = self._get_current_price(symbol)
        target_price = self._calculate_target_price(symbol, combined_signal, current_price)
        
        # Store prediction
        self._store_prediction(symbol, combined_signal, target_price)
        
        return {
            'direction': combined_signal['direction'],
            'confidence': combined_signal['confidence'],
            'target': target_price,
            'timeframe_signals': tf_signals
        }
    
    def _has_sufficient_data(self, symbol: str) -> bool:
        """Check if we have enough data for prediction."""
        for timeframe in ['5m', '30m']:  # At minimum need short timeframes
            if (symbol not in self.timeframe_data[timeframe] or
                len(self.timeframe_data[timeframe][symbol]) < 20):
                return False
        return True
    
    def _analyze_timeframe(self, symbol: str, timeframe: str) -> Dict[str, any]:
        """
        Analyze a single timeframe.
        
        Returns:
            Signal dict with direction, strength, and indicators
        """
        if (symbol not in self.timeframe_data[timeframe] or 
            len(self.timeframe_data[timeframe][symbol]) < 10):
            return {'direction': 'neutral', 'strength': 0, 'confidence': 0}
        
        data = list(self.timeframe_data[timeframe][symbol])
        closes = [candle['close'] for candle in data]
        highs = [candle['high'] for candle in data]
        lows = [candle['low'] for candle in data]
        volumes = [candle['volume'] for candle in data]
        
        # Calculate technical indicators
        rsi = self._calculate_rsi(closes)
        macd = self._calculate_macd(closes)
        ma_signal = self._calculate_ma_crossover(closes)
        volume_signal = self._analyze_volume(volumes)
        
        # Combine indicators
        signals = [rsi, macd, ma_signal, volume_signal]
        avg_signal = sum(signals) / len(signals)
        
        # Determine direction
        if avg_signal > 0.3:
            direction = 'up'
            strength = min(avg_signal, 1.0)
        elif avg_signal < -0.3:
            direction = 'down'
            strength = min(abs(avg_signal), 1.0)
        else:
            direction = 'neutral'
            strength = 0
        
        # Confidence based on signal alignment
        signal_alignment = 1.0 - (np.std(signals) / 2.0) if len(signals) > 1 else 0.5
        
        return {
            'direction': direction,
            'strength': strength,
            'confidence': signal_alignment,
            'indicators': {'rsi': rsi, 'macd': macd, 'ma': ma_signal, 'volume': volume_signal}
        }
    
    def _calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        """
        Calculate RSI indicator.
        Returns signal: -1 (oversold/bullish) to 1 (overbought/bearish)
        """
        if len(closes) < period + 1:
            return 0.0
        
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [max(change, 0) for change in changes[-period:]]
        losses = [abs(min(change, 0)) for change in changes[-period:]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 1.0  # Overbought
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        # Convert to signal (-1 to 1)
        if rsi > 70:
            return (rsi - 70) / 30  # Overbought (bearish): 0 to 1
        elif rsi < 30:
            return -(30 - rsi) / 30  # Oversold (bullish): -1 to 0
        else:
            return 0.0
    
    def _calculate_macd(self, closes: List[float]) -> float:
        """
        Calculate MACD indicator.
        Returns signal: -1 (bearish) to 1 (bullish)
        """
        if len(closes) < 26:
            return 0.0
        
        # Calculate EMAs
        ema_12 = self._ema(closes, 12)
        ema_26 = self._ema(closes, 26)
        
        macd_line = ema_12 - ema_26
        
        # Normalize to -1 to 1
        avg_price = np.mean(closes[-26:])
        normalized_macd = macd_line / (avg_price * 0.02)  # 2% scale
        
        return max(min(normalized_macd, 1.0), -1.0)
    
    def _ema(self, values: List[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(values) < period:
            return sum(values) / len(values)
        
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period
        
        for value in values[period:]:
            ema = (value * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def _calculate_ma_crossover(self, closes: List[float]) -> float:
        """
        Calculate moving average crossover signal.
        Returns: -1 (bearish cross) to 1 (bullish cross)
        """
        if len(closes) < 20:
            return 0.0
        
        ma_short = np.mean(closes[-5:])   # 5-period MA
        ma_long = np.mean(closes[-20:])   # 20-period MA
        
        # Calculate signal strength
        diff = (ma_short - ma_long) / ma_long
        signal = diff * 50  # Amplify
        
        return max(min(signal, 1.0), -1.0)
    
    def _analyze_volume(self, volumes: List[float]) -> float:
        """
        Analyze volume for confirmation.
        Returns: -1 to 1 based on volume trend
        """
        if len(volumes) < 10:
            return 0.0
        
        recent_vol = np.mean(volumes[-5:])
        avg_vol = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
        
        if avg_vol == 0:
            return 0.0
        
        vol_ratio = (recent_vol - avg_vol) / avg_vol
        
        # High volume = strong signal
        return max(min(vol_ratio, 1.0), -1.0)
    
    def _combine_timeframe_signals(self, tf_signals: Dict[str, Dict]) -> Dict[str, any]:
        """
        Combine signals from multiple timeframes with intelligent weighting.
        
        Longer timeframes get higher weight as they're more reliable.
        """
        # Weights for each timeframe
        weights = {
            '5m': 0.15,
            '30m': 0.25,
            '4h': 0.30,
            'daily': 0.30
        }
        
        # Convert directions to numeric
        direction_map = {'up': 1, 'down': -1, 'neutral': 0}
        
        weighted_signal = 0
        total_weight = 0
        confidences = []
        
        for timeframe, signal in tf_signals.items():
            if signal['confidence'] > 0.1:  # Only consider meaningful signals
                weight = weights.get(timeframe, 0) * signal['confidence']
                direction_value = direction_map.get(signal['direction'], 0)
                weighted_signal += direction_value * signal['strength'] * weight
                total_weight += weight
                confidences.append(signal['confidence'])
        
        if total_weight == 0:
            return {'direction': 'neutral', 'confidence': 0, 'strength': 0}
        
        # Normalize
        final_signal = weighted_signal / total_weight
        avg_confidence = np.mean(confidences) if confidences else 0
        
        # Determine direction
        if final_signal > 0.2:
            direction = 'up'
        elif final_signal < -0.2:
            direction = 'down'
        else:
            direction = 'neutral'
        
        return {
            'direction': direction,
            'confidence': avg_confidence,
            'strength': abs(final_signal)
        }
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price from most recent data."""
        for timeframe in ['5m', '30m', '4h', 'daily']:
            if symbol in self.timeframe_data[timeframe] and self.timeframe_data[timeframe][symbol]:
                return list(self.timeframe_data[timeframe][symbol])[-1]['close']
        return None
    
    def _calculate_target_price(self, symbol: str, signal: Dict, current_price: float) -> Optional[float]:
        """Calculate target price based on prediction."""
        if not current_price or signal['direction'] == 'neutral':
            return None
        
        # Calculate target based on volatility and signal strength
        volatility = self._calculate_volatility(symbol)
        price_move_pct = volatility * signal['strength'] * 2  # 2x volatility move
        
        if signal['direction'] == 'up':
            target = current_price * (1 + price_move_pct)
        else:
            target = current_price * (1 - price_move_pct)
        
        return target
    
    def _calculate_volatility(self, symbol: str) -> float:
        """Calculate price volatility."""
        if symbol not in self.timeframe_data['30m'] or len(self.timeframe_data['30m'][symbol]) < 20:
            return 0.01  # Default 1%
        
        closes = [candle['close'] for candle in list(self.timeframe_data['30m'][symbol])]
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        
        return float(np.std(returns))
    
    def _store_prediction(self, symbol: str, signal: Dict, target: float):
        """Store prediction for later validation."""
        if symbol not in self.predictions:
            self.predictions[symbol] = deque(maxlen=100)
        
        self.predictions[symbol].append({
            'timestamp': datetime.now(),
            'direction': signal['direction'],
            'confidence': signal['confidence'],
            'target': target,
            'current_price': self._get_current_price(symbol)
        })
    
    def validate_predictions(self, symbol: str):
        """
        Validate previous predictions and update accuracy stats.
        Called periodically to improve model.
        """
        if symbol not in self.predictions:
            return
        
        current_price = self._get_current_price(symbol)
        if not current_price:
            return
        
        for pred in list(self.predictions[symbol]):
            # Skip if too recent (need time to play out)
            if (datetime.now() - pred['timestamp']).seconds < 3600:  # 1 hour
                continue
            
            # Check if prediction was correct
            if pred['direction'] == 'up' and current_price > pred['current_price']:
                self.accuracy_stats['correct_predictions'] += 1
            elif pred['direction'] == 'down' and current_price < pred['current_price']:
                self.accuracy_stats['correct_predictions'] += 1
            
            self.accuracy_stats['total_predictions'] += 1
        
        # Update accuracy rate
        if self.accuracy_stats['total_predictions'] > 0:
            self.accuracy_stats['accuracy_rate'] = (
                self.accuracy_stats['correct_predictions'] / 
                self.accuracy_stats['total_predictions']
            )
    
    def get_prediction_accuracy(self) -> float:
        """Get current prediction accuracy rate."""
        return self.accuracy_stats['accuracy_rate']
    
    def get_ai_signal(self, symbol: str) -> Optional[str]:
        """
        Get AI-generated trading signal.
        
        Returns:
            'BUY', 'SELL', or None
        """
        prediction = self.predict_price_movement(symbol)
        
        # Require high confidence for signal
        if prediction['confidence'] < 0.6:
            return None
        
        if prediction['direction'] == 'up':
            return 'BUY'
        elif prediction['direction'] == 'down':
            return 'SELL'
        
        return None
    
    def learn_from_trade(self, symbol: str, success: bool):
        """
        Update model based on trade outcome.
        
        Args:
            symbol: Trading symbol
            success: Whether trade was profitable
        """
        # In a full ML implementation, this would adjust model weights
        # For now, we track success rates
        if symbol not in self.model_params:
            self.model_params[symbol] = {'success_rate': 0.5, 'trades': 0}
        
        params = self.model_params[symbol]
        params['trades'] += 1
        
        # Update success rate with exponential moving average
        alpha = 0.1  # Learning rate
        if success:
            params['success_rate'] = params['success_rate'] * (1 - alpha) + alpha * 1.0
        else:
            params['success_rate'] = params['success_rate'] * (1 - alpha) + alpha * 0.0
        
        # Ensure success rate stays within reasonable bounds (10% - 90%)
        params['success_rate'] = max(0.1, min(0.9, params['success_rate']))
        
        self.logger.info(f"Model updated for {symbol}: {params['success_rate']:.2%} success rate (trades: {params['trades']})")
    
    def get_confidence_adjustment(self, symbol: str) -> float:
        """
        Get confidence adjustment based on model performance.
        
        Returns:
            Multiplier (0.5 to 1.5) for signals
        """
        if symbol not in self.model_params:
            return 1.0
        
        success_rate = self.model_params[symbol]['success_rate']
        
        # Adjust confidence based on past performance
        if success_rate > 0.6:
            return 1.0 + (success_rate - 0.5)  # Up to 1.5x
        elif success_rate < 0.4:
            return 0.5 + success_rate  # Down to 0.5x
        
        return 1.0
    
    def save_model(self, filepath: str):
        """Save model parameters and predictions."""
        try:
            data = {
                'model_params': self.model_params,
                'accuracy_stats': self.accuracy_stats
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            self.logger.info(f"Model saved to {filepath}")
        except Exception as e:
            self.logger.error(f"Error saving model: {e}")
    
    def load_model(self, filepath: str):
        """Load model parameters and predictions."""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                self.model_params = data.get('model_params', {})
                self.accuracy_stats = data.get('accuracy_stats', self.accuracy_stats)
                self.logger.info(f"Model loaded from {filepath}")
        except Exception as e:
            self.logger.error(f"Error loading model: {e}")
