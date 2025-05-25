"""Data models for trading signals.

This module contains the data classes used to represent trading signals
and their components.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class TakeProfit:
    """Represents a take profit level with price and pip value."""
    level: int
    price: float
    pips: Optional[int] = None

@dataclass
class TradingSignal:
    """Represents a parsed trading signal with all its components."""
    symbol: str
    direction: str  # 'buy' or 'sell'
    entry_price: float
    stop_loss: float
    stop_loss_pips: Optional[int]
    take_profits: List[TakeProfit]
    timestamp: datetime
    raw_message: str
    confidence_score: float
    additional_notes: Optional[str] = None 