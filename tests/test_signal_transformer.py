"""Tests for the signal transformer."""

import pytest
from lark import Lark
from src.telegram.signal_transformer import SignalTransformer
from src.telegram.models import TradingSignal, TakeProfit
from src.common.types import SignalDirection, SignalType

# Load grammar file
with open('src/telegram/grammar/signal.lark', 'r') as f:
    GRAMMAR = f.read()

@pytest.fixture
def parser():
    """Create a Lark parser instance."""
    return Lark(GRAMMAR, parser='lalr', start='signal')

@pytest.fixture
def transformer():
    """Create a SignalTransformer instance."""
    valid_symbols = {'XAUUSD', 'EURUSD', 'GBPUSD'}
    return SignalTransformer(valid_symbols)

def test_parse_gold_signal(parser, transformer):
    """Test parsing a gold trading signal."""
    # Test signal
    signal_text = """XAUUSD Buy Now 
Enter 3334
SL 3324
TP1 3339
TP2 3345
TP3 3350
TP4 3355"""

    # Set raw message
    transformer._raw_message = signal_text
    
    # Parse and transform
    tree = parser.parse(signal_text)
    signal = transformer.transform(tree)
    
    # Verify signal was created
    assert signal is not None
    assert isinstance(signal, TradingSignal)
    
    # Verify basic properties
    assert signal.symbol == 'XAUUSD'
    assert signal.direction == SignalDirection.BUY
    assert signal.entry_price == 3334
    assert signal.stop_loss == 3324
    
    # Verify take profits
    assert len(signal.take_profits) == 4
    
    # Check each take profit level
    expected_tps = [
        (1, 3339),
        (2, 3345),
        (3, 3350),
        (4, 3355)
    ]
    
    for (expected_level, expected_price), tp in zip(expected_tps, signal.take_profits):
        assert tp.level == expected_level
        assert tp.price == expected_price
        
        # Verify pips calculation (for gold, multiply by 10 instead of 10000)
        expected_pips = abs(expected_price - signal.entry_price) * 10
        assert abs(tp.pips - expected_pips) < 0.01  # Allow for small floating point differences

def test_parse_invalid_symbol(parser, transformer):
    """Test parsing signal with invalid symbol."""
    signal_text = """INVALID Buy Now
Enter 1.2000
SL 1.1990
TP1 1.2010"""
    
    transformer._raw_message = signal_text
    tree = parser.parse(signal_text)
    signal = transformer.transform(tree)
    
    assert signal is None

def test_parse_missing_entry(parser, transformer):
    """Test parsing signal without entry price."""
    signal_text = """XAUUSD Buy Now
SL 1900
TP1 1920"""
    
    transformer._raw_message = signal_text
    tree = parser.parse(signal_text)
    signal = transformer.transform(tree)
    
    assert signal is None

def test_parse_invalid_price(parser, transformer):
    """Test parsing signal with invalid price format."""
    signal_text = """XAUUSD Buy Now
Enter invalid
SL 1900
TP1 1920"""
    
    transformer._raw_message = signal_text
    tree = parser.parse(signal_text)
    signal = transformer.transform(tree)
    
    assert signal is None 