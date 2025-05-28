"""FastAPI application entry point.

This module initializes and configures the FastAPI application,
including middleware, routers, and dependencies.
"""

import os
from pathlib import Path
from typing import Dict, Any

import structlog
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

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
                    risk_config=risk_config
                )
                signal_validator = SignalValidator(
                    signal_repository=signal_repository,
                    mt5_connection=mt5_service.connection
                )
                
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
                
        except Exception as e:
            logger.error("shutdown_error", error=str(e))
    
    return app

def load_config() -> Dict[str, Any]:
    """Load and validate configuration from YAML file.
    
    Returns:
        Dict[str, Any]: Validated configuration dictionary
        
    Raises:
        HTTPException: If configuration loading or validation fails
    """
    try:
        config_path = os.getenv("GOLDMIRROR_CONFIG", "config/config.yaml")
        with open(config_path, "r") as f:
            raw_config = yaml.safe_load(f)
            
        # Validate and convert to Pydantic model
        config = AppConfig(**raw_config)
        logger.info("config_loaded", path=config_path)
        return config.dict()
        
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
        logger.error("config_validation_error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Configuration validation failed: {str(e)}"
        )

app = create_app() 