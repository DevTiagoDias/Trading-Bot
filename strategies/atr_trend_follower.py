"""
Estratégia ATR Trend Follower
Segue tendências com confirmação de RSI e stops dinâmicos baseados em ATR
"""

import pandas as pd
from typing import Optional, Dict, Any
from strategies.base import BaseStrategy, TradingSignal, SignalType
from core.logger import get_logger


class ATRTrendFollower(BaseStrategy):
    """
    Estratégia de seguimento de tendência com ATR
    
    Lógica:
    - Compra: Preço > EMA(200) E RSI < 30 (pullback em tendência de alta)
    - Venda: Preço < EMA(200) E RSI > 70 (pullback em tendência de baixa)
    - Stop Loss: 2.0 x ATR
    - Take Profit: 3.0 x ATR
    - Trailing Stop: Dinâmico baseado em ATR
    """

    def __init__(self, parameters: Dict[str, Any]):
        """
        Args:
            parameters: Parâmetros da estratégia
                - ema_period: Período da EMA (padrão: 200)
                - rsi_period: Período do RSI (padrão: 14)
                - rsi_oversold: Nível de sobrevenda (padrão: 30)
                - rsi_overbought: Nível de sobrecompra (padrão: 70)
                - atr_period: Período do ATR (padrão: 14)
                - atr_multiplier_stop: Multiplicador ATR para stop (padrão: 2.0)
                - atr_multiplier_target: Multiplicador ATR para target (padrão: 3.0)
                - min_bars: Mínimo de barras necessárias (padrão: 250)
        """
        super().__init__("ATR Trend Follower", parameters)
        
        # Parâmetros
        self.ema_period = self.get_parameter('ema_period', 200)
        self.rsi_period = self.get_parameter('rsi_period', 14)
        self.rsi_oversold = self.get_parameter('rsi_oversold', 30)
        self.rsi_overbought = self.get_parameter('rsi_overbought', 70)
        self.atr_period = self.get_parameter('atr_period', 14)
        self.atr_multiplier_stop = self.get_parameter('atr_multiplier_stop', 2.0)
        self.atr_multiplier_target = self.get_parameter('atr_multiplier_target', 3.0)
        self.min_bars = self.get_parameter('min_bars', 250)
        
        # Estado interno
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        
    def initialize(self) -> bool:
        """Inicializa a estratégia"""
        self.logger.info(f"Inicializando {self.name}")
        self.logger.info(f"EMA: {self.ema_period} | RSI: {self.rsi_period}")
        self.logger.info(f"RSI Oversold/Overbought: {self.rsi_oversold}/{self.rsi_overbought}")
        self.logger.info(f"ATR Period: {self.atr_period} | Multipliers: {self.atr_multiplier_stop}/{self.atr_multiplier_target}")
        
        self.is_initialized = True
        return True

    def generate_signal(self, data: pd.DataFrame, symbol: str) -> Optional[TradingSignal]:
        """
        Gera sinal baseado nos dados
        
        Args:
            data: DataFrame com OHLCV e indicadores
            symbol: Símbolo
            
        Returns:
            TradingSignal ou None
        """
        if not self.is_initialized:
            self.logger.warning("Estratégia não inicializada")
            return None

        # Verifica dados suficientes
        if len(data) < self.min_bars:
            self.logger.debug(f"Dados insuficientes para {symbol}: {len(data)}/{self.min_bars}")
            return None

        # Verifica indicadores necessários
        required_indicators = [f'ema_{self.ema_period}', 'rsi', 'atr']
        for indicator in required_indicators:
            if indicator not in data.columns:
                self.logger.error(f"Indicador '{indicator}' não encontrado nos dados")
                return None

        # Obtém últimos valores
        last_close = data['close'].iloc[-1]
        last_ema = data[f'ema_{self.ema_period}'].iloc[-1]
        last_rsi = data['rsi'].iloc[-1]
        last_atr = data['atr'].iloc[-1]
        
        # Verifica se indicadores são válidos (não NaN)
        if pd.isna(last_ema) or pd.isna(last_rsi) or pd.isna(last_atr):
            self.logger.debug(f"Indicadores com valores NaN para {symbol}")
            return None

        # --- LÓGICA DE COMPRA ---
        # Condições: Preço acima da EMA (tendência de alta) E RSI oversold (pullback)
        if last_close > last_ema and last_rsi < self.rsi_oversold:
            # Verifica se não há momentum muito fraco
            if last_rsi < 20:  # RSI extremamente baixo pode indicar problema
                self.logger.debug(f"{symbol}: RSI muito baixo ({last_rsi:.2f}), aguardando")
                return None
            
            # Calcula stop loss e take profit
            stop_loss = self.calculate_stop_loss(
                last_close,
                SignalType.BUY,
                last_atr,
                self.atr_multiplier_stop
            )
            
            take_profit = self.calculate_take_profit(
                last_close,
                SignalType.BUY,
                last_atr,
                self.atr_multiplier_target
            )
            
            reason = (
                f"Tendência de alta (Close {last_close:.5f} > EMA {last_ema:.5f}) "
                f"+ RSI Oversold ({last_rsi:.2f} < {self.rsi_oversold})"
            )
            
            signal = TradingSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=last_close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=self._calculate_confidence(last_rsi, self.rsi_oversold, True),
                reason=reason,
                metadata={
                    'ema': last_ema,
                    'rsi': last_rsi,
                    'atr': last_atr
                }
            )
            
            if self.validate_signal(signal):
                self.logger.info(f"SINAL GERADO: {signal}")
                return signal

        # --- LÓGICA DE VENDA ---
        # Condições: Preço abaixo da EMA (tendência de baixa) E RSI overbought (pullback)
        elif last_close < last_ema and last_rsi > self.rsi_overbought:
            # Verifica se não há momentum muito forte
            if last_rsi > 80:  # RSI extremamente alto
                self.logger.debug(f"{symbol}: RSI muito alto ({last_rsi:.2f}), aguardando")
                return None
            
            # Calcula stop loss e take profit
            stop_loss = self.calculate_stop_loss(
                last_close,
                SignalType.SELL,
                last_atr,
                self.atr_multiplier_stop
            )
            
            take_profit = self.calculate_take_profit(
                last_close,
                SignalType.SELL,
                last_atr,
                self.atr_multiplier_target
            )
            
            reason = (
                f"Tendência de baixa (Close {last_close:.5f} < EMA {last_ema:.5f}) "
                f"+ RSI Overbought ({last_rsi:.2f} > {self.rsi_overbought})"
            )
            
            signal = TradingSignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=last_close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=self._calculate_confidence(last_rsi, self.rsi_overbought, False),
                reason=reason,
                metadata={
                    'ema': last_ema,
                    'rsi': last_rsi,
                    'atr': last_atr
                }
            )
            
            if self.validate_signal(signal):
                self.logger.info(f"SINAL GERADO: {signal}")
                return signal

        return None

    def on_tick(self, symbol: str, bid: float, ask: float) -> Optional[TradingSignal]:
        """
        Processa tick individual
        Nesta estratégia, trabalhamos com candles fechados, então retorna None
        
        Args:
            symbol: Símbolo
            bid: Preço bid
            ask: Preço ask
            
        Returns:
            None (estratégia baseada em candles)
        """
        # Esta estratégia não opera em ticks individuais
        return None

    def should_close_position(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        position_type: str
    ) -> bool:
        """
        Verifica se deve fechar posição com trailing stop
        
        Args:
            symbol: Símbolo
            entry_price: Preço de entrada
            current_price: Preço atual
            position_type: 'BUY' ou 'SELL'
            
        Returns:
            True se deve fechar
        """
        # Implementar trailing stop dinâmico baseado em ATR
        # Por enquanto, deixa o stop loss fixo gerenciar
        return False

    def _calculate_confidence(self, rsi: float, threshold: float, is_buy: bool) -> float:
        """
        Calcula nível de confiança do sinal baseado na distância do RSI ao threshold
        
        Args:
            rsi: Valor do RSI
            threshold: Threshold de referência
            is_buy: Se é sinal de compra
            
        Returns:
            Confiança entre 0.5 e 1.0
        """
        if is_buy:
            # Quanto mais abaixo do oversold, maior a confiança
            distance = abs(threshold - rsi)
            confidence = min(1.0, 0.5 + (distance / 20.0))
        else:
            # Quanto mais acima do overbought, maior a confiança
            distance = abs(rsi - threshold)
            confidence = min(1.0, 0.5 + (distance / 20.0))
        
        return confidence

    def get_required_indicators(self) -> Dict[str, Dict[str, Any]]:
        """
        Retorna indicadores necessários para a estratégia
        
        Returns:
            Dicionário de indicadores e parâmetros
        """
        return {
            'ema': {'length': self.ema_period},
            'rsi': {'length': self.rsi_period},
            'atr': {'length': self.atr_period}
        }
