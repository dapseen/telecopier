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
        
        # List all symbols with their details
        logger.info("checking_all_symbols_details")
        all_symbols = connection.mt5.symbols_get()
        if all_symbols:
            for symbol in all_symbols:
                if "BTC" in symbol.name:  # Focus on BTC-related symbols
                    logger.info(
                        "symbol_details",
                        name=symbol.name,
                        description=symbol.description,
                        trade_mode=symbol.trade_mode,
                        trade_contract_size=symbol.trade_contract_size,
                        volume_min=symbol.volume_min,
                        volume_max=symbol.volume_max,
                        is_visible=symbol.visible,
                        is_trade_allowed=symbol.trade_mode == connection.mt5.SYMBOL_TRADE_MODE_FULL
                    )
        
        # Test crypto symbols specifically
        crypto_symbols = ["BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "BCHUSD"]
        logger.info("checking_crypto_symbols")
        for symbol in crypto_symbols:
            is_available = connection.is_symbol_available(symbol)
            if is_available:
                # Get symbol info if available
                symbol_info = connection.mt5.symbol_info(symbol)
                if symbol_info:
                    # Get tick info only if symbol exists
                    tick_info = connection.mt5.symbol_info_tick(symbol)
                    if tick_info:
                        logger.info(
                            "crypto_symbol_info",
                            symbol=symbol,
                            available=is_available,
                            bid=tick_info.bid,
                            ask=tick_info.ask,
                            volume_min=symbol_info.volume_min,
                            volume_max=symbol_info.volume_max,
                            trade_mode=symbol_info.trade_mode,
                            trade_contract_size=symbol_info.trade_contract_size
                        )
                    else:
                        logger.warning(
                            "crypto_symbol_no_tick_info",
                            symbol=symbol,
                            available=is_available,
                            reason="Symbol exists but no tick data available"
                        )
                else:
                    logger.warning(
                        "crypto_symbol_no_info",
                        symbol=symbol,
                        available=is_available,
                        reason="Symbol exists but no detailed info available"
                    )
            else:
                # Check if symbol exists in MT5 but is not available for trading
                symbol_info = connection.mt5.symbol_info(symbol)
                if symbol_info:
                    logger.warning(
                        "crypto_symbol_not_available",
                        symbol=symbol,
                        available=is_available,
                        reason="Symbol exists but not available for trading",
                        trade_mode=symbol_info.trade_mode,
                        trade_allowed=symbol_info.trade_mode == connection.mt5.SYMBOL_TRADE_MODE_FULL
                    )
                else:
                    logger.warning(
                        "crypto_symbol_not_found",
                        symbol=symbol,
                        available=is_available,
                        reason="Symbol not found in MT5 terminal"
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