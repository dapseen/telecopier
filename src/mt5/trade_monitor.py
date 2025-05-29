"""Trade monitoring module.

This module implements the TradeMonitor class which handles:
- Monitoring active trades in MT5
- Updating trade statuses in Redis
- Cleaning up closed trades
"""

import asyncio
from typing import Optional
import structlog
from .redis_manager import RedisTradeManager
from .connection import MT5Connection

logger = structlog.get_logger(__name__)

class TradeMonitor:
    """Monitors active trades and updates their status."""
    
    def __init__(
        self,
        redis_manager: RedisTradeManager,
        mt5_connection: MT5Connection,
        check_interval: float = 20.0
    ):
        """Initialize trade monitor.
        
        Args:
            redis_manager: Redis trade manager instance
            mt5_connection: MT5 connection instance
            check_interval: Interval in seconds between trade checks
        """
        self.redis_manager = redis_manager
        self.mt5_connection = mt5_connection
        self.check_interval = check_interval
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start monitoring trades."""
        if self.running:
            logger.warning("trade_monitor_already_running")
            return
            
        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("trade_monitor_started", check_interval=self.check_interval)
        
    async def stop(self):
        """Stop monitoring trades."""
        if not self.running:
            return
            
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            
        logger.info("trade_monitor_stopped")
        
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                await self.check_trades()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error("trade_monitor_error", error=str(e))
                await asyncio.sleep(self.check_interval)
                
    async def check_trades(self):
        """Check status of all active trades."""
        try:
            active_trades = await self.redis_manager.check_active_trades()
            logger.debug("Retrieved active trades", count=len(active_trades))
            
            for trade in active_trades:
                current_symbol = None  # Initialize at trade level
                try:
                    # Validate trade data first
                    if not isinstance(trade, dict):
                        logger.error("invalid_trade_type", trade_type=type(trade))
                        continue
                        
                    if "symbol" not in trade:
                        logger.error("missing_symbol_in_trade", trade_keys=list(trade.keys()))
                        continue
                    
                    current_symbol = trade["symbol"]
                    logger.debug("Processing trade", symbol=current_symbol)
                    
                    if "orders" not in trade:
                        logger.error("missing_orders_in_trade", symbol=current_symbol)
                        continue
                        
                    if not isinstance(trade["orders"], list):
                        logger.error("invalid_orders_type", symbol=current_symbol, type=type(trade["orders"]))
                        continue

                    logger.debug("Trade orders", symbol=current_symbol, orders=trade["orders"])
                    
                    all_closed = True
                    had_errors = False
                    
                    # Process each order
                    for order in trade["orders"]:
                        try:
                            # Validate order data
                            if not isinstance(order, dict):
                                logger.error(
                                    "invalid_order_type", 
                                    symbol=current_symbol,
                                    type=type(order)
                                )
                                had_errors = True
                                continue
                                
                            if not all(k in order for k in ["order_id", "status"]):
                                logger.error(
                                    "missing_order_fields", 
                                    symbol=current_symbol,
                                    available_fields=list(order.keys())
                                )
                                had_errors = True
                                continue
                                
                            order_id = int(order["order_id"])
                            current_status = order["status"]
                            
                            if current_status != "CLOSED":
                                # Only pass the order_id/ticket
                                mt5_position = await self.mt5_connection.get_positions(ticket=order_id)
                                
                                if not mt5_position:
                                    logger.debug(
                                        "Updating order status to CLOSED",
                                        symbol=current_symbol,
                                        order_id=order_id
                                    )
                                    await self.redis_manager.update_order_status(order_id, "CLOSED")
                                    logger.info(
                                        "position_closed",
                                        symbol=current_symbol,
                                        order_id=order_id
                                    )
                                else:
                                    all_closed = False
                                    logger.debug(
                                        "Order still active",
                                        symbol=current_symbol,
                                        order_id=order_id
                                    )
                                    
                        except Exception as order_error:
                            logger.error(
                                "order_processing_error",
                                error=str(order_error),
                                symbol=current_symbol,  # Use current_symbol consistently
                                order_id=order.get("order_id", "unknown")
                            )
                            had_errors = True
                            continue
                    
                    # Decision to remove trade
                    if all_closed and not had_errors:
                        logger.debug(
                            "Removing closed trade",
                            symbol=current_symbol,
                            all_closed=all_closed,
                            had_errors=had_errors
                        )
                        await self.redis_manager.remove_closed_trade(current_symbol)
                        logger.info(
                            "trade_completed",
                            symbol=current_symbol
                        )
                    else:
                        logger.debug(
                            "Trade not removed",
                            symbol=current_symbol,
                            all_closed=all_closed,
                            had_errors=had_errors,
                            reason="Errors occurred or orders still active"
                        )
                    
                except Exception as trade_error:
                    logger.error(
                        "trade_processing_error",
                        error=str(trade_error),
                        symbol=trade.get("symbol", "unknown"),
                        trade_data=trade
                    )
                    continue
                
        except Exception as e:
            logger.error(
                "check_trades_error", 
                error=str(e),
                error_type=type(e).__name__
            ) 