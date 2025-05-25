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

from src.db.connection import DatabaseConnection, init_db
from src.db.models.base import Base
from src.db.models.signal import Signal
from src.db.models.trade import Trade
from src.db.models.statistics import DailyStatistics

logger = logging.getLogger(__name__)

async def create_tables(engine: AsyncEngine) -> None:
    """Create database tables.
    
    Args:
        engine: SQLAlchemy async engine
    """
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)
        
        # Create indexes
        await conn.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_signals_channel_date 
            ON signals (channel_name, created_at);
            
            CREATE INDEX IF NOT EXISTS idx_trades_symbol_date 
            ON trades (symbol, created_at);
            
            CREATE INDEX IF NOT EXISTS idx_statistics_date 
            ON daily_statistics (date);
            """)
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
        if not await db.check_connection():
            raise RuntimeError("Failed to connect to database")
            
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
        logger.error(
            "database_initialization_failed",
            error=str(e)
        )
        await db.close()
        raise

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