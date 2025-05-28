"""MT5 router for managing MetaTrader 5 operations.

This module provides endpoints for:
- MT5 connection management
- Order placement and management
- Position monitoring and modification
- Account information
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException

from src.common.types import OrderType, TradeState
from ..dependencies import get_mt5_service
from ..models import (
    MT5OrderCreate,
    MT5OrderResponse,
    MT5PositionResponse,
    MT5PositionModify,
    MT5ConnectionStatus,
    MT5AccountInfo
)
from ..services.mt5_service import MT5Service

router = APIRouter()

@router.get("/status", response_model=MT5ConnectionStatus)
async def get_connection_status(
    service: MT5Service = Depends(get_mt5_service)
) -> Dict:
    """Get MT5 connection status.
    
    Args:
        service: MT5 service instance
        
    Returns:
        Dictionary containing connection status and info
    """
    return await service.get_connection_status()

@router.get("/account", response_model=MT5AccountInfo)
async def get_account_info(
    service: MT5Service = Depends(get_mt5_service)
) -> Dict:
    """Get MT5 account information.
    
    Args:
        service: MT5 service instance
        
    Returns:
        Dictionary containing account information
    """
    return await service.get_account_info()

@router.post("/orders", response_model=MT5OrderResponse)
async def place_order(
    order: MT5OrderCreate,
    service: MT5Service = Depends(get_mt5_service)
) -> Dict:
    """Place a trading order.
    
    Args:
        order: Order parameters
        service: MT5 service instance
        
    Returns:
        Dictionary containing order result
    """
    return await service.place_order(
        symbol=order.symbol,
        order_type=order.order_type,
        direction=order.direction,
        volume=order.volume,
        price=order.price,
        stop_loss=order.stop_loss,
        take_profit=order.take_profit,
        comment=order.comment,
        magic=order.magic
    )

@router.get("/positions", response_model=List[MT5PositionResponse])
async def get_positions(
    service: MT5Service = Depends(get_mt5_service)
) -> List[Dict]:
    """Get all open positions.
    
    Args:
        service: MT5 service instance
        
    Returns:
        List of dictionaries containing position information
    """
    return await service.get_positions()

@router.delete("/positions/{ticket}")
async def close_position(
    ticket: int,
    volume: Optional[float] = None,
    service: MT5Service = Depends(get_mt5_service)
) -> Dict:
    """Close a position.
    
    Args:
        ticket: Position ticket number
        volume: Optional volume to close (for partial closes)
        service: MT5 service instance
        
    Returns:
        Dictionary containing close result
    """
    return await service.close_position(ticket=ticket, volume=volume)

@router.patch("/positions/{ticket}", response_model=MT5PositionResponse)
async def modify_position(
    ticket: int,
    position: MT5PositionModify,
    service: MT5Service = Depends(get_mt5_service)
) -> Dict:
    """Modify a position's stop loss and take profit.
    
    Args:
        ticket: Position ticket number
        position: Position modification parameters
        service: MT5 service instance
        
    Returns:
        Dictionary containing modification result
    """
    return await service.modify_position(
        ticket=ticket,
        stop_loss=position.stop_loss,
        take_profit=position.take_profit
    )

@router.get("/symbols")
async def get_available_symbols(
    service: MT5Service = Depends(get_mt5_service)
) -> List[str]:
    """Get available trading symbols.
    
    Args:
        service: MT5 service instance
        
    Returns:
        List of available trading symbols
    """
    return list(await service.get_available_symbols()) 