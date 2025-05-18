"""MT5 position management module.

This module implements the PositionManager class which handles:
- Position tracking and monitoring
- Risk calculation and position sizing
- Take profit and stop loss management
- Position analytics and reporting
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union
import asyncio

import MetaTrader5 as mt5
import structlog
from pydantic import BaseModel, Field, validator

logger = structlog.get_logger(__name__)

class PositionType(Enum):
    """Types of trading positions."""
    BUY = mt5.POSITION_TYPE_BUY
    SELL = mt5.POSITION_TYPE_SELL

class PositionStatus(Enum):
    """Status of a trading position."""
    OPEN = "open"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"
    MODIFIED = "modified"

@dataclass
class PositionInfo:
    """Information about a trading position."""
    ticket: int
    symbol: str
    type: PositionType
    volume: float
    price_open: float
    price_current: float
    sl: Optional[float]
    tp: Optional[float]
    profit: float
    swap: float
    comment: str
    magic: int
    time_open: datetime
    status: PositionStatus = PositionStatus.OPEN
    partial_closes: List[Tuple[float, float]] = None  # (volume, price) pairs
    modifications: List[Dict] = None  # List of modifications

class RiskConfig(BaseModel):
    """Configuration for risk management."""
    account_balance: float = Field(gt=0)
    risk_per_trade: float = Field(gt=0, le=100)  # Percentage
    max_open_trades: int = Field(gt=0)
    max_daily_loss: float = Field(gt=0, le=100)  # Percentage
    max_symbol_risk: float = Field(gt=0, le=100)  # Maximum risk per symbol (%)
    position_sizing: str = Field(pattern="^(risk_based|fixed)$")
    fixed_position_size: Optional[float] = None

    @validator("fixed_position_size")
    def validate_fixed_size(cls, v, values):
        """Validate fixed position size when position_sizing is fixed."""
        if values.get("position_sizing") == "fixed" and v is None:
            raise ValueError("fixed_position_size is required when position_sizing is fixed")
        return v

class PositionManager:
    """Manages trading positions and risk in MT5.
    
    This class provides functionality for:
    - Tracking open positions
    - Calculating position sizes
    - Managing risk exposure
    - Monitoring position status
    - Position analytics
    """
    
    def __init__(self, connection: "MT5Connection", risk_config: RiskConfig):
        """Initialize position manager.
        
        Args:
            connection: MT5Connection instance
            risk_config: RiskConfig with risk management settings
        """
        self.connection = connection
        self.risk_config = risk_config
        self._lock = asyncio.Lock()
        self._positions: Dict[int, PositionInfo] = {}  # ticket -> PositionInfo
        self._daily_stats = {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "profit": 0.0,
            "max_drawdown": 0.0
        }
        
    async def update_positions(self) -> None:
        """Update information about all open positions."""
        if not self.connection.is_connected:
            logger.error("mt5_not_connected")
            return
            
        async with self._lock:
            try:
                positions = mt5.positions_get()
                if not positions:
                    self._positions.clear()
                    return
                    
                # Update existing positions and add new ones
                current_tickets = set()
                for pos in positions:
                    current_tickets.add(pos.ticket)
                    
                    if pos.ticket in self._positions:
                        # Update existing position
                        position = self._positions[pos.ticket]
                        position.price_current = pos.price_current
                        position.profit = pos.profit
                        position.swap = pos.swap
                        
                        # Check for modifications
                        if pos.sl != position.sl or pos.tp != position.tp:
                            if position.modifications is None:
                                position.modifications = []
                            position.modifications.append({
                                "time": datetime.now(),
                                "old_sl": position.sl,
                                "new_sl": pos.sl,
                                "old_tp": position.tp,
                                "new_tp": pos.tp
                            })
                            position.sl = pos.sl
                            position.tp = pos.tp
                            position.status = PositionStatus.MODIFIED
                    else:
                        # Add new position
                        self._positions[pos.ticket] = PositionInfo(
                            ticket=pos.ticket,
                            symbol=pos.symbol,
                            type=PositionType(pos.type),
                            volume=pos.volume,
                            price_open=pos.price_open,
                            price_current=pos.price_current,
                            sl=pos.sl,
                            tp=pos.tp,
                            profit=pos.profit,
                            swap=pos.swap,
                            comment=pos.comment,
                            magic=pos.magic,
                            time_open=datetime.fromtimestamp(pos.time),
                            status=PositionStatus.OPEN,
                            partial_closes=[],
                            modifications=[]
                        )
                        
                # Remove closed positions
                closed_tickets = set(self._positions.keys()) - current_tickets
                for ticket in closed_tickets:
                    position = self._positions[ticket]
                    if position.partial_closes:
                        position.status = PositionStatus.PARTIALLY_CLOSED
                    else:
                        position.status = PositionStatus.CLOSED
                        # Update daily stats
                        self._update_daily_stats(position)
                    del self._positions[ticket]
                    
            except Exception as e:
                logger.error(
                    "update_positions_error",
                    error=str(e)
                )
                
    def _update_daily_stats(self, position: PositionInfo) -> None:
        """Update daily trading statistics.
        
        Args:
            position: Closed position information
        """
        self._daily_stats["trades"] += 1
        self._daily_stats["profit"] += position.profit + position.swap
        
        if position.profit > 0:
            self._daily_stats["wins"] += 1
        else:
            self._daily_stats["losses"] += 1
            
        # Update max drawdown
        current_drawdown = abs(min(0, self._daily_stats["profit"]))
        self._daily_stats["max_drawdown"] = max(
            self._daily_stats["max_drawdown"],
            current_drawdown
        )
        
    async def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        risk_amount: Optional[float] = None
    ) -> Optional[float]:
        """Calculate position size based on risk parameters.
        
        For XAU/USD (Gold):
        - Standard lot = 100 oz
        - 1 pip = $0.01
        - Pip value = $1 per pip per lot
        - Formula: Lot Size = Risk Amount / Stop Loss in pips
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price level
            stop_loss: Stop loss price level
            risk_amount: Optional specific risk amount to use
            
        Returns:
            Optional[float]: Position size in lots, None if calculation fails
        """
        logger.info(
            "starting_position_calculation",
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_amount=risk_amount,
            is_connected=self.connection.is_connected
        )
        
        if not self.connection.is_connected:
            logger.error("mt5_not_connected")
            return None
            
        try:
            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)
            logger.info(
                "symbol_info_retrieved",
                symbol=symbol,
                symbol_info_exists=bool(symbol_info),
                symbol_info_dict=symbol_info._asdict() if symbol_info else None
            )
            
            if not symbol_info:
                logger.error(
                    "symbol_not_found",
                    symbol=symbol
                )
                return None
                
            # Calculate risk amount if not provided
            if risk_amount is None:
                if self.risk_config.position_sizing == "fixed":
                    return self.risk_config.fixed_position_size
                    
                account_info = mt5.account_info()
                if not account_info:
                    logger.error("account_info_not_found")
                    return None
                    
                risk_amount = account_info.balance * (self.risk_config.risk_per_trade / 100)
                
            # Special handling for XAU/USD
            if symbol == "XAUUSD":
                # Get account info first to ensure we have it
                account_info = mt5.account_info()
                if not account_info:
                    logger.error(
                        "account_info_not_found_for_gold",
                        symbol=symbol
                    )
                    return None
                    
                # Validate risk parameters
                if self.risk_config.risk_per_trade <= 0 or self.risk_config.risk_per_trade > 100:
                    logger.error(
                        "invalid_risk_per_trade",
                        risk_per_trade=self.risk_config.risk_per_trade,
                        symbol=symbol
                    )
                    return None
                    
                # Calculate stop loss in pips (1 pip = 0.01 for Gold)
                stop_loss_pips = abs(entry_price - stop_loss) * 100  # Convert to pips
                if stop_loss_pips == 0:
                    logger.error(
                        "invalid_stop_loss_pips",
                        entry_price=entry_price,
                        stop_loss=stop_loss,
                        symbol=symbol
                    )
                    return None
                
                # For Gold, pip value is $1 per lot, so we can directly calculate lots
                position_size = risk_amount / stop_loss_pips
                
                logger.info(
                    "gold_position_calculation_details",
                    symbol=symbol,
                    account_balance=account_info.balance,
                    risk_per_trade_pct=self.risk_config.risk_per_trade,
                    risk_amount=risk_amount,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    stop_loss_distance=abs(entry_price - stop_loss),
                    stop_loss_pips=stop_loss_pips,
                    calculated_lots=position_size,
                    volume_min=symbol_info.volume_min,
                    volume_max=symbol_info.volume_max,
                    volume_step=symbol_info.volume_step
                )
                
                # Validate position size against symbol limits before rounding
                if position_size < symbol_info.volume_min:
                    logger.error(
                        "position_size_below_minimum",
                        calculated_size=position_size,
                        minimum_size=symbol_info.volume_min,
                        symbol=symbol,
                        risk_amount=risk_amount,
                        stop_loss_pips=stop_loss_pips
                    )
                    return None
                    
                if position_size > symbol_info.volume_max:
                    logger.error(
                        "position_size_above_maximum",
                        calculated_size=position_size,
                        maximum_size=symbol_info.volume_max,
                        symbol=symbol,
                        risk_amount=risk_amount,
                        stop_loss_pips=stop_loss_pips
                    )
                    return None
                    
                # Round to lot step
                position_size = round(position_size / symbol_info.volume_step) * symbol_info.volume_step
                
                logger.info(
                    "gold_position_size_final",
                    symbol=symbol,
                    initial_size=risk_amount / stop_loss_pips,
                    rounded_size=position_size,
                    lot_step=symbol_info.volume_step,
                    risk_amount=risk_amount,
                    stop_loss_pips=stop_loss_pips
                )
            else:
                # Original calculation for other symbols
                price_risk = abs(entry_price - stop_loss)
                if price_risk == 0:
                    logger.error(
                        "invalid_price_risk",
                        entry_price=entry_price,
                        stop_loss=stop_loss
                    )
                    return None
                    
                tick_value = symbol_info.trade_tick_value
                point = symbol_info.point
                monetary_risk_per_point = risk_amount / price_risk
                position_size = monetary_risk_per_point / (tick_value * point)
            
            # Adjust to symbol lot step
            position_size = round(
                position_size / symbol_info.volume_step
            ) * symbol_info.volume_step
            
            # Validate against symbol limits
            position_size = min(
                position_size,
                symbol_info.volume_max
            )
            position_size = max(
                position_size,
                symbol_info.volume_min
            )
            
            # Check against max open trades
            if len(self._positions) >= self.risk_config.max_open_trades:
                logger.warning(
                    "max_open_trades_reached",
                    current=len(self._positions),
                    max=self.risk_config.max_open_trades
                )
                return None
                
            # Check symbol risk exposure
            symbol_risk = self._calculate_symbol_risk(symbol)
            if symbol_risk >= self.risk_config.max_symbol_risk:
                logger.warning(
                    "max_symbol_risk_reached",
                    symbol=symbol,
                    current_risk=symbol_risk,
                    max_risk=self.risk_config.max_symbol_risk
                )
                return None
                
            return position_size
            
        except Exception as e:
            logger.error(
                "calculate_position_size_error",
                error=str(e),
                symbol=symbol
            )
            return None
            
    def _calculate_symbol_risk(self, symbol: str) -> float:
        """Calculate current risk exposure for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            float: Current risk exposure as percentage of account
        """
        try:
            account_info = mt5.account_info()
            if not account_info:
                return 0.0
                
            symbol_positions = [
                pos for pos in self._positions.values()
                if pos.symbol == symbol
            ]
            
            if not symbol_positions:
                return 0.0
                
            total_risk = sum(
                abs(pos.price_open - (pos.sl or pos.price_open)) * pos.volume
                for pos in symbol_positions
            )
            
            return (total_risk / account_info.balance) * 100
            
        except Exception as e:
            logger.error(
                "calculate_symbol_risk_error",
                error=str(e),
                symbol=symbol
            )
            return 0.0
            
    async def get_position_info(self, ticket: int) -> Optional[PositionInfo]:
        """Get information about a specific position.
        
        Args:
            ticket: Position ticket
            
        Returns:
            Optional[PositionInfo]: Position information if found
        """
        await self.update_positions()
        return self._positions.get(ticket)
        
    async def get_all_positions(self) -> List[PositionInfo]:
        """Get information about all open positions.
        
        Returns:
            List[PositionInfo]: List of position information
        """
        await self.update_positions()
        return list(self._positions.values())
        
    async def get_daily_stats(self) -> Dict:
        """Get daily trading statistics.
        
        Returns:
            Dict: Daily trading statistics
        """
        return self._daily_stats.copy()
        
    async def check_risk_limits(self) -> Tuple[bool, str]:
        """Check if current positions comply with risk limits.
        
        Returns:
            Tuple[bool, str]: (Compliance status, Reason if not compliant)
        """
        try:
            account_info = mt5.account_info()
            if not account_info:
                return False, "Account information not available"
                
            # Check daily loss limit
            daily_loss_pct = (abs(min(0, self._daily_stats["profit"])) / account_info.balance) * 100
            if daily_loss_pct >= self.risk_config.max_daily_loss:
                return False, f"Daily loss limit reached: {daily_loss_pct:.2f}%"
                
            # Check max open trades
            if len(self._positions) > self.risk_config.max_open_trades:
                return False, f"Max open trades exceeded: {len(self._positions)}"
                
            # Check symbol risk limits
            for symbol in set(pos.symbol for pos in self._positions.values()):
                symbol_risk = self._calculate_symbol_risk(symbol)
                if symbol_risk > self.risk_config.max_symbol_risk:
                    return False, f"Symbol risk limit exceeded for {symbol}: {symbol_risk:.2f}%"
                    
            return True, "All risk limits are within bounds"
            
        except Exception as e:
            logger.error(
                "check_risk_limits_error",
                error=str(e)
            )
            return False, f"Error checking risk limits: {str(e)}" 