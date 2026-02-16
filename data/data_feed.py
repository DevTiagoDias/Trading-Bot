"""
Market Data Handler com Buffer Circular
Gerencia dados históricos e indicadores técnicos de múltiplos símbolos
"""

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
from collections import deque
from core.logger import get_logger


class MarketDataHandler:
    """
    Gerenciador de dados de mercado com buffer circular
    Mantém histórico rolante de dados para múltiplos símbolos
    """

    def __init__(
        self,
        symbols: List[str],
        timeframe: str = 'M15',
        buffer_size: int = 1000
    ):
        """
        Inicializa o handler de dados
        
        Args:
            symbols: Lista de símbolos a monitorar
            timeframe: Timeframe dos dados (M1, M5, M15, H1, etc)
            buffer_size: Tamanho do buffer circular
        """
        self.logger = get_logger()
        self.symbols = symbols
        self.timeframe = self._parse_timeframe(timeframe)
        self.buffer_size = buffer_size
        
        # Buffer circular para cada símbolo
        self.data_buffers: Dict[str, pd.DataFrame] = {}
        self.last_update: Dict[str, datetime] = {}
        
        # Cache de indicadores
        self.indicators_cache: Dict[str, Dict[str, pd.Series]] = {}
        
        self.logger.info(f"MarketDataHandler inicializado para {len(symbols)} símbolos")

    def _parse_timeframe(self, timeframe: str) -> int:
        """
        Converte string de timeframe para constante MT5
        
        Args:
            timeframe: String do timeframe (M1, M5, M15, H1, H4, D1)
            
        Returns:
            Constante MT5 do timeframe
        """
        timeframes = {
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
        
        tf = timeframes.get(timeframe.upper())
        if tf is None:
            self.logger.warning(f"Timeframe {timeframe} inválido, usando M15")
            return mt5.TIMEFRAME_M15
        
        return tf

    def initialize_buffers(self) -> bool:
        """
        Inicializa os buffers com dados históricos
        
        Returns:
            True se inicialização bem sucedida
        """
        self.logger.info("Inicializando buffers de dados históricos...")
        
        success_count = 0
        for symbol in self.symbols:
            if self._load_historical_data(symbol):
                success_count += 1
        
        self.logger.info(
            f"Buffers inicializados: {success_count}/{len(self.symbols)} símbolos"
        )
        
        return success_count == len(self.symbols)

    def _load_historical_data(self, symbol: str) -> bool:
        """
        Carrega dados históricos para um símbolo
        
        Args:
            symbol: Símbolo a carregar
            
        Returns:
            True se carregamento bem sucedido
        """
        try:
            # Tenta obter dados históricos
            rates = mt5.copy_rates_from_pos(symbol, self.timeframe, 0, self.buffer_size)
            
            if rates is None or len(rates) == 0:
                self.logger.error(f"Falha ao obter dados para {symbol}: {mt5.last_error()}")
                return False
            
            # Converte para DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            # Renomeia colunas para padrão
            df.columns = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
            
            self.data_buffers[symbol] = df
            self.last_update[symbol] = datetime.now()
            
            self.logger.info(
                f"Carregados {len(df)} candles para {symbol} "
                f"({df.index[0]} até {df.index[-1]})"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao carregar dados de {symbol}: {str(e)}", exc_info=True)
            return False

    def update_data(self, symbol: Optional[str] = None) -> bool:
        """
        Atualiza dados com os candles mais recentes
        
        Args:
            symbol: Símbolo específico ou None para todos
            
        Returns:
            True se atualização bem sucedida
        """
        symbols_to_update = [symbol] if symbol else self.symbols
        success = True
        
        for sym in symbols_to_update:
            if sym not in self.data_buffers:
                self.logger.warning(f"Buffer não inicializado para {sym}")
                continue
            
            try:
                # Obtém apenas os últimos candles
                rates = mt5.copy_rates_from_pos(sym, self.timeframe, 0, 10)
                
                if rates is None or len(rates) == 0:
                    self.logger.warning(f"Sem novos dados para {sym}")
                    success = False
                    continue
                
                # Converte para DataFrame
                new_df = pd.DataFrame(rates)
                new_df['time'] = pd.to_datetime(new_df['time'], unit='s')
                new_df.set_index('time', inplace=True)
                new_df.columns = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
                
                # Obtém último timestamp do buffer
                last_time = self.data_buffers[sym].index[-1]
                
                # Filtra apenas candles novos
                new_candles = new_df[new_df.index > last_time]
                
                if len(new_candles) > 0:
                    # Adiciona novos candles ao buffer
                    self.data_buffers[sym] = pd.concat([self.data_buffers[sym], new_candles])
                    
                    # Mantém apenas últimos buffer_size candles
                    if len(self.data_buffers[sym]) > self.buffer_size:
                        self.data_buffers[sym] = self.data_buffers[sym].iloc[-self.buffer_size:]
                    
                    self.last_update[sym] = datetime.now()
                    
                    # Limpa cache de indicadores ao adicionar novos dados
                    if sym in self.indicators_cache:
                        self.indicators_cache[sym].clear()
                    
                    self.logger.debug(f"Adicionados {len(new_candles)} novos candles para {sym}")
                
            except Exception as e:
                self.logger.error(f"Erro ao atualizar {sym}: {str(e)}", exc_info=True)
                success = False
        
        return success

    def get_data(self, symbol: str, bars: Optional[int] = None) -> Optional[pd.DataFrame]:
        """
        Retorna dados do buffer para um símbolo
        
        Args:
            symbol: Símbolo
            bars: Número de barras (None para todas)
            
        Returns:
            DataFrame com os dados ou None
        """
        if symbol not in self.data_buffers:
            self.logger.error(f"Buffer não existe para {symbol}")
            return None
        
        df = self.data_buffers[symbol]
        
        if bars is not None:
            df = df.iloc[-bars:]
        
        return df.copy()

    def calculate_indicators(
        self,
        symbol: str,
        indicators: Dict[str, Dict[str, any]]
    ) -> Optional[pd.DataFrame]:
        """
        Calcula indicadores técnicos usando pandas_ta
        
        Args:
            symbol: Símbolo
            indicators: Dicionário com indicadores e parâmetros
                       Ex: {'ema': {'length': 200}, 'rsi': {'length': 14}}
        
        Returns:
            DataFrame com dados e indicadores
        """
        df = self.get_data(symbol)
        if df is None or len(df) == 0:
            return None
        
        try:
            # Calcula cada indicador
            for indicator_name, params in indicators.items():
                if indicator_name.lower() == 'ema':
                    length = params.get('length', 200)
                    df[f'ema_{length}'] = ta.ema(df['close'], length=length)
                
                elif indicator_name.lower() == 'rsi':
                    length = params.get('length', 14)
                    df['rsi'] = ta.rsi(df['close'], length=length)
                
                elif indicator_name.lower() == 'atr':
                    length = params.get('length', 14)
                    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=length)
                
                elif indicator_name.lower() == 'macd':
                    fast = params.get('fast', 12)
                    slow = params.get('slow', 26)
                    signal = params.get('signal', 9)
                    macd = ta.macd(df['close'], fast=fast, slow=slow, signal=signal)
                    df = pd.concat([df, macd], axis=1)
                
                elif indicator_name.lower() == 'bbands':
                    length = params.get('length', 20)
                    std = params.get('std', 2)
                    bbands = ta.bbands(df['close'], length=length, std=std)
                    df = pd.concat([df, bbands], axis=1)
                
                elif indicator_name.lower() == 'sma':
                    length = params.get('length', 50)
                    df[f'sma_{length}'] = ta.sma(df['close'], length=length)
            
            return df
            
        except Exception as e:
            self.logger.error(
                f"Erro ao calcular indicadores para {symbol}: {str(e)}",
                exc_info=True
            )
            return None

    def get_latest_price(self, symbol: str) -> Optional[Tuple[float, float]]:
        """
        Obtém último preço bid/ask
        
        Args:
            symbol: Símbolo
            
        Returns:
            Tupla (bid, ask) ou None
        """
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            return (tick.bid, tick.ask)
            
        except Exception as e:
            self.logger.error(f"Erro ao obter preço de {symbol}: {str(e)}")
            return None

    def get_buffer_info(self) -> Dict[str, Dict[str, any]]:
        """
        Retorna informações sobre os buffers
        
        Returns:
            Dicionário com informações dos buffers
        """
        info = {}
        for symbol, df in self.data_buffers.items():
            info[symbol] = {
                'size': len(df),
                'first_candle': df.index[0] if len(df) > 0 else None,
                'last_candle': df.index[-1] if len(df) > 0 else None,
                'last_update': self.last_update.get(symbol)
            }
        
        return info
