"""Tests for the signal parser module.

This module contains tests for both the Lark-based parser and regex fallback
functionality in the SignalParser class.
"""

import pytest
from datetime import datetime
from src.telegram.signal_parser import SignalParser, TradingSignal, TakeProfit

@pytest.fixture
def parser():
    """Create a SignalParser instance with test symbols."""
    return SignalParser(valid_symbols={'XAUUSD', 'EURUSD', 'GBPUSD'})

@pytest.fixture
def sample_signals():
    """Return a list of sample trading signals to test parsing."""
    return [
        # Sample 1: Standard format
        """
        XAUUSD buy now 
        Enter 3232
        SL 3220
        TP1 3235
        TP2 3239
        TP3 3255
        TP4 3333.50 (1000)
        
        Max 0.25%
        """,
        
        # Sample 2: Alternative format
        """
        XAUUSD Buy now 
        Enter 3187
        SL 3176 (100pips) 
        TP1 3190
        TP2 3195
        TP3 3200
        TP4 3205
        """,
        
        # Sample 3: Mixed case and comments
        """
        XAUUSD buy now
        Enter 3173
        SL 3163 (100)
        TP1 3177
        Tp2 3180
        Tp3 3190
        TP4 3373 (2000)
        
        Max 0.25% risk
        Don't let one trade ruin weeks of profits
        
        TP5 3477
        """,
        
        # Sample 4: Invalid symbol
        """
        INVALID buy now
        Enter 100
        SL 90
        TP1 110
        """,
        
        # Sample 5: Missing components
        """
        XAUUSD buy now
        Enter 3173
        SL 3163
        """,
        
        # Sample 6: Invalid price relationships
        """
        XAUUSD buy now
        Enter 3173
        SL 3183  # SL above entry
        TP1 3170  # TP below entry
        """
    ]

def test_lark_parser_initialization(parser):
    """Test that Lark parser is properly initialized."""
    assert parser.parser is not None
    assert parser.transformer is not None
    assert parser.valid_symbols == {'XAUUSD', 'EURUSD', 'GBPUSD'}

def test_parse_valid_signals(parser, sample_signals):
    """Test parsing of valid trading signals."""
    # Test first three samples which should parse successfully
    for i, message in enumerate(sample_signals[:3]):
        signal = parser.parse(message)
        assert signal is not None, f"Failed to parse sample {i+1}"
        assert isinstance(signal, TradingSignal)
        
        # Verify basic structure
        assert signal.symbol == "XAUUSD"
        assert signal.direction == "buy"
        assert isinstance(signal.entry_price, float)
        assert isinstance(signal.stop_loss, float)
        assert isinstance(signal.take_profits, list)
        assert all(isinstance(tp, TakeProfit) for tp in signal.take_profits)
        assert isinstance(signal.timestamp, datetime)
        assert isinstance(signal.raw_message, str)
        assert 0.0 <= signal.confidence_score <= 1.0
        
        # Verify specific values for first sample
        if i == 0:
            assert signal.entry_price == 3232.0
            assert signal.stop_loss == 3220.0
            assert len(signal.take_profits) == 4
            assert signal.take_profits[0].price == 3235.0
            assert signal.take_profits[-1].price == 3333.50
            assert signal.take_profits[-1].pips == 1000
            assert "Max 0.25%" in signal.additional_notes

def test_parse_invalid_signals(parser, sample_signals):
    """Test parsing of invalid trading signals."""
    # Test samples 4-6 which should fail parsing
    for i, message in enumerate(sample_signals[3:], 4):
        signal = parser.parse(message)
        if i == 4:  # Invalid symbol
            assert signal is None
        elif i == 5:  # Missing components
            assert signal is None
        elif i == 6:  # Invalid price relationships
            assert signal is not None  # Should parse but with low confidence
            assert signal.confidence_score < 0.8

def test_regex_fallback(parser, sample_signals):
    """Test that regex fallback works when Lark parser fails."""
    # Temporarily disable Lark parser
    original_parser = parser.parser
    parser.parser = None
    
    try:
        # Should still parse using regex
        signal = parser.parse(sample_signals[0])
        assert signal is not None
        assert isinstance(signal, TradingSignal)
        assert signal.symbol == "XAUUSD"
        assert signal.direction == "buy"
    finally:
        # Restore Lark parser
        parser.parser = original_parser

def test_confidence_scoring(parser, sample_signals):
    """Test confidence scoring for different signal qualities."""
    # Test high confidence signal
    signal = parser.parse(sample_signals[0])
    assert signal is not None
    assert signal.confidence_score > 0.9
    
    # Test signal with invalid price relationships
    signal = parser.parse(sample_signals[5])
    assert signal is not None
    assert signal.confidence_score < 0.8
    
    # Test signal with missing components
    signal = parser.parse(sample_signals[4])
    assert signal is None  # Should fail parsing entirely

def test_additional_notes(parser, sample_signals):
    """Test extraction of additional notes and context."""
    # Test signal with risk management note
    signal = parser.parse(sample_signals[0])
    assert signal is not None
    assert "Max 0.25%" in signal.additional_notes
    
    # Test signal with multiple comments
    signal = parser.parse(sample_signals[2])
    assert signal is not None
    assert "Max 0.25% risk" in signal.additional_notes
    assert "Don't let one trade ruin weeks of profits" in signal.additional_notes

def test_take_profit_ordering(parser, sample_signals):
    """Test that take profit levels are properly ordered."""
    signal = parser.parse(sample_signals[2])
    assert signal is not None
    assert len(signal.take_profits) == 5
    
    # Verify levels are in order
    levels = [tp.level for tp in signal.take_profits]
    assert levels == sorted(levels)
    
    # Verify prices are in order for buy signal
    prices = [tp.price for tp in signal.take_profits]
    assert prices == sorted(prices)  # For buy signal, prices should increase 