"""Signal validator module for validating trading signals.

This module implements the SignalValidator class which is responsible for validating
trading signals before they are executed. It ensures signals are valid, timely,
and safe to trade.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
import logging
from collections import deque

import structlog

from telegram.signal_parser import TradingSignal
from mt5.connection import MT5Connection

logger = structlog.get_logger(__name__)

@dataclass
class ValidationResult:
    """Represents the result of a signal validation attempt."""
    is_valid: bool
    reason: str
    details: Optional[Dict[str, any]] = None

class SignalValidator:
    """Validator for trading signals.
    
    This class handles the validation of trading signals, including:
    - Required field validation
    - Signal age checking
    - Symbol availability verification
    - Duplicate signal detection
    """
    
    def __init__(
        self,
        max_signal_age_minutes: int = 5,
        duplicate_window_minutes: int = 30,
        cache_size: int = 100,
        mt5_connection: Optional[MT5Connection] = None
    ):
        """Initialize the signal validator.
        
        Args:
            max_signal_age_minutes: Maximum age of a signal in minutes
            duplicate_window_minutes: Time window for duplicate detection
            cache_size: Size of the signal cache for duplicate detection
            mt5_connection: Optional MT5 connection for symbol validation
        """
        self.max_signal_age = timedelta(minutes=max_signal_age_minutes)
        self.duplicate_window = timedelta(minutes=duplicate_window_minutes)
        self.signal_cache: deque[Tuple[datetime, TradingSignal]] = deque(maxlen=cache_size)
        self.mt5_connection = mt5_connection
        self._available_symbols: Set[str] = set()
        
    def clear_cache(self) -> None:
        """Clear the signal cache and reset available symbols."""
        self.signal_cache.clear()
        self._available_symbols.clear()
        logger.info("signal_validator_cache_cleared")
        
    def validate_signal(self, signal: TradingSignal) -> ValidationResult:
        """Validate a trading signal.
        
        Args:
            signal: The trading signal to validate
            
        Returns:
            ValidationResult containing validation status and details
        """
        # Log the validation attempt
        logger.info(
            "validating_signal",
            symbol=signal.symbol,
            direction=signal.direction,
            timestamp=signal.timestamp.isoformat()
        )
        
        # Validate required fields
        required_fields_result = self._validate_required_fields(signal)
        if not required_fields_result.is_valid:
            return required_fields_result
            
        # Check signal age
        age_result = self._validate_signal_age(signal)
        if not age_result.is_valid:
            return age_result
            
        # Verify symbol availability
        symbol_result = self._verify_symbol(signal.symbol)
        if not symbol_result.is_valid:
            return symbol_result
            
        # Check for duplicates
        duplicate_result = self._check_duplicate(signal)
        if not duplicate_result.is_valid:
            return duplicate_result
            
        # Add to signal cache if valid
        self.signal_cache.append((datetime.now(), signal))
        
        return ValidationResult(
            is_valid=True,
            reason="Signal validated successfully",
            details={
                "confidence_score": signal.confidence_score,
                "validation_time": datetime.now().isoformat()
            }
        )
        
    def _validate_required_fields(self, signal: TradingSignal) -> ValidationResult:
        """Validate that all required fields are present and valid.
        
        Args:
            signal: The trading signal to validate
            
        Returns:
            ValidationResult indicating if required fields are valid
        """
        # Check for missing or invalid fields
        if not signal.symbol:
            return ValidationResult(False, "Missing symbol")
            
        if not signal.direction or signal.direction.lower() not in {'buy', 'sell'}:
            return ValidationResult(False, "Invalid direction")
            
        if not signal.entry_price or signal.entry_price <= 0:
            return ValidationResult(False, "Invalid entry price")
            
        if not signal.stop_loss or signal.stop_loss <= 0:
            return ValidationResult(False, "Invalid stop loss")
            
        if not signal.take_profits:
            return ValidationResult(False, "Missing take profit levels")
            
        # Validate price relationships
        if signal.direction.lower() == 'buy':
            if not (signal.stop_loss < signal.entry_price < max(tp.price for tp in signal.take_profits)):
                return ValidationResult(False, "Invalid price relationships for buy signal")
        else:  # sell
            if not (signal.stop_loss > signal.entry_price > min(tp.price for tp in signal.take_profits)):
                return ValidationResult(False, "Invalid price relationships for sell signal")
                
        return ValidationResult(True, "Required fields validated")
        
    def _validate_signal_age(self, signal: TradingSignal) -> ValidationResult:
        """Validate that the signal is not too old.
        
        Args:
            signal: The trading signal to validate
            
        Returns:
            ValidationResult indicating if signal age is valid
        """
        signal_age = datetime.now() - signal.timestamp
        
        if signal_age > self.max_signal_age:
            return ValidationResult(
                False,
                f"Signal too old ({signal_age.total_seconds() / 60:.1f} minutes)",
                {"max_age_minutes": self.max_signal_age.total_seconds() / 60}
            )
            
        return ValidationResult(True, "Signal age validated")
        
    def _verify_symbol(self, symbol: str) -> ValidationResult:
        """Verify that the trading symbol is available.
        
        Args:
            symbol: The trading symbol to verify
            
        Returns:
            ValidationResult indicating if symbol is valid
        """
        if not self.mt5_connection:
            # If no MT5 connection, use basic validation
            if not symbol.isalpha() or len(symbol) != 6:
                return ValidationResult(False, f"Invalid symbol format: {symbol}")
            return ValidationResult(True, "Symbol format validated (MT5 not connected)")
            
        if not self.mt5_connection.is_symbol_available(symbol):
            return ValidationResult(
                False,
                f"Symbol not available: {symbol}",
                {"available_symbols": list(self.mt5_connection.available_symbols)}
            )
            
        return ValidationResult(True, "Symbol verified")
        
    def _check_duplicate(self, signal: TradingSignal) -> ValidationResult:
        """Check if the signal is a duplicate of a recent signal.
        
        Args:
            signal: The trading signal to check
            
        Returns:
            ValidationResult indicating if signal is unique
        """
        now = datetime.now()
        
        # Clean old signals from cache
        while self.signal_cache and (now - self.signal_cache[0][0]) > self.duplicate_window:
            self.signal_cache.popleft()
            
        # Check for duplicates
        for timestamp, cached_signal in self.signal_cache:
            if self._is_similar_signal(signal, cached_signal):
                return ValidationResult(
                    False,
                    "Duplicate signal detected",
                    {
                        "original_signal_time": timestamp.isoformat(),
                        "time_difference_minutes": (now - timestamp).total_seconds() / 60
                    }
                )
                
        return ValidationResult(True, "No duplicate detected")
        
    def _is_similar_signal(self, signal1: TradingSignal, signal2: TradingSignal) -> bool:
        """Check if two signals are similar enough to be considered duplicates.
        
        Args:
            signal1: First trading signal
            signal2: Second trading signal
            
        Returns:
            bool indicating if signals are similar
        """
        # Check basic properties
        if (signal1.symbol != signal2.symbol or
            signal1.direction != signal2.direction):
            return False
            
        # Check if prices are within 0.1% of each other
        price_tolerance = 0.001
        
        if abs(signal1.entry_price - signal2.entry_price) / signal1.entry_price > price_tolerance:
            return False
            
        if abs(signal1.stop_loss - signal2.stop_loss) / signal1.stop_loss > price_tolerance:
            return False
            
        # Check take profit levels
        if len(signal1.take_profits) != len(signal2.take_profits):
            return False
            
        for tp1, tp2 in zip(signal1.take_profits, signal2.take_profits):
            if (tp1.level != tp2.level or
                abs(tp1.price - tp2.price) / tp1.price > price_tolerance):
                return False
                
        return True
        
    def update_available_symbols(self, symbols: Set[str]) -> None:
        """Update the list of available trading symbols.
        
        Args:
            symbols: Set of available trading symbols
        """
        if not self.mt5_connection:
            logger.warning(
                "updating_symbols_without_mt5",
                symbol_count=len(symbols)
            )
            return
            
        self.mt5_connection.update_available_symbols(symbols)
        logger.info(
            "updated_available_symbols",
            symbol_count=len(symbols),
            symbols=list(symbols)
        ) 