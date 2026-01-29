"""
Notification system for sending alerts via Telegram.
Provides real-time updates on trade execution and errors.
"""

import requests
from typing import Optional
from datetime import datetime

from config import config
from core.logger import get_logger

logger = get_logger(__name__)


class TelegramNotifier:
    """
    Sends notifications to Telegram bot.
    Can be extended to support other notification channels.
    """
    
    def __init__(self):
        """Initialize Telegram notifier."""
        self.enabled = config.get('notifications', 'telegram_enabled', default=False)
        self.token = config.get('notifications', 'telegram_token', default='')
        self.chat_id = config.get('notifications', 'telegram_chat_id', default='')
        
        if self.enabled and (not self.token or not self.chat_id):
            logger.warning("Telegram notifications enabled but credentials not configured")
            self.enabled = False
        
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        
        if self.enabled:
            logger.info("Telegram notifications enabled")
    
    def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Send message to Telegram.
        
        Args:
            message: Message text
            parse_mode: Parse mode (HTML or Markdown)
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    def notify_trade_opened(self, symbol: str, action: str, lot: float, 
                           price: float, sl: float, tp: float) -> None:
        """
        Send notification for opened trade.
        
        Args:
            symbol: Trading symbol
            action: BUY or SELL
            lot: Position size
            price: Entry price
            sl: Stop loss
            tp: Take profit
        """
        emoji = "🟢" if action == "BUY" else "🔴"
        
        message = (
            f"{emoji} <b>Trade Opened</b>\n\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Action:</b> {action}\n"
            f"<b>Lot:</b> {lot:.2f}\n"
            f"<b>Price:</b> {price:.5f}\n"
            f"<b>SL:</b> {sl:.5f}\n"
            f"<b>TP:</b> {tp:.5f}\n"
            f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        self.send_message(message)
    
    def notify_trade_closed(self, symbol: str, profit: float, reason: str = "") -> None:
        """
        Send notification for closed trade.
        
        Args:
            symbol: Trading symbol
            profit: Profit/loss amount
            reason: Reason for closure
        """
        emoji = "✅" if profit >= 0 else "❌"
        
        message = (
            f"{emoji} <b>Trade Closed</b>\n\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Profit:</b> ${profit:.2f}\n"
        )
        
        if reason:
            message += f"<b>Reason:</b> {reason}\n"
        
        message += f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        self.send_message(message)
    
    def notify_circuit_breaker(self, drawdown_percent: float) -> None:
        """
        Send critical alert for circuit breaker activation.
        
        Args:
            drawdown_percent: Current drawdown percentage
        """
        message = (
            f"🚨 <b>CIRCUIT BREAKER ACTIVATED</b> 🚨\n\n"
            f"<b>Daily Drawdown:</b> {drawdown_percent:.2f}%\n"
            f"<b>Trading suspended</b>\n"
            f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        self.send_message(message)
    
    def notify_error(self, error_message: str) -> None:
        """
        Send error notification.
        
        Args:
            error_message: Error description
        """
        message = (
            f"⚠️ <b>Error Occurred</b>\n\n"
            f"{error_message}\n"
            f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        self.send_message(message)
    
    def notify_bot_started(self) -> None:
        """Send notification when bot starts."""
        message = (
            f"🤖 <b>Trading Bot Started</b>\n\n"
            f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        self.send_message(message)
    
    def notify_bot_stopped(self) -> None:
        """Send notification when bot stops."""
        message = (
            f"🛑 <b>Trading Bot Stopped</b>\n\n"
            f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        self.send_message(message)


# Global notifier instance
notifier = TelegramNotifier()