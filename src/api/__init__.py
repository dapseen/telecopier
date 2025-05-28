"""FastAPI implementation for GoldMirror.

This package provides the REST API interface for:
- Signal management
- Trade execution
- Statistics and analytics
"""

from .app import app
from .models import (
    SignalBase,
    SignalCreate,
    SignalResponse,
    TradeBase,
    TradeCreate,
    TradeResponse,
    StatisticsBase,
    StatisticsCreate,
    StatisticsResponse
)

__all__ = [
    "app",
    "SignalBase",
    "SignalCreate",
    "SignalResponse",
    "TradeBase",
    "TradeCreate",
    "TradeResponse",
    "StatisticsBase",
    "StatisticsCreate",
    "StatisticsResponse"
] 