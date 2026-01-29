"""
Base strategy class with abstract methods for signal generation.
All concrete strategies must inherit from BaseStrategy.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from enum import Enum
import pandas as pd

from core.logger import get_logger

logger = get_logger(__name__)


class SignalType(Enum):
    """Trade signal types."""
    BUY = "BUY"
    SELL = "SELL"
    CLOSE_BUY = "CLOSE_BUY"
    CLOSE_SELL = "CLOSE_SELL"
    HOLD = "HOLD"


class TradeSignal:
    """Container for trade signals with metadata."""
    
    def __init__(self, symbol: str, signal_type: SignalType, 
                 price: float, stop_loss: float, take_profit: float,
                 reason: str = "", confidence: float = 1.0):
        """
        Initialize trade signal.
        
        Args:
            symbol: Trading symbol
            signal_type: Type of signal (BUY/SELL/CLOSE/HOLD)
            price: Entry/exit price
            stop_loss: Stop loss level
            take_profit: Take profit level
            reason: Reason for signal
            confidence: Signal confidence (0.0 to 1.0)
        """
        self.symbol = symbol
        self.signal_type = signal_type
        self.price = price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.reason = reason
        self.confidence = confidence
    
    def __repr__(self) -> str:
        return (f"TradeSignal({self.signal_type.value} {self.symbol} @ {self.price:.5f} | "
                f"SL: {self.stop_loss:.5f} | TP: {self.take_profit:.5f})")
    
    def is_entry_signal(self) -> bool:
        """Check if this is an entry signal."""
        return self.signal_type in [SignalType.BUY, SignalType.SELL]
    
    def is_exit_signal(self) -> bool:
        """Check if this is an exit signal."""
        return self.signal_type in [SignalType.CLOSE_BUY, SignalType.CLOSE_SELL]


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    All strategies must implement on_tick and generate_signal methods.
    """
    
    def __init__(self, name: str):
        """
        Initialize strategy.
        
        Args:
            name: Strategy name
        """
        self.name = name
        self.active_signals: Dict[str, TradeSignal] = {}
        logger.info(f"Strategy initialized: {name}")
    
    @abstractmethod
    def on_tick(self, symbol: str, tick_data: Dict) -> Optional[TradeSignal]:
        """
        Process tick data and potentially generate signal.
        Called on every tick update.
        
        Args:
            symbol: Trading symbol
            tick_data: Current tick information
            
        Returns:
            TradeSignal or None
        """
        pass
    
    @abstractmethod
    def generate_signal(self, symbol: str, dataframe: pd.DataFrame) -> Optional[TradeSignal]:
        """
        Generate trading signal based on candle data and indicators.
        Called when new candle is formed or on-demand.
        
        Args:
            symbol: Trading symbol
            dataframe: Historical price data with indicators
            
        Returns:
            TradeSignal or None
        """
        pass
    
    def should_exit(self, symbol: str, current_price: float, 
                    position_type: str) -> Optional[TradeSignal]:
        """
        Check if existing position should be closed.
        Override in concrete strategies for custom exit logic.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            position_type: Position type ('buy' or 'sell')
            
        Returns:
            Exit signal or None
        """
        return None
    
    def reset(self) -> None:
        """Reset strategy state. Override if needed."""
        self.active_signals.clear()
        logger.info(f"Strategy {self.name} reset")
    
    def get_parameters(self) -> Dict:
        """
        Get strategy parameters for logging/monitoring.
        Override in concrete strategies.
        
        Returns:
            Dictionary of parameter values
        """
        return {"name": self.name}