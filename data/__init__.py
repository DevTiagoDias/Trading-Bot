"""
Módulo data - Engenharia de Features e Filtros Quantitativos.

Este módulo contém:
- FeatureEngine: Cálculo de indicadores técnicos
- CUSUMFilter: Detecção de mudanças estruturais
- BarrierLabeler: Geração de labels para ML
"""

from data.features import FeatureEngine, CUSUMFilter, BarrierLabeler

__all__ = [
    'FeatureEngine',
    'CUSUMFilter',
    'BarrierLabeler',
]

__version__ = '1.0.0'
