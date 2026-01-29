"""
MetaTrader 5 Interface with Singleton pattern and intelligent retry mechanism.
Handles connection, reconnection, and validates trading permissions.
"""

import MetaTrader5 as mt5
import time
from typing import Optional, Callable, Any
from functools import wraps

from config import config
from core.logger import get_logger

logger = get_logger(__name__)


def retry_on_connection_failure(max_attempts: int = 3, delay: int = 5):
    """
    Decorator for automatic retry on transient connection failures.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Delay in seconds between retries
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except MT5ConnectionError as e:
                    last_exception = e
                    
                    # Don't retry on authentication errors
                    if "authentication" in str(e).lower() or "invalid" in str(e).lower():
                        logger.error(f"Authentication error, not retrying: {e}")
                        raise
                    
                    if attempt < max_attempts:
                        logger.warning(f"Connection failed (attempt {attempt}/{max_attempts}), retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} connection attempts failed")
                        raise last_exception
            
            return None
        return wrapper
    return decorator


class MT5ConnectionError(Exception):
    """Custom exception for MT5 connection errors."""
    pass


class MT5Client:
    """
    Singleton MetaTrader 5 client with connection management.
    Ensures only one instance connects to MT5 terminal.
    """
    
    _instance: Optional['MT5Client'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize MT5 client (only once)."""
        if not self._initialized:
            self._connected = False
            self._account_info = None
            MT5Client._initialized = True
    
    @retry_on_connection_failure(max_attempts=3, delay=5)
    def connect(self) -> bool:
        """
        Establish connection to MT5 terminal with automatic retry.
        
        Returns:
            True if connection successful
            
        Raises:
            MT5ConnectionError: If connection fails after all retries
        """
        if self._connected:
            logger.info("Already connected to MT5")
            return True
        
        # Initialize MT5
        mt5_path = config.get('mt5', 'path', default='')
        
        if not mt5.initialize(path=mt5_path if mt5_path else None):
            error_code = mt5.last_error()
            raise MT5ConnectionError(f"MT5 initialization failed: {error_code}")
        
        # Login to account
        login = config.get('mt5', 'login')
        password = config.get('mt5', 'password')
        server = config.get('mt5', 'server')
        timeout = config.get('mt5', 'timeout', default=60000)
        
        if not mt5.login(login=login, password=password, server=server, timeout=timeout):
            error_code = mt5.last_error()
            mt5.shutdown()
            raise MT5ConnectionError(f"MT5 login failed: {error_code}")
        
        # Validate trading permissions
        if not self._validate_trading_enabled():
            mt5.shutdown()
            raise MT5ConnectionError("Algorithmic trading is not enabled in MT5 terminal")
        
        self._connected = True
        self._account_info = mt5.account_info()
        
        logger.info(f"Connected to MT5 | Account: {login} | Server: {server} | Balance: {self._account_info.balance}")
        return True
    
    def _validate_trading_enabled(self) -> bool:
        """
        Check if algorithmic trading is enabled.
        
        Returns:
            True if trading is allowed
        """
        terminal_info = mt5.terminal_info()
        
        if terminal_info is None:
            logger.error("Failed to get terminal info")
            return False
        
        if not terminal_info.trade_allowed:
            logger.error("Algorithmic trading is disabled in terminal settings")
            return False
        
        return True
    
    def disconnect(self) -> None:
        """Disconnect from MT5 terminal."""
        if self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("Disconnected from MT5")
    
    def is_connected(self) -> bool:
        """Check if connected to MT5."""
        if not self._connected:
            return False
        
        # Verify connection is still alive
        try:
            account_info = mt5.account_info()
            return account_info is not None
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            self._connected = False
            return False
    
    def reconnect(self) -> bool:
        """
        Attempt to reconnect to MT5.
        
        Returns:
            True if reconnection successful
        """
        logger.info("Attempting to reconnect to MT5...")
        self.disconnect()
        time.sleep(2)
        
        try:
            return self.connect()
        except MT5ConnectionError as e:
            logger.error(f"Reconnection failed: {e}")
            return False
    
    def get_account_info(self) -> Optional[Any]:
        """
        Get current account information.
        
        Returns:
            Account info object or None
        """
        if not self.is_connected():
            logger.error("Not connected to MT5")
            return None
        
        return mt5.account_info()
    
    def get_terminal_info(self) -> Optional[Any]:
        """
        Get terminal information.
        
        Returns:
            Terminal info object or None
        """
        if not self.is_connected():
            logger.error("Not connected to MT5")
            return None
        
        return mt5.terminal_info()
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()