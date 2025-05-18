"""Tests for MT5 connection management."""

import os
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from src.mt5.connection import MT5Connection, MT5Config

@pytest.fixture(autouse=True)
def patch_mt5():
    with patch("src.mt5.mt5_utils.get_mt5") as mock_get_mt5, \
         patch("src.mt5.mt5_utils.is_mt5_available", return_value=True):
        mock_mt5 = MagicMock()
        mock_get_mt5.return_value = mock_mt5
        # Mock terminal info
        mock_mt5.terminal_info.return_value = MagicMock(
            connected=True,
            trade_allowed=True
        )
        # Mock account info
        mock_mt5.account_info.return_value = MagicMock(
            balance=10000.0,
            equity=10050.0
        )
        # Mock symbols
        mock_mt5.symbols_get.return_value = [
            MagicMock(name="EURUSD"),
            MagicMock(name="GBPUSD"),
            MagicMock(name="XAUUSD")
        ]
        mock_mt5.symbols_total.return_value = 3
        yield

@pytest.fixture
def mt5_config():
    """Create test MT5 configuration."""
    return MT5Config(
        server="test_server",
        login=12345,
        password="test_password",
        timeout_ms=1000,
        retry_delay_seconds=1,
        max_retries=2,
        health_check_interval_seconds=1
    )

@pytest.fixture
def connection(mt5_config):
    """Create MT5Connection instance for testing."""
    return MT5Connection(config=mt5_config)

@pytest.mark.asyncio
async def test_connection_success(connection):
    """Test successful connection to MT5."""
    connection.mt5.initialize.return_value = True
    connection.mt5.login.return_value = True
    success = await connection.connect()
    assert success
    assert connection.is_connected
    assert connection.mt5.initialize.called
    assert connection.mt5.login.called
    assert len(connection.available_symbols) == 3

@pytest.mark.asyncio
async def test_connection_failure(connection):
    """Test failed connection to MT5."""
    connection.mt5.initialize.return_value = False
    connection.mt5.last_error.return_value = (1, "Test error")
    success = await connection.connect()
    assert not success
    assert not connection.is_connected
    assert connection.mt5.initialize.called
    assert not connection.mt5.login.called

@pytest.mark.asyncio
async def test_connection_login_failure(connection):
    """Test failed login to MT5."""
    connection.mt5.initialize.return_value = True
    connection.mt5.login.return_value = False
    connection.mt5.last_error.return_value = (2, "Invalid credentials")
    success = await connection.connect()
    assert not success
    assert not connection.is_connected
    assert connection.mt5.initialize.called
    assert connection.mt5.login.called

@pytest.mark.asyncio
async def test_disconnect(connection):
    """Test disconnecting from MT5."""
    connection.mt5.initialize.return_value = True
    connection.mt5.login.return_value = True
    await connection.connect()
    await connection.disconnect()
    assert not connection.is_connected
    assert connection.mt5.shutdown.called

@pytest.mark.asyncio
async def test_health_check_loop(connection):
    """Test health check monitoring."""
    connection.mt5.initialize.return_value = True
    connection.mt5.login.return_value = True
    await connection.connect()
    connection.mt5.terminal_info.return_value = None
    await asyncio.sleep(1.5)
    assert connection._connection_attempts > 0
    assert connection.mt5.initialize.call_count > 1

@pytest.mark.asyncio
async def test_max_retries(connection):
    """Test maximum reconnection attempts."""
    connection.mt5.initialize.return_value = True
    connection.mt5.login.return_value = True
    await connection.connect()
    connection.mt5.terminal_info.return_value = None
    connection.mt5.initialize.return_value = False
    await asyncio.sleep(3)
    assert connection._connection_attempts >= connection.config.max_retries
    assert not connection.is_connected

@pytest.mark.asyncio
async def test_connection_info(connection):
    """Test getting connection information."""
    connection.mt5.initialize.return_value = True
    connection.mt5.login.return_value = True
    await connection.connect()
    info = connection.get_connection_info()
    assert info["connected"]
    assert info["server"] == connection.config.server
    assert info["login"] == connection.config.login
    assert info["terminal"]["connected"]
    assert info["terminal"]["trade_allowed"]
    assert info["terminal"]["balance"] == 10000.0
    assert info["terminal"]["equity"] == 10050.0

@pytest.mark.asyncio
async def test_connection_info_disconnected(mt5_config):
    """Test getting connection information when disconnected."""
    connection = MT5Connection(config=mt5_config)
    info = connection.get_connection_info()
    assert not info["connected"]
    assert info["last_health_check"] is None
    assert info["connection_attempts"] == 0

@pytest.mark.asyncio
async def test_environment_config():
    """Test loading configuration from environment variables."""
    test_env = {
        "MT5_SERVER": "env_server",
        "MT5_LOGIN": "54321",
        "MT5_PASSWORD": "env_password"
    }
    with patch.dict(os.environ, test_env):
        config = MT5Config.from_environment()
        connection = MT5Connection(config=config)
        assert connection.config.server == "env_server"
        assert connection.config.login == 54321
        assert connection.config.password == "env_password"

def test_missing_environment_vars():
    """Test handling of missing environment variables."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError) as exc_info:
            MT5Config.from_environment()
        assert "Missing required environment variables" in str(exc_info.value) 