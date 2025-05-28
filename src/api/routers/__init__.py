"""API routers package.

This package provides FastAPI routers for:
- Signal management
- Trade execution
- Statistics and analytics
"""

from . import signals, trades, statistics

__all__ = [
    "signals",
    "trades",
    "statistics"
] 