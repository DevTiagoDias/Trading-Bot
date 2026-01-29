"""
Professional logging system for Trading Bot.
Configures rotating file and console handlers with appropriate formatting.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from config import config


class TradingLogger:
    """Centralized logging configuration for the trading bot."""
    
    _loggers = {}
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        Get or create a logger instance.
        
        Args:
            name: Logger name (typically __name__ of the module)
            
        Returns:
            Configured logger instance
        """
        if name in cls._loggers:
            return cls._loggers[name]
        
        logger = logging.getLogger(name)
        
        # Only configure if not already configured
        if not logger.handlers:
            cls._configure_logger(logger)
        
        cls._loggers[name] = logger
        return logger
    
    @classmethod
    def _configure_logger(cls, logger: logging.Logger) -> None:
        """Configure logger with file and console handlers."""
        log_level = config.get('logging', 'level', default='INFO')
        logger.setLevel(getattr(logging, log_level))
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # File handler with rotation
        log_file = config.get('logging', 'file', default='logs/trading_bot.log')
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        max_bytes = config.get('logging', 'max_bytes', default=10485760)  # 10MB
        backup_count = config.get('logging', 'backup_count', default=5)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        
        # Add handlers
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    @classmethod
    def log_trade(cls, action: str, symbol: str, lot: float, 
                  price: float, sl: float, tp: float, 
                  reason: str = "", order_id: Optional[int] = None) -> None:
        """
        Log trade execution with standardized format.
        
        Args:
            action: Trade action (BUY/SELL)
            symbol: Trading symbol
            lot: Position size
            price: Entry price
            sl: Stop loss
            tp: Take profit
            reason: Reason for trade
            order_id: MT5 order ID if available
        """
        logger = cls.get_logger('TRADE')
        
        trade_info = (
            f"{action} {symbol} | Lot: {lot:.2f} | "
            f"Price: {price:.5f} | SL: {sl:.5f} | TP: {tp:.5f}"
        )
        
        if order_id:
            trade_info += f" | Order: {order_id}"
        
        if reason:
            trade_info += f" | Reason: {reason}"
        
        logger.info(trade_info)
    
    @classmethod
    def log_error(cls, error_msg: str, exception: Optional[Exception] = None) -> None:
        """
        Log errors with optional exception details.
        
        Args:
            error_msg: Error message
            exception: Exception object if available
        """
        logger = cls.get_logger('ERROR')
        
        if exception:
            logger.error(f"{error_msg} | Exception: {str(exception)}", exc_info=True)
        else:
            logger.error(error_msg)


# Convenience function
def get_logger(name: str) -> logging.Logger:
    """Get logger instance for a module."""
    return TradingLogger.get_logger(name)