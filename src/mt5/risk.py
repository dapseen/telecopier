"""Risk management module.

This module implements risk management configurations and calculations for trading.
"""

from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel, Field

@dataclass
class RiskConfig:
    """Risk management configuration.
    
    Attributes:
        risk_per_trade: Percentage of account balance to risk per trade (0-100)
        max_open_trades: Maximum number of open trades allowed
        max_daily_loss: Maximum daily loss limit in account currency
        max_drawdown: Maximum drawdown percentage allowed (0-100)
        max_position_size: Maximum position size in lots
    """
    risk_per_trade: float = 1.0  # 1% risk per trade
    max_open_trades: int = 5
    max_daily_loss: float = 1000.0  # $1000 max daily loss
    max_drawdown: float = 20.0  # 20% max drawdown
    max_position_size: float = 1.0  # 1.0 lots max position size

class RiskMetrics(BaseModel):
    """Risk metrics for monitoring trading performance.
    
    Attributes:
        current_drawdown: Current drawdown percentage
        daily_pnl: Today's profit/loss
        open_positions: Number of currently open positions
        total_risk: Total risk exposure across all positions
    """
    current_drawdown: float = Field(ge=0, le=100)
    daily_pnl: float
    open_positions: int = Field(ge=0)
    total_risk: float = Field(ge=0)

class RiskLimits(BaseModel):
    """Risk limits for trading operations.
    
    Attributes:
        max_position_size: Maximum position size in lots
        min_position_size: Minimum position size in lots
        max_leverage: Maximum allowed leverage
        min_margin_level: Minimum required margin level
    """
    max_position_size: float = Field(gt=0)
    min_position_size: float = Field(gt=0)
    max_leverage: int = Field(gt=0)
    min_margin_level: float = Field(gt=0)

def calculate_position_size(
    account_balance: float,
    risk_per_trade: float,
    entry_price: float,
    stop_loss: float,
    symbol_info: dict
) -> Optional[float]:
    """Calculate position size based on risk parameters.
    
    Args:
        account_balance: Current account balance
        risk_per_trade: Percentage of balance to risk (0-100)
        entry_price: Entry price for the trade
        stop_loss: Stop loss price
        symbol_info: Dictionary containing symbol information
        
    Returns:
        Optional[float]: Position size in lots, or None if calculation fails
    """
    try:
        # Calculate risk amount
        risk_amount = account_balance * (risk_per_trade / 100)
        
        # Calculate stop loss distance
        sl_distance = abs(entry_price - stop_loss)
        if sl_distance <= 0:
            return None
            
        # Calculate position size
        point_value = symbol_info["point"] * symbol_info["trade_contract_size"]
        position_size = risk_amount / (sl_distance * point_value)
        
        # Round to allowed lot step
        position_size = round(position_size / symbol_info["volume_step"]) * symbol_info["volume_step"]
        
        # Ensure within allowed limits
        position_size = min(
            position_size,
            symbol_info["volume_max"],
            symbol_info["max_position_size"]
        )
        position_size = max(
            position_size,
            symbol_info["volume_min"]
        )
        
        return position_size
        
    except Exception as e:
        return None

def validate_risk_limits(
    position_size: float,
    account_balance: float,
    margin_required: float,
    risk_config: RiskConfig
) -> tuple[bool, Optional[str]]:
    """Validate trade against risk limits.
    
    Args:
        position_size: Position size in lots
        account_balance: Current account balance
        margin_required: Required margin for the position
        risk_config: Risk configuration
        
    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        # Check position size limits
        if position_size > risk_config.max_position_size:
            return False, f"Position size {position_size} exceeds maximum {risk_config.max_position_size}"
            
        # Check margin requirements
        margin_level = (account_balance / margin_required) * 100
        if margin_level < 100:
            return False, f"Insufficient margin level: {margin_level:.2f}%"
            
        return True, None
        
    except Exception as e:
        return False, str(e) 