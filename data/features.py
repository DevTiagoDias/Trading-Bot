"""
Engenharia de Features Quantitativas e Filtros de Mercado.

Este módulo implementa a fundação quantitativa do sistema de trading:
1. FeatureEngine: Cálculo vetorizado de indicadores técnicos (EMA, RSI, ATR, ADX, MACD)
2. CUSUMFilter: Detecção de mudanças estruturais (López de Prado, 2018)
3. BarrierLabeler: Triple-Barrier Method para meta-labeling

Referências Acadêmicas:
- López de Prado, M. (2018). Advances in Financial Machine Learning. Wiley.
- Wilder, J.W. (1978). New Concepts in Technical Trading Systems. Trend Research.

Performance:
- Operações vetorizadas (NumPy) para máxima velocidade
- Look-ahead bias free (sem informação futura)
- Memory efficient (dropna agressivo)
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
    
    Indicadores Implementados:
    - Tendência: EMA, MACD, ADX
    - Momentum: RSI, Price Acceleration
    - Volatilidade: ATR, Rolling Std
    - Volume: Volume Ratio
    - Price Action: Range, Body/Shadow Ratio
    
    Exemplo:
        >>> engine = FeatureEngine(ema_period=200, rsi_period=14, atr_period=14)
        >>> df = engine.calculate_indicators(ohlcv_df)
        >>> df = engine.create_ml_features(df)
    """
    
    def __init__(
        self,
        ema_period: int = 200,
        rsi_period: int = 14,
        atr_period: int = 14,
        adx_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9
    ):
        """
        Inicializa o motor de features.
        
        Args:
            ema_period: Período da média móvel exponencial (padrão: 200)
            rsi_period: Período do RSI (padrão: 14)
            atr_period: Período do ATR (padrão: 14)
            adx_period: Período do ADX (padrão: 14)
            macd_fast: Período rápido do MACD (padrão: 12)
            macd_slow: Período lento do MACD (padrão: 26)
            macd_signal: Período da linha de sinal MACD (padrão: 9)
        """
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        
        logger.info(
            f"FeatureEngine inicializado - "
            f"EMA: {ema_period}, RSI: {rsi_period}, ATR: {atr_period}, "
            f"ADX: {adx_period}, MACD: {macd_fast}/{macd_slow}/{macd_signal}"
        )
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula todos os indicadores técnicos de forma vetorizada.
        
        Indicadores calculados:
        1. EMA (Exponential Moving Average) - Filtro de tendência
        2. RSI (Relative Strength Index) - Momentum
        3. ATR (Average True Range) - Volatilidade
        4. ADX (Average Directional Index) - Força da tendência
        5. MACD - Convergência/Divergência de médias móveis
        6. Features derivadas (returns, volatility, momentum, etc.)
        
        Args:
            df: DataFrame com colunas OHLCV (open, high, low, close, tick_volume)
            
        Returns:
            DataFrame enriquecido com indicadores técnicos
            
        Raises:
            Exception: Se houver erro no cálculo (propaga para debug)
        """
        if df is None or len(df) == 0:
            logger.warning("DataFrame vazio recebido em calculate_indicators")
            return pd.DataFrame()
        
        df = df.copy()
        initial_rows = len(df)
        
        try:
            # ========== INDICADORES DE TENDÊNCIA ==========
            
            # EMA - Média Móvel Exponencial
            # Identifica direção da tendência (preço > EMA = alta, preço < EMA = baixa)
            df['ema'] = ta.ema(df['close'], length=self.ema_period)
            
            # MACD - Moving Average Convergence Divergence
            # Detecta mudanças de momentum e timing de entrada/saída
            # MACD > Signal = Momentum bullish | MACD < Signal = Momentum bearish
            macd_result = ta.macd(
                df['close'],
                fast=self.macd_fast,
                slow=self.macd_slow,
                signal=self.macd_signal
            )
            
            if macd_result is not None and not macd_result.empty:
                df['macd'] = macd_result[f'MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}']
                df['macd_signal'] = macd_result[f'MACDs_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}']
                df['macd_hist'] = macd_result[f'MACDh_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}']
                logger.debug("MACD calculado com sucesso")
            else:
                df['macd'] = 0.0
                df['macd_signal'] = 0.0
                df['macd_hist'] = 0.0
                logger.warning("MACD não pôde ser calculado - usando zeros")
            
            # ADX - Average Directional Index
            # Mede a FORÇA da tendência (não a direção!)
            # ADX > 25 = Tendência forte (sistema funciona bem)
            # ADX < 20 = Mercado lateral (evitar trades)
            # CRÍTICO: Filtra mercados laterais onde seguidores de tendência perdem
            adx_result = ta.adx(
                df['high'],
                df['low'],
                df['close'],
                length=self.adx_period
            )
            
            if adx_result is not None and not adx_result.empty:
                df['adx'] = adx_result[f'ADX_{self.adx_period}']
                df['adx_plus'] = adx_result[f'DMP_{self.adx_period}']  # Directional Movement Positive
                df['adx_minus'] = adx_result[f'DMN_{self.adx_period}']  # Directional Movement Negative
                logger.debug("ADX calculado com sucesso")
            else:
                df['adx'] = 0.0
                df['adx_plus'] = 0.0
                df['adx_minus'] = 0.0
                logger.warning("ADX não pôde ser calculado - usando zeros")
            
            # ========== INDICADORES DE MOMENTUM ==========
            
            # RSI - Relative Strength Index
            # Identifica condições de sobrecompra/sobrevenda
            # RSI > 70 = Sobrecomprado | RSI < 30 = Sobrevendido
            df['rsi'] = ta.rsi(df['close'], length=self.rsi_period)
            
            # ========== INDICADORES DE VOLATILIDADE ==========
            
            # ATR - Average True Range
            # Mede volatilidade do mercado (usado para stops e targets dinâmicos)
            df['atr'] = ta.atr(
                df['high'],
                df['low'],
                df['close'],
                length=self.atr_period
            )
            
            # ========== FEATURES DERIVADAS ==========
            
            # Retornos (simples e logarítmicos)
            df['returns'] = df['close'].pct_change()
            df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
            
            # Volatilidade realizada (rolling standard deviation)
            df['volatility'] = df['returns'].rolling(window=20).std()
            
            # Momentum (diferença de preço)
            df['momentum'] = df['close'] - df['close'].shift(10)
            
            # Distância do preço em relação à EMA (normalizada pelo ATR)
            # Valores altos = preço muito afastado da média (possível reversão)
            df['price_distance_ema'] = (df['close'] - df['ema']) / df['atr'].replace(0, 1e-9)
            
            # Volume relativo (volume atual vs média de 20 períodos)
            if 'tick_volume' in df.columns:
                df['volume_ratio'] = df['tick_volume'] / df['tick_volume'].rolling(20).mean().replace(0, 1e-9)
            else:
                df['volume_ratio'] = 1.0
                logger.debug("Coluna 'tick_volume' não encontrada - usando volume_ratio = 1.0")
            
            # ========== LIMPEZA DE DADOS ==========
            
            # Remove NaNs gerados pelos cálculos de rolling/shift
            df.dropna(inplace=True)
            final_rows = len(df)
            dropped = initial_rows - final_rows
            
            if dropped > 0:
                logger.debug(f"Removidas {dropped} linhas com NaN após cálculo de indicadores")
            
            logger.info(
                f"Indicadores calculados com sucesso: "
                f"{final_rows} barras válidas, {len(df.columns)} colunas"
            )
            
        except Exception as e:
            logger.error(f"Erro ao calcular indicadores técnicos: {e}", exc_info=True)
            raise  # Propaga exceção para debug (não mascarar erros)
        
        return df
    
    def create_ml_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Cria features estatísticas avançadas para Meta-Labeling (Machine Learning).
        
        Features criadas:
        - Múltiplas janelas temporais (5, 10, 20 períodos)
        - Estatísticas de retornos e volatilidade
        - Médias do RSI
        - Tendência da EMA
        - Aceleração de preço
        - Price action quantitativo (range, corpo/sombra)
        
        Args:
            df: DataFrame com indicadores calculados
            
        Returns:
            DataFrame com features para ML (20+ features)
            
        Raises:
            Exception: Se houver erro na criação de features
        """
        if df is None or len(df) == 0:
            logger.warning("DataFrame vazio recebido em create_ml_features")
            return pd.DataFrame()
        
        df = df.copy()
        initial_rows = len(df)
        
        try:
            # ========== FEATURES BASEADAS EM JANELAS TEMPORAIS ==========
            
            # Múltiplas janelas para capturar diferentes time scales
            for window in [5, 10, 20]:
                # Média dos retornos (captura momentum de curto/médio/longo prazo)
                df[f'return_mean_{window}'] = df['returns'].rolling(window).mean()
                
                # Volatilidade por janela (detecta mudanças na volatilidade)
                df[f'volatility_{window}'] = df['returns'].rolling(window).std()
                
                # RSI médio (suaviza oscilações do RSI)
                if 'rsi' in df.columns:
                    df[f'rsi_mean_{window}'] = df['rsi'].rolling(window).mean()
            
            # ========== FEATURES DE TENDÊNCIA ==========
            
            # Direção da tendência da EMA (1 = subindo, -1 = descendo)
            df['ema_trend'] = np.sign(df['ema'].diff())
            
            # ========== FEATURES DE PRICE ACTION ==========
            
            # Aceleração do preço (segunda derivada)
            df['price_acceleration'] = df['returns'].diff()
            
            # Range normalizado (tamanho da vela / ATR)
            # Valores altos = volatilidade aumentada
            high_low_range = (df['high'] - df['low']).replace(0, 1e-9)
            df['range_normalized'] = high_low_range / df['atr'].replace(0, 1e-9)
            
            # Razão corpo/sombra da vela (price action)
            # Valores próximos de 1 = corpo grande (movimento decisivo)
            # Valores próximos de 0 = sombras grandes (indecisão)
            df['body_shadow_ratio'] = (
                np.abs(df['close'] - df['open']) / high_low_range
            ).fillna(0)
            
            # ========== FEATURES DE MACD ==========
            
            # Divergência MACD-Signal (força do momentum)
            if 'macd' in df.columns and 'macd_signal' in df.columns:
                df['macd_divergence'] = df['macd'] - df['macd_signal']
            
            # ========== FEATURES DE ADX ==========
            
            # Direção da tendência baseada em DM+ vs DM-
            if 'adx_plus' in df.columns and 'adx_minus' in df.columns:
                df['adx_direction'] = np.sign(df['adx_plus'] - df['adx_minus'])
            
            # ========== LIMPEZA FINAL ==========
            
            # Remove NaNs gerados pelos rolling/diff
            df.dropna(inplace=True)
            final_rows = len(df)
            dropped = initial_rows - final_rows
            
            if dropped > 0:
                logger.debug(f"Removidas {dropped} linhas com NaN após criação de features ML")
            
            logger.info(
                f"Features ML criadas com sucesso: "
                f"{final_rows} barras válidas, {len(df.columns)} colunas totais"
            )
            
        except Exception as e:
            logger.error(f"Erro ao criar features para ML: {e}", exc_info=True)
            raise
        
        return df
    
    def get_feature_names(self) -> List[str]:
        """
        Retorna lista de nomes de features usadas pelo modelo ML.
        
        Útil para validação e debug do RandomForest.
        
        Returns:
            Lista de nomes das features
        """
        base_features = [
            'rsi', 'volatility', 'momentum', 'price_distance_ema',
            'volume_ratio', 'ema_trend', 'price_acceleration',
            'range_normalized', 'body_shadow_ratio'
        ]
        
        # Features com janelas temporais
        for window in [5, 10, 20]:
            base_features.extend([
                f'return_mean_{window}',
                f'volatility_{window}',
                f'rsi_mean_{window}'
            ])
        
        # Features de MACD e ADX (se disponíveis)
        base_features.extend([
            'macd_divergence',
            'adx',
            'adx_direction'
        ])
        
        return base_features


