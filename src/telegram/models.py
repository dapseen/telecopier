"""Data models for trading signals.

This module contains the Pydantic models used for signal parsing and validation.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from dataclasses import dataclass
from datetime import datetime

from src.common.types import SignalDirection, SignalType

@dataclass
class TakeProfit:
    """Represents a take profit level with price and optional pip calculation."""
    
    level: int
    price: float
    pips: Optional[float] = None
    
    def __post_init__(self):
        """Validate take profit values after initialization."""
        if self.level < 1:
            raise ValueError(f"Take profit level must be positive, got {self.level}")
        if self.price <= 0:
            raise ValueError(f"Take profit price must be positive, got {self.price}")
        if self.pips is not None and self.pips <= 0:
            raise ValueError(f"Take profit pips must be positive if specified, got {self.pips}")

@dataclass
class TradingSignal:
    """Represents a complete trading signal with all necessary components."""
    
    symbol: str
    direction: SignalDirection
    entry_price: float
    stop_loss: Optional[float] = None
    stop_loss_pips: Optional[float] = None
    take_profits: List[TakeProfit] = None
    signal_type: SignalType = SignalType.MARKET
    raw_message: str = ""
    additional_notes: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        """Validate signal values after initialization."""
        if not self.symbol:
            raise ValueError("Symbol cannot be empty")
            
        if self.entry_price <= 0:
            raise ValueError(f"Entry price must be positive, got {self.entry_price}")
            
        if self.stop_loss is not None and self.stop_loss <= 0:
            raise ValueError(f"Stop loss must be positive if specified, got {self.stop_loss}")
            
        if self.stop_loss_pips is not None and self.stop_loss_pips <= 0:
            raise ValueError(f"Stop loss pips must be positive if specified, got {self.stop_loss_pips}")
            
        if self.take_profits is None:
            self.take_profits = []
            
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
            
    @property
    def risk_reward_ratio(self) -> Optional[float]:
        """Calculate the risk/reward ratio for the first take profit level.
        
        Returns:
            Float representing R:R ratio if both stop loss and at least one TP are set,
            None otherwise
        """
        if not self.stop_loss or not self.take_profits:
            return None
            
        risk = abs(self.entry_price - self.stop_loss)
        if risk == 0:
            return None
            
        first_tp = self.take_profits[0]
        reward = abs(first_tp.price - self.entry_price)
        
        return reward / risk
        
    @property
    def has_valid_levels(self) -> bool:
        """Check if signal has valid price levels.
        
        Returns:
            True if entry, stop loss and at least one take profit are set with valid relationships
        """
        if not self.stop_loss or not self.take_profits:
            return False
            
        if self.direction == SignalDirection.BUY:
            # For buy signals: SL < Entry < TP
            return (self.stop_loss < self.entry_price and 
                   all(tp.price > self.entry_price for tp in self.take_profits))
                   
        else:  # SELL
            # For sell signals: TP < Entry < SL
            return (self.stop_loss > self.entry_price and 
                   all(tp.price < self.entry_price for tp in self.take_profits))
                   
    def __str__(self) -> str:
        """Return a human-readable string representation of the signal."""
        tp_str = ", ".join(f"TP{tp.level}@{tp.price}" for tp in self.take_profits)
        return (
            f"{self.symbol} {self.direction.name} @ {self.entry_price} "
            f"(SL: {self.stop_loss or 'None'}, {tp_str})"
        )

class TakeProfit(BaseModel):
    """Model for take profit levels."""
    level: int = Field(..., description="Take profit level number")
    price: float = Field(..., description="Take profit price")
    pips: Optional[int] = Field(None, description="Take profit distance in pips")

class TradingSignal(BaseModel):
    """Model for parsed trading signals."""
    message_id: int = Field(0, description="Telegram message ID")  # Default to 0
    chat_id: int = Field(0, description="Telegram chat ID")  # Default to 0
    channel_name: str = Field("default", description="Name of the Telegram channel")  # Default to "default"
    signal_type: SignalType = Field(SignalType.MARKET, description="Type of trading signal")  # Default to MARKET
    symbol: str = Field(..., description="Trading symbol (e.g., XAUUSD)")
    direction: SignalDirection = Field(..., description="Trade direction")
    entry_price: float = Field(..., description="Entry price for the trade")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    stop_loss_pips: Optional[int] = Field(None, description="Stop loss distance in pips")
    take_profits: List[TakeProfit] = Field(default_factory=list, description="Take profit levels")
    risk_reward: Optional[float] = Field(None, description="Risk to reward ratio")
    lot_size: Optional[float] = Field(None, description="Position size in lots")
    confidence_score: Optional[float] = Field(None, description="Signal confidence score")
    additional_notes: Optional[str] = Field(None, description="Additional trading notes")
    raw_message: str = Field(..., description="Raw Telegram message text") 