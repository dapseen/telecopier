"""MT5 trade execution module.

This module implements the TradeExecutor class which handles:
- Trade execution in MT5
- Position management
- Risk management
- Trade monitoring
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any

import structlog
from pydantic import BaseModel

# Import TradingSignal only when needed to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.telegram.signal_parser import TradingSignal

from .connection import MT5Connection
from .position_manager import RiskConfig, PositionManager

logger = structlog.get_logger(__name__)

@dataclass
class TradeResult:
    """Result of a trade execution attempt."""
    success: bool
    order_id: Optional[int] = None
    error: Optional[str] = None
    simulation: bool = False

class TradeExecutor:
    """Handles execution of trading signals with risk management.
    
    This class is responsible for:
    - Validating signals against current market conditions
    - Calculating position sizes based on risk parameters
    - Placing and managing orders
    - Monitoring open positions
    - Adjusting stop loss and take profit levels
    """
    
    def __init__(
        self,
        connection: MT5Connection,
        risk_config: RiskConfig,
        simulation_mode: bool = False
    ):
        """Initialize trade executor.
        
        Args:
            connection: MT5 connection instance
            risk_config: Risk management configuration
            simulation_mode: Whether to run in simulation mode
        """
        self.connection = connection
        self.risk_config = risk_config
        self.simulation_mode = simulation_mode or connection.is_simulation_mode
        self._active_trades: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self.position_manager = PositionManager(connection, risk_config)
        
    async def execute_signal(self, signal: "TradingSignal") -> TradeResult:
        """Execute a trading signal.
        
        Args:
            signal: The trading signal to execute
            
        Returns:
            TradeResult containing execution status and details
        """
        try:
            async with self._lock:
                # Validate signal
                validation_result = self._validate_signal(signal)
                if not validation_result:
                    return TradeResult(
                        success=False,
                        error="Signal validation failed",
                        simulation=self.simulation_mode
                    )
                
                # Ensure position manager is initialized
                if not hasattr(self, 'position_manager') or self.position_manager is None:
                    logger.error(
                        "position_manager_not_initialized",
                        symbol=signal.symbol
                    )
                    return TradeResult(
                        success=False,
                        error="Position manager not initialized",
                        simulation=self.simulation_mode
                    )
                    
                # Calculate position size
                try:
                    position_size = await self._calculate_position_size(signal)
                    if not position_size:
                        return TradeResult(
                            success=False,
                            error="Failed to calculate position size",
                            simulation=self.simulation_mode
                            )
                except Exception as e:
                    logger.error(
                        "position_size_calculation_error",
                        error=str(e),
                        symbol=signal.symbol,
                        entry=signal.entry_price,
                        sl=signal.stop_loss
                    )
                    return TradeResult(
                        success=False,
                        error=f"Position size calculation error: {str(e)}",
                        simulation=self.simulation_mode
                    )
                    
                logger.info(
                    "position_size_calculated",
                    symbol=signal.symbol,
                    size=position_size,
                    entry=signal.entry_price,
                    sl=signal.stop_loss
                    )
                    
                if self.simulation_mode:
                    # Simulate trade execution
                    return await self._simulate_trade(signal, position_size)
                else:
                    # Execute real trade
                    return await self._execute_real_trade(signal, position_size)
                    
        except Exception as e:
            logger.error(
                "trade_execution_failed",
                error=str(e),
                symbol=signal.symbol,
                simulation=self.simulation_mode
            )
            return TradeResult(
                success=False,
                error=str(e),
                simulation=self.simulation_mode
            )
            
    def _validate_signal(self, signal: "TradingSignal") -> bool:
        """Validate signal against current market conditions.
        
        Args:
            signal: The trading signal to validate
            
        Returns:
            bool: True if signal is valid, False otherwise
        """
        try:
            # Check if symbol is available
            if not self.simulation_mode:
                # Use synchronous check for symbol availability
                symbol_available = self.connection.is_symbol_available(signal.symbol)
                if not symbol_available:
                    logger.warning(
                        "symbol_not_available",
                        symbol=signal.symbol
                    )
                    return False
                    
            # Check if we already have an open position
            if signal.symbol in self._active_trades:
                logger.warning(
                    "position_already_open",
                    symbol=signal.symbol
                )
                return False
                
            # Validate price levels
            if not self._validate_price_levels(signal):
                logger.warning(
                    "invalid_price_levels",
                    symbol=signal.symbol,
                    entry=signal.entry_price,
                    sl=signal.stop_loss,
                    direction=signal.direction
                )
                return False
                
            return True
            
        except Exception as e:
            logger.error(
                "signal_validation_failed",
                error=str(e),
                symbol=signal.symbol
            )
            return False
            
    def _validate_price_levels(self, signal: "TradingSignal") -> bool:
        """Validate price levels in the signal.
        
        Args:
            signal: The trading signal to validate
            
        Returns:
            bool: True if price levels are valid, False otherwise
        """
        try:
            # Basic price validation
            if signal.entry_price <= 0 or signal.stop_loss <= 0:
                logger.warning(
                    "invalid_price_values",
                    symbol=signal.symbol,
                    entry=signal.entry_price,
                    sl=signal.stop_loss,
                    direction=signal.direction
                )
                return False
                
            # Validate stop loss (case-insensitive)
            direction = signal.direction.upper()
            if direction == "BUY":
                if signal.stop_loss >= signal.entry_price:
                    logger.warning(
                        "invalid_buy_sl",
                        symbol=signal.symbol,
                        entry=signal.entry_price,
                        sl=signal.stop_loss,
                        direction=direction
                    )
                    return False
            elif direction == "SELL":
                if signal.stop_loss <= signal.entry_price:
                    logger.warning(
                        "invalid_sell_sl",
                        symbol=signal.symbol,
                        entry=signal.entry_price,
                        sl=signal.stop_loss,
                        direction=direction
                    )
                    return False
            else:
                logger.warning(
                    "invalid_direction",
                    symbol=signal.symbol,
                    direction=signal.direction
                )
                return False
                    
            # Validate take profit levels
            if not signal.take_profits:
                logger.warning(
                    "missing_take_profits",
                    symbol=signal.symbol,
                    direction=direction
                )
                return False
                
            for tp in signal.take_profits:
                if tp.price <= 0:
                    logger.warning(
                        "invalid_tp_price",
                        symbol=signal.symbol,
                        tp_level=tp.level,
                        tp_price=tp.price,
                        direction=direction
                    )
                    return False
                if direction == "BUY":
                    if tp.price <= signal.entry_price:
                        logger.warning(
                            "invalid_buy_tp",
                            symbol=signal.symbol,
                            tp_level=tp.level,
                            tp_price=tp.price,
                            entry=signal.entry_price,
                            direction=direction
                        )
                        return False
                else:  # SELL
                    if tp.price >= signal.entry_price:
                        logger.warning(
                            "invalid_sell_tp",
                            symbol=signal.symbol,
                            tp_level=tp.level,
                            tp_price=tp.price,
                            entry=signal.entry_price,
                            direction=direction
                        )
                        return False
                        
            logger.info(
                "price_levels_validated",
                symbol=signal.symbol,
                direction=direction,
                entry=signal.entry_price,
                sl=signal.stop_loss,
                tps=[(tp.level, tp.price) for tp in signal.take_profits]
            )
            return True
            
        except Exception as e:
            logger.error(
                "price_validation_failed",
                error=str(e),
                symbol=signal.symbol,
                direction=signal.direction
            )
            return False
            
    async def _calculate_position_size(self, signal: "TradingSignal") -> Optional[float]:
        """Calculate position size based on risk parameters.
        
        Args:
            signal: The trading signal to calculate position size for
            
        Returns:
            Optional[float]: Position size in lots, or None if calculation fails
        """
        try:
            if self.simulation_mode:
                logger.info(
                    "using_simulation_position_size",
                    symbol=signal.symbol,
                    size=0.1
                )
                return 0.1  # 0.1 lots
                
            # Use PositionManager for position size calculation
            try:
                position_size = await self.position_manager.calculate_position_size(
                    symbol=signal.symbol,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss
                )
                
                if position_size is None:
                    logger.error(
                        "position_size_calculation_failed",
                        symbol=signal.symbol,
                        entry=signal.entry_price,
                        sl=signal.stop_loss
                    )
                    return None
                    
                logger.info(
                    "position_size_calculation_success",
                    symbol=signal.symbol,
                    size=position_size,
                    entry=signal.entry_price,
                    sl=signal.stop_loss
                )
                
                return position_size
                
            except Exception as e:
                logger.error(
                    "position_manager_calculation_error",
                    error=str(e),
                    symbol=signal.symbol
                )
                return None
            
        except Exception as e:
            logger.error(
                "position_size_calculation_failed",
                error=str(e),
                symbol=signal.symbol
            )
            return None
            
    async def _simulate_trade(self, signal: "TradingSignal", position_size: float) -> TradeResult:
        """Simulate trade execution.
        
        Args:
            signal: The trading signal to simulate
            position_size: Position size in lots
            
        Returns:
            TradeResult containing simulation results
        """
        try:
            # Generate simulated order ID
            order_id = int(datetime.now().timestamp())
            
            # Record the simulated trade
            self._active_trades[signal.symbol] = {
                "order_id": order_id,
                "symbol": signal.symbol,
                "direction": signal.direction,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profits": signal.take_profits,
                "position_size": position_size,
                "timestamp": datetime.now(),
                "simulation": True
            }
            
            logger.info(
                "trade_simulated",
                symbol=signal.symbol,
                direction=signal.direction,
                entry=signal.entry_price,
                sl=signal.stop_loss,
                tp=[tp.price for tp in signal.take_profits],
                size=position_size
            )
            
            return TradeResult(
                success=True,
                order_id=order_id,
                simulation=True
            )
            
        except Exception as e:
            logger.error(
                "trade_simulation_failed",
                error=str(e),
                symbol=signal.symbol
            )
            return TradeResult(
                success=False,
                error=str(e),
                simulation=True
            )
            
    async def _execute_real_trade(self, signal: "TradingSignal", position_size: float) -> TradeResult:
        """Execute a real trade with partial take profit management.
        
        Args:
            signal: The trading signal to execute
            position_size: Position size in lots
            
        Returns:
            TradeResult containing execution results
        """
        try:
            # For market orders, we don't specify an entry price
            # MT5 will use current ask price for buy orders and bid price for sell orders
            order_params = {
                "symbol": signal.symbol,
                "order_type": "MARKET",
                "direction": signal.direction,
                "volume": position_size,
                "stop_loss": signal.stop_loss,
                "take_profit": None,  # We'll manage TPs separately
                "comment": f"Signal Entry: {signal.entry_price}"  # Store intended entry in comment
            }
            
            # Log order parameters
            logger.info(
                "placing_market_order",
                symbol=signal.symbol,
                direction=signal.direction,
                intended_entry=signal.entry_price,
                stop_loss=signal.stop_loss,
                volume=position_size
            )
            
            # Place the order
            order_result = await self.connection.place_order(**order_params)
            
            # Handle dictionary response from place_order
            if not isinstance(order_result, dict):
                return TradeResult(
                    success=False,
                    error="Invalid order result format",
                    simulation=False
                )
            
            if not order_result.get("success", False):
                return TradeResult(
                    success=False,
                    error=order_result.get("error", "Unknown error"),
                    simulation=False
                )
                
            order_id = order_result.get("order_id")
            if not order_id:
                return TradeResult(
                    success=False,
                    error="No order ID in response",
                    simulation=False
                )
                
            # Get the actual execution price from MT5
            actual_price = order_result.get("price")
            if not actual_price:
                logger.warning(
                    "no_execution_price",
                    symbol=signal.symbol,
                    order_id=order_id
                )
                return TradeResult(
                    success=False,
                    error="No execution price received",
                    simulation=False
                )
                
            # Set up trade management with partial take profits
            # Calculate volume fractions for each TP
            tp_volumes = [0.25] * len(signal.take_profits)  # Equal distribution
            take_profits = list(zip([tp.price for tp in signal.take_profits], tp_volumes))
            
            # Set up trade management
            if not await self.setup_trade_management(
                order_id=order_id,
                take_profits=take_profits,
                initial_sl=signal.stop_loss,
                entry_price=actual_price
            ):
                logger.error(
                    "trade_management_setup_failed",
                    order_id=order_id,
                    symbol=signal.symbol
                )
                # Don't return error here as the trade is already placed
                
            # Record the trade with actual execution price
            self._active_trades[signal.symbol] = {
                "order_id": order_id,
                "symbol": signal.symbol,
                "direction": signal.direction,
                "intended_entry": signal.entry_price,  # Store intended entry
                "actual_entry": actual_price,  # Store actual execution price
                "stop_loss": signal.stop_loss,
                "take_profits": signal.take_profits,
                "position_size": position_size,
                "timestamp": datetime.now(),
                "simulation": False
            }
            
            logger.info(
                "trade_executed",
                symbol=signal.symbol,
                direction=signal.direction,
                intended_entry=signal.entry_price,
                actual_entry=actual_price,
                sl=signal.stop_loss,
                tp=[tp.price for tp in signal.take_profits],
                size=position_size,
                order_id=order_id
            )
            
            return TradeResult(
                success=True,
                order_id=order_id,
                simulation=False
            )
            
        except Exception as e:
            logger.error(
                "real_trade_execution_failed",
                error=str(e),
                symbol=signal.symbol
            )
            return TradeResult(
                success=False,
                error=str(e),
                simulation=False
            ) 