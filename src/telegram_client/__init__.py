"""
Telegram client module for GoldMirror trading automation.
Handles signal reception, parsing, and validation from Telegram channels.
"""

from .client import SignalMonitor

__all__ = ["SignalMonitor"] 