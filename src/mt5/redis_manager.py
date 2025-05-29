"""Redis trade management module.

This module implements the RedisTradeManager class which handles:
- Storing trade data in Redis
- Monitoring active trades
- Updating trade statuses
- Managing trade lifecycle
"""

from redis.asyncio import Redis
from datetime import datetime, timezone
import json
from typing import Dict, List, Optional, Any
import structlog
from urllib.parse import urlparse, parse_qs
import asyncio

logger = structlog.get_logger(__name__)

class RedisConfig:
    """Redis configuration helper."""
    
    @staticmethod
    def parse_redis_url(url: str) -> Dict[str, Any]:
        """Parse Redis URL and extract configuration.
        
        Args:
            url: Redis URL with optional parameters
            
        Returns:
            Dict containing Redis connection parameters
        """
        parsed = urlparse(url)
        
        # Extract basic connection info
        config = {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 6379,
            "db": int(parsed.path.lstrip("/") or 0),
            "username": parsed.username,
            "password": parsed.password,
            "ssl": parsed.scheme == "rediss"
        }
        
        # Remove None values
        config = {k: v for k, v in config.items() if v is not None}
        
        # Parse query parameters for additional options
        if parsed.query:
            params = parse_qs(parsed.query)
            if "decode_responses" in params:
                config["decode_responses"] = params["decode_responses"][0].lower() == "true"
            if "max_connections" in params:
                config["max_connections"] = int(params["max_connections"][0])
            if "socket_timeout" in params:
                config["socket_timeout"] = float(params["socket_timeout"][0])
                
        return config

