"""
Risk Manager with position sizing, drawdown protection, and circuit breaker.
Critical component that validates all signals before execution.
"""

import MetaTrader5 as mt5
from typing import Optional, Dict
from datetime import datetime, date

from config import config
from core.logger import get_logger, TradingLogger
from strategies.base import TradeSignal

logger = get_logger(__name__)


class RiskManager:
    """
    Manages risk for all trading operations.
    Validates signals, calculates position sizes, and enforces limits.
    """
    
    def __init__(self):
        """Initialize Risk Manager."""
        # Load risk parameters
        self.risk_per_trade_percent = config.get('risk', 'risk_per_trade_percent', default=1.0)
        self.max_daily_drawdown_percent = config.get('risk', 'max_daily_drawdown_percent', default=3.0)
        self.max_spread_points = config.get('risk', 'max_spread_points', default=20)
        self.min_free_margin_percent = config.get('risk', 'min_free_margin_percent', default=20.0)
        self.max_positions = config.get('trading', 'max_positions', default=3)
        
        # Track daily performance
        self.daily_starting_balance: float = 0
        self.daily_peak_balance: float = 0
        self.current_date: date = datetime.now().date()
        self.circuit_breaker_active: bool = False
        
        logger.info(f"RiskManager initialized | Risk per trade: {self.risk_per_trade_percent}% | "
                   f"Max DD: {self.max_daily_drawdown_percent}%")
    
    def validate_signal(self, signal: TradeSignal) -> tuple[bool, str]:
        """
        Validate trade signal against risk parameters.
        
        Args:
            signal: Trade signal to validate
            
        Returns:
            Tuple of (is_valid, rejection_reason)
        """
        # Check circuit breaker
        if self.circuit_breaker_active:
            return False, "Circuit breaker active - daily drawdown limit exceeded"
        
        # Check if entry signal
        if not signal.is_entry_signal():
            return True, ""  # Exit signals don't need validation
        
        # Get account info
        account_info = mt5.account_info()
        if account_info is None:
            return False, "Failed to get account information"
        
        # Check free margin
        free_margin_percent = (account_info.margin_free / account_info.balance) * 100
        if free_margin_percent < self.min_free_margin_percent:
            return False, f"Insufficient free margin: {free_margin_percent:.1f}%"
        
        # Check position count
        positions = mt5.positions_get(symbol=signal.symbol)
        if positions is not None and len(positions) > 0:
            return False, f"Position already exists for {signal.symbol}"
        
        total_positions = mt5.positions_total()
        if total_positions >= self.max_positions:
            return False, f"Maximum positions reached: {total_positions}/{self.max_positions}"
        
        # Check symbol info
        symbol_info = mt5.symbol_info(signal.symbol)
        if symbol_info is None:
            return False, f"Symbol {signal.symbol} not found"
        
        if not symbol_info.visible:
            if not mt5.symbol_select(signal.symbol, True):
                return False, f"Failed to enable {signal.symbol}"
        
        # Check spread
        tick = mt5.symbol_info_tick(signal.symbol)
        if tick is None:
            return False, f"Failed to get tick data for {signal.symbol}"
        
        spread_points = (tick.ask - tick.bid) / symbol_info.point
        if spread_points > self.max_spread_points:
            return False, f"Spread too high: {spread_points:.1f} points"
        
        # Check trading hours (if configured)
        if not self._is_within_trading_hours():
            return False, "Outside trading hours"
        
        return True, ""
    
    def calculate_lot_size(self, signal: TradeSignal) -> float:
        """
        Calculate position size based on risk percentage and stop loss.
        Formula: Lot = (Balance * Risk%) / (SL_Distance_Points * Tick_Value)
        
        Args:
            signal: Trade signal with stop loss
            
        Returns:
            Lot size (volume)
        """
        try:
            # Get account balance
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("Failed to get account info for lot calculation")
                return 0.0
            
            balance = account_info.balance
            risk_amount = balance * (self.risk_per_trade_percent / 100)
            
            # Get symbol info
            symbol_info = mt5.symbol_info(signal.symbol)
            if symbol_info is None:
                logger.error(f"Failed to get symbol info for {signal.symbol}")
                return 0.0
            
            # Calculate stop loss distance in points
            sl_distance = abs(signal.price - signal.stop_loss)
            sl_distance_points = sl_distance / symbol_info.point
            
            if sl_distance_points == 0:
                logger.error(f"Stop loss distance is zero for {signal.symbol}")
                return 0.0
            
            # Get tick value (value of 1 pip movement per lot)
            tick_value = self._get_tick_value(signal.symbol)
            if tick_value == 0:
                logger.error(f"Invalid tick value for {signal.symbol}")
                return 0.0
            
            # Calculate lot size
            lot_size = risk_amount / (sl_distance_points * tick_value)
            
            # Apply symbol constraints
            lot_size = max(symbol_info.volume_min, lot_size)
            lot_size = min(symbol_info.volume_max, lot_size)
            
            # Round to volume step
            lot_size = round(lot_size / symbol_info.volume_step) * symbol_info.volume_step
            
            logger.info(f"Lot calculation for {signal.symbol} | Balance: {balance:.2f} | "
                       f"Risk: {risk_amount:.2f} | SL distance: {sl_distance_points:.1f} points | "
                       f"Tick value: {tick_value:.2f} | Lot: {lot_size:.2f}")
            
            return lot_size
            
        except Exception as e:
            logger.error(f"Error calculating lot size: {e}")
            return 0.0
    
    def _get_tick_value(self, symbol: str) -> float:
        """
        Get tick value for a symbol (value of 1 pip per 1 lot).
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Tick value in account currency
        """
        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return 0.0
            
            # Get tick value directly from MT5
            tick_value = symbol_info.trade_tick_value
            
            # For cross pairs, tick value might need adjustment
            # MT5 usually provides the correct value automatically
            
            return tick_value
            
        except Exception as e:
            logger.error(f"Error getting tick value for {symbol}: {e}")
            return 0.0
    
    def check_daily_drawdown(self) -> bool:
        """
        Check if daily drawdown limit has been exceeded.
        Activates circuit breaker if limit is breached.
        
        Returns:
            True if within limits, False if circuit breaker activated
        """
        # Reset daily stats if new day
        current_date = datetime.now().date()
        if current_date != self.current_date:
            self._reset_daily_stats()
            self.current_date = current_date
        
        # Get current balance
        account_info = mt5.account_info()
        if account_info is None:
            logger.error("Failed to get account info for drawdown check")
            return True  # Allow trading if we can't check (failsafe)
        
        current_balance = account_info.balance
        
        # Initialize if first check of the day
        if self.daily_starting_balance == 0:
            self.daily_starting_balance = current_balance
            self.daily_peak_balance = current_balance
        
        # Update peak balance
        if current_balance > self.daily_peak_balance:
            self.daily_peak_balance = current_balance
        
        # Calculate drawdown from starting balance
        drawdown_from_start = ((self.daily_starting_balance - current_balance) / 
                               self.daily_starting_balance) * 100
        
        # Calculate drawdown from peak
        drawdown_from_peak = ((self.daily_peak_balance - current_balance) / 
                             self.daily_peak_balance) * 100
        
        # Check if either drawdown exceeds limit
        if drawdown_from_start >= self.max_daily_drawdown_percent:
            self.circuit_breaker_active = True
            TradingLogger.log_error(
                f"CIRCUIT BREAKER ACTIVATED | Daily drawdown: {drawdown_from_start:.2f}% | "
                f"Limit: {self.max_daily_drawdown_percent}%"
            )
            return False
        
        if drawdown_from_peak >= self.max_daily_drawdown_percent:
            self.circuit_breaker_active = True
            TradingLogger.log_error(
                f"CIRCUIT BREAKER ACTIVATED | Drawdown from peak: {drawdown_from_peak:.2f}% | "
                f"Limit: {self.max_daily_drawdown_percent}%"
            )
            return False
        
        return True
    
    def _reset_daily_stats(self) -> None:
        """Reset daily tracking statistics."""
        self.daily_starting_balance = 0
        self.daily_peak_balance = 0
        self.circuit_breaker_active = False
        logger.info("Daily risk statistics reset")
    
    def _is_within_trading_hours(self) -> bool:
        """
        Check if current time is within configured trading hours.
        
        Returns:
            True if within trading hours
        """
        now = datetime.now()
        start_hour = config.get('schedule', 'trading_start_hour', default=0)
        end_hour = config.get('schedule', 'trading_end_hour', default=24)
        
        if start_hour <= now.hour < end_hour:
            return True
        
        return False
    
    def get_risk_metrics(self) -> Dict:
        """
        Get current risk metrics for monitoring.
        
        Returns:
            Dictionary with risk metrics
        """
        account_info = mt5.account_info()
        if account_info is None:
            return {}
        
        drawdown = 0
        if self.daily_starting_balance > 0:
            drawdown = ((self.daily_starting_balance - account_info.balance) / 
                       self.daily_starting_balance) * 100
        
        return {
            'daily_starting_balance': self.daily_starting_balance,
            'current_balance': account_info.balance,
            'daily_drawdown_percent': drawdown,
            'circuit_breaker_active': self.circuit_breaker_active,
            'open_positions': mt5.positions_total(),
            'max_positions': self.max_positions,
            'free_margin': account_info.margin_free,
            'margin_level': account_info.margin_level if account_info.margin != 0 else 0
        }