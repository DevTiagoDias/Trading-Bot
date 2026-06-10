"""
Engenharia de Features Quantitativas e Filtros de Mercado.

Este módulo implementa a fundação quantitativa do sistema de trading:
1. FeatureEngine: Cálculo de indicadores técnicos, codificação cíclica de tempo e volatilidade.
2. CUSUMFilter: Detecção de mudanças estruturais (López de Prado).
3. BarrierLabeler: Método de Barreiras Triplas para rotulagem de alvos.
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
            f"FeatureEngine Otimizado Inicializado | EMA: {ema_period} | RSI: {rsi_period} | ATR: {atr_period}"
        )
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula os indicadores técnicos primários."""
        if df is None or df.empty:
            return pd.DataFrame()
            
        df = df.copy()
        
        try:
            # 1. Base (Tendência e Volatilidade)
            df['ema'] = ta.ema(df['close'], length=self.ema_period)
            df['rsi'] = ta.rsi(df['close'], length=self.rsi_period)
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=self.atr_period)
            
            # 2. ADX (Força da Tendência)
            adx_length = 14
            adx_df = ta.adx(df['high'], df['low'], df['close'], length=adx_length)
            if adx_df is not None and not adx_df.empty:
                adx_col = f'ADX_{adx_length}'
                df['adx'] = adx_df[adx_col] if adx_col in adx_df.columns else adx_df.iloc[:, 0]
            else:
                df['adx'] = 0.0
                
            # 3. MACD Clássico
            macd_df = ta.macd(df['close'], fast=12, slow=26, signal=9)
            if macd_df is not None and not macd_df.empty:
                df['macd'] = macd_df.iloc[:, 0]
                df['macd_hist'] = macd_df.iloc[:, 1]
            else:
                df['macd'] = 0.0
                df['macd_hist'] = 0.0
                
            # 4. Bandas de Bollinger (Cálculo Nativo para Segurança)
            bb_period = 20
            bb_std = 2.0
            rolling_mean = df['close'].rolling(window=bb_period).mean()
            rolling_std = df['close'].rolling(window=bb_period).std()
            
            upper_band = rolling_mean + (rolling_std * bb_std)
            lower_band = rolling_mean - (rolling_std * bb_std)
            
            # Limpeza preventiva
            df.ffill(inplace=True)
            df.bfill(inplace=True)
            
            # Features de Bollinger: Largura (Squeeze) e Posição do Preço (%)
            df['bb_width'] = (upper_band - lower_band) / rolling_mean.replace(0, 1e-9)
            df['bb_position'] = (df['close'] - lower_band) / (upper_band - lower_band).replace(0, 1e-9)
            
        except Exception as e:
            logger.error(f"Erro ao calcular indicadores técnicos: {e}", exc_info=True)
            
        return df

    def create_ml_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cria as features estatísticas avançadas e dados cíclicos."""
        if df is None or df.empty:
            return pd.DataFrame()
            
        df = df.copy()
        
        try:
            # 1. Transformação Cíclica de Tempo (CRUCIAL para M15 e H1)
            # Ajuda a IA a entender a diferença entre a Sessão de Londres e a da Ásia
            hours = df.index.hour
            days = df.index.dayofweek
            
            df['hour_sin'] = np.sin(2 * np.pi * hours / 24.0)
            df['hour_cos'] = np.cos(2 * np.pi * hours / 24.0)
            df['day_sin'] = np.sin(2 * np.pi * days / 5.0)  # 5 dias úteis de mercado
            df['day_cos'] = np.cos(2 * np.pi * days / 5.0)

            # 2. Retornos Logarítmicos e Volatilidade
            df['log_return'] = np.log(df['close'] / df['close'].shift(1))
            
            for window in [5, 10, 20]:
                df[f'return_mean_{window}'] = df['log_return'].rolling(window=window).mean()
                df[f'volatility_{window}'] = df['log_return'].rolling(window=window).std()
            
            # 3. Momentum Avançado e Aceleração
            df['momentum'] = df['close'] - df['close'].shift(10)
            df['price_acceleration'] = df['log_return'] - df['log_return'].shift(1)
            
            if 'macd_hist' in df.columns:
                # Derivada do MACD: Indica se o ímpeto está a acelerar ou a travar
                df['macd_slope'] = df['macd_hist'] - df['macd_hist'].shift(1)
            else:
                df['macd_slope'] = 0.0

            # 4. Distâncias Normalizadas (Mede se o preço está "esticado")
            if 'ema' in df.columns and 'atr' in df.columns:
                safe_atr = df['atr'].replace(0, 1e-9)
                df['price_distance_ema'] = (df['close'] - df['ema']) / safe_atr
            
            # 5. Price Action Microestrutural
            high_low_range = (df['high'] - df['low']).replace(0, 1e-9)
            safe_atr_pa = df['atr'].replace(0, 1e-9)
            df['range_normalized'] = high_low_range / safe_atr_pa
            
            # Tamanho do corpo da vela em relação à vela inteira (Identifica Dojis vs Marubozus)
            df['body_shadow_ratio'] = abs(df['close'] - df['open']) / high_low_range
            
            # Limpeza Extrema Final
            df.replace([np.inf, -np.inf], np.nan, inplace=True)
            df.dropna(inplace=True)
            
        except Exception as e:
            logger.error(f"Erro na criação de features para ML: {e}", exc_info=True)
            
        return df


class CUSUMFilter:
    """
    Filtro CUSUM (Cumulative Sum Control Chart).
    Deteta ruturas estruturais para evitar que a IA opere em mercados parados.
    """
    
    def __init__(self, threshold: float = 0.005, drift: float = 0.0001):
        self.threshold = threshold
        self.drift = drift
        self.sp = 0.0
        self.sn = 0.0
        
    def update(self, y_t: float, timestamp: Any) -> Tuple[bool, str]:
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
    Método de Barreiras Triplas (Triple Barrier Method).
    """
    
    def __init__(
        self, 
        sl_multiplier: float = 1.5, 
        tp_multiplier: float = 2.0, 
        max_bars: int = 20 # Aumentado ligeiramente para M15
    ):
        self.sl_multiplier = float(sl_multiplier)
        self.tp_multiplier = float(tp_multiplier)
        self.max_bars = int(max_bars)

    def generate_labels(self, df: pd.DataFrame, side: int) -> pd.Series:
        if df is None or df.empty or 'atr' not in df.columns:
            return pd.Series(index=df.index if df is not None else [], data=np.nan)

        labels = pd.Series(index=df.index, data=np.nan)
        
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
            
            if pd.isna(atr) or atr <= 0: continue
                
            evaluated += 1
            
            if side == 1:
                tp_barrier = entry_price + (self.tp_multiplier * atr)
                sl_barrier = entry_price - (self.sl_multiplier * atr)
            elif side == -1:
                tp_barrier = entry_price - (self.tp_multiplier * atr)
                sl_barrier = entry_price + (self.sl_multiplier * atr)
            else:
                continue
            
            labels.iloc[i] = 0
            
            for j in range(1, self.max_bars + 1):
                if i + j >= n_samples: break
                
                future_high = highs[i + j]
                future_low = lows[i + j]
                
                if side == 1:
                    if future_low <= sl_barrier: break
                    if future_high >= tp_barrier:
                        labels.iloc[i] = 1
                        wins += 1
                        break
                else:
                    if future_high >= sl_barrier: break
                    if future_low <= tp_barrier:
                        labels.iloc[i] = 1
                        wins += 1
                        break
        
        if evaluated > 0:
            win_rate = wins / evaluated
            logger.info(f"Labeler Side {side}: {wins}/{evaluated} Vitórias ({win_rate:.1%})")
            
        return labels