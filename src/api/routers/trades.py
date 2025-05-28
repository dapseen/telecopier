"""Trade router for managing MT5 trade execution.

This module provides endpoints for:
- Trade execution from signals
- Trade management and monitoring
- Trade status updates
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query

from src.common.types import TradeState
from ..models import (
    TradeCreate,
    TradeResponse,
    TradeUpdate,
    MT5OrderResponse,
    MT5PositionResponse,
    MT5PositionModify
)
from ..services.mt5_service import MT5Service
from ..dependencies import get_mt5_service, get_signal_service, get_trade_repository
from ..services.signal_service import SignalService
from src.db.repositories.trade import TradeRepository

router = APIRouter()

@router.post("/execute", response_model=MT5OrderResponse)
async def execute_trade(
    signal_id: UUID,
    mt5_service: MT5Service = Depends(get_mt5_service),
    signal_service: SignalService = Depends(get_signal_service)
) -> MT5OrderResponse:
    """Execute a trade from a validated signal.
    
    Args:
        signal_id: ID of the validated signal
        mt5_service: MT5 service instance
        signal_service: Signal service instance
        
    Returns:
        MT5OrderResponse: Execution result
        
    Raises:
        HTTPException: If trade execution fails
    """
    try:
        # Get and validate signal
        signal = await signal_service.get_signal(signal_id)
        if not signal or signal.status != "VALID":
            raise HTTPException(
                status_code=400,
                detail="Signal not found or not validated"
            )
            
        # Execute trade
        result = await mt5_service.execute_gold_trade(
            symbol=signal.symbol,
            direction=signal.direction.value,
            entry=signal.entry_price,
            sl=signal.stop_loss,
            tps=[(tp.price, 0.25) for tp in signal.take_profits],
            comment=f"Signal ID: {signal_id}"
        )
        
        if not result:
            raise HTTPException(
                status_code=400,
                detail="Trade execution failed"
            )
            
        # Get order details
        order = await mt5_service.get_order_info(result)
        if not order:
            raise HTTPException(
                status_code=404,
                detail="Order not found after execution"
            )
            
        return MT5OrderResponse(
            ticket=order["ticket"],
            symbol=order["symbol"],
            order_type="MARKET",
            direction=order["type"],
            volume=order["volume"],
            price=order["price_open"],
            stop_loss=order["sl"],
            take_profit=order["tp"],
            comment=order["comment"],
            magic=order["magic"],
            state=TradeState.OPEN,
            error=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Trade execution failed: {str(e)}"
        )

@router.get("/{ticket}", response_model=MT5PositionResponse)
async def get_trade(
    ticket: int,
    mt5_service: MT5Service = Depends(get_mt5_service)
) -> MT5PositionResponse:
    """Get trade details by ticket number.
    
    Args:
        ticket: MT5 ticket number
        mt5_service: MT5 service instance
        
    Returns:
        MT5PositionResponse: Position details
        
    Raises:
        HTTPException: If position not found
    """
    try:
        position = await mt5_service.get_order_info(ticket)
        if not position:
            raise HTTPException(
                status_code=404,
                detail="Position not found"
            )
            
        return MT5PositionResponse(
            ticket=position["ticket"],
            symbol=position["symbol"],
            direction=position["type"],
            volume=position["volume"],
            price=position["price_open"],
            stop_loss=position["sl"],
            take_profit=position["tp"],
            comment=position["comment"],
            magic=position["magic"],
            profit=position["profit"],
            swap=position["swap"],
            commission=0.0,  # Not available in position info
            open_time=position.get("open_time", None)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get position info: {str(e)}"
        )

@router.post("/{ticket}/modify", response_model=MT5PositionResponse)
async def modify_trade(
    ticket: int,
    modification: MT5PositionModify,
    mt5_service: MT5Service = Depends(get_mt5_service)
) -> MT5PositionResponse:
    """Modify an open position's SL/TP.
    
    Args:
        ticket: MT5 ticket number
        modification: New SL/TP values
        mt5_service: MT5 service instance
        
    Returns:
        MT5PositionResponse: Updated position details
        
    Raises:
        HTTPException: If modification fails
    """
    try:
        # Verify position exists
        position = await mt5_service.get_order_info(ticket)
        if not position:
            raise HTTPException(
                status_code=404,
                detail="Position not found"
            )
            
        # Apply modification
        success = await mt5_service.executor.modify_order({
            "order_id": ticket,
            "stop_loss": modification.stop_loss,
            "take_profit": modification.take_profit
        })
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to modify position"
            )
            
        # Get updated position
        updated = await mt5_service.get_order_info(ticket)
        return MT5PositionResponse(
            ticket=updated["ticket"],
            symbol=updated["symbol"],
            direction=updated["type"],
            volume=updated["volume"],
            price=updated["price_open"],
            stop_loss=updated["sl"],
            take_profit=updated["tp"],
            comment=updated["comment"],
            magic=updated["magic"],
            profit=updated["profit"],
            swap=updated["swap"],
            commission=0.0,
            open_time=updated.get("open_time", None)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Position modification failed: {str(e)}"
        )

@router.post("/{ticket}/close", response_model=MT5OrderResponse)
async def close_trade(
    ticket: int,
    volume: Optional[float] = None,
    mt5_service: MT5Service = Depends(get_mt5_service)
) -> MT5OrderResponse:
    """Close an open position.
    
    Args:
        ticket: MT5 ticket number
        volume: Optional volume to close (for partial close)
        mt5_service: MT5 service instance
        
    Returns:
        MT5OrderResponse: Close order result
        
    Raises:
        HTTPException: If close operation fails
    """
    try:
        # Verify position exists
        position = await mt5_service.get_order_info(ticket)
        if not position:
            raise HTTPException(
                status_code=404,
                detail="Position not found"
            )
            
        # Close position
        success = await mt5_service.executor.close_order(ticket, volume)
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to close position"
            )
            
        return MT5OrderResponse(
            ticket=ticket,
            symbol=position["symbol"],
            order_type="CLOSE",
            direction="SELL" if position["type"] == "BUY" else "BUY",
            volume=volume or position["volume"],
            price=position["price_current"],
            stop_loss=None,
            take_profit=None,
            comment="Close position",
            magic=position["magic"],
            state=TradeState.CLOSED,
            error=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Position close failed: {str(e)}"
        )

@router.post("/", response_model=TradeResponse)
async def create_trade(
    trade: TradeCreate,
    repo: TradeRepository = Depends(get_trade_repository)
) -> TradeResponse:
    """Create a new trade.
    
    Args:
        trade: Trade data
        repo: Trade repository
        
    Returns:
        TradeResponse: Created trade
        
    Raises:
        HTTPException: If trade creation fails
    """
    try:
        db_trade = await repo.create(trade.model_dump())
        return TradeResponse.model_validate(db_trade)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create trade: {str(e)}"
        )

@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: UUID,
    repo: TradeRepository = Depends(get_trade_repository)
) -> TradeResponse:
    """Get trade by ID.
    
    Args:
        trade_id: Trade ID
        repo: Trade repository
        
    Returns:
        TradeResponse: Trade data
        
    Raises:
        HTTPException: If trade not found
    """
    trade = await repo.get(trade_id)
    if not trade:
        raise HTTPException(
            status_code=404,
            detail="Trade not found"
        )
    return TradeResponse.model_validate(trade)

@router.get("/", response_model=List[TradeResponse])
async def list_trades(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    signal_id: Optional[UUID] = None,
    symbol: Optional[str] = None,
    state: Optional[str] = None,
    repo: TradeRepository = Depends(get_trade_repository)
) -> List[TradeResponse]:
    """List trades with optional filtering.
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        signal_id: Filter by signal ID
        symbol: Filter by trading symbol
        state: Filter by trade state
        repo: Trade repository
        
    Returns:
        List[TradeResponse]: List of trades
    """
    filters = {}
    if signal_id:
        filters["signal_id"] = signal_id
    if symbol:
        filters["symbol"] = symbol
    if state:
        filters["state"] = state
        
    trades = await repo.get_multi(
        skip=skip,
        limit=limit,
        filters=filters
    )
    return [TradeResponse.model_validate(t) for t in trades]

@router.patch("/{trade_id}", response_model=TradeResponse)
async def update_trade(
    trade_id: UUID,
    trade_update: TradeUpdate,
    repo: TradeRepository = Depends(get_trade_repository)
) -> TradeResponse:
    """Update trade status.
    
    Args:
        trade_id: Trade ID
        trade_update: Update data
        repo: Trade repository
        
    Returns:
        TradeResponse: Updated trade
        
    Raises:
        HTTPException: If trade not found or update fails
    """
    trade = await repo.get(trade_id)
    if not trade:
        raise HTTPException(
            status_code=404,
            detail="Trade not found"
        )
        
    try:
        updated_trade = await repo.update(
            db_obj=trade,
            obj_in=trade_update.model_dump(exclude_unset=True)
        )
        return TradeResponse.model_validate(updated_trade)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to update trade: {str(e)}"
        ) 