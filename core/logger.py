"""
Sistema de logging unificado com saída para console e arquivo rotativo.

Este módulo implementa um sistema de logging robusto com:
- Logs rotativos para gerenciamento de espaço em disco
- Formatação consistente com timestamps
- Níveis de log configuráveis
- Saída simultânea para console e arquivo
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
import json


class LoggerManager:
    """
    Gerenciador centralizado de logging para o sistema de trading.
    
    Implementa padrão Singleton implícito através de cache de loggers,
    garantindo configuração única e consistente em todo o sistema.
    """
    
    _loggers: dict[str, logging.Logger] = {}
    _configured: bool = False
    
    @classmethod
    def configure(
        cls,
        level: str = "INFO",
        console: bool = True,
        file: bool = True,
        log_dir: str = "logs",
        max_bytes: int = 10485760,  # 10MB
        backup_count: int = 5
    ) -> None:
        """
        Configura o sistema de logging global.
        
        Args:
            level: Nível de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            console: Se True, envia logs para console
            file: Se True, envia logs para arquivo rotativo
            log_dir: Diretório para armazenar arquivos de log
            max_bytes: Tamanho máximo de cada arquivo de log
            backup_count: Número de arquivos de backup a manter
        """
        if cls._configured:
            return
        
        # Cria diretório de logs se não existir
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # Define formato de log com timestamp completo
        log_format = (
            '%(asctime)s | %(levelname)-8s | %(name)-20s | '
            '%(funcName)-15s | %(message)s'
        )
        date_format = '%Y-%m-%d %H:%M:%S'
        
        formatter = logging.Formatter(log_format, datefmt=date_format)
        
        # Configura handler para console
        handlers = []
        
        if console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            handlers.append(console_handler)
        
        # Configura handler para arquivo rotativo
        if file:
            file_handler = RotatingFileHandler(
                filename=log_path / "trading_bot.log",
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        
        # Configura logging raiz
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, level.upper()))
        
        # Remove handlers existentes para evitar duplicação
        root_logger.handlers.clear()
        
        # Adiciona handlers configurados
        for handler in handlers:
            root_logger.addHandler(handler)
        
        cls._configured = True
        
        root_logger.info("=" * 80)
        root_logger.info("Sistema de Logging Inicializado")
        root_logger.info(f"Nível: {level.upper()}")
        root_logger.info(f"Console: {console}")
        root_logger.info(f"Arquivo: {file}")
        root_logger.info(f"Diretório: {log_path.absolute()}")
        root_logger.info("=" * 80)
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        Obtém ou cria um logger com o nome especificado.
        
        Args:
            name: Nome do logger (geralmente __name__ do módulo)
            
        Returns:
            Instância configurada de Logger
        """
        if name not in cls._loggers:
            logger = logging.getLogger(name)
            cls._loggers[name] = logger
        
        return cls._loggers[name]


def get_logger(name: str) -> logging.Logger:
    """
    Função de conveniência para obter logger.
    
    Args:
        name: Nome do logger
        
    Returns:
        Logger configurado
        
    Example:
        >>> from core.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Mensagem de log")
    """
    return LoggerManager.get_logger(name)


def configure_logging_from_config(config_path: str = "config/settings.json") -> None:
    """
    Configura logging a partir de arquivo de configuração JSON.
    
    Args:
        config_path: Caminho para arquivo de configuração
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        log_config = config.get('logging', {})
        
        LoggerManager.configure(
            level=log_config.get('level', 'INFO'),
            console=log_config.get('console', True),
            file=log_config.get('file', True),
            log_dir=log_config.get('log_dir', 'logs'),
            max_bytes=log_config.get('max_bytes', 10485760),
            backup_count=log_config.get('backup_count', 5)
        )
    except Exception as e:
        # Fallback para configuração padrão em caso de erro
        print(f"Erro ao carregar configuração de logging: {e}")
        print("Usando configuração padrão...")
        LoggerManager.configure()
