"""FastAPI dependencies for database and service injection.

This module provides:
- Database session dependency
- Repository dependencies
- Service dependencies
"""

from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import DatabaseConnection, get_db as get_db_connection
from src.db.repositories.signal import SignalRepository
from src.db.repositories.trade import TradeRepository
from src.db.repositories.statistics import StatisticsRepository
from src.telegram.signal_parser import SignalParser
from src.telegram.signal_queue import SignalQueue
from .services.signal_service import SignalService
from .services.mt5_service import MT5Service

# Database session dependency
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from request state.
    
    Args:
        request: FastAPI request object
        
    Yields:
        AsyncSession: Database session
    """
    if not hasattr(request.app.state, "db_session"):
        raise HTTPException(
            status_code=500,
            detail="Database session factory not initialized"
        )
        
    async with request.app.state.db_session() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()

# Repository dependencies
async def get_signal_repository(
    session: AsyncSession = Depends(get_db)
) -> SignalRepository:
    """Get signal repository.
    
    Args:
        session: Database session
        
    Returns:
        SignalRepository: Signal repository instance
    """
    return SignalRepository(session)

async def get_trade_repository(
    session: AsyncSession = Depends(get_db)
) -> TradeRepository:
    """Get trade repository.
    
    Args:
        session: Database session
        
    Returns:
        TradeRepository: Trade repository instance
    """
    return TradeRepository(session)

async def get_statistics_repository(
    session: AsyncSession = Depends(get_db)
) -> StatisticsRepository:
    """Get statistics repository.
    
    Args:
        session: Database session
        
    Returns:
        StatisticsRepository: Statistics repository instance
    """
    return StatisticsRepository(session)

# Service dependencies
async def get_signal_parser() -> SignalParser:
    """Get signal parser instance.
    
    Returns:
        SignalParser: Signal parser instance
    """
    return SignalParser()

async def get_signal_queue() -> SignalQueue:
    """Get signal queue instance.
    
    Returns:
        SignalQueue: Signal queue instance
    """
    return SignalQueue()

async def get_signal_service(
    parser: SignalParser = Depends(get_signal_parser),
    queue: SignalQueue = Depends(get_signal_queue),
    repo: SignalRepository = Depends(get_signal_repository)
) -> SignalService:
    """Get signal service instance.
    
    Args:
        parser: Signal parser instance
        queue: Signal queue instance
        repo: Signal repository instance
        
    Returns:
        SignalService: Signal service instance
    """
    return SignalService(parser, queue, repo)

# MT5 dependencies
async def get_mt5_service(request: Request) -> MT5Service:
    """Get MT5 service instance from request state.
    
    Args:
        request: FastAPI request object
        
    Returns:
        MT5Service: Service instance
        
    Raises:
        HTTPException: If MT5 service not initialized
    """
    if not hasattr(request.app.state, "mt5_service"):
        raise HTTPException(
            status_code=503,
            detail="MT5 service not initialized"
        )
    return request.app.state.mt5_service 