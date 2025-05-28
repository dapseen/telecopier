"""Signal parser for Telegram trading messages using GPT-3.5.

This module provides functionality to parse trading signals from Telegram messages
using OpenAI's GPT-3.5 model. It transforms natural language messages into 
structured trading signal data.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import json
import os

import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from src.common.types import SignalDirection, SignalType

logger = structlog.get_logger(__name__)

class TakeProfit(BaseModel):
    """Represents a take profit level."""
    level: int = Field(..., description="Take profit level number (1-4)")
    price: float = Field(..., description="Take profit price target")
    pips: Optional[int] = Field(None, description="Distance in pips from entry")

class TradingSignal(BaseModel):
    """Model for parsed trading signals."""
    message_id: int = Field(0, description="Telegram message ID")
    chat_id: int = Field(0, description="Telegram chat ID")
    channel_name: str = Field("default", description="Name of the Telegram channel")
    signal_type: SignalType = Field(SignalType.MARKET, description="Type of trading signal")
    symbol: str = Field(..., description="Trading symbol (e.g., XAUUSD)")
    direction: SignalDirection = Field(..., description="Trade direction")
    entry_price: float = Field(..., description="Entry price for the trade")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    stop_loss_pips: Optional[int] = Field(None, description="Stop loss distance in pips")
    take_profits: List[TakeProfit] = Field(default_factory=list, description="Take profit levels")
    risk_reward: Optional[float] = Field(None, description="Risk to reward ratio")
    lot_size: Optional[float] = Field(None, description="Position size in lots")
    confidence_score: Optional[float] = Field(None, description="Signal confidence score")
    additional_notes: Optional[str] = Field(None, description="Additional trading notes")
    raw_message: str = Field(..., description="Raw Telegram message text")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc), description="Signal creation timestamp")

def calculate_pips(symbol: str, price1: float, price2: float) -> int:
    """Calculate the number of pips between two prices.
    
    Args:
        symbol: The trading symbol (e.g., EURUSD, USDJPY, XAUUSD)
        price1: First price
        price2: Second price
        
    Returns:
        int: Number of pips between the prices
    """
    # Get the absolute price difference
    price_diff = abs(price1 - price2)
    
    # Handle different instrument types
    if symbol.endswith('JPY'):  # JPY pairs
        return int(price_diff * 100)  # 1 pip = 0.01
    elif symbol in {'XAUUSD', 'XAGUSD'}:  # Gold and Silver
        return int(price_diff * 10)  # 1 pip = 0.1
    elif any(symbol.startswith(i) for i in {'US30', 'US500', 'NAS100'}):  # Indices
        return int(price_diff)  # 1 pip = 1.0
    else:  # Standard forex pairs
        return int(price_diff * 10000)  # 1 pip = 0.0001

class SignalParser:
    """Parser for converting Telegram messages into structured trading signals using GPT-3.5.
    
    This class handles the parsing of trading signals from Telegram messages using
    OpenAI's GPT-3.5 model with robust error handling and validation.
    """
    
    def __init__(
        self,
        api_key: str,
        valid_symbols: Optional[set[str]] = None,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
        max_tokens: int = 300
    ):
        """Initialize the signal parser.
        
        Args:
            api_key: OpenAI API key
            valid_symbols: Set of valid trading symbols. If None, will be populated from config.
            model: OpenAI model to use
            temperature: Model temperature (0.0 to 2.0)
            max_tokens: Maximum tokens for completion
        """
        if not api_key:
            raise ValueError("OpenAI API key is required")
            
        self.api_key = api_key
        self.valid_symbols = valid_symbols or self._load_symbols_from_config()
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.openai_client = AsyncOpenAI(api_key=api_key)
        
        # System prompt for GPT-3.5
        self.system_prompt = """You are a trading signal parser. Your task is to extract structured trading information from Telegram messages.
Extract the following information if present:
- Trading symbol (e.g., XAUUSD, EURUSD)
- Trade direction (Buy/Sell)
- Entry price
- Stop loss price
- Take profit targets (up to 4 levels)
- Additional notes or conditions

Format the output as a JSON object with the following structure:
{
    "symbol": str,
    "direction": str,
    "entry": float,
    "sl": float,
    "take_profits": {
        "TP1": float,
        "TP2": float,
        "TP3": float,
        "TP4": float
    },
    "notes": str
}

Only include fields that are present in the message. Handle variations in message format, typos, and natural language.
If a message is not a trading signal or critical information is missing, return null."""

    def _load_symbols_from_config(self) -> set[str]:
        """Load valid trading symbols from configuration.
        
        Returns:
            Set of valid trading symbols
        """
        # TODO: Implement loading symbols from config
        return {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY"}  # Default symbols

    async def parse(self, message: str, message_id: int = 0, chat_id: int = 0, channel_name: str = "default") -> Optional[TradingSignal]:
        """Parse a trading signal message into a structured format using GPT-3.5.
        
        This method uses GPT-3.5 to extract trading signal components from the
        message text. It includes validation and error handling.
        
        Args:
            message: The raw message text from Telegram
            message_id: The Telegram message ID
            chat_id: The Telegram chat ID
            channel_name: The name of the Telegram channel
            
        Returns:
            TradingSignal object if parsing is successful, None otherwise
            
        Raises:
            ValueError: If the message format is invalid or missing required components
        """
        try:
            # Call GPT-3.5 to parse the message
            completion = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": message}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            # Get the parsed result
            parsed_text = completion.choices[0].message.content
            
            # Handle non-signal messages
            if parsed_text.lower().strip() in ['null', 'none', '']:
                logger.info("Message not recognized as a trading signal")
                return None
                
            try:
                # Parse JSON response
                parsed_data = json.loads(parsed_text)
                
                # Validate symbol
                symbol = parsed_data.get('symbol', '').upper()
                if not symbol or symbol not in self.valid_symbols:
                    logger.warning(f"Invalid or missing symbol: {symbol}")
                    return None
                    
                # Convert direction to enum
                direction_str = parsed_data.get('direction', '').upper()
                try:
                    direction = SignalDirection[direction_str]
                except KeyError:
                    logger.warning(f"Invalid direction: {direction_str}")
                    return None
                    
                # Extract take profits
                take_profits = []
                tp_data = parsed_data.get('take_profits', {})
                for level in range(1, 5):
                    tp_key = f"TP{level}"
                    if tp_key in tp_data:
                        take_profits.append(
                            TakeProfit(
                                level=level,
                                price=float(tp_data[tp_key]),
                                pips=None  # Calculate pips if needed
                            )
                        )
                
                # Calculate stop loss pips if entry and sl present
                stop_loss_pips = None
                entry_price = float(parsed_data.get('entry', 0))
                stop_loss = parsed_data.get('sl')
                if entry_price and stop_loss:
                    stop_loss = float(stop_loss)
                    stop_loss_pips = calculate_pips(symbol, entry_price, stop_loss)
                
                # Calculate take profit pips
                for tp in take_profits:
                    tp.pips = calculate_pips(symbol, entry_price, tp.price)

                # Create trading signal object
                signal = TradingSignal(
                    message_id=message_id,
                    chat_id=chat_id,
                    channel_name=channel_name,
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    stop_loss_pips=stop_loss_pips,
                    take_profits=take_profits,
                    additional_notes=parsed_data.get('notes'),
                    raw_message=message,
                    confidence_score=0.95  # High confidence for GPT-parsed signals
                )

                
                logger.info(
                    "Successfully parsed signal",
                    symbol=signal.symbol,
                    direction=signal.direction,
                )
                return signal
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse GPT response: {str(e)}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling GPT-3.5 API: {str(e)}")
            return None 