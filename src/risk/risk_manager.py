"""Risk manager implementation for the GoldMirror trading system.

This module implements risk management functionality including account balance monitoring,
daily loss limits, position sizing, and risk exposure tracking.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional, Tuple

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

@dataclass
class RiskParameters:
    """Risk parameters for trading account management.
    
    Attributes:
        risk_per_trade_pct: Percentage of account balance to risk per trade
        max_position_size_pct: Maximum position size as percentage of account balance
        max_open_positions: Maximum number of open positions allowed
        max_daily_loss_pct: Maximum daily loss as percentage of account balance
        daily_loss_limit: Maximum daily loss in account currency (absolute value)
        min_account_balance: Minimum required account balance
        cooldown_after_loss: Seconds to wait after a loss before trading again
        max_slippage: Maximum allowed slippage in points
    """
    risk_per_trade_pct: Decimal
    max_position_size_pct: Decimal
    max_open_positions: int
    max_daily_loss_pct: Decimal
    daily_loss_limit: Decimal
    min_account_balance: Decimal
    cooldown_after_loss: int
    max_slippage: int

class RiskManager:
    """Manages trading risk and position sizing.
    
    This class handles account balance monitoring, daily loss limits,
    position sizing calculations, and risk exposure tracking.
    
    Attributes:
        risk_params: RiskParameters instance containing risk management settings
        daily_stats: Dictionary tracking daily trading statistics
    """
    
    def __init__(self, risk_params: RiskParameters) -> None:
        """Initialize the RiskManager.
        
        Args:
            risk_params: RiskParameters instance containing risk management settings
        """
        self.risk_params = risk_params
        self.daily_stats: Dict[str, Decimal] = {
            "daily_pnl": Decimal("0"),
            "daily_trades": 0,
            "max_drawdown": Decimal("0"),
            "last_reset": datetime.now(),
            "last_loss_time": None
        }
        
    def validate_account_balance(self) -> Tuple[bool, str]:
        """Validate if the current account balance meets minimum requirements.
        
        Returns:
            Tuple containing:
                - bool: True if account balance is valid, False otherwise
                - str: Error message if validation fails, empty string otherwise
        """
        try:
            account_info = mt5.account_info()
            if not account_info:
                return False, "Failed to fetch account information"
                
            balance = Decimal(str(account_info.balance))
            if balance < self.risk_params.min_account_balance:
                return False, f"Account balance {balance} below minimum required {self.risk_params.min_account_balance}"
                
            return True, ""
            
        except Exception as e:
            logger.error(f"Error validating account balance: {str(e)}")
            return False, f"Error validating account balance: {str(e)}"
            
    def check_daily_loss_limit(self) -> Tuple[bool, str]:
        """Check if daily loss limit has been reached.
        
        Returns:
            Tuple containing:
                - bool: True if within daily loss limit, False otherwise
                - str: Error message if limit reached, empty string otherwise
        """
        try:
            # Reset daily stats if it's a new day
            if datetime.now().date() > self.daily_stats["last_reset"].date():
                self._reset_daily_stats()
                
            account_info = mt5.account_info()
            if not account_info:
                return False, "Failed to fetch account information"
                
            daily_pnl = Decimal(str(account_info.profit)) - self.daily_stats["daily_pnl"]
            
            # Check both percentage and absolute daily loss limits
            max_daily_loss_pct = account_info.balance * float(self.risk_params.max_daily_loss_pct)
            max_daily_loss_abs = self.risk_params.daily_loss_limit
            
            if daily_pnl < -max_daily_loss_pct:
                return False, f"Daily loss percentage limit reached: {daily_pnl} < -{max_daily_loss_pct}"
            if daily_pnl < -max_daily_loss_abs:
                return False, f"Daily loss absolute limit reached: {daily_pnl} < -{max_daily_loss_abs}"
                
            return True, ""
            
        except Exception as e:
            logger.error(f"Error checking daily loss limit: {str(e)}")
            return False, f"Error checking daily loss limit: {str(e)}"
            
    def check_cooldown_period(self) -> Tuple[bool, str]:
        """Check if we're in cooldown period after a loss.
        
        Returns:
            Tuple containing:
                - bool: True if cooldown period has passed, False otherwise
                - str: Error message if in cooldown, empty string otherwise
        """
        if self.daily_stats["last_loss_time"] is None:
            return True, ""
            
        cooldown_end = self.daily_stats["last_loss_time"] + timedelta(seconds=self.risk_params.cooldown_after_loss)
        if datetime.now() < cooldown_end:
            remaining = cooldown_end - datetime.now()
            return False, f"In cooldown period after loss. {remaining.seconds} seconds remaining"
            
        return True, ""
            
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        risk_amount: Optional[Decimal] = None
    ) -> Tuple[Decimal, str]:
        """Calculate appropriate position size based on risk parameters.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price for the position
            stop_loss: Stop loss price
            risk_amount: Optional specific risk amount to use
            
        Returns:
            Tuple containing:
                - Decimal: Calculated position size in lots
                - str: Error message if calculation fails, empty string otherwise
        """
        try:
            account_info = mt5.account_info()
            if not account_info:
                return Decimal("0"), "Failed to fetch account information"
                
            # Get symbol info for lot size calculation
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return Decimal("0"), f"Failed to fetch symbol info for {symbol}"
                
            # Calculate risk amount if not provided
            if risk_amount is None:
                risk_amount = Decimal(str(account_info.balance)) * self.risk_params.risk_per_trade_pct
                
            # Calculate position size based on risk
            price_risk = abs(entry_price - stop_loss)
            if price_risk == 0:
                return Decimal("0"), "Invalid price risk (entry price equals stop loss)"
                
            position_size = risk_amount / price_risk
            
            # Convert to lots and apply maximum position size limit
            max_position_size = Decimal(str(account_info.balance)) * self.risk_params.max_position_size_pct
            position_size = min(position_size, max_position_size)
            
            # Round to symbol's lot step
            lot_step = Decimal(str(symbol_info.volume_step))
            position_size = (position_size / lot_step).quantize(Decimal("1")) * lot_step
            
            return position_size, ""
            
        except Exception as e:
            logger.error(f"Error calculating position size: {str(e)}")
            return Decimal("0"), f"Error calculating position size: {str(e)}"
            
    def _reset_daily_stats(self) -> None:
        """Reset daily trading statistics."""
        self.daily_stats = {
            "daily_pnl": Decimal("0"),
            "daily_trades": 0,
            "max_drawdown": Decimal("0"),
            "last_reset": datetime.now(),
            "last_loss_time": None
        }
        
    def update_daily_stats(self, pnl: Decimal) -> None:
        """Update daily trading statistics.
        
        Args:
            pnl: Profit/loss amount to add to daily statistics
        """
        self.daily_stats["daily_pnl"] += pnl
        self.daily_stats["daily_trades"] += 1
        self.daily_stats["max_drawdown"] = min(
            self.daily_stats["max_drawdown"],
            self.daily_stats["daily_pnl"]
        )
        
        # Update last loss time if this was a losing trade
        if pnl < 0:
            self.daily_stats["last_loss_time"] = datetime.now() 