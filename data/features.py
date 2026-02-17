"""
Engenharia de Features Quantitativas e Filtro CUSUM.

Este módulo implementa:
- Cálculo vetorizado de indicadores técnicos (EMA, RSI, ATR)
- Filtro CUSUM para detecção de mudanças estruturais no mercado
- Features para meta-labeling
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple
import pandas_ta as ta

from core.logger import get_logger

logger = get_logger(__name__)


class FeatureEngine:
    """
    Motor de engenharia de features para análise quantitativa.
    
    Calcula indicadores técnicos e features estatísticas de forma
    vetorizada para máxima performance computacional.
    """
    
    def __init__(
        self,
        ema_period: int = 200,
        rsi_period: int = 14,
        atr_period: int = 14
    ):
        """
        Inicializa motor de features.
        
        Args:
            ema_period: Período da média móvel exponencial
            rsi_period: Período do índice de força relativa
            atr_period: Período do average true range
        """
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        
        logger.info(
            f"FeatureEngine inicializado - "
            f"EMA: {ema_period}, RSI: {rsi_period}, ATR: {atr_period}"
        )
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula todos os indicadores técnicos de forma vetorizada.
        
        Args:
            df: DataFrame com colunas OHLCV
            
        Returns:
            DataFrame enriquecido com indicadores
        """
        if df is None or len(df) == 0:
            logger.warning("DataFrame vazio recebido")
            return df
        
        df = df.copy()
        
        try:
            # EMA - Média Móvel Exponencial
            df['ema'] = ta.ema(df['close'], length=self.ema_period)
            
            # RSI - Índice de Força Relativa
            df['rsi'] = ta.rsi(df['close'], length=self.rsi_period)
            
            # ATR - Average True Range
            df['atr'] = ta.atr(
                df['high'],
                df['low'],
                df['close'],
                length=self.atr_period
            )
            
            # Features adicionais para ML
            df['returns'] = df['close'].pct_change()
            df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
            
            # Volatilidade realizada (rolling std dos retornos)
            df['volatility'] = df['returns'].rolling(window=20).std()
            
            # Momentum
            df['momentum'] = df['close'] - df['close'].shift(10)
            
            # Distância do preço em relação à EMA (em múltiplos de ATR)
            df['price_distance_ema'] = (df['close'] - df['ema']) / df['atr']
            
            # Volume relativo
            df['volume_ratio'] = df['tick_volume'] / df['tick_volume'].rolling(20).mean()
            
            # Remove NaNs gerados pelos cálculos
            initial_rows = len(df)
            df.dropna(inplace=True)
            dropped = initial_rows - len(df)
            
            if dropped > 0:
                logger.debug(f"Removidas {dropped} linhas com NaN após cálculo de features")
            
            logger.debug(f"Calculados {len(df.columns)} features para {len(df)} barras")
            
        except Exception as e:
            logger.error(f"Erro ao calcular indicadores: {e}")
            raise
        
        return df
    
    def create_ml_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Cria features específicas para meta-labeling.
        
        Args:
            df: DataFrame com indicadores calculados
            
        Returns:
            DataFrame com features para ML
        """
        df = df.copy()
        
        try:
            # Features baseadas em janelas temporais
            for period in [5, 10, 20]:
                # Média dos retornos
                df[f'return_mean_{period}'] = df['returns'].rolling(period).mean()
                
                # Volatilidade
                df[f'volatility_{period}'] = df['returns'].rolling(period).std()
                
                # RSI médio
                df[f'rsi_mean_{period}'] = df['rsi'].rolling(period).mean()
            
            # Tendência da EMA
            df['ema_trend'] = np.sign(df['ema'] - df['ema'].shift(1))
            
            # Aceleração do preço
            df['price_acceleration'] = df['close'].diff().diff()
            
            # Distância entre máxima e mínima normalizada
            df['range_normalized'] = (df['high'] - df['low']) / df['close']
            
            # Razão corpo/sombra da vela
            df['body_shadow_ratio'] = np.abs(df['close'] - df['open']) / (df['high'] - df['low'] + 1e-10)
            
            df.dropna(inplace=True)
            
            logger.debug(f"Features ML criadas: {len(df.columns)} colunas")
            
        except Exception as e:
            logger.error(f"Erro ao criar features ML: {e}")
            raise
        
        return df


class CUSUMFilter:
    """
    Filtro CUSUM (Cumulative Sum) para detecção de mudanças estruturais.
    
    O filtro CUSUM detecta mudanças persistentes no processo gerador de dados,
    filtrando ruído de mercado e identificando regimes de volatilidade.
    
    Referência: López de Prado, M. (2018). Advances in Financial Machine Learning.
    """
    
    def __init__(
        self,
        threshold: float = 0.02,
        drift: float = 0.001
    ):
        """
        Inicializa filtro CUSUM.
        
        Args:
            threshold: Limite para detecção de evento (típico: 0.01-0.03)
            drift: Drift esperado do processo (típico: 0.0001-0.001)
        """
        self.threshold = threshold
        self.drift = drift
        self.s_pos = 0.0  # CUSUM positivo
        self.s_neg = 0.0  # CUSUM negativo
        self.last_event_time = None
        
        logger.info(
            f"CUSUMFilter inicializado - "
            f"Threshold: {threshold}, Drift: {drift}"
        )
    
    def update(self, value: float, timestamp: Any) -> Tuple[bool, str]:
        """
        Atualiza filtro CUSUM com nova observação.
        
        Args:
            value: Valor observado (tipicamente retorno logarítmico)
            timestamp: Timestamp da observação
            
        Returns:
            Tupla (evento_detectado, direção)
            direção: 'UP' para evento positivo, 'DOWN' para negativo, '' para nenhum
        """
        # Atualiza CUSUM positivo e negativo
        self.s_pos = max(0, self.s_pos + value - self.drift)
        self.s_neg = min(0, self.s_neg + value + self.drift)
        
        # Detecta eventos
        if self.s_pos > self.threshold:
            logger.info(f"CUSUM: Evento UP detectado em {timestamp} (S+={self.s_pos:.4f})")
            self.s_pos = 0
            self.s_neg = 0
            self.last_event_time = timestamp
            return True, 'UP'
        
        if self.s_neg < -self.threshold:
            logger.info(f"CUSUM: Evento DOWN detectado em {timestamp} (S-={self.s_neg:.4f})")
            self.s_pos = 0
            self.s_neg = 0
            self.last_event_time = timestamp
            return True, 'DOWN'
        
        return False, ''
    
    def reset(self) -> None:
        """
        Reseta o estado do filtro CUSUM.
        """
        self.s_pos = 0.0
        self.s_neg = 0.0
        self.last_event_time = None
        logger.debug("CUSUM resetado")
    
    def get_state(self) -> Dict[str, Any]:
        """
        Retorna estado atual do filtro.
        
        Returns:
            Dicionário com valores de S+ e S-
        """
        return {
            's_pos': self.s_pos,
            's_neg': self.s_neg,
            'last_event': self.last_event_time
        }


class BarrierLabeler:
    """
    Gerador de labels baseado em barreiras triplas (Triple-Barrier Method).
    
    Cria labels para ML baseados em três barreiras:
    - Take Profit (barreira superior)
    - Stop Loss (barreira inferior)
    - Tempo máximo (barreira horizontal)
    """
    
    def __init__(
        self,
        sl_multiplier: float = 2.0,
        tp_multiplier: float = 3.0,
        max_bars: int = 10
    ):
        """
        Inicializa gerador de labels.
        
        Args:
            sl_multiplier: Multiplicador do ATR para Stop Loss
            tp_multiplier: Multiplicador do ATR para Take Profit
            max_bars: Número máximo de barras para avaliação
        """
        self.sl_multiplier = sl_multiplier
        self.tp_multiplier = tp_multiplier
        self.max_bars = max_bars
    
    def generate_labels(
        self,
        df: pd.DataFrame,
        side: int
    ) -> np.ndarray:
        """
        Gera labels baseados em barreiras triplas.
        
        Args:
            df: DataFrame com preços e ATR
            side: Direção do trade (1 para compra, -1 para venda)
            
        Returns:
            Array de labels (1 para sucesso, 0 para falha)
        """
        labels = np.zeros(len(df))
        
        for i in range(len(df) - self.max_bars):
            entry_price = df['close'].iloc[i]
            atr = df['atr'].iloc[i]
            
            if pd.isna(atr) or atr == 0:
                continue
            
            # Define barreiras
            if side == 1:  # Compra
                tp_barrier = entry_price + (self.tp_multiplier * atr)
                sl_barrier = entry_price - (self.sl_multiplier * atr)
            else:  # Venda
                tp_barrier = entry_price - (self.tp_multiplier * atr)
                sl_barrier = entry_price + (self.sl_multiplier * atr)
            
            # Verifica próximas barras
            for j in range(1, self.max_bars + 1):
                if i + j >= len(df):
                    break
                
                future_price = df['close'].iloc[i + j]
                
                # Verifica se atingiu TP
                if side == 1 and future_price >= tp_barrier:
                    labels[i] = 1
                    break
                elif side == -1 and future_price <= tp_barrier:
                    labels[i] = 1
                    break
                
                # Verifica se atingiu SL
                if side == 1 and future_price <= sl_barrier:
                    labels[i] = 0
                    break
                elif side == -1 and future_price >= sl_barrier:
                    labels[i] = 0
                    break
        
        return labels
