#!/usr/bin/env python3
"""
GoldMirror: Telegram to MT5 Signal Automation
Main application entry point.
"""

import asyncio
import os
import sys
from typing import Dict, Any

import structlog
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.telegram import SignalMonitor, SignalParser, SignalValidator, SignalQueue, SignalPriority
from src.api.config import AppConfig
from src.api.services.signal_service import SignalService
from src.api.services.mt5_service import MT5Service
from src.db.repositories.signal import SignalRepository
from src.db.init_db import init_database
from src.db.connection import get_db, get_async_session

logger = structlog.get_logger(__name__)

class GoldMirror:
    """Main application class for GoldMirror trading automation.
    
    This class orchestrates all components of the trading system:
    - Configuration management
    - Telegram signal monitoring
    - MT5 trade execution
    - Risk management
    - Logging and analytics
    """

    def __init__(self, config_path: str = None):
        """Initialize GoldMirror application.

        Args:
            config_path: Optional path to config file. If not provided, will use default.
        """
        # Load configuration
        from src.api.app import load_config
        self.config = load_config()
        self._setup_logging()

        # Initialize components
        self.telegram_client: SignalMonitor = None
        self.signal_service: SignalService = None
        self.mt5_service: MT5Service = None
        self.session_factory: async_sessionmaker[AsyncSession] = None
        
    async def start(self) -> None:
        """Start the GoldMirror trading system."""
        try:
            # Initialize database
            db = await init_database()
            self.session_factory = db.async_session
            logger.info("database_initialized")
            
            # Initialize MT5 service
            self.mt5_service = await MT5Service.create()
            logger.info("mt5_service_initialized")
            
            # Create session for signal repository
            session = self.session_factory()
            
            # Initialize signal service with session
            self.signal_service = SignalService(
                signal_parser=SignalParser(),
                signal_queue=SignalQueue(),
                signal_repository=SignalRepository(session=session)
            )
            logger.info("signal_service_initialized")
            
            # Initialize Telegram client
            self._setup_telegram()
            
            # Start the main event loop
            await self._run_event_loop()
            
        except Exception as e:
            logger.error("startup_failed", error=str(e))
            raise
            
    def _setup_telegram(self) -> None:
        """Set up Telegram client and signal processing."""
        logger.info("setting_up_telegram")
        
        # Initialize Telegram client
        self.telegram_client = SignalMonitor(
            api_id=int(os.getenv("TELEGRAM_API_ID", "0")),
            api_hash=os.getenv("TELEGRAM_API_HASH", ""),
            channel_id=os.getenv("TELEGRAM_CHANNEL_ID", ""),
            message_callback=self._handle_telegram_message
        )
        
    async def _handle_telegram_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming Telegram message."""
        try:
            # Create new session for each message
            async with self.session_factory() as session:
                # Process message through signal service with new session
                signal_repository = SignalRepository(session=session)
                signal_service = SignalService(
                    signal_parser=self.signal_service.parser,
                    signal_queue=self.signal_service.queue,
                    signal_repository=signal_repository
                )
                
                signal_response = await signal_service.process_telegram_message(
                    message_text=message.get("text", ""),
                    chat_id=message.get("chat_id"),
                    message_id=message.get("message_id"),
                    channel_name=message.get("channel_name", "")
                )
                
                if not signal_response:
                    logger.debug(
                        "no_signal_processed",
                        message_id=message.get("message_id")
                    )
                    return
                    
                logger.info(
                    "signal_processed",
                    signal_id=signal_response.id,
                    symbol=signal_response.symbol,
                    direction=signal_response.direction
                )
                
        except Exception as e:
            logger.error(
                "message_handling_failed",
                error=str(e),
                message_id=message.get("message_id")
            )
            
    async def _run_event_loop(self) -> None:
        """Run the main event loop."""
        try:
            # Start Telegram client
            if self.telegram_client:
                await self.telegram_client.connect()
                logger.info("telegram_client_connected")
                
            # Keep the event loop running
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("shutting_down")
            if self.telegram_client:
                await self.telegram_client.disconnect()
                logger.info("telegram_client_disconnected")
            if self.mt5_service:
                await self.mt5_service.connection.disconnect()
                logger.info("mt5_disconnected")
        except Exception as e:
            logger.error("event_loop_error", error=str(e))
            raise

    def _setup_logging(self) -> None:
        """Configure logging based on config settings."""
        log_config = self.config.logging
        
        # Configure structured logging
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.stdlib.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        logger.info("logging_configured", level=log_config.level)

    async def clear_cache(self) -> None:
        """Clear all system caches."""
        logger.info("clearing_system_caches")
        
        # Clear signal service cache
        if self.signal_service:
            await self.signal_service.clear_cache()
            logger.info("signal_service_cache_cleared")
            
        # Clear MT5 service cache
        if self.mt5_service:
            await self.mt5_service.connection.clear_cache()
            logger.info("mt5_service_cache_cleared")
            
        logger.info("all_caches_cleared")

async def main() -> None:
    """Application entry point."""
    # Load environment variables
    load_dotenv()
    
    # Create and start application
    app = GoldMirror()
    
    # Add command line argument handling
    if len(sys.argv) > 1 and sys.argv[1] == "--clear-cache":
        await app.clear_cache()
        logger.info("caches_cleared_exiting")
        return
        
    await app.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
    except Exception as e:
        logger.error("fatal_error", error=str(e))
        raise 