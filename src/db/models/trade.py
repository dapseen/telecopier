"""Trade model for storing MT5 trades.

This module defines the Trade model which stores:
- Trade metadata (signal reference, timestamps, etc.)
- Trade details (symbol, direction, prices, etc.)
- Trade status and execution state
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base
from src.mt5.types import OrderType, TradeState
from src.telegram.parser import SignalDirection

class Trade(Base):
    """Model for storing MT5 trades.
    
    Attributes:
        signal_id: Reference to the signal that triggered this trade
        mt5_ticket: MT5 order ticket number
        mt5_position_id: MT5 position ID
        symbol: Trading symbol (e.g., XAUUSD)
        order_type: Type of order (MARKET, LIMIT, etc.)
        direction: Trade direction (LONG, SHORT)
        volume: Position size in lots
        entry_price: Actual entry price
        stop_loss: Stop loss price
        take_profit: Take profit price
        exit_price: Actual exit price
        state: Current state of the trade
        profit: Trade profit/loss
        commission: Trade commission
        swap: Swap charges
        error_message: Error message if execution failed
        metadata: Additional trade metadata as JSON
    """
    
    __tablename__ = "trades"
    
    # Signal reference
    signal_id: Mapped[UUID] = mapped_column(
        ForeignKey("signals.id"),
        nullable=False,
        index=True
    )
    
    # MT5 metadata
    mt5_ticket: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        unique=True,
        index=True
    )
    mt5_position_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True
    )
    
    # Trade details
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True
    )
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType),
        nullable=False
    )
    direction: Mapped[SignalDirection] = mapped_column(
        Enum(SignalDirection),
        nullable=False
    )
    volume: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )
    
    # Prices
    entry_price: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )
    stop_loss: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    take_profit: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    exit_price: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    
    # Trade state
    state: Mapped[TradeState] = mapped_column(
        Enum(TradeState),
        nullable=False,
        default=TradeState.PENDING,
        index=True
    )
    
    # Financials
    profit: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    commission: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    swap: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    
    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Additional metadata
    metadata: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Relationships
    signal = relationship(
        "Signal",
        back_populates="trades"
    )
    
    def __repr__(self) -> str:
        """String representation of trade.
        
        Returns:
            str: String representation
        """
        return (
            f"Trade(id={self.id}, "
            f"symbol={self.symbol}, "
            f"direction={self.direction}, "
            f"state={self.state})"
        )
        
    @property
    def is_active(self) -> bool:
        """Check if trade is active.
        
        Returns:
            bool: True if trade is active
        """
        return (
            self.deleted_at is None
            and self.state in [
                TradeState.PENDING,
                TradeState.OPEN,
                TradeState.PARTIAL
            ]
        )
        
    @property
    def is_closed(self) -> bool:
        """Check if trade is closed.
        
        Returns:
            bool: True if trade is closed
        """
        return self.state in [
            TradeState.CLOSED,
            TradeState.CANCELLED,
            TradeState.REJECTED
        ]
        
    @property
    def total_profit(self) -> float:
        """Calculate total profit including commission and swap.
        
        Returns:
            float: Total profit/loss
        """
        if self.profit is None:
            return 0.0
            
        total = self.profit
        if self.commission:
            total -= self.commission
        if self.swap:
            total -= self.swap
        return total
        
    def update_state(
        self,
        state: TradeState,
        error_message: Optional[str] = None
    ) -> None:
        """Update trade state.
        
        Args:
            state: New trade state
            error_message: Error message if state change failed
        """
        self.state = state
        if error_message:
            self.error_message = error_message
            
    def close_trade(
        self,
        exit_price: float,
        profit: float,
        commission: Optional[float] = None,
        swap: Optional[float] = None
    ) -> None:
        """Close trade with final details.
        
        Args:
            exit_price: Final exit price
            profit: Trade profit/loss
            commission: Trade commission
            swap: Swap charges
        """
        self.exit_price = exit_price
        self.profit = profit
        self.commission = commission
        self.swap = swap
        self.state = TradeState.CLOSED
        self.updated_at = datetime.now(timezone=True) 