"""
Market Data Handler with circular buffer and technical indicators.
Efficiently manages multi-symbol price data and calculates indicators.
"""

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from collections import deque

from config import config
from core.logger import get_logger
from core.mt5_interface import MT5Client

logger = get_logger(__name__)


class MarketDataHandler:
    """
    Manages market data collection and indicator calculation.
    Uses circular buffers for memory efficiency.
    """
    
    def __init__(self, buffer_size: int = 1000):
        """
        Initialize market data handler.
        
        Args:
            buffer_size: Maximum number of candles to store per symbol
        """
        self.buffer_size = buffer_size
        self.mt5_client = MT5Client()
        
        # Data buffers: {symbol: DataFrame}
        self.data_buffers: Dict[str, pd.DataFrame] = {}
        
        # Symbols to track
        self.symbols = config.get('trading', 'symbols', default=[])
        self.timeframe = self._parse_timeframe(config.get('trading', 'timeframe', default='M15'))
        
        # Indicator parameters
        self.atr_period = config.get('strategy', 'atr_period', default=14)
        self.ema_period = config.get('strategy', 'ema_period', default=200)
        self.rsi_period = config.get('strategy', 'rsi_period', default=14)
        
        logger.info(f"MarketDataHandler initialized | Symbols: {self.symbols} | Timeframe: {self.timeframe}")
    
    def _parse_timeframe(self, timeframe_str: str) -> int:
        """
        Parse timeframe string to MT5 constant.
        
        Args:
            timeframe_str: Timeframe string (e.g., 'M15', 'H1', 'D1')
            
        Returns:
            MT5 timeframe constant
        """
        timeframe_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
        }
        
        return timeframe_map.get(timeframe_str, mt5.TIMEFRAME_M15)
    
    def initialize_buffers(self) -> bool:
        """
        Initialize data buffers for all symbols.
        
        Returns:
            True if all buffers initialized successfully
        """
        success = True
        
        for symbol in self.symbols:
            if not self._load_initial_data(symbol):
                logger.error(f"Failed to initialize buffer for {symbol}")
                success = False
        
        return success
    
    def _load_initial_data(self, symbol: str) -> bool:
        """
        Load initial historical data for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            True if data loaded successfully
        """
        try:
            # Get historical data
            rates = mt5.copy_rates_from_pos(symbol, self.timeframe, 0, self.buffer_size)
            
            if rates is None or len(rates) == 0:
                logger.error(f"No data received for {symbol}")
                return False
            
            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            # Calculate indicators
            df = self._calculate_indicators(df)
            
            self.data_buffers[symbol] = df
            logger.info(f"Loaded {len(df)} candles for {symbol}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading data for {symbol}: {e}")
            return False
    
    def update_data(self, symbol: Optional[str] = None) -> bool:
        """
        Update market data for symbols (incremental update).
        
        Args:
            symbol: Specific symbol to update, or None for all
            
        Returns:
            True if update successful
        """
        symbols_to_update = [symbol] if symbol else self.symbols
        success = True
        
        for sym in symbols_to_update:
            if sym not in self.data_buffers:
                logger.warning(f"Buffer not initialized for {sym}, loading initial data")
                if not self._load_initial_data(sym):
                    success = False
                    continue
            
            try:
                # Get the latest candle
                rates = mt5.copy_rates_from_pos(sym, self.timeframe, 0, 1)
                
                if rates is None or len(rates) == 0:
                    logger.warning(f"No new data for {sym}")
                    continue
                
                # Convert to DataFrame
                new_data = pd.DataFrame(rates)
                new_data['time'] = pd.to_datetime(new_data['time'], unit='s')
                new_data.set_index('time', inplace=True)
                
                # Check if this is truly new data
                last_time = self.data_buffers[sym].index[-1]
                new_time = new_data.index[0]
                
                if new_time > last_time:
                    # Append new candle
                    self.data_buffers[sym] = pd.concat([self.data_buffers[sym], new_data])
                    
                    # Maintain buffer size
                    if len(self.data_buffers[sym]) > self.buffer_size:
                        self.data_buffers[sym] = self.data_buffers[sym].iloc[-self.buffer_size:]
                    
                    # Recalculate indicators (only for recent data)
                    self.data_buffers[sym] = self._calculate_indicators(
                        self.data_buffers[sym],
                        incremental=True
                    )
                    
                    logger.debug(f"Updated data for {sym} | New candle: {new_time}")
                else:
                    # Update current candle (in-progress)
                    self.data_buffers[sym].iloc[-1] = new_data.iloc[0]
                    
            except Exception as e:
                logger.error(f"Error updating data for {sym}: {e}")
                success = False
        
        return success
    
    def _calculate_indicators(self, df: pd.DataFrame, incremental: bool = False) -> pd.DataFrame:
        """
        Calculate technical indicators using pandas_ta.
        
        Args:
            df: Price DataFrame
            incremental: If True, only recalculate last few rows
            
        Returns:
            DataFrame with indicators added
        """
        try:
            if incremental and len(df) > 50:
                # For incremental updates, recalculate only last 50 rows
                # This is a compromise between accuracy and performance
                calc_df = df.iloc[-50:].copy()
            else:
                calc_df = df.copy()
            
            # ATR (Average True Range)
            calc_df.ta.atr(length=self.atr_period, append=True)
            
            # EMA (Exponential Moving Average)
            calc_df.ta.ema(length=self.ema_period, append=True)
            
            # RSI (Relative Strength Index)
            calc_df.ta.rsi(length=self.rsi_period, append=True)
            
            if incremental and len(df) > 50:
                # Update only the calculated portion
                indicator_cols = [col for col in calc_df.columns if col not in df.columns or col.startswith('ATR') or col.startswith('EMA') or col.startswith('RSI')]
                df.loc[calc_df.index, indicator_cols] = calc_df[indicator_cols]
                return df
            else:
                return calc_df
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return df
    
    def get_current_data(self, symbol: str, periods: int = 100) -> Optional[pd.DataFrame]:
        """
        Get recent data for a symbol.
        
        Args:
            symbol: Trading symbol
            periods: Number of recent periods to return
            
        Returns:
            DataFrame with recent data or None
        """
        if symbol not in self.data_buffers:
            logger.warning(f"No data available for {symbol}")
            return None
        
        return self.data_buffers[symbol].tail(periods).copy()
    
    def get_latest_values(self, symbol: str) -> Optional[Dict]:
        """
        Get latest price and indicator values.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with latest values or None
        """
        if symbol not in self.data_buffers or len(self.data_buffers[symbol]) == 0:
            return None
        
        latest = self.data_buffers[symbol].iloc[-1]
        
        return {
            'time': latest.name,
            'open': latest['open'],
            'high': latest['high'],
            'low': latest['low'],
            'close': latest['close'],
            'volume': latest['tick_volume'],
            'atr': latest.get(f'ATRr_{self.atr_period}', 0),
            'ema': latest.get(f'EMA_{self.ema_period}', 0),
            'rsi': latest.get(f'RSI_{self.rsi_period}', 0)
        }
    
    def get_tick(self, symbol: str) -> Optional[Dict]:
        """
        Get current tick data for symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with tick data or None
        """
        try:
            tick = mt5.symbol_info_tick(symbol)
            
            if tick is None:
                return None
            
            return {
                'time': datetime.fromtimestamp(tick.time),
                'bid': tick.bid,
                'ask': tick.ask,
                'last': tick.last,
                'volume': tick.volume
            }
            
        except Exception as e:
            logger.error(f"Error getting tick for {symbol}: {e}")
            return None