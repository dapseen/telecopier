"""
Tests for the TelegramClient class.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update, Message, Chat
from telegram.ext import ContextTypes

from src.telegram.client import TelegramClient

@pytest.fixture
def mock_update():
    """Create a mock Telegram update."""
    chat = MagicMock(spec=Chat)
    chat.id = "123456789"
    
    message = MagicMock(spec=Message)
    message.message_id = 1
    message.chat = chat
    message.text = "Test message"
    message.date = datetime.now()
    message.edit_date = None
    
    update = MagicMock(spec=Update)
    update.message = message
    return update

@pytest.fixture
def mock_context():
    """Create a mock Telegram context."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    return context

@pytest.fixture
def client():
    """Create a TelegramClient instance for testing."""
    return TelegramClient(
        api_id="test_api_id",
        api_hash="test_api_hash",
        channel_id="123456789",
        session_path=":memory:",  # Use in-memory session for testing
    )

@pytest.mark.asyncio
async def test_client_initialization(client):
    """Test client initialization with correct parameters."""
    assert client.api_id == "test_api_id"
    assert client.api_hash == "test_api_hash"
    assert client.channel_id == "123456789"
    assert not client.is_connected
    assert client.last_message_time is None

@pytest.mark.asyncio
async def test_connection_retry_logic(client):
    """Test connection retry logic when connection fails."""
    with patch("telegram.ext.ApplicationBuilder.build") as mock_build:
        # Simulate connection failure
        mock_build.side_effect = Exception("Connection failed")
        
        with pytest.raises(ConnectionError) as exc_info:
            await client.connect()
        
        assert "Failed to connect after 5 attempts" in str(exc_info.value)
        assert client._connection_attempts == 5

@pytest.mark.asyncio
async def test_message_handling(client, mock_update, mock_context):
    """Test message handling with callback."""
    callback_called = False
    received_data = None
    
    async def mock_callback(data):
        nonlocal callback_called, received_data
        callback_called = True
        received_data = data
    
    client.message_callback = mock_callback
    await client._handle_message(mock_update, mock_context)
    
    assert callback_called
    assert received_data["message_id"] == 1
    assert received_data["text"] == "Test message"
    assert client.last_message_time is not None

@pytest.mark.asyncio
async def test_status_command(client, mock_update, mock_context):
    """Test status command handling."""
    await client._handle_status(mock_update, mock_context)
    
    # Verify status message was sent
    mock_update.message.reply_text.assert_called_once()
    status_text = mock_update.message.reply_text.call_args[0][0]
    assert "connected" in status_text.lower()

@pytest.mark.asyncio
async def test_disconnect_not_connected(client):
    """Test disconnect when not connected."""
    await client.disconnect()  # Should not raise any errors
    assert not client.is_connected

@pytest.mark.asyncio
async def test_disconnect_while_connected(client):
    """Test disconnect when connected."""
    # Mock the application
    mock_app = AsyncMock()
    client.app = mock_app
    client._is_connected = True
    
    await client.disconnect()
    
    assert not client.is_connected
    mock_app.stop.assert_called_once()
    mock_app.shutdown.assert_called_once() 