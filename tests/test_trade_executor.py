"""Tests for MT5 trade execution."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from src.mt5.trade_executor import (
    TradeExecutor,
    OrderRequest,
    OrderType,
    OrderAction,
    PartialTP,
    BreakevenConfig,
    OrderModification
)
from src.mt5.position_manager import RiskConfig
from src.mt5.connection import MT5Connection, MT5Config

@pytest.fixture
def mock_mt5():
    """Mock MT5 module for testing."""
    with patch("src.mt5.trade_executor.mt5") as mock:
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
        
        # Mock symbol tick
        mock.symbol_info_tick.return_value = MagicMock(
            ask=1.1000,
            bid=1.0990
        )
        
        # Mock order send
        mock.order_send.return_value = MagicMock(
            retcode=10009,  # TRADE_RETCODE_DONE
            order=12345,
            price=1.1000,
            sl=1.0900,
            tp=1.1200
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
def executor(connection, risk_config):
    """Create TradeExecutor instance for testing."""
    return TradeExecutor(connection, risk_config)

@pytest.mark.asyncio
async def test_place_order_with_risk_management(executor, mock_mt5):
    """Test order placement with risk management."""
    request = OrderRequest(
        symbol="EURUSD",
        action=OrderAction.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,  # Will be overridden by position manager
        stop_loss=1.0900
    )
    
    order_id = await executor.place_order(request)
    assert order_id is not None
    
    # Verify position manager was updated
    positions = await executor.position_manager.get_all_positions()
    assert len(positions) == 1
    assert positions[0].ticket == order_id

@pytest.mark.asyncio
async def test_place_order_risk_limits_exceeded(executor, mock_mt5):
    """Test order placement when risk limits are exceeded."""
    # Mock risk check to fail
    executor.position_manager.check_risk_limits = AsyncMock(
        return_value=(False, "Daily loss limit reached")
    )
    
    request = OrderRequest(
        symbol="EURUSD",
        action=OrderAction.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
        stop_loss=1.0900
    )
    
    order_id = await executor.place_order(request)
    assert order_id is None

@pytest.mark.asyncio
async def test_modify_order_with_position_tracking(executor, mock_mt5):
    """Test order modification with position tracking."""
    # Place initial order
    request = OrderRequest(
        symbol="EURUSD",
        action=OrderAction.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
        stop_loss=1.0900
    )
    order_id = await executor.place_order(request)
    
    # Modify order
    modification = OrderModification(
        order_id=order_id,
        stop_loss=1.0950
    )
    
    success = await executor.modify_order(modification)
    assert success
    
    # Verify position was updated
    position = await executor.position_manager.get_position_info(order_id)
    assert position is not None
    assert position.status == "modified"
    assert len(position.modifications) == 1

@pytest.mark.asyncio
async def test_close_order_with_position_tracking(executor, mock_mt5):
    """Test order closure with position tracking."""
    # Place initial order
    request = OrderRequest(
        symbol="EURUSD",
        action=OrderAction.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
        stop_loss=1.0900
    )
    order_id = await executor.place_order(request)
    
    # Close order
    success = await executor.close_order(order_id)
    assert success
    
    # Verify position was closed
    position = await executor.position_manager.get_position_info(order_id)
    assert position is None
    
    # Verify daily stats were updated
    stats = await executor.position_manager.get_daily_stats()
    assert stats["trades"] == 1
    assert stats["profit"] == 50.0

@pytest.mark.asyncio
async def test_get_order_info_with_position_details(executor, mock_mt5):
    """Test getting order information with position details."""
    # Place initial order
    request = OrderRequest(
        symbol="EURUSD",
        action=OrderAction.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
        stop_loss=1.0900
    )
    order_id = await executor.place_order(request)
    
    # Get order info
    info = await executor.get_order_info(order_id)
    assert info is not None
    assert info["ticket"] == order_id
    assert info["position_status"] == "open"
    assert info["modifications"] == []
    assert info["partial_closes"] == []

@pytest.mark.asyncio
async def test_get_trading_stats(executor, mock_mt5):
    """Test getting comprehensive trading statistics."""
    # Place initial order
    request = OrderRequest(
        symbol="EURUSD",
        action=OrderAction.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
        stop_loss=1.0900
    )
    await executor.place_order(request)
    
    # Get trading stats
    stats = await executor.get_trading_stats()
    assert "daily_stats" in stats
    assert "open_positions" in stats
    assert "total_profit" in stats
    assert "total_swap" in stats
    assert "risk_compliance" in stats
    
    assert stats["open_positions"] == 1
    assert stats["total_profit"] == 50.0
    assert isinstance(stats["risk_compliance"], tuple)

@pytest.mark.asyncio
async def test_disconnected_executor(executor, mock_mt5):
    """Test operations when MT5 is disconnected."""
    executor.connection._connected = False
    
    # Test various operations
    request = OrderRequest(
        symbol="EURUSD",
        action=OrderAction.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
        stop_loss=1.0900
    )
    
    assert await executor.place_order(request) is None
    assert not await executor.modify_order(OrderModification(order_id=12345))
    assert not await executor.close_order(12345)
    assert await executor.get_order_info(12345) is None
    assert await executor.get_all_orders() == []
    
    stats = await executor.get_trading_stats()
    assert stats["open_positions"] == 0
    assert stats["total_profit"] == 0.0
    assert not stats["risk_compliance"][0] 