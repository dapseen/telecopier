"""Tests for the signal parser module.

This module contains tests for the GPT-3.5 based signal parser.
"""

import os
import pytest
from unittest.mock import AsyncMock, patch
from src.telegram.signal_parser import SignalParser, TradingSignal, TakeProfit
from src.common.types import SignalDirection, SignalType

@pytest.fixture
def mock_openai():
    """Mock OpenAI client responses."""
    with patch('src.telegram.signal_parser.AsyncOpenAI') as mock:
        # Create mock completion response
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(
                message=AsyncMock(
                    content='''{
                        "symbol": "XAUUSD",
                        "direction": "BUY",
                        "entry": 3232.0,
                        "sl": 3220.0,
                        "take_profits": {
                            "TP1": 3235.0,
                            "TP2": 3239.0,
                            "TP3": 3255.0,
                            "TP4": 3333.5
                        },
                        "notes": "Max 0.25%"
                    }'''
                )
            )
        ]
        mock.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        yield mock

@pytest.fixture
def parser(mock_openai):
    """Create a SignalParser instance with test configuration."""
    return SignalParser(
        api_key="test_key",
        valid_symbols={'XAUUSD', 'EURUSD', 'GBPUSD'},
        model="gpt-3.5-turbo",
        temperature=0.1,
        max_tokens=300
    )

@pytest.mark.asyncio
async def test_parser_initialization():
    """Test parser initialization with API key."""
    # Test valid initialization
    parser = SignalParser(
        api_key="test_key",
        valid_symbols={'XAUUSD'}
    )
    assert parser.api_key == "test_key"
    assert parser.valid_symbols == {'XAUUSD'}
    assert parser.model == "gpt-3.5-turbo"
    
    # Test missing API key
    with pytest.raises(ValueError):
        SignalParser(api_key="")

@pytest.mark.asyncio
async def test_parse_valid_signal(parser, mock_openai):
    """Test parsing of a valid trading signal."""
    message = """
        XAUUSD buy now 
        Enter 3232
        SL 3220
        TP1 3235
        TP2 3239
        TP3 3255
    TP4 3333.50
        
        Max 0.25%
    """
    
    signal = await parser.parse(
        message=message,
        message_id=123,
        chat_id=456,
        channel_name="test_channel"
    )
    
    assert signal is not None
    assert isinstance(signal, TradingSignal)
    assert signal.symbol == "XAUUSD"
    assert signal.direction == SignalDirection.BUY
    assert signal.entry_price == 3232.0
    assert signal.stop_loss == 3220.0
    assert len(signal.take_profits) == 4
    assert signal.take_profits[0].price == 3235.0
    assert signal.take_profits[-1].price == 3333.5
    assert signal.message_id == 123
    assert signal.chat_id == 456
    assert signal.channel_name == "test_channel"
    assert signal.confidence_score == 0.95

@pytest.mark.asyncio
async def test_parse_invalid_signal(parser, mock_openai):
    """Test parsing of invalid signals."""
    # Mock OpenAI to return null for invalid signal
    mock_openai.return_value.chat.completions.create.return_value.choices[0].message.content = "null"
    
    message = "This is not a trading signal"
    signal = await parser.parse(message)
    assert signal is None

@pytest.mark.asyncio
async def test_parse_invalid_symbol(parser, mock_openai):
    """Test parsing signal with invalid symbol."""
    # Mock OpenAI to return invalid symbol
    mock_openai.return_value.chat.completions.create.return_value.choices[0].message.content = '''{
        "symbol": "INVALID",
        "direction": "BUY",
        "entry": 100.0,
        "sl": 90.0
    }'''
    
    message = "INVALID buy now Enter 100 SL 90"
    signal = await parser.parse(message)
    assert signal is None

@pytest.mark.asyncio
async def test_parse_invalid_direction(parser, mock_openai):
    """Test parsing signal with invalid direction."""
    # Mock OpenAI to return invalid direction
    mock_openai.return_value.chat.completions.create.return_value.choices[0].message.content = '''{
        "symbol": "XAUUSD",
        "direction": "INVALID",
        "entry": 3232.0,
        "sl": 3220.0
    }'''
    
    message = "XAUUSD invalid_direction now Enter 3232 SL 3220"
    signal = await parser.parse(message)
    assert signal is None

@pytest.mark.asyncio
async def test_openai_error_handling(parser, mock_openai):
    """Test handling of OpenAI API errors."""
    # Mock OpenAI to raise an exception
    mock_openai.return_value.chat.completions.create.side_effect = Exception("API Error")
    
    message = "XAUUSD buy now Enter 3232 SL 3220"
    signal = await parser.parse(message)
    assert signal is None 