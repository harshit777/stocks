"""
AI-Enhanced Intraday Trading Strategy

Combines the high-low intraday strategy with AI capabilities:
- Pattern recognition for entry/exit signals
- Sentiment analysis for market mood
- Multi-timeframe predictive analytics
- Continuous learning from trade outcomes
- Dynamic risk management based on AI confidence
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime
import os

from .intraday_high_low_strategy import IntradayHighLowStrategy
from ..ai_modules.pattern_recognition import PatternRecognizer
from ..ai_modules.sentiment_analyzer import SentimentAnalyzer
from ..ai_modules.predictive_model import PredictiveModel
from ..ai_modules.trading_psychology import TradingPsychologyGuard


class AIIntradayStrategy(IntradayHighLowStrategy):
    """
    AI-powered intraday strategy that enhances the base strategy with:
    - Machine learning for pattern recognition
    - Sentiment analysis
    - Multi-timeframe analysis
    - Continuous learning and adaptation
    """
    
    def __init__(self,
                 trader,
                 symbols: List[str],
                 min_profit_margin: float = 0.015,
                 buy_threshold: float = 0.25,
                 sell_threshold: float = 0.75,
                 risk_reward_ratio: float = 2.5,
                 max_position_pct: float = 0.1,
                 stop_loss_pct: float = 0.02,
                 ai_confidence_threshold: float = 0.6,
                 name: str = "AIIntradayStrategy"):
        """
        Initialize AI-enhanced strategy.
        
        Args:
            ai_confidence_threshold: Minimum AI confidence to influence trades (0-1)
            ... (other params same as IntradayHighLowStrategy)
        """
        super().__init__(
            trader, symbols, min_profit_margin, buy_threshold,
            sell_threshold, risk_reward_ratio, max_position_pct,
            stop_loss_pct, name
        )
        
        # Initialize AI modules
        self.pattern_recognizer = PatternRecognizer(lookback_periods=100)
        self.sentiment_analyzer = SentimentAnalyzer()
        self.predictive_model = PredictiveModel()
        
        # Initialize psychology guard for emotional control
        self.psychology_guard = TradingPsychologyGuard(
            max_daily_trades=999,  # Effectively unlimited for paper trading
            max_consecutive_losses=3,
            cooldown_after_loss=15,
            reduce_size_after_wins=3,
            max_drawdown_pct=0.05,
            fomo_prevention_window=5
        )
        
        self.ai_confidence_threshold = ai_confidence_threshold
        
        # Track AI performance
        self.ai_trades = {
            'total': 0,
            'successful': 0,
            'failed': 0
        }
        
        # AI data directory
        self.ai_data_dir = 'ai_data'
        os.makedirs(self.ai_data_dir, exist_ok=True)
        
        # Load previously learned patterns
        self._load_ai_models()
        
        self.logger.info(f"AI-Enhanced Strategy initialized with confidence threshold={ai_confidence_threshold}")
    
    def _load_ai_models(self):
        """Load previously trained AI models."""
        pattern_file = os.path.join(self.ai_data_dir, 'patterns.json')
        sentiment_file = os.path.join(self.ai_data_dir, 'sentiment.json')
        model_file = os.path.join(self.ai_data_dir, 'model.json')
        
        self.pattern_recognizer.load_patterns(pattern_file)
        self.sentiment_analyzer.load_sentiment_data(sentiment_file)
        self.predictive_model.load_model(model_file)
    
    def _save_ai_models(self):
        """Save trained AI models."""
        pattern_file = os.path.join(self.ai_data_dir, 'patterns.json')
        sentiment_file = os.path.join(self.ai_data_dir, 'sentiment.json')
        model_file = os.path.join(self.ai_data_dir, 'model.json')
        
        self.pattern_recognizer.save_patterns(pattern_file)
        self.sentiment_analyzer.save_sentiment_data(sentiment_file)
        self.predictive_model.save_model(model_file)
    
    def analyze(self, symbol: str, market_data: Dict) -> Optional[str]:
        """
        Enhanced analysis using AI modules + base strategy logic.
        
        Process:
        1. Update all AI modules with latest data
        2. Get base strategy signal
        3. Get AI predictions and sentiment
        4. Combine signals with intelligent weighting
        5. Apply emotion-free decision making
        """
        # Update intraday data (base strategy)
        self.update_intraday_data(symbol, market_data)
        
        # Update AI modules with market data
        self._update_ai_modules(symbol, market_data)
        
        # Get base strategy signal
        base_signal = super().analyze(symbol, market_data)
        
        # Get AI-enhanced signal
        ai_signal = self._get_ai_signal(symbol, market_data)
        
        # Combine signals
        final_signal = self._combine_signals(symbol, base_signal, ai_signal)
        
        if final_signal:
            self.logger.info(
                f"AI Strategy signal for {symbol}: {final_signal} "
                f"(base={base_signal}, ai={ai_signal['signal']}, "
                f"confidence={ai_signal['confidence']:.2f})"
            )
        
        return final_signal
    
    def _update_ai_modules(self, symbol: str, market_data: Dict):
        """Update all AI modules with latest market data."""
        symbol_key = f"NSE:{symbol}"
        if symbol_key not in market_data:
            return
        
        quote = market_data[symbol_key]
        ohlc = quote.get('ohlc', {})
        
        # Prepare candle data
        candle = {
            'open': ohlc.get('open', quote.get('last_price', 0)),
            'high': ohlc.get('high', quote.get('last_price', 0)),
            'low': ohlc.get('low', quote.get('last_price', 0)),
            'close': quote.get('last_price', 0),
            'volume': quote.get('volume', 0)
        }
        
        # Update pattern recognizer
        self.pattern_recognizer.update_price_history(symbol, candle)
        
        # Update predictive model (using current data as 5m timeframe)
        self.predictive_model.update_timeframe_data(symbol, '5m', candle)
        
        # Update sentiment based on price action
        if symbol in self.intraday_data:
            prev_close = self.intraday_data[symbol].get('prev_close', candle['close'])
            price_change = ((candle['close'] - prev_close) / prev_close * 100) if prev_close > 0 else 0
            volume_change = 0  # Would calculate from historical volume
            
            self.sentiment_analyzer.update_sentiment(symbol, price_change, volume_change)
            self.intraday_data[symbol]['prev_close'] = candle['close']
    
    def _get_ai_signal(self, symbol: str, market_data: Dict) -> Dict:
        """
        Get comprehensive AI signal combining all modules.
        
        Returns:
            Dict with signal, confidence, and component scores
        """
        # 1. Pattern Recognition
        patterns = self.pattern_recognizer.detect_candlestick_patterns(symbol)
        pattern_signal = self._interpret_patterns(patterns)
        
        # 2. Trend Analysis
        trend = self.pattern_recognizer.detect_trend(symbol)
        trend_signal = self._interpret_trend(trend)
        
        # 3. Sentiment Analysis
        sentiment = self.sentiment_analyzer.get_sentiment_score(symbol)
        sentiment_signal = self._interpret_sentiment(sentiment)
        
        # 4. Predictive Model
        prediction = self.predictive_model.predict_price_movement(symbol)
        prediction_signal = self._interpret_prediction(prediction)
        
        # 5. Support/Resistance
        levels = self.pattern_recognizer.identify_support_resistance(symbol)
        sr_signal = self._check_support_resistance(symbol, market_data, levels)
        
        # Combine all signals with weights
        signals = {
            'pattern': {'signal': pattern_signal, 'weight': 0.2},
            'trend': {'signal': trend_signal, 'weight': 0.25},
            'sentiment': {'signal': sentiment_signal, 'weight': 0.15},
            'prediction': {'signal': prediction_signal, 'weight': 0.3},
            'sr_levels': {'signal': sr_signal, 'weight': 0.1}
        }
        
        # Calculate weighted signal
        total_score = 0
        total_weight = 0
        
        for component, data in signals.items():
            if data['signal'] in ['BUY', 'SELL']:
                score = 1 if data['signal'] == 'BUY' else -1
                total_score += score * data['weight']
                total_weight += data['weight']
        
        # Determine final AI signal
        if total_weight == 0:
            return {'signal': None, 'confidence': 0, 'components': signals}
        
        avg_score = total_score / total_weight
        confidence = abs(avg_score)
        
        if avg_score > 0.3:
            final_signal = 'BUY'
        elif avg_score < -0.3:
            final_signal = 'SELL'
        else:
            final_signal = None
        
        return {
            'signal': final_signal,
            'confidence': confidence,
            'components': signals
        }
    
    def _interpret_patterns(self, patterns: Dict[str, float]) -> Optional[str]:
        """Interpret candlestick patterns."""
        if not patterns:
            return None
        
        bullish_patterns = ['hammer', 'bullish_engulfing', 'morning_star']
        bearish_patterns = ['shooting_star', 'bearish_engulfing', 'evening_star']
        
        bullish_score = sum(patterns.get(p, 0) for p in bullish_patterns)
        bearish_score = sum(patterns.get(p, 0) for p in bearish_patterns)
        
        if bullish_score > bearish_score and bullish_score > 0.6:
            return 'BUY'
        elif bearish_score > bullish_score and bearish_score > 0.6:
            return 'SELL'
        
        return None
    
    def _interpret_trend(self, trend: Dict) -> Optional[str]:
        """Interpret trend analysis."""
        if trend['confidence'] < 0.5:
            return None
        
        if trend['direction'] == 'uptrend' and trend['strength'] > 0.5:
            return 'BUY'
        elif trend['direction'] == 'downtrend' and trend['strength'] > 0.5:
            return 'SELL'
        
        return None
    
    def _interpret_sentiment(self, sentiment: Dict) -> Optional[str]:
        """Interpret sentiment analysis."""
        if sentiment['confidence'] < 0.4:
            return None
        
        return self.sentiment_analyzer.get_sentiment_signal(
            list(self.sentiment_analyzer.sentiment_cache.keys())[0] 
            if self.sentiment_analyzer.sentiment_cache else None
        )
    
    def _interpret_prediction(self, prediction: Dict) -> Optional[str]:
        """Interpret predictive model output."""
        if prediction['confidence'] < self.ai_confidence_threshold:
            return None
        
        if prediction['direction'] == 'up':
            return 'BUY'
        elif prediction['direction'] == 'down':
            return 'SELL'
        
        return None
    
    def _check_support_resistance(self, symbol: str, market_data: Dict, levels: Dict) -> Optional[str]:
        """Check if price is near support/resistance."""
        symbol_key = f"NSE:{symbol}"
        if symbol_key not in market_data:
            return None
        
        current_price = market_data[symbol_key].get('last_price', 0)
        if current_price == 0:
            return None
        
        # Check if near support (buy opportunity)
        for support in levels.get('support', [])[:2]:  # Check top 2 support levels
            if abs(current_price - support) / support < 0.005:  # Within 0.5%
                return 'BUY'
        
        # Check if near resistance (sell opportunity)
        for resistance in levels.get('resistance', [])[:2]:
            if abs(current_price - resistance) / resistance < 0.005:
                return 'SELL'
        
        return None
    
    def _combine_signals(self, symbol: str, base_signal: Optional[str], 
                        ai_signal: Dict) -> Optional[str]:
        """
        Emotion-free signal combination using data-driven rules.
        
        Priority:
        1. If AI confidence is high and agrees with base -> strong signal
        2. If AI confidence is high but disagrees -> use AI (it sees more)
        3. If AI confidence is low -> use base strategy
        4. If both neutral -> no trade
        5. Psychology guard has final veto power
        """
        ai_conf = ai_signal['confidence']
        ai_sig = ai_signal['signal']
        
        # First determine the raw signal without psychology filter
        raw_signal = self._get_raw_combined_signal(symbol, base_signal, ai_signal)
        
        # If no raw signal, nothing to check
        if not raw_signal:
            return None
        
        # Apply psychology guard - this is the emotional control layer
        psych_check = self.psychology_guard.should_allow_trade(
            symbol, raw_signal, ai_conf
        )
        
        if not psych_check['allowed']:
            self.logger.warning(
                f"{symbol}: Trade BLOCKED by psychology guard - {psych_check['reason']}"
            )
            coaching = self.psychology_guard.get_emotional_coaching()
            self.logger.info(coaching)
            return None
        
        # Log emotional state even when allowing trade
        if psych_check['emotional_state'] != 'neutral':
            self.logger.info(
                f"{symbol}: Trading with {psych_check['emotional_state']} state - "
                f"adjustment: {psych_check['adjustment']:.2f}x"
            )
        
        return raw_signal
    
    def _get_raw_combined_signal(self, symbol: str, base_signal: Optional[str],
                                 ai_signal: Dict) -> Optional[str]:
        """
        Get raw combined signal without psychology filtering.
        
        Returns:
            Raw signal before emotional control checks
        """
        ai_conf = ai_signal['confidence']
        ai_sig = ai_signal['signal']
        
        # Check position status for sell signals
        has_position = self.has_position(symbol)
        
        # High AI confidence - trust the AI
        if ai_conf >= self.ai_confidence_threshold:
            # Both agree - strong signal
            if base_signal == ai_sig and base_signal:
                self.logger.info(f"{symbol}: Strong consensus - Base and AI agree on {base_signal}")
                return base_signal
            
            # AI has signal, base doesn't - use AI
            elif ai_sig and not base_signal:
                # CRITICAL: Don't SELL if we have no position
                if ai_sig == 'SELL' and not has_position:
                    self.logger.debug(f"{symbol}: AI SELL signal ignored - no position to sell")
                    return None
                self.logger.info(f"{symbol}: AI signal {ai_sig} (confidence: {ai_conf:.2f})")
                return ai_sig
            
            # Both have signals but disagree - use higher confidence source
            elif ai_sig and base_signal and ai_sig != base_signal:
                # CRITICAL: Don't SELL if we have no position
                if ai_sig == 'SELL' and not has_position:
                    self.logger.debug(f"{symbol}: AI SELL signal ignored - no position to sell")
                    return None
                self.logger.info(f"{symbol}: Conflict - AI={ai_sig}, Base={base_signal}. Using AI.")
                return ai_sig
        
        # Low AI confidence - use base strategy
        if base_signal:
            # Check sentiment supports the trade (risk management)
            if self.sentiment_analyzer.should_trade_based_on_sentiment(symbol, base_signal):
                self.logger.info(f"{symbol}: Base strategy signal {base_signal} (AI confidence low)")
                return base_signal
            else:
                self.logger.info(f"{symbol}: Base signal {base_signal} blocked by negative sentiment")
                return None
        
        return None
    
    def calculate_position_size(self, symbol: str, signal: str) -> int:
        """
        Dynamic position sizing using AI confidence, sentiment, and psychology.
        """
        # Get base position size
        base_size = super().calculate_position_size(symbol, signal)
        
        if base_size == 0:
            return 0
        
        # Apply AI adjustments
        sentiment_adj = self.sentiment_analyzer.get_sentiment_adjustment(symbol)
        prediction_adj = self.predictive_model.get_confidence_adjustment(symbol)
        
        # Get psychology adjustment (handles win/loss streaks)
        psych_check = self.psychology_guard.should_allow_trade(symbol, signal, 0.5)
        psych_adj = psych_check.get('adjustment', 1.0)
        
        # Combined adjustment
        total_adjustment = (sentiment_adj + prediction_adj) / 2 * psych_adj
        total_adjustment = max(0.3, min(1.5, total_adjustment))
        
        adjusted_size = int(base_size * total_adjustment)
        
        self.logger.info(
            f"{symbol} position size: {base_size} -> {adjusted_size} "
            f"(sentiment: {sentiment_adj:.2f}x, prediction: {prediction_adj:.2f}x, "
            f"psychology: {psych_adj:.2f}x)"
        )
        
        return max(1, adjusted_size)
    
    def execute_signal(self, symbol: str, signal: str):
        """
        Execute trade and update AI models with outcome (continuous learning).
        """
        try:
            # Get entry price before execution
            ltp_data = self.trader.get_ltp([symbol])
            entry_price = ltp_data.get(f"NSE:{symbol}", 0)
            
            if entry_price <= 0:
                self.logger.error(f"Invalid entry price for {symbol}: {entry_price}")
                return
            
            # Execute the trade
            super().execute_signal(symbol, signal)
            
            # Record trade in psychology guard
            quantity = self.get_position_quantity(symbol)
            if quantity > 0:
                self.psychology_guard.record_trade(
                    symbol, signal, entry_price, abs(quantity), None
                )
            
            # Track for later learning
            if signal in ['BUY', 'SELL']:
                if symbol not in self.entry_prices:
                    self.entry_prices[symbol] = {
                        'price': entry_price,
                        'timestamp': datetime.now(),
                        'signal': signal,
                        'patterns': self.pattern_recognizer.detect_candlestick_patterns(symbol)
                    }
        except Exception as e:
            self.logger.error(f"Error executing signal for {symbol}: {e}", exc_info=True)
    
    def _learn_from_trade(self, symbol: str, success: bool):
        """
        Continuous learning from trade outcomes.
        Updates all AI modules based on trade success/failure.
        """
        self.ai_trades['total'] += 1
        
        if success:
            self.ai_trades['successful'] += 1
        else:
            self.ai_trades['failed'] += 1
        
        # Update pattern recognizer
        if symbol in self.entry_prices and 'patterns' in self.entry_prices[symbol]:
            for pattern_name in self.entry_prices[symbol]['patterns'].keys():
                self.pattern_recognizer.learn_from_pattern(pattern_name, success)
        
        # Update predictive model
        self.predictive_model.learn_from_trade(symbol, success)
        
        # Save models periodically
        if self.ai_trades['total'] % 10 == 0:
            self._save_ai_models()
        
        success_rate = self.ai_trades['successful'] / self.ai_trades['total'] if self.ai_trades['total'] > 0 else 0
        self.logger.info(
            f"AI Learning Update - Total: {self.ai_trades['total']}, "
            f"Success Rate: {success_rate:.2%}"
        )
    
    def update_position(self, symbol: str, transaction_type: str, quantity: int):
        """
        Override to learn from closed positions and update psychology guard.
        """
        try:
            super().update_position(symbol, transaction_type, quantity)
            
            # If closing a position (SELL after BUY), learn from it
            if transaction_type == 'SELL' and symbol in self.entry_prices:
                entry_price = self.entry_prices[symbol].get('price', 0)
                
                # Get current exit price
                try:
                    ltp_data = self.trader.get_ltp([symbol])
                    exit_price = ltp_data.get(f"NSE:{symbol}", 0)
                except Exception as e:
                    self.logger.warning(f"Could not get exit price for {symbol}: {e}")
                    exit_price = 0
                
                if entry_price > 0 and exit_price > 0:
                    profit_loss = (exit_price - entry_price) * quantity
                    success = profit_loss > 0
                    
                    # Update psychology guard with outcome
                    self.psychology_guard.record_trade(
                        symbol, transaction_type, exit_price, quantity, profit_loss
                )
                
                    # Update capital tracking
                    try:
                        if hasattr(self.trader, 'margins'):
                            margins = self.trader.margins()
                        elif hasattr(self.trader, 'kite'):
                            margins = self.trader.kite.margins()
                        else:
                            margins = {}
                        current_capital = margins.get('equity', {}).get('available', {}).get('cash', 0)
                        self.psychology_guard.update_capital(current_capital)
                    except Exception as e:
                        self.logger.error(f"Error updating capital: {e}")
                    
                    # Learn from the trade
                    self._learn_from_trade(symbol, success)
        except Exception as e:
            self.logger.error(f"Error in update_position for {symbol}: {e}", exc_info=True)
    
    def get_ai_metrics(self) -> Dict:
        """Get AI performance metrics including psychology."""
        return {
            'total_trades': self.ai_trades['total'],
            'successful_trades': self.ai_trades['successful'],
            'failed_trades': self.ai_trades['failed'],
            'success_rate': (self.ai_trades['successful'] / self.ai_trades['total'] 
                           if self.ai_trades['total'] > 0 else 0),
            'prediction_accuracy': self.predictive_model.get_prediction_accuracy(),
            'pattern_success_rates': self.pattern_recognizer.pattern_success_rates,
            'psychology': self.psychology_guard.get_discipline_report()
        }
    
    def reset_daily_data(self):
        """Reset daily data including psychology guard."""
        super().reset_daily_data()
        
        # Reset psychology guard with current capital
        try:
            margins = self.trader.kite.margins()
            starting_capital = margins.get('equity', {}).get('available', {}).get('cash', 0)
            self.psychology_guard.reset_daily_stats(starting_capital)
        except Exception as e:
            self.logger.error(f"Error resetting psychology guard: {e}")
    
    def cleanup(self):
        """Save AI models before cleanup."""
        self._save_ai_models()
        
        # Log final discipline report
        discipline_report = self.psychology_guard.get_discipline_report()
        self.logger.info(f"Final Discipline Report: {discipline_report}")
        
        super().cleanup()
