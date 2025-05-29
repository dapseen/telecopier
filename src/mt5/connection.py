"""MT5 connection management module.

This module implements the MT5Connection class which handles:
- Secure connection to MetaTrader 5
- Connection monitoring and health checks
- Automatic reconnection
- Session management
"""

import os
import platform
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
import asyncio
import time

import structlog
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .mt5_utils import get_mt5, is_mt5_available, is_platform_supported
from src.common.types import OrderType, TradeState

logger = structlog.get_logger(__name__)

class MT5Config(BaseModel):
    """Configuration for MT5 connection.""" 
    server: str = Field(..., description="MT5 server address")
    login: int = Field(..., description="MT5 account login number")
    password: str = Field(..., description="MT5 account password")
    timezone: str = Field(default="UTC", description="Timezone for MT5 operations")
    timeout_ms: int = Field(default=60000, gt=0, description="Connection timeout in milliseconds")
    retry_delay_seconds: int = Field(default=5, gt=0, description="Delay between reconnection attempts")
    max_retries: int = Field(default=3, gt=0, description="Maximum number of reconnection attempts")
    health_check_interval_seconds: int = Field(default=30, gt=0, description="Interval between health checks")

    @classmethod
    def from_environment(cls) -> "MT5Config":
        """Create MT5Config from environment variables.
        
        Required environment variables:
        - MT5_SERVER: MT5 server address
        - MT5_LOGIN: MT5 account login number
        - MT5_PASSWORD: MT5 account password
        
        Optional environment variables:
        - MT5_TIMEOUT_MS: Connection timeout in milliseconds (default: 60000)
        - MT5_RETRY_DELAY: Delay between reconnection attempts in seconds (default: 5)
        - MT5_MAX_RETRIES: Maximum number of reconnection attempts (default: 3)
        - MT5_HEALTH_CHECK_INTERVAL: Interval between health checks in seconds (default: 30)
        - MT5_TIMEZONE: Timezone for MT5 operations (default: UTC)
        
        Returns:
            MT5Config instance with values from environment variables
            
        Raises:
            ValueError: If required environment variables are missing
        """
        required_vars = {
            "MT5_SERVER": "server",
            "MT5_LOGIN": "login",
            "MT5_PASSWORD": "password"
        }
        
        # Check for required variables
        missing_vars = [var for var in required_vars if var not in os.environ]
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )
            
        # Get required values
        config_data = {
            "server": os.environ["MT5_SERVER"],
            "login": int(os.environ["MT5_LOGIN"]),
            "password": os.environ["MT5_PASSWORD"]
        }
        
        # Get optional values with defaults
        optional_vars = {
            "MT5_TIMEOUT_MS": ("timeout_ms", int),
            "MT5_RETRY_DELAY": ("retry_delay_seconds", int),
            "MT5_MAX_RETRIES": ("max_retries", int),
            "MT5_HEALTH_CHECK_INTERVAL": ("health_check_interval_seconds", int),
            "MT5_TIMEZONE": ("timezone", str)
        }
        
        for env_var, (field, type_) in optional_vars.items():
            if env_var in os.environ:
                config_data[field] = type_(os.environ[env_var])
                
        return cls(**config_data)

