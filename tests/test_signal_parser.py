"""Tests for the signal parser module."""

import pytest
from src.telegram.signal_parser import SignalParser, TradingSignal, TakeProfit

def test_parse_gold_signal():
    """Test parsing a gold trading signal."""
    parser = SignalParser()
    message = """XAUUSD buy 
Enter 3373
SL 3360 (130) 
TP1 3376
TP2 3380
TP3 3385
TP4 3402 (290)

Wider SL due to overnight trade

It's risky but I want to see if we catch a push"""

    signal = parser.parse(message)
    assert signal is not None
    assert isinstance(signal, TradingSignal)
    
    # Verify signal components
    assert signal.symbol == "XAUUSD"
    assert signal.direction == "buy"
    assert signal.entry_price == 3373.0
    assert signal.stop_loss == 3360.0
    assert signal.stop_loss_pips == 130
    
    # Verify take profits
    assert len(signal.take_profits) == 4
    assert signal.take_profits[0].level == 1
    assert signal.take_profits[0].price == 3376.0
    assert signal.take_profits[3].price == 3402.0
    assert signal.take_profits[3].pips == 290
    
    # Verify additional notes
    assert "Wider SL due to overnight trade" in signal.additional_notes
    assert "risky" in signal.additional_notes
    
    # Verify confidence score
    assert 0.0 <= signal.confidence_score <= 1.0

def test_invalid_symbol():
    """Test parsing a signal with invalid symbol."""
    parser = SignalParser()
    message = """INVALID buy 
Enter 3373
SL 3360 (130) 
TP1 3376"""
    
    signal = parser.parse(message)
    assert signal is None

def test_missing_components():
    """Test parsing a signal with missing components."""
    parser = SignalParser()
    message = """XAUUSD buy 
Enter 3373"""
    
    signal = parser.parse(message)
    assert signal is None

def test_different_direction_formats():
    """Test parsing signals with different direction formats."""
    parser = SignalParser()
    test_cases = [
        ("XAUUSD buy", "buy"),
        ("XAUUSD long", "buy"),
        ("XAUUSD b", "buy"),
        ("XAUUSD sell", "sell"),
        ("XAUUSD short", "sell"),
        ("XAUUSD s", "sell"),
    ]
    
    for message, expected in test_cases:
        signal = parser.parse(message + "\nEnter 3373\nSL 3360\nTP1 3376")
        assert signal is not None
        assert signal.direction == expected

def test_price_validation():
    """Test validation of price relationships."""
    parser = SignalParser()
    
    # Invalid buy signal (SL > Entry)
    invalid_buy = """XAUUSD buy
Enter 3360
SL 3373 (130)
TP1 3376"""
    
    # Invalid sell signal (SL < Entry)
    invalid_sell = """XAUUSD sell
Enter 3373
SL 3360 (130)
TP1 3370"""
    
    buy_signal = parser.parse(invalid_buy)
    sell_signal = parser.parse(invalid_sell)
    
    assert buy_signal is not None
    assert sell_signal is not None
    assert buy_signal.confidence_score < 1.0
    assert sell_signal.confidence_score < 1.0 