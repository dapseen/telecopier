#!/usr/bin/env python3
"""
GoldMirror: Telegram to MT5 Signal Automation
Main application entry point.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

import structlog
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, validator

from telegram import (
    SignalMonitor,
    SignalParser,
    SignalValidator,
    SignalQueue,
    SignalPriority,
    TradingSignal
)
from mt5 import MT5Connection, TradeExecutor, MT5Config
from mt5.position_manager import RiskConfig as PositionRiskConfig  # Renamed to avoid confusion

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

class TradingSession(BaseModel):
    """Trading session configuration."""
    name: str
    start_time: str
    end_time: str
    symbols: List[str]
    timezone: str
    is_24_7: bool = False

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time format (HH:MM).
        
        Args:
            v: Time string to validate
            
        Returns:
            str: Validated time string
            
        Raises:
            ValueError: If time format is invalid
        """
        try:
            hours, minutes = map(int, v.split(":"))
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError("Time must be in HH:MM format")
        return v

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: List[str]) -> List[str]:
        """Validate trading symbols.
        
        Args:
            v: List of symbol strings
            
        Returns:
            List[str]: Validated list of symbols
            
        Raises:
            ValueError: If symbols are invalid
        """
        if not v:
            raise ValueError("symbols cannot be empty")
        if not all(isinstance(symbol, str) and symbol for symbol in v):
            raise ValueError("symbols must be non-empty strings")
        if len(set(v)) != len(v):
            raise ValueError("symbols must be unique")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone string.
        
        Args:
            v: Timezone string to validate
            
        Returns:
            str: Validated timezone string
            
        Raises:
            ValueError: If timezone is invalid
        """
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(v)
        except Exception:
            raise ValueError(f"Invalid timezone: {v}")
        return v

class PositionConfig(BaseModel):
    """Position management configuration."""
    breakeven: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "trigger_tp": 1,  # Move to breakeven after TP1
            "offset": 1  # Points above entry
        }
    )
    partial_close: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "levels": [0.25, 0.25, 0.25, 0.25]  # Split position into 4 equal parts
        }
    )

    @field_validator("breakeven")
    @classmethod
    def validate_breakeven(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate breakeven configuration.
        
        Args:
            v: Breakeven configuration dictionary
            
        Returns:
            Dict[str, Any]: Validated breakeven configuration
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not isinstance(v.get("enabled"), bool):
            raise ValueError("breakeven.enabled must be a boolean")
        if not isinstance(v.get("trigger_tp"), int) or v["trigger_tp"] < 1:
            raise ValueError("breakeven.trigger_tp must be a positive integer")
        if not isinstance(v.get("offset"), (int, float)) or v["offset"] < 0:
            raise ValueError("breakeven.offset must be a non-negative number")
        return v

    @field_validator("partial_close")
    @classmethod
    def validate_partial_close(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate partial close configuration.
        
        Args:
            v: Partial close configuration dictionary
            
        Returns:
            Dict[str, Any]: Validated partial close configuration
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not isinstance(v.get("enabled"), bool):
            raise ValueError("partial_close.enabled must be a boolean")
        if not isinstance(v.get("levels"), list):
            raise ValueError("partial_close.levels must be a list")
        if not all(isinstance(x, (int, float)) and 0 < x <= 1 for x in v["levels"]):
            raise ValueError("partial_close.levels must be numbers between 0 and 1")
        if abs(sum(v["levels"]) - 1.0) > 0.0001:  # Allow for floating point imprecision
            raise ValueError("partial_close.levels must sum to 1.0")
        return v

class NewsFilterConfig(BaseModel):
    """News filter configuration."""
    buffer_minutes: int = Field(gt=0)
    affected_symbols: Dict[str, List[str]]

class SignalConfig(BaseModel):
    """Signal validation configuration."""
    confidence_threshold: float = Field(ge=0, le=1)
    max_signal_age: int = Field(gt=0)
    required_fields: List[str] = Field(
        default=[
            "direction",
            "symbol",
            "entry",
            "sl",
            "tp1",
            "tp2",
            "tp3",
            "tp4"
        ]
    )

    @field_validator("required_fields")
    @classmethod
    def validate_required_fields(cls, v: List[str]) -> List[str]:
        """Validate required fields configuration.
        
        Args:
            v: List of required field names
            
        Returns:
            List[str]: Validated list of required fields
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not v:
            raise ValueError("required_fields cannot be empty")
        if not all(isinstance(field, str) for field in v):
            raise ValueError("required_fields must be strings")
        if len(set(v)) != len(v):
            raise ValueError("required_fields must be unique")
        return v

