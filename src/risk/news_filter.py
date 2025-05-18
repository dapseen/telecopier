"""News filter implementation for the GoldMirror trading system.

This module implements news impact filtering including economic calendar integration,
news impact assessment, and pre/post news trading buffers.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

import MetaTrader5 as mt5
import pytz
import requests

logger = logging.getLogger(__name__)

class NewsImpact(Enum):
    """News impact levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

@dataclass
class NewsEvent:
    """Economic calendar event.
    
    Attributes:
        currency: Currency affected by the event
        name: Name of the economic event
        impact: Impact level of the event
        time: Event time in UTC
        actual: Actual value (if available)
        forecast: Forecasted value
        previous: Previous value
    """
    currency: str
    name: str
    impact: NewsImpact
    time: datetime
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None

class NewsFilter:
    """Filters trading based on economic news events.
    
    This class handles economic calendar integration, news impact filtering,
    and pre/post news trading buffers.
    
    Attributes:
        api_key: API key for economic calendar service
        buffer_minutes: Minutes to wait before/after high impact news
        affected_symbols: Mapping of currencies to trading symbols
        calendar_url: URL for economic calendar API
    """
    
    def __init__(
        self,
        api_key: str,
        buffer_minutes: int = 30,
        affected_symbols: Optional[Dict[str, Set[str]]] = None,
        calendar_url: str = "https://api.example.com/calendar"  # Replace with actual API
    ) -> None:
        """Initialize the NewsFilter.
        
        Args:
            api_key: API key for economic calendar service
            buffer_minutes: Minutes to wait before/after high impact news
            affected_symbols: Mapping of currencies to trading symbols
            calendar_url: URL for economic calendar API
        """
        self.api_key = api_key
        self.buffer_minutes = buffer_minutes
        self.affected_symbols = affected_symbols or {}
        self.calendar_url = calendar_url
        
    def is_safe_to_trade(self, symbol: str) -> Tuple[bool, str]:
        """Check if it's safe to trade based on upcoming news events.
        
        Args:
            symbol: Trading symbol to check
            
        Returns:
            Tuple containing:
                - bool: True if safe to trade, False otherwise
                - str: Error message if unsafe, empty string otherwise
        """
        try:
            # Get currencies affected by this symbol
            currencies = self._get_symbol_currencies(symbol)
            if not currencies:
                return True, ""  # Symbol not affected by news
                
            # Get upcoming news events
            events = self._get_upcoming_events(currencies)
            if not events:
                return True, ""
                
            # Check for high impact events within buffer period
            now = datetime.now(pytz.UTC)
            buffer = timedelta(minutes=self.buffer_minutes)
            
            for event in events:
                if event.impact == NewsImpact.HIGH:
                    event_time = event.time
                    if abs(event_time - now) <= buffer:
                        return False, (
                            f"High impact news event '{event.name}' for {event.currency} "
                            f"at {event_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                        )
                        
            return True, ""
            
        except Exception as e:
            logger.error(f"Error checking news safety: {str(e)}")
            return False, f"Error checking news safety: {str(e)}"
            
    def get_upcoming_events(
        self,
        currencies: Optional[Set[str]] = None,
        impact: Optional[NewsImpact] = None,
        hours_ahead: int = 24
    ) -> List[NewsEvent]:
        """Get upcoming economic calendar events.
        
        Args:
            currencies: Set of currencies to filter by
            impact: Impact level to filter by
            hours_ahead: Hours to look ahead for events
            
        Returns:
            List of upcoming NewsEvent instances
        """
        try:
            # Get all upcoming events
            events = self._get_upcoming_events(currencies or set())
            
            # Filter by impact if specified
            if impact:
                events = [e for e in events if e.impact == impact]
                
            # Filter by time window
            now = datetime.now(pytz.UTC)
            end_time = now + timedelta(hours=hours_ahead)
            events = [e for e in events if now <= e.time <= end_time]
            
            return events
            
        except Exception as e:
            logger.error(f"Error getting upcoming events: {str(e)}")
            return []
            
    def _get_symbol_currencies(self, symbol: str) -> Set[str]:
        """Get currencies affected by a trading symbol.
        
        Args:
            symbol: Trading symbol to check
            
        Returns:
            Set of affected currencies
        """
        currencies = set()
        for currency, symbols in self.affected_symbols.items():
            if symbol in symbols:
                currencies.add(currency)
        return currencies
        
    def _get_upcoming_events(self, currencies: Set[str]) -> List[NewsEvent]:
        """Fetch upcoming economic calendar events.
        
        Args:
            currencies: Set of currencies to filter by
            
        Returns:
            List of NewsEvent instances
        """
        try:
            # This is a placeholder for actual API implementation
            # Replace with actual API call to economic calendar service
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {
                "currencies": ",".join(currencies),
                "start": datetime.now(pytz.UTC).isoformat(),
                "end": (datetime.now(pytz.UTC) + timedelta(days=1)).isoformat()
            }
            
            response = requests.get(
                self.calendar_url,
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            # Parse response and create NewsEvent instances
            # This is a placeholder for actual response parsing
            events = []
            for event_data in response.json():
                events.append(NewsEvent(
                    currency=event_data["currency"],
                    name=event_data["name"],
                    impact=NewsImpact(event_data["impact"]),
                    time=datetime.fromisoformat(event_data["time"]),
                    actual=event_data.get("actual"),
                    forecast=event_data.get("forecast"),
                    previous=event_data.get("previous")
                ))
                
            return events
            
        except Exception as e:
            logger.error(f"Error fetching economic calendar: {str(e)}")
            return [] 