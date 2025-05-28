"""Tests for the signal queue module."""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from src.telegram.signal_queue import (
    SignalQueue,
    SignalPriority,
    QueueItem
)

@pytest.fixture
def signal_queue():
    """Create a signal queue for testing."""
    return SignalQueue(
        max_queue_size=10,
        max_retries=3,
        retry_delay_minutes=1
    )

@pytest.mark.asyncio
async def test_enqueue_dequeue():
    """Test basic enqueue and dequeue operations."""
    queue = SignalQueue(max_queue_size=5)
    signal_id = uuid4()
    
    # Enqueue signal
    success = await queue.enqueue(signal_id, SignalPriority.NORMAL)
    assert success is True
    
    # Dequeue signal
    item = await queue.dequeue()
    assert item is not None
    assert item.signal_id == signal_id
    assert item.priority == SignalPriority.NORMAL
    
    # Queue should be empty
    empty_item = await queue.dequeue()
    assert empty_item is None

@pytest.mark.asyncio
async def test_queue_priority():
    """Test that signals are dequeued in priority order."""
    queue = SignalQueue(max_queue_size=5)
    
    # Add signals with different priorities
    high_id = uuid4()
    normal_id = uuid4()
    low_id = uuid4()
    
    await queue.enqueue(low_id, SignalPriority.LOW)
    await queue.enqueue(normal_id, SignalPriority.NORMAL)
    await queue.enqueue(high_id, SignalPriority.HIGH)
    
    # Should dequeue in priority order
    first = await queue.dequeue()
    assert first.signal_id == high_id
    
    second = await queue.dequeue()
    assert second.signal_id == normal_id
    
    third = await queue.dequeue()
    assert third.signal_id == low_id

@pytest.mark.asyncio
async def test_queue_full():
    """Test queue size limits."""
    queue = SignalQueue(max_queue_size=2)
    
    # Fill queue
    signal1_id = uuid4()
    signal2_id = uuid4()
    signal3_id = uuid4()
    
    assert await queue.enqueue(signal1_id) is True
    assert await queue.enqueue(signal2_id) is True
    
    # Should reject when full
    assert await queue.enqueue(signal3_id) is False

@pytest.mark.asyncio
async def test_retry():
    """Test signal retry functionality."""
    queue = SignalQueue(max_queue_size=5, max_retries=2)
    signal_id = uuid4()
    
    # Initial enqueue
    await queue.enqueue(signal_id, SignalPriority.NORMAL)
    
    # Process and retry
    item = await queue.dequeue()
    assert item.retry_count == 0
    
    # Retry signal
    await queue.retry(signal_id, SignalPriority.NORMAL)
    
    # Check retry count increased
    retried = await queue.dequeue()
    assert retried.signal_id == signal_id
    assert retried.retry_count == 1

@pytest.mark.asyncio
async def test_queue_stats():
    """Test queue statistics."""
    queue = SignalQueue(max_queue_size=5)
    signal_id = uuid4()
    
    # Add and process a signal
    await queue.enqueue(signal_id)
    await queue.dequeue()
    await queue.retry(signal_id, SignalPriority.NORMAL)
    
    stats = queue.get_queue_stats()
    assert stats["total_queued"] == 1
    assert stats["total_processed"] == 1
    assert stats["total_retried"] == 1
    
@pytest.mark.asyncio
async def test_clear():
    """Test clearing the queue."""
    queue = SignalQueue(max_queue_size=5)
    
    # Add some signals
    await queue.enqueue(uuid4())
    await queue.enqueue(uuid4())
    
    # Clear queue
    await queue.clear()
    
    # Queue should be empty
    assert queue._get_total_queue_size() == 0
    stats = queue.get_queue_stats()
    assert stats["total_queued"] == 0
    assert stats["total_processed"] == 0
    assert stats["total_retried"] == 0 