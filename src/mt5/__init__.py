"""MT5 trading module.

This module provides classes for interacting with MetaTrader 5:
- MT5Connection: Manages connection to MT5 terminal
- MT5Config: Configuration for MT5 connection
- TradeExecutor: Handles trade execution and management
- PositionManager: Manages positions and risk
- OrderRequest: Request for placing a new order
- OrderType: Types of trading orders
- OrderAction: Trading order actions
- PartialTP: Configuration for partial take profit
- BreakevenConfig: Configuration for breakeven management
- OrderModification: Request for modifying an existing order
- PositionType: Types of trading positions
- PositionStatus: Status of trading positions
- PositionInfo: Information about a trading position
- RiskConfig: Configuration for risk management
"""

from .connection import MT5Connection, MT5Config
from .trade_executor import (
    TradeExecutor,
    OrderRequest,
    OrderType,
    OrderAction,
    PartialTP,
    BreakevenConfig,
    OrderModification
)
from .position_manager import (
    PositionManager,
    PositionType,
    PositionStatus,
    PositionInfo,
    RiskConfig
)

__all__ = [
    "MT5Connection",
    "MT5Config",
    "TradeExecutor",
    "PositionManager",
    "OrderRequest",
    "OrderType",
    "OrderAction",
    "PartialTP",
    "BreakevenConfig",
    "OrderModification",
    "PositionType",
    "PositionStatus",
    "PositionInfo",
    "RiskConfig"
] 