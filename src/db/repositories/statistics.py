"""Statistics repository with statistics-specific operations.

This module provides:
- Statistics-specific database operations
- Daily statistics management
- Performance metrics calculation
- Historical data analysis
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from src.db.models.statistics import DailyStatistics
from src.db.repositories.base import BaseRepository

class StatisticsRepository(BaseRepository[DailyStatistics]):
    """Repository for statistics operations.
    
    This class provides statistics-specific database operations including:
    - Daily statistics management
    - Performance metrics calculation
    - Historical data analysis
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize statistics repository.
        
        Args:
            session: Database session
        """
        super().__init__(DailyStatistics, session)
        
    async def get_by_date(self, date: date) -> Optional[DailyStatistics]:
        """Get statistics by date.
        
        Args:
            date: Statistics date
            
        Returns:
            Optional[DailyStatistics]: Statistics if found
        """
        return await self.get_one_by_filters(
            filters={"date": date}
        )
        
    async def get_date_range(
        self,
        start_date: date,
        end_date: date
    ) -> List[DailyStatistics]:
        """Get statistics for date range.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            List[DailyStatistics]: List of statistics
        """
        query = self._build_query(
            filters={
                "date": and_(
                    DailyStatistics.date >= start_date,
                    DailyStatistics.date <= end_date
                )
            }
        )
        
        # Order by date
        query = query.order_by(DailyStatistics.date)
        
        return await self.get_multi(query=query)
        
    async def get_latest_statistics(
        self,
        days: int = 30
    ) -> List[DailyStatistics]:
        """Get latest statistics.
        
        Args:
            days: Number of days to get
            
        Returns:
            List[DailyStatistics]: List of statistics
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        return await self.get_date_range(start_date, end_date)
        
    async def get_performance_metrics(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, float]:
        """Get performance metrics for date range.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            Dict[str, float]: Dictionary of metrics
        """
        # Build base query
        query = select(DailyStatistics)
        
        # Add date range
        if start_date:
            query = query.where(DailyStatistics.date >= start_date)
        if end_date:
            query = query.where(DailyStatistics.date <= end_date)
            
        # Get statistics
        result = await self.session.execute(query)
        stats = list(result.scalars().all())
        
        if not stats:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_profit": 0.0,
                "net_profit": 0.0,
                "average_profit": 0.0,
                "average_loss": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
                "recovery_factor": 0.0,
                "sharpe_ratio": 0.0
            }
            
        # Calculate metrics
        total_trades = sum(s.total_trades for s in stats)
        winning_trades = sum(s.winning_trades for s in stats)
        losing_trades = sum(s.losing_trades for s in stats)
        
        total_profit = sum(s.total_profit for s in stats)
        total_commission = sum(s.total_commission for s in stats)
        total_swap = sum(s.total_swap for s in stats)
        
        # Calculate drawdown
        balance = 0.0
        peak = 0.0
        max_drawdown = 0.0
        
        for stat in sorted(stats, key=lambda s: s.date):
            balance += stat.net_profit
            peak = max(peak, balance)
            drawdown = peak - balance
            max_drawdown = max(max_drawdown, drawdown)
            
        # Calculate recovery factor
        gross_profit = sum(s.gross_profit for s in stats)
        gross_loss = sum(s.gross_loss for s in stats)
        
        recovery_factor = (
            gross_profit / max_drawdown
            if max_drawdown > 0 else 0.0
        )
        
        # Calculate Sharpe ratio (assuming risk-free rate of 0)
        returns = [s.net_profit for s in stats if s.net_profit != 0]
        if returns:
            avg_return = sum(returns) / len(returns)
            std_dev = (
                sum((r - avg_return) ** 2 for r in returns) / len(returns)
            ) ** 0.5
            sharpe_ratio = (
                avg_return / std_dev * (252 ** 0.5)
                if std_dev > 0 else 0.0
            )
        else:
            sharpe_ratio = 0.0
            
        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": (winning_trades / total_trades * 100)
                if total_trades > 0 else 0.0,
            "total_profit": total_profit,
            "net_profit": total_profit - total_commission - total_swap,
            "average_profit": (
                sum(s.average_profit or 0 for s in stats) / len(stats)
                if stats else 0.0
            ),
            "average_loss": (
                sum(s.average_loss or 0 for s in stats) / len(stats)
                if stats else 0.0
            ),
            "profit_factor": (
                gross_profit / gross_loss
                if gross_loss > 0 else 0.0
            ),
            "max_drawdown": max_drawdown,
            "recovery_factor": recovery_factor,
            "sharpe_ratio": sharpe_ratio
        }
        
    async def get_symbol_performance(
        self,
        symbol: str,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, float]:
        """Get symbol performance metrics.
        
        Args:
            symbol: Trading symbol
            start_date: Start date
            end_date: End date
            
        Returns:
            Dict[str, float]: Dictionary of metrics
        """
        # Build base query
        query = select(DailyStatistics).where(
            DailyStatistics.metadata.like(f'%"symbol": "{symbol}"%')
        )
        
        # Add date range
        if start_date:
            query = query.where(DailyStatistics.date >= start_date)
        if end_date:
            query = query.where(DailyStatistics.date <= end_date)
            
        # Get statistics
        result = await self.session.execute(query)
        stats = list(result.scalars().all())
        
        if not stats:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_profit": 0.0,
                "net_profit": 0.0,
                "average_profit": 0.0,
                "average_loss": 0.0,
                "profit_factor": 0.0
            }
            
        # Calculate metrics
        total_trades = sum(s.total_trades for s in stats)
        winning_trades = sum(s.winning_trades for s in stats)
        losing_trades = sum(s.losing_trades for s in stats)
        
        total_profit = sum(s.total_profit for s in stats)
        total_commission = sum(s.total_commission for s in stats)
        total_swap = sum(s.total_swap for s in stats)
        
        gross_profit = sum(s.gross_profit for s in stats)
        gross_loss = sum(s.gross_loss for s in stats)
        
        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": (winning_trades / total_trades * 100)
                if total_trades > 0 else 0.0,
            "total_profit": total_profit,
            "net_profit": total_profit - total_commission - total_swap,
            "average_profit": (
                sum(s.average_profit or 0 for s in stats) / len(stats)
                if stats else 0.0
            ),
            "average_loss": (
                sum(s.average_loss or 0 for s in stats) / len(stats)
                if stats else 0.0
            ),
            "profit_factor": (
                gross_profit / gross_loss
                if gross_loss > 0 else 0.0
            )
        }
        
    async def cleanup_old_statistics(
        self,
        max_age: timedelta
    ) -> int:
        """Clean up old statistics.
        
        Args:
            max_age: Maximum age of statistics to clean up
            
        Returns:
            int: Number of statistics cleaned up
        """
        # Build query
        query = select(DailyStatistics).where(
            DailyStatistics.date <= date.today() - max_age
        )
        
        # Get statistics to clean up
        result = await self.session.execute(query)
        stats = list(result.scalars().all())
        
        # Soft delete statistics
        for stat in stats:
            stat.soft_delete()
            
        await self.session.flush()
        return len(stats) 