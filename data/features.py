"""
Engenharia de Features Quantitativas e Filtros de Mercado.

Este módulo implementa a fundação quantitativa do sistema de trading:
1. FeatureEngine: Cálculo vetorizado de indicadores técnicos (EMA, RSI, ATR, ADX, MACD)
2. CUSUMFilter: Detecção de mudanças estruturais (López de Prado, 2018)
3. BarrierLabeler: Método de Barreiras Triplas (Triple-Barrier Method) para rotulagem

Referências Académicas:
- López de Prado, M. (2018). Advances in Financial Machine Learning. Wiley.
- Wilder, J.W. (1978). New Concepts in Technical Trading Systems. Trend Research.

Desenvolvido para máxima performance, tolerância a falhas (NaNs) e prevenção de Look-ahead bias.
"""

import pandas as pd
import numpy as np
import pandas_ta as ta
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime

from core.logger import get_logger

logger = get_logger(__name__)


class FeatureEngine:
    """
    Motor de Engenharia de Features para Análise Quantitativa.
    
    Calcula indicadores técnicos e features estatísticas de forma vetorizada,
    garantindo máxima performance e prevenção de look-ahead bias.
    """
    
    def __init__(
        self,
        ema_period: int = 200,
        rsi_period: int = 14,
        atr_period: int = 14
    ):
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        
        logger.info(
            f"FeatureEngine Inicializado | EMA: {ema_period} | RSI: {rsi_period} | ATR: {atr_period}"
        )
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula os indicadores técnicos primários de forma vetorizada e segura."""
        if df is None or df.empty:
            logger.error("FeatureEngine: DataFrame vazio recebido.")
            return pd.DataFrame()
            
        df = df.copy()
        
        try:
            # 1. Indicadores de Tendência e Volatilidade Base
            df['ema'] = ta.ema(df['close'], length=self.ema_period)
            df['rsi'] = ta.rsi(df['close'], length=self.rsi_period)
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=self.atr_period)
            
            # 2. ADX (Average Directional Index) - Filtro de Força de Tendência
            adx_length = 14
            adx_df = ta.adx(df['high'], df['low'], df['close'], length=adx_length)
            if adx_df is not None and not adx_df.empty:
                # O pandas_ta gera colunas como ADX_14, DMP_14, DMN_14. Garantimos a extração correta.
                adx_col = f'ADX_{adx_length}'
                df['adx'] = adx_df[adx_col] if adx_col in adx_df.columns else adx_df.iloc[:, 0]
            else:
                df['adx'] = 0.0
                
            # 3. MACD (Moving Average Convergence Divergence) - Timing de Entrada
            macd_df = ta.macd(df['close'], fast=12, slow=26, signal=9)
            if macd_df is not None and not macd_df.empty:
                df['macd'] = macd_df.iloc[:, 0]        # Linha MACD
                df['macd_hist'] = macd_df.iloc[:, 1]   # Histograma
                df['macd_signal'] = macd_df.iloc[:, 2] # Linha de Sinal
            else:
                df['macd'] = 0.0
                df['macd_hist'] = 0.0
                df['macd_signal'] = 0.0
                
            # Limpeza cirúrgica de valores corrompidos antes da IA
            df.ffill(inplace=True)
            df.bfill(inplace=True)
            
        except Exception as e:
            logger.error(f"Erro ao calcular indicadores técnicos: {e}", exc_info=True)
            
        return df

    def create_ml_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cria as features estatísticas avançadas usadas pelo Random Forest."""
        if df is None or df.empty:
            return pd.DataFrame()
            
        df = df.copy()
        
        try:
            # Retornos e Volatilidade
            df['log_return'] = np.log(df['close'] / df['close'].shift(1))
            df['volatility'] = df['log_return'].rolling(window=self.atr_period).std()
            
            # Janelas Múltiplas de Observação
            for window in [5, 10, 20]:
                df[f'return_mean_{window}'] = df['log_return'].rolling(window=window).mean()
                df[f'volatility_{window}'] = df['log_return'].rolling(window=window).std()
                if 'rsi' in df.columns:
                    df[f'rsi_mean_{window}'] = df['rsi'].rolling(window=window).mean()
            
            # Momentum e Distâncias Normalizadas
            df['momentum'] = df['close'] - df['close'].shift(10)
            if 'ema' in df.columns and 'atr' in df.columns:
                # Substitui zero no ATR por epsilon (1e-9) para evitar divisão por zero
                safe_atr = df['atr'].replace(0, 1e-9)
                df['price_distance_ema'] = (df['close'] - df['ema']) / safe_atr
            
            # Rácio de Volume (Se disponível pela corretora)
            if 'volume' in df.columns and df['volume'].sum() > 0:
                safe_vol_mean = df['volume'].rolling(window=20).mean().replace(0, 1e-9)
                df['volume_ratio'] = df['volume'] / safe_vol_mean
            else:
                df['volume_ratio'] = 1.0
                
            df['ema_trend'] = np.where(df['close'] > df['ema'], 1, -1)
            df['price_acceleration'] = df['log_return'] - df['log_return'].shift(1)
            
            # Price Action Quantitativo
            high_low_range = (df['high'] - df['low']).replace(0, 1e-9)
            safe_atr_pa = df['atr'].replace(0, 1e-9)
            df['range_normalized'] = high_low_range / safe_atr_pa
            df['body_shadow_ratio'] = abs(df['close'] - df['open']) / high_low_range
            
            # Limpeza extrema: A IA não pode ver NaNs em nenhum cenário
            df.dropna(inplace=True)
            
        except Exception as e:
            logger.error(f"Erro na criação de features para ML: {e}", exc_info=True)
            
        return df


