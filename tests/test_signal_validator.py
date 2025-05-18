"""Tests for the signal validator module."""

import pytest
from datetime import datetime, timedelta
from typing import List

from src.telegram.signal_validator import SignalValidator, ValidationResult
from src.telegram.signal_parser import TradingSignal, TakeProfit

@pytest.fixture
def validator():
    """Create a SignalValidator instance for testing."""
    return SignalValidator(
        max_signal_age_minutes=5,
        duplicate_window_minutes=30,
        cache_size=10
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

@pytest.fixture
def valid_sell_signal():
    """Create a valid sell signal for testing."""
    return TradingSignal(
        symbol="EURUSD",
        direction="sell",
        entry_price=1.1000,
        stop_loss=1.1050,
        stop_loss_pips=50,
        take_profits=[
            TakeProfit(level=1, price=1.0950, pips=50),
            TakeProfit(level=2, price=1.0900, pips=100)
        ],
        timestamp=datetime.now(),
        raw_message="Test sell signal",
        confidence_score=0.9
    )

def test_validate_required_fields(validator: SignalValidator, valid_signal: TradingSignal):
    """Test validation of required fields."""
    result = validator.validate_signal(valid_signal)
    assert result.is_valid
    assert "validated successfully" in result.reason

def test_missing_symbol(validator: SignalValidator, valid_signal: TradingSignal):
    """Test validation with missing symbol."""
    signal = TradingSignal(**{**valid_signal.__dict__, "symbol": ""})
    result = validator.validate_signal(signal)
    assert not result.is_valid
    assert "Missing symbol" in result.reason

def test_invalid_direction(validator: SignalValidator, valid_signal: TradingSignal):
    """Test validation with invalid direction."""
    signal = TradingSignal(**{**valid_signal.__dict__, "direction": "invalid"})
    result = validator.validate_signal(signal)
    assert not result.is_valid
    assert "Invalid direction" in result.reason

def test_invalid_price_relationships_buy(validator: SignalValidator, valid_signal: TradingSignal):
    """Test validation with invalid price relationships for buy signal."""
    # Make stop loss higher than entry price
    signal = TradingSignal(**{**valid_signal.__dict__, "stop_loss": valid_signal.entry_price + 0.001})
    result = validator.validate_signal(signal)
    assert not result.is_valid
    assert "Invalid price relationships" in result.reason

def test_invalid_price_relationships_sell(validator: SignalValidator, valid_sell_signal: TradingSignal):
    """Test validation with invalid price relationships for sell signal."""
    # Make stop loss lower than entry price
    signal = TradingSignal(**{**valid_sell_signal.__dict__, "stop_loss": valid_sell_signal.entry_price - 0.001})
    result = validator.validate_signal(signal)
    assert not result.is_valid
    assert "Invalid price relationships" in result.reason

def test_signal_age_validation(validator: SignalValidator, valid_signal: TradingSignal):
    """Test validation of signal age."""
    # Create an old signal
    old_signal = TradingSignal(**{
        **valid_signal.__dict__,
        "timestamp": datetime.now() - timedelta(minutes=10)
    })
    result = validator.validate_signal(old_signal)
    assert not result.is_valid
    assert "Signal too old" in result.reason

def test_symbol_validation(validator: SignalValidator, valid_signal: TradingSignal):
    """Test validation of trading symbol."""
    # Test with invalid symbol format
    invalid_symbol = TradingSignal(**{**valid_signal.__dict__, "symbol": "INVALID"})
    result = validator.validate_signal(invalid_symbol)
    assert not result.is_valid
    assert "Invalid symbol format" in result.reason
    
    # Test with valid symbol format but not in available symbols
    validator.update_available_symbols({"GBPUSD", "USDJPY"})
    result = validator.validate_signal(valid_signal)
    assert not result.is_valid
    assert "Symbol not available" in result.reason
    
    # Test with available symbol
    validator.update_available_symbols({"EURUSD", "GBPUSD"})
    result = validator.validate_signal(valid_signal)
    assert result.is_valid

def test_duplicate_detection(validator: SignalValidator, valid_signal: TradingSignal):
    """Test duplicate signal detection."""
    # First signal should be valid
    result1 = validator.validate_signal(valid_signal)
    assert result1.is_valid
    
    # Identical signal should be detected as duplicate
    result2 = validator.validate_signal(valid_signal)
    assert not result2.is_valid
    assert "Duplicate signal detected" in result2.reason
    
    # Similar signal with slightly different prices should be detected as duplicate
    similar_signal = TradingSignal(**{
        **valid_signal.__dict__,
        "entry_price": valid_signal.entry_price + 0.0001,  # 0.01 pip difference
        "stop_loss": valid_signal.stop_loss + 0.0001,
        "take_profits": [
            TakeProfit(level=tp.level, price=tp.price + 0.0001, pips=tp.pips)
            for tp in valid_signal.take_profits
        ]
    })
    result3 = validator.validate_signal(similar_signal)
    assert not result3.is_valid
    assert "Duplicate signal detected" in result3.reason
    
    # Different signal should be valid
    different_signal = TradingSignal(**{
        **valid_signal.__dict__,
        "entry_price": valid_signal.entry_price + 0.01,  # 1 pip difference
        "stop_loss": valid_signal.stop_loss + 0.01,
        "take_profits": [
            TakeProfit(level=tp.level, price=tp.price + 0.01, pips=tp.pips)
            for tp in valid_signal.take_profits
        ]
    })
    result4 = validator.validate_signal(different_signal)
    assert result4.is_valid

def test_duplicate_window_expiry(validator: SignalValidator, valid_signal: TradingSignal):
    """Test that duplicate detection window expires correctly."""
    # First signal
    result1 = validator.validate_signal(valid_signal)
    assert result1.is_valid
    
    # Create a signal outside the duplicate window
    old_timestamp = datetime.now() - timedelta(minutes=31)
    old_signal = TradingSignal(**{
        **valid_signal.__dict__,
        "timestamp": old_timestamp
    })
    
    # This should be considered a duplicate because it's identical to the first signal
    result2 = validator.validate_signal(valid_signal)
    assert not result2.is_valid
    
    # But if we wait for the duplicate window to expire, it should be valid
    validator.signal_cache.clear()  # Simulate window expiry
    result3 = validator.validate_signal(valid_signal)
    assert result3.is_valid 