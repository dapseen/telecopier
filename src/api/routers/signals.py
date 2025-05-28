"""Signal router for managing trading signals.

This module provides endpoints for:
- Signal creation and management
- Signal queue operations
- Signal validation and processing
"""

from typing import Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query

from src.common.types import SignalDirection, SignalType, SignalStatus, SignalPriority
from src.telegram.signal_parser import SignalParser, TradingSignal
from src.telegram.signal_queue import SignalQueue
from ..dependencies import get_signal_repository, get_mt5_service
from ..models import (
    SignalCreate,
    SignalUpdate,
    SignalResponse,
    QueueStatsResponse,
    MT5OrderResponse
)
from ..services.signal_service import SignalService
from ..services.mt5_service import MT5Service
from src.db.repositories.signal import SignalRepository

router = APIRouter()

# Dependencies
async def get_signal_service(
    repo: SignalRepository = Depends(get_signal_repository)
) -> SignalService:
    """Get signal service instance.
    
    Args:
        repo: Signal repository
        
    Returns:
        SignalService: Signal service instance
    """
    # Initialize components
    parser = SignalParser()
    queue = SignalQueue()
    return SignalService(parser, queue, repo)

@router.post("/", response_model=SignalResponse)
async def create_signal(
    signal: SignalCreate,
    service: SignalService = Depends(get_signal_service)
) -> SignalResponse:
    """Create a new signal.
    
    Args:
        signal: Signal data
        service: Signal service
        
    Returns:
        SignalResponse: Created signal
        
    Raises:
        HTTPException: If signal creation fails
    """
    try:
        return await service.process_telegram_message(
            message_text=signal.raw_message,
            chat_id=signal.chat_id,
            message_id=signal.message_id,
            channel_name=signal.channel_name
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create signal: {str(e)}"
        )

@router.post("/telegram", response_model=SignalResponse)
async def process_telegram_message(
    message_text: str,
    chat_id: int,
    message_id: int,
    channel_name: str,
    service: SignalService = Depends(get_signal_service)
) -> SignalResponse:
    """Process a Telegram message into a trading signal.
    
    Args:
        message_text: Raw message text
        chat_id: Telegram chat ID
        message_id: Telegram message ID
        channel_name: Channel name
        service: Signal service
        
    Returns:
        SignalResponse: Created signal
        
    Raises:
        HTTPException: If signal processing fails
    """
    try:
        return await service.process_telegram_message(
            message_text=message_text,
            chat_id=chat_id,
            message_id=message_id,
            channel_name=channel_name
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to process message: {str(e)}"
        )

@router.post("/{signal_id}/validate", response_model=SignalResponse)
async def validate_signal(
    signal_id: UUID,
    service: SignalService = Depends(get_signal_service)
) -> SignalResponse:
    """Validate a signal before execution.
    
    Args:
        signal_id: Signal ID
        service: Signal service
        
    Returns:
        SignalResponse: Validated signal
        
    Raises:
        HTTPException: If validation fails
    """
    try:
        # Get signal
        signal = await service.get_signal(signal_id)
        if not signal:
            raise HTTPException(
                status_code=404,
                detail="Signal not found"
            )
            
        # Validate signal
        validation_result = await service.validate_signal(signal_id)
        if not validation_result:
            raise HTTPException(
                status_code=400,
                detail="Signal validation failed"
            )
            
        return validation_result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Signal validation failed: {str(e)}"
        )

@router.post("/{signal_id}/execute", response_model=MT5OrderResponse)
async def execute_signal(
    signal_id: UUID,
    service: SignalService = Depends(get_signal_service),
    mt5_service: MT5Service = Depends(get_mt5_service)
) -> MT5OrderResponse:
    """Execute a validated signal.
    
    Args:
        signal_id: Signal ID
        service: Signal service
        mt5_service: MT5 service
        
    Returns:
        MT5OrderResponse: Execution result
        
    Raises:
        HTTPException: If execution fails
    """
    try:
        # Get and validate signal
        signal = await service.get_signal(signal_id)
        if not signal:
            raise HTTPException(
                status_code=404,
                detail="Signal not found"
            )
            
        if signal.status != "VALID":
            # Try to validate signal
            signal = await service.validate_signal(signal_id)
            if not signal or signal.status != "VALID":
                raise HTTPException(
                    status_code=400,
                    detail="Signal must be validated before execution"
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
            # Update signal status
            await service.update_signal(
                signal_id,
                SignalUpdate(
                    status="FAILED",
                    error_message="Trade execution failed"
                )
            )
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
            
        # Update signal status
        await service.update_signal(
            signal_id,
            SignalUpdate(
                status="EXECUTED",
                processed_at=order.get("open_time")
            )
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
        # Update signal status
        await service.update_signal(
            signal_id,
            SignalUpdate(
                status="FAILED",
                error_message=str(e)
            )
        )
        raise HTTPException(
            status_code=400,
            detail=f"Signal execution failed: {str(e)}"
        )

@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(
    signal_id: UUID,
    service: SignalService = Depends(get_signal_service)
) -> SignalResponse:
    """Get signal by ID.
    
    Args:
        signal_id: Signal ID
        service: Signal service
        
    Returns:
        SignalResponse: Signal data
        
    Raises:
        HTTPException: If signal not found
    """
    return await service.get_signal(signal_id)

@router.get("/", response_model=List[SignalResponse])
async def list_signals(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    channel_name: Optional[str] = None,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    service: SignalService = Depends(get_signal_service)
) -> List[SignalResponse]:
    """List signals with optional filtering.
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        channel_name: Filter by channel name
        symbol: Filter by trading symbol
        status: Filter by signal status
        service: Signal service
        
    Returns:
        List[SignalResponse]: List of signals
    """
    return await service.list_signals(
        skip=skip,
        limit=limit,
        channel_name=channel_name,
        symbol=symbol,
        status=status
    )

@router.patch("/{signal_id}", response_model=SignalResponse)
async def update_signal(
    signal_id: UUID,
    signal_update: SignalUpdate,
    service: SignalService = Depends(get_signal_service)
) -> SignalResponse:
    """Update signal status.
    
    Args:
        signal_id: Signal ID
        signal_update: Update data
        service: Signal service
        
    Returns:
        SignalResponse: Updated signal
        
    Raises:
        HTTPException: If signal not found or update fails
    """
    return await service.update_signal(signal_id, signal_update)

@router.get("/queue/stats", response_model=Dict)
async def get_queue_stats(
    service: SignalService = Depends(get_signal_service)
) -> Dict:
    """Get current signal queue statistics.
    
    Args:
        service: Signal service
        
    Returns:
        Dictionary containing queue statistics
    """
    return await service.get_queue_stats() 