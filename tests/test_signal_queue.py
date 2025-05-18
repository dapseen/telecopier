"""Tests for the signal queue module."""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import List

from src.telegram.signal_queue import SignalQueue, SignalPriority, QueuedSignal
from src.telegram.signal_parser import TradingSignal, TakeProfit
from src.telegram.signal_validator import ValidationResult

@pytest.fixture
def queue():
    """Create a SignalQueue instance for testing."""
    return SignalQueue(
        max_queue_size=10,
        max_retries=2,
        retry_delay_minutes=1,
        signal_expiry_minutes=5
    )

@pytest.fixture
def valid_signal():
    """Create a valid trading signal for testing."""
    return TradingSignal(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0950,
        stop_loss_pips=50,
        take_profits=[
            TakeProfit(level=1, price=1.1050, pips=50),
            TakeProfit(level=2, price=1.1100, pips=100)
        ],
        timestamp=datetime.now(),
        raw_message="Test signal",
        confidence_score=0.9
    )

@pytest.mark.asyncio
async def test_enqueue_dequeue(queue: SignalQueue, valid_signal: TradingSignal):
    """Test basic enqueue and dequeue operations."""
    # Enqueue a signal
    success = await queue.enqueue(valid_signal, SignalPriority.NORMAL)
    assert success
    
    # Dequeue the signal
    queued_signal = await queue.dequeue()
    assert queued_signal is not None
    assert queued_signal.signal == valid_signal
    assert queued_signal.priority == SignalPriority.NORMAL
    assert queued_signal.retry_count == 0
    
    # Queue should be empty
    assert await queue.dequeue() is None

@pytest.mark.asyncio
async def test_priority_ordering(queue: SignalQueue, valid_signal: TradingSignal):
    """Test that signals are processed in priority order."""
    # Create signals with different priorities
    low_signal = TradingSignal(**{**valid_signal.__dict__, "symbol": "LOW"})
    normal_signal = TradingSignal(**{**valid_signal.__dict__, "symbol": "NORMAL"})
    high_signal = TradingSignal(**{**valid_signal.__dict__, "symbol": "HIGH"})
    
    # Enqueue in random order
    await queue.enqueue(normal_signal, SignalPriority.NORMAL)
    await queue.enqueue(high_signal, SignalPriority.HIGH)
    await queue.enqueue(low_signal, SignalPriority.LOW)
    
    # Dequeue and verify order
    first = await queue.dequeue()
    assert first.signal.symbol == "HIGH"
    
    second = await queue.dequeue()
    assert second.signal.symbol == "NORMAL"
    
    third = await queue.dequeue()
    assert third.signal.symbol == "LOW"

@pytest.mark.asyncio
async def test_queue_full(queue: SignalQueue, valid_signal: TradingSignal):
    """Test queue full condition."""
    # Fill the queue
    for i in range(queue.max_queue_size):
        signal = TradingSignal(**{**valid_signal.__dict__, "symbol": f"TEST{i}"})
        success = await queue.enqueue(signal)
        assert success
    
    # Try to enqueue one more
    signal = TradingSignal(**{**valid_signal.__dict__, "symbol": "FULL"})
    success = await queue.enqueue(signal)
    assert not success

@pytest.mark.asyncio
async def test_signal_expiry(queue: SignalQueue, valid_signal: TradingSignal):
    """Test signal expiration."""
    # Create an old signal
    old_signal = TradingSignal(**{
        **valid_signal.__dict__,
        "timestamp": datetime.now() - timedelta(minutes=10)
    })
    
    # Enqueue the old signal
    await queue.enqueue(old_signal)
    
    # Dequeue should return None because signal is expired
    assert await queue.dequeue() is None
    
    # Verify stats
    stats = queue.get_queue_stats()
    assert stats["total_expired"] == 1

@pytest.mark.asyncio
async def test_retry_mechanism(queue: SignalQueue, valid_signal: TradingSignal):
    """Test signal retry mechanism."""
    # Enqueue a signal
    await queue.enqueue(valid_signal)
    queued_signal = await queue.dequeue()
    assert queued_signal is not None
    
    # Retry the signal
    success = await queue.retry_signal(queued_signal)
    assert success
    assert queued_signal.retry_count == 1
    
    # Retry again
    queued_signal = await queue.dequeue()
    success = await queue.retry_signal(queued_signal)
    assert success
    assert queued_signal.retry_count == 2
    
    # One more retry should fail
    queued_signal = await queue.dequeue()
    success = await queue.retry_signal(queued_signal)
    assert not success
    
    # Verify stats
    stats = queue.get_queue_stats()
    assert stats["total_failed"] == 1

@pytest.mark.asyncio
async def test_clear_expired_signals(queue: SignalQueue, valid_signal: TradingSignal):
    """Test clearing expired signals."""
    # Create some signals with different timestamps
    now = datetime.now()
    signals = [
        TradingSignal(**{
            **valid_signal.__dict__,
            "symbol": f"TEST{i}",
            "timestamp": now - timedelta(minutes=i * 2)
        })
        for i in range(5)
    ]
    
    # Enqueue all signals
    for signal in signals:
        await queue.enqueue(signal)
    
    # Clear expired signals (those older than 5 minutes)
    cleared = await queue.clear_expired_signals()
    assert cleared == 3  # Signals at 6, 8, and 10 minutes should be cleared
    
    # Verify remaining signals
    stats = queue.get_queue_stats()
    assert stats["current_queue_size"] == 2

@pytest.mark.asyncio
async def test_queue_stats(queue: SignalQueue, valid_signal: TradingSignal):
    """Test queue statistics tracking."""
    # Initial stats
    stats = queue.get_queue_stats()
    assert stats["total_queued"] == 0
    assert stats["total_processed"] == 0
    assert stats["total_expired"] == 0
    assert stats["total_failed"] == 0
    assert stats["current_queue_size"] == 0
    
    # Enqueue and process some signals
    await queue.enqueue(valid_signal)
    await queue.enqueue(valid_signal)
    await queue.dequeue()
    
    # Check updated stats
    stats = queue.get_queue_stats()
    assert stats["total_queued"] == 2
    assert stats["total_processed"] == 1
    assert stats["current_queue_size"] == 1
    
    # Verify priority queue sizes
    assert all(size >= 0 for size in stats["queue_sizes_by_priority"].values())
    assert sum(stats["queue_sizes_by_priority"].values()) == stats["current_queue_size"] 