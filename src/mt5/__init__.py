"""MT5 trading module.

This package provides:
- MT5 connection management
- Trade execution
- Risk management
- Platform-specific handling
"""

from .mt5_utils import is_mt5_available, is_platform_supported, get_mt5
from .connection import MT5Connection, MT5Config
from .executor import TradeExecutor, TradeResult
from ..main import RiskConfig

__all__ = [
    "MT5Connection",
    "MT5Config",
    "TradeExecutor",
    "TradeResult",
    "RiskConfig",
    "is_mt5_available",
    "is_platform_supported",
    "get_mt5"
] 