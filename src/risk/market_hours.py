"""Market hours validation for the GoldMirror trading system.

This module implements market hours validation including session time checks,
timezone handling, and market status monitoring.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Set, Tuple

import MetaTrader5 as mt5
import pytz

logger = logging.getLogger(__name__)

@dataclass
class TradingSession:
    """Trading session configuration.
    
    Attributes:
        name: Name of the trading session (e.g., "London", "New York")
        start_time: Session start time in UTC
        end_time: Session end time in UTC
        symbols: Set of symbols traded in this session
        timezone: Timezone for the session
    """
    name: str
    start_time: time
    end_time: time
    symbols: Set[str]
    timezone: str

class MarketHours:
    """Validates trading sessions and market status.
    
    This class handles session time validation, timezone management,
    and market status checks for different trading sessions.
    
    Attributes:
        sessions: List of TradingSession instances
        broker_timezone: Timezone of the broker
    """
    
    def __init__(self, sessions: List[TradingSession], broker_timezone: str = "UTC") -> None:
        """Initialize the MarketHours validator.
        
        Args:
            sessions: List of TradingSession instances
            broker_timezone: Timezone of the broker (default: UTC)
        """
        self.sessions = sessions
        self.broker_timezone = pytz.timezone(broker_timezone)
        
    def is_market_open(self, symbol: str) -> Tuple[bool, str]:
        """Check if the market is open for a given symbol.
        
        Args:
            symbol: Trading symbol to check
            
        Returns:
            Tuple containing:
                - bool: True if market is open, False otherwise
                - str: Error message if check fails, empty string otherwise
        """
        try:
            # Check if symbol exists
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return False, f"Symbol {symbol} not found"
                
            # Check if symbol is visible and enabled
            if not symbol_info.visible:
                if not mt5.symbol_select(symbol, True):
                    return False, f"Failed to enable symbol {symbol}"
                    
            # Get current time in broker's timezone
            current_time = datetime.now(self.broker_timezone).time()
            
            # Check if symbol is in any active session
            for session in self.sessions:
                if symbol in session.symbols:
                    session_tz = pytz.timezone(session.timezone)
                    session_time = datetime.now(session_tz).time()
                    
                    if session.start_time <= session_time <= session.end_time:
                        return True, ""
                        
            return False, f"Market closed for {symbol}"
            
        except Exception as e:
            logger.error(f"Error checking market status: {str(e)}")
            return False, f"Error checking market status: {str(e)}"
            
    def get_active_sessions(self) -> List[str]:
        """Get list of currently active trading sessions.
        
        Returns:
            List of active session names
        """
        active_sessions = []
        current_time = datetime.now(self.broker_timezone).time()
        
        for session in self.sessions:
            session_tz = pytz.timezone(session.timezone)
            session_time = datetime.now(session_tz).time()
            
            if session.start_time <= session_time <= session.end_time:
                active_sessions.append(session.name)
                
        return active_sessions
        
    def get_session_symbols(self, session_name: str) -> Optional[Set[str]]:
        """Get set of symbols for a specific trading session.
        
        Args:
            session_name: Name of the trading session
            
        Returns:
            Set of symbols for the session, or None if session not found
        """
        for session in self.sessions:
            if session.name == session_name:
                return session.symbols
        return None
        
    def get_next_session_start(self, session_name: str) -> Optional[datetime]:
        """Get the start time of the next occurrence of a session.
        
        Args:
            session_name: Name of the trading session
            
        Returns:
            Datetime of next session start, or None if session not found
        """
        for session in self.sessions:
            if session.name == session_name:
                session_tz = pytz.timezone(session.timezone)
                now = datetime.now(session_tz)
                
                # Create datetime for today's session start
                session_start = datetime.combine(now.date(), session.start_time)
                session_start = session_tz.localize(session_start)
                
                # If session already started today, get tomorrow's start
                if now.time() > session.start_time:
                    session_start += timedelta(days=1)
                    
                return session_start.astimezone(self.broker_timezone)
                
        return None 