"""Risk management module for MT5 trading.

This module provides risk management functionality specifically for MT5 trading,
including position sizing, risk limits, and trade validation.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple, Dict, List

import structlog
import MetaTrader5 as mt5

from src.risk.risk_manager import RiskManager, RiskParameters

logger = structlog.get_logger(__name__)

@dataclass
class RiskConfig:
    """Configuration for MT5 risk management.
    
    Attributes:
        risk_per_trade_pct: Percentage of account balance to risk per trade
        max_position_size_pct: Maximum position size as percentage of account balance
        max_open_positions: Maximum number of open positions allowed
        max_daily_loss_pct: Maximum daily loss as percentage of account balance
        daily_loss_limit: Maximum daily loss in account currency
        min_account_balance: Minimum required account balance
        cooldown_after_loss: Seconds to wait after a loss before trading again
        max_slippage: Maximum allowed slippage in points
    """
    risk_per_trade_pct: float = 0.25  # 0.25% risk per trade
    max_position_size_pct: float = 2.0  # 2% max position size
    max_open_positions: int = 5
    max_daily_loss_pct: float = 2.0  # 2% max daily loss
    daily_loss_limit: float = 1000.0  # $1000 max daily loss
    min_account_balance: float = 10000.0  # $10,000 minimum balance
    cooldown_after_loss: int = 300  # 5 minutes cooldown
    max_slippage: int = 10  # 10 points max slippage

class PositionManager:
    """Manages MT5 positions with risk controls.
    
    This class handles:
    - Position sizing calculations
    - Risk limit validation
    - Position tracking and management
    """
    
    def __init__(self, connection: "MT5Connection", risk_config: RiskConfig):
        """Initialize position manager.
        
        Args:
            connection: MT5Connection instance
            risk_config: Risk configuration parameters
        """
        self.connection = connection
        self.risk_config = risk_config
        self.risk_manager = RiskManager(RiskParameters(
            risk_per_trade_pct=Decimal(str(risk_config.risk_per_trade_pct / 100)),
            max_position_size_pct=Decimal(str(risk_config.max_position_size_pct / 100)),
            max_open_positions=risk_config.max_open_positions,
            max_daily_loss_pct=Decimal(str(risk_config.max_daily_loss_pct / 100)),
            daily_loss_limit=Decimal(str(risk_config.daily_loss_limit)),
            min_account_balance=Decimal(str(risk_config.min_account_balance)),
            cooldown_after_loss=risk_config.cooldown_after_loss,
            max_slippage=risk_config.max_slippage
        ))
        
    async def check_risk_limits(self) -> Tuple[bool, str]:
        """Check if current trading activity complies with risk limits.
        
        Returns:
            Tuple[bool, str]: (is_compliant, reason if not compliant)
        """
        # Check account balance
        balance_ok, balance_msg = self.risk_manager.validate_account_balance()
        if not balance_ok:
            return False, balance_msg
            
        # Check daily loss limit
        loss_ok, loss_msg = self.risk_manager.check_daily_loss_limit()
        if not loss_ok:
            return False, loss_msg
            
        # Check cooldown period
        cooldown_ok, cooldown_msg = self.risk_manager.check_cooldown_period()
        if not cooldown_ok:
            return False, cooldown_msg
            
        # Check open positions limit
        positions = mt5.positions_get()
        if positions and len(positions) >= self.risk_config.max_open_positions:
            return False, f"Maximum open positions limit reached: {len(positions)}/{self.risk_config.max_open_positions}"
            
        return True, ""
        
    async def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: Optional[float] = None
    ) -> Optional[float]:
        """Calculate appropriate position size based on risk parameters.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price for the position
            stop_loss: Optional stop loss price
            
        Returns:
            Optional[float]: Position size in lots, None if calculation fails
        """
        try:
            if stop_loss is None:
                # If no stop loss provided, use a default risk of 1% of entry price
                stop_loss = entry_price * 0.99 if entry_price > 0 else entry_price * 1.01
                
            size, error = self.risk_manager.calculate_position_size(
                symbol=symbol,
                entry_price=Decimal(str(entry_price)),
                stop_loss=Decimal(str(stop_loss))
            )
            
            if error:
                logger.error(
                    "position_size_calculation_failed",
                    error=error,
                    symbol=symbol,
                    entry_price=entry_price,
                    stop_loss=stop_loss
                )
                return None
                
            return float(size)
            
        except Exception as e:
            logger.error(
                "position_size_calculation_error",
                error=str(e),
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss
            )
            return None
            
    async def update_positions(self) -> None:
        """Update position tracking and risk statistics."""
        try:
            positions = mt5.positions_get()
            if not positions:
                return
                
            total_pnl = sum(pos.profit + pos.swap for pos in positions)
            self.risk_manager.update_daily_stats(Decimal(str(total_pnl)))
            
        except Exception as e:
            logger.error("position_update_error", error=str(e))
            
    async def get_position_info(self, order_id: int) -> Optional[Dict]:
        """Get detailed information about a position.
        
        Args:
            order_id: Order ticket number
            
        Returns:
            Optional[Dict]: Position information if found
        """
        try:
            position = mt5.positions_get(ticket=order_id)
            if not position:
                return None
                
            position = position[0]
            return {
                "ticket": position.ticket,
                "symbol": position.symbol,
                "type": "BUY" if position.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": position.volume,
                "price_open": position.price_open,
                "sl": position.sl,
                "tp": position.tp,
                "profit": position.profit,
                "swap": position.swap,
                "magic": position.magic,
                "comment": position.comment
            }
            
        except Exception as e:
            logger.error(
                "get_position_info_error",
                error=str(e),
                order_id=order_id
            )
            return None
            
    async def get_daily_stats(self) -> Dict:
        """Get daily trading statistics.
        
        Returns:
            Dict: Daily trading statistics
        """
        try:
            positions = mt5.positions_get()
            total_pnl = sum(pos.profit + pos.swap for pos in positions) if positions else 0
            
            return {
                "daily_pnl": float(self.risk_manager.daily_stats["daily_pnl"]),
                "daily_trades": self.risk_manager.daily_stats["daily_trades"],
                "max_drawdown": float(self.risk_manager.daily_stats["max_drawdown"]),
                "open_positions": len(positions) if positions else 0,
                "current_pnl": total_pnl
            }
            
        except Exception as e:
            logger.error("get_daily_stats_error", error=str(e))
            return {
                "daily_pnl": 0.0,
                "daily_trades": 0,
                "max_drawdown": 0.0,
                "open_positions": 0,
                "current_pnl": 0.0
            } 