"""
Interface MT5 com padrão Singleton e retry logic inteligente
Gerencia conexão única e robusta com o MetaTrader 5
"""

import MetaTrader5 as mt5
import time
from typing import Optional, Dict, Any, Callable
from functools import wraps
from datetime import datetime
from core.logger import get_logger


class ConnectionError(Exception):
    """Erro de conexão com MT5"""
    pass


class AuthenticationError(Exception):
    """Erro de autenticação MT5"""
    pass


def retry_on_connection_error(max_attempts: int = 3, delay: int = 5):
    """
    Decorador para retry inteligente em operações MT5
    
    Args:
        max_attempts: Número máximo de tentativas
        delay: Delay entre tentativas em segundos
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger()
            last_error = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except ConnectionError as e:
                    last_error = e
                    error_code = mt5.last_error()
                    
                    # Erros de autenticação não devem ser retriados
                    if error_code[0] in [10004, 10005, 10006]:  # Erros de credenciais
                        logger.error(f"Erro de autenticação: {error_code}. Não será retriado.")
                        raise AuthenticationError(f"Falha de autenticação: {error_code}")
                    
                    # Erros transientes podem ser retriados
                    if error_code[0] in [-10005, -2]:  # Connection lost, timeout
                        if attempt < max_attempts:
                            logger.warning(
                                f"Tentativa {attempt}/{max_attempts} falhou com erro {error_code}. "
                                f"Retentando em {delay}s..."
                            )
                            time.sleep(delay)
                            continue
                    
                    # Outros erros também levantam exceção
                    raise
                except Exception as e:
                    logger.error(f"Erro inesperado em {func.__name__}: {str(e)}", exc_info=True)
                    raise
            
            # Se todas as tentativas falharam
            raise last_error
        
        return wrapper
    return decorator


class MT5Client:
    """
    Cliente Singleton para conexão com MetaTrader 5
    Garante uma única instância de conexão em todo o sistema
    """
    _instance: Optional['MT5Client'] = None
    _connected: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.logger = get_logger()
        self._config: Optional[Dict[str, Any]] = None

    @retry_on_connection_error(max_attempts=3, delay=5)
    def connect(
        self,
        login: int,
        password: str,
        server: str,
        path: str = "",
        timeout: int = 60000
    ) -> bool:
        """
        Conecta ao MetaTrader 5 com retry automático
        
        Args:
            login: Número da conta
            password: Senha da conta
            server: Servidor MT5
            path: Caminho do terminal (opcional)
            timeout: Timeout em milliseconds
            
        Returns:
            True se conectado com sucesso
            
        Raises:
            ConnectionError: Se falha na conexão
            AuthenticationError: Se falha na autenticação
        """
        if self._connected:
            self.logger.info("MT5 já está conectado")
            return True

        # Inicializa o MT5
        if path:
            if not mt5.initialize(path=path, login=login, password=password, server=server, timeout=timeout):
                error = mt5.last_error()
                raise ConnectionError(f"Falha ao inicializar MT5: {error}")
        else:
            if not mt5.initialize(login=login, password=password, server=server, timeout=timeout):
                error = mt5.last_error()
                raise ConnectionError(f"Falha ao inicializar MT5: {error}")

        # Verifica se conectou
        if not mt5.login(login=login, password=password, server=server):
            error = mt5.last_error()
            mt5.shutdown()
            raise AuthenticationError(f"Falha no login MT5: {error}")

        # Verifica informações da conta
        account_info = mt5.account_info()
        if account_info is None:
            mt5.shutdown()
            raise ConnectionError("Não foi possível obter informações da conta")

        # Verifica se trading automático está habilitado
        terminal_info = mt5.terminal_info()
        if terminal_info is None:
            mt5.shutdown()
            raise ConnectionError("Não foi possível obter informações do terminal")

        if not terminal_info.trade_allowed:
            self.logger.warning("AlgoTrading não está habilitado no terminal!")
            self.logger.warning("Por favor, habilite 'Permitir negociação algorítmica' nas opções do MT5")

        self._connected = True
        self._config = {
            'login': login,
            'server': server,
            'account_info': account_info._asdict(),
            'terminal_info': terminal_info._asdict()
        }

        self.logger.info("=" * 80)
        self.logger.info(f"Conectado ao MT5 com sucesso!")
        self.logger.info(f"Conta: {account_info.login} | Servidor: {account_info.server}")
        self.logger.info(f"Saldo: {account_info.balance:.2f} | Equity: {account_info.equity:.2f}")
        self.logger.info(f"Margem Livre: {account_info.margin_free:.2f}")
        self.logger.info(f"AlgoTrading: {'HABILITADO' if terminal_info.trade_allowed else 'DESABILITADO'}")
        self.logger.info("=" * 80)

        return True

    def disconnect(self) -> None:
        """Desconecta do MT5"""
        if self._connected:
            mt5.shutdown()
            self._connected = False
            self.logger.info("Desconectado do MT5")

    def is_connected(self) -> bool:
        """Verifica se está conectado"""
        return self._connected

    def check_connection(self) -> bool:
        """
        Verifica se a conexão ainda está ativa
        
        Returns:
            True se conectado e funcional
        """
        if not self._connected:
            return False

        try:
            account_info = mt5.account_info()
            if account_info is None:
                self._connected = False
                return False
            return True
        except Exception as e:
            self.logger.error(f"Erro ao verificar conexão: {str(e)}")
            self._connected = False
            return False

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Retorna informações da conta
        
        Returns:
            Dicionário com informações da conta ou None
        """
        if not self._connected:
            self.logger.error("Não conectado ao MT5")
            return None

        account_info = mt5.account_info()
        if account_info is None:
            self.logger.error("Falha ao obter informações da conta")
            return None

        return account_info._asdict()

    def get_terminal_info(self) -> Optional[Dict[str, Any]]:
        """
        Retorna informações do terminal
        
        Returns:
            Dicionário com informações do terminal ou None
        """
        if not self._connected:
            self.logger.error("Não conectado ao MT5")
            return None

        terminal_info = mt5.terminal_info()
        if terminal_info is None:
            self.logger.error("Falha ao obter informações do terminal")
            return None

        return terminal_info._asdict()

    def reconnect(self) -> bool:
        """
        Tenta reconectar usando configurações anteriores
        
        Returns:
            True se reconexão bem sucedida
        """
        if self._config is None:
            self.logger.error("Nenhuma configuração anterior disponível para reconexão")
            return False

        self.logger.info("Tentando reconectar ao MT5...")
        self._connected = False

        try:
            return self.connect(
                login=self._config['login'],
                password="",  # Senha não é armazenada por segurança
                server=self._config['server']
            )
        except Exception as e:
            self.logger.error(f"Falha na reconexão: {str(e)}")
            return False

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