class CUSUMFilter:
    """
    Filtro CUSUM (Cumulative Sum Control Chart) para Detecção de Mudanças Estruturais.
    
    Implementa o filtro CUSUM de López de Prado para detectar mudanças persistentes
    no processo gerador de dados (regime shifts), filtrando ruído de mercado.
    
    O filtro acumula desvios em relação a um drift esperado e dispara eventos
    quando o acumulado excede um threshold.
    
    Matemática:
        S+ = max(0, S+ + y_t - drift)
        S- = min(0, S- + y_t + drift)
        
        Evento UP se S+ > threshold
        Evento DOWN se S- < -threshold
    
    Referência:
        López de Prado, M. (2018). Advances in Financial Machine Learning.
        Chapter 2: Financial Data Structures.
    
    Exemplo:
        >>> cusum = CUSUMFilter(threshold=0.02, drift=0.001)
        >>> for log_return, timestamp in data:
        ...     event, direction = cusum.update(log_return, timestamp)
        ...     if event:
        ...         print(f"Evento {direction} detectado!")
    """
    
    def __init__(
        self,
        threshold: float = 0.02,
        drift: float = 0.001
    ):
        """
        Inicializa o filtro CUSUM.
        
        Args:
            threshold: Limite para detecção de evento (típico: 0.01-0.03)
                      Valores maiores = menos sinais (mais seletivo)
                      Valores menores = mais sinais (menos seletivo)
            drift: Drift esperado do processo (típico: 0.0001-0.001)
                   Compensa tendência natural do mercado
        """
        self.threshold = threshold
        self.drift = drift
        
        # Estado do filtro
        self.s_pos = 0.0  # CUSUM positivo (detecta movimentos para cima)
        self.s_neg = 0.0  # CUSUM negativo (detecta movimentos para baixo)
        self.last_event_time = None
        self.event_count = {'UP': 0, 'DOWN': 0}
        
        logger.info(
            f"CUSUMFilter inicializado - "
            f"Threshold: {threshold:.4f}, Drift: {drift:.6f}"
        )
    
    def update(self, value: float, timestamp: Any) -> Tuple[bool, str]:
        """
        Atualiza o filtro CUSUM com nova observação.
        
        Args:
            value: Valor observado (tipicamente retorno logarítmico)
            timestamp: Timestamp da observação (para logging)
            
        Returns:
            Tupla (evento_detectado: bool, direção: str)
            - evento_detectado: True se threshold foi excedido
            - direção: 'UP' para evento positivo, 'DOWN' para negativo, '' para nenhum
        """
        # Valida entrada
        if pd.isna(value):
            logger.debug(f"Valor NaN recebido em CUSUM.update() - ignorando")
            return False, ''
        
        # Atualiza CUSUM positivo e negativo
        self.s_pos = max(0.0, self.s_pos + value - self.drift)
        self.s_neg = min(0.0, self.s_neg + value + self.drift)
        
        # Detecta evento UP (movimento persistente para cima)
        if self.s_pos > self.threshold:
            logger.info(
                f"CUSUM: Evento UP detectado em {timestamp} "
                f"(S+={self.s_pos:.4f} > {self.threshold:.4f})"
            )
            
            self.s_pos = 0.0
            self.s_neg = 0.0
            self.last_event_time = timestamp
            self.event_count['UP'] += 1
            
            return True, 'UP'
        
        # Detecta evento DOWN (movimento persistente para baixo)
        if self.s_neg < -self.threshold:
            logger.info(
                f"CUSUM: Evento DOWN detectado em {timestamp} "
                f"(S-={self.s_neg:.4f} < {-self.threshold:.4f})"
            )
            
            self.s_pos = 0.0
            self.s_neg = 0.0
            self.last_event_time = timestamp
            self.event_count['DOWN'] += 1
            
            return True, 'DOWN'
        
        # Nenhum evento detectado
        return False, ''
    
    def reset(self) -> None:
        """
        Reseta o estado do filtro CUSUM.
        
        Útil para reiniciar o filtro após mudanças de regime
        ou para debug/testing.
        """
        self.s_pos = 0.0
        self.s_neg = 0.0
        self.last_event_time = None
        logger.debug("CUSUM resetado para estado inicial")
    
    def get_state(self) -> Dict[str, Any]:
        """
        Retorna o estado atual do filtro CUSUM.
        
        Útil para debug, logging e persistência de estado.
        
        Returns:
            Dicionário com:
            - s_pos: Valor atual do CUSUM positivo
            - s_neg: Valor atual do CUSUM negativo
            - last_event: Timestamp do último evento detectado
            - event_count: Contador de eventos UP/DOWN
        """
        return {
            's_pos': self.s_pos,
            's_neg': self.s_neg,
            'last_event': self.last_event_time,
            'event_count': self.event_count.copy(),
            'threshold': self.threshold,
            'drift': self.drift
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas de uso do filtro.
        
        Returns:
            Dicionário com estatísticas de eventos detectados
        """
        total_events = sum(self.event_count.values())
        
        stats = {
            'total_events': total_events,
            'up_events': self.event_count['UP'],
            'down_events': self.event_count['DOWN'],
        }
        
        if total_events > 0:
            stats['up_ratio'] = self.event_count['UP'] / total_events
            stats['down_ratio'] = self.event_count['DOWN'] / total_events
        
        return stats


class BarrierLabeler:
    """
    Gerador de Labels baseado em Barreiras Triplas (Triple-Barrier Method).
    
    Implementa o método de López de Prado para criar labels para meta-labeling.
    Avalia cada trade potencial usando três barreiras:
    
    1. Take Profit (barreira superior) - Objetivo de lucro
    2. Stop Loss (barreira inferior) - Limite de perda
    3. Tempo Máximo (barreira horizontal) - Expiração
    
    O label é definido pelo que for atingido primeiro:
    - Label = 1 se atingir TP antes de SL ou tempo
    - Label = 0 se atingir SL ou tempo antes de TP
    
    Referência:
        López de Prado, M. (2018). Advances in Financial Machine Learning.
        Chapter 3: Labeling.
    
    Exemplo:
        >>> labeler = BarrierLabeler(sl_multiplier=2.0, tp_multiplier=3.0, max_bars=10)
        >>> labels = labeler.generate_labels(df, side=1)  # 1 = compra
        >>> accuracy = labels.mean()  # % de labels = 1
    """
    
    def __init__(
        self,
        sl_multiplier: float = 2.0,
        tp_multiplier: float = 3.0,
        max_bars: int = 10
    ):
        """
        Inicializa o gerador de labels.
        
        Args:
            sl_multiplier: Multiplicador do ATR para Stop Loss (padrão: 2.0)
                          SL = entry_price ± (sl_multiplier * ATR)
            tp_multiplier: Multiplicador do ATR para Take Profit (padrão: 3.0)
                          TP = entry_price ± (tp_multiplier * ATR)
            max_bars: Número máximo de barras para avaliação (padrão: 10)
                     Trade expira se não atingir TP/SL neste período
        """
        self.sl_multiplier = sl_multiplier
        self.tp_multiplier = tp_multiplier
        self.max_bars = max_bars
        
        logger.info(
            f"BarrierLabeler inicializado - "
            f"SL: {sl_multiplier}xATR, TP: {tp_multiplier}xATR, Max Bars: {max_bars}"
        )
    
    def generate_labels(
        self,
        df: pd.DataFrame,
        side: int
    ) -> np.ndarray:
        """
        Gera labels baseados em barreiras triplas.
        
        Para cada barra, simula entrada e verifica se o trade seria vencedor.
        
        Args:
            df: DataFrame com colunas ['close', 'high', 'low', 'atr']
            side: Direção do trade
                  1 para compra (long)
                  -1 para venda (short)
            
        Returns:
            Array NumPy de labels:
            - 1: Trade vencedor (atingiu TP)
            - 0: Trade perdedor (atingiu SL ou expirou)
            
        Raises:
            KeyError: Se coluna 'atr' não existir no DataFrame
        """
        if 'atr' not in df.columns:
            logger.error("Coluna 'atr' não encontrada no DataFrame")
            raise KeyError("DataFrame deve conter coluna 'atr'")
        
        labels = np.zeros(len(df))
        evaluated = 0
        wins = 0
        
        logger.debug(f"Gerando labels para side={side} em {len(df)} barras")
        
        # Itera sobre cada barra (exceto últimas max_bars que não têm futuro)
        for i in range(len(df) - self.max_bars):
            entry_price = df['close'].iloc[i]
            atr = df['atr'].iloc[i]
            
            # Pula se ATR inválido
            if pd.isna(atr) or atr <= 0:
                continue
            
            evaluated += 1
            
            # Define barreiras baseadas na direção do trade
            if side == 1:  # Compra
                tp_barrier = entry_price + (self.tp_multiplier * atr)
                sl_barrier = entry_price - (self.sl_multiplier * atr)
            else:  # Venda (side == -1)
                tp_barrier = entry_price - (self.tp_multiplier * atr)
                sl_barrier = entry_price + (self.sl_multiplier * atr)
            
            # Verifica próximas barras até max_bars
            for j in range(1, self.max_bars + 1):
                if i + j >= len(df):
                    break
                
                future_high = df['high'].iloc[i + j]
                future_low = df['low'].iloc[i + j]
                
                # Verifica se atingiu TP (vitória)
                if side == 1:
                    if future_high >= tp_barrier:
                        labels[i] = 1
                        wins += 1
                        break
                    # Verifica se atingiu SL (derrota)
                    if future_low <= sl_barrier:
                        labels[i] = 0
                        break
                else:  # side == -1
                    if future_low <= tp_barrier:
                        labels[i] = 1
                        wins += 1
                        break
                    if future_high >= sl_barrier:
                        labels[i] = 0
                        break
        
        # Estatísticas de geração de labels
        if evaluated > 0:
            win_rate = wins / evaluated
            logger.info(
                f"Labels gerados: {evaluated} avaliados, "
                f"{wins} wins ({win_rate:.1%}), "
                f"{evaluated - wins} losses"
            )
        else:
            logger.warning("Nenhum label pôde ser gerado (ATR inválido em todas as barras?)")
        
        return labels