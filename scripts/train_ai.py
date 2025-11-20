#!/usr/bin/env python3
"""
AI Historical Training Module

Fetches historical data from Kite API and trains the AI model.
- Downloads past market data (1-3 months)
- Trains pattern recognition on historical patterns
- Trains predictive model on price movements
- Trains sentiment analyzer on price action
- Validates model accuracy
- Saves trained models for paper trading
"""
import os
import logging
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
import json
from typing import List, Dict

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'data/logs/ai_training_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AIHistoricalTrainer:
    """
    Trains AI models using historical market data.
    """
    
    def __init__(self, trader, symbols: List[str], lookback_days: int = 60):
        """
        Initialize trainer.
        
        Args:
            trader: KiteTrader instance for fetching data
            symbols: List of stock symbols to train on
            lookback_days: Number of days of historical data to fetch
        """
        self.trader = trader
        self.symbols = symbols
        self.lookback_days = lookback_days
        
        # Initialize AI modules
        from src.ai_modules.pattern_recognition import PatternRecognizer
        from src.ai_modules.sentiment_analyzer import SentimentAnalyzer
        from src.ai_modules.predictive_model import PredictiveModel
        
        self.pattern_recognizer = PatternRecognizer(lookback_periods=100)
        self.sentiment_analyzer = SentimentAnalyzer()
        self.predictive_model = PredictiveModel()
        
        self.historical_data = {}
        self.training_stats = {
            'total_candles': 0,
            'patterns_detected': 0,
            'predictions_made': 0,
            'successful_predictions': 0
        }
        
        logger.info(f"AI Trainer initialized for {len(symbols)} symbols, {lookback_days} days lookback")
    
    def fetch_historical_data(self):
        """
        Fetch historical data for all symbols.
        """
        logger.info("\n" + "=" * 70)
        logger.info("📥 FETCHING HISTORICAL DATA")
        logger.info("=" * 70)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.lookback_days)
        
        for symbol in self.symbols:
            logger.info(f"\nFetching data for {symbol}...")
            
            try:
                # Fetch daily data
                daily_data = self.trader.get_historical_data(
                    symbol=symbol,
                    from_date=start_date,
                    to_date=end_date,
                    interval="day"
                )
                
                # Fetch 5-minute data for last 30 days (for intraday patterns)
                intraday_start = end_date - timedelta(days=30)
                intraday_data = self.trader.get_historical_data(
                    symbol=symbol,
                    from_date=intraday_start,
                    to_date=end_date,
                    interval="5minute"
                )
                
                self.historical_data[symbol] = {
                    'daily': daily_data,
                    'intraday': intraday_data
                }
                
                logger.info(f"  ✓ Fetched {len(daily_data)} daily candles")
                logger.info(f"  ✓ Fetched {len(intraday_data)} 5-minute candles")
                
                self.training_stats['total_candles'] += len(daily_data) + len(intraday_data)
                
            except Exception as e:
                logger.error(f"  ✗ Failed to fetch data for {symbol}: {e}")
                self.historical_data[symbol] = {'daily': [], 'intraday': []}
        
        logger.info(f"\n✅ Total candles fetched: {self.training_stats['total_candles']}")
    
    def train_pattern_recognition(self):
        """
        Train pattern recognition on historical data.
        """
        logger.info("\n" + "=" * 70)
        logger.info("🔍 TRAINING PATTERN RECOGNITION")
        logger.info("=" * 70)
        
        for symbol in self.symbols:
            if symbol not in self.historical_data:
                continue
            
            logger.info(f"\nTraining patterns for {symbol}...")
            
            daily_data = self.historical_data[symbol]['daily']
            intraday_data = self.historical_data[symbol]['intraday']
            
            # Train on daily data
            for i, candle in enumerate(daily_data):
                # Convert to expected format
                candle_data = {
                    'open': candle['open'],
                    'high': candle['high'],
                    'low': candle['low'],
                    'close': candle['close'],
                    'volume': candle['volume']
                }
                
                # Update price history
                self.pattern_recognizer.update_price_history(symbol, candle_data)
                
                # Detect patterns (after sufficient data)
                if i > 20:
                    patterns = self.pattern_recognizer.detect_candlestick_patterns(symbol)
                    if patterns:
                        self.training_stats['patterns_detected'] += len(patterns)
                        
                        # Validate pattern by checking next candle
                        if i < len(daily_data) - 1:
                            next_candle = daily_data[i + 1]
                            current_close = candle['close']
                            next_close = next_candle['close']
                            
                            # Check if prediction was correct
                            for pattern_name, confidence in patterns.items():
                                bullish_patterns = ['hammer', 'bullish_engulfing', 'morning_star']
                                bearish_patterns = ['shooting_star', 'bearish_engulfing', 'evening_star']
                                
                                if pattern_name in bullish_patterns:
                                    success = next_close > current_close
                                    self.pattern_recognizer.learn_from_pattern(pattern_name, success)
                                elif pattern_name in bearish_patterns:
                                    success = next_close < current_close
                                    self.pattern_recognizer.learn_from_pattern(pattern_name, success)
            
            # Train on intraday data (last 1000 candles for speed)
            for candle in intraday_data[-1000:]:
                candle_data = {
                    'open': candle['open'],
                    'high': candle['high'],
                    'low': candle['low'],
                    'close': candle['close'],
                    'volume': candle['volume']
                }
                self.pattern_recognizer.update_price_history(symbol, candle_data)
            
            logger.info(f"  ✓ Trained on {len(daily_data)} daily + {min(1000, len(intraday_data))} intraday candles")
        
        logger.info(f"\n✅ Total patterns detected: {self.training_stats['patterns_detected']}")
        logger.info(f"📊 Pattern success rates:")
        for pattern, stats in list(self.pattern_recognizer.pattern_success_rates.items())[:10]:
            total = stats['successes'] + stats['failures']
            if total > 0:
                logger.info(f"  {pattern}: {stats['rate']:.1%} ({stats['successes']}/{total})")
    
    def train_sentiment_analyzer(self):
        """
        Train sentiment analyzer on historical price action.
        """
        logger.info("\n" + "=" * 70)
        logger.info("💭 TRAINING SENTIMENT ANALYZER")
        logger.info("=" * 70)
        
        for symbol in self.symbols:
            if symbol not in self.historical_data:
                continue
            
            logger.info(f"\nTraining sentiment for {symbol}...")
            
            daily_data = self.historical_data[symbol]['daily']
            
            for i in range(1, len(daily_data)):
                prev_candle = daily_data[i - 1]
                curr_candle = daily_data[i]
                
                # Validate candle data types
                try:
                    prev_close = float(prev_candle['close']) if not isinstance(prev_candle['close'], dict) else float(prev_candle['close'].get('value', prev_candle['close'].get('close', 0)))
                    curr_close = float(curr_candle['close']) if not isinstance(curr_candle['close'], dict) else float(curr_candle['close'].get('value', curr_candle['close'].get('close', 0)))
                    prev_volume = float(prev_candle['volume']) if not isinstance(prev_candle['volume'], dict) else float(prev_candle['volume'].get('value', prev_candle['volume'].get('volume', 0)))
                    curr_volume = float(curr_candle['volume']) if not isinstance(curr_candle['volume'], dict) else float(curr_candle['volume'].get('value', curr_candle['volume'].get('volume', 0)))
                    
                    # Calculate price change
                    if prev_close > 0:
                        price_change = ((curr_close - prev_close) / prev_close) * 100
                    else:
                        continue
                    
                    # Calculate volume change
                    volume_change = ((curr_volume - prev_volume) / prev_volume) * 100 if prev_volume > 0 else 0
                    
                    # Update sentiment
                    self.sentiment_analyzer.update_sentiment(symbol, price_change, volume_change)
                except (TypeError, ValueError, KeyError) as e:
                    logger.warning(f"  ⚠ Skipping candle {i} for {symbol}: Invalid data format - {e}")
                    continue
            
            logger.info(f"  ✓ Trained on {len(daily_data)} days of price action")
        
        logger.info("\n✅ Sentiment analysis training complete")
    
    def train_predictive_model(self):
        """
        Train predictive model on historical price movements.
        """
        logger.info("\n" + "=" * 70)
        logger.info("🔮 TRAINING PREDICTIVE MODEL")
        logger.info("=" * 70)
        
        for symbol in self.symbols:
            if symbol not in self.historical_data:
                continue
            
            logger.info(f"\nTraining predictions for {symbol}...")
            
            intraday_data = self.historical_data[symbol]['intraday']
            
            # Train on 5-minute data
            for i, candle in enumerate(intraday_data[:-1]):  # Skip last candle
                candle_data = {
                    'open': candle['open'],
                    'high': candle['high'],
                    'low': candle['low'],
                    'close': candle['close'],
                    'volume': candle['volume']
                }
                
                # Update model with current timeframe
                self.predictive_model.update_timeframe_data(symbol, '5m', candle_data)
                
                # Make prediction and validate (after sufficient data)
                if i > 50:
                    prediction = self.predictive_model.predict_price_movement(symbol)
                    
                    # Check if prediction was correct
                    next_candle = intraday_data[i + 1]
                    actual_direction = 'up' if next_candle['close'] > candle['close'] else 'down'
                    
                    if prediction['direction'] == actual_direction:
                        self.predictive_model.learn_from_trade(symbol, True)
                        self.training_stats['successful_predictions'] += 1
                    else:
                        self.predictive_model.learn_from_trade(symbol, False)
                    
                    self.training_stats['predictions_made'] += 1
            
            logger.info(f"  ✓ Trained on {len(intraday_data)} 5-minute candles")
        
        accuracy = (self.training_stats['successful_predictions'] / self.training_stats['predictions_made'] * 100) if self.training_stats['predictions_made'] > 0 else 0
        logger.info(f"\n✅ Predictions made: {self.training_stats['predictions_made']}")
        logger.info(f"📊 Prediction accuracy: {accuracy:.2f}%")
    
    def save_trained_models(self, data_dir='data/ai_data'):
        """
        Save all trained models to disk.
        """
        logger.info("\n" + "=" * 70)
        logger.info("💾 SAVING TRAINED MODELS")
        logger.info("=" * 70)
        
        os.makedirs(data_dir, exist_ok=True)
        
        # Save pattern recognizer
        pattern_file = os.path.join(data_dir, 'patterns.json')
        self.pattern_recognizer.save_patterns(pattern_file)
        logger.info(f"  ✓ Patterns saved to {pattern_file}")
        
        # Save sentiment analyzer
        sentiment_file = os.path.join(data_dir, 'sentiment.json')
        self.sentiment_analyzer.save_sentiment_data(sentiment_file)
        logger.info(f"  ✓ Sentiment data saved to {sentiment_file}")
        
        # Save predictive model
        model_file = os.path.join(data_dir, 'model.json')
        self.predictive_model.save_model(model_file)
        logger.info(f"  ✓ Model saved to {model_file}")
        
        # Save training stats
        stats_file = os.path.join(data_dir, 'training_stats.json')
        with open(stats_file, 'w') as f:
            json.dump(self.training_stats, f, indent=2)
        logger.info(f"  ✓ Training stats saved to {stats_file}")
        
        logger.info("\n✅ All models saved successfully")
    
    def run_training(self):
        """
        Run complete training pipeline.
        """
        logger.info("\n" + "=" * 70)
        logger.info("🎓 AI HISTORICAL TRAINING - START")
        logger.info("=" * 70)
        logger.info(f"Symbols: {', '.join(self.symbols)}")
        logger.info(f"Lookback: {self.lookback_days} days")
        logger.info("=" * 70)
        
        try:
            # Step 1: Fetch historical data
            self.fetch_historical_data()
            
            # Step 2: Train pattern recognition
            self.train_pattern_recognition()
            
            # Step 3: Train sentiment analyzer
            self.train_sentiment_analyzer()
            
            # Step 4: Train predictive model
            self.train_predictive_model()
            
            # Step 5: Save models
            self.save_trained_models()
            
            # Final summary
            logger.info("\n" + "=" * 70)
            logger.info("🎉 TRAINING COMPLETE - SUMMARY")
            logger.info("=" * 70)
            logger.info(f"Total candles processed: {self.training_stats['total_candles']}")
            logger.info(f"Patterns detected: {self.training_stats['patterns_detected']}")
            logger.info(f"Predictions made: {self.training_stats['predictions_made']}")
            logger.info(f"Successful predictions: {self.training_stats['successful_predictions']}")
            
            if self.training_stats['predictions_made'] > 0:
                accuracy = (self.training_stats['successful_predictions'] / self.training_stats['predictions_made']) * 100
                logger.info(f"Overall accuracy: {accuracy:.2f}%")
            
            logger.info("\n✅ AI models are now trained and ready for paper trading!")
            logger.info("=" * 70)
            
            return True
            
        except Exception as e:
            logger.error(f"\n❌ Training failed: {e}", exc_info=True)
            return False


def main():
    """
    Main training function.
    """
    from src.kite_trader.trader import KiteTrader
    
    # Connect to Kite for historical data
    logger.info("Connecting to Zerodha Kite API...")
    trader = KiteTrader()
    
    if not trader.is_connected():
        logger.error("Failed to connect to Zerodha. Check your credentials.")
        logger.error("Make sure KITE_ACCESS_TOKEN is set in .env file.")
        return
    
    logger.info("✓ Connected to Zerodha")
    
    # Define symbols to train on
    symbols = [
        'RELIANCE',    # Reliance Industries
        'TCS',         # Tata Consultancy Services
        'INFY',        # Infosys
        'HDFCBANK',    # HDFC Bank
        'ICICIBANK',   # ICICI Bank
        'SBIN',        # State Bank of India
        'BHARTIARTL',  # Bharti Airtel
        'ITC',         # ITC Limited
        'WIPRO',       # Wipro
        'LT'           # Larsen & Toubro
    ]
    
    # Initialize trainer
    trainer = AIHistoricalTrainer(
        trader=trader,
        symbols=symbols,
        lookback_days=60  # 2 months of data
    )
    
    # Run training
    success = trainer.run_training()
    
    if success:
        logger.info("\n" + "=" * 70)
        logger.info("🚀 NEXT STEPS")
        logger.info("=" * 70)
        logger.info("1. Review training stats in data/logs/ai_training_*.log")
        logger.info("2. Check pattern success rates in ai_data/patterns.json")
        logger.info("3. Run paper trading to validate: python ai_paper_trader.py")
        logger.info("4. Monitor AI performance in real-time")
        logger.info("=" * 70)


if __name__ == "__main__":
    main()