class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str
    format: str
    file: Dict[str, Any]
    telegram: Dict[str, Any]

    @field_validator("level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate logging level.
        
        Args:
            v: The log level value to validate
            
        Returns:
            str: The validated and normalized log level
            
        Raises:
            ValueError: If the log level is invalid
        """
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {', '.join(valid_levels)}")
        return v.upper()

class AnalyticsConfig(BaseModel):
    """Analytics configuration."""
    enabled: bool
    metrics: List[str]
    dashboard: Dict[str, Any]

class RiskConfig(BaseModel):
    """Risk management configuration from config.yaml."""
    # Position Sizing
    risk_per_trade_pct: float = Field(gt=0, le=1)
    max_position_size_pct: float = Field(gt=0, le=1)
    max_open_positions: int = Field(gt=0)
    
    # Loss Limits
    max_daily_loss_pct: float = Field(gt=0, le=1)
    daily_loss_limit: float = Field(gt=0)
    min_account_balance: float = Field(gt=0)
    
    # Trade Management
    cooldown_after_loss: int = Field(gt=0)
    max_slippage: int = Field(gt=0)

    def to_position_risk_config(self, account_balance: float) -> PositionRiskConfig:
        """Convert to PositionManager RiskConfig.
        
        Args:
            account_balance: Current account balance
            
        Returns:
            PositionRiskConfig: Risk configuration for position management
        """
        return PositionRiskConfig(
            account_balance=account_balance,
            risk_per_trade=self.risk_per_trade_pct * 100,  # Convert to percentage
            max_open_trades=self.max_open_positions,
            max_daily_loss=self.max_daily_loss_pct * 100,  # Convert to percentage
            max_symbol_risk=self.max_position_size_pct * 100,  # Convert to percentage
            daily_loss_limit=self.daily_loss_limit,
            cooldown_after_loss=self.cooldown_after_loss,
            max_slippage=self.max_slippage,
            position_sizing="risk_based"  # Default to risk-based position sizing
        )

class MT5Config(BaseModel):
    """MT5 configuration.
    
    Note: server, login, and password are loaded from environment variables:
    - MT5_SERVER: Your broker's MT5 server address
    - MT5_LOGIN: Your MT5 account number
    - MT5_PASSWORD: Your MT5 account password
    """
    server: Optional[str] = None  # Loaded from MT5_SERVER env var
    timezone: str = "UTC"
    timeout_ms: int = Field(default=60000, gt=0)
    retry_delay_seconds: int = Field(default=5, gt=0)
    max_retries: int = Field(default=3, gt=0)
    health_check_interval_seconds: int = Field(default=30, gt=0)
    login: Optional[int] = None  # Loaded from MT5_LOGIN env var
    password: Optional[str] = None  # Loaded from MT5_PASSWORD env var

    @classmethod
    def from_environment(cls) -> "MT5Config":
        """Create MT5Config from environment variables.
        
        Returns:
            MT5Config: Configuration loaded from environment variables
            
        Raises:
            ValueError: If required environment variables are missing
        """
        # Get required values
        server = os.getenv("MT5_SERVER")
        if not server:
            raise ValueError("MT5_SERVER environment variable is required")
            
        login = os.getenv("MT5_LOGIN")
        if not login:
            raise ValueError("MT5_LOGIN environment variable is required")
            
        password = os.getenv("MT5_PASSWORD")
        if not password:
            raise ValueError("MT5_PASSWORD environment variable is required")
            
        # Create config with environment values
        return cls(
            server=server,
            login=int(login),
            password=password,
            timeout_ms=int(os.getenv("MT5_TIMEOUT_MS", "60000")),
            retry_delay_seconds=int(os.getenv("MT5_RETRY_DELAY_SECONDS", "5")),
            max_retries=int(os.getenv("MT5_MAX_RETRIES", "3")),
            health_check_interval_seconds=int(os.getenv("MT5_HEALTH_CHECK_INTERVAL_SECONDS", "30"))
        )

    def __init__(self, **data):
        """Initialize with provided data."""
        super().__init__(**data)
        # Always load sensitive data from environment
        self.server = os.getenv("MT5_SERVER")
        self.login = int(os.getenv("MT5_LOGIN", "0"))
        self.password = os.getenv("MT5_PASSWORD", "")

class AppConfig(BaseModel):
    """Main application configuration."""
    trading_sessions: List[TradingSession]
    position: PositionConfig
    news_filter: NewsFilterConfig
    signal: SignalConfig
    logging: LoggingConfig
    analytics: AnalyticsConfig
    mt5: MT5Config
    risk: RiskConfig  # This now contains all trading parameters

    def __init__(self, **data):
        """Initialize config with environment variables for MT5 credentials."""
        super().__init__(**data)
        # Override MT5 credentials from environment variables
        self.mt5.login = int(os.getenv("MT5_LOGIN", "0"))
        self.mt5.password = os.getenv("MT5_PASSWORD", "")

class GoldMirror:
    """Main application class for GoldMirror trading automation.
    
    This class orchestrates all components of the trading system:
    - Configuration management
    - Telegram signal monitoring
    - MT5 trade execution
    - Risk management
    - Logging and analytics
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize GoldMirror application.

        Args:
            config_path: Optional path to config file. If not provided, will use default.
        """
        self.config = self._load_config(config_path)
        self._setup_logging()

        # Extract valid symbols from trading sessions
        valid_symbols = set()
        for session in self.config.trading_sessions:
            valid_symbols.update(session.symbols)

        # Initialize components
        self.telegram_client: Optional[SignalMonitor] = None
        self.signal_parser = SignalParser(valid_symbols=valid_symbols)
        self.signal_validator = SignalValidator(
            max_signal_age_minutes=self.config.signal.max_signal_age,
            duplicate_window_minutes=30,  # Default value
            cache_size=100,  # Default value
            mt5_connection=None  # Will be set after MT5 connection is established
        )
        self.signal_queue = SignalQueue(
            max_queue_size=1000,  # Default value
            max_retries=self.config.signal.max_retries if hasattr(self.config.signal, 'max_retries') else 3,
            retry_delay_minutes=5,  # Default value
            signal_expiry_minutes=30  # Default value
        )
        self.mt5_connection: Optional[MT5Connection] = None
        self.trade_executor: Optional[TradeExecutor] = None
        
    async def start(self) -> None:
        """Start the GoldMirror trading system.
        
        This method:
        1. Initializes MT5 connection
        2. Sets up trade executor
        3. Starts Telegram client
        4. Begins signal processing
        """
        try:
            # Initialize MT5 connection using the imported MT5Config
            try:
                mt5_config = MT5Config.from_environment()
                logger.info(
                    "loaded_mt5_config",
                    server=mt5_config.server,
                    login=mt5_config.login,
                    timeout_ms=mt5_config.timeout_ms
                )
            except ValueError as e:
                logger.error("mt5_config_error", error=str(e))
                raise RuntimeError(f"MT5 configuration error: {str(e)}")
            
            self.mt5_connection = MT5Connection(mt5_config)
            
            # Connect to MT5
            logger.info("connecting_to_mt5")
            if not await self.mt5_connection.connect():
                logger.error("failed_to_connect_to_mt5")
                raise RuntimeError("Failed to connect to MT5")
            
            logger.info("connected_to_mt5")
            
            if self.mt5_connection.is_simulation_mode:
                logger.warning("running_in_simulation_mode")
                self._setup_simulation_mode()
            else:
                await self._setup_trading_mode()
            
            # Initialize Telegram client
            self._setup_telegram()
            
            # Start the main event loop
            await self._run_event_loop()
            
        except Exception as e:
            logger.error("startup_failed", error=str(e), exc_info=True)
            raise
            
    def _setup_simulation_mode(self) -> None:
        """Set up components for simulation mode."""
        logger.info("setting_up_simulation_mode")
        
        # Use default account balance for simulation
        account_balance = 10000.0
        
        # Initialize simulation components
        self.trade_executor = TradeExecutor(
            connection=self.mt5_connection,
            risk_config=self.config.risk.to_position_risk_config(account_balance),
            simulation_mode=True
        )
        
        # Initialize signal validator with simulation symbols
        self.signal_validator = SignalValidator(
            max_signal_age_minutes=self.config.signal.max_signal_age,
            duplicate_window_minutes=30,  # Default value
            cache_size=100,  # Default value
            mt5_connection=self.mt5_connection
        )
        
        # Get all symbols from trading sessions in config
        simulation_symbols = set()
        for session in self.config.trading_sessions:
            simulation_symbols.update(session.symbols)
        
        if self.mt5_connection:
            self.mt5_connection.update_available_symbols(simulation_symbols)
            logger.info(
                "simulation_symbols_updated",
                symbols=list(simulation_symbols),
                session_count=len(self.config.trading_sessions)
            )
        else:
            logger.warning(
                "mt5_connection_not_available",
                message="Running in simulation mode without MT5 connection"
            )
        
    async def _setup_trading_mode(self) -> None:
        """Set up components for real trading mode."""
        logger.info("setting_up_trading_mode")
        
        # Get account balance for risk config
        account_balance = await self.mt5_connection.get_account_balance() if self.mt5_connection else 10000.0
        
        # Initialize real trading components
        self.trade_executor = TradeExecutor(
            connection=self.mt5_connection,
            risk_config=self.config.risk.to_position_risk_config(account_balance)
        )
        
        # Initialize signal validator with real trading symbols
        self.signal_validator = SignalValidator(
            max_signal_age_minutes=self.config.signal.max_signal_age,
            duplicate_window_minutes=30,  # Default value
            cache_size=100,  # Default value
            mt5_connection=self.mt5_connection
        )
        # Update with actual available symbols from MT5
        if self.mt5_connection and self.mt5_connection.is_connected:
            self.signal_validator.update_available_symbols(
                self.mt5_connection.available_symbols
            )
        
    def _setup_telegram(self) -> None:
        """Set up Telegram client and signal processing."""
        logger.info("setting_up_telegram")
        
        # Initialize Telegram client
        self.telegram_client = SignalMonitor(
            api_id=int(os.getenv("TELEGRAM_API_ID", "0")),
            api_hash=os.getenv("TELEGRAM_API_HASH", ""),
            channel_id=os.getenv("TELEGRAM_CHANNEL_ID", ""),
            message_callback=self._handle_telegram_message
        )
        
    async def _handle_telegram_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming Telegram message.
        
        Args:
            message: The received message data dictionary containing:
                - message_id: Unique message ID
                - chat_id: Chat/channel ID
                - text: Message text content
                - date: Message timestamp
                - edit_date: Last edit timestamp (if edited)
        """
        try:
            # Extract message text
            message_text = message.get("text", "")
            if not message_text:
                logger.debug("empty_message_received", message_id=message.get("message_id"))
                return
                
            # Parse signal
            signal = self.signal_parser.parse(message_text)
            if not signal:
                logger.debug(
                    "no_signal_parsed",
                    message_id=message.get("message_id"),
                    message_text=message_text[:100]  # Log first 100 chars
                )
                return
                
            # Log successful parse
            logger.info(
                "signal_parsed",
                symbol=signal.symbol,
                direction=signal.direction,
                entry_price=signal.entry_price,
                confidence=signal.confidence_score,
                message_id=message.get("message_id")
            )
                
            # Validate signal
            validation_result = self.signal_validator.validate_signal(signal)
            if not validation_result.is_valid:
                logger.warning(
                    "invalid_signal",
                    symbol=signal.symbol,
                    reason=validation_result.reason,
                    details=validation_result.details,
                    message_id=message.get("message_id")
                )
                return
                
            # Log successful validation
            logger.info(
                "signal_validated",
                symbol=signal.symbol,
                confidence=signal.confidence_score,
                validation_details=validation_result.details,
                message_id=message.get("message_id")
            )
                
            # Queue signal for processing
            queue_success = await self.signal_queue.enqueue(
                signal=signal,
                priority=SignalPriority.HIGH if signal.confidence_score > 0.8 else SignalPriority.NORMAL,
                validation_result=validation_result
            )
            
            if not queue_success:
                logger.warning(
                    "signal_queue_full",
                    symbol=signal.symbol,
                    message_id=message.get("message_id")
                )
                return
                
            # Log successful queuing
            logger.info(
                "signal_queued",
                symbol=signal.symbol,
                priority=SignalPriority.HIGH if signal.confidence_score > 0.8 else SignalPriority.NORMAL,
                queue_stats=self.signal_queue.get_queue_stats(),
                message_id=message.get("message_id")
            )
            
            # Process signal if executor is available
            if self.trade_executor:
                try:
                    result = await self.trade_executor.execute_signal(signal)
                    if result.success:
                        logger.info(
                            "signal_executed",
                            symbol=signal.symbol,
                            direction=signal.direction,
                                order_id=result.order_id,
                                simulation=result.simulation,
                                message_id=message.get("message_id")
                            )
                    else:
                        logger.error(
                            "signal_execution_failed",
                            symbol=signal.symbol,
                            error=result.error,
                            simulation=result.simulation,
                        message_id=message.get("message_id")
                    )
                except Exception as e:
                    logger.error(
                        "signal_execution_error",
                        symbol=signal.symbol,
                        error=str(e),
                        message_id=message.get("message_id")
                    )
                
        except Exception as e:
            logger.error(
                "message_handling_failed",
                error=str(e),
                message_id=message.get("message_id"),
                message_text=message.get("text", "")[:100]  # Log first 100 chars
            )
            
    async def _run_event_loop(self) -> None:
        """Run the main event loop."""
        try:
            # Start Telegram client
            if self.telegram_client:
                await self.telegram_client.connect()
                logger.info("telegram_client_connected")
                
            # Keep the event loop running
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("shutting_down")
            if self.telegram_client:
                await self.telegram_client.disconnect()
                logger.info("telegram_client_disconnected")
        except Exception as e:
            logger.error("event_loop_error", error=str(e))
            if self.telegram_client and self.telegram_client.is_connected:
                await self.telegram_client.disconnect()
            raise

    def _load_config(self, config_path: Optional[str] = None) -> AppConfig:
        """Load and validate configuration from YAML file.

        Returns:
            AppConfig: Validated configuration object.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            yaml.YAMLError: If config file is invalid.
            ValidationError: If config values are invalid.
        """
        try:
            with open(config_path or os.getenv("GOLDMIRROR_CONFIG", "config/config.yaml"), "r") as f:
                raw_config = yaml.safe_load(f)
                
            # Validate and convert to Pydantic model
            config = AppConfig(**raw_config)
            logger.info("config_loaded", path=config_path or os.getenv("GOLDMIRROR_CONFIG", "config/config.yaml"))
            return config
            
        except FileNotFoundError:
            logger.error("config_file_not_found", path=config_path or os.getenv("GOLDMIRROR_CONFIG", "config/config.yaml"))
            raise
        except yaml.YAMLError as e:
            logger.error("invalid_config_file", error=str(e))
            raise
        except Exception as e:
            logger.error("config_validation_error", error=str(e))
            raise

    def _setup_logging(self) -> None:
        """Configure logging based on config settings."""
        log_config = self.config.logging
        log_level = getattr(logging, log_config.level)
        
        # Create logs directory if it doesn't exist
        log_path = Path(log_config.file["path"])
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Configure file handler if enabled
        if log_config.file["enabled"]:
            file_handler = logging.FileHandler(log_path)
            file_handler.setLevel(log_level)
            logging.getLogger().addHandler(file_handler)

        logger.info("logging_configured", level=log_config.level)

    async def clear_cache(self) -> None:
        """Clear all system caches.
        
        This method clears:
        - Signal validator cache (duplicate detection)
        - Signal queue cache
        - MT5 connection cache (available symbols)
        """
        logger.info("clearing_system_caches")
        
        # Clear signal validator cache
        if self.signal_validator:
            self.signal_validator.clear_cache()
            logger.info("signal_validator_cache_cleared")
            
        # Clear signal queue
        if self.signal_queue:
            await self.signal_queue.clear()
            logger.info("signal_queue_cleared")
            
        # Clear MT5 connection cache
        if self.mt5_connection:
            await self.mt5_connection.clear_cache()
            logger.info("mt5_connection_cache_cleared")
            
        logger.info("all_caches_cleared")

async def main() -> None:
    """Application entry point."""
    # Load environment variables
    load_dotenv()
    
    # Create and start application
    app = GoldMirror()
    
    # Add command line argument handling
    if len(sys.argv) > 1 and sys.argv[1] == "--clear-cache":
        await app.clear_cache()
        logger.info("caches_cleared_exiting")
        return
        
    await app.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
    except Exception as e:
        logger.error("fatal_error", error=str(e))
        raise 