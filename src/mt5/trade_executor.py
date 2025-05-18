"""MT5 trade execution module.

This module implements the TradeExecutor class which handles:
- Order placement and management
- Partial take profit handling
- Breakeven management
- Order modifications
- Risk management through PositionManager
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

from .position_manager import PositionManager, RiskConfig

logger = structlog.get_logger(__name__)

class OrderType(Enum):
    """Types of trading orders."""
    MARKET = mt5.ORDER_TYPE_MARKET
    LIMIT = mt5.ORDER_TYPE_LIMIT
    STOP = mt5.ORDER_TYPE_STOP
    STOP_LIMIT = mt5.ORDER_TYPE_STOP_LIMIT

class OrderAction(Enum):
    """Trading order actions."""
    BUY = mt5.ORDER_TYPE_BUY
    SELL = mt5.ORDER_TYPE_SELL

@dataclass
class OrderRequest:
    """Request for placing a new order."""
    symbol: str
    action: OrderAction
    order_type: OrderType
    volume: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    comment: str = ""
    expiration: Optional[datetime] = None
    magic: int = 0
    deviation: int = 10  # Maximum price deviation in points

class PartialTP(BaseModel):
    """Configuration for partial take profit."""
    volume: float = Field(gt=0, le=1)  # Volume as fraction of total position
    price: float
    triggered: bool = False

class BreakevenConfig(BaseModel):
    """Configuration for breakeven management."""
    activation_price: float  # Price level to activate breakeven
    offset_points: int = 0  # Points to add/subtract from entry for breakeven
    triggered: bool = False

class OrderModification(BaseModel):
    """Request for modifying an existing order."""
    order_id: int
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    expiration: Optional[datetime] = None

class TradeExecutor:
    """Handles trade execution and management in MT5.
    
    This class provides functionality for:
    - Placing and managing orders
    - Handling partial take profits
    - Managing breakeven levels
    - Modifying existing orders
    - Risk management through PositionManager
    """
    
    def __init__(self, connection: "MT5Connection", risk_config: RiskConfig):
        """Initialize trade executor.
        
        Args:
            connection: MT5Connection instance for trading
            risk_config: RiskConfig for position management
        """
        self.connection = connection
        self._lock = asyncio.Lock()
        self._active_orders: Dict[int, Dict] = {}  # order_id -> order info
        self._partial_tps: Dict[int, List[PartialTP]] = {}  # order_id -> [PartialTP]
        self._breakeven_configs: Dict[int, BreakevenConfig] = {}  # order_id -> BreakevenConfig
        self.position_manager = PositionManager(connection, risk_config)
        
    async def place_order(self, request: OrderRequest) -> Optional[int]:
        """Place a new trading order with risk management.
        
        Args:
            request: OrderRequest containing order details
            
        Returns:
            Optional[int]: Order ticket if successful, None otherwise
        """
        if not self.connection.is_connected:
            logger.error("mt5_not_connected")
            return None
            
        async with self._lock:
            try:
                # Check risk limits before placing order
                compliant, reason = await self.position_manager.check_risk_limits()
                if not compliant:
                    logger.warning(
                        "risk_limits_exceeded",
                        reason=reason
                    )
                    return None
                    
                # Calculate position size based on risk
                if request.order_type == OrderType.MARKET:
                    position_size = await self.position_manager.calculate_position_size(
                        symbol=request.symbol,
                        entry_price=request.price or mt5.symbol_info_tick(request.symbol).ask,
                        stop_loss=request.stop_loss
                    )
                    
                    if position_size is None:
                        logger.error(
                            "position_size_calculation_failed",
                            symbol=request.symbol
                        )
                        return None
                        
                    request.volume = position_size
                    
                # Prepare order request
                order_type = request.order_type.value
                if request.order_type == OrderType.MARKET:
                    order_type = request.action.value
                    
                request_dict = {
                    "action": mt5.TRADE_ACTION_DEAL if request.order_type == OrderType.MARKET
                             else mt5.TRADE_ACTION_PENDING,
                    "symbol": request.symbol,
                    "volume": request.volume,
                    "type": order_type,
                    "price": request.price if request.price else mt5.symbol_info_tick(request.symbol).ask,
                    "sl": request.stop_loss,
                    "tp": request.take_profit,
                    "deviation": request.deviation,
                    "magic": request.magic,
                    "comment": request.comment,
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK,
                }
                
                if request.expiration:
                    request_dict["type_time"] = mt5.ORDER_TIME_SPECIFIED
                    request_dict["expiration"] = int(request.expiration.timestamp())
                    
                # Send order
                result = mt5.order_send(request_dict)
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    logger.error(
                        "order_placement_failed",
                        retcode=result.retcode,
                        comment=result.comment,
                        request=request_dict
                    )
                    return None
                    
                order_id = result.order
                logger.info(
                    "order_placed",
                    order_id=order_id,
                    symbol=request.symbol,
                    action=request.action.name,
                    volume=request.volume
                )
                
                # Store order information
                self._active_orders[order_id] = {
                    "symbol": request.symbol,
                    "type": order_type,
                    "volume": request.volume,
                    "price": result.price,
                    "sl": result.sl,
                    "tp": result.tp,
                    "comment": request.comment,
                    "magic": request.magic
                }
                
                # Update position manager
                await self.position_manager.update_positions()
                
                return order_id
                
            except Exception as e:
                logger.error(
                    "order_placement_error",
                    error=str(e),
                    request=request_dict
                )
                return None
                
    async def modify_order(self, modification: OrderModification) -> bool:
        """Modify an existing order with position tracking.
        
        Args:
            modification: OrderModification containing changes
            
        Returns:
            bool indicating if modification was successful
        """
        if not self.connection.is_connected:
            logger.error("mt5_not_connected")
            return False
            
        async with self._lock:
            try:
                # Get current order info
                order = mt5.orders_get(ticket=modification.order_id)
                if not order:
                    logger.error(
                        "order_not_found",
                        order_id=modification.order_id
                    )
                    return False
                    
                order = order[0]
                
                # Prepare modification request
                request = {
                    "action": mt5.TRADE_ACTION_MODIFY,
                    "ticket": modification.order_id,
                    "price": modification.price if modification.price else order.price_open,
                    "sl": modification.stop_loss if modification.stop_loss else order.sl,
                    "tp": modification.take_profit if modification.take_profit else order.tp,
                    "type_time": mt5.ORDER_TIME_GTC,
                }
                
                if modification.expiration:
                    request["type_time"] = mt5.ORDER_TIME_SPECIFIED
                    request["expiration"] = int(modification.expiration.timestamp())
                    
                # Send modification request
                result = mt5.order_send(request)
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    logger.error(
                        "order_modification_failed",
                        retcode=result.retcode,
                        comment=result.comment,
                        request=request
                    )
                    return False
                    
                # Update stored order info
                if modification.order_id in self._active_orders:
                    self._active_orders[modification.order_id].update({
                        "price": result.price,
                        "sl": result.sl,
                        "tp": result.tp
                    })
                    
                # Update position manager
                await self.position_manager.update_positions()
                    
                logger.info(
                    "order_modified",
                    order_id=modification.order_id,
                    changes=request
                )
                
                return True
                
            except Exception as e:
                logger.error(
                    "order_modification_error",
                    error=str(e),
                    order_id=modification.order_id
                )
                return False
                
    async def close_order(self, order_id: int, volume: Optional[float] = None) -> bool:
        """Close an existing order with position tracking.
        
        Args:
            order_id: Ticket of the order to close
            volume: Optional volume to close (partial close)
            
        Returns:
            bool indicating if closure was successful
        """
        if not self.connection.is_connected:
            logger.error("mt5_not_connected")
            return False
            
        async with self._lock:
            try:
                # Get order info
                position = mt5.positions_get(ticket=order_id)
                if not position:
                    logger.error(
                        "position_not_found",
                        order_id=order_id
                    )
                    return False
                    
                position = position[0]
                
                # Prepare close request
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": position.symbol,
                    "volume": volume if volume else position.volume,
                    "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY
                            else mt5.ORDER_TYPE_BUY,
                    "position": order_id,
                    "price": mt5.symbol_info_tick(position.symbol).bid
                            if position.type == mt5.ORDER_TYPE_BUY
                            else mt5.symbol_info_tick(position.symbol).ask,
                    "deviation": 10,
                    "magic": position.magic,
                    "comment": "Close order",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK,
                }
                
                # Send close request
                result = mt5.order_send(request)
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    logger.error(
                        "order_close_failed",
                        retcode=result.retcode,
                        comment=result.comment,
                        request=request
                    )
                    return False
                    
                # Update stored order info
                if order_id in self._active_orders:
                    if volume and volume < position.volume:
                        self._active_orders[order_id]["volume"] -= volume
                    else:
                        del self._active_orders[order_id]
                        self._partial_tps.pop(order_id, None)
                        self._breakeven_configs.pop(order_id, None)
                        
                # Update position manager
                await self.position_manager.update_positions()
                        
                logger.info(
                    "order_closed",
                    order_id=order_id,
                    volume=volume if volume else position.volume
                )
                
                return True
                
            except Exception as e:
                logger.error(
                    "order_close_error",
                    error=str(e),
                    order_id=order_id
                )
                return False
                
    async def set_partial_tps(self, order_id: int, partial_tps: List[PartialTP]) -> bool:
        """Set partial take profit levels for an order.
        
        Args:
            order_id: Ticket of the order
            partial_tps: List of PartialTP configurations
            
        Returns:
            bool indicating if setup was successful
        """
        if not self.connection.is_connected:
            logger.error("mt5_not_connected")
            return False
            
        async with self._lock:
            try:
                # Validate order exists
                position = mt5.positions_get(ticket=order_id)
                if not position:
                    logger.error(
                        "position_not_found",
                        order_id=order_id
                    )
                    return False
                    
                position = position[0]
                
                # Validate total volume
                total_volume = sum(tp.volume for tp in partial_tps)
                if total_volume > 1:
                    logger.error(
                        "invalid_partial_tp_volume",
                        total_volume=total_volume
                    )
                    return False
                    
                # Store partial TPs
                self._partial_tps[order_id] = partial_tps
                
                logger.info(
                    "partial_tps_set",
                    order_id=order_id,
                    tp_count=len(partial_tps)
                )
                
                return True
                
            except Exception as e:
                logger.error(
                    "set_partial_tps_error",
                    error=str(e),
                    order_id=order_id
                )
                return False
                
    async def set_breakeven(self, order_id: int, config: BreakevenConfig) -> bool:
        """Set breakeven configuration for an order.
        
        Args:
            order_id: Ticket of the order
            config: BreakevenConfig with settings
            
        Returns:
            bool indicating if setup was successful
        """
        if not self.connection.is_connected:
            logger.error("mt5_not_connected")
            return False
            
        async with self._lock:
            try:
                # Validate order exists
                position = mt5.positions_get(ticket=order_id)
                if not position:
                    logger.error(
                        "position_not_found",
                        order_id=order_id
                    )
                    return False
                    
                position = position[0]
                
                # Store breakeven config
                self._breakeven_configs[order_id] = config
                
                logger.info(
                    "breakeven_set",
                    order_id=order_id,
                    activation_price=config.activation_price,
                    offset_points=config.offset_points
                )
                
                return True
                
            except Exception as e:
                logger.error(
                    "set_breakeven_error",
                    error=str(e),
                    order_id=order_id
                )
                return False
                
    async def check_partial_tps(self) -> None:
        """Check and execute partial take profits."""
        if not self.connection.is_connected:
            return
            
        async with self._lock:
            for order_id, tps in self._partial_tps.items():
                try:
                    position = mt5.positions_get(ticket=order_id)
                    if not position:
                        continue
                        
                    position = position[0]
                    current_price = mt5.symbol_info_tick(position.symbol).bid
                    
                    for tp in tps:
                        if tp.triggered:
                            continue
                            
                        # Check if price reached take profit level
                        if (position.type == mt5.ORDER_TYPE_BUY and current_price >= tp.price) or \
                           (position.type == mt5.ORDER_TYPE_SELL and current_price <= tp.price):
                            # Calculate volume to close
                            close_volume = position.volume * tp.volume
                            
                            # Close partial position
                            if await self.close_order(order_id, close_volume):
                                tp.triggered = True
                                logger.info(
                                    "partial_tp_triggered",
                                    order_id=order_id,
                                    tp_price=tp.price,
                                    volume=close_volume
                                )
                                
                except Exception as e:
                    logger.error(
                        "check_partial_tp_error",
                        error=str(e),
                        order_id=order_id
                    )
                    
    async def check_breakeven(self) -> None:
        """Check and execute breakeven levels."""
        if not self.connection.is_connected:
            return
            
        async with self._lock:
            for order_id, config in self._breakeven_configs.items():
                try:
                    if config.triggered:
                        continue
                        
                    position = mt5.positions_get(ticket=order_id)
                    if not position:
                        continue
                        
                    position = position[0]
                    current_price = mt5.symbol_info_tick(position.symbol).bid
                    
                    # Check if price reached activation level
                    if (position.type == mt5.ORDER_TYPE_BUY and current_price >= config.activation_price) or \
                       (position.type == mt5.ORDER_TYPE_SELL and current_price <= config.activation_price):
                        # Calculate breakeven price
                        entry_price = position.price_open
                        points = config.offset_points * mt5.symbol_info(position.symbol).point
                        
                        breakeven_price = entry_price + points if position.type == mt5.ORDER_TYPE_BUY \
                                        else entry_price - points
                                        
                        # Modify stop loss to breakeven
                        modification = OrderModification(
                            order_id=order_id,
                            stop_loss=breakeven_price
                        )
                        
                        if await self.modify_order(modification):
                            config.triggered = True
                            logger.info(
                                "breakeven_triggered",
                                order_id=order_id,
                                breakeven_price=breakeven_price
                            )
                            
                except Exception as e:
                    logger.error(
                        "check_breakeven_error",
                        error=str(e),
                        order_id=order_id
                    )
                    
    async def get_order_info(self, order_id: int) -> Optional[Dict]:
        """Get information about an order with position details.
        
        Args:
            order_id: Ticket of the order
            
        Returns:
            Optional[Dict]: Order information if found
        """
        if not self.connection.is_connected:
            return None
            
        try:
            position = mt5.positions_get(ticket=order_id)
            if not position:
                return None
                
            position = position[0]
            
            # Get position info from position manager
            position_info = await self.position_manager.get_position_info(order_id)
            
            return {
                "ticket": position.ticket,
                "symbol": position.symbol,
                "type": "BUY" if position.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": position.volume,
                "price_open": position.price_open,
                "price_current": position.price_current,
                "sl": position.sl,
                "tp": position.tp,
                "profit": position.profit,
                "swap": position.swap,
                "comment": position.comment,
                "magic": position.magic,
                "partial_tps": self._partial_tps.get(order_id, []),
                "breakeven": self._breakeven_configs.get(order_id),
                "position_status": position_info.status if position_info else None,
                "modifications": position_info.modifications if position_info else None,
                "partial_closes": position_info.partial_closes if position_info else None
            }
            
        except Exception as e:
            logger.error(
                "get_order_info_error",
                error=str(e),
                order_id=order_id
            )
            return None
            
    async def get_all_orders(self) -> List[Dict]:
        """Get information about all active orders with position details.
        
        Returns:
            List[Dict]: List of order information
        """
        if not self.connection.is_connected:
            return []
            
        try:
            positions = mt5.positions_get()
            if not positions:
                return []
                
            return [await self.get_order_info(pos.ticket) for pos in positions]
            
        except Exception as e:
            logger.error(
                "get_all_orders_error",
                error=str(e)
            )
            return []
            
    async def get_trading_stats(self) -> Dict:
        """Get comprehensive trading statistics.
        
        Returns:
            Dict: Combined statistics from position manager and executor
        """
        daily_stats = await self.position_manager.get_daily_stats()
        positions = await self.get_all_orders()
        
        return {
            "daily_stats": daily_stats,
            "open_positions": len(positions),
            "total_profit": sum(pos["profit"] for pos in positions),
            "total_swap": sum(pos["swap"] for pos in positions),
            "risk_compliance": await self.position_manager.check_risk_limits()
        } 