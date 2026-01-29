"""Strategies module initialization."""

from strategies.base import BaseStrategy, TradeSignal, SignalType
from strategies.atr_trend_follower import ATRTrendFollower

__all__ = ['BaseStrategy', 'TradeSignal', 'SignalType', 'ATRTrendFollower']