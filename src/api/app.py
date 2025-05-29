"""FastAPI application entry point.

This module initializes and configures the FastAPI application,
including middleware, routers, and dependencies.
"""

import os
from pathlib import Path
from typing import Dict, Any
import re

import structlog
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from redis.asyncio import Redis
from dotenv import load_dotenv

from src.db.connection import DatabaseConnection, init_db, get_db
from src.db.init_db import init_database
from src.db.repositories.signal import SignalRepository
from .config import AppConfig
from .routers import signals, mt5, trades
from .services.signal_service import SignalService
from .services.mt5_service import MT5Service, load_config
from .services.telegram_service import TelegramService
from src.telegram.signal_processor import SignalProcessor
from src.telegram.signal_validator import SignalValidator
from src.telegram.signal_queue import SignalQueue
from src.mt5.executor import TradeExecutor
from src.mt5.position_manager import RiskConfig
from src.mt5.redis_manager import RedisTradeManager
from src.mt5.trade_monitor import TradeMonitor

logger = structlog.get_logger(__name__)

def create_app() -> FastAPI:
    """Create and configure FastAPI application.
    
    Returns:
        FastAPI: Configured application instance
    """
    # Create FastAPI app
    app = FastAPI(
        title="GoldMirror API",
        description="API for GoldMirror trading automation",
        version="1.0.0"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Load configuration
    try:
        config_data = load_config()
        app.state.config = AppConfig(**config_data)
        logger.info("config_loaded_successfully")
    except Exception as e:
        logger.error("config_load_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load configuration: {str(e)}"
        )
        
    # Include routers
    app.include_router(signals.router, prefix="/api/signals", tags=["signals"])
    app.include_router(mt5.router, prefix="/api/mt5", tags=["mt5"])
    app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
    
    @app.on_event("startup")
    async def startup_event():
        """Initialize application on startup."""
        try:
            # Initialize database
            db = await init_database()
            app.state.db = db
            
            # Store session factory in app state
            app.state.db_session = db.async_session
            logger.info("database_initialized")
            
            # Initialize Redis connection
            redis_url = app.state.config.redis.url
            redis = Redis.from_url(redis_url, decode_responses=True)
            # Test Redis connection
            try:
                await redis.ping()
                logger.info("redis_connection_successful")
            except Exception as e:
                logger.error("redis_connection_failed", error=str(e))
                raise
                
            # Initialize Redis trade manager
            redis_manager = RedisTradeManager(
                redis_url=redis_url,
                pool_size=app.state.config.redis.pool_size,
                timeout=app.state.config.redis.timeout,
                retry_interval=app.state.config.redis.retry_interval,
                max_retries=app.state.config.redis.max_retries
            )
            app.state.redis_manager = redis_manager
            logger.info("redis_manager_initialized")
            
            # Initialize MT5 service
            mt5_service = await MT5Service.create()
            app.state.mt5_service = mt5_service
            logger.info("mt5_service_initialized")
            
            # Get account info
            account_info = await mt5_service.get_account_info()
            
            # Get risk settings from config
            risk_settings = app.state.config.risk
            
            # Initialize risk configuration from config.yaml
            risk_config = RiskConfig(
                account_balance=account_info["balance"],
                risk_per_trade=float(risk_settings.risk_per_trade_pct) * 100,
                max_open_trades=risk_settings.max_open_positions,
                max_daily_loss=float(risk_settings.max_daily_loss_pct) * 100,
                max_symbol_risk=float(risk_settings.max_position_size_pct) * 100,
                position_sizing="risk_based"
            )
            
            # Create initial session for setup
            async with db.session() as session:
                # Initialize repositories
                signal_repository = SignalRepository(session)
                
                # Initialize components for signal processing
                signal_queue = SignalQueue()
                trade_executor = TradeExecutor(
                    connection=mt5_service.connection,
                    risk_config=risk_config,
                    redis_manager=redis_manager,  # Add Redis manager to executor
                    simulation_mode=False
                )
                signal_validator = SignalValidator(
                    signal_repository=signal_repository,
                    mt5_connection=mt5_service.connection
                )
                
                # Initialize trade monitor
                trade_monitor = TradeMonitor(
                    redis_manager=redis_manager,
                    mt5_connection=mt5_service.connection,
                    check_interval=1.0  # Check every second
                )
                
                # Start trade monitor
                await trade_monitor.start()
                app.state.trade_monitor = trade_monitor
                logger.info("trade_monitor_started")
                
                # Store components in app state
                app.state.signal_queue = signal_queue
                app.state.trade_executor = trade_executor
                app.state.risk_config = risk_config
                
                # Initialize signal processor with new session factory
                signal_processor = SignalProcessor(
                    signal_queue=signal_queue,
                    trade_executor=trade_executor,
                    signal_validator=signal_validator,
                    signal_repository=signal_repository
                )
                app.state.signal_processor = signal_processor
                
                # Start signal processor
                await signal_processor.start()
                logger.info("signal_processor_started")
                
                # Initialize Telegram service with signal queue
                telegram_service = await TelegramService.create(
                    db_session=session,
                    config=app.state.config,
                    signal_queue=signal_queue
                )
                app.state.telegram_service = telegram_service
                logger.info("telegram_service_initialized")
                
                # Start signal processing
                await telegram_service.monitor.connect()
                logger.info("telegram_monitor_started")
            
        except Exception as e:
            logger.error("startup_failed", error=str(e))
            raise HTTPException(
                status_code=500,
                detail=f"Application startup failed: {str(e)}"
            )
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Clean up resources on shutdown."""
        try:
            # Stop trade monitor
            if hasattr(app.state, "trade_monitor"):
                await app.state.trade_monitor.stop()
                logger.info("trade_monitor_stopped")
            
            # Stop signal processor
            if hasattr(app.state, "signal_processor"):
                await app.state.signal_processor.stop()
                logger.info("signal_processor_stopped")
            
            # Disconnect MT5
            if hasattr(app.state, "mt5_service"):
                await app.state.mt5_service.connection.disconnect()
                logger.info("mt5_disconnected")
                
            # Stop Telegram service
            if hasattr(app.state, "telegram_service"):
                await app.state.telegram_service.stop()
                logger.info("telegram_service_stopped")
                
            # Close Redis connection
            if hasattr(app.state, "redis_manager"):
                await app.state.redis_manager.redis.close()
                logger.info("redis_connection_closed")
                
        except Exception as e:
            logger.error("shutdown_error", error=str(e))
    
    return app

def interpolate_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively interpolate environment variables in config values.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Dict with environment variables interpolated
    """
    result = {}
    
    for key, value in config.items():
        if isinstance(value, dict):
            result[key] = interpolate_env_vars(value)
        elif isinstance(value, list):
            result[key] = [
                interpolate_env_vars(item) if isinstance(item, dict) 
                else interpolate_env_var(item) if isinstance(item, str)
                else item
                for item in value
            ]
        elif isinstance(value, str):
            result[key] = interpolate_env_var(value)
        else:
            result[key] = value
            
    return result

def interpolate_env_var(value: str) -> Any:
    """Interpolate a single environment variable value.
    
    Args:
        value: String potentially containing environment variables
        
    Returns:
        Interpolated value with correct type
    """
    if not isinstance(value, str):
        return value
        
    # Match ${VAR_NAME:-default} or ${VAR_NAME} pattern
    pattern = r'\${([^}]+)}'
    match = re.search(pattern, value)
    
    if not match:
        return value
        
    env_var = match.group(1)
    if ':-' in env_var:
        env_name, default = env_var.split(':-')
        env_value = os.getenv(env_name, default)
    else:
        env_value = os.getenv(env_var)
        if env_value is None:
            raise ValueError(f"Environment variable {env_var} not set")
            
    # Try to convert to appropriate type
    try:
        if env_value.isdigit():
            return int(env_value)
        elif env_value.replace('.', '', 1).isdigit():
            return float(env_value)
        elif env_value.lower() in ('true', 'false'):
            return env_value.lower() == 'true'
        else:
            return env_value
    except (ValueError, AttributeError):
        return env_value

def load_config() -> Dict[str, Any]:
    """Load and validate configuration from YAML file.
    
    Returns:
        Dict[str, Any]: Validated configuration dictionary
        
    Raises:
        HTTPException: If configuration loading or validation fails
    """
    try:
        # Load environment variables
        load_dotenv()
        
        config_path = os.getenv("GOLDMIRROR_CONFIG", "config/config.yaml")
        with open(config_path, "r") as f:
            raw_config = yaml.safe_load(f)
            
        # Interpolate environment variables
        processed_config = interpolate_env_vars(raw_config)
        
        # Validate and convert to Pydantic model
        try:
            config = AppConfig(**processed_config)
            logger.info("config_loaded", path=config_path)
            return config.dict()
        except Exception as e:
            logger.error(
                "config_validation_failed",
                error=str(e),
                config=processed_config
            )
            raise HTTPException(
                status_code=500,
                detail=f"Configuration validation failed: {str(e)}"
            )
            
    except FileNotFoundError:
        logger.error("config_file_not_found", path=config_path)
        raise HTTPException(
            status_code=500,
            detail=f"Configuration file not found: {config_path}"
        )
    except yaml.YAMLError as e:
        logger.error("invalid_config_file", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Invalid configuration file: {str(e)}"
        )
    except Exception as e:
        logger.error("config_load_error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Configuration load failed: {str(e)}"
        )

app = create_app() 