class MT5Connection:
    """Manages connection to MetaTrader 5 terminal.
    
    This class handles the connection to MT5, including:
    - Secure login with credentials
    - Connection monitorls -aing
    - Automatic reconnection
    - Session management
    """
    
    def __init__(self, config: MT5Config):
        """Initialize MT5 connection manager.
        
        Args:
            config: MT5 configuration
        """
        self.mt5 = get_mt5()
        self._simulation_mode = not is_mt5_available()
        
        if self._simulation_mode:
            if is_platform_supported():
                logger.warning("mt5_not_installed")
            else:
                logger.warning("mt5_not_supported", platform=platform.system())
            
        self.config = config
        self._connected = False
        self._last_health_check = datetime.now()
        self._connection_attempts = 0
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        self._available_symbols: Set[str] = set()
        
    @staticmethod
    def _load_config() -> MT5Config:
        """Load MT5 configuration from environment variables.
        
        Returns:
            MT5Config object with connection settings
            
        Raises:
            ValueError: If required environment variables are missing
        """
        load_dotenv()
        
        required_vars = {
            "MT5_SERVER": os.getenv("MT5_SERVER"),
            "MT5_LOGIN": os.getenv("MT5_LOGIN"),
            "MT5_PASSWORD": os.getenv("MT5_PASSWORD")
        }
        
        missing = [var for var, value in required_vars.items() if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
            
        return MT5Config(
            server=required_vars["MT5_SERVER"],
            login=int(required_vars["MT5_LOGIN"]),
            password=required_vars["MT5_PASSWORD"]
        )
        
    async def connect(self) -> bool:
        """Establish connection to MT5 terminal.
        
        Returns:
            bool indicating if connection was successful
        """
        async with self._lock:
            if self._connected:
                return True
                
            try:
                # Initialize MT5
                if not self.mt5.initialize():
                    logger.error(
                        "mt5_initialize_failed",
                        error=self.mt5.last_error()
                    )
                    return False
                    
                # Attempt login
                if not self.mt5.login(
                    login=self.config.login,
                    password=self.config.password,
                    server=self.config.server,
                    timeout=self.config.timeout_ms
                ):
                    logger.error(
                        "mt5_login_failed",
                        error=self.mt5.last_error()
                    )
                    return False
                    
                self._connected = True
                self._connection_attempts = 0
                
                # Update available symbols
                await self._update_available_symbols()
                
                # Start health check task
                self._health_check_task = asyncio.create_task(self._health_check_loop())
                
                logger.info(
                    "mt5_connected",
                    server=self.config.server,
                    login=self.config.login
                )
                
                return True
                
            except Exception as e:
                logger.error(
                    "mt5_connection_error",
                    error=str(e)
                )
                return False
                
    async def disconnect(self) -> None:
        """Disconnect from MT5 terminal."""
        async with self._lock:
            if not self._connected:
                return
                
            # Stop health check task
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
                    
            # Shutdown MT5
            self.mt5.shutdown()
            self._connected = False
            
            logger.info("mt5_disconnected")
            
    async def _health_check_loop(self) -> None:
        """Monitor connection health and handle reconnection."""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval_seconds)
                
                if not await self._check_connection():
                    logger.warning("mt5_connection_lost")
                    await self._reconnect()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "health_check_error",
                    error=str(e)
                )
                
    async def _check_connection(self) -> bool:
        """Check if MT5 connection is healthy.
        
        Returns:
            bool indicating if connection is healthy
        """
        try:
            # Check if MT5 is still connected
            if not self.mt5.terminal_info():
                return False
                
            # Try a simple operation
            if not self.mt5.symbols_total():
                return False
                
            self._last_health_check = datetime.now()
            return True
            
        except Exception as e:
            logger.error(
                "connection_check_error",
                error=str(e)
            )
            return False
            
    async def _reconnect(self) -> bool:
        """Attempt to reconnect to MT5.
        
        Returns:
            bool indicating if reconnection was successful
        """
        async with self._lock:
            if self._connection_attempts >= self.config.max_retries:
                logger.error(
                    "max_reconnection_attempts",
                    attempts=self._connection_attempts
                )
                return False
                
            self._connection_attempts += 1
            
            # Disconnect first
            self.mt5.shutdown()
            self._connected = False
            
            # Wait before retrying
            await asyncio.sleep(self.config.retry_delay_seconds)
            
            # Attempt reconnection
            success = await self.connect()
            if success:
                logger.info(
                    "mt5_reconnected",
                    attempt=self._connection_attempts
                )
            else:
                logger.error(
                    "mt5_reconnection_failed",
                    attempt=self._connection_attempts
                )
                
            return success
            
    async def _update_available_symbols(self) -> None:
        """Update the list of available trading symbols."""
        try:
            symbols = self.mt5.symbols_get()
            if symbols:
                self._available_symbols = {symbol.name for symbol in symbols}
                logger.info(
                    "updated_available_symbols",
                    count=len(self._available_symbols)
                )
        except Exception as e:
            logger.error(
                "update_symbols_error",
                error=str(e)
            )
            
    @property
    def is_connected(self) -> bool:
        """Check if connected to MT5.
        
        Returns:
            bool indicating if connected
        """
        return self._connected
        
    @property
    def available_symbols(self) -> Set[str]:
        """Get list of available trading symbols.
        
        Returns:
            Set of available symbol names
        """
        return self._available_symbols.copy()
        
    def is_symbol_available(self, symbol: str) -> bool:
        """Check if a symbol is available for trading.
        
        Args:
            symbol: Symbol to check (e.g., "XAUUSD")
            
        Returns:
            bool indicating if symbol is available
        """
        symbol = symbol.upper()
        
        # In simulation mode, check against available_symbols set
        if self._simulation_mode:
            return symbol in self._available_symbols
            
        # For real trading, check connection and available symbols
        if not self._connected:
            logger.warning("checking_symbol_availability_not_connected")
            return False
            
        return symbol in self._available_symbols

    def update_available_symbols(self, symbols: Set[str]) -> None:
        """Update the list of available trading symbols.
        
        Args:
            symbols: Set of available trading symbols
        """
        self._available_symbols = {symbol.upper() for symbol in symbols}
        logger.info(
            "updated_available_symbols",
            count=len(self._available_symbols)
        )

    def get_connection_info(self) -> Dict[str, any]:
        """Get current connection information.
        
        Returns:
            Dictionary containing connection details
        """
        if not self._connected:
            return {
                "connected": False,
                "last_health_check": None,
                "connection_attempts": self._connection_attempts
            }
            
        try:
            terminal_info = self.mt5.terminal_info()
            account_info = self.mt5.account_info()
            
            return {
                "connected": True,
                "server": self.config.server,
                "login": self.config.login,
                "last_health_check": self._last_health_check.isoformat(),
                "connection_attempts": self._connection_attempts,
                "terminal": {
                    "connected": terminal_info.connected,
                    "trade_allowed": terminal_info.trade_allowed,
                    "balance": account_info.balance if account_info else None,
                    "equity": account_info.equity if account_info else None
                }
            }
        except Exception as e:
            logger.error(
                "get_connection_info_error",
                error=str(e)
            )
            return {
                "connected": False,
                "error": str(e)
            }

    @property
    def is_simulation_mode(self) -> bool:
        """Check if running in simulation mode.
        
        Returns:
            bool: True if in simulation mode, False otherwise
        """
        return self._simulation_mode 

    async def get_account_balance(self) -> Optional[float]:
        """Get current account balance.
        
        Returns:
            Optional[float]: Account balance if available, None otherwise
        """
        if not self._connected:
            logger.warning("getting_balance_not_connected")
            return None
            
        try:
            account_info = self.mt5.account_info()
            if not account_info:
                logger.error("account_info_not_found")
                return None
                
            logger.debug(
                "account_balance_retrieved",
                balance=account_info.balance,
                equity=account_info.equity
            )
            return account_info.balance
            
        except Exception as e:
            logger.error(
                "get_account_balance_error",
                error=str(e)
            )
            return None

    async def get_positions(
        self,
        ticket: Optional[int] = None
    ) -> Optional[List[Dict]]:
        """Get open positions with optional filtering.
        
        Args:
            ticket: Optional specific position ticket number
            
        Returns:
            List of position dictionaries if successful, None if error
        """
        if not self._connected:
            logger.warning("getting_positions_not_connected")
            return None
            
        try:
            # Get positions based on provided filters
            if ticket is not None:
                positions = self.mt5.positions_get(ticket=ticket)
                
                if positions is None:
                    error = self.mt5.last_error()
                    logger.error(
                        "positions_get_failed",
                        error_code=error[0],
                        error_message=error[1]
                    )
                    return None
                
            # Convert positions to dictionaries
            positions_list = []
            for position in positions:
                position_dict = {
                    "ticket": position.ticket,
                    "time": position.time,
                    "type": position.type,
                    "magic": position.magic,
                    "identifier": position.identifier,
                    "reason": position.reason,
                    "volume": position.volume,
                    "price_open": position.price_open,
                    "sl": position.sl,
                    "tp": position.tp,
                    "price_current": position.price_current,
                    "swap": position.swap,
                    "profit": position.profit,
                    "symbol": position.symbol,
                    "comment": position.comment
                }
                positions_list.append(position_dict)
                
            logger.info(
                "positions_retrieved",
                count=len(positions_list),
                ticket=ticket
            )
            
            return positions_list
            
        except Exception as e:
            logger.error(
                "get_positions_error",
                error=str(e),
                ticket=ticket
            )
            return None

    async def clear_cache(self) -> None:
        """Clear cached data and refresh from MT5."""
        async with self._lock:
            self._available_symbols.clear()
            if self.is_connected:
                # Refresh available symbols
                symbols = self.mt5.symbols_get()
                if symbols:
                    self._available_symbols = {s.name for s in symbols}
            logger.info("mt5_connection_cache_cleared")

    async def place_order(
        self,
        symbol: str,
        order_type: str,
        direction: str,
        volume: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = "",
        magic: int = 0,
        deviation: int = 10,
        max_modify_retries: int = 3,
        modify_retry_delay: float = 1.0
    ) -> Dict[str, Any]:
        """Place a trading order."""
        if not self.is_connected:
            return {
                "success": False,
                "error": "MT5 not connected"
            }
            
        try:
            # Get current symbol info
            symbol_info = self.mt5.symbol_info(symbol)
            if not symbol_info:
                return {
                    "success": False,
                    "error": f"Symbol {symbol} not found"
                }
                
            # Get current price
            tick = self.mt5.symbol_info_tick(symbol)
            if not tick:
                return {
                    "success": False,
                    "error": "Failed to get current price"
                }

            # Log current market prices with explicit direction check
            logger.info(
                "current_market_prices",
                symbol=symbol,
                ask=tick.ask,
                bid=tick.bid,
                direction=direction.upper(),
                is_buy=direction.upper() == "BUY",
                is_sell=direction.upper() == "SELL",
                spread=tick.ask - tick.bid,
                spread_points=int((tick.ask - tick.bid) / symbol_info.point)
            )
            
            # For market orders, we'll use a two-step process
            if order_type == "MARKET":
                # Place order with SL/TP directly
                request = {
                    "action": self.mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": float(volume),  # Ensure volume is float
                    "type": self.mt5.ORDER_TYPE_BUY if direction.upper() == "BUY" else self.mt5.ORDER_TYPE_SELL,
                    "price": float(tick.ask if direction.upper() == "BUY" else tick.bid),  # Ensure price is float
                    "sl": float(stop_loss) if stop_loss is not None else None,  # Ensure SL is float
                    "tp": float(take_profit) if take_profit is not None else None,  # Ensure TP is float
                    "deviation": int(deviation),  # Ensure deviation is int
                    "magic": int(magic),  # Ensure magic is int
                    "comment": "Signal Order",  # Using simple comment format
                    "type_time": self.mt5.ORDER_TIME_GTC,
                    "type_filling": self.mt5.ORDER_FILLING_IOC,  # Using FOK for XAUUSD
                }

                # Log the request with all parameters
                logger.info(
                    "placing_market_order",
                    symbol=symbol,
                    direction=direction,
                    request_type=request["type"],
                    volume=request["volume"],
                    price=request["price"],
                    sl=request["sl"],
                    tp=request["tp"],
                    comment=request["comment"],  # Log the actual comment being sent
                    filling_type=request["type_filling"],
                    current_ask=tick.ask,
                    current_bid=tick.bid
                )

                # Send order with retry logic
                max_retries = 3
                retry_delay = 1.0
                result = None
                
                for attempt in range(max_retries):
                    # Check symbol info before sending order
                    symbol_info = self.mt5.symbol_info(symbol)
                    if symbol_info:
                        logger.info(
                            "symbol_info_before_order",
                            symbol=symbol,
                            attempt=attempt + 1
                        )

                    # Send order
                    result = self.mt5.order_send(request)
                    
                    if result is not None:
                        logger.info(
                            "order_result",
                            symbol=symbol,
                            direction=direction,
                            retcode=result.retcode if hasattr(result, 'retcode') else None,
                            comment=result.comment if hasattr(result, 'comment') else None,
                            order=result.order if hasattr(result, 'order') else None,
                            volume=result.volume if hasattr(result, 'volume') else None,
                            price=result.price if hasattr(result, 'price') else None
                        )
                        break
                    else:
                        error = self.mt5.last_error()
                        logger.error(
                            "order_send_error",
                            symbol=symbol,
                            direction=direction,
                            attempt=attempt + 1,
                            error_code=error[0] if error else None,
                            error_message=error[1] if error else None
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue

                # If all retries failed
                if result is None:
                    return {
                        "success": False,
                        "error": f"Order placement failed after {max_retries} attempts: {error}"
                    }
                
                # Check result code
                if result.retcode != self.mt5.TRADE_RETCODE_DONE:
                    return {
                        "success": False,
                        "error": f"Order failed: {result.comment} (code: {result.retcode})"
                    }
                    
                return {
                    "success": True,
                    "order_id": result.order,
                    "price": result.price,
                    "volume": result.volume
                }
            else:
                # For pending orders, proceed as before
                request = {
                    "action": self.mt5.TRADE_ACTION_PENDING,
                    "symbol": symbol,
                    "volume": volume,
                    "type": self.mt5.ORDER_TYPE_BUY if direction.upper() == "BUY" else self.mt5.ORDER_TYPE_SELL,
                    "price": price,
                    "sl": stop_loss,
                    "tp": take_profit,
                    "deviation": deviation,
                    "magic": magic,
                    "comment": comment,
                    "type_time": self.mt5.ORDER_TIME_GTC,
                    "type_filling": self.mt5.ORDER_FILLING_IOC if symbol == "XAUUSD" else self.mt5.ORDER_FILLING_FOK,
                }
                
                # Send order
                result = self.mt5.order_send(request)
                
                if result.retcode != self.mt5.TRADE_RETCODE_DONE:
                    return {
                        "success": False,
                        "error": f"Order placement failed: {result.comment} (code: {result.retcode})"
                    }
                    
                return {
                    "success": True,
                    "order_id": result.order,
                    "price": result.price
                }
                
        except Exception as e:
            logger.error(
                "order_placement_error",
                error=str(e),
                symbol=symbol,
                direction=direction
            )
            return {
                "success": False,
                "error": str(e)
            } 