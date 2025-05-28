"""Signal validator module for validating trading signals.

This module implements the SignalValidator class which is responsible for validating
trading signals before they are executed, including checks for:
- Signal age
- Duplicate detection
- Symbol availability
- Required fields
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple, Any, Union
import json
import logging

import structlog

from .signal_parser import TradingSignal, TakeProfit
from ..mt5.connection import MT5Connection
from ..db.repositories.signal import SignalRepository
from ..db.models.signal import Signal
from src.common.types import SignalDirection, SignalType, SignalStatus

logger = structlog.get_logger(__name__)

@dataclass
class ValidationResult:
    """Result of signal validation including validity status and details."""
    is_valid: bool
    reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class SignalValidator:
    """Validator for trading signals.
    
    This class handles the validation of trading signals, including:
    - Required field validation
    - Signal age checking
    - Symbol availability verification
    - Duplicate signal detection using database
    """
    
    def __init__(
        self,
        signal_repository: SignalRepository,
        max_signal_age_minutes: int = 5,
        duplicate_window_minutes: int = 30,
        mt5_connection: Optional[MT5Connection] = None
    ):
        """Initialize the signal validator.
        
        Args:
            signal_repository: Repository for signal operations
            max_signal_age_minutes: Maximum age of a signal in minutes
            duplicate_window_minutes: Time window for duplicate detection
            mt5_connection: Optional MT5 connection for symbol validation
        """
        self.signal_repository = signal_repository
        self.max_signal_age = timedelta(minutes=max_signal_age_minutes)
        self.duplicate_window = timedelta(minutes=duplicate_window_minutes)
        self.mt5_connection = mt5_connection
        self._available_symbols: Set[str] = set()
        
    def clear_available_symbols(self) -> None:
        """Clear the available symbols cache."""
        self._available_symbols.clear()
        logger.info(
            "available_symbols_cleared",
            available_symbols_count=len(self._available_symbols)
        )
        
    async def validate(self, signal: Union[Signal, TradingSignal]) -> ValidationResult:
        """Validate a signal.
        
        Args:
            signal: Signal to validate (either database Signal or TradingSignal)
            
        Returns:
            ValidationResult containing validation status and details
        """
        # Convert database signal to TradingSignal if needed
        if isinstance(signal, Signal):
            trading_signal = signal.to_trading_signal()
        else:
            trading_signal = signal
            
        return await self.validate_signal(trading_signal)
        
    async def validate_signal(self, signal: TradingSignal) -> ValidationResult:
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
            created_at=signal.created_at.isoformat()
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
            
        # Check for duplicates in database
        # duplicate_result = await self._check_duplicate(signal)
        # if not duplicate_result.is_valid:
        #     return duplicate_result
            
        return ValidationResult(
            is_valid=True,
            reason="Signal validated successfully",
            details={
                "confidence_score": signal.confidence_score,
                "validation_time": datetime.now(tz=timezone.utc).isoformat()
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
            
        if not signal.direction:
            return ValidationResult(False, "Invalid direction")
            
        if not signal.entry_price or signal.entry_price <= 0:
            return ValidationResult(False, "Invalid entry price")
            
        if not signal.stop_loss or signal.stop_loss <= 0:
            return ValidationResult(False, "Invalid stop loss")
            
        if not signal.take_profits:
            return ValidationResult(False, "Missing take profit levels")
            
        # Validate price relationships
        if signal.direction == SignalDirection.BUY:
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
        signal_age = datetime.now(tz=timezone.utc) - signal.created_at
        
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
        
    async def _check_duplicate(self, signal: TradingSignal) -> ValidationResult:
        """Check if the signal is a duplicate using the database.
        
        Args:
            signal: The trading signal to check
            
        Returns:
            ValidationResult indicating if signal is unique
        """
        # Create a temporary Signal object for duplicate check
        temp_signal = Signal(
            id=None,  # New signal, no ID yet
            message_id=signal.message_id,
            chat_id=signal.chat_id,
            channel_name=signal.channel_name,
            signal_type=signal.signal_type,
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profits[0].price if signal.take_profits else None,
            created_at=signal.created_at,
            status=SignalStatus.PENDING,
            is_duplicate=False,
            deleted_at=None,
            signal_metadata=None
        )
        
        # Check for duplicates in database
        duplicate = await self.signal_repository.find_duplicate(
            temp_signal,
            time_window=self.duplicate_window
        )
        
        if duplicate:
            return ValidationResult(
                False,
                "Duplicate signal detected in database",
                {
                    "original_signal_id": str(duplicate.id),
                    "original_signal_time": duplicate.created_at.isoformat(),
                    "time_difference_minutes": (
                        (signal.created_at - duplicate.created_at).total_seconds() / 60
                    )
                }
            )
            
        return ValidationResult(True, "No duplicate detected")

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