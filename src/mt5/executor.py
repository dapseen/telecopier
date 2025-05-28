"""MT5 trade execution module.

This module implements the TradeExecutor class which handles:
- Trade execution in MT5
- Position management
- Risk management
- Trade monitoring
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
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
from src.common.types import SignalDirection

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
        logger.info("Executing signal", signal=signal)
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
                
            # Validate stop loss (using SignalDirection enum)
            if signal.direction == SignalDirection.BUY:
                if signal.stop_loss >= signal.entry_price:
                    logger.warning(
                        "invalid_buy_sl",
                        symbol=signal.symbol,
                        entry=signal.entry_price,
                        sl=signal.stop_loss,
                        direction=signal.direction
                    )
                    return False
            elif signal.direction == SignalDirection.SELL:
                if signal.stop_loss <= signal.entry_price:
                    logger.warning(
                        "invalid_sell_sl",
                        symbol=signal.symbol,
                        entry=signal.entry_price,
                        sl=signal.stop_loss,
                        direction=signal.direction
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
                    direction=signal.direction
                )
                return False
                
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
            Optional[float]: Position size per take profit target, None if calculation fails
        """
        try:
            if self.simulation_mode:
                logger.info(
                    "using_simulation_position_size",
                    symbol=signal.symbol,
                    size=0.1
                )
                # Divide simulation size by number of TPs
                per_tp_size = 0.1 / len(signal.take_profits)
                return per_tp_size
                
            # Use PositionManager for total position size calculation
            try:
                total_size = await self.position_manager.calculate_position_size(
                    symbol=signal.symbol,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss
                )
                
                if total_size is None:
                    logger.error(
                        "position_size_calculation_failed",
                        symbol=signal.symbol,
                        entry=signal.entry_price,
                        sl=signal.stop_loss
                    )
                    return None
                    
                # Calculate per-TP size
                num_positions = len(signal.take_profits)  # Each position has its own TP
                per_tp_size = total_size / num_positions
                
                # Get symbol info for lot step rounding
                symbol_info = self.connection.mt5.symbol_info(signal.symbol)
                if symbol_info:
                    # Round to symbol's lot step
                    lot_step = symbol_info.volume_step
                    per_tp_size = round(per_tp_size / lot_step) * lot_step
                
                logger.info(
                    "position_size_calculation_success",
                    symbol=signal.symbol,
                    total_size=total_size,
                    num_positions=num_positions,
                    per_tp_size=per_tp_size,
                    entry=signal.entry_price,
                    sl=signal.stop_loss
                )
                
                return per_tp_size
                
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
            
    async def _simulate_trade(self, signal: "TradingSignal", per_position_size: float) -> TradeResult:
        """Simulate trade execution with separate orders for each take profit target.
        
        Args:
            signal: The trading signal to simulate
            per_position_size: Position size per position (each with its own TP)
            
        Returns:
            TradeResult containing simulation results
        """
        try:
            # Generate simulated order IDs
            base_timestamp = int(datetime.now().timestamp())
            order_ids = []
            
            # Simulate orders for each TP
            for i, tp in enumerate(signal.take_profits):
                order_id = base_timestamp + i
                order_ids.append(order_id)
            
            # Record the simulated trades
            self._active_trades[signal.symbol] = {
                "order_ids": order_ids,  # Store all order IDs
                "symbol": signal.symbol,
                "direction": signal.direction,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profits": signal.take_profits,
                "position_size": per_position_size * len(signal.take_profits),  # Total size
                "per_position_size": per_position_size,  # Store individual position size
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
                total_size=per_position_size * len(signal.take_profits),
                per_position_size=per_position_size,
                num_orders=len(order_ids)
            )
            
            return TradeResult(
                success=True,
                order_id=order_ids[0],  # Return first order ID for compatibility
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
            
    async def _execute_real_trade(self, signal: "TradingSignal", per_position_size: float) -> TradeResult:
        """Execute a real trade with separate orders for each take profit target.
        
        Args:
            signal: The trading signal to execute
            per_position_size: Position size per position (each with its own TP)
            
        Returns:
            TradeResult containing execution results
        """
        try:
            order_ids = []
            executed_prices = {}  # Track actual entry prices
            successful_orders = 0
            
            # Place separate orders for each take profit target
            for tp in signal.take_profits:
                order_params = {
                    "symbol": signal.symbol,
                    "order_type": "MARKET",
                    "direction": str(signal.direction),
                    "volume": per_position_size,
                    "stop_loss": signal.stop_loss,
                    "take_profit": tp.price,
                    "comment": f"Signal Position: Entry {signal.entry_price} TP {tp.price}"
                }
                
                # Log order parameters
                logger.info(
                    "placing_order",
                    symbol=signal.symbol,
                    direction=signal.direction,
                    intended_entry=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=tp.price,
                    volume=per_position_size
                )
                
                # Place order
                order_result = await self.connection.place_order(**order_params)
                if order_result.get("success", False):
                    order_id = order_result["order_id"]
                    order_ids.append(order_id)
                    successful_orders += 1
                    
                    actual_price = order_result.get("price")
                    if actual_price:
                        executed_prices[order_id] = actual_price  # Store actual entry price
                        logger.info(
                            "order_executed",
                            symbol=signal.symbol,
                            intended_entry=signal.entry_price,
                            actual_entry=actual_price,
                            take_profit=tp.price,
                            order_id=order_id,
                            slippage=actual_price - signal.entry_price if signal.direction == SignalDirection.BUY else signal.entry_price - actual_price
                        )
                else:
                    logger.error(
                        "order_failed",
                        symbol=signal.symbol,
                        take_profit=tp.price,
                        error=order_result.get("error", "Unknown error")
                    )
            
            # Record the trades in active_trades
            if order_ids:
                self._active_trades[signal.symbol] = {
                    "order_ids": order_ids,  # Store all order IDs
                    "symbol": signal.symbol,
                    "direction": signal.direction,
                    "intended_entry": signal.entry_price,
                    "actual_entries": executed_prices,  # Store mapping of order_id to actual entry price
                    "stop_loss": signal.stop_loss,
                    "take_profits": signal.take_profits,
                    "position_size": per_position_size * len(signal.take_profits),  # Total size
                    "timestamp": datetime.now(),
                    "simulation": False
                }

            
            # Return success if at least one order was placed
            if successful_orders > 0:
                return TradeResult(
                    success=True,
                    order_id=order_ids[0],  # Return first order ID for compatibility
                    simulation=False
                )
            else:
                return TradeResult(
                    success=False,
                    error="Failed to place any orders",
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