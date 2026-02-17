"""
Módulo risk - Gestão Quantitativa de Risco.

Este módulo contém:
- KellyRiskManager: Critério de Kelly Fracionário
- Dimensionamento científico de posição
- Validação multi-camada de trades
"""

from risk.manager import KellyRiskManager

__all__ = [
    'KellyRiskManager',
]

__version__ = '1.0.0'
