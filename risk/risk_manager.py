"""
Risk Manager - Gestor de Risco
Módulo crítico responsável por validação de risco e cálculo de tamanho de posição
"""

import MetaTrader5 as mt5
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from core.logger import get_logger
from strategies.base import TradingSignal, SignalType


class RiskViolation(Exception):
    """Exceção levantada quando regra de risco é violada"""
    pass


class RiskManager:
    """
    Gerenciador de risco do sistema
    Valida todas as operações antes da execução
    """

    def __init__(
        self,
        risk_percent_per_trade: float = 1.0,
        max_daily_drawdown_percent: float = 3.0,
        max_position_size: float = 1.0,
        min_position_size: float = 0.01,
        max_positions: int = 5,
        use_dynamic_sizing: bool = True
    ):
        """
        Args:
            risk_percent_per_trade: Risco por operação (% do saldo)
            max_daily_drawdown_percent: Drawdown diário máximo (%)
            max_position_size: Tamanho máximo de posição (lotes)
            min_position_size: Tamanho mínimo de posição (lotes)
            max_positions: Número máximo de posições simultâneas
            use_dynamic_sizing: Usar sizing dinâmico baseado em volatilidade
        """
        self.logger = get_logger()
        
        self.risk_percent_per_trade = risk_percent_per_trade
        self.max_daily_drawdown_percent = max_daily_drawdown_percent
        self.max_position_size = max_position_size
        self.min_position_size = min_position_size
        self.max_positions = max_positions
        self.use_dynamic_sizing = use_dynamic_sizing
        
        # Estado interno
        self.daily_start_balance: Optional[float] = None
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.circuit_breaker_active = False
        
        self.logger.info("=" * 80)
        self.logger.info("Risk Manager Inicializado")
        self.logger.info(f"Risco por Trade: {risk_percent_per_trade}%")
        self.logger.info(f"Drawdown Diário Máximo: {max_daily_drawdown_percent}%")
        self.logger.info(f"Tamanho Posição: {min_position_size} - {max_position_size} lotes")
        self.logger.info(f"Max Posições: {max_positions}")
        self.logger.info(f"Sizing Dinâmico: {'ATIVO' if use_dynamic_sizing else 'DESATIVADO'}")
        self.logger.info("=" * 80)

    def initialize(self) -> bool:
        """
        Inicializa o gerenciador de risco
        Obtém saldo inicial do dia
        
        Returns:
            True se inicialização bem sucedida
        """
        account_info = mt5.account_info()
        if account_info is None:
            self.logger.error("Falha ao obter informações da conta")
            return False

        self.daily_start_balance = account_info.balance
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        self.logger.info(f"Saldo inicial do dia: ${self.daily_start_balance:,.2f}")
        
        return True

    def reset_daily_metrics(self) -> None:
        """Reseta métricas diárias (chamado no início de cada dia)"""
        account_info = mt5.account_info()
        if account_info is not None:
            self.daily_start_balance = account_info.balance
            self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            self.circuit_breaker_active = False
            
            self.logger.info("=" * 80)
            self.logger.info("RESET DIÁRIO DE RISCO")
            self.logger.info(f"Novo saldo base: ${self.daily_start_balance:,.2f}")
            self.logger.info("Circuit Breaker DESATIVADO")
            self.logger.info("=" * 80)

    def validate_signal(self, signal: TradingSignal) -> Tuple[bool, str]:
        """
        Valida sinal contra regras de risco
        
        Args:
            signal: Sinal a validar
            
        Returns:
            Tupla (válido, razão)
        """
        # Verifica circuit breaker
        if self.circuit_breaker_active:
            return False, "Circuit Breaker ATIVO - Trading bloqueado"

        # Verifica drawdown diário
        dd_check, dd_reason = self._check_daily_drawdown()
        if not dd_check:
            return False, dd_reason

        # Verifica número máximo de posições
        positions_check, positions_reason = self._check_max_positions()
        if not positions_check:
            return False, positions_reason

        # Verifica se há margem suficiente
        margin_check, margin_reason = self._check_margin_available(signal)
        if not margin_check:
            return False, margin_reason

        return True, "OK"

    def calculate_position_size(
        self,
        symbol: str,
        signal: TradingSignal,
        account_balance: Optional[float] = None
    ) -> Optional[float]:
        """
        Calcula tamanho da posição baseado em risco
        
        FÓRMULA: Lotes = (Saldo * Risco%) / (Distância_SL_Pontos * Valor_do_Ponto)
        
        Args:
            symbol: Símbolo
            signal: Sinal de trading
            account_balance: Saldo da conta (None para obter automaticamente)
            
        Returns:
            Volume em lotes ou None se erro
        """
        try:
            # Obtém informações da conta
            if account_balance is None:
                account_info = mt5.account_info()
                if account_info is None:
                    self.logger.error("Falha ao obter informações da conta")
                    return None
                account_balance = account_info.balance

            # Obtém informações do símbolo
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                self.logger.error(f"Falha ao obter informações de {symbol}")
                return None

            # Verifica se stop loss está definido
            if signal.stop_loss is None or signal.stop_loss == 0:
                self.logger.warning(f"Stop loss não definido para {symbol}, usando default")
                # Usa 1% do preço como stop loss padrão
                if signal.signal_type == SignalType.BUY:
                    signal.stop_loss = signal.price * 0.99
                else:
                    signal.stop_loss = signal.price * 1.01

            # Calcula distância do stop loss em pontos
            if signal.signal_type == SignalType.BUY:
                sl_distance_price = signal.price - signal.stop_loss
            else:
                sl_distance_price = signal.stop_loss - signal.price

            # Converte para pontos
            point = symbol_info.point
            sl_distance_points = sl_distance_price / point

            if sl_distance_points <= 0:
                self.logger.error(f"Distância de SL inválida: {sl_distance_points}")
                return None

            # Obtém valor do tick
            tick_value = self._get_tick_value(symbol_info)
            if tick_value is None or tick_value <= 0:
                self.logger.error(f"Tick value inválido para {symbol}: {tick_value}")
                return None

            # Calcula valor do ponto
            tick_size = symbol_info.trade_tick_size
            point_value = (tick_value / tick_size) * point

            # Calcula risco monetário
            risk_amount = account_balance * (self.risk_percent_per_trade / 100.0)

            # FÓRMULA PRINCIPAL
            volume = risk_amount / (sl_distance_points * point_value)

            # Normaliza volume
            volume = self._normalize_volume(volume, symbol_info)

            # Aplica limites
            volume = max(self.min_position_size, min(volume, self.max_position_size))

            # Ajuste dinâmico baseado em volatilidade (se ativado)
            if self.use_dynamic_sizing and 'atr' in signal.metadata:
                atr = signal.metadata['atr']
                volume = self._adjust_for_volatility(volume, atr, symbol_info)

            # Log detalhado
            self.logger.info("=" * 80)
            self.logger.info("CÁLCULO DE POSIÇÃO")
            self.logger.info(f"Símbolo: {symbol}")
            self.logger.info(f"Saldo: ${account_balance:,.2f}")
            self.logger.info(f"Risco: {self.risk_percent_per_trade}% = ${risk_amount:,.2f}")
            self.logger.info(f"Preço Entrada: {signal.price:.5f}")
            self.logger.info(f"Stop Loss: {signal.stop_loss:.5f}")
            self.logger.info(f"Distância SL: {sl_distance_price:.5f} ({sl_distance_points:.0f} pontos)")
            self.logger.info(f"Valor do Ponto: ${point_value:.5f}")
            self.logger.info(f"Volume Calculado: {volume:.2f} lotes")
            self.logger.info("=" * 80)

            return volume

        except Exception as e:
            self.logger.error(f"Erro no cálculo de posição: {str(e)}", exc_info=True)
            return None

    def _check_daily_drawdown(self) -> Tuple[bool, str]:
        """
        Verifica se drawdown diário foi ultrapassado
        
        Returns:
            Tupla (ok, razão)
        """
        if self.daily_start_balance is None:
            self.logger.warning("Saldo inicial não definido, tentando obter")
            if not self.initialize():
                return False, "Falha ao obter saldo inicial"

        account_info = mt5.account_info()
        if account_info is None:
            return False, "Falha ao obter informações da conta"

        current_balance = account_info.balance
        daily_pnl = current_balance - self.daily_start_balance
        daily_pnl_percent = (daily_pnl / self.daily_start_balance) * 100

        if daily_pnl_percent <= -self.max_daily_drawdown_percent:
            # Ativa circuit breaker
            self.circuit_breaker_active = True
            
            msg = (
                f"CIRCUIT BREAKER ATIVADO! "
                f"Drawdown diário: {daily_pnl_percent:.2f}% "
                f"(Limite: {self.max_daily_drawdown_percent}%) | "
                f"Perda: ${abs(daily_pnl):,.2f}"
            )
            
            self.logger.error("=" * 80)
            self.logger.error(msg)
            self.logger.error("Trading BLOQUEADO até reset diário")
            self.logger.error("=" * 80)
            
            return False, msg

        return True, "OK"

    def _check_max_positions(self) -> Tuple[bool, str]:
        """
        Verifica número de posições abertas
        
        Returns:
            Tupla (ok, razão)
        """
        positions = mt5.positions_get()
        if positions is None:
            positions = []

        num_positions = len(positions)

        if num_positions >= self.max_positions:
            msg = f"Máximo de posições atingido: {num_positions}/{self.max_positions}"
            self.logger.warning(msg)
            return False, msg

        return True, "OK"

    def _check_margin_available(self, signal: TradingSignal) -> Tuple[bool, str]:
        """
        Verifica se há margem suficiente
        
        Args:
            signal: Sinal a verificar
            
        Returns:
            Tupla (ok, razão)
        """
        account_info = mt5.account_info()
        if account_info is None:
            return False, "Falha ao obter informações da conta"

        margin_free = account_info.margin_free

        # Margem mínima recomendada: 30% da margem livre
        min_margin_required = margin_free * 0.3

        # Estima margem necessária (simplificado)
        # Em produção, use mt5.order_calc_margin()
        
        if margin_free < min_margin_required:
            msg = f"Margem livre insuficiente: ${margin_free:,.2f} < ${min_margin_required:,.2f}"
            self.logger.warning(msg)
            return False, msg

        return True, "OK"

    def _get_tick_value(self, symbol_info) -> Optional[float]:
        """
        Obtém valor do tick em tempo real
        Essencial para pares cruzados e índices
        
        Args:
            symbol_info: Informações do símbolo
            
        Returns:
            Valor do tick ou None
        """
        try:
            # Tenta obter valor do tick diretamente
            tick_value = symbol_info.trade_tick_value
            
            if tick_value is None or tick_value <= 0:
                # Fallback: calcula baseado em contract size
                contract_size = symbol_info.trade_contract_size
                tick_size = symbol_info.trade_tick_size
                
                # Para Forex
                if symbol_info.trade_calc_mode == mt5.SYMBOL_CALC_MODE_FOREX:
                    tick_value = contract_size * tick_size
                # Para outros instrumentos
                else:
                    tick_value = tick_size
            
            return tick_value
            
        except Exception as e:
            self.logger.error(f"Erro ao obter tick value: {str(e)}")
            return None

    def _normalize_volume(self, volume: float, symbol_info) -> float:
        """Normaliza volume conforme especificações do símbolo"""
        min_volume = symbol_info.volume_min
        max_volume = symbol_info.volume_max
        volume_step = symbol_info.volume_step

        volume = max(min_volume, min(volume, max_volume))
        volume = round(volume / volume_step) * volume_step
        
        return round(volume, 2)

    def _adjust_for_volatility(
        self,
        volume: float,
        atr: float,
        symbol_info
    ) -> float:
        """
        Ajusta tamanho baseado em volatilidade (ATR)
        
        Args:
            volume: Volume calculado
            atr: Valor do ATR
            symbol_info: Informações do símbolo
            
        Returns:
            Volume ajustado
        """
        # Normaliza ATR como % do preço
        tick = mt5.symbol_info_tick(symbol_info.name)
        if tick is None:
            return volume

        current_price = (tick.bid + tick.ask) / 2
        atr_percent = (atr / current_price) * 100

        # Se volatilidade muito alta (ATR > 2%), reduz posição
        if atr_percent > 2.0:
            adjustment_factor = 0.7  # Reduz 30%
            adjusted_volume = volume * adjustment_factor
            
            self.logger.info(
                f"Volatilidade alta (ATR {atr_percent:.2f}%), "
                f"reduzindo posição: {volume:.2f} -> {adjusted_volume:.2f}"
            )
            
            return self._normalize_volume(adjusted_volume, symbol_info)

        # Se volatilidade muito baixa (ATR < 0.5%), pode aumentar
        elif atr_percent < 0.5:
            adjustment_factor = 1.2  # Aumenta 20%
            adjusted_volume = min(volume * adjustment_factor, self.max_position_size)
            
            self.logger.info(
                f"Volatilidade baixa (ATR {atr_percent:.2f}%), "
                f"aumentando posição: {volume:.2f} -> {adjusted_volume:.2f}"
            )
            
            return self._normalize_volume(adjusted_volume, symbol_info)

        return volume

    def get_risk_metrics(self) -> Dict[str, Any]:
        """
        Retorna métricas de risco atuais
        
        Returns:
            Dicionário com métricas
        """
        account_info = mt5.account_info()
        if account_info is None:
            return {}

        positions = mt5.positions_get()
        num_positions = len(positions) if positions else 0

        daily_pnl = 0
        daily_pnl_percent = 0
        
        if self.daily_start_balance is not None:
            daily_pnl = account_info.balance - self.daily_start_balance
            daily_pnl_percent = (daily_pnl / self.daily_start_balance) * 100

        return {
            'balance': account_info.balance,
            'equity': account_info.equity,
            'margin_free': account_info.margin_free,
            'margin_level': account_info.margin_level if account_info.margin != 0 else 0,
            'daily_start_balance': self.daily_start_balance,
            'daily_pnl': daily_pnl,
            'daily_pnl_percent': daily_pnl_percent,
            'num_positions': num_positions,
            'max_positions': self.max_positions,
            'circuit_breaker_active': self.circuit_breaker_active,
            'risk_percent_per_trade': self.risk_percent_per_trade,
            'max_daily_drawdown_percent': self.max_daily_drawdown_percent
        }

    def log_risk_status(self) -> None:
        """Loga status de risco atual"""
        metrics = self.get_risk_metrics()
        
        self.logger.info("=" * 80)
        self.logger.info("STATUS DE RISCO")
        self.logger.info(f"Saldo: ${metrics.get('balance', 0):,.2f} | Equity: ${metrics.get('equity', 0):,.2f}")
        self.logger.info(f"Margem Livre: ${metrics.get('margin_free', 0):,.2f} | Nível: {metrics.get('margin_level', 0):.2f}%")
        self.logger.info(f"P&L Diário: ${metrics.get('daily_pnl', 0):,.2f} ({metrics.get('daily_pnl_percent', 0):.2f}%)")
        self.logger.info(f"Posições: {metrics.get('num_positions', 0)}/{metrics.get('max_positions', 0)}")
        self.logger.info(f"Circuit Breaker: {'ATIVO ⚠️' if metrics.get('circuit_breaker_active') else 'Inativo'}")
        self.logger.info("=" * 80)
