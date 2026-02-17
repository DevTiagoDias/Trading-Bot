"""
Gestão de Risco Quantitativa com Critério de Kelly.

Implementa:
- Critério de Kelly Fracionário para dimensionamento de posição
- Cálculo dinâmico de lote baseado em volatilidade
- Validação de exposição e limites de risco
"""

import math
from typing import Dict, Any, Optional
from core.logger import get_logger

logger = get_logger(__name__)


class KellyRiskManager:
    """
    Gestor de risco baseado no Critério de Kelly Fracionário.
    
    O Critério de Kelly determina a fração ótima do capital a arriscar
    em cada trade baseado na taxa de acerto esperada e no payoff ratio.
    
    Fórmula: f* = (p * b - q) / b
    Onde:
        f* = fração Kelly
        p = probabilidade de ganho
        q = probabilidade de perda (1 - p)
        b = razão ganho/perda (payoff ratio)
    
    Usamos Kelly Fracionário (tipicamente 25% do Kelly completo) para
    reduzir volatilidade e evitar superexposição.
    """
    
    def __init__(
        self,
        kelly_fraction: float = 0.25,
        max_risk_per_trade: float = 0.02,
        estimated_win_rate: float = 0.55,
        min_kelly_exposure: float = 0.01,
        max_kelly_exposure: float = 0.10
    ):
        """
        Inicializa gestor de risco Kelly.
        
        Args:
            kelly_fraction: Fração do Kelly a usar (0.25 = 25% do Kelly)
            max_risk_per_trade: Risco máximo por trade (% do capital)
            estimated_win_rate: Taxa de acerto estimada da estratégia
            min_kelly_exposure: Exposição mínima permitida
            max_kelly_exposure: Exposição máxima permitida
        """
        self.kelly_fraction = kelly_fraction
        self.max_risk_per_trade = max_risk_per_trade
        self.estimated_win_rate = estimated_win_rate
        self.min_kelly_exposure = min_kelly_exposure
        self.max_kelly_exposure = max_kelly_exposure
        
        logger.info(
            f"KellyRiskManager inicializado - "
            f"Fração: {kelly_fraction}, Max Risk: {max_risk_per_trade*100:.1f}%, "
            f"Win Rate: {estimated_win_rate*100:.1f}%"
        )
    
    def calculate_kelly_fraction(
        self,
        win_rate: Optional[float] = None,
        payoff_ratio: float = 1.5
    ) -> float:
        """
        Calcula fração de Kelly para dimensionamento.
        
        Args:
            win_rate: Taxa de acerto (se None, usa estimativa)
            payoff_ratio: Razão ganho médio / perda média
            
        Returns:
            Fração de Kelly ajustada
        """
        p = win_rate if win_rate is not None else self.estimated_win_rate
        q = 1 - p
        b = payoff_ratio
        
        # Fórmula de Kelly
        kelly = (p * b - q) / b
        
        # Kelly fracionário
        fractional_kelly = kelly * self.kelly_fraction
        
        # Aplica limites
        fractional_kelly = max(self.min_kelly_exposure, fractional_kelly)
        fractional_kelly = min(self.max_kelly_exposure, fractional_kelly)
        
        logger.debug(
            f"Kelly Calc - WinRate: {p:.2%}, Payoff: {b:.2f}, "
            f"Full Kelly: {kelly:.2%}, Fractional: {fractional_kelly:.2%}"
        )
        
        return fractional_kelly
    
    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        symbol_info: Dict[str, Any],
        win_rate: Optional[float] = None,
        payoff_ratio: float = 1.5
    ) -> Dict[str, Any]:
        """
        Calcula tamanho da posição baseado em Kelly e características do símbolo.
        
        Args:
            account_balance: Saldo da conta
            entry_price: Preço de entrada
            stop_loss: Preço de stop loss
            symbol_info: Informações do símbolo (do MT5)
            win_rate: Taxa de acerto (opcional)
            payoff_ratio: Razão ganho/perda esperada
            
        Returns:
            Dicionário com tamanho da posição e metadados
        """
        # Extrai informações do símbolo
        point = symbol_info['point']
        tick_value = symbol_info['trade_tick_value']
        tick_size = symbol_info['trade_tick_size']
        volume_min = symbol_info['volume_min']
        volume_max = symbol_info['volume_max']
        volume_step = symbol_info['volume_step']
        digits = symbol_info['digits']
        
        # Calcula distância do SL em pontos
        sl_distance_points = abs(entry_price - stop_loss) / point
        
        # Calcula risco em moeda da conta por ponto
        risk_per_point = tick_value * (point / tick_size)
        
        # Calcula risco total em moeda para 1 lote
        risk_for_one_lot = sl_distance_points * risk_per_point
        
        if risk_for_one_lot <= 0:
            logger.error("Risco calculado inválido (≤ 0)")
            return self._invalid_position()
        
        # Calcula fração de Kelly
        kelly_frac = self.calculate_kelly_fraction(win_rate, payoff_ratio)
        
        # Capital a arriscar baseado em Kelly
        kelly_risk_amount = account_balance * kelly_frac
        
        # Limita ao risco máximo permitido
        max_risk_amount = account_balance * self.max_risk_per_trade
        risk_amount = min(kelly_risk_amount, max_risk_amount)
        
        # Calcula lote baseado no risco
        calculated_volume = risk_amount / risk_for_one_lot
        
        # Arredonda para step do símbolo
        volume = self._round_to_step(calculated_volume, volume_step)
        
        # Aplica limites de volume
        volume = max(volume_min, volume)
        volume = min(volume_max, volume)
        
        # Recalcula risco real com volume ajustado
        actual_risk = volume * risk_for_one_lot
        actual_risk_pct = (actual_risk / account_balance) * 100
        
        logger.info(
            f"Position Sizing - Balance: {account_balance:.2f}, "
            f"Kelly Risk: {kelly_risk_amount:.2f} ({kelly_frac:.2%}), "
            f"Volume: {volume:.2f} lots, "
            f"Actual Risk: {actual_risk:.2f} ({actual_risk_pct:.2f}%)"
        )
        
        return {
            'volume': volume,
            'risk_amount': actual_risk,
            'risk_percentage': actual_risk_pct,
            'kelly_fraction': kelly_frac,
            'sl_distance_points': sl_distance_points,
            'risk_per_point': risk_per_point,
            'valid': True
        }
    
    def validate_trade(
        self,
        account_balance: float,
        account_equity: float,
        existing_positions: int,
        max_positions: int,
        proposed_risk: float
    ) -> Dict[str, Any]:
        """
        Valida se um novo trade pode ser aberto baseado em regras de risco.
        
        Args:
            account_balance: Saldo da conta
            account_equity: Equity da conta
            existing_positions: Número de posições abertas
            max_positions: Máximo de posições permitidas
            proposed_risk: Risco proposto para novo trade
            
        Returns:
            Dicionário com resultado da validação
        """
        validations = []
        
        # Verifica número de posições
        if existing_positions >= max_positions:
            validations.append({
                'rule': 'max_positions',
                'passed': False,
                'message': f"Máximo de {max_positions} posições atingido"
            })
        else:
            validations.append({
                'rule': 'max_positions',
                'passed': True,
                'message': f"Posições: {existing_positions}/{max_positions}"
            })
        
        # Verifica drawdown
        drawdown = ((account_balance - account_equity) / account_balance) * 100
        max_drawdown_allowed = 20.0  # 20%
        
        if drawdown > max_drawdown_allowed:
            validations.append({
                'rule': 'max_drawdown',
                'passed': False,
                'message': f"Drawdown de {drawdown:.2f}% excede limite de {max_drawdown_allowed}%"
            })
        else:
            validations.append({
                'rule': 'max_drawdown',
                'passed': True,
                'message': f"Drawdown: {drawdown:.2f}%"
            })
        
        # Verifica risco do trade
        risk_pct = (proposed_risk / account_balance) * 100
        
        if risk_pct > self.max_risk_per_trade * 100:
            validations.append({
                'rule': 'max_trade_risk',
                'passed': False,
                'message': f"Risco de {risk_pct:.2f}% excede máximo de {self.max_risk_per_trade*100:.2f}%"
            })
        else:
            validations.append({
                'rule': 'max_trade_risk',
                'passed': True,
                'message': f"Risco: {risk_pct:.2f}%"
            })
        
        # Verifica se equity está positivo
        if account_equity <= 0:
            validations.append({
                'rule': 'positive_equity',
                'passed': False,
                'message': "Equity não positivo"
            })
        else:
            validations.append({
                'rule': 'positive_equity',
                'passed': True,
                'message': f"Equity: {account_equity:.2f}"
            })
        
        # Determina se pode operar
        all_passed = all(v['passed'] for v in validations)
        
        if all_passed:
            logger.info("✓ Validação de risco APROVADA")
        else:
            failed = [v for v in validations if not v['passed']]
            logger.warning(
                f"✗ Validação de risco REJEITADA: "
                f"{', '.join(v['message'] for v in failed)}"
            )
        
        return {
            'approved': all_passed,
            'validations': validations,
            'drawdown': drawdown,
            'risk_percentage': risk_pct
        }
    
    def _round_to_step(self, value: float, step: float) -> float:
        """
        Arredonda valor para o step mais próximo.
        
        Args:
            value: Valor a arredondar
            step: Step de arredondamento
            
        Returns:
            Valor arredondado
        """
        if step == 0:
            return value
        
        return round(value / step) * step
    
    def _invalid_position(self) -> Dict[str, Any]:
        """
        Retorna estrutura de posição inválida.
        """
        return {
            'volume': 0.0,
            'risk_amount': 0.0,
            'risk_percentage': 0.0,
            'kelly_fraction': 0.0,
            'sl_distance_points': 0.0,
            'risk_per_point': 0.0,
            'valid': False
        }
    
    def calculate_payoff_ratio(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float
    ) -> float:
        """
        Calcula razão risco/recompensa (payoff ratio).
        
        Args:
            entry_price: Preço de entrada
            stop_loss: Preço de stop loss
            take_profit: Preço de take profit
            
        Returns:
            Payoff ratio (reward/risk)
        """
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        
        if risk == 0:
            return 0.0
        
        return reward / risk
