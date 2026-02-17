"""
Cliente MetaTrader 5 com padrão Singleton e reconexão automática.

Este módulo encapsula todas as interações com o MetaTrader 5,
garantindo uma única conexão ativa e reconexão automática em
caso de falhas de rede ou desconexões.
"""

import MetaTrader5 as mt5
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import pandas as pd

from core.decorators import singleton, retry_with_backoff
from core.logger import get_logger

logger = get_logger(__name__)


@singleton
class MT5Client:
    """
    Cliente Singleton para interação com MetaTrader 5.
    
    Gerencia conexão única, validação de estado e operações
    de trading com tratamento robusto de erros.
    
    Attributes:
        login: Número da conta MT5
        password: Senha da conta
        server: Servidor do broker
        timeout: Timeout para operações (ms)
        path: Caminho para terminal MT5 (vazio para auto-detect)
        connected: Status da conexão
    """
    
    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        timeout: int = 60000,
        path: str = ""
    ):
        """
        Inicializa cliente MT5.
        
        Args:
            login: Número da conta
            password: Senha da conta
            server: Nome do servidor
            timeout: Timeout em milissegundos
            path: Caminho para terminal (opcional)
        """
        self.login = login
        self.password = password
        self.server = server
        self.timeout = timeout
        self.path = path
        self.connected = False
        
        logger.info(f"MT5Client inicializado - Login: {login}, Server: {server}")
    
    @retry_with_backoff(
        max_attempts=5,
        base_delay=2.0,
        max_delay=60.0,
        exponential=True,
        exceptions=(Exception,)
    )
    async def connect(self) -> bool:
        """
        Estabelece conexão com MetaTrader 5.
        
        Implementa retry automático com backoff exponencial
        para lidar com falhas temporárias de conexão.
        
        Returns:
            True se conectado com sucesso, False caso contrário
            
        Raises:
            Exception: Após esgotadas todas as tentativas de conexão
        """
        if self.connected and mt5.terminal_info() is not None:
            logger.debug("Já conectado ao MT5")
            return True
        
        # Inicializa terminal MT5
        if self.path:
            initialized = mt5.initialize(
                path=self.path,
                login=self.login,
                password=self.password,
                server=self.server,
                timeout=self.timeout
            )
        else:
            initialized = mt5.initialize(
                login=self.login,
                password=self.password,
                server=self.server,
                timeout=self.timeout
            )
        
        if not initialized:
            error_code = mt5.last_error()
            error_msg = f"Falha ao inicializar MT5: {error_code}"
            logger.error(error_msg)
            raise ConnectionError(error_msg)
        
        # Valida conexão
        terminal_info = mt5.terminal_info()
        account_info = mt5.account_info()
        
        if terminal_info is None or account_info is None:
            error_code = mt5.last_error()
            error_msg = f"Falha ao obter informações do terminal: {error_code}"
            logger.error(error_msg)
            mt5.shutdown()
            raise ConnectionError(error_msg)
        
        self.connected = True
        
        logger.info("=" * 80)
        logger.info("✓ Conexão MT5 Estabelecida com Sucesso")
        logger.info(f"Conta: {account_info.login}")
        logger.info(f"Servidor: {account_info.server}")
        logger.info(f"Broker: {account_info.company}")
        logger.info(f"Saldo: {account_info.balance:.2f} {account_info.currency}")
        logger.info(f"Equity: {account_info.equity:.2f} {account_info.currency}")
        logger.info(f"Terminal: {terminal_info.build} ({terminal_info.name})")
        logger.info("=" * 80)
        
        return True
    
    async def disconnect(self) -> None:
        """
        Desconecta do MetaTrader 5 de forma segura.
        """
        if self.connected:
            mt5.shutdown()
            self.connected = False
            logger.info("Desconectado do MT5")
    
    async def ensure_connected(self) -> bool:
        """
        Garante que a conexão está ativa, reconectando se necessário.
        
        Returns:
            True se conectado, False caso contrário
        """
        if not self.connected or mt5.terminal_info() is None:
            logger.warning("Conexão perdida. Tentando reconectar...")
            return await self.connect()
        return True
    
    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Obtém informações da conta de trading.
        
        Returns:
            Dicionário com informações da conta ou None em caso de erro
        """
        await self.ensure_connected()
        
        account_info = mt5.account_info()
        if account_info is None:
            logger.error(f"Erro ao obter informações da conta: {mt5.last_error()}")
            return None
        
        return {
            'login': account_info.login,
            'server': account_info.server,
            'balance': account_info.balance,
            'equity': account_info.equity,
            'margin': account_info.margin,
            'margin_free': account_info.margin_free,
            'margin_level': account_info.margin_level,
            'profit': account_info.profit,
            'currency': account_info.currency,
            'leverage': account_info.leverage
        }
    
    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Obtém informações detalhadas de um símbolo.
        
        Args:
            symbol: Nome do símbolo (ex: "EURUSD")
            
        Returns:
            Dicionário com informações do símbolo ou None
        """
        await self.ensure_connected()
        
        # Seleciona símbolo no Market Watch
        if not mt5.symbol_select(symbol, True):
            logger.error(f"Falha ao selecionar símbolo {symbol}: {mt5.last_error()}")
            return None
        
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Erro ao obter informações de {symbol}: {mt5.last_error()}")
            return None
        
        return {
            'symbol': symbol_info.name,
            'bid': symbol_info.bid,
            'ask': symbol_info.ask,
            'spread': symbol_info.spread,
            'digits': symbol_info.digits,
            'point': symbol_info.point,
            'trade_tick_value': symbol_info.trade_tick_value,
            'trade_tick_size': symbol_info.trade_tick_size,
            'volume_min': symbol_info.volume_min,
            'volume_max': symbol_info.volume_max,
            'volume_step': symbol_info.volume_step,
            'filling_mode': symbol_info.filling_mode,
            'trade_contract_size': symbol_info.trade_contract_size
        }
    
    async def get_rates(
        self,
        symbol: str,
        timeframe: str,
        count: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Obtém dados históricos de preços.
        
        Args:
            symbol: Nome do símbolo
            timeframe: Timeframe (ex: "H1", "M15", "D1")
            count: Número de barras a obter
            
        Returns:
            DataFrame com OHLCV ou None em caso de erro
        """
        await self.ensure_connected()
        
        # Mapeia string de timeframe para constante MT5
        timeframe_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
            'MN1': mt5.TIMEFRAME_MN1
        }
        
        tf = timeframe_map.get(timeframe)
        if tf is None:
            logger.error(f"Timeframe inválido: {timeframe}")
            return None
        
        # Obtém dados
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        
        if rates is None or len(rates) == 0:
            logger.error(f"Erro ao obter dados de {symbol}: {mt5.last_error()}")
            return None
        
        # Converte para DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        
        logger.debug(f"Obtidos {len(df)} barras de {symbol} {timeframe}")
        
        return df
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Obtém posições abertas.
        
        Args:
            symbol: Filtrar por símbolo específico (opcional)
            
        Returns:
            Lista de dicionários com informações das posições
        """
        await self.ensure_connected()
        
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        if positions is None:
            logger.debug("Nenhuma posição aberta")
            return []
        
        position_list = []
        for pos in positions:
            position_list.append({
                'ticket': pos.ticket,
                'symbol': pos.symbol,
                'type': 'BUY' if pos.type == 0 else 'SELL',
                'volume': pos.volume,
                'price_open': pos.price_open,
                'price_current': pos.price_current,
                'sl': pos.sl,
                'tp': pos.tp,
                'profit': pos.profit,
                'magic': pos.magic,
                'comment': pos.comment
            })
        
        return position_list
    
    async def check_connection(self) -> bool:
        """
        Verifica status da conexão.
        
        Returns:
            True se conectado e operacional
        """
        try:
            terminal_info = mt5.terminal_info()
            return terminal_info is not None and self.connected
        except Exception as e:
            logger.error(f"Erro ao verificar conexão: {e}")
            return False
