"""Signal repository for database operations.

This module provides database operations for signal management.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.expression import true, false

from ..models.signal import Signal
from .base import BaseRepository
from src.common.types import SignalDirection, SignalType, SignalStatus

class SignalRepository(BaseRepository[Signal]):
    """Repository for signal operations.
    
    This class provides signal-specific database operations including:
    - Duplicate signal detection
    - Signal status management
    - Signal querying by various criteria
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize signal repository.
        
        Args:
            session: Database session
        """
        super().__init__(Signal, session)
        
    async def get_by_message_id(
        self,
        message_id: int,
        chat_id: int
    ) -> Optional[Signal]:
        """Get signal by Telegram message ID.
        
        Args:
            message_id: Telegram message ID
            chat_id: Telegram chat ID
            
        Returns:
            Optional[Signal]: Signal if found
        """
        return await self.get_one_by_filters(
            filters={
                "message_id": message_id,
                "chat_id": chat_id
            }
        )
        
    async def get_active_signals(
        self,
        *,
        symbol: Optional[str] = None,
        direction: Optional[SignalDirection] = None,
        signal_type: Optional[SignalType] = None,
        channel_name: Optional[str] = None,
        max_age: Optional[timedelta] = None
    ) -> List[Signal]:
        """Get active signals matching criteria.
        
        Args:
            symbol: Trading symbol to filter by
            direction: Trade direction to filter by
            signal_type: Signal type to filter by
            channel_name: Channel name to filter by
            max_age: Maximum age of signals to return
            
        Returns:
            List[Signal]: List of active signals
        """
        filters = {}
        
        if symbol:
            filters["symbol"] = symbol
        if direction:
            filters["direction"] = direction
        if signal_type:
            filters["signal_type"] = signal_type
        if channel_name:
            filters["channel_name"] = channel_name
            
        query = self._build_query(filters=filters)
        
        # Add active signal conditions
        query = query.where(
            and_(
                Signal.deleted_at.is_(None),
                Signal.is_duplicate.is_(False),
                Signal.status != "CANCELLED"
            )
        )
        
        # Add max age condition
        if max_age:
            min_date = datetime.now(tz=timezone.utc) - max_age
            query = query.where(Signal.created_at >= min_date)
            
        # Order by creation date
        query = query.order_by(Signal.created_at.desc())
        
        return await self.get_multi(query=query)
        
    async def find_duplicate(
        self,
        signal: Signal,
        time_window: timedelta = timedelta(minutes=5)
    ) -> Optional[Signal]:
        """Find duplicate signal using both message ID and content matching.
        
        The method uses a two-step approach:
        1. First checks for exact duplicate using message_id and chat_id
        2. If no exact duplicate found, checks for similar signals within time window
        
        Args:
            signal: Signal to check for duplicates
            time_window: Time window to look for similar signals
            
        Returns:
            Optional[Signal]: Duplicate signal if found
        """
        # Step 1: Check for exact message ID duplicate
        exact_duplicate = await self.get_by_message_id(
            message_id=signal.message_id,
            chat_id=signal.chat_id
        )
        if exact_duplicate:
            return exact_duplicate

        # Step 2: If no exact duplicate, check for similar signals in time window
        now = datetime.now(tz=timezone.utc)
        
        # Build query for similar signals
        query = select(Signal).where(
            and_(
                Signal.symbol == signal.symbol,
                Signal.direction == signal.direction,
                Signal.signal_type == signal.signal_type,
                Signal.channel_name == signal.channel_name,
                Signal.is_duplicate.is_(False),
                Signal.deleted_at.is_(None),
                Signal.created_at >= now - time_window,
                Signal.created_at <= now + time_window,
                Signal.id != signal.id,
                # Exclude the exact message we just checked
                Signal.message_id != signal.message_id
            )
        )
        
        # Order by creation date to get most recent first
        query = query.order_by(Signal.created_at.desc())
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
        
    async def get_signals_by_status(
        self,
        status: str,
        *,
        min_age: Optional[timedelta] = None,
        max_age: Optional[timedelta] = None
    ) -> List[Signal]:
        """Get signals by status and age.
        
        Args:
            status: Signal status to filter by
            min_age: Minimum age of signals to return
            max_age: Maximum age of signals to return
            
        Returns:
            List[Signal]: List of signals
        """
        query = self._build_query(filters={"status": status})
        
        # Add age conditions
        if min_age or max_age:
            now = datetime.now(tz=timezone.utc)
            if min_age:
                query = query.where(
                    Signal.created_at >= now - min_age
                )
            if max_age:
                query = query.where(
                    Signal.created_at <= now - max_age
                )
                
        # Order by creation date
        query = query.order_by(Signal.created_at.desc())
        
        return await self.get_multi(query=query)
        
    async def get_channel_statistics(
        self,
        channel_name: str,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Tuple[int, int, int]:
        """Get channel signal statistics.
        
        Args:
            channel_name: Channel name to get statistics for
            start_date: Start date for statistics
            end_date: End date for statistics
            
        Returns:
            Tuple[int, int, int]: Total signals, active signals, duplicate signals
        """
        # Build base query
        query = select(Signal).where(
            Signal.channel_name == channel_name
        )
        
        # Add date range
        if start_date:
            query = query.where(Signal.created_at >= start_date)
        if end_date:
            query = query.where(Signal.created_at <= end_date)
            
        # Get total signals
        total = await self.count(query=query)
        
        # Get active signals
        active_query = query.where(
            and_(
                Signal.deleted_at.is_(None),
                Signal.is_duplicate.is_(False),
                Signal.status != "CANCELLED"
            )
        )
        active = await self.count(query=active_query)
        
        # Get duplicate signals
        duplicate_query = query.where(Signal.is_duplicate.is_(True))
        duplicates = await self.count(query=duplicate_query)
        
        return total, active, duplicates
        
    async def cleanup_old_signals(
        self,
        max_age: timedelta,
        *,
        status: Optional[str] = None
    ) -> int:
        """Clean up old signals.
        
        Args:
            max_age: Maximum age of signals to clean up
            status: Optional status to filter by
            
        Returns:
            int: Number of signals cleaned up
        """
        # Build query
        query = select(Signal).where(
            Signal.created_at <= datetime.now(tz=timezone.utc) - max_age
        )
        
        if status:
            query = query.where(Signal.status == status)
            
        # Get signals to clean up
        result = await self.session.execute(query)
        signals = list(result.scalars().all())
        
        # Soft delete signals
        for signal in signals:
            signal.soft_delete()
            
        await self.session.flush()
        return len(signals)
        
    async def find_duplicate_by_data(
        self,
        symbol: str,
        direction: SignalDirection,
        entry_price: float,
        message_id: int,
        chat_id: int,
        channel_name: str,
        time_window: timedelta = timedelta(minutes=5)
    ) -> Optional[Signal]:
        """Find duplicate signal using signal data.
        
        Args:
            symbol: Trading symbol
            direction: Trade direction
            entry_price: Entry price
            message_id: Telegram message ID
            chat_id: Telegram chat ID
            channel_name: Channel name
            time_window: Time window to look for duplicates
            
        Returns:
            Optional[Signal]: Duplicate signal if found
        """
        # Step 1: Check for exact message ID duplicate
        exact_duplicate = await self.get_by_message_id(
            message_id=message_id,
            chat_id=chat_id
        )
        if exact_duplicate:
            return exact_duplicate

        # Step 2: If no exact duplicate, check for similar signals in time window
        now = datetime.now(tz=timezone.utc)
        
        # Build query for similar signals
        query = select(Signal).where(
            and_(
                Signal.symbol == symbol,
                Signal.direction == direction,
                Signal.entry_price == entry_price,
                Signal.channel_name == channel_name,
                Signal.is_duplicate.is_(False),
                Signal.deleted_at.is_(None),
                Signal.created_at >= now - time_window,
                Signal.created_at <= now + time_window,
                # Exclude the exact message we just checked
                Signal.message_id != message_id
            )
        )
        
        # Order by creation date to get most recent first
        query = query.order_by(Signal.created_at.desc())
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none() 