class RedisTradeManager:
    """Manages trade data persistence and monitoring in Redis."""
    
    def __init__(
        self,
        redis_url: str,
        pool_size: int = 10,
        timeout: int = 30,
        retry_interval: int = 1,
        max_retries: int = 3,
        prefix: str = "telecopier"
    ):
        """Initialize Redis trade manager.
        
        Args:
            redis_url: Redis connection URL with optional auth
            pool_size: Connection pool size
            timeout: Connection timeout in seconds
            retry_interval: Retry interval in seconds
            max_retries: Maximum number of connection retries
            prefix: Key prefix for Redis storage
        """
        self.prefix = prefix
        
        try:
            # Parse Redis URL and create connection
            redis_config = RedisConfig.parse_redis_url(redis_url)
            redis_config.update({
                "max_connections": pool_size,
                "socket_timeout": timeout,
                "retry_on_timeout": True,
                "decode_responses": True,  # Always decode responses
            })
            
            self.redis = Redis(**redis_config)
            self.pool_size = pool_size
            self.timeout = timeout
            self.retry_interval = retry_interval
            self.max_retries = max_retries
            
        except Exception as e:
            logger.error(
                "redis_initialization_failed",
                error=str(e),
                redis_url=redis_url.replace(
                    redis_config.get("password", ""),
                    "***" if redis_config.get("password") else ""
                )
            )
            raise
        
    async def initialize(self) -> bool:
        """Initialize Redis connection with retries.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                # Test connection
                await self.redis.ping()
                connection_info = self.redis.connection_pool.connection_kwargs
                logger.info(
                    "redis_connection_successful",
                    host=connection_info["host"],
                    port=connection_info["port"],
                    db=connection_info["db"],
                    ssl=connection_info.get("ssl", False)
                )
                return True
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        "redis_connection_retry",
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        error=str(e)
                    )
                    await asyncio.sleep(self.retry_interval)
                else:
                    logger.error(
                        "redis_connection_failed",
                        error=str(e)
                    )
                    raise
        return False

    async def close(self):
        """Close Redis connection."""
        try:
            await self.redis.close()
            logger.info("redis_connection_closed")
        except Exception as e:
            logger.error(
                "redis_close_failed",
                error=str(e)
            )

    async def store_trade(self, symbol: str, trade_data: Dict) -> bool:
        """Store trade data in Redis.
        
        Args:
            symbol: Trading symbol
            trade_data: Dictionary containing trade details
            
        Returns:
            bool: True if storage successful, False otherwise
        """
        try:
            # Store main trade data
            trade_key = f"{self.prefix}:active_trades:{symbol}"
            trade_data_redis = {
                "symbol": symbol,
                "direction": str(trade_data["direction"]),
                "intended_entry": str(trade_data["intended_entry"]),
                "stop_loss": str(trade_data["stop_loss"]),
                "position_size": str(trade_data["position_size"]),
                "timestamp": trade_data["timestamp"].isoformat(),
                "order_ids": json.dumps(trade_data["order_ids"]),
                "status": "ACTIVE"
            }
            
            # Store individual orders
            for order_id, entry_price in trade_data["actual_entries"].items():
                order_key = f"{self.prefix}:active_orders:{order_id}"
                take_profit = next(
                    (tp.price for tp, oid in zip(trade_data["take_profits"], trade_data["order_ids"]) 
                     if oid == order_id), 
                    None
                )
                order_data = {
                    "order_id": str(order_id),
                    "symbol": symbol,
                    "actual_entry": str(entry_price),
                    "take_profit": str(take_profit),
                    "volume": str(trade_data["position_size"] / len(trade_data["order_ids"])),
                    "status": "ACTIVE",
                    "last_checked": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.hmset(order_key, order_data)
            
            # Add to active symbols set
            await self.redis.sadd(f"{self.prefix}:active_symbols", symbol)
            
            # Store main trade data
            success = await self.redis.hmset(trade_key, trade_data_redis)
            
            logger.info(
                "trade_stored_in_redis",
                symbol=symbol,
                order_ids=trade_data["order_ids"],
                success=success
            )
            
            return success
            
        except Exception as e:
            logger.error(
                "failed_to_store_trade_in_redis",
                error=str(e),
                symbol=symbol
            )
            return False
    
    async def check_active_trades(self) -> List[Dict]:
        """Check status of all active trades.
        
        Returns:
            List[Dict]: List of active trades with their current status
        """
        active_trades = []
        try:
            # Get all active symbols
            symbols = await self.redis.smembers(f"{self.prefix}:active_symbols")
            
            for symbol in symbols:
              
                try:
                    trade_key = f"{self.prefix}:active_trades:{symbol}"
                    trade_data = await self.redis.hgetall(trade_key)
                    
                    if not trade_data:
                        logger.warning("empty_trade_data", symbol=symbol)
                        continue
                        
                    # Validate required trade data fields
                    if "order_ids" not in trade_data:
                        logger.error("missing_order_ids", symbol=symbol)
                        continue
                        
                    try:
                        order_ids = json.loads(trade_data["order_ids"])
                    except json.JSONDecodeError as e:
                        logger.error("invalid_order_ids_json", symbol=symbol, error=str(e))
                        continue
                    
                    # Check each order
                    orders_status = []
                    for order_id in order_ids:
                        try:
                            order_key = f"{self.prefix}:active_orders:{order_id}"
                            order_data = await self.redis.hgetall(order_key)

                            if order_data:
                                orders_status.append(order_data)
                            else:
                                logger.warning("missing_order_data", symbol=symbol, order_id=order_id)
                        except Exception as e:
                            logger.error("order_data_fetch_error", symbol=symbol, order_id=order_id, error=str(e))
                            continue
                    
                    trade_data["orders"] = orders_status
                    active_trades.append(trade_data)
                except Exception as e:
                    logger.error("trade_processing_error", symbol=symbol, error=str(e))
                    continue
            
            return active_trades
            
        except Exception as e:
            logger.error("failed_to_check_active_trades", error=str(e))
            return []

    async def update_order_status(self, order_id: int, status: str) -> bool:
        """Update status of an individual order.
        
        Args:
            order_id: MT5 order ID
            status: New status for the order
            
        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            order_key = f"{self.prefix}:active_orders:{order_id}"
            updates = {
                "status": status,
                "last_checked": datetime.now(timezone.utc).isoformat()
            }
            await self.redis.hmset(order_key, updates)
            
            logger.info(
                "order_status_updated",
                order_id=order_id,
                status=status
            )
            return True
            
        except Exception as e:
            logger.error(
                "failed_to_update_order_status",
                error=str(e),
                order_id=order_id
            )
            return False
            
    async def remove_closed_trade(self, symbol: str) -> bool:
        """Remove a trade and its orders when all positions are closed.
        
        Args:
            symbol: Trading symbol to remove
            
        Returns:
            bool: True if removal successful, False otherwise
        """
        try:
            trade_key = f"{self.prefix}:active_trades:{symbol}"
            trade_data = await self.redis.hgetall(trade_key)
            
            if trade_data:
                # Remove decode() since responses are already decoded due to decode_responses=True
                order_ids = json.loads(trade_data["order_ids"])
                
                # Remove all order records
                for order_id in order_ids:
                    order_key = f"{self.prefix}:active_orders:{order_id}"
                    await self.redis.delete(order_key)
                
                # Remove trade record and symbol from active set
                await self.redis.delete(trade_key)
                await self.redis.srem(f"{self.prefix}:active_symbols", symbol)
                
                logger.info(
                    "closed_trade_removed",
                    symbol=symbol,
                    order_ids=order_ids
                )
                return True
                
        except Exception as e:
            logger.error(
                "failed_to_remove_closed_trade",
                error=str(e),
                symbol=symbol
            )
            return False 