"""Daily statistics model for storing trading performance metrics.

This module defines the DailyStatistics model which stores:
- Daily trading performance metrics
- Win/loss statistics
- Risk metrics
- Profit/loss analysis
"""

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Integer,
    String
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base

class DailyStatistics(Base):
    """Model for storing daily trading statistics.
    
    Attributes:
        date: Trading date
        total_trades: Total number of trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        total_profit: Total profit/loss
        total_commission: Total commission paid
        total_swap: Total swap charges
        max_profit: Maximum profit in a single trade
        max_loss: Maximum loss in a single trade
        average_profit: Average profit per trade
        average_loss: Average loss per trade
        win_rate: Win rate percentage
        profit_factor: Profit factor (gross profit / gross loss)
        average_risk_reward: Average risk to reward ratio
        max_drawdown: Maximum drawdown
        recovery_factor: Recovery factor
        sharpe_ratio: Sharpe ratio
        metadata: Additional statistics metadata
    """
    
    __tablename__ = "daily_statistics"
    
    # Date
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        unique=True,
        index=True
    )
    
    # Trade counts
    total_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    winning_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    losing_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    
    # Financials
    total_profit: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0
    )
    total_commission: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0
    )
    total_swap: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0
    )
    
    # Trade metrics
    max_profit: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    max_loss: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    average_profit: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    average_loss: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    
    # Performance metrics
    win_rate: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    profit_factor: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    average_risk_reward: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    
    # Risk metrics
    max_drawdown: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    recovery_factor: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    
    # Additional metadata
    metadata: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True
    )
    
    def __repr__(self) -> str:
        """String representation of daily statistics.
        
        Returns:
            str: String representation
        """
        return (
            f"DailyStatistics(date={self.date}, "
            f"total_trades={self.total_trades}, "
            f"total_profit={self.total_profit})"
        )
        
    @property
    def net_profit(self) -> float:
        """Calculate net profit after commission and swap.
        
        Returns:
            float: Net profit/loss
        """
        return (
            self.total_profit
            - self.total_commission
            - self.total_swap
        )
        
    @property
    def gross_profit(self) -> float:
        """Calculate gross profit from winning trades.
        
        Returns:
            float: Gross profit
        """
        if self.average_profit is None:
            return 0.0
        return self.average_profit * self.winning_trades
        
    @property
    def gross_loss(self) -> float:
        """Calculate gross loss from losing trades.
        
        Returns:
            float: Gross loss
        """
        if self.average_loss is None:
            return 0.0
        return abs(self.average_loss * self.losing_trades)
        
    def update_metrics(self) -> None:
        """Update derived metrics based on current values."""
        # Update win rate
        if self.total_trades > 0:
            self.win_rate = (self.winning_trades / self.total_trades) * 100
            
        # Update profit factor
        if self.gross_loss > 0:
            self.profit_factor = self.gross_profit / self.gross_loss
            
        # Update averages
        if self.winning_trades > 0:
            self.average_profit = self.gross_profit / self.winning_trades
        if self.losing_trades > 0:
            self.average_loss = self.gross_loss / self.losing_trades
            
    def add_trade(
        self,
        profit: float,
        commission: float,
        swap: float,
        risk_reward: Optional[float] = None
    ) -> None:
        """Add a trade to the daily statistics.
        
        Args:
            profit: Trade profit/loss
            commission: Trade commission
            swap: Swap charges
            risk_reward: Risk to reward ratio
        """
        self.total_trades += 1
        self.total_profit += profit
        self.total_commission += commission
        self.total_swap += swap
        
        if profit > 0:
            self.winning_trades += 1
            if self.max_profit is None or profit > self.max_profit:
                self.max_profit = profit
        else:
            self.losing_trades += 1
            if self.max_loss is None or profit < self.max_loss:
                self.max_loss = profit
                
        if risk_reward is not None:
            if self.average_risk_reward is None:
                self.average_risk_reward = risk_reward
            else:
                self.average_risk_reward = (
                    (self.average_risk_reward * (self.total_trades - 1) + risk_reward)
                    / self.total_trades
                )
                
        self.update_metrics() 