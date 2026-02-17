"""
Módulo execution - Gestão de Execução de Ordens ECN/STP.

Este módulo contém:
- OrderManager: Envio e gestão de ordens
- Tratamento automático de erros MT5 (requotes, rejeições)
- Mapeamento inteligente de filling_mode
"""

from execution.order_manager import OrderManager

__all__ = [
    'OrderManager',
]

__version__ = '1.0.0'
