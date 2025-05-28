"""Signal service for handling signal processing and queueing.

This module provides:
- Signal parsing and validation
- Signal queue management
- Signal processing coordination
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.telegram.signal_parser import SignalParser, TradingSignal
from src.telegram.signal_queue import SignalQueue, SignalPriority
from src.db.repositories.signal import SignalRepository
from src.db.models.signal import Signal
from ..models import SignalCreate, SignalUpdate, SignalResponse
from src.common.types import SignalStatus
from src.telegram.signal_validator import SignalValidator
from src.telegram.signal_persistence import SignalPersistence

logger = structlog.get_logger(__name__)

class SignalService:
    """Service for managing signal processing and queueing."""
    
    def __init__(
        self,
        session: AsyncSession,
        signal_parser: SignalParser,
        signal_queue: SignalQueue,
        signal_validator: SignalValidator,
        signal_persistence: SignalPersistence
    ):
        """Initialize signal service.
        
        Args:
            session: Database session
            signal_parser: Signal parser instance
            signal_queue: Signal queue instance
            signal_validator: Validator for signals
            signal_persistence: Persistence layer for signals
        """
        self.session = session
        self.parser = signal_parser
        self.queue = signal_queue
        self.validator = signal_validator
        self.persistence = signal_persistence
        self.repository = SignalRepository(session)
        
    async def process_telegram_message(
        self,
        message_text: str,
        chat_id: int,
        message_id: int,
        channel_name: str
    ) -> SignalResponse:
        """Process a Telegram message into a trading signal.
        
        Args:
            message_text: Raw message text
            chat_id: Telegram chat ID
            message_id: Telegram message ID
            channel_name: Channel name
            
        Returns:
            SignalResponse: Created signal
            
        Raises:
            HTTPException: If signal parsing or creation fails
        """
        try:
            # Parse signal
            parsed_signal = self.parser.parse(message_text)
            if not parsed_signal:
                raise HTTPException(
                    status_code=400,
                    detail="Failed to parse trading signal from message"
                )
                
            # Create signal model
            signal_data = SignalCreate(
                message_id=message_id,
                chat_id=chat_id,
                channel_name=channel_name,
                signal_type=parsed_signal.signal_type,
                symbol=parsed_signal.symbol,
                direction=parsed_signal.direction,
                entry_price=parsed_signal.entry_price,
                stop_loss=parsed_signal.stop_loss,
                take_profit=parsed_signal.take_profits[0].price if parsed_signal.take_profits else None,
                risk_reward=parsed_signal.risk_reward,
                lot_size=parsed_signal.lot_size
            )
            
            # Save to database
            db_signal = await self.repository.create(signal_data.model_dump())
            
            # Queue signal for processing
            success = await self.queue.enqueue(
                signal_id=db_signal.id,
                priority=SignalPriority.NORMAL
            )
            
            if not success:
                logger.warning(
                    "signal_queue_full",
                    signal_id=db_signal.id,
                    symbol=db_signal.symbol
                )
                # Update signal status
                await self.repository.update(
                    db_obj=db_signal,
                    obj_in={"status": SignalStatus.QUEUE_FULL}
                )
                
            return SignalResponse.model_validate(db_signal)
            
        except Exception as e:
            logger.error(
                "signal_processing_failed",
                error=str(e),
                message_id=message_id
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process signal: {str(e)}"
            )
        
    async def get_signal(self, signal_id: UUID) -> SignalResponse:
        """Get signal by ID.
        
        Args:
            signal_id: Signal ID
            
        Returns:
            SignalResponse: Signal data
            
        Raises:
            HTTPException: If signal not found
        """
        signal = await self.repository.get(signal_id)
        if not signal:
            raise HTTPException(
                status_code=404,
                detail="Signal not found"
            )
        return SignalResponse.model_validate(signal)
        
    async def list_signals(
        self,
        skip: int = 0,
        limit: int = 100,
        channel_name: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[SignalResponse]:
        """List signals with optional filtering.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            channel_name: Filter by channel name
            symbol: Filter by trading symbol
            status: Filter by signal status
            
        Returns:
            List[SignalResponse]: List of signals
        """
        filters = {}
        if channel_name:
            filters["channel_name"] = channel_name
        if symbol:
            filters["symbol"] = symbol
        if status:
            filters["status"] = status
            
        signals = await self.repository.get_multi(
            skip=skip,
            limit=limit,
            filters=filters
        )
        return [SignalResponse.model_validate(s) for s in signals]
        
    async def update_signal(
        self,
        signal_id: UUID,
        signal_update: SignalUpdate
    ) -> SignalResponse:
        """Update signal status.
        
        Args:
            signal_id: Signal ID
            signal_update: Update data
            
        Returns:
            SignalResponse: Updated signal
            
        Raises:
            HTTPException: If signal not found or update fails
        """
        signal = await self.repository.get(signal_id)
        if not signal:
            raise HTTPException(
                status_code=404,
                detail="Signal not found"
            )
            
        try:
            updated_signal = await self.repository.update(
                db_obj=signal,
                obj_in=signal_update.model_dump(exclude_unset=True)
            )
            return SignalResponse.model_validate(updated_signal)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to update signal: {str(e)}"
            )
            
    async def get_queue_stats(self) -> dict:
        """Get current signal queue statistics.
        
        Returns:
            Dictionary containing queue statistics
        """
        return self.queue.get_queue_stats()
        
    async def cancel_signal(self, signal_id: UUID) -> bool:
        """Cancel a queued signal.
        
        Args:
            signal_id: UUID of the signal to cancel
            
        Returns:
            bool indicating if signal was cancelled
        """
        signal = await self.repository.get(signal_id)
        if not signal:
            return False
            
        # Only cancel if not yet processed
        if signal.status in [SignalStatus.PENDING, SignalStatus.PROCESSING]:
            await self.repository.update(
                db_obj=signal,
                obj_in={"status": SignalStatus.CANCELLED}
            )
            return True
            
        return False 