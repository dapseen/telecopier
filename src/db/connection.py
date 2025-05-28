"""Database connection management for GoldMirror.

This module provides database connection management including:
- Connection pooling
- Session management
- Transaction handling
- Connection monitoring
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine
)
from sqlalchemy.pool import NullPool  # Use NullPool for better async handling
from sqlalchemy import text

import structlog

# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger(__name__)

@lru_cache()
def get_database_url() -> str:
    """Get the database connection URL.
    
    Returns:
        str: Database connection URL from environment or default
    """
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/goldmirror"
    )

class DatabaseConnection:
    """Manages database connections and sessions.
    
    This class handles:
    - Database connection pooling
    - Session management
    - Transaction handling
    - Connection monitoring
    """
    
    def __init__(
        self,
        database_url: Optional[str] = None,
        echo: bool = False
    ):
        """Initialize database connection.
        
        Args:
            database_url: Database connection URL. If not provided, will use DATABASE_URL env var
            echo: Whether to echo SQL statements
        """
        self.database_url = database_url or get_database_url()
        
        # Create async engine without connection pooling (better for async)
        self.engine: AsyncEngine = create_async_engine(
            self.database_url,
            poolclass=NullPool,  # Don't use connection pooling with async
            echo=echo,
        )
        
        # Create async session factory
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )
        
        logger.info(
            "database_connection_initialized",
            database_url=self.database_url,
            echo=echo
        )
        
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session.
        
        Yields:
            AsyncSession: Database session
            
        Example:
            async with db.session() as session:
                result = await session.execute(query)
        """
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(
                    "database_session_error",
                    exc_info=True
                )
                raise
            finally:
                await session.close()
                
    async def check_connection(self) -> bool:
        """Check if database connection is working.
        
        Returns:
            bool: True if connection is working, False otherwise
        """
        try:
            async with self.session() as session:
                await session.execute(text("SELECT 1"))
                await session.commit()
            return True
        except Exception as e:
            logger.error(
                "database_connection_check_failed",
                exc_info=True
            )
            return False
            
    async def close(self) -> None:
        """Close all database connections."""
        await self.engine.dispose()
        logger.info("database_connections_closed")

# Global database connection instance
_db: Optional[DatabaseConnection] = None
_engine: Optional[AsyncEngine] = None
_async_session: Optional[async_sessionmaker[AsyncSession]] = None

def get_engine() -> AsyncEngine:
    """Get the global database engine instance.
    
    Returns:
        AsyncEngine: Database engine instance
        
    Raises:
        RuntimeError: If database connection is not initialized
    """
    global _engine
    if _engine is None:
        raise RuntimeError("Database engine not initialized")
    return _engine

def get_async_session() -> async_sessionmaker[AsyncSession]:
    """Get the global async session factory.
    
    Returns:
        async_sessionmaker[AsyncSession]: Async session factory
        
    Raises:
        RuntimeError: If database connection is not initialized
    """
    global _async_session
    if _async_session is None:
        raise RuntimeError("Database session factory not initialized")
    return _async_session

def init_db(
    database_url: Optional[str] = None,
    echo: bool = False
) -> DatabaseConnection:
    """Initialize the global database connection.
    
    Args:
        database_url: Database connection URL
        echo: Whether to echo SQL statements
        
    Returns:
        DatabaseConnection: Initialized database connection
        
    Raises:
        RuntimeError: If database connection is already initialized
    """
    global _db, _engine, _async_session
    if _db is not None:
        raise RuntimeError("Database connection already initialized")
        
    _db = DatabaseConnection(
        database_url=database_url,
        echo=echo
    )
    
    # Set global engine and session factory
    _engine = _db.engine
    _async_session = _db.async_session
    
    return _db

def get_db() -> DatabaseConnection:
    """Get the global database connection instance.
    
    Returns:
        DatabaseConnection: Database connection instance
        
    Raises:
        RuntimeError: If database connection is not initialized
    """
    if _db is None:
        raise RuntimeError("Database connection not initialized")
    return _db 