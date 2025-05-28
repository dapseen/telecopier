#!/usr/bin/env python3
"""

Run this script to test the connection and message reception.
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, Any

import structlog
from dotenv import load_dotenv
from src.telegram.telegram_client import SignalMonitor

# Configure logging
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

logger = structlog.get_logger(__name__)

async def message_handler(message_data: Dict[str, Any]) -> None:
    """Handle incoming messages from Telegram."""
    logger.info(
        "received_message",
        message_id=message_data["message_id"],
        text=message_data["text"],
        date=message_data["date"],
    )
    
    print("\n=== New Message ===")
    print(f"Message ID: {message_data['message_id']}")
    print(f"Text: {message_data['text']}")
    print(f"Date: {message_data['date']}")
    if message_data.get("edit_date"):
        print(f"Edited: {message_data['edit_date']}")
    print("==================\n")

async def main() -> None:
    """Main function to test the Telegram client."""
    # Load environment variables
    load_dotenv()
    
    # Get credentials from environment
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
    
    # Validate required credentials
    if not all([api_id, api_hash, channel_id]):
        logger.error("missing_credentials")
        print("\nError: Missing required Telegram credentials!")
        print("Please set the following environment variables:")
        print("  - TELEGRAM_API_ID")
        print("  - TELEGRAM_API_HASH")
        print("  - TELEGRAM_CHANNEL_ID")
        print("\nYou can get these from https://my.telegram.org/apps")
        return
    
    # Create and start the client
    monitor = SignalMonitor(
        api_id=api_id,
        api_hash=api_hash,
        channel_id=channel_id,
        message_callback=message_handler,
    )
    
    try:
        print("\nConnecting to Telegram...")
        await monitor.connect()
        print("Connected successfully!")
        print(f"Monitoring channel: {channel_id}")
        print("\nPress Ctrl+C to stop\n")
        
        # Keep the script running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        logger.error("error", error=str(e))
        raise
    finally:
        await monitor.disconnect()
        print("Disconnected")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"\nError: {str(e)}")
        raise