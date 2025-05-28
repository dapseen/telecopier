"""Pydantic models for API request/response validation.

This module defines the data models used for:
- Request validation
- Response serialization
- Documentation generation
"""

from datetime import datetime, date
from typing import Optional, List, Dict
from uuid import UUID

from pydantic import BaseModel, Field, validator

from src.common.types import (
    SignalDirection,
    SignalType,
    OrderType,
    TradeState,
    SignalStatus,
    SignalPriority
)

class TakeProfitModel(BaseModel):
    """Model for take profit levels."""
    level: int = Field(..., description="Take profit level number")
    price: float = Field(..., description="Take profit price")
    pips: Optional[int] = Field(None, description="Take profit distance in pips")

class SignalBase(BaseModel):
    """Base model for signal data."""
    message_id: int = Field(..., description="Telegram message ID")
    chat_id: int = Field(..., description="Telegram chat ID")
    channel_name: str = Field(..., description="Name of the Telegram channel")
    signal_type: SignalType = Field(..., description="Type of trading signal")
    symbol: str = Field(..., description="Trading symbol (e.g., XAUUSD)")
    direction: SignalDirection = Field(..., description="Trade direction")
    entry_price: float = Field(..., description="Entry price for the trade")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    stop_loss_pips: Optional[int] = Field(None, description="Stop loss distance in pips")
    take_profits: List[TakeProfitModel] = Field(default_factory=list, description="Take profit levels")
    risk_reward: Optional[float] = Field(None, description="Risk to reward ratio")
    lot_size: Optional[float] = Field(None, description="Position size in lots")
    confidence_score: Optional[float] = Field(None, description="Signal confidence score")
    additional_notes: Optional[str] = Field(None, description="Additional trading notes")

class SignalCreate(SignalBase):
    """Model for creating new signals."""
    raw_message: str = Field(..., description="Raw Telegram message text")

class SignalUpdate(BaseModel):
    """Model for updating existing signals."""
    status: Optional[str] = Field(None, description="Signal processing status")
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    priority: Optional[SignalPriority] = None

class SignalResponse(SignalBase):
    """Model for signal responses."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    status: str
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    is_duplicate: bool
    original_signal_id: Optional[UUID] = None
    priority: Optional[SignalPriority] = None
    validation_result: Optional[Dict] = None

    class Config:
        from_attributes = True

class QueueStatsResponse(BaseModel):
    """Model for queue statistics response."""
    total_queued: int = Field(..., description="Total signals queued")
    total_processed: int = Field(..., description="Total signals processed")
    total_expired: int = Field(..., description="Total signals expired")
    total_failed: int = Field(..., description="Total signals failed")
    current_queue_size: int = Field(..., description="Current queue size")
    queue_sizes_by_priority: Dict[str, int] = Field(..., description="Queue sizes by priority level")

class TradeBase(BaseModel):
    """Base model for trade data."""
    signal_id: UUID = Field(..., description="Reference to the signal")
    mt5_ticket: int = Field(..., description="MT5 order ticket number")
    symbol: str = Field(..., description="Trading symbol")
    order_type: OrderType = Field(..., description="Type of order")
    direction: SignalDirection = Field(..., description="Trade direction")
    volume: float = Field(..., description="Position size in lots")
    entry_price: float = Field(..., description="Entry price")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")

class TradeCreate(TradeBase):
    """Model for creating new trades."""
    pass

class TradeUpdate(BaseModel):
    """Model for updating existing trades."""
    state: Optional[TradeState] = None
    exit_price: Optional[float] = None
    profit: Optional[float] = None
    commission: Optional[float] = None
    swap: Optional[float] = None
    error_message: Optional[str] = None

class TradeResponse(TradeBase):
    """Model for trade responses."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    mt5_position_id: Optional[int] = None
    state: TradeState
    exit_price: Optional[float] = None
    profit: Optional[float] = None
    commission: Optional[float] = None
    swap: Optional[float] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True

