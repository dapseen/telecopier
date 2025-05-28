"""MT5 service for managing MetaTrader 5 operations.

This module provides:
- MT5 connection management
- Trade execution
- Position management
- Account monitoring
"""

from typing import Dict, List, Optional, Set
from datetime import datetime
import yaml
from pathlib import Path

import structlog
from fastapi import HTTPException

from src.mt5.connection import MT5Connection, MT5Config
from src.mt5.trade_executor import TradeExecutor
from src.mt5.risk import RiskConfig, PositionManager
from src.common.types import OrderType, TradeState, SignalDirection

logger = structlog.get_logger(__name__)

def load_config() -> Dict:
    """Load configuration from config.yaml.
    
    Returns:
        Dict containing configuration settings
        
    Raises:
        HTTPException: If config file cannot be loaded
    """
    try:
        config_path = Path("config/config.yaml")
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found at {config_path}")
            
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error("config_load_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load configuration: {str(e)}"
        )

class MT5Service:
    """Service for managing MT5 operations."""
    
    def __init__(
        self,
        connection: MT5Connection,
        trade_executor: TradeExecutor,
        position_manager: PositionManager
    ):
        """Initialize MT5 service.
        
        Args:
            connection: MT5 connection instance
            trade_executor: Trade executor instance
            position_manager: Position manager instance
        """
        self.connection = connection
        self.executor = trade_executor
        self.position_manager = position_manager
        
    @classmethod
    async def create(cls, config: Optional[MT5Config] = None) -> "MT5Service":
        """Create MT5 service instance.
        
        Args:
            config: Optional MT5 configuration. If not provided, will load from environment.
            
        Returns:
            MT5Service instance
            
        Raises:
            HTTPException: If MT5 connection fails
        """
        try:
            # Load config from environment if not provided
            mt5_config = config or MT5Config.from_environment()
            
            # Create connection
            connection = MT5Connection(mt5_config)
            if not await connection.connect():
                raise HTTPException(
                    status_code=500,
                    detail="Failed to connect to MT5"
                )
                
            # Load configuration from file
            config_data = load_config()
            risk_settings = config_data.get("risk", {})
            
            # Create risk configuration from yaml settings
            risk_config = RiskConfig(
                risk_per_trade_pct=risk_settings.get("risk_per_trade_pct", 0.02) * 100,  # Convert to percentage
                max_position_size_pct=risk_settings.get("max_position_size_pct", 0.02) * 100,
                max_open_positions=risk_settings.get("max_open_positions", 2),
                max_daily_loss_pct=risk_settings.get("max_daily_loss_pct", 0.04) * 100,
                daily_loss_limit=risk_settings.get("daily_loss_limit", 200),
                min_account_balance=risk_settings.get("min_account_balance", 100),
                cooldown_after_loss=risk_settings.get("cooldown_after_loss", 3600),
                max_slippage=risk_settings.get("max_slippage", 5)
            )
            
            # Create components
            position_manager = PositionManager(connection, risk_config)
            trade_executor = TradeExecutor(connection, risk_config)
            
            return cls(connection, trade_executor, position_manager)
            
        except Exception as e:
            logger.error("mt5_service_creation_failed", error=str(e))
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create MT5 service: {str(e)}"
            )
            
    async def get_connection_status(self) -> Dict:
        """Get MT5 connection status.
        
        Returns:
            Dictionary containing connection status and info
        """
        return {
            "connected": self.connection.is_connected,
            "simulation_mode": self.connection.is_simulation_mode,
            **self.connection.get_connection_info()
        }
        
    async def get_account_info(self) -> Dict:
        """Get MT5 account information.
        
        Returns:
            Dictionary containing account information
            
        Raises:
            HTTPException: If failed to get account info
        """
        try:
            balance = await self.connection.get_account_balance()
            if balance is None:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to get account balance"
                )
                
            return {
                "balance": balance,
                "connected": self.connection.is_connected,
                "server": self.connection.config.server,
                "login": self.connection.config.login
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get account info: {str(e)}"
            )
            
    async def place_order(
        self,
        symbol: str,
        order_type: OrderType,
        direction: str,
        volume: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = "",
        magic: int = 0
    ) -> Dict:
        """Place a trading order.
        
        Args:
            symbol: Trading symbol
            order_type: Type of order
            direction: Trade direction (BUY/SELL)
            volume: Position size in lots
            price: Order price (required for limit/stop orders)
            stop_loss: Stop loss price
            take_profit: Take profit price
            comment: Order comment
            magic: Magic number
            
        Returns:
            Dictionary containing order result
            
        Raises:
            HTTPException: If order placement fails
        """
        try:
            # Validate symbol
            if not self.connection.is_symbol_available(symbol):
                raise HTTPException(
                    status_code=400,
                    detail=f"Symbol not available: {symbol}"
                )
                
            # Place order
            result = await self.connection.place_order(
                symbol=symbol,
                order_type=order_type.name,
                direction=direction,
                volume=volume,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment=comment,
                magic=magic
            )
            
            if "error" in result:
                raise HTTPException(
                    status_code=400,
                    detail=f"Order placement failed: {result['error']}"
                )
                
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to place order: {str(e)}"
            )
            
    async def get_positions(self) -> List[Dict]:
        """Get all open positions.
        
        Returns:
            List of dictionaries containing position information
            
        Raises:
            HTTPException: If failed to get positions
        """
        try:
            return await self.position_manager.get_positions()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get positions: {str(e)}"
            )
            
    async def close_position(
        self,
        ticket: int,
        volume: Optional[float] = None
    ) -> Dict:
        """Close a position.
        
        Args:
            ticket: Position ticket number
            volume: Optional volume to close (for partial closes)
            
        Returns:
            Dictionary containing close result
            
        Raises:
            HTTPException: If position closure fails
        """
        try:
            result = await self.position_manager.close_position(
                ticket=ticket,
                volume=volume
            )
            
            if "error" in result:
                raise HTTPException(
                    status_code=400,
                    detail=f"Position closure failed: {result['error']}"
                )
                
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to close position: {str(e)}"
            )
            
    async def modify_position(
        self,
        ticket: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict:
        """Modify a position's stop loss and take profit.
        
        Args:
            ticket: Position ticket number
            stop_loss: New stop loss price
            take_profit: New take profit price
            
        Returns:
            Dictionary containing modification result
            
        Raises:
            HTTPException: If position modification fails
        """
        try:
            result = await self.position_manager.modify_position(
                ticket=ticket,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if "error" in result:
                raise HTTPException(
                    status_code=400,
                    detail=f"Position modification failed: {result['error']}"
                )
                
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to modify position: {str(e)}"
            )
            
    async def get_available_symbols(self) -> Set[str]:
        """Get available trading symbols.
        
        Returns:
            Set of available trading symbols
        """
        return self.connection.available_symbols 