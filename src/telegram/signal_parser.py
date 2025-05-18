"""Signal parser module for processing Telegram trading signals.

This module implements the SignalParser class which is responsible for parsing
trading signals from Telegram messages into structured data that can be used
by the trading system.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class TakeProfit:
    """Represents a take profit level with price and pip value."""
    level: int
    price: float
    pips: Optional[int] = None

@dataclass
class TradingSignal:
    """Represents a parsed trading signal with all its components."""
    symbol: str
    direction: str  # 'buy' or 'sell'
    entry_price: float
    stop_loss: float
    stop_loss_pips: Optional[int]
    take_profits: List[TakeProfit]
    timestamp: datetime
    raw_message: str
    confidence_score: float
    additional_notes: Optional[str] = None

class SignalParser:
    """Parser for converting Telegram messages into structured trading signals.
    
    This class handles the parsing of trading signals from Telegram messages,
    supporting both structured and unstructured message formats. It includes
    pattern matching, validation, and confidence scoring.
    """
    
    # Common trading symbols
    VALID_SYMBOLS = {
        'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD',
        'USDCAD', 'NZDUSD', 'USDCHF', 'EURGBP', 'EURJPY'
    }
    
    # Direction keywords
    DIRECTION_KEYWORDS = {
        'buy': {'buy', 'long', 'b'},
        'sell': {'sell', 'short', 's'}
    }
    
    def __init__(self):
        """Initialize the signal parser with compiled regex patterns."""
        # Pattern for symbol and direction
        self.symbol_pattern = re.compile(
            r'([A-Z]{6})\s+(buy|sell|long|short|b|s)',
            re.IGNORECASE
        )
        
        # Pattern for entry price
        self.entry_pattern = re.compile(
            r'(?:enter|entry|@)\s*(\d+(?:\.\d+)?)',
            re.IGNORECASE
        )
        
        # Pattern for stop loss
        self.sl_pattern = re.compile(
            r'SL\s*(\d+(?:\.\d+)?)\s*(?:\((\d+)\))?',
            re.IGNORECASE
        )
        
        # Pattern for take profit levels
        self.tp_pattern = re.compile(
            r'TP(\d+)\s*(\d+(?:\.\d+)?)(?:\s*\((\d+)\))?',
            re.IGNORECASE
        )

    def parse(self, message: str) -> Optional[TradingSignal]:
        """Parse a trading signal message into a structured format.
        
        Args:
            message: The raw message text from Telegram
            
        Returns:
            TradingSignal object if parsing is successful, None otherwise
            
        Raises:
            ValueError: If the message format is invalid or required fields are missing
        """
        try:
            # Extract basic signal components
            symbol, direction = self._extract_symbol_and_direction(message)
            entry_price = self._extract_entry_price(message)
            stop_loss, sl_pips = self._extract_stop_loss(message)
            take_profits = self._extract_take_profits(message)
            
            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(
                message, symbol, direction, entry_price, stop_loss, take_profits
            )
            
            # Extract any additional notes
            additional_notes = self._extract_additional_notes(message)
            
            return TradingSignal(
                symbol=symbol,
                direction=direction.lower(),
                entry_price=float(entry_price),
                stop_loss=float(stop_loss),
                stop_loss_pips=sl_pips,
                take_profits=take_profits,
                timestamp=datetime.now(),
                raw_message=message,
                confidence_score=confidence_score,
                additional_notes=additional_notes
            )
            
        except Exception as e:
            logger.error(f"Failed to parse signal message: {str(e)}")
            return None

    def _extract_symbol_and_direction(self, message: str) -> tuple[str, str]:
        """Extract trading symbol and direction from message."""
        match = self.symbol_pattern.search(message)
        if not match:
            raise ValueError("Could not find symbol and direction in message")
            
        symbol, direction = match.groups()
        if symbol not in self.VALID_SYMBOLS:
            raise ValueError(f"Invalid trading symbol: {symbol}")
            
        # Normalize direction
        for dir_key, keywords in self.DIRECTION_KEYWORDS.items():
            if direction.lower() in keywords:
                return symbol, dir_key
                
        raise ValueError(f"Invalid direction: {direction}")

    def _extract_entry_price(self, message: str) -> float:
        """Extract entry price from message."""
        match = self.entry_pattern.search(message)
        if not match:
            raise ValueError("Could not find entry price in message")
        return float(match.group(1))

    def _extract_stop_loss(self, message: str) -> tuple[float, Optional[int]]:
        """Extract stop loss price and pips from message."""
        match = self.sl_pattern.search(message)
        if not match:
            raise ValueError("Could not find stop loss in message")
            
        price, pips = match.groups()
        return float(price), int(pips) if pips else None

    def _extract_take_profits(self, message: str) -> List[TakeProfit]:
        """Extract all take profit levels from message."""
        take_profits = []
        for match in self.tp_pattern.finditer(message):
            level, price, pips = match.groups()
            take_profits.append(TakeProfit(
                level=int(level),
                price=float(price),
                pips=int(pips) if pips else None
            ))
        return sorted(take_profits, key=lambda x: x.level)

    def _extract_additional_notes(self, message: str) -> Optional[str]:
        """Extract any additional notes or context from the message."""
        # Remove the main signal components to get remaining text
        cleaned = self.symbol_pattern.sub('', message)
        cleaned = self.entry_pattern.sub('', cleaned)
        cleaned = self.sl_pattern.sub('', cleaned)
        cleaned = self.tp_pattern.sub('', cleaned)
        
        # Clean up extra whitespace and newlines
        notes = ' '.join(cleaned.split())
        return notes if notes.strip() else None

    def _calculate_confidence_score(
        self,
        message: str,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profits: List[TakeProfit]
    ) -> float:
        """Calculate a confidence score for the signal based on various factors.
        
        The score ranges from 0.0 to 1.0, where:
        - 1.0 indicates high confidence
        - 0.0 indicates low confidence or invalid signal
        """
        score = 1.0
        
        # Check for required components
        if not all([symbol, direction, entry_price, stop_loss, take_profits]):
            score *= 0.5
            
        # Validate price relationships
        if direction == 'buy':
            if not (stop_loss < entry_price < max(tp.price for tp in take_profits)):
                score *= 0.8
        else:  # sell
            if not (stop_loss > entry_price > min(tp.price for tp in take_profits)):
                score *= 0.8
                
        # Check for risk management
        if not take_profits:
            score *= 0.7
            
        # Check for additional context
        if not self._extract_additional_notes(message):
            score *= 0.9
            
        return round(score, 2) 