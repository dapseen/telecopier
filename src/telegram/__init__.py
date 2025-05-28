"""Telegram module for signal processing and management.

This module provides functionality for:
- Parsing trading signals from Telegram messages
- Managing signal queue and persistence
- Validating and processing signals
"""

from .signal_parser import SignalParser, TradingSignal, TakeProfit
from .signal_queue import SignalQueue, SignalPriority, QueueItem
from .signal_validator import SignalValidator, ValidationResult
from .signal_persistence import SignalPersistence
from .telegram_client import SignalMonitor

__all__ = [
    'SignalParser',
    'TradingSignal',
    'TakeProfit',
    'SignalQueue',
    'SignalPriority',
    'QueueItem',
    'SignalValidator',
    'ValidationResult',
    'SignalPersistence',
    'SignalMonitor'
] 