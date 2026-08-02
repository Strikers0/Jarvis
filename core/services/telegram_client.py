from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TelegramClientFactory:
    """Create and manage the Telethon TelegramClient singleton.

    Only this module touches Telethon, keeping the rest of the service
    platform-agnostic. The client is lazily constructed and cached.
    """

    _client: Optional[Any] = None

    @classmethod
    def create(cls, api_id: int, api_hash: str, session_name: str = "jarvis_telegram") -> Any:
        if cls._client is not None:
            return cls._client

        if not api_id or not api_hash:
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required.")

        try:
            from telethon import TelegramClient
        except ImportError:
            raise RuntimeError(
                "Telethon is not installed. Install it with: pip install telethon"
            )

        cls._client = TelegramClient(session_name, api_id, api_hash)
        return cls._client

    @classmethod
    def reset(cls) -> None:
        cls._client = None

    @classmethod
    def get(cls) -> Optional[Any]:
        return cls._client
