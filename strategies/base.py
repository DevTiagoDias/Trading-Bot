"""
Classe Base Abstrata para Estratégias de Trading
Define interface padrão que todas as estratégias devem implementar
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional, Dict, Any, Tuple
from enum import Enum
from core.logger import get_logger


class SignalType(Enum):
    """Tipos de sinais de trading"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE_BUY = "CLOSE_BUY"
    CLOSE_SELL = "CLOSE_SELL"


class TradingSignal:
    """
    Classe para representar um sinal de trading
    """
    
    def __init__(
        self,
        symbol: str,
        signal_type: SignalType,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        confidence: float = 1.0,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            symbol: Símbolo do ativo
            signal_type: Tipo de sinal (BUY, SELL, HOLD)
            price: Preço de referência
            stop_loss: Preço de stop loss
            take_profit: Preço de take profit
            confidence: Nível de confiança (0-1)
            reason: Razão do sinal
            metadata: Metadados adicionais
        """
        self.symbol = symbol
        self.signal_type = signal_type
        self.price = price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.confidence = confidence
        self.reason = reason
        self.metadata = metadata or {}

    def is_entry_signal(self) -> bool:
        """Verifica se é um sinal de entrada"""
        return self.signal_type in [SignalType.BUY, SignalType.SELL]

    def is_exit_signal(self) -> bool:
        """Verifica se é um sinal de saída"""
        return self.signal_type in [SignalType.CLOSE_BUY, SignalType.CLOSE_SELL]

    def __repr__(self) -> str:
        return (
            f"TradingSignal({self.symbol}, {self.signal_type.value}, "
            f"price={self.price:.5f}, SL={self.stop_loss}, TP={self.take_profit})"
        )


class BaseStrategy(ABC):
    """
    Classe base abstrata para todas as estratégias de trading
    Força implementação de métodos essenciais
    """

    def __init__(self, name: str, parameters: Dict[str, Any]):
        """
        Args:
            name: Nome da estratégia
            parameters: Parâmetros de configuração
        """
        self.name = name
        self.parameters = parameters
        self.logger = get_logger()
        self.is_initialized = False
        
        self.logger.info(f"Estratégia '{name}' criada com parâmetros: {parameters}")

    @abstractmethod
    def initialize(self) -> bool:
        """
        Inicializa a estratégia
        Deve ser implementado pela estratégia concreta
        
        Returns:
            True se inicialização bem sucedida
        """
        pass

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame, symbol: str) -> Optional[TradingSignal]:
        """
        Gera sinal de trading baseado nos dados
        MÉTODO PRINCIPAL que deve ser implementado
        
        Args:
            data: DataFrame com dados OHLCV e indicadores
            symbol: Símbolo sendo analisado
            
        Returns:
            TradingSignal ou None se não houver sinal
        """
        pass

    @abstractmethod
    def on_tick(self, symbol: str, bid: float, ask: float) -> Optional[TradingSignal]:
        """
        Processa tick individual (opcional, mas deve ser declarado)
        
        Args:
            symbol: Símbolo
            bid: Preço bid
            ask: Preço ask
            
        Returns:
            TradingSignal ou None
        """
        pass

    @abstractmethod
    def should_close_position(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        position_type: str
    ) -> bool:
        """
        Verifica se deve fechar posição existente
        
        Args:
            symbol: Símbolo
            entry_price: Preço de entrada
            current_price: Preço atual
            position_type: 'BUY' ou 'SELL'
            
        Returns:
            True se deve fechar
        """
        pass

    def validate_signal(self, signal: TradingSignal) -> bool:
        """
        Valida um sinal gerado
        
        Args:
            signal: Sinal a validar
            
        Returns:
            True se sinal válido
        """
        if signal is None:
            return False

        # Validações básicas
        if signal.price <= 0:
            self.logger.warning(f"Sinal inválido: preço <= 0")
            return False

        if signal.stop_loss is not None:
            if signal.signal_type == SignalType.BUY and signal.stop_loss >= signal.price:
                self.logger.warning("Stop loss de compra deve ser menor que preço")
                return False
            
            if signal.signal_type == SignalType.SELL and signal.stop_loss <= signal.price:
                self.logger.warning("Stop loss de venda deve ser maior que preço")
                return False

        if signal.take_profit is not None:
            if signal.signal_type == SignalType.BUY and signal.take_profit <= signal.price:
                self.logger.warning("Take profit de compra deve ser maior que preço")
                return False
            
            if signal.signal_type == SignalType.SELL and signal.take_profit >= signal.price:
                self.logger.warning("Take profit de venda deve ser menor que preço")
                return False

        return True

    def get_parameter(self, key: str, default: Any = None) -> Any:
        """
        Obtém parâmetro de configuração
        
        Args:
            key: Chave do parâmetro
            default: Valor padrão se não encontrado
            
        Returns:
            Valor do parâmetro
        """
        return self.parameters.get(key, default)

    def update_parameter(self, key: str, value: Any) -> None:
        """
        Atualiza parâmetro de configuração
        
        Args:
            key: Chave do parâmetro
            value: Novo valor
        """
        old_value = self.parameters.get(key)
        self.parameters[key] = value
        self.logger.info(f"Parâmetro '{key}' atualizado: {old_value} -> {value}")

    def calculate_stop_loss(
        self,
        entry_price: float,
        signal_type: SignalType,
        atr: float,
        multiplier: float = 2.0
    ) -> float:
        """
        Calcula stop loss baseado em ATR
        
        Args:
            entry_price: Preço de entrada
            signal_type: Tipo de sinal
            atr: Valor do ATR
            multiplier: Multiplicador do ATR
            
        Returns:
            Preço de stop loss
        """
        if signal_type == SignalType.BUY:
            return entry_price - (atr * multiplier)
        else:
            return entry_price + (atr * multiplier)

    def calculate_take_profit(
        self,
        entry_price: float,
        signal_type: SignalType,
        atr: float,
        multiplier: float = 3.0
    ) -> float:
        """
        Calcula take profit baseado em ATR
        
        Args:
            entry_price: Preço de entrada
            signal_type: Tipo de sinal
            atr: Valor do ATR
            multiplier: Multiplicador do ATR
            
        Returns:
            Preço de take profit
        """
        if signal_type == SignalType.BUY:
            return entry_price + (atr * multiplier)
        else:
            return entry_price - (atr * multiplier)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"
