"""
Sistema de Logging Profissional para Trading Bot
Implementa logging rotativo com níveis distintos
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional
from pathlib import Path


class TradingLogger:
    """
    Logger singleton para o sistema de trading
    Implementa logging em arquivo rotativo e console
    """
    _instance: Optional['TradingLogger'] = None
    _logger: Optional[logging.Logger] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._logger is not None:
            return
        
        self._logger = logging.getLogger('TradingBot')
        self._logger.setLevel(logging.DEBUG)
        self._logger.handlers.clear()

    def setup(
        self,
        log_level: str = 'INFO',
        log_to_file: bool = True,
        log_dir: str = 'logs',
        max_bytes: int = 10485760,
        backup_count: int = 5
    ) -> None:
        """
        Configura o sistema de logging
        
        Args:
            log_level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_to_file: Se deve logar em arquivo
            log_dir: Diretório dos logs
            max_bytes: Tamanho máximo do arquivo de log
            backup_count: Número de backups rotativos
        """
        # Formato detalhado
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, log_level))
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

        # File Handler (rotativo)
        if log_to_file:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            
            log_filename = os.path.join(
                log_dir,
                f"trading_bot_{datetime.now().strftime('%Y%m%d')}.log"
            )
            
            file_handler = RotatingFileHandler(
                log_filename,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

        self._logger.info("=" * 80)
        self._logger.info("Sistema de Logging Inicializado")
        self._logger.info("=" * 80)

    def get_logger(self) -> logging.Logger:
        """Retorna a instância do logger"""
        return self._logger

    def log_trade(
        self,
        action: str,
        symbol: str,
        volume: float,
        price: float,
        sl: float = 0.0,
        tp: float = 0.0,
        ticket: int = 0
    ) -> None:
        """
        Log especializado para operações de trading
        
        Args:
            action: Tipo de ação (BUY, SELL, CLOSE)
            symbol: Símbolo negociado
            volume: Volume da operação
            price: Preço de entrada/saída
            sl: Stop Loss
            tp: Take Profit
            ticket: Número do ticket
        """
        msg = f"TRADE | {action} | {symbol} | Vol: {volume:.2f} | Price: {price:.5f}"
        if sl > 0:
            msg += f" | SL: {sl:.5f}"
        if tp > 0:
            msg += f" | TP: {tp:.5f}"
        if ticket > 0:
            msg += f" | Ticket: {ticket}"
        
        self._logger.info(msg)

    def log_signal(self, symbol: str, signal: str, reason: str) -> None:
        """
        Log especializado para sinais de estratégia
        
        Args:
            symbol: Símbolo
            signal: Tipo de sinal (BUY, SELL, HOLD)
            reason: Razão do sinal
        """
        self._logger.info(f"SIGNAL | {symbol} | {signal} | {reason}")

    def log_risk_event(self, event_type: str, details: str) -> None:
        """
        Log especializado para eventos de gestão de risco
        
        Args:
            event_type: Tipo de evento
            details: Detalhes do evento
        """
        self._logger.warning(f"RISK | {event_type} | {details}")

    def log_error(self, error_type: str, error_msg: str, exception: Optional[Exception] = None) -> None:
        """
        Log especializado para erros
        
        Args:
            error_type: Tipo de erro
            error_msg: Mensagem de erro
            exception: Exceção capturada (opcional)
        """
        msg = f"ERROR | {error_type} | {error_msg}"
        if exception:
            self._logger.error(msg, exc_info=True)
        else:
            self._logger.error(msg)


# Instância global
logger_instance = TradingLogger()

def get_logger() -> logging.Logger:
    """Função helper para obter o logger"""
    return logger_instance.get_logger()
