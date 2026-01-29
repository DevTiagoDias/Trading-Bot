"""
Advanced example: Running multiple strategies simultaneously.
This example shows how to extend the bot to run multiple strategies.
"""

import MetaTrader5 as mt5
import time
from datetime import datetime
from typing import List

from config import config
from core.logger import get_logger
from core.mt5_interface import MT5Client
from data.data_feed import MarketDataHandler
from strategies.base import BaseStrategy
from strategies.atr_trend_follower import ATRTrendFollower
from execution.order_manager import OrderManager
from risk.risk_manager import RiskManager
from utils.notifications import notifier

logger = get_logger(__name__)


class MultiStrategyBot:
    """
    Trading bot that can run multiple strategies simultaneously.
    Each strategy can target different symbols or timeframes.
    """
    
    def __init__(self, strategies: List[BaseStrategy]):
        """
        Initialize multi-strategy bot.
        
        Args:
            strategies: List of strategy instances to run
        """
        self.mt5_client = MT5Client()
        self.data_handler = MarketDataHandler()
        self.order_manager = OrderManager()
        self.risk_manager = RiskManager()
        
        self.strategies = strategies
        self.running = False
        
        # Track which strategy opened each position
        self.position_strategy_map = {}
        
        logger.info(f"MultiStrategyBot initialized with {len(strategies)} strategies")
    
    def start(self):
        """Start the multi-strategy bot."""
        try:
            # Connect to MT5
            if not self.mt5_client.connect():
                logger.error("Failed to connect to MT5")
                return False
            
            # Initialize data
            if not self.data_handler.initialize_buffers():
                logger.error("Failed to initialize data buffers")
                return False
            
            self.running = True
            notifier.notify_bot_started()
            
            # Run main loop
            self._run_loop()
            
        except Exception as e:
            logger.error(f"Error in multi-strategy bot: {e}", exc_info=True)
    
    def _run_loop(self):
        """Main trading loop for multiple strategies."""
        logger.info("Multi-strategy loop started")
        
        while self.running:
            try:
                # Check connection
                if not self.mt5_client.is_connected():
                    if not self.mt5_client.reconnect():
                        time.sleep(30)
                        continue
                
                # Check risk limits
                if not self.risk_manager.check_daily_drawdown():
                    time.sleep(300)
                    continue
                
                # Update data
                self.data_handler.update_data()
                
                # Process each strategy
                for strategy in self.strategies:
                    self._process_strategy(strategy)
                
                time.sleep(5)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in loop: {e}", exc_info=True)
                time.sleep(10)
    
    def _process_strategy(self, strategy: BaseStrategy):
        """
        Process signals from a single strategy.
        
        Args:
            strategy: Strategy instance
        """
        try:
            symbols = config.get('trading', 'symbols', default=[])
            
            for symbol in symbols:
                # Get data
                data = self.data_handler.get_current_data(symbol, periods=300)
                if data is None:
                    continue
                
                # Generate signal
                signal = strategy.generate_signal(symbol, data)
                
                if signal and signal.is_entry_signal():
                    # Check if we already have a position from ANY strategy
                    positions = self.order_manager.get_open_positions(symbol)
                    if positions:
                        logger.debug(f"Position already exists for {symbol}, skipping")
                        continue
                    
                    # Validate and execute
                    is_valid, reason = self.risk_manager.validate_signal(signal)
                    
                    if is_valid:
                        lot_size = self.risk_manager.calculate_lot_size(signal)
                        if lot_size > 0:
                            result, order_id, msg = self.order_manager.execute_order(signal, lot_size)
                            
                            if result.name == "SUCCESS" and order_id:
                                # Map position to strategy
                                self.position_strategy_map[order_id] = strategy
                                logger.info(f"✓ {strategy.name} opened position on {symbol}")
                    
        except Exception as e:
            logger.error(f"Error processing {strategy.name}: {e}")
    
    def stop(self):
        """Stop the bot."""
        self.running = False
        self.order_manager.close_all_positions()
        self.mt5_client.disconnect()
        notifier.notify_bot_stopped()


def create_custom_strategy_example():
    """
    Example: Create a custom momentum strategy.
    """
    from strategies.base import BaseStrategy, TradeSignal, SignalType
    import pandas as pd
    
    class MomentumStrategy(BaseStrategy):
        """Simple momentum crossover strategy."""
        
        def __init__(self):
            super().__init__("Momentum Crossover")
            self.fast_ma = 10
            self.slow_ma = 30
        
        def generate_signal(self, symbol, dataframe):
            if len(dataframe) < self.slow_ma:
                return None
            
            # Calculate moving averages
            dataframe['MA_fast'] = dataframe['close'].rolling(self.fast_ma).mean()
            dataframe['MA_slow'] = dataframe['close'].rolling(self.slow_ma).mean()
            
            current = dataframe.iloc[-1]
            previous = dataframe.iloc[-2]
            
            # BUY: Fast MA crosses above Slow MA
            if (previous['MA_fast'] <= previous['MA_slow'] and 
                current['MA_fast'] > current['MA_slow']):
                
                atr = current.get('ATRr_14', 0.001)
                
                return TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=current['close'],
                    stop_loss=current['close'] - (2 * atr),
                    take_profit=current['close'] + (3 * atr),
                    reason="MA Crossover Up"
                )
            
            # SELL: Fast MA crosses below Slow MA
            elif (previous['MA_fast'] >= previous['MA_slow'] and 
                  current['MA_fast'] < current['MA_slow']):
                
                atr = current.get('ATRr_14', 0.001)
                
                return TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    price=current['close'],
                    stop_loss=current['close'] + (2 * atr),
                    take_profit=current['close'] - (3 * atr),
                    reason="MA Crossover Down"
                )
            
            return None
        
        def on_tick(self, symbol, tick_data):
            return None
    
    return MomentumStrategy()


def main():
    """Run multi-strategy bot example."""
    
    # Create strategy instances
    strategies = [
        ATRTrendFollower(),              # Original strategy
        create_custom_strategy_example()  # Custom momentum strategy
    ]
    
    # Initialize and run bot
    bot = MultiStrategyBot(strategies)
    
    try:
        bot.start()
    except KeyboardInterrupt:
        logger.info("Stopping multi-strategy bot...")
    finally:
        bot.stop()


if __name__ == "__main__":
    main()