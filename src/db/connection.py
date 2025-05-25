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

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine
)
from sqlalchemy.pool import AsyncAdaptedQueuePool

import structlog

# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger(__name__)

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
        pool_size: int = 5,
        max_overflow: int = 10,
        echo: bool = False
    ):
        """Initialize database connection.
        
        Args:
            database_url: Database connection URL. If not provided, will use DATABASE_URL env var
            pool_size: Size of the connection pool
            max_overflow: Maximum number of connections that can be created beyond pool_size
            echo: Whether to echo SQL statements
        """
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/goldmirror"
        )
        
        # Create async engine with connection pooling
        self.engine: AsyncEngine = create_async_engine(
            self.database_url,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            echo=echo,
            pool_pre_ping=True,  # Enable connection health checks
            pool_recycle=3600,   # Recycle connections after 1 hour
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
            pool_size=pool_size,
            max_overflow=max_overflow,
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
                    error=str(e)
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
                await session.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(
                "database_connection_check_failed",
                error=str(e)
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
    pool_size: int = 5,
    max_overflow: int = 10,
    echo: bool = False
) -> DatabaseConnection:
    """Initialize the global database connection.
    
    Args:
        database_url: Database connection URL
        pool_size: Size of the connection pool
        max_overflow: Maximum number of connections that can be created beyond pool_size
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
        pool_size=pool_size,
        max_overflow=max_overflow,
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