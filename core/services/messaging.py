from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from core.services.base import Service


@dataclass
class Attachment:
    """A platform-neutral file or media attachment."""

    path: Path
    mime_type: str = ""
    caption: str = ""


@dataclass
class InboundMessage:
    """A platform-neutral inbound message.

    `recipient_id` is the identifier to reply to (e.g. a chat id on Telegram).
    `user_id` is the identity to scope conversation memory / permissions to.
    """

    text: str
    sender_id: str
    chat_id: str
    recipient_id: str
    platform: str = "generic"
    attachments: list[Attachment] = field(default_factory=list)
    raw: Any = None

    @property
    def is_command(self) -> bool:
        return self.text.startswith("/")


@dataclass
class OutboundMessage:
    """A platform-neutral outbound message or media send request."""

    recipient_id: str
    text: str = ""
    attachments: list[Attachment] = field(default_factory=list)
    voice: Optional[Path] = None


MessageHandler = Callable[[InboundMessage], Awaitable[Any]]


class MessagingService(Service):
    """Base interface for chat/messaging platforms.

    Any platform (Telegram, WhatsApp, Discord, Slack, Signal, SMS) implements
    this same contract so it can plug into the JARVIS runtime with minimal changes.
    """

    name: str = "messaging"
    description: str = "Messaging platform service"

    def __init__(self) -> None:
        self._message_handler: Optional[MessageHandler] = None

    # ---- lifecycle ----

    @abstractmethod
    async def start(self) -> None:
        """Connect to the platform and begin listening for inbound events."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening and disconnect cleanly."""

    # ---- outbound ----

    @abstractmethod
    async def send_message(self, recipient_id: str, text: str) -> bool:
        """Send a plain text message."""

    @abstractmethod
    async def send_file(self, recipient_id: str, path: Path, caption: str = "") -> bool:
        """Send a file/document attachment."""

    @abstractmethod
    async def send_voice(self, recipient_id: str, path: Path, caption: str = "") -> bool:
        """Send an audio/voice note."""

    # ---- inbound ----

    def on_message(self, handler: MessageHandler) -> None:
        """Register the callback invoked for every inbound message."""
        self._message_handler = handler

    async def _dispatch_inbound(self, message: InboundMessage) -> Any:
        if self._message_handler is None:
            return None
        return await self._message_handler(message)

    async def close(self) -> None:
        await self.stop()
