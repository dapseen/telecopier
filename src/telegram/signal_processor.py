"""Signal processor for automated signal execution.

This module provides the SignalProcessor class which:
- Continuously monitors the signal queue
- Validates and processes signals
- Executes trades via MT5
- Handles errors and retries
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog

from src.telegram.signal_queue import SignalQueue, SignalPriority, QueueItem
from src.telegram.signal_validator import SignalValidator
from src.mt5.executor import TradeExecutor
from src.db.repositories.signal import SignalRepository
from src.common.types import SignalStatus
from src.db.models.signal import Signal

logger = structlog.get_logger(__name__)

class SignalProcessor:
    """Processes signals from queue and executes trades automatically."""
    
    def __init__(
        self,
        signal_queue: SignalQueue,
        trade_executor: TradeExecutor,
        signal_validator: SignalValidator,
        signal_repository: SignalRepository,
        processing_interval: float = 1.0,
        max_retries: int = 3
    ):
        """Initialize signal processor.
        
        Args:
            signal_queue: Queue containing signals to process
            trade_executor: Executor for MT5 trades
            signal_validator: Validator for signals
            signal_repository: Repository for signal persistence
            processing_interval: Time between queue checks in seconds
            max_retries: Maximum number of retry attempts
        """
        self.queue = signal_queue
        self.executor = trade_executor
        self.validator = signal_validator
        self.repository = signal_repository
        self.processing_interval = processing_interval
        self.max_retries = max_retries
        
        self._is_running = False
        self._processor_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the signal processor."""
        if self._is_running:
            logger.warning("signal_processor_already_running")
            return
            
        self._is_running = True
        self._processor_task = asyncio.create_task(self._process_queue())
        logger.info("signal_processor_started")
        
    async def stop(self):
        """Stop the signal processor."""
        if not self._is_running:
            return
            
        self._is_running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("signal_processor_stopped")
        
    async def _process_queue(self):
        """Main processing loop for signals."""
        while self._is_running:
            try:
                # Get next signal from queue
                queue_item = await self.queue.dequeue()
                if not queue_item:
                    await asyncio.sleep(self.processing_interval)
                    continue
                    
                # Get signal from database using UUID
                signal = await self.repository.get(queue_item.signal_id)
                if not signal:
                    logger.error(
                        "signal_not_found_in_db",
                        signal_id=queue_item.signal_id
                    )
                    continue
                
                # Process the signal
                await self._process_signal(signal, queue_item)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "queue_processing_error",
                    error=str(e)
                )
                await asyncio.sleep(self.processing_interval)
                
    async def _process_signal(self, signal: Signal, queue_item: QueueItem):
        """Process a single signal.
        
        Args:
            signal: Database signal to process
            queue_item: Queue item containing processing metadata
        """
        execution_started = False
        try:
            # Update signal status
            await self.repository.update(
                db_obj=signal,
                obj_in={"status": SignalStatus.PROCESSING}
            )
            
            # Validate signal
            validation_result = await self.validator.validate(signal)
            if not validation_result.is_valid:
                logger.warning(
                    "signal_validation_failed",
                    signal_id=signal.id,
                    reason=validation_result.reason
                )
                await self.repository.update(
                    db_obj=signal,
                    obj_in={
                        "status": SignalStatus.FAILED,
                        "error_message": f"Validation failed: {validation_result.reason}"
                    }
                )
                return
                    
            # Mark that we've started execution
            execution_started = True
            
            # Convert database signal to TradingSignal
            trading_signal = signal.to_trading_signal()
            logger.info(
                "executing_signal",
                signal_id=signal.id,
                entry_price=trading_signal.entry_price,
                stop_loss=trading_signal.stop_loss,
                take_profits=[tp.price for tp in trading_signal.take_profits]
            )
                
            # Execute trade with TradingSignal
            result = await self.executor.execute_signal(trading_signal)
            if not result.success:
                # Handle retry if needed
                if queue_item.retry_count < self.max_retries:
                    logger.info(
                        "retrying_signal",
                        signal_id=signal.id,
                        retry_count=queue_item.retry_count + 1
                    )
                    # Re-queue with incremented retry count
                    await self.queue.retry(signal.id, queue_item.priority)
                    return
                    
                # Max retries reached
                logger.error(
                    "signal_execution_failed",
                    signal_id=signal.id,
                    error=result.error
                )
                await self.repository.update(
                    db_obj=signal,
                    obj_in={
                        "status": SignalStatus.FAILED,
                        "error_message": f"Execution failed: {result.error}"
                    }
                )
                return
                
            # Update signal as completed
            await self.repository.update(
                db_obj=signal,
                obj_in={
                    "status": SignalStatus.COMPLETED,
                    "processed_at": datetime.now(tz=timezone.utc)
                }
            )
            
            logger.info(
                "signal_processed_successfully",
                signal_id=signal.id,
                symbol=signal.symbol,
                direction=signal.direction
            )
            
        except Exception as e:
            logger.error(
                "signal_processing_error",
                signal_id=signal.id,
                error=str(e)
            )
            # Only update status if execution actually started
            if execution_started:
                await self.repository.update(
                    db_obj=signal,
                    obj_in={
                        "status": SignalStatus.FAILED,
                        "error_message": f"Processing error: {str(e)}"
                    }
                ) 