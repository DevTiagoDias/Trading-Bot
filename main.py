"""
Main Trading Bot Orchestrator.
Coordinates all components and manages the trading loop.
"""

import MetaTrader5 as mt5
import time
import signal
import sys
from datetime import datetime
from typing import Dict

from config import config
from core.logger import get_logger, TradingLogger
from core.mt5_interface import MT5Client, MT5ConnectionError
from data.data_feed import MarketDataHandler
from strategies.atr_trend_follower import ATRTrendFollower
from execution.order_manager import OrderManager, OrderResult
from risk.risk_manager import RiskManager
from utils.notifications import notifier

logger = get_logger(__name__)


class TradingBot:
    """
    Main trading bot that orchestrates all components.
    Manages the trading lifecycle from initialization to shutdown.
    """
    
    def __init__(self):
        """Initialize trading bot components."""
        logger.info("=" * 80)
        logger.info("Initializing Trading Bot...")
        logger.info("=" * 80)
        
        # Core components
        self.mt5_client = MT5Client()
        self.data_handler = MarketDataHandler()
        self.strategy = ATRTrendFollower()
        self.order_manager = OrderManager()
        self.risk_manager = RiskManager()
        
        # State management
        self.running = False
        self.symbols = config.get('trading', 'symbols', default=[])
        self.update_interval = 60  # seconds
        self.last_update_time = {}
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {sig}, initiating shutdown...")
        self.stop()
    
    def start(self) -> bool:
        """
        Start the trading bot.
        
        Returns:
            True if started successfully
        """
        try:
            # Connect to MT5
            if not self.mt5_client.connect():
                logger.error("Failed to connect to MT5")
                return False
            
            # Initialize data buffers
            logger.info("Loading historical data...")
            if not self.data_handler.initialize_buffers():
                logger.error("Failed to initialize data buffers")
                return False
            
            # Initialize risk manager
            self.risk_manager.check_daily_drawdown()
            
            # Send startup notification
            notifier.notify_bot_started()
            
            self.running = True
            logger.info("Trading Bot started successfully")
            logger.info(f"Monitoring symbols: {', '.join(self.symbols)}")
            
            # Start main loop
            self._run_main_loop()
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}", exc_info=True)
            notifier.notify_error(f"Bot startup failed: {str(e)}")
            return False
    
    def stop(self) -> None:
        """Stop the trading bot gracefully."""
        logger.info("Stopping Trading Bot...")
        self.running = False
        
        # Close all positions if configured
        if config.get('schedule', 'close_all_eod', default=False):
            logger.info("Closing all open positions...")
            closed = self.order_manager.close_all_positions()
            logger.info(f"Closed {closed} positions")
        
        # Disconnect from MT5
        self.mt5_client.disconnect()
        
        # Send shutdown notification
        notifier.notify_bot_stopped()
        
        logger.info("Trading Bot stopped")
        logger.info("=" * 80)
    
    def _run_main_loop(self) -> None:
        """Main trading loop."""
        logger.info("Entering main trading loop...")
        
        while self.running:
            try:
                # Check connection health
                if not self.mt5_client.is_connected():
                    logger.warning("Connection lost, attempting to reconnect...")
                    if not self.mt5_client.reconnect():
                        logger.error("Reconnection failed, waiting 30s...")
                        time.sleep(30)
                        continue
                
                # Check daily drawdown (circuit breaker)
                if not self.risk_manager.check_daily_drawdown():
                    logger.warning("Circuit breaker active, no new trades allowed")
                    risk_metrics = self.risk_manager.get_risk_metrics()
                    notifier.notify_circuit_breaker(risk_metrics['daily_drawdown_percent'])
                    time.sleep(300)  # Wait 5 minutes before next check
                    continue
                
                # Process each symbol
                for symbol in self.symbols:
                    self._process_symbol(symbol)
                
                # Update trailing stops for open positions
                self._update_trailing_stops()
                
                # Log status periodically
                self._log_status()
                
                # Sleep between iterations
                time.sleep(5)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt detected")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                notifier.notify_error(f"Main loop error: {str(e)}")
                time.sleep(10)
    
    def _process_symbol(self, symbol: str) -> None:
        """
        Process trading logic for a single symbol.
        
        Args:
            symbol: Trading symbol to process
        """
        try:
            # Get current time
            now = datetime.now()
            
            # Check if it's time to update data
            last_update = self.last_update_time.get(symbol, datetime.min)
            if (now - last_update).total_seconds() < self.update_interval:
                return  # Skip if updated recently
            
            # Update market data
            if not self.data_handler.update_data(symbol):
                logger.warning(f"Failed to update data for {symbol}")
                return
            
            self.last_update_time[symbol] = now
            
            # Get current data
            current_data = self.data_handler.get_current_data(symbol, periods=300)
            if current_data is None or len(current_data) < 200:
                return
            
            # Check for existing position
            existing_positions = self.order_manager.get_open_positions(symbol)
            
            if existing_positions:
                # Manage existing position
                self._manage_position(symbol, existing_positions[0])
            else:
                # Look for entry signal
                signal = self.strategy.generate_signal(symbol, current_data)
                
                if signal and signal.is_entry_signal():
                    self._execute_signal(signal)
                    
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}", exc_info=True)
    
    def _execute_signal(self, signal) -> None:
        """
        Validate and execute trade signal.
        
        Args:
            signal: Trade signal to execute
        """
        # Validate signal with risk manager
        is_valid, rejection_reason = self.risk_manager.validate_signal(signal)
        
        if not is_valid:
            logger.info(f"Signal rejected for {signal.symbol}: {rejection_reason}")
            return
        
        # Calculate position size
        lot_size = self.risk_manager.calculate_lot_size(signal)
        
        if lot_size <= 0:
            logger.warning(f"Invalid lot size calculated for {signal.symbol}")
            return
        
        # Execute order
        result, order_id, message = self.order_manager.execute_order(signal, lot_size)
        
        if result == OrderResult.SUCCESS:
            logger.info(f"✓ Order executed: {signal.symbol} {signal.signal_type.value} | Lot: {lot_size:.2f}")
            notifier.notify_trade_opened(
                symbol=signal.symbol,
                action=signal.signal_type.value,
                lot=lot_size,
                price=signal.price,
                sl=signal.stop_loss,
                tp=signal.take_profit
            )
        else:
            logger.error(f"✗ Order failed: {signal.symbol} | {message}")
            notifier.notify_error(f"Order execution failed: {message}")
    
    def _manage_position(self, symbol: str, position) -> None:
        """
        Manage existing position (trailing stops, exits).
        
        Args:
            symbol: Trading symbol
            position: MT5 position object
        """
        try:
            # Get current values
            current_values = self.data_handler.get_latest_values(symbol)
            if current_values is None:
                return
            
            current_price = current_values['close']
            atr = current_values['atr']
            
            # Update trailing stop for the strategy
            if position.type == mt5.ORDER_TYPE_BUY:
                self.strategy.update_trailing_stop(symbol, current_price, atr)
                
                # Check if trailing stop hit
                exit_signal = self.strategy.should_exit(symbol, current_price, 'buy')
                
                if exit_signal:
                    success, message = self.order_manager.close_position(position)
                    if success:
                        self.strategy.remove_trailing_stop(symbol)
                        notifier.notify_trade_closed(
                            symbol=symbol,
                            profit=position.profit,
                            reason=exit_signal.reason
                        )
                        
        except Exception as e:
            logger.error(f"Error managing position for {symbol}: {e}")
    
    def _update_trailing_stops(self) -> None:
        """Update trailing stops for all open positions."""
        try:
            positions = self.order_manager.get_open_positions()
            
            for position in positions:
                symbol = position.symbol
                current_values = self.data_handler.get_latest_values(symbol)
                
                if current_values is None:
                    continue
                
                # Only update for buy positions (can extend to sells)
                if position.type == mt5.ORDER_TYPE_BUY:
                    current_price = current_values['close']
                    atr = current_values['atr']
                    
                    self.strategy.update_trailing_stop(symbol, current_price, atr)
                    
        except Exception as e:
            logger.error(f"Error updating trailing stops: {e}")
    
    def _log_status(self) -> None:
        """Log periodic status information."""
        # This could be expanded to log every 5 minutes or hourly
        pass


def main():
    """Main entry point."""
    bot = TradingBot()
    
    try:
        if bot.start():
            logger.info("Bot is running. Press Ctrl+C to stop.")
        else:
            logger.error("Failed to start bot")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        bot.stop()


if __name__ == "__main__":
    main()