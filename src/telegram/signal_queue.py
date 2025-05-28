"""Signal queue module for managing signal processing order.

This module implements the SignalQueue class which is responsible for:
- Managing processing order of signals
- Handling signal priorities
- Flow control for signal processing
- Retry management
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Optional, Deque
import asyncio
from collections import deque
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

class SignalPriority(Enum):
    """Priority levels for trading signals."""
    HIGH = 0    # Immediate execution (e.g., market orders)
    NORMAL = 1  # Standard priority (e.g., limit orders)
    LOW = 2     # Delayed execution (e.g., pending orders)

@dataclass
class QueueItem:
    """Represents a signal in the processing queue."""
    signal_id: UUID
    priority: SignalPriority
    queued_at: datetime
    retry_count: int = 0
    last_retry: Optional[datetime] = None

class SignalQueue:
    """Queue for managing signal processing order with priority.
    
    This class implements a priority queue for signal processing with:
    - FIFO ordering within priority levels
    - Flow control for processing rate
    - Retry tracking
    """
    
    def __init__(
        self,
        max_queue_size: int = 1000,
        max_retries: int = 3,
        retry_delay_minutes: int = 5
    ):
        """Initialize the signal queue.
        
        Args:
            max_queue_size: Maximum number of signals in queue
            max_retries: Maximum number of retry attempts
            retry_delay_minutes: Delay between retries in minutes
        """
        self.max_queue_size = max_queue_size
        self.max_retries = max_retries
        self.retry_delay = timedelta(minutes=retry_delay_minutes)
        
        # Priority queues
        self.queues: Dict[SignalPriority, Deque[QueueItem]] = {
            priority: deque(maxlen=max_queue_size)
            for priority in SignalPriority
        }
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        # Statistics
        self.total_queued = 0
        self.total_processed = 0
        self.total_retried = 0
        
    async def enqueue(
        self,
        signal_id: UUID,
        priority: SignalPriority = SignalPriority.NORMAL
    ) -> bool:
        """Add a signal to the processing queue.
        
        Args:
            signal_id: UUID of the signal in the database
            priority: Processing priority level
            
        Returns:
            bool indicating if signal was queued
        """
        async with self._lock:
            if self._is_queue_full():
                logger.warning(
                    "queue_full",
                    max_size=self.max_queue_size
                )
                return False
                
            queue_item = QueueItem(
                signal_id=signal_id,
                priority=priority,
                queued_at=datetime.now(tz=timezone.utc)
            )
            
            self.queues[priority].append(queue_item)
            self.total_queued += 1
            
            logger.info(
                "signal_queued",
                signal_id=signal_id,
                priority=priority.name,
                queue_size=self._get_total_queue_size()
            )
            
            return True
            
    async def dequeue(self) -> Optional[QueueItem]:
        """Get the next signal to process.
        
        Returns:
            QueueItem if available, None if queue empty
        """
        async with self._lock:
            for priority in SignalPriority:
                if self.queues[priority]:
                    item = self.queues[priority].popleft()
                    self.total_processed += 1
                    return item
            return None
            
    async def retry(
        self,
        signal_id: UUID,
        priority: SignalPriority
    ) -> bool:
        """Add a signal back to queue for retry.
        
        Args:
            signal_id: UUID of the signal to retry
            priority: Priority level for retry
            
        Returns:
            bool indicating if signal was requeued
        """
        async with self._lock:
            self.total_retried += 1
            return await self.enqueue(signal_id, priority)
            
    def _is_queue_full(self) -> bool:
        """Check if queue is at capacity."""
        return self._get_total_queue_size() >= self.max_queue_size
        
    def _get_total_queue_size(self) -> int:
        """Get total number of signals in all queues."""
        return sum(len(queue) for queue in self.queues.values())
        
    def get_queue_stats(self) -> Dict[str, any]:
        """Get current queue statistics."""
        return {
            "total_queued": self.total_queued,
            "total_processed": self.total_processed,
            "total_retried": self.total_retried,
            "current_size": self._get_total_queue_size(),
            "sizes_by_priority": {
                priority.name: len(queue)
                for priority, queue in self.queues.items()
            }
        }
        
    async def clear(self) -> None:
        """Clear all items from queue and reset statistics."""
        async with self._lock:
            for queue in self.queues.values():
                queue.clear()
            self.total_queued = 0
            self.total_processed = 0
            self.total_retried = 0
            logger.info("queue_cleared") 