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
        table.add_row("Stop Loss", f"{signal.stop_loss} ({signal.stop_loss_pips} pips)")
        table.add_row("Confidence", f"{signal.confidence_score:.2f}")
        table.add_row("Message Time", message_date.strftime("%Y-%m-%d %H:%M:%S"))
        
        # Add take profit levels
        tp_table = Table(show_header=False, box=None)
        for tp in signal.take_profits:
            tp_info = f"TP{tp.level}: {tp.price}"
            if tp.pips:
                tp_info += f" ({tp.pips} pips)"
            tp_table.add_row(tp_info)
            
        table.add_row("Take Profits", tp_table)
        
        # Add additional notes if any
        if signal.additional_notes:
            table.add_row("Notes", signal.additional_notes)
            
        # Display the table
        self.console.print(table)
        self.console.print()  # Add spacing

async def message_handler(message_data: Dict[str, Any], tester: SignalParserTester) -> None:
    """Handle incoming messages from Telegram and parse them for trading signals.
    
    Args:
        message_data: The message data from Telegram
        tester: The SignalParserTester instance
    """
    tester.messages_analyzed += 1
    
    # Log the received message
    logger.info(
        "received_message",
        message_id=message_data["message_id"],
        text=message_data["text"],
        date=message_data["date"],
    )
    
    # Try to parse the message as a trading signal
    signal = tester.parser.parse(message_data["text"])
    if signal:
        tester.signals_found += 1
        tester.display_signal(signal, message_data["date"])
        
        # Log the parsed signal
        logger.info(
            "parsed_signal",
            message_id=message_data["message_id"],
            symbol=signal.symbol,
            direction=signal.direction,
            confidence=signal.confidence_score,
        )

async def main() -> None:
    """Main function to test the signal parser with live messages."""
    # Load environment variables
    load_dotenv()
    
    # Get credentials from environment
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
    phone = os.getenv("TELEGRAM_PHONE")  # Add phone number
    
    # Validate required credentials
    if not all([api_id, api_hash, channel_id, phone]):  # Add phone to validation
        logger.error("missing_credentials")
        print("\nError: Missing required Telegram credentials!")
        print("Please set the following environment variables:")
        print("  - TELEGRAM_API_ID")
        print("  - TELEGRAM_API_HASH")
        print("  - TELEGRAM_CHANNEL_ID")
        print("  - TELEGRAM_PHONE")  # Add phone to message
        print("\nYou can get these from https://my.telegram.org/apps")
        return
    
    # Initialize the signal parser tester
    tester = SignalParserTester()
    
    # Create message handler with the tester instance
    async def handler(message_data: Dict[str, Any]) -> None:
        await message_handler(message_data, tester)
    
    # Create and start the client
    monitor = SignalMonitor(
        api_id=api_id,
        api_hash=api_hash,
        channel_id=channel_id,
        message_callback=handler,
        phone=phone,  # Add phone number
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
        # Print summary before disconnecting
        if tester.messages_analyzed > 0:
            success_rate = (tester.signals_found / tester.messages_analyzed) * 100
            print("\n=== Analysis Summary ===")
            print(f"Messages analyzed: {tester.messages_analyzed}")
            print(f"Signals found: {tester.signals_found}")
            print(f"Success rate: {success_rate:.1f}%")
            print("======================\n")
        
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