"""Database initialization script.

This module provides functions for:
- Creating database tables
- Initializing database connection
- Running database migrations
- Seeding initial data
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
import structlog

from src.db.connection import DatabaseConnection, init_db
from src.db.models.base import Base
from src.db.models.signal import Signal
from src.db.models.trade import Trade
from src.db.models.statistics import DailyStatistics

logger = structlog.get_logger(__name__)

async def create_tables(engine: AsyncEngine) -> None:
    """Create database tables.
    
    Args:
        engine: SQLAlchemy async engine
    """
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)
        
        # Create indexes one by one
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_signals_channel_date ON signals (channel_name, created_at)")
        )
        
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_trades_symbol_date ON trades (symbol, created_at)")
        )
        
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_statistics_date ON daily_statistics (trading_date)")
        )
        
    logger.info("database_tables_created")

async def drop_tables(engine: AsyncEngine) -> None:
    """Drop all database tables.
    
    Args:
        engine: SQLAlchemy async engine
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("database_tables_dropped")

async def init_database(
    database_url: Optional[str] = None,
    drop_existing: bool = False
) -> DatabaseConnection:
    """Initialize database connection and create tables.
    
    Args:
        database_url: Database connection URL
        drop_existing: Whether to drop existing tables
        
    Returns:
        DatabaseConnection: Initialized database connection
    """
    # Initialize database connection
    db = init_db(database_url=database_url)
    
    try:
        # Test connection
        async with db.session() as session:
            # Test if we can execute queries
            await session.execute(text("SELECT 1"))
            await session.commit()
            
            # Test if we have the necessary permissions
            await session.execute(text("CREATE TABLE IF NOT EXISTS _test_table (id serial PRIMARY KEY)"))
            await session.execute(text("DROP TABLE _test_table"))
            await session.commit()
            
        # Drop tables if requested
        if drop_existing:
            await drop_tables(db.engine)
            
        # Create tables
        await create_tables(db.engine)
        
        logger.info(
            "database_initialized",
            database_url=db.database_url,
            drop_existing=drop_existing
        )
        
        return db
        
    except Exception as e:
        error_msg = str(e)
        if "password authentication failed" in error_msg.lower():
            logger.error("database_auth_failed", exc_info=True)
            raise RuntimeError("Database authentication failed. Please check your credentials.")
        elif "connection refused" in error_msg.lower():
            logger.error("database_connection_refused", exc_info=True)
            raise RuntimeError("Database connection refused. Please check if PostgreSQL is running.")
        elif "permission denied" in error_msg.lower():
            logger.error("database_permission_denied", exc_info=True)
            raise RuntimeError("Database permission denied. Please check user permissions.")
        else:
            logger.error("database_initialization_failed", exc_info=True)
            raise RuntimeError(f"Failed to initialize database: {error_msg}")

async def reset_database(
    database_url: Optional[str] = None
) -> DatabaseConnection:
    """Reset database by dropping and recreating all tables.
    
    Args:
        database_url: Database connection URL
        
    Returns:
        DatabaseConnection: Initialized database connection
    """
    return await init_database(
        database_url=database_url,
        drop_existing=True
    )

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Initialize database
    asyncio.run(init_database()) 