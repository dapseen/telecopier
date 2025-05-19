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
    
    # Direction keywords
    DIRECTION_KEYWORDS = {
        'buy': {'buy', 'long', 'b'},
        'sell': {'sell', 'short', 's'}
    }
    
    def __init__(self, valid_symbols: Optional[set[str]] = None):
        """Initialize the signal parser with compiled regex patterns.
        
        Args:
            valid_symbols: Set of valid trading symbols. If None, will be populated from config.
        """
        # Initialize valid symbols from config if not provided
        self.valid_symbols = valid_symbols or self._load_symbols_from_config()
        
        # Pattern for symbol and direction - handle both single line and multiline
        self.symbol_pattern = re.compile(
            r'(?:^|\n)\s*([A-Z]{6})\s+(buy|sell|long|short|b|s)\b',
            re.IGNORECASE | re.MULTILINE
        )
        
        # Pattern for entry price - handle both with and without keywords
        self.entry_pattern = re.compile(
            r'(?:^|\n)\s*(?:enter|entry|@)?\s*(\d+(?:\.\d+)?)\b',
            re.IGNORECASE | re.MULTILINE
        )
        
        # Pattern for stop loss - handle both with and without pips
        self.sl_pattern = re.compile(
            r'(?:^|\n)\s*SL\s*(\d+(?:\.\d+)?)(?:\s*\((\d+)\))?',
            re.IGNORECASE | re.MULTILINE
        )
        
        # Pattern for take profit levels - handle both with and without pips
        self.tp_pattern = re.compile(
            r'(?:^|\n)\s*TP(\d+)\s*(\d+(?:\.\d+)?)(?:\s*\((\d+)\))?',
            re.IGNORECASE | re.MULTILINE
        )

    def _load_symbols_from_config(self) -> set[str]:
        """Load valid symbols from trading sessions in config.yaml.
        
        Returns:
            Set of valid trading symbols from all trading sessions.
        """
        try:
            import yaml
            from pathlib import Path
            
            # Load config file
            config_path = Path("config/config.yaml")
            if not config_path.exists():
                logger.warning("Config file not found: %s", str(config_path))
                return set()
                
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
                
            # Extract symbols from all trading sessions
            symbols = set()
            for session in config.get("trading_sessions", []):
                symbols.update(session.get("symbols", []))
                
            logger.info(
                "Loaded %d symbols from config: %s",
                len(symbols),
                ", ".join(sorted(symbols))
            )
            return symbols
            
        except Exception as e:
            logger.error("Failed to load symbols from config: %s", str(e))
            # Fallback to a minimal set of common symbols
            return {'XAUUSD', 'EURUSD', 'GBPUSD', 'BTCUSD'}

    def parse(self, message: str) -> Optional[TradingSignal]:
        """Parse a trading signal message into a structured format.
        
        Args:
            message: The raw message text from Telegram
            
        Returns:
            TradingSignal object if parsing is successful, None otherwise
        """
        try:
            # Normalize message by replacing multiple spaces with single space, but preserve newlines
            original_message = message
            message = re.sub(r'[ ]+', ' ', message)  # Only collapse spaces, not newlines
            # Do NOT collapse newlines into spaces
            # message = re.sub(r'\n\s*', '\n', message)  # This is fine to keep for trimming spaces after newlines
            message = re.sub(r'\n[ ]+', '\n', message)  # Remove spaces after newlines
            
            logger.debug(
                "Parsing signal (length: %d):\nOriginal: %s\nNormalized: %s",
                len(message),
                original_message,
                message
            )
            
            # Extract basic signal components
            try:
                symbol, direction = self._extract_symbol_and_direction(message)
                logger.debug(
                    "Extracted symbol and direction: %s %s (pattern: %s)",
                    symbol,
                    direction,
                    self.symbol_pattern.pattern
                )
            except ValueError as e:
                logger.debug(
                    "Failed to extract symbol and direction: %s (pattern: %s)\nMessage: %s",
                    str(e),
                    self.symbol_pattern.pattern,
                    message[:100]
                )
                return None
            
            try:
                entry_price = self._extract_entry_price(message)
                logger.debug(
                    "Extracted entry price: %s (pattern: %s)",
                    entry_price,
                    self.entry_pattern.pattern
                )
            except ValueError as e:
                logger.debug(
                    "Failed to extract entry price: %s (pattern: %s)\nMessage: %s",
                    str(e),
                    self.entry_pattern.pattern,
                    message[:100]
                )
                return None
            
            try:
                stop_loss, sl_pips = self._extract_stop_loss(message)
                logger.debug(
                    "Extracted stop loss: %s (pips: %s) (pattern: %s)",
                    stop_loss,
                    sl_pips,
                    self.sl_pattern.pattern
                )
            except ValueError as e:
                logger.debug(
                    "Failed to extract stop loss: %s (pattern: %s)\nMessage: %s",
                    str(e),
                    self.sl_pattern.pattern,
                    message[:100]
                )
                return None
            
            try:
                take_profits = self._extract_take_profits(message)
                logger.debug(
                    "Extracted %d take profits: %s (pattern: %s)",
                    len(take_profits),
                    [(tp.level, tp.price, tp.pips) for tp in take_profits],
                    self.tp_pattern.pattern
                )
            except ValueError as e:
                logger.debug(
                    "Failed to extract take profits: %s (pattern: %s)\nMessage: %s",
                    str(e),
                    self.tp_pattern.pattern,
                    message[:100]
                )
                return None
            
            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(
                message, symbol, direction, entry_price, stop_loss, take_profits
            )
            
            # Extract any additional notes
            additional_notes = self._extract_additional_notes(message)
            
            signal = TradingSignal(
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
            
            logger.debug(
                "Successfully parsed signal: %s",
                signal.__dict__
            )
            return signal
            
        except Exception as e:
            logger.error(
                "Signal parse failed: %s\nMessage: %s",
                str(e),
                message[:100]
            )
            return None

    def _extract_symbol_and_direction(self, message: str) -> tuple[str, str]:
        """Extract trading symbol and direction from message."""
        logger.debug(
            "Trying symbol pattern: %s\nMessage: %s",
            self.symbol_pattern.pattern,
            message[:100]
        )
        match = self.symbol_pattern.search(message)
        if not match:
            logger.debug(
                "Symbol pattern no match: %s\nMessage: %s",
                self.symbol_pattern.pattern,
                message[:100]
            )
            raise ValueError("Could not find symbol and direction in message")
            
        symbol, direction = match.groups()
        logger.debug(
            "Symbol pattern match: %s %s (text: %s)",
            symbol,
            direction,
            match.group(0)
        )
        
        # Convert symbol to uppercase for validation
        symbol = symbol.upper()
        if symbol not in self.valid_symbols:
            logger.debug(
                "Invalid symbol: %s (valid: %s)",
                symbol,
                ", ".join(sorted(self.valid_symbols))
            )
            raise ValueError(f"Invalid trading symbol: {symbol}")
            
        # Normalize direction
        direction = direction.lower()
        for dir_key, keywords in self.DIRECTION_KEYWORDS.items():
            if direction in keywords:
                return symbol, dir_key
                
        logger.debug(
            "Invalid direction: %s (valid: %s)",
            direction,
            ", ".join(sorted(k for k in self.DIRECTION_KEYWORDS.keys()))
        )
        raise ValueError(f"Invalid direction: {direction}")

    def _extract_entry_price(self, message: str) -> float:
        """Extract entry price from message."""
        logger.debug(
            "Trying entry pattern: %s\nMessage: %s",
            self.entry_pattern.pattern,
            message[:100]
        )
        match = self.entry_pattern.search(message)
        if not match:
            logger.debug(
                "Entry pattern no match: %s\nMessage: %s",
                self.entry_pattern.pattern,
                message[:100]
            )
            raise ValueError("Could not find entry price in message")
            
        price = float(match.group(1))
        logger.debug(
            "Entry pattern match: %s (text: %s)",
            price,
            match.group(0)
        )
        return price

    def _extract_stop_loss(self, message: str) -> tuple[float, Optional[int]]:
        """Extract stop loss price and pips from message."""
        logger.debug(
            "Trying SL pattern: %s\nMessage: %s",
            self.sl_pattern.pattern,
            message[:100]
        )
        # Use findall to get all matches, then pick the first with a price
        matches = list(self.sl_pattern.finditer(message))
        for match in matches:
            price, pips = match.groups()
            logger.debug(
                "SL pattern match: %s (pips: %s) (text: %s)",
                price,
                pips,
                match.group(0)
            )
            if price:
                return float(price), int(pips) if pips else None
        logger.debug(
            "SL pattern no match: %s\nMessage: %s",
            self.sl_pattern.pattern,
            message[:100]
        )
        raise ValueError("Could not find stop loss in message")

    def _extract_take_profits(self, message: str) -> List[TakeProfit]:
        """Extract all take profit levels from message."""
        logger.debug(
            "Trying TP pattern: %s\nMessage: %s",
            self.tp_pattern.pattern,
            message[:100]
        )
        take_profits = []
        for match in self.tp_pattern.finditer(message):
            level, price, pips = match.groups()
            logger.debug(
                "TP pattern match: level=%s, price=%s, pips=%s (text: %s)",
                level,
                price,
                pips,
                match.group(0)
            )
            take_profits.append(TakeProfit(
                level=int(level),
                price=float(price),
                pips=int(pips) if pips else None
            ))
            
        if not take_profits:
            logger.debug(
                "TP pattern no matches: %s\nMessage: %s",
                self.tp_pattern.pattern,
                message[:100]
            )
            raise ValueError("Could not find any take profit levels")
            
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
            
        # Validate price relationships but don't fail parsing
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