class StatisticsBase(BaseModel):
    """Base model for daily statistics."""
    trading_date: date = Field(..., description="Trading date")
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    total_profit: float = Field(..., description="Total profit/loss")
    win_rate: float = Field(..., description="Win rate percentage")
    profit_factor: Optional[float] = Field(None, description="Profit factor")
    max_drawdown: Optional[float] = Field(None, description="Maximum drawdown")
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio")

class StatisticsCreate(StatisticsBase):
    """Model for creating new statistics records."""
    pass

class StatisticsResponse(StatisticsBase):
    """Model for statistics responses."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# MT5 Models
class MT5OrderCreate(BaseModel):
    """Model for creating MT5 orders."""
    symbol: str = Field(..., description="Trading symbol")
    order_type: OrderType = Field(..., description="Type of order")
    direction: str = Field(..., description="Trade direction (BUY/SELL)")
    volume: float = Field(..., gt=0, description="Position size in lots")
    price: Optional[float] = Field(None, description="Order price (required for limit/stop orders)")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    comment: str = Field("", description="Order comment")
    magic: int = Field(0, description="Magic number")

class MT5OrderResponse(BaseModel):
    """Model for MT5 order responses."""
    ticket: int = Field(..., description="Order ticket number")
    symbol: str = Field(..., description="Trading symbol")
    order_type: str = Field(..., description="Type of order")
    direction: str = Field(..., description="Trade direction")
    volume: float = Field(..., description="Position size in lots")
    price: float = Field(..., description="Order price")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    comment: str = Field(..., description="Order comment")
    magic: int = Field(..., description="Magic number")
    state: TradeState = Field(..., description="Order state")
    error: Optional[str] = Field(None, description="Error message if order failed")

class MT5PositionResponse(BaseModel):
    """Model for MT5 position responses."""
    ticket: int = Field(..., description="Position ticket number")
    symbol: str = Field(..., description="Trading symbol")
    direction: str = Field(..., description="Trade direction")
    volume: float = Field(..., description="Position size in lots")
    price: float = Field(..., description="Position open price")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    comment: str = Field(..., description="Position comment")
    magic: int = Field(..., description="Magic number")
    profit: float = Field(..., description="Current floating profit")
    swap: float = Field(..., description="Swap charges")
    commission: float = Field(..., description="Commission charges")
    open_time: datetime = Field(..., description="Position open time")

class MT5PositionModify(BaseModel):
    """Model for modifying MT5 positions."""
    stop_loss: Optional[float] = Field(None, description="New stop loss price")
    take_profit: Optional[float] = Field(None, description="New take profit price")

class MT5ConnectionStatus(BaseModel):
    """Model for MT5 connection status."""
    connected: bool = Field(..., description="Whether MT5 is connected")
    simulation_mode: bool = Field(..., description="Whether running in simulation mode")
    server: str = Field(..., description="MT5 server address")
    login: int = Field(..., description="MT5 account login")
    last_ping: Optional[datetime] = Field(None, description="Last successful ping time")
    connection_time: Optional[datetime] = Field(None, description="Connection establishment time")
    error: Optional[str] = Field(None, description="Last error message")

class MT5AccountInfo(BaseModel):
    """Model for MT5 account information."""
    balance: float = Field(..., description="Account balance")
    connected: bool = Field(..., description="Whether MT5 is connected")
    server: str = Field(..., description="MT5 server address")
    login: int = Field(..., description="MT5 account login")
    equity: Optional[float] = Field(None, description="Account equity")
    margin: Optional[float] = Field(None, description="Used margin")
    free_margin: Optional[float] = Field(None, description="Free margin")
    margin_level: Optional[float] = Field(None, description="Margin level percentage")
    leverage: Optional[int] = Field(None, description="Account leverage")
    currency: Optional[str] = Field(None, description="Account currency")
    company: Optional[str] = Field(None, description="Broker company name") 