"""Script to test the signal parser with live messages from Telegram channel."""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Union

import structlog
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..telegram_client.client import SignalMonitor
from .signal_parser import SignalParser, TradingSignal

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

class SignalParserTester:
    """Class to test signal parser with live Telegram messages."""
    
    def __init__(self):
        """Initialize the signal parser tester."""
        self.parser = SignalParser()
        self.console = Console()
        self.signals_found = 0
        self.messages_analyzed = 0
        
    def display_signal(self, signal: TradingSignal, message_date: Union[str, datetime]) -> None:
        """Display a parsed signal in a rich format.
        
        Args:
            signal: The parsed trading signal
            message_date: Original message timestamp (ISO format string or datetime)
        """
        # Parse message date if it's a string
        if isinstance(message_date, str):
            try:
                message_date = datetime.fromisoformat(message_date.replace('Z', '+00:00'))
            except ValueError as e:
                logger.error(
                    "date_parse_error",
                    date=message_date,
                    error=str(e),
                )
                message_date = datetime.now()  # Fallback to current time
        
        # Create a table for the signal details
        table = Table(title=f"Signal for {signal.symbol}")
        table.add_column("Component", style="cyan")
        table.add_column("Value", style="green")
        
        # Add basic signal information
        table.add_row("Direction", signal.direction.upper())
        table.add_row("Entry Price", str(signal.entry_price))
        if signal.stop_loss:
            table.add_row("Stop Loss", f"{signal.stop_loss} ({signal.stop_loss_pips} pips)")
        table.add_row("Confidence", f"{signal.confidence_score:.2f}")
        table.add_row("Message Time", message_date.strftime("%Y-%m-%d %H:%M:%S"))
        
        # Add take profit levels
        if signal.take_profits:
            tp_table = Table(show_header=False, box=None)
            for tp in signal.take_profits:
                tp_table.add_row(f"TP{tp.level}", str(tp.price))
            table.add_row("Take Profits", tp_table)
        
        # Add notes if present
        if signal.additional_notes:
            table.add_row("Notes", signal.additional_notes)
            
        # Display the table
        self.console.print(table)
        self.console.print()

    async def process_message(self, message_data: Dict[str, Any]) -> None:
        """Process a message by parsing it and displaying the result if it's a signal.
        
        Args:
            message_data: The message data from Telegram
        """
        try:
            # Try to parse the message as a trading signal
            signal = await self.parser.parse(
                message=message_data["text"],
                message_id=message_data["message_id"],
                chat_id=message_data["chat_id"],
                channel_name=message_data["channel_name"]
            )
            
            if signal:
                self.signals_found += 1
                self.display_signal(signal, message_data["date"])
                
                # Log the parsed signal
                logger.info(
                    "parsed_signal",
                    message_id=message_data["message_id"],
                    symbol=signal.symbol,
                    direction=signal.direction,
                    confidence=signal.confidence_score,
                )
        except Exception as e:
            logger.error(
                "message_handling_failed",
                error=str(e),
                message_id=message_data.get("message_id", "unknown"),
            )

    async def handle_message(self, message_data: Dict[str, Any]) -> None:
        """Handle incoming messages from Telegram.
        
        This is the callback that will be passed to the SignalMonitor.
        It increments the message counter and processes the message.
        
        Args:
            message_data: The message data from Telegram
        """
        self.messages_analyzed += 1
        
        # Log the received message
        logger.info(
            "received_message",
            message_id=message_data.get("message_id", "unknown"),
            text=message_data.get("text", ""),
            date=message_data.get("date"),
        )
        
        # Process the message in a new task to prevent blocking
        await self.process_message(message_data)

async def main() -> None:
    """Main function to test the signal parser with live messages."""
    # Load environment variables
    load_dotenv()
    
    # Get credentials from environment
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
    phone = os.getenv("TELEGRAM_PHONE")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    # Validate required credentials
    if not all([api_id, api_hash, channel_id, phone, openai_key]):
        logger.error("missing_credentials")
        print("\nError: Missing required credentials!")
        print("Please set the following environment variables:")
        print("  - TELEGRAM_API_ID")
        print("  - TELEGRAM_API_HASH")
        print("  - TELEGRAM_CHANNEL_ID")
        print("  - TELEGRAM_PHONE")
        print("  - OPENAI_API_KEY")
        print("\nYou can get Telegram credentials from https://my.telegram.org/apps")
        print("Get your OpenAI API key from https://platform.openai.com/api-keys")
        return
    
    # Initialize the signal parser tester
    tester = SignalParserTester()
    
    # Create and start the client
    monitor = SignalMonitor(
        api_id=api_id,
        api_hash=api_hash,
        channel_id=channel_id,
        message_callback=tester.handle_message,
        phone=phone,
    )
    
    try:
        await monitor.start()
        print("\nMonitoring Telegram channel for trading signals...")
        print("Press Ctrl+C to stop\n")
        await monitor.run_forever()
    except KeyboardInterrupt:
        print("\nStopping signal monitor...")
    finally:
        await monitor.stop()
        print(f"\nProcessed {tester.messages_analyzed} messages")
        print(f"Found {tester.signals_found} trading signals")

if __name__ == "__main__":
    asyncio.run(main()) 