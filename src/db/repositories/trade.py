"""Trade repository with trade-specific operations.

This module provides:
- Trade-specific database operations
- Trade status management
- Trade querying by various criteria
- Trade statistics and analytics
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from src.db.models.trade import Trade
from src.db.repositories.base import BaseRepository
from src.mt5.types import OrderType, TradeState
from src.telegram.parser import SignalDirection

class TradeRepository(BaseRepository[Trade]):
    """Repository for trade operations.
    
    This class provides trade-specific database operations including:
    - Trade status management
    - Trade querying by various criteria
    - Trade statistics and analytics
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize trade repository.
        
        Args:
            session: Database session
        """
        super().__init__(Trade, session)
        
    async def get_by_mt5_ticket(self, ticket: int) -> Optional[Trade]:
        """Get trade by MT5 ticket number.
        
        Args:
            ticket: MT5 ticket number
            
        Returns:
            Optional[Trade]: Trade if found
        """
        return await self.get_one_by_filters(
            filters={"mt5_ticket": ticket}
        )
        
    async def get_by_mt5_position(self, position_id: int) -> Optional[Trade]:
        """Get trade by MT5 position ID.
        
        Args:
            position_id: MT5 position ID
            
        Returns:
            Optional[Trade]: Trade if found
        """
        return await self.get_one_by_filters(
            filters={"mt5_position_id": position_id}
        )
        
    async def get_active_trades(
        self,
        *,
        symbol: Optional[str] = None,
        direction: Optional[SignalDirection] = None,
        order_type: Optional[OrderType] = None
    ) -> List[Trade]:
        """Get active trades matching criteria.
        
        Args:
            symbol: Trading symbol to filter by
            direction: Trade direction to filter by
            order_type: Order type to filter by
            
        Returns:
            List[Trade]: List of active trades
        """
        filters = {}
        
        if symbol:
            filters["symbol"] = symbol
        if direction:
            filters["direction"] = direction
        if order_type:
            filters["order_type"] = order_type
            
        query = self._build_query(filters=filters)
        
        # Add active trade conditions
        query = query.where(
            and_(
                Trade.deleted_at.is_(None),
                Trade.state.in_([
                    TradeState.PENDING,
                    TradeState.OPEN,
                    TradeState.PARTIAL
                ])
            )
        )
        
        # Order by creation date
        query = query.order_by(Trade.created_at.desc())
        
        return await self.get_multi(query=query)
        
    async def get_trades_by_state(
        self,
        state: TradeState,
        *,
        min_age: Optional[timedelta] = None,
        max_age: Optional[timedelta] = None
    ) -> List[Trade]:
        """Get trades by state and age.
        
        Args:
            state: Trade state to filter by
            min_age: Minimum age of trades to return
            max_age: Maximum age of trades to return
            
        Returns:
            List[Trade]: List of trades
        """
        query = self._build_query(filters={"state": state})
        
        # Add age conditions
        if min_age or max_age:
            now = datetime.now(timezone=True)
            if min_age:
                query = query.where(
                    Trade.created_at >= now - min_age
                )
            if max_age:
                query = query.where(
                    Trade.created_at <= now - max_age
                )
                
        # Order by creation date
        query = query.order_by(Trade.created_at.desc())
        
        return await self.get_multi(query=query)
        
    async def get_trade_statistics(
        self,
        *,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Get trade statistics.
        
        Args:
            symbol: Trading symbol to filter by
            start_date: Start date for statistics
            end_date: End date for statistics
            
        Returns:
            Dict[str, float]: Dictionary of statistics
        """
        # Build base query
        query = select(Trade).where(
            and_(
                Trade.deleted_at.is_(None),
                Trade.state == TradeState.CLOSED
            )
        )
        
        # Add filters
        if symbol:
            query = query.where(Trade.symbol == symbol)
        if start_date:
            query = query.where(Trade.created_at >= start_date)
        if end_date:
            query = query.where(Trade.created_at <= end_date)
            
        # Get trades
        result = await self.session.execute(query)
        trades = list(result.scalars().all())
        
        # Calculate statistics
        total_trades = len(trades)
        if total_trades == 0:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_profit": 0.0,
                "total_commission": 0.0,
                "total_swap": 0.0,
                "net_profit": 0.0,
                "average_profit": 0.0,
                "average_loss": 0.0,
                "profit_factor": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0
            }
            
        winning_trades = [t for t in trades if t.profit > 0]
        losing_trades = [t for t in trades if t.profit <= 0]
        
        total_profit = sum(t.profit for t in trades)
        total_commission = sum(t.commission or 0 for t in trades)
        total_swap = sum(t.swap or 0 for t in trades)
        
        avg_profit = (
            sum(t.profit for t in winning_trades) / len(winning_trades)
            if winning_trades else 0.0
        )
        avg_loss = (
            sum(t.profit for t in losing_trades) / len(losing_trades)
            if losing_trades else 0.0
        )
        
        gross_profit = sum(t.profit for t in winning_trades)
        gross_loss = abs(sum(t.profit for t in losing_trades))
        
        return {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": (len(winning_trades) / total_trades) * 100,
            "total_profit": total_profit,
            "total_commission": total_commission,
            "total_swap": total_swap,
            "net_profit": total_profit - total_commission - total_swap,
            "average_profit": avg_profit,
            "average_loss": avg_loss,
            "profit_factor": gross_profit / gross_loss if gross_loss else 0.0,
            "max_profit": max(t.profit for t in trades),
            "max_loss": min(t.profit for t in trades)
        }
        
    async def get_symbol_statistics(
        self,
        symbol: str,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Tuple[int, int, float]:
        """Get symbol trade statistics.
        
        Args:
            symbol: Trading symbol to get statistics for
            start_date: Start date for statistics
            end_date: End date for statistics
            
        Returns:
            Tuple[int, int, float]: Total trades, winning trades, win rate
        """
        # Build base query
        query = select(Trade).where(
            and_(
                Trade.symbol == symbol,
                Trade.deleted_at.is_(None),
                Trade.state == TradeState.CLOSED
            )
        )
        
        # Add date range
        if start_date:
            query = query.where(Trade.created_at >= start_date)
        if end_date:
            query = query.where(Trade.created_at <= end_date)
            
        # Get trades
        result = await self.session.execute(query)
        trades = list(result.scalars().all())
        
        total_trades = len(trades)
        if total_trades == 0:
            return 0, 0, 0.0
            
        winning_trades = len([t for t in trades if t.profit > 0])
        win_rate = (winning_trades / total_trades) * 100
        
        return total_trades, winning_trades, win_rate
        
    async def cleanup_old_trades(
        self,
        max_age: timedelta,
        *,
        state: Optional[TradeState] = None
    ) -> int:
        """Clean up old trades.
        
        Args:
            max_age: Maximum age of trades to clean up
            state: Optional state to filter by
            
        Returns:
            int: Number of trades cleaned up
        """
        # Build query
        query = select(Trade).where(
            Trade.created_at <= datetime.now(timezone=True) - max_age
        )
        
        if state:
            query = query.where(Trade.state == state)
            
        # Get trades to clean up
        result = await self.session.execute(query)
        trades = list(result.scalars().all())
        
        # Soft delete trades
        for trade in trades:
            trade.soft_delete()
            
        await self.session.flush()
        return len(trades) 