"""
Módulo core - Infraestrutura fundamental do sistema.

Este módulo contém:
- Decoradores (Singleton, Retry)
- Sistema de logging
- Cliente MT5 com reconexão automática
- Cliente Telegram (Novo)
"""

from core.decorators import singleton, retry_with_backoff, measure_time
from core.logger import get_logger, configure_logging_from_config, LoggerManager
from core.mt5_client import MT5Client
from core.telegram import TelegramBot

__all__ = [
    # Decorators
    'singleton',
    'retry_with_backoff',
    'measure_time',
    
    # Logging
    'get_logger',
    'configure_logging_from_config',
    'LoggerManager',
    
    # MT5
    'MT5Client',
    
    # Telegram
    'TelegramBot'
]

__version__ = '1.1.0'