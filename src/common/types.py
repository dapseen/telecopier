"""Common type definitions for the trading system.

This module contains shared enums and types used across different components
of the system.
"""

from enum import Enum, auto
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class SignalDirection(Enum):
    """Trading signal direction."""
    
    BUY = auto()
    SELL = auto()
    
    def __str__(self) -> str:
        """Return string representation."""
        return self.name.capitalize()


class SignalType(Enum):
    """Trading signal type."""
    
    MARKET = auto()  # Immediate execution at market price
    LIMIT = auto()   # Execution at specified price or better
    STOP = auto()    # Execution when price reaches trigger level
    
    def __str__(self) -> str:
        """Return string representation."""
        return self.name.capitalize()


class OrderType(Enum):
    """MetaTrader 5 order types."""
    
    MARKET = auto()  # Market order
    LIMIT = auto()   # Limit order
    STOP = auto()    # Stop order
    STOP_LIMIT = auto()  # Stop limit order


class TradeState(Enum):
    """Trade execution states."""
    
    PENDING = auto()      # Trade is pending execution
    EXECUTED = auto()     # Trade has been executed
    CANCELLED = auto()    # Trade was cancelled
    REJECTED = auto()     # Trade was rejected by broker
    PARTIAL = auto()      # Trade was partially filled
    EXPIRED = auto()      # Trade order expired
    ERROR = auto()        # Error occurred during execution


class SignalStatus(Enum):
    """Signal processing status."""
    
    PENDING = "PENDING"       # Signal is pending processing
    PROCESSING = "PROCESSING" # Signal is being processed
    COMPLETED = "COMPLETED"   # Signal was successfully processed
    FAILED = "FAILED"        # Signal processing failed
    DUPLICATE = "DUPLICATE"   # Signal was identified as duplicate
    CANCELLED = "CANCELLED"   # Signal was cancelled
    EXPIRED = "EXPIRED"      # Signal has expired


class SignalPriority(Enum):
    """Signal processing priority."""
    
    LOW = auto()      # Low priority signals
    NORMAL = auto()   # Normal priority signals
    HIGH = auto()     # High priority signals
    URGENT = auto()   # Urgent priority signals 