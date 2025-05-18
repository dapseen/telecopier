"""Signal queue module for buffering and managing trading signals.

This module implements the SignalQueue class which is responsible for:
- Buffering signals in a FIFO queue
- Handling signal priorities
- Managing signal expiration
- Providing thread-safe signal processing
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Deque
import asyncio
import heapq
from collections import deque

import structlog

from .signal_parser import TradingSignal
from .signal_validator import SignalValidator, ValidationResult

logger = structlog.get_logger(__name__)

class SignalPriority(Enum):
    """Priority levels for trading signals."""
    HIGH = 0    # Immediate execution (e.g., market orders)
    NORMAL = 1  # Standard priority (e.g., limit orders)
    LOW = 2     # Delayed execution (e.g., pending orders)

@dataclass
class QueuedSignal:
    """Represents a signal in the queue with priority and metadata."""
    signal: TradingSignal
    priority: SignalPriority
    queued_at: datetime
    validation_result: ValidationResult
    retry_count: int = 0
    last_retry: Optional[datetime] = None

class SignalQueue:
    """Queue for managing trading signals with priority and expiration.
    
    This class implements a priority queue for trading signals with the following features:
    - FIFO ordering within priority levels
    - Signal expiration management
    - Retry handling for failed signals
    - Thread-safe operations
    """
    
    def __init__(
        self,
        max_queue_size: int = 1000,
        max_retries: int = 3,
        retry_delay_minutes: int = 5,
        signal_expiry_minutes: int = 30
    ):
        """Initialize the signal queue.
        
        Args:
            max_queue_size: Maximum number of signals in the queue
            max_retries: Maximum number of retry attempts for failed signals
            retry_delay_minutes: Delay between retry attempts in minutes
            signal_expiry_minutes: Time after which signals expire
        """
        self.max_queue_size = max_queue_size
        self.max_retries = max_retries
        self.retry_delay = timedelta(minutes=retry_delay_minutes)
        self.signal_expiry = timedelta(minutes=signal_expiry_minutes)
        
        # Priority queues for each priority level
        self.queues: Dict[SignalPriority, Deque[QueuedSignal]] = {
            priority: deque(maxlen=max_queue_size)
            for priority in SignalPriority
        }
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        # Statistics
        self.total_signals_queued = 0
        self.total_signals_processed = 0
        self.total_signals_expired = 0
        self.total_signals_failed = 0
        
    async def enqueue(
        self,
        signal: TradingSignal,
        priority: SignalPriority = SignalPriority.NORMAL,
        validation_result: Optional[ValidationResult] = None
    ) -> bool:
        """Add a signal to the queue.
        
        Args:
            signal: The trading signal to queue
            priority: Priority level for the signal
            validation_result: Optional validation result if signal was pre-validated
            
        Returns:
            bool indicating if the signal was successfully queued
        """
        async with self._lock:
            # Check if queue is full
            if self._is_queue_full():
                logger.warning(
                    "queue_full",
                    max_size=self.max_queue_size,
                    signal_symbol=signal.symbol
                )
                return False
                
            # Create queued signal
            queued_signal = QueuedSignal(
                signal=signal,
                priority=priority,
                queued_at=datetime.now(),
                validation_result=validation_result or ValidationResult(True, "Pending validation")
            )
            
            # Add to appropriate priority queue
            self.queues[priority].append(queued_signal)
            self.total_signals_queued += 1
            
            logger.info(
                "signal_queued",
                symbol=signal.symbol,
                priority=priority.name,
                queue_size=self._get_total_queue_size()
            )
            
            return True
            
    async def dequeue(self) -> Optional[QueuedSignal]:
        """Get the next signal to process.
        
        Returns:
            The next QueuedSignal to process, or None if queue is empty
        """
        async with self._lock:
            # Try each priority queue in order
            for priority in SignalPriority:
                if self.queues[priority]:
                    queued_signal = self.queues[priority].popleft()
                    
                    # Check if signal has expired
                    if self._is_signal_expired(queued_signal):
                        self.total_signals_expired += 1
                        logger.info(
                            "signal_expired",
                            symbol=queued_signal.signal.symbol,
                            age_minutes=(datetime.now() - queued_signal.queued_at).total_seconds() / 60
                        )
                        continue
                        
                    self.total_signals_processed += 1
                    return queued_signal
                    
            return None
            
    async def retry_signal(self, queued_signal: QueuedSignal) -> bool:
        """Retry a failed signal.
        
        Args:
            queued_signal: The signal to retry
            
        Returns:
            bool indicating if the signal was successfully requeued
        """
        async with self._lock:
            # Check if max retries reached
            if queued_signal.retry_count >= self.max_retries:
                self.total_signals_failed += 1
                logger.warning(
                    "max_retries_reached",
                    symbol=queued_signal.signal.symbol,
                    retry_count=queued_signal.retry_count
                )
                return False
                
            # Update retry information
            queued_signal.retry_count += 1
            queued_signal.last_retry = datetime.now()
            
            # Requeue with same priority
            return await self.enqueue(
                queued_signal.signal,
                queued_signal.priority,
                queued_signal.validation_result
            )
            
    def _is_queue_full(self) -> bool:
        """Check if the queue is full.
        
        Returns:
            bool indicating if queue is at capacity
        """
        return self._get_total_queue_size() >= self.max_queue_size
        
    def _get_total_queue_size(self) -> int:
        """Get the total number of signals in all queues.
        
        Returns:
            Total number of signals in the queue
        """
        return sum(len(queue) for queue in self.queues.values())
        
    def _is_signal_expired(self, queued_signal: QueuedSignal) -> bool:
        """Check if a signal has expired.
        
        Args:
            queued_signal: The signal to check
            
        Returns:
            bool indicating if signal has expired
        """
        age = datetime.now() - queued_signal.queued_at
        return age > self.signal_expiry
        
    def get_queue_stats(self) -> Dict[str, any]:
        """Get current queue statistics.
        
        Returns:
            Dictionary containing queue statistics
        """
        return {
            "total_queued": self.total_signals_queued,
            "total_processed": self.total_signals_processed,
            "total_expired": self.total_signals_expired,
            "total_failed": self.total_signals_failed,
            "current_queue_size": self._get_total_queue_size(),
            "queue_sizes_by_priority": {
                priority.name: len(queue)
                for priority, queue in self.queues.items()
            }
        }
        
    async def clear_expired_signals(self) -> int:
        """Clear all expired signals from the queue.
        
        Returns:
            Number of signals cleared
        """
        async with self._lock:
            cleared_count = 0
            now = datetime.now()
            
            for priority in SignalPriority:
                # Keep only non-expired signals
                original_size = len(self.queues[priority])
                self.queues[priority] = deque(
                    (signal for signal in self.queues[priority]
                     if not self._is_signal_expired(signal)),
                    maxlen=self.max_queue_size
                )
                cleared_count += original_size - len(self.queues[priority])
                
            if cleared_count > 0:
                logger.info(
                    "cleared_expired_signals",
                    count=cleared_count,
                    remaining=self._get_total_queue_size()
                )
                
            return cleared_count

    async def clear(self) -> None:
        """Clear all signals from the queue and reset statistics."""
        async with self._lock:
            for queue in self.queues.values():
                queue.clear()
            self.total_signals_queued = 0
            self.total_signals_processed = 0
            self.total_signals_expired = 0
            self.total_signals_failed = 0
            logger.info("signal_queue_cleared") 