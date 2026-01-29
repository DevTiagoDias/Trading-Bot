"""
Order Manager for trade execution with intelligent error handling.
Handles order placement, modification, and closure with retry logic.
"""

import MetaTrader5 as mt5
import time
from typing import Optional, Dict, List
from enum import Enum

from config import config
from core.logger import get_logger, TradingLogger
from strategies.base import TradeSignal, SignalType

logger = get_logger(__name__)


class OrderResult(Enum):
    """Order execution result types."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    REQUOTE = "REQUOTE"
    INVALID = "INVALID"


class OrderManager:
    """
    Manages order execution with automatic filling type detection
    and intelligent error handling.
    """
    
    def __init__(self):
        """Initialize Order Manager."""
        self.magic_number = config.get('trading', 'magic_number', default=234000)
        self.max_slippage = 10  # Points
        self.max_requote_retries = 3
        
        logger.info(f"OrderManager initialized | Magic: {self.magic_number}")
    
    def execute_order(self, signal: TradeSignal, lot_size: float) -> tuple[OrderResult, Optional[int], str]:
        """
        Execute trade order with automatic filling type selection.
        
        Args:
            signal: Trade signal to execute
            lot_size: Position size
            
        Returns:
            Tuple of (result, order_id, message)
        """
        if lot_size <= 0:
            return OrderResult.INVALID, None, "Invalid lot size"
        
        # Get symbol info
        symbol_info = mt5.symbol_info(signal.symbol)
        if symbol_info is None:
            return OrderResult.FAILED, None, f"Symbol {signal.symbol} not found"
        
        # Determine order type
        if signal.signal_type == SignalType.BUY:
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(signal.symbol).ask
        elif signal.signal_type == SignalType.SELL:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(signal.symbol).bid
        else:
            return OrderResult.INVALID, None, f"Invalid signal type: {signal.signal_type}"
        
        # Determine filling type based on symbol properties
        filling_type = self._get_filling_type(symbol_info)
        
        # Prepare request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": signal.symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": signal.stop_loss,
            "tp": signal.take_profit,
            "deviation": self.max_slippage,
            "magic": self.magic_number,
            "comment": f"{signal.reason[:30]}",  # MT5 comment limit
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_type,
        }
        
        # Execute with retry on requote
        for attempt in range(1, self.max_requote_retries + 1):
            result = mt5.order_send(request)
            
            if result is None:
                error = mt5.last_error()
                return OrderResult.FAILED, None, f"Order send failed: {error}"
            
            # Handle result codes
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                TradingLogger.log_trade(
                    action=signal.signal_type.value,
                    symbol=signal.symbol,
                    lot=lot_size,
                    price=result.price,
                    sl=signal.stop_loss,
                    tp=signal.take_profit,
                    reason=signal.reason,
                    order_id=result.order
                )
                return OrderResult.SUCCESS, result.order, "Order executed successfully"
            
            elif result.retcode == mt5.TRADE_RETCODE_REQUOTE:
                if attempt < self.max_requote_retries:
                    logger.warning(f"Requote received (attempt {attempt}), retrying with new price...")
                    time.sleep(0.5)
                    # Update price for retry
                    if order_type == mt5.ORDER_TYPE_BUY:
                        request["price"] = mt5.symbol_info_tick(signal.symbol).ask
                    else:
                        request["price"] = mt5.symbol_info_tick(signal.symbol).bid
                    continue
                else:
                    return OrderResult.REQUOTE, None, "Max requote retries exceeded"
            
            elif result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
                # Try alternative filling type
                if attempt == 1:
                    logger.warning("Invalid fill type, trying alternative...")
                    request["type_filling"] = self._get_alternative_filling_type(filling_type)
                    continue
                else:
                    return OrderResult.INVALID, None, "Invalid filling type"
            
            elif result.retcode == mt5.TRADE_RETCODE_NO_MONEY:
                return OrderResult.FAILED, None, "Insufficient funds"
            
            elif result.retcode == mt5.TRADE_RETCODE_MARKET_CLOSED:
                return OrderResult.FAILED, None, "Market closed"
            
            elif result.retcode == mt5.TRADE_RETCODE_INVALID_PRICE:
                return OrderResult.FAILED, None, "Invalid price"
            
            else:
                return OrderResult.FAILED, None, f"Order failed: {result.retcode} - {result.comment}"
        
        return OrderResult.FAILED, None, "Order execution failed"
    
    def _get_filling_type(self, symbol_info) -> int:
        """
        Determine appropriate filling type for symbol.
        
        Args:
            symbol_info: MT5 symbol info object
            
        Returns:
            MT5 filling type constant
        """
        filling_mode = symbol_info.filling_mode
        
        # Check supported filling modes (bitwise flags)
        if filling_mode & 1:  # FOK supported
            return mt5.ORDER_FILLING_FOK
        elif filling_mode & 2:  # IOC supported
            return mt5.ORDER_FILLING_IOC
        else:  # Return (default)
            return mt5.ORDER_FILLING_RETURN
    
    def _get_alternative_filling_type(self, current_type: int) -> int:
        """
        Get alternative filling type.
        
        Args:
            current_type: Current filling type
            
        Returns:
            Alternative filling type
        """
        if current_type == mt5.ORDER_FILLING_FOK:
            return mt5.ORDER_FILLING_IOC
        elif current_type == mt5.ORDER_FILLING_IOC:
            return mt5.ORDER_FILLING_RETURN
        else:
            return mt5.ORDER_FILLING_FOK
    
    def close_position(self, position) -> tuple[bool, str]:
        """
        Close an open position.
        
        Args:
            position: MT5 position object
            
        Returns:
            Tuple of (success, message)
        """
        symbol_info = mt5.symbol_info(position.symbol)
        if symbol_info is None:
            return False, f"Symbol {position.symbol} not found"
        
        # Determine close parameters
        if position.type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(position.symbol).bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(position.symbol).ask
        
        filling_type = self._get_filling_type(symbol_info)
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "deviation": self.max_slippage,
            "magic": self.magic_number,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_type,
        }
        
        result = mt5.order_send(request)
        
        if result is None:
            error = mt5.last_error()
            return False, f"Close order failed: {error}"
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            profit = result.profit if hasattr(result, 'profit') else position.profit
            logger.info(f"Position closed | {position.symbol} | Ticket: {position.ticket} | "
                       f"Profit: {profit:.2f}")
            return True, "Position closed successfully"
        else:
            return False, f"Close failed: {result.retcode} - {result.comment}"
    
    def close_all_positions(self, symbol: Optional[str] = None) -> int:
        """
        Close all open positions (optionally filtered by symbol).
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            Number of positions closed
        """
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        if positions is None or len(positions) == 0:
            logger.info("No positions to close")
            return 0
        
        closed_count = 0
        
        for position in positions:
            success, message = self.close_position(position)
            if success:
                closed_count += 1
            else:
                logger.error(f"Failed to close position {position.ticket}: {message}")
            
            time.sleep(0.5)  # Small delay between closes
        
        logger.info(f"Closed {closed_count}/{len(positions)} positions")
        return closed_count
    
    def modify_position(self, ticket: int, new_sl: float, new_tp: float) -> tuple[bool, str]:
        """
        Modify stop loss and take profit of existing position.
        
        Args:
            ticket: Position ticket
            new_sl: New stop loss
            new_tp: New take profit
            
        Returns:
            Tuple of (success, message)
        """
        position = mt5.positions_get(ticket=ticket)
        if position is None or len(position) == 0:
            return False, f"Position {ticket} not found"
        
        position = position[0]
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": new_tp,
        }
        
        result = mt5.order_send(request)
        
        if result is None:
            error = mt5.last_error()
            return False, f"Modify failed: {error}"
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Position modified | Ticket: {ticket} | SL: {new_sl:.5f} | TP: {new_tp:.5f}")
            return True, "Position modified successfully"
        else:
            return False, f"Modify failed: {result.retcode} - {result.comment}"
    
    def get_open_positions(self, symbol: Optional[str] = None) -> List:
        """
        Get list of open positions.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of positions
        """
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        return list(positions) if positions is not None else []