class CUSUMFilter:
    """
    Filtro CUSUM (Cumulative Sum Control Chart).
    Deteta ruturas estruturais e grandes injeções de liquidez no mercado, 
    evitando que o sistema processe ruído constante.
    """
    
    def __init__(self, threshold: float = 0.005, drift: float = 0.0001):
        self.threshold = threshold
        self.drift = drift
        self.sp = 0.0  # Soma cumulativa positiva
        self.sn = 0.0  # Soma cumulativa negativa
        
    def update(self, y_t: float, timestamp: Any) -> Tuple[bool, str]:
        """Processa o tick atual e verifica se a barreira foi rompida."""
        if pd.isna(y_t):
            return False, ""
            
        self.sp = max(0.0, self.sp + y_t - self.drift)
        self.sn = min(0.0, self.sn + y_t + self.drift)
        
        if self.sp > self.threshold:
            self.sp = 0.0
            self.sn = 0.0
            return True, "UP"
            
        elif self.sn < -self.threshold:
            self.sp = 0.0
            self.sn = 0.0
            return True, "DOWN"
            
        return False, ""


class BarrierLabeler:
    """
    Implementação do Método de Barreiras Triplas (Triple Barrier Method).
    
    Rotula os dados históricos simulando operações reais. O resultado (1 ou 0)
    serve como alvo (target - Y) para o treino do classificador Random Forest.
    """
    
    def __init__(
        self, 
        sl_multiplier: float = 1.5, 
        tp_multiplier: float = 2.0, 
        max_bars: int = 15
    ):
        self.sl_multiplier = float(sl_multiplier)
        self.tp_multiplier = float(tp_multiplier)
        self.max_bars = int(max_bars)

    def generate_labels(self, df: pd.DataFrame, side: int) -> pd.Series:
        """
        Gera os rótulos (Y) baseados na simulação das barreiras.
        
        Args:
            df (pd.DataFrame): Dados OHLC com ATR calculado.
            side (int): 1 para COMPRA, -1 para VENDA.
            
        Returns:
            pd.Series: Rótulos temporais (1 para Hit TP, 0 para Hit SL / Timeout)
        """
        if df is None or df.empty or 'atr' not in df.columns:
            logger.error("BarrierLabeler: Dados inválidos para rotulagem.")
            return pd.Series(index=df.index if df is not None else [], data=np.nan)

        labels = pd.Series(index=df.index, data=np.nan)
        
        # Otimização Numpy para performance massiva em grandes datasets
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        atrs = df['atr'].values
        n_samples = len(df)
        
        evaluated = 0
        wins = 0
        
        for i in range(n_samples - self.max_bars):
            entry_price = closes[i]
            atr = atrs[i]
            
            if pd.isna(atr) or atr <= 0:
                continue
                
            evaluated += 1
            
            # Definição dos limiares das barreiras
            if side == 1:  # Compra
                tp_barrier = entry_price + (self.tp_multiplier * atr)
                sl_barrier = entry_price - (self.sl_multiplier * atr)
            elif side == -1:  # Venda
                tp_barrier = entry_price - (self.tp_multiplier * atr)
                sl_barrier = entry_price + (self.sl_multiplier * atr)
            else:
                continue
            
            # Padrão é perda (0) caso expire o tempo sem atingir o alvo
            labels.iloc[i] = 0
            
            # Varredura do horizonte futuro
            for j in range(1, self.max_bars + 1):
                if i + j >= n_samples:
                    break
                
                future_high = highs[i + j]
                future_low = lows[i + j]
                
                if side == 1:
                    # Tocou no Stop Loss primeiro?
                    if future_low <= sl_barrier:
                        break
                    # Tocou no Take Profit?
                    if future_high >= tp_barrier:
                        labels.iloc[i] = 1
                        wins += 1
                        break
                else:  # side == -1
                    # Tocou no Stop Loss primeiro?
                    if future_high >= sl_barrier:
                        break
                    # Tocou no Take Profit?
                    if future_low <= tp_barrier:
                        labels.iloc[i] = 1
                        wins += 1
                        break
        
        # Estatísticas Cruciais de Treino
        if evaluated > 0:
            win_rate = wins / evaluated
            logger.info(
                f"BarrierLabeler (Side {side}): {evaluated} amostras processadas | "
                f"Vitórias: {wins} ({win_rate:.1%}) | Derrotas: {evaluated - wins}"
            )
            if win_rate < 0.10:
                logger.warning("Taxa de vitória extremamente baixa nos dados históricos. A estratégia base pode estar desalinhada.")
        else:
            logger.warning("Nenhum rótulo pôde ser gerado (Verifique se o ATR é válido).")
        
        return labels