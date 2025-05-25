"""Transformer for converting Lark parse trees into structured trading signals.

This module implements the SignalTransformer class which is responsible for
converting Lark parse trees into structured TradingSignal objects.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from lark import Transformer, Token
import logging

from .models import TradingSignal, TakeProfit

logger = logging.getLogger(__name__)

class SignalTransformer(Transformer):
    """Transforms Lark parse trees into structured trading signals.
    
    This transformer converts the raw parse tree from the Lark parser into
    a structured TradingSignal object that can be used by the trading system.
    """
    
    def __init__(self, valid_symbols: set[str]):
        """Initialize the transformer with validation rules.
        
        Args:
            valid_symbols: Set of valid trading symbols to validate against.
        """
        super().__init__()
        self.valid_symbols = valid_symbols
        self._current_signal: Dict[str, Any] = {
            "symbol": None,
            "direction": None,
            "entry_price": None,
            "stop_loss": None,
            "stop_loss_pips": None,
            "take_profits": [],
            "timestamp": datetime.now(),
            "raw_message": "",
            "confidence_score": 1.0,
            "additional_notes": None
        }
        self._raw_message = ""
        
    def start(self, items):
        """Transform the start rule into a TradingSignal.
        
        Args:
            items: List of parsed items from the grammar.
            
        Returns:
            TradingSignal object if parsing was successful, None otherwise.
        """
        if not self._validate_signal():
            return None
            
        return TradingSignal(**self._current_signal)
        
    def signal(self, items):
        """Process the main signal rule.
        
        Args:
            items: List of parsed components (symbol, direction, entry, etc.)
        """
        # Store raw message for later use
        self._current_signal["raw_message"] = self._raw_message
        
        # Process each component
        for item in items:
            if isinstance(item, dict):
                self._current_signal.update(item)
                
        # Calculate confidence score
        self._current_signal["confidence_score"] = self._calculate_confidence_score()
        
    def symbol(self, items):
        """Process the symbol token.
        
        Args:
            items: List containing the symbol token.
            
        Returns:
            Dict with the symbol if valid, empty dict otherwise.
        """
        symbol = items[0].value.upper()
        if symbol not in self.valid_symbols:
            logger.warning(f"Invalid symbol: {symbol}")
            return {}
        return {"symbol": symbol}
        
    def direction(self, items):
        """Process the direction token.
        
        Args:
            items: List containing the direction token.
            
        Returns:
            Dict with normalized direction.
        """
        direction = items[0].value.lower()
        # Normalize direction
        if direction in {"b", "long"}:
            direction = "buy"
        elif direction in {"s", "short"}:
            direction = "sell"
        return {"direction": direction}
        
    def entry(self, items):
        """Process the entry price.
        
        Args:
            items: List containing the entry price token.
            
        Returns:
            Dict with the entry price.
        """
        return {"entry_price": float(items[-1].value)}
        
    def sl(self, items):
        """Process the stop loss.
        
        Args:
            items: List containing stop loss price and optional pips.
            
        Returns:
            Dict with stop loss price and pips.
        """
        result = {"stop_loss": float(items[0].value)}
        if len(items) > 1 and items[1]:
            result["stop_loss_pips"] = int(items[1][0].value)
        return result
        
    def tp(self, items):
        """Process a take profit level.
        
        Args:
            items: List containing TP level, price and optional pips.
            
        Returns:
            Dict with take profit information to be merged into signal.
        """
        # Extract TP level from token (e.g., "TP1" -> 1)
        tp_level = 1
        if items[0].value.upper().startswith("TP"):
            try:
                tp_level = int(items[0].value[2:]) if len(items[0].value) > 2 else 1
            except ValueError:
                tp_level = 1
                
        tp = {
            "level": tp_level,
            "price": float(items[1].value),
            "pips": None
        }
        
        if len(items) > 2 and items[2]:
            tp["pips"] = int(items[2][0].value)
            
        self._current_signal["take_profits"].append(TakeProfit(**tp))
        return {}
        
    def risk_note(self, items):
        """Process risk management note.
        
        Args:
            items: List containing the risk note token.
            
        Returns:
            Dict with additional notes.
        """
        return {"additional_notes": items[0].value}
        
    def COMMENT(self, token):
        """Process comment lines.
        
        Args:
            token: The comment token.
            
        Returns:
            None as comments are just stored in raw message.
        """
        return None
        
    def _validate_signal(self) -> bool:
        """Validate the parsed signal has required components.
        
        Returns:
            True if signal is valid, False otherwise.
        """
        required = ["symbol", "direction", "entry_price", "stop_loss"]
        if not all(self._current_signal.get(field) for field in required):
            logger.warning("Missing required signal components")
            return False
            
        if not self._current_signal["take_profits"]:
            logger.warning("No take profit levels found")
            return False
            
        return True
        
    def _calculate_confidence_score(self) -> float:
        """Calculate confidence score for the parsed signal.
        
        Returns:
            Float between 0.0 and 1.0 indicating confidence level.
        """
        score = 1.0
        
        # Check required components
        required = ["symbol", "direction", "entry_price", "stop_loss"]
        if not all(self._current_signal.get(field) for field in required):
            score *= 0.5
            
        # Validate price relationships
        direction = self._current_signal["direction"]
        entry = self._current_signal["entry_price"]
        sl = self._current_signal["stop_loss"]
        tps = [tp.price for tp in self._current_signal["take_profits"]]
        
        if direction == "buy":
            if not (sl < entry < max(tps)):
                score *= 0.8
        else:  # sell
            if not (sl > entry > min(tps)):
                score *= 0.8
                
        # Check for risk management
        if not self._current_signal["take_profits"]:
            score *= 0.7
            
        # Check for additional context
        if not self._current_signal["additional_notes"]:
            score *= 0.9
            
        return round(score, 2) 