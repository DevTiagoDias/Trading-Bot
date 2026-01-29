"""
ATR Trend Follower Strategy.
Buys on pullbacks in uptrends, uses ATR-based trailing stops.
"""

import MetaTrader5 as mt5
from typing import Dict, Optional
import pandas as pd

from strategies.base import BaseStrategy, TradeSignal, SignalType
from config import config
from core.logger import get_logger

logger = get_logger(__name__)


class ATRTrendFollower(BaseStrategy):
    """
    Trend following strategy with ATR-based stops.
    
    Logic:
    - Entry: Price > EMA(200) AND RSI < 30 (oversold in uptrend)
    - Exit: Trailing stop at 2.0 x ATR
    """
    
    def __init__(self):
        """Initialize ATR Trend Follower strategy."""
        super().__init__("ATR Trend Follower")
        
        # Load parameters from config
        self.atr_period = config.get('strategy', 'atr_period', default=14)
        self.atr_multiplier = config.get('strategy', 'atr_multiplier', default=2.0)
        self.ema_period = config.get('strategy', 'ema_period', default=200)
        self.rsi_period = config.get('strategy', 'rsi_period', default=14)
        self.rsi_oversold = config.get('strategy', 'rsi_oversold', default=30)
        self.rsi_overbought = config.get('strategy', 'rsi_overbought', default=70)
        
        # Track trailing stops for open positions
        self.trailing_stops: Dict[str, float] = {}
        
        logger.info(f"ATR Trend Follower initialized | ATR: {self.atr_period} | "
                   f"Multiplier: {self.atr_multiplier} | EMA: {self.ema_period}")
    
    def on_tick(self, symbol: str, tick_data: Dict) -> Optional[TradeSignal]:
        """
        Process tick for trailing stop updates.
        
        Args:
            symbol: Trading symbol
            tick_data: Current tick data
            
        Returns:
            Exit signal if trailing stop hit, else None
        """
        # This method primarily handles trailing stops
        # Actual entry signals are generated in generate_signal
        
        if symbol in self.trailing_stops:
            current_price = tick_data.get('bid', 0)
            trailing_stop = self.trailing_stops[symbol]
            
            if current_price <= trailing_stop:
                logger.info(f"Trailing stop hit for {symbol} at {current_price:.5f}")
                return TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE_BUY,
                    price=current_price,
                    stop_loss=0,
                    take_profit=0,
                    reason="Trailing stop triggered"
                )
        
        return None
    
    def generate_signal(self, symbol: str, dataframe: pd.DataFrame) -> Optional[TradeSignal]:
        """
        Generate buy/sell signals based on trend and RSI.
        
        Args:
            symbol: Trading symbol
            dataframe: Price data with indicators
            
        Returns:
            TradeSignal or None
        """
        if len(dataframe) < max(self.ema_period, self.rsi_period, self.atr_period):
            logger.debug(f"Insufficient data for {symbol}")
            return None
        
        # Get latest values
        latest = dataframe.iloc[-1]
        previous = dataframe.iloc[-2]
        
        close = latest['close']
        ema = latest.get(f'EMA_{self.ema_period}', 0)
        rsi = latest.get(f'RSI_{self.rsi_period}', 0)
        atr = latest.get(f'ATRr_{self.atr_period}', 0)
        
        # Validate indicator values
        if ema == 0 or rsi == 0 or atr == 0 or pd.isna(ema) or pd.isna(rsi) or pd.isna(atr):
            logger.debug(f"Invalid indicator values for {symbol}")
            return None
        
        # Get symbol info for price precision
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Failed to get symbol info for {symbol}")
            return None
        
        digits = symbol_info.digits
        
        # BUY SIGNAL: Uptrend + RSI oversold (pullback)
        if close > ema and rsi < self.rsi_oversold:
            # Check if this is a fresh signal (RSI just crossed below oversold)
            prev_rsi = previous.get(f'RSI_{self.rsi_period}', 0)
            if prev_rsi >= self.rsi_oversold:  # Fresh cross
                stop_loss = round(close - (atr * self.atr_multiplier), digits)
                take_profit = round(close + (atr * self.atr_multiplier * 2), digits)
                
                signal = TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=close,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    reason=f"Uptrend pullback | Price: {close:.5f} > EMA: {ema:.5f} | RSI: {rsi:.1f}",
                    confidence=0.8
                )
                
                logger.info(f"BUY signal generated for {symbol} | {signal.reason}")
                return signal
        
        # SELL SIGNAL: Downtrend + RSI overbought (pullback)
        elif close < ema and rsi > self.rsi_overbought:
            prev_rsi = previous.get(f'RSI_{self.rsi_period}', 0)
            if prev_rsi <= self.rsi_overbought:  # Fresh cross
                stop_loss = round(close + (atr * self.atr_multiplier), digits)
                take_profit = round(close - (atr * self.atr_multiplier * 2), digits)
                
                signal = TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    price=close,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    reason=f"Downtrend pullback | Price: {close:.5f} < EMA: {ema:.5f} | RSI: {rsi:.1f}",
                    confidence=0.8
                )
                
                logger.info(f"SELL signal generated for {symbol} | {signal.reason}")
                return signal
        
        return None
    
    def should_exit(self, symbol: str, current_price: float, 
                    position_type: str) -> Optional[TradeSignal]:
        """
        Check if position should be exited based on trailing stop.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            position_type: 'buy' or 'sell'
            
        Returns:
            Exit signal or None
        """
        if position_type.lower() == 'buy':
            if symbol in self.trailing_stops:
                if current_price <= self.trailing_stops[symbol]:
                    return TradeSignal(
                        symbol=symbol,
                        signal_type=SignalType.CLOSE_BUY,
                        price=current_price,
                        stop_loss=0,
                        take_profit=0,
                        reason="Trailing stop hit"
                    )
        
        return None
    
    def update_trailing_stop(self, symbol: str, current_price: float, atr: float) -> None:
        """
        Update trailing stop for a symbol.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            atr: Current ATR value
        """
        new_stop = current_price - (atr * self.atr_multiplier)
        
        if symbol not in self.trailing_stops:
            self.trailing_stops[symbol] = new_stop
            logger.debug(f"Initial trailing stop for {symbol}: {new_stop:.5f}")
        else:
            # Only move stop up, never down
            if new_stop > self.trailing_stops[symbol]:
                self.trailing_stops[symbol] = new_stop
                logger.debug(f"Trailing stop updated for {symbol}: {new_stop:.5f}")
    
    def remove_trailing_stop(self, symbol: str) -> None:
        """Remove trailing stop when position is closed."""
        if symbol in self.trailing_stops:
            del self.trailing_stops[symbol]
            logger.debug(f"Trailing stop removed for {symbol}")
    
    def get_parameters(self) -> Dict:
        """Get strategy parameters."""
        return {
            "name": self.name,
            "atr_period": self.atr_period,
            "atr_multiplier": self.atr_multiplier,
            "ema_period": self.ema_period,
            "rsi_period": self.rsi_period,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought
        }