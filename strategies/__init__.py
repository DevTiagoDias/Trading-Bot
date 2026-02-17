"""
Módulo strategies - Lógica de Inteligência Artificial para Trading.

Este módulo contém:
- PrimaryStrategy: Seguidor de tendência (EMA + RSI)
- MetaLabeler: RandomForest para meta-labeling
- AITradingLogic: Orquestrador da IA
"""

from strategies.ai_logic import PrimaryStrategy, MetaLabeler, AITradingLogic

__all__ = [
    'PrimaryStrategy',
    'MetaLabeler',
    'AITradingLogic',
]

__version__ = '1.0.0'
