"""Signal model for storing Telegram trading signals.

This module defines the Signal model which stores:
- Signal metadata (source, timestamp, etc.)
- Signal content (symbol, direction, etc.)
- Signal status and processing state
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID
import json

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Column
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, remote

from .base import Base
from src.common.types import SignalDirection, SignalType, SignalStatus

class Signal(Base):
    """Model for storing Telegram trading signals.
    
    Attributes:
        message_id: Original Telegram message ID
        chat_id: Telegram chat ID where signal was received
        channel_name: Name of the Telegram channel
        signal_type: Type of signal (ENTRY, EXIT, etc.)
        symbol: Trading symbol (e.g., XAUUSD)
        direction: Trade direction (LONG, SHORT)
        entry_price: Entry price for the trade
        stop_loss: Stop loss price
        take_profit: Take profit price
        risk_reward: Risk to reward ratio
        lot_size: Position size in lots
        status: Current status of signal processing
        processed_at: When signal was processed
        error_message: Error message if processing failed
        is_duplicate: Whether signal was identified as duplicate
        original_signal_id: ID of original signal if this is a duplicate
        signal_metadata: Additional signal metadata as JSON
    """
    
    __tablename__ = "signals"
    
    # Telegram metadata
    message_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True
    )
    chat_id: Mapped[int] = mapped_column(
        BigInteger,  # Use BigInteger for large Telegram chat IDs
        nullable=False,
        index=True
    )
    channel_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )
    
    # Signal content
    signal_type: Mapped[SignalType] = mapped_column(
        Enum(SignalType),
        nullable=False
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True
    )
    direction: Mapped[SignalDirection] = mapped_column(
        Enum(SignalDirection),
        nullable=False
    )
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
    risk_reward: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    lot_size: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    
    # Processing state
    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus),
        nullable=False,
        default=SignalStatus.PENDING,
        index=True
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Duplicate detection
    is_duplicate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True
    )
    original_signal_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Additional metadata
    signal_metadata: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Relationships
    trades = relationship(
        "Trade",
        back_populates="signal",
        cascade="all, delete-orphan"
    )
    
    # Self-referential relationship for duplicate signals
    original_signal = relationship(
        "Signal",
        primaryjoin="Signal.original_signal_id == remote(Signal.id)",
        backref="duplicate_signals",
        lazy="joined",
        uselist=False
    )
    
    def __repr__(self) -> str:
        """String representation of signal.
        
        Returns:
            str: String representation
        """
        return (
            f"Signal(id={self.id}, "
            f"symbol={self.symbol}, "
            f"direction={self.direction}, "
            f"status={self.status})"
        )
        
    @property
    def is_processed(self) -> bool:
        """Check if signal has been processed.
        
        Returns:
            bool: True if signal is processed
        """
        return self.processed_at is not None
        
    @property
    def is_active(self) -> bool:
        """Check if signal is active (not deleted or duplicate).
        
        Returns:
            bool: True if signal is active
        """
        return (
            self.deleted_at is None
            and not self.is_duplicate
            and self.status != SignalStatus.CANCELLED
        )
        
    def mark_as_processed(
        self,
        status: SignalStatus = SignalStatus.COMPLETED,
        error_message: Optional[str] = None
    ) -> None:
        """Mark signal as processed.
        
        Args:
            status: Processing status
            error_message: Error message if processing failed
        """
        self.status = status
        self.processed_at = datetime.now(tz=timezone.utc)
        if error_message:
            self.error_message = error_message
            
    def mark_as_duplicate(self, original_signal_id: UUID) -> None:
        """Mark signal as duplicate of another signal.
        
        Args:
            original_signal_id: ID of original signal
        """
        self.is_duplicate = True
        self.original_signal_id = original_signal_id
        self.status = SignalStatus.DUPLICATE
        self.processed_at = datetime.now(tz=timezone.utc)
        
    def to_trading_signal(self) -> "TradingSignal":
        """Convert database signal to TradingSignal model.
        
        Returns:
            TradingSignal: Trading signal representation
        """
        from src.telegram.signal_parser import TradingSignal, TakeProfit
        
        # Convert take profits from metadata if available
        take_profits = []
        if self.signal_metadata:
            try:
                metadata = json.loads(self.signal_metadata)
                if "take_profits" in metadata:
                    take_profits = [
                        TakeProfit(
                            level=tp["level"],
                            price=tp["price"],
                            pips=tp.get("pips")
                        )
                        for tp in metadata["take_profits"]
                    ]
                elif self.take_profit:  # Fallback to single take profit
                    take_profits = [TakeProfit(level=1, price=self.take_profit)]
            except (json.JSONDecodeError, KeyError):
                if self.take_profit:  # Fallback to single take profit
                    take_profits = [TakeProfit(level=1, price=self.take_profit)]
        
        return TradingSignal(
            message_id=self.message_id,
            chat_id=self.chat_id,
            channel_name=self.channel_name,
            signal_type=self.signal_type,
            symbol=self.symbol,
            direction=self.direction,
            entry_price=self.entry_price,
            stop_loss=self.stop_loss,
            take_profits=take_profits,
            risk_reward=self.risk_reward,
            lot_size=self.lot_size,
            raw_message=self.signal_metadata or "",
            created_at=self.created_at
        ) 