"""Tests for MT5 position management."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from src.mt5.position_manager import (
    PositionManager,
    PositionType,
    PositionStatus,
    PositionInfo,
    RiskConfig
)
from src.mt5.connection import MT5Connection, MT5Config

@pytest.fixture
def mock_mt5():
    """Mock MT5 module for testing."""
    with patch("src.mt5.position_manager.mt5") as mock:
        # Mock account info
        mock.account_info.return_value = MagicMock(
            balance=10000.0,
            equity=10100.0,
            margin=1000.0,
            free_margin=9100.0
        )
        
        # Mock symbol info
        mock.symbol_info.return_value = MagicMock(
            point=0.0001,
            digits=5,
            volume_min=0.01,
            volume_max=10.0,
            volume_step=0.01,
            trade_tick_value=1.0
        )
        
        # Mock positions
        mock.positions_get.return_value = [
            MagicMock(
                ticket=12345,
                symbol="EURUSD",
                type=0,  # POSITION_TYPE_BUY
                volume=0.1,
                price_open=1.1000,
                price_current=1.1050,
                sl=1.0900,
                tp=1.1200,
                profit=50.0,
                swap=0.0,
                comment="Test position",
                magic=123456,
                time=int(datetime.now().timestamp())
            )
        ]
        
        yield mock

@pytest.fixture
def mt5_config():
    """Create test MT5 configuration."""
    return MT5Config(
        server="test_server",
        login=12345,
        password="test_password"
    )

@pytest.fixture
def connection(mt5_config):
    """Create MT5Connection instance for testing."""
    connection = MT5Connection(config=mt5_config)
    connection._connected = True  # Simulate connected state
    return connection

@pytest.fixture
def risk_config():
    """Create test risk configuration."""
    return RiskConfig(
        account_balance=10000.0,
        risk_per_trade=1.0,
        max_open_trades=5,
        max_daily_loss=5.0,
        max_symbol_risk=10.0,
        position_sizing="risk_based"
    )

@pytest.fixture
def manager(connection, risk_config):
    """Create PositionManager instance for testing."""
    return PositionManager(connection, risk_config)

@pytest.mark.asyncio
async def test_update_positions(manager, mock_mt5):
    """Test updating position information."""
    await manager.update_positions()
    
    positions = await manager.get_all_positions()
    assert len(positions) == 1
    assert positions[0].ticket == 12345
    assert positions[0].symbol == "EURUSD"
    assert positions[0].type == PositionType.BUY
    assert positions[0].volume == 0.1
    assert positions[0].status == PositionStatus.OPEN

@pytest.mark.asyncio
async def test_position_modification(manager, mock_mt5):
    """Test tracking position modifications."""
    # Initial position
    await manager.update_positions()
    
    # Modify position
    mock_mt5.positions_get.return_value[0].sl = 1.0950
    mock_mt5.positions_get.return_value[0].tp = 1.1150
    
    await manager.update_positions()
    
    position = await manager.get_position_info(12345)
    assert position is not None
    assert position.status == PositionStatus.MODIFIED
    assert position.sl == 1.0950
    assert position.tp == 1.1150
    assert len(position.modifications) == 1

@pytest.mark.asyncio
async def test_position_closure(manager, mock_mt5):
    """Test tracking position closure."""
    # Initial position
    await manager.update_positions()
    
    # Close position
    mock_mt5.positions_get.return_value = []
    
    await manager.update_positions()
    
    positions = await manager.get_all_positions()
    assert len(positions) == 0
    
    stats = await manager.get_daily_stats()
    assert stats["trades"] == 1
    assert stats["wins"] == 1
    assert stats["profit"] == 50.0

@pytest.mark.asyncio
async def test_calculate_position_size_risk_based(manager, mock_mt5):
    """Test risk-based position sizing."""
    size = await manager.calculate_position_size(
        symbol="EURUSD",
        entry_price=1.1000,
        stop_loss=1.0900
    )
    
    assert size is not None
    assert size > 0
    assert size <= mock_mt5.symbol_info.return_value.volume_max
    assert size >= mock_mt5.symbol_info.return_value.volume_min

@pytest.mark.asyncio
async def test_calculate_position_size_fixed(manager, mock_mt5):
    """Test fixed position sizing."""
    manager.risk_config.position_sizing = "fixed"
    manager.risk_config.fixed_position_size = 0.1
    
    size = await manager.calculate_position_size(
        symbol="EURUSD",
        entry_price=1.1000,
        stop_loss=1.0900
    )
    
    assert size == 0.1

@pytest.mark.asyncio
async def test_max_open_trades_limit(manager, mock_mt5):
    """Test position size calculation with max open trades limit."""
    # Fill up positions
    mock_mt5.positions_get.return_value = [
        MagicMock(
            ticket=i,
            symbol="EURUSD",
            type=0,
            volume=0.1,
            price_open=1.1000,
            price_current=1.1050,
            sl=1.0900,
            tp=1.1200,
            profit=50.0,
            swap=0.0,
            comment=f"Test position {i}",
            magic=123456,
            time=int(datetime.now().timestamp())
        )
        for i in range(5)  # Max open trades
    ]
    
    await manager.update_positions()
    
    # Try to calculate position size
    size = await manager.calculate_position_size(
        symbol="EURUSD",
        entry_price=1.1000,
        stop_loss=1.0900
    )
    
    assert size is None  # Should be None due to max open trades limit

@pytest.mark.asyncio
async def test_symbol_risk_limit(manager, mock_mt5):
    """Test position size calculation with symbol risk limit."""
    # Add existing position with high risk
    mock_mt5.positions_get.return_value = [
        MagicMock(
            ticket=12345,
            symbol="EURUSD",
            type=0,
            volume=1.0,  # Large position
            price_open=1.1000,
            price_current=1.1050,
            sl=1.0000,  # Wide stop loss
            tp=1.1200,
            profit=50.0,
            swap=0.0,
            comment="Test position",
            magic=123456,
            time=int(datetime.now().timestamp())
        )
    ]
    
    await manager.update_positions()
    
    # Try to calculate position size
    size = await manager.calculate_position_size(
        symbol="EURUSD",
        entry_price=1.1000,
        stop_loss=1.0900
    )
    
    assert size is None  # Should be None due to symbol risk limit

@pytest.mark.asyncio
async def test_check_risk_limits(manager, mock_mt5):
    """Test risk limit checking."""
    # Initial check
    compliant, reason = await manager.check_risk_limits()
    assert compliant
    assert "within bounds" in reason
    
    # Test daily loss limit
    manager._daily_stats["profit"] = -600.0  # 6% loss
    compliant, reason = await manager.check_risk_limits()
    assert not compliant
    assert "Daily loss limit" in reason
    
    # Test max open trades
    mock_mt5.positions_get.return_value = [
        MagicMock(
            ticket=i,
            symbol="EURUSD",
            type=0,
            volume=0.1,
            price_open=1.1000,
            price_current=1.1050,
            sl=1.0900,
            tp=1.1200,
            profit=50.0,
            swap=0.0,
            comment=f"Test position {i}",
            magic=123456,
            time=int(datetime.now().timestamp())
        )
        for i in range(6)  # Exceed max open trades
    ]
    
    await manager.update_positions()
    compliant, reason = await manager.check_risk_limits()
    assert not compliant
    assert "Max open trades exceeded" in reason

@pytest.mark.asyncio
async def test_disconnected_manager(manager, mock_mt5):
    """Test operations when MT5 is disconnected."""
    manager.connection._connected = False
    
    # Test various operations
    await manager.update_positions()
    assert await manager.get_all_positions() == []
    
    assert await manager.calculate_position_size(
        symbol="EURUSD",
        entry_price=1.1000,
        stop_loss=1.0900
    ) is None
    
    assert await manager.get_position_info(12345) is None
    
    compliant, reason = await manager.check_risk_limits()
    assert not compliant
    assert "not available" in reason 