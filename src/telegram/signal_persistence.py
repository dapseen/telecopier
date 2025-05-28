"""Signal persistence module for storing and retrieving trading signals.

This module provides functionality to:
- Store signals in the database
- Retrieve signals by various criteria
- Handle signal deduplication
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID
import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.types import SignalDirection, SignalType, SignalStatus
from src.db.repositories.signal import SignalRepository
from src.db.models.signal import Signal
from .signal_parser import TradingSignal

logger = structlog.get_logger(__name__)

class SignalPersistence:
    """Handles persistence of Telegram signals to the database.
    
    This class is responsible for:
    - Converting TradingSignal to database Signal model
    - Persisting signals to the database
    - Handling duplicate detection
    - Managing signal status
    """
    
    def __init__(self, signal_repository: SignalRepository):
        """Initialize signal persistence.
        
        Args:
            signal_repository: Repository for signal operations
        """
        self.signal_repository = signal_repository
        
    async def persist_signal(
        self,
        trading_signal: TradingSignal,
        message_id: int,
        chat_id: int,
        channel_name: str
    ) -> Optional[Signal]:
        """Persist a trading signal to the database.
        
        Args:
            trading_signal: The trading signal to persist
            message_id: Telegram message ID
            chat_id: Telegram chat ID
            channel_name: Name of the Telegram channel
            
        Returns:
            Optional[Signal]: Persisted signal if successful
        """
        try:
            # Check for existing signal
            existing_signal = await self.signal_repository.get_by_message_id(
                message_id=message_id,
                chat_id=chat_id
            )
            
            if existing_signal:
                logger.info(
                    "signal_already_exists",
                    message_id=message_id,
                    chat_id=chat_id
                )
                return existing_signal
                
            # Create signal data dictionary
            signal_data = {
                "message_id": message_id,
                "chat_id": chat_id,
                "channel_name": channel_name,
                "signal_type": SignalType.MARKET,  # Default to market order
                "symbol": trading_signal.symbol,
                "direction": trading_signal.direction,  # Already a SignalDirection enum
                "entry_price": trading_signal.entry_price,
                "stop_loss": trading_signal.stop_loss,
                "take_profit": trading_signal.take_profits[0].price if trading_signal.take_profits else None,
                "risk_reward": self._calculate_risk_reward(trading_signal),
                "status": SignalStatus.PENDING,  # Use enum instead of string
                "signal_metadata": self._create_metadata(trading_signal),
                "created_at": trading_signal.created_at
            }
            
            # Check for duplicates using signal data
            duplicate = await self.signal_repository.find_duplicate_by_data(
                symbol=signal_data["symbol"],
                direction=signal_data["direction"],
                entry_price=signal_data["entry_price"],
                message_id=message_id,
                chat_id=chat_id,
                channel_name=channel_name
            )
            
            if duplicate:
                logger.info(
                    "duplicate_signal_detected",
                    original_id=duplicate.id,
                    message_id=message_id
                )
                # Add duplicate fields to signal data
                signal_data.update({
                    "is_duplicate": True,
                    "original_signal_id": duplicate.id,
                    "status": SignalStatus.DUPLICATE
                })
            
            # Save to database using dictionary
            saved_signal = await self.signal_repository.create(signal_data)
            
            logger.info(
                "signal_persisted",
                signal_id=saved_signal.id,
                symbol=saved_signal.symbol,
                direction=saved_signal.direction.name
            )
            
            return saved_signal
            
        except Exception as e:
            logger.error(
                "signal_persistence_error",
                error=str(e),
                message_id=message_id,
                chat_id=chat_id
            )
            return None
            
    def _calculate_risk_reward(self, trading_signal: TradingSignal) -> Optional[float]:
        """Calculate risk to reward ratio.
        
        Args:
            trading_signal: Trading signal
            
        Returns:
            Optional[float]: Risk to reward ratio
        """
        try:
            if not trading_signal.take_profits or not trading_signal.stop_loss:
                return None
                
            # Use first take profit for calculation
            take_profit = trading_signal.take_profits[0].price
            entry = trading_signal.entry_price
            stop_loss = trading_signal.stop_loss
            
            # Compare enum directly instead of using lower()
            if trading_signal.direction == SignalDirection.BUY:
                reward = take_profit - entry
                risk = entry - stop_loss
            else:  # SELL
                reward = entry - take_profit
                risk = stop_loss - entry
                
            if risk <= 0:
                return None
                
            return round(reward / risk, 2)
            
        except Exception as e:
            logger.warning(
                "risk_reward_calculation_error",
                error=str(e)
            )
            return None
            
    def _create_metadata(self, trading_signal: TradingSignal) -> Optional[str]:
        """Create JSON metadata from trading signal.
        
        Args:
            trading_signal: Trading signal
            
        Returns:
            Optional[str]: JSON metadata string
        """
        try:
            metadata = {
                "confidence_score": trading_signal.confidence_score,
                "stop_loss_pips": trading_signal.stop_loss_pips,
                "take_profits": [
                    {
                        "level": tp.level,
                        "price": tp.price,
                        "pips": tp.pips
                    }
                    for tp in trading_signal.take_profits
                ],
                "additional_notes": trading_signal.additional_notes,
                "raw_message": trading_signal.raw_message
            }
            
            return json.dumps(metadata)
            
        except Exception as e:
            logger.warning(
                "metadata_creation_error",
                error=str(e)
            )
            return None 