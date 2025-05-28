"""Telegram service for managing Telegram operations.

This module provides:
- Telegram client management
- Signal parsing and validation
- Signal queue management
"""

from typing import Optional, Dict
import os
from pathlib import Path

import structlog
from fastapi import HTTPException

from src.telegram.telegram_client import SignalMonitor
from src.telegram.signal_parser import SignalParser
from src.telegram.signal_validator import SignalValidator
from src.telegram.signal_queue import SignalQueue, SignalPriority
from src.telegram.signal_persistence import SignalPersistence
from src.db.repositories.signal import SignalRepository

logger = structlog.get_logger(__name__)

class TelegramService:
    """Service for managing Telegram operations."""
    
    def __init__(
        self,
        signal_monitor: SignalMonitor,
        signal_parser: SignalParser,
        signal_validator: SignalValidator,
        signal_queue: SignalQueue,
        signal_persistence: SignalPersistence
    ):
        """Initialize Telegram service.
        
        Args:
            signal_monitor: SignalMonitor instance
            signal_parser: SignalParser instance
            signal_validator: SignalValidator instance
            signal_queue: SignalQueue instance
            signal_persistence: SignalPersistence instance
        """
        self.monitor = signal_monitor
        self.parser = signal_parser
        self.validator = signal_validator
        self.queue = signal_queue
        self.persistence = signal_persistence
        
    @classmethod
    async def create(
        cls,
        db_session,
        config: Optional[Dict] = None,
        signal_queue: Optional[SignalQueue] = None
    ) -> "TelegramService":
        """Create Telegram service instance.
        
        Args:
            db_session: Database session
            config: Optional configuration dictionary
            signal_queue: Optional signal queue instance
            
        Returns:
            TelegramService instance
            
        Raises:
            HTTPException: If service creation fails
        """
        try:
            # Load configuration
            api_id = os.getenv("TELEGRAM_API_ID")
            api_hash = os.getenv("TELEGRAM_API_HASH")
            channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
            phone = os.getenv("TELEGRAM_PHONE")
            openai_key = os.getenv("OPENAI_API_KEY")
            
            if not all([api_id, api_hash, channel_id, openai_key]):
                raise ValueError("Missing required credentials (Telegram or OpenAI)")
                
            # Set up session path
            session_dir = Path.home() / ".goldmirror"
            session_dir.mkdir(parents=True, exist_ok=True)
            session_path = str(session_dir / "telegram.session")
            
            # Create repositories and components
            signal_repository = SignalRepository(db_session)
            
            # Initialize components with dependencies
            signal_persistence = SignalPersistence(signal_repository)
            signal_parser = SignalParser(api_key=openai_key)
            signal_validator = SignalValidator(signal_repository)
            
            # Use provided signal queue or create new one
            if signal_queue is None:
                signal_queue = SignalQueue()
            
            # Create message handler
            async def message_handler(message_data: Dict):
                try:
                    # Parse signal
                    signal = await signal_parser.parse(
                        message=message_data["text"],
                        message_id=message_data["message_id"],
                        chat_id=message_data["chat_id"],
                        channel_name=message_data.get("channel_name", "")
                    )
                    
                    if not signal:
                        logger.debug(
                            "no_signal_found",
                            message_id=message_data["message_id"]
                        )
                        return
                        
                    # Persist signal to database
                    db_signal = await signal_persistence.persist_signal(
                        trading_signal=signal,
                        message_id=message_data["message_id"],
                        chat_id=message_data["chat_id"],
                        channel_name=message_data.get("channel_name", "")
                    )
                    
                    if not db_signal:
                        logger.error(
                            "signal_persistence_failed",
                            message_id=message_data["message_id"]
                        )
                        return
                        
                    # Queue signal ID for processing
                    success = await signal_queue.enqueue(
                        signal_id=db_signal.id,  # Queue the database ID
                        priority=SignalPriority.NORMAL
                    )
                    
                    if success:
                        logger.info(
                            "signal_queued",
                            signal_id=db_signal.id,
                            symbol=signal.symbol,
                            direction=signal.direction
                        )
                    else:
                        logger.error(
                            "signal_queue_failed",
                            signal_id=db_signal.id,
                            reason="queue_full"
                        )
                        
                except Exception as e:
                    logger.error(
                        "message_handling_failed",
                        error=str(e),
                        message_id=message_data.get("message_id")
                    )
            
            # Create signal monitor
            signal_monitor = SignalMonitor(
                api_id=api_id,
                api_hash=api_hash,
                channel_id=channel_id,
                session_path=session_path,
                phone=phone,
                message_callback=message_handler
            )
            
            # Connect to Telegram
            await signal_monitor.connect()
            logger.info("telegram_monitor_connected")
            
            return cls(
                signal_monitor=signal_monitor,
                signal_parser=signal_parser,
                signal_validator=signal_validator,
                signal_queue=signal_queue,
                signal_persistence=signal_persistence
            )
            
        except Exception as e:
            logger.error("telegram_service_creation_failed", error=str(e))
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create Telegram service: {str(e)}"
            )
            
    async def stop(self):
        """Stop Telegram service."""
        try:
            await self.monitor.disconnect()
            logger.info("telegram_monitor_stopped")
        except Exception as e:
            logger.error("telegram_stop_error", error=str(e))
            
    async def get_queue_stats(self) -> Dict:
        """Get signal queue statistics.
        
        Returns:
            Dict containing queue statistics
        """
        return self.queue.get_queue_stats()
        
    async def get_monitor_status(self) -> Dict:
        """Get monitor status.
        
        Returns:
            Dict containing monitor status
        """
        return {
            "is_connected": self.monitor.is_connected(),
            "last_message_time": self.monitor.last_message_time
        } 