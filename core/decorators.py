"""
Decoradores para resiliência de rede e padrão Singleton.

Este módulo fornece decoradores fundamentais para garantir a robustez
do sistema de trading, incluindo retry com backoff exponencial e
implementação do padrão Singleton para recursos compartilhados.
"""

import asyncio
import functools
import time
from typing import Callable, TypeVar, Any, Optional
from core.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


def singleton(cls: type[T]) -> type[T]:
    """
    Decorador Singleton para garantir instância única de uma classe.
    
    Este padrão é crítico para recursos compartilhados como conexões
    ao MetaTrader 5, evitando múltiplas conexões simultâneas que
    causariam conflitos e vazamento de recursos.
    
    Args:
        cls: Classe a ser transformada em Singleton
        
    Returns:
        Classe decorada com comportamento Singleton
        
    Example:
        >>> @singleton
        >>> class DatabaseConnection:
        ...     pass
    """
    instances = {}
    
    @functools.wraps(cls)
    def get_instance(*args: Any, **kwargs: Any) -> T:
        if cls not in instances:
            logger.info(f"Criando instância Singleton de {cls.__name__}")
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance


def retry_with_backoff(
    max_attempts: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    exponential: bool = True,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Decorador de retry com backoff exponencial para operações de rede.
    
    Implementa estratégia de retry inteligente com aumento progressivo
    do tempo de espera entre tentativas, essencial para reconexões
    ao broker em cenários de instabilidade de rede.
    
    Args:
        max_attempts: Número máximo de tentativas
        base_delay: Delay inicial entre tentativas (segundos)
        max_delay: Delay máximo permitido (segundos)
        exponential: Se True, usa backoff exponencial; se False, delay fixo
        exceptions: Tupla de exceções que devem disparar retry
        
    Returns:
        Decorador configurado
        
    Example:
        >>> @retry_with_backoff(max_attempts=3, base_delay=1.0)
        >>> def connect_to_broker():
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.debug(
                        f"Tentativa {attempt}/{max_attempts} - {func.__name__}"
                    )
                    result = await func(*args, **kwargs)
                    
                    if attempt > 1:
                        logger.info(
                            f"✓ Sucesso após {attempt} tentativa(s) - {func.__name__}"
                        )
                    
                    return result
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.error(
                            f"✗ Falha definitiva após {max_attempts} tentativas - "
                            f"{func.__name__}: {str(e)}"
                        )
                        raise
                    
                    # Calcula delay com backoff exponencial
                    if exponential:
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    else:
                        delay = base_delay
                    
                    logger.warning(
                        f"⚠ Tentativa {attempt} falhou - {func.__name__}: {str(e)}. "
                        f"Aguardando {delay:.1f}s antes de retry..."
                    )
                    
                    await asyncio.sleep(delay)
            
            # Fallback (não deve chegar aqui, mas por segurança)
            if last_exception:
                raise last_exception
            
            raise RuntimeError(f"Retry logic error in {func.__name__}")
        
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.debug(
                        f"Tentativa {attempt}/{max_attempts} - {func.__name__}"
                    )
                    result = func(*args, **kwargs)
                    
                    if attempt > 1:
                        logger.info(
                            f"✓ Sucesso após {attempt} tentativa(s) - {func.__name__}"
                        )
                    
                    return result
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.error(
                            f"✗ Falha definitiva após {max_attempts} tentativas - "
                            f"{func.__name__}: {str(e)}"
                        )
                        raise
                    
                    # Calcula delay com backoff exponencial
                    if exponential:
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    else:
                        delay = base_delay
                    
                    logger.warning(
                        f"⚠ Tentativa {attempt} falhou - {func.__name__}: {str(e)}. "
                        f"Aguardando {delay:.1f}s antes de retry..."
                    )
                    
                    time.sleep(delay)
            
            # Fallback (não deve chegar aqui, mas por segurança)
            if last_exception:
                raise last_exception
            
            raise RuntimeError(f"Retry logic error in {func.__name__}")
        
        # Retorna wrapper apropriado baseado se a função é async ou não
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def measure_time(func: Callable) -> Callable:
    """
    Decorador para medir tempo de execução de funções.
    
    Útil para monitoramento de performance e identificação
    de gargalos no sistema de trading.
    
    Args:
        func: Função a ser medida
        
    Returns:
        Função decorada com medição de tempo
    """
    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        result = await func(*args, **kwargs)
        elapsed = time.time() - start_time
        
        logger.debug(
            f"⏱ {func.__name__} executado em {elapsed:.4f}s"
        )
        
        return result
    
    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        
        logger.debug(
            f"⏱ {func.__name__} executado em {elapsed:.4f}s"
        )
        
        return result
    
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
