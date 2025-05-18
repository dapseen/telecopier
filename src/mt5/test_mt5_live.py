#!/usr/bin/env python3
"""Live test script for MT5 connection and basic functionality."""

import asyncio
import os
from dotenv import load_dotenv
import structlog

from mt5.connection import MT5Connection, MT5Config

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

async def test_mt5_connection():
    """Test MT5 connection and basic functionality."""
    try:
        # Load environment variables
        load_dotenv()
        
        # Create MT5 config from environment
        config = MT5Config.from_environment()
        logger.info("loaded_mt5_config", server=config.server, login=config.login)
        
        # Create connection
        connection = MT5Connection(config)
        
        # Connect to MT5
        logger.info("connecting_to_mt5")
        success = await connection.connect()
        
        if not success:
            logger.error("failed_to_connect")
            return
            
        logger.info("connected_to_mt5")
        
        # Get connection info
        info = connection.get_connection_info()
        logger.info(
            "connection_info",
            connected=info["connected"],
            server=info["server"],
            login=info["login"],
            terminal=info["terminal"]
        )
        
        # Get available symbols
        symbols = connection.available_symbols
        logger.info(
            "available_symbols",
            count=len(symbols),
            symbols=list(symbols)
        )
        
        # Test symbol availability
        test_symbols = ["XAUUSD", "EURUSD", "GBPUSD", "INVALID"]
        for symbol in test_symbols:
            is_available = connection.is_symbol_available(symbol)
            logger.info(
                "symbol_check",
                symbol=symbol,
                available=is_available
            )
            
        # Disconnect
        await connection.disconnect()
        logger.info("disconnected_from_mt5")
        
    except Exception as e:
        logger.error("test_failed", error=str(e))
        raise

if __name__ == "__main__":
    try:
        asyncio.run(test_mt5_connection())
    except KeyboardInterrupt:
        logger.info("test_interrupted")
    except Exception as e:
        logger.error("fatal_error", error=str(e))
        raise 