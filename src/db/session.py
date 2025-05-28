"""Database session management.

This module provides:
- Session factory for database connections
- Dependency injection for FastAPI endpoints
- Session lifecycle management
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy.orm import sessionmaker

from .connection import get_database_url

# Create async engine
engine = create_async_engine(
    get_database_url(),
    pool_pre_ping=True,
    echo=False
)

# Create session factory
AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session.
    
    This is a FastAPI dependency that provides a database session
    for route handlers. The session is automatically closed when
    the request is complete.
    
    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        finally:
            await session.close()

@asynccontextmanager
async def get_session_context():
    """Context manager for database sessions.
    
    This is used for background tasks and other non-request contexts
    where FastAPI dependencies are not available.
    
    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        finally:
            await session.close()

async def get_session_local() -> AsyncSession:
    """Get a new database session.
    
    This is used when you need direct control over the session
    lifecycle. Remember to close the session when done.
    
    Returns:
        AsyncSession: Database session
    """
    return AsyncSessionFactory() 