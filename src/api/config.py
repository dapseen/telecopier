"""Configuration models for FastAPI application.

This module contains Pydantic models for configuration validation
and management.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator

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
        """Validate time format (HH:MM)."""
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
        """Validate trading symbols."""
        if not v:
            raise ValueError("symbols cannot be empty")
        if not all(isinstance(symbol, str) and symbol for symbol in v):
            raise ValueError("symbols must be non-empty strings")
        if len(set(v)) != len(v):
            raise ValueError("symbols must be unique")
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

class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str
    format: str
    file: Dict[str, Any]
    telegram: Dict[str, Any]

    @field_validator("level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate logging level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {', '.join(valid_levels)}")
        return v.upper()

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate logging format."""
        valid_formats = ["structured", "text", "json"]
        if v.lower() not in valid_formats:
            raise ValueError(f"Invalid format. Must be one of: {', '.join(valid_formats)}")
        return v.lower()

    @field_validator("file")
    @classmethod
    def validate_file_config(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate file logging configuration."""
        required_fields = {"enabled", "path"}
        missing_fields = required_fields - set(v.keys())
        if missing_fields:
            raise ValueError(f"Missing required file config fields: {', '.join(missing_fields)}")
        return v

class AnalyticsConfig(BaseModel):
    """Analytics configuration."""
    enabled: bool
    metrics: List[str]
    dashboard: Dict[str, Any]

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, v: List[str]) -> List[str]:
        """Validate analytics metrics."""
        valid_metrics = {
            "win_rate",
            "profit_factor",
            "average_win",
            "average_loss",
            "max_drawdown",
            "breakeven_hit_rate"
        }
        invalid_metrics = [m for m in v if m not in valid_metrics]
        if invalid_metrics:
            raise ValueError(f"Invalid metrics: {', '.join(invalid_metrics)}")
        return v

class RiskConfig(BaseModel):
    """Risk management configuration."""
    risk_per_trade_pct: float = Field(gt=0, le=5)  # Max 5% risk per trade
    max_position_size_pct: float = Field(gt=0, le=2)  # Max 2% position size
    max_open_positions: int = Field(gt=0)
    max_daily_loss_pct: float = Field(gt=0, le=5)  # Max 5% daily loss
    daily_loss_limit: float = Field(gt=0)
    min_account_balance: float = Field(gt=0)
    cooldown_after_loss: int = Field(gt=0)
    max_slippage: int = Field(gt=0)

class MT5Config(BaseModel):
    """MT5 configuration."""
    server: Optional[str] = None  # Loaded from MT5_SERVER env var
    timezone: str = "UTC"
    timeout_ms: int = Field(default=60000, gt=0)
    retry_delay_seconds: int = Field(default=5, gt=0)
    max_retries: int = Field(default=3, gt=0)
    health_check_interval_seconds: int = Field(default=30, gt=0)
    login: Optional[int] = None  # Loaded from MT5_LOGIN env var
    password: Optional[str] = None  # Loaded from MT5_PASSWORD env var

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone string."""
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(v)
        except Exception:
            raise ValueError(f"Invalid timezone: {v}")
        return v

class OpenAIConfig(BaseModel):
    """OpenAI configuration."""
    model: str = "gpt-3.5-turbo"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, gt=0)
    timeout_seconds: int = Field(default=30, gt=0)
    retry_attempts: int = Field(default=3, gt=0)
    retry_delay_seconds: int = Field(default=1, gt=0)

class AppConfig(BaseModel):
    """Main application configuration."""
    trading_sessions: List[TradingSession]
    position: PositionConfig
    news_filter: NewsFilterConfig
    signal: SignalConfig
    logging: LoggingConfig
    analytics: AnalyticsConfig
    mt5: MT5Config
    risk: RiskConfig
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig) 