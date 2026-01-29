"""
Unit tests for Risk Manager.
Example of how to structure tests for the trading bot.
"""

import unittest
from unittest.mock import Mock, patch
import MetaTrader5 as mt5

from risk.risk_manager import RiskManager
from strategies.base import TradeSignal, SignalType


class TestRiskManager(unittest.TestCase):
    """Test cases for RiskManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.risk_manager = RiskManager()
    
    @patch('MetaTrader5.account_info')
    @patch('MetaTrader5.symbol_info')
    @patch('MetaTrader5.symbol_info_tick')
    @patch('MetaTrader5.positions_get')
    @patch('MetaTrader5.positions_total')
    def test_validate_signal_success(self, mock_positions_total, mock_positions_get, 
                                     mock_tick, mock_symbol_info, mock_account_info):
        """Test successful signal validation."""
        # Mock account info
        mock_account = Mock()
        mock_account.balance = 10000
        mock_account.margin_free = 9000
        mock_account_info.return_value = mock_account
        
        # Mock symbol info
        mock_symbol = Mock()
        mock_symbol.visible = True
        mock_symbol.point = 0.00001
        mock_symbol_info.return_value = mock_symbol
        
        # Mock tick
        mock_tick_data = Mock()
        mock_tick_data.bid = 1.08450
        mock_tick_data.ask = 1.08452
        mock_tick.return_value = mock_tick_data
        
        # Mock positions
        mock_positions_get.return_value = None
        mock_positions_total.return_value = 0
        
        # Create signal
        signal = TradeSignal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            price=1.08450,
            stop_loss=1.08350,
            take_profit=1.08650,
            reason="Test signal"
        )
        
        # Validate
        is_valid, reason = self.risk_manager.validate_signal(signal)
        
        # Assert
        self.assertTrue(is_valid)
        self.assertEqual(reason, "")
    
    @patch('MetaTrader5.account_info')
    def test_validate_signal_circuit_breaker(self, mock_account_info):
        """Test signal rejection when circuit breaker is active."""
        # Activate circuit breaker
        self.risk_manager.circuit_breaker_active = True
        
        signal = TradeSignal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            price=1.08450,
            stop_loss=1.08350,
            take_profit=1.08650
        )
        
        is_valid, reason = self.risk_manager.validate_signal(signal)
        
        self.assertFalse(is_valid)
        self.assertIn("circuit breaker", reason.lower())
    
    @patch('MetaTrader5.account_info')
    @patch('MetaTrader5.symbol_info')
    def test_calculate_lot_size(self, mock_symbol_info, mock_account_info):
        """Test lot size calculation."""
        # Mock account
        mock_account = Mock()
        mock_account.balance = 10000
        mock_account_info.return_value = mock_account
        
        # Mock symbol
        mock_symbol = Mock()
        mock_symbol.point = 0.00001
        mock_symbol.volume_min = 0.01
        mock_symbol.volume_max = 100.0
        mock_symbol.volume_step = 0.01
        mock_symbol.trade_tick_value = 1.0
        mock_symbol_info.return_value = mock_symbol
        
        # Create signal
        signal = TradeSignal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            price=1.08450,
            stop_loss=1.08350,  # 100 points
            take_profit=1.08650
        )
        
        # Calculate lot
        lot = self.risk_manager.calculate_lot_size(signal)
        
        # Assert
        self.assertGreater(lot, 0)
        self.assertGreaterEqual(lot, mock_symbol.volume_min)
        self.assertLessEqual(lot, mock_symbol.volume_max)


if __name__ == '__main__':
    unittest.main()