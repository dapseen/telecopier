"""
Telegram client implementation for GoldMirror.
Handles secure connection to Telegram API and message reception using Telethon.
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Awaitable, Union

import structlog
from telethon import TelegramClient as TelethonClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    FloodWaitError,
    ChannelPrivateError,
    ChannelInvalidError,
)
from telethon.tl.types import Channel, Message, InputPeerChannel, InputPeerChat, InputChannel

logger = structlog.get_logger(__name__)

class SignalMonitor:
    """Manages secure connection to Telegram API and handles message reception."""

    def __init__(
        self,
        api_id: str,
        api_hash: str,
        channel_id: str,
        session_path: Optional[str] = None,
        message_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        phone: Optional[str] = None,
    ) -> None:
        """Initialize the Telegram client.

        Args:
            api_id: Telegram API ID from https://my.telegram.org
            api_hash: Telegram API hash from https://my.telegram.org
            channel_id: ID or username of the channel to monitor
                      For private channels, use format: -100xxxxxxxxxx
                      For public channels, use the channel username
            session_path: Optional path to store session data
            message_callback: Async callback function for new messages
            phone: Phone number for authentication (optional)
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.channel_id = channel_id
        self._channel_entity = None  # Will store the resolved channel entity
        
        # Set up session path and ensure directory exists
        if session_path:
            self.session_path = session_path
        else:
            session_dir = Path.home() / ".goldmirror"
            session_dir.mkdir(parents=True, exist_ok=True)
            self.session_path = str(session_dir / "telegram.session")
            
        self.message_callback = message_callback
        self.client: Optional[TelethonClient] = None
        self._is_connected = False
        self._last_message_time: Optional[datetime] = None
        self._connection_attempts = 0
        self._max_retries = 5
        self._retry_delay = 5  # seconds
        self.phone = phone

    def _get_phone_number(self) -> str:
        """Get and validate phone number input from user.

        Returns:
            str: Valid phone number with country code
        """
        while True:
            phone = input('Please enter your phone number (with country code, e.g., +1234567890): ').strip()
            if not phone:
                print("Phone number cannot be empty. Please try again.")
                continue
                
            # Basic validation for phone number format
            if not re.match(r'^\+[1-9]\d{1,14}$', phone):
                print("Invalid phone number format. Please include country code (e.g., +1234567890)")
                continue
                
            return phone

    def _get_verification_code(self) -> str:
        """Get and validate verification code input from user.

        Returns:
            str: Valid verification code
        """
        while True:
            code = input('Please enter the verification code sent to your phone: ').strip()
            if not code:
                print("Verification code cannot be empty. Please try again.")
                continue
                
            # Basic validation for verification code
            if not code.isdigit():
                print("Verification code should contain only digits. Please try again.")
                continue
                
            return code

    def _get_2fa_password(self) -> str:
        """Get and validate 2FA password input from user.

        Returns:
            str: Valid 2FA password
        """
        while True:
            password = input('Please enter your 2FA password: ').strip()
            if not password:
                print("Password cannot be empty. Please try again.")
                continue
            return password

    async def _sign_in(self) -> None:
        """Handle the sign-in process for the Telegram client."""
        if not self.client:
            raise RuntimeError("Client not initialized")

        try:
            # Get phone number
            phone = self._get_phone_number()
            
            # Send code request
            await self.client.send_code_request(phone)
            logger.info("verification_code_sent")
            
            # Get verification code
            code = self._get_verification_code()
            
            try:
                # Try to sign in with phone and code
                await self.client.sign_in(phone=phone, code=code)
            except SessionPasswordNeededError:
                # If 2FA is enabled, get password
                password = self._get_2fa_password()
                await self.client.sign_in(password=password)
                
        except PhoneNumberInvalidError:
            logger.error("invalid_phone_number")
            raise ValueError("Invalid phone number. Please check the format and try again.")
        except Exception as e:
            logger.error("sign_in_failed", error=str(e))
            raise

    async def _resolve_channel(self) -> None:
        """Resolve the channel ID to a proper Telegram entity.
        
        This method handles both private and public channels, converting
        the channel ID to the appropriate format that Telethon can use.
        """
        if not self.client:
            raise RuntimeError("Client not initialized")

        try:
            # First try to get the channel directly
            try:
                self._channel_entity = await self.client.get_entity(self.channel_id)
                logger.info(
                    "channel_resolved",
                    channel_id=self.channel_id,
                    title=getattr(self._channel_entity, "title", "Unknown"),
                    type=self._channel_entity.__class__.__name__,
                )
                return
            except ValueError:
                pass

            # If direct resolution fails, try to parse the channel ID
            if self.channel_id.startswith("-100"):
                # Private channel format: -100xxxxxxxxxx
                # Convert to proper channel ID format
                try:
                    # Remove the -100 prefix and convert to integer
                    channel_id = int(self.channel_id[4:])
                    # Create InputPeerChannel
                    self._channel_entity = InputPeerChannel(channel_id, 0)  # access_hash will be filled by Telethon
                    # Get the full channel entity
                    self._channel_entity = await self.client.get_entity(self._channel_entity)
                    logger.info(
                        "private_channel_resolved",
                        channel_id=self.channel_id,
                        title=getattr(self._channel_entity, "title", "Unknown"),
                    )
                    return
                except (ValueError, ChannelInvalidError) as e:
                    logger.error(
                        "private_channel_resolution_failed",
                        channel_id=self.channel_id,
                        error=str(e),
                    )
                    raise ValueError(
                        f"Invalid private channel ID format: {self.channel_id}. "
                        "Expected format: -100xxxxxxxxxx"
                    ) from e

            # If we get here, the channel ID is invalid
            raise ValueError(
                f"Could not resolve channel: {self.channel_id}. "
                "Please ensure the channel ID is correct and you have access to it."
            )

        except Exception as e:
            logger.error(
                "channel_resolution_error",
                channel_id=self.channel_id,
                error=str(e),
            )
            raise

    async def start(self) -> None:
        """Start the Telegram client and connect."""
        await self.connect()

    async def stop(self) -> None:
        """Stop the Telegram client and disconnect."""
        await self.disconnect()

    async def run_forever(self) -> None:
        """Run the client forever until interrupted."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        await self.client.run_until_disconnected()

    async def connect(self) -> None:
        """Establish connection to Telegram API with retry logic."""
        if self._is_connected:
            logger.warning("already_connected")
            return

        while self._connection_attempts < self._max_retries:
            try:
                # Ensure session directory exists
                session_dir = os.path.dirname(self.session_path)
                os.makedirs(session_dir, exist_ok=True)
                
                # Create client instance
                self.client = TelethonClient(
                    self.session_path,
                    self.api_id,
                    self.api_hash,
                    device_model="GoldMirror",
                    system_version="Python",
                    app_version="1.0.0",
                )

                # Connect to Telegram
                await self.client.connect()
                
                # Check if we need to sign in
                if not await self.client.is_user_authorized():
                    logger.info("sign_in_required")
                    await self._sign_in()
                
                # Resolve the channel
                await self._resolve_channel()

                # Add message handler after successful connection
                @self.client.on(events.NewMessage(chats=self._channel_entity))
                async def handle_new_message(event: events.NewMessage.Event) -> None:
                    try:
                        await self._handle_message(event.message)
                    except Exception as e:
                        logger.error(
                            "event_handler_error",
                            error=str(e),
                            message_id=event.message.id if event.message else "unknown"
                        )

                self._is_connected = True
                self._connection_attempts = 0
                logger.info(
                    "telegram_connected",
                    channel_id=self.channel_id,
                    channel_title=getattr(self._channel_entity, "title", "Unknown"),
                    session_path=self.session_path,
                )
                return

            except Exception as e:
                self._connection_attempts += 1
                logger.error(
                    "connection_failed",
                    error=str(e),
                    attempt=self._connection_attempts,
                    max_retries=self._max_retries,
                )
                
                if self._connection_attempts < self._max_retries:
                    await asyncio.sleep(self._retry_delay)
                    continue
                else:
                    raise ConnectionError(f"Failed to connect after {self._max_retries} attempts")

    async def disconnect(self) -> None:
        """Safely disconnect from Telegram API."""
        if not self._is_connected or not self.client:
            return

        try:
            await self.client.disconnect()
            self._is_connected = False
            logger.info("telegram_disconnected")
        except Exception as e:
            logger.error("disconnect_error", error=str(e))
            raise

    async def _handle_message(self, message: Message) -> None:
        """Handle incoming messages from the monitored channel.

        Args:
            message: Telegram message object
        """
        try:
            # Convert datetime objects to ISO format strings
            message_date = message.date.isoformat() if message.date else None
            edit_date = message.edit_date.isoformat() if message.edit_date else None

            # Extract channel name if available
            channel_name = None
            if message.chat:
                channel_name = getattr(message.chat, 'title', None) or getattr(message.chat, 'username', None)

            message_data = {
                "message_id": message.id,
                "chat_id": message.chat_id,
                "channel_name": channel_name or "default",
                "text": message.text,
                "date": message_date,
                "edit_date": edit_date,
            }

            self._last_message_time = message.date
            logger.debug("message_received", **message_data)

            if self.message_callback:
                # Create a task for the callback to prevent blocking
                asyncio.create_task(self._execute_callback(message_data))

        except Exception as e:
            logger.error(
                "message_handling_error",
                error=str(e),
                message_id=getattr(message, 'id', 'unknown'),
                message_text=getattr(message, "text", None),
            )

    async def _execute_callback(self, message_data: Dict[str, Any]) -> None:
        """Execute the message callback in a safe manner.

        Args:
            message_data: The message data to pass to the callback
        """
        try:
            await self.message_callback(message_data)
        except Exception as e:
            logger.error(
                "callback_execution_error",
                error=str(e),
                message_id=message_data.get("message_id", "unknown")
            )

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected to Telegram.

        Returns:
            bool: True if connected, False otherwise
        """
        return self._is_connected

    @property
    def last_message_time(self) -> Optional[datetime]:
        """Get the timestamp of the last received message.

        Returns:
            Optional[datetime]: Timestamp of last message or None if no messages
        """
        return self._last_message_time 