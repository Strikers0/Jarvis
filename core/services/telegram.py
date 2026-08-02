from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
from typing import Any, Optional

from core.services.messaging import MessagingService
from core.services.telegram_client import TelegramClientFactory

logger = logging.getLogger(__name__)


class TelegramService(MessagingService):
    """Telegram messaging service backed by a Telethon MTProto userbot client."""

    name = "telegram"
    description = "Telegram messaging via Telethon userbot"

    def __init__(
        self,
        api_id: int = 0,
        api_hash: str = "",
        session_name: str = "jarvis_telegram",
        allowed_users: Optional[list[int]] = None,
        owner_chat_id: int = 0,
        voice_enabled: bool = True,
    ):
        super().__init__()
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name
        self.allowed_users = set(allowed_users or [])
        self.owner_chat_id = owner_chat_id
        self.voice_enabled = voice_enabled
        self.client: Optional[Any] = None
        self._running = False
        self._event_handler: Optional[Any] = None
        self._self_user_id: int = 0
        self._sent_ids: deque[int] = deque(maxlen=200)

    # ---- lifecycle ----

    async def start(self) -> None:
        if not self.is_configured():
            raise RuntimeError("Telegram not configured (TELEGRAM_API_ID / TELEGRAM_API_HASH).")
        self.client = TelegramClientFactory.create(
            self.api_id, self.api_hash, self.session_name
        )
        await self.client.start()
        if self._event_handler is not None:
            from telethon import events

            self.client.add_event_handler(
                self._event_handler.handle, events.NewMessage()
            )
        self._running = True
        logger.info("Telegram service started (me=%s)", await self._me())

    async def stop(self) -> None:
        self._running = False
        if self.client is not None:
            try:
                if self._event_handler is not None:
                    from telethon import events

                    self.client.remove_event_handler(
                        self._event_handler.handle, events.NewMessage()
                    )
                await self.client.disconnect()
            except Exception as e:
                logger.warning("Error disconnecting Telegram client: %s", e)
            self.client = None

    def attach_event_handler(self, handler: Any) -> None:
        """Register the inbound event handler used by `start()`."""
        self._event_handler = handler

    async def _me(self) -> str:
        try:
            me = await self.client.get_me()
            return str(getattr(me, "username", "") or getattr(me, "first_name", "") or "?")
        except Exception:
            return "?"

    # ---- outbound ----

    async def send_message(self, recipient_id: str, text: str) -> bool:
        if self.client is None:
            return False
        try:
            sent = await self.client.send_message(int(recipient_id), text)
            self._record_sent(sent)
            return True
        except Exception as e:
            logger.warning("Telegram send_message failed: %s", e)
            return False

    async def send_file(self, recipient_id: str, path: Path, caption: str = "") -> bool:
        if self.client is None or not Path(path).exists():
            return False
        try:
            sent = await self.client.send_file(
                int(recipient_id), str(path), caption=caption or None
            )
            self._record_sent(sent)
            return True
        except Exception as e:
            logger.warning("Telegram send_file failed: %s", e)
            return False

    async def send_voice(self, recipient_id: str, path: Path, caption: str = "") -> bool:
        if self.client is None or not Path(path).exists():
            return False
        try:
            sent = await self.client.send_file(
                int(recipient_id), str(path), voice_note=True, caption=caption or None
            )
            self._record_sent(sent)
            return True
        except Exception as e:
            logger.warning("Telegram send_voice failed: %s", e)
            return False

    def _record_sent(self, sent: Any) -> None:
        msg_id = getattr(sent, "id", None)
        if msg_id is not None:
            self._sent_ids.append(int(msg_id))

    def was_sent_by_us(self, message_id: int) -> bool:
        return int(message_id) in self._sent_ids

    async def self_user_id(self) -> int:
        if self._self_user_id or self.client is None:
            return self._self_user_id
        try:
            me = await self.client.get_me()
            self._self_user_id = int(getattr(me, "id", 0) or 0)
        except Exception:
            self._self_user_id = 0
        return self._self_user_id

    # ---- helpers ----

    def is_configured(self) -> bool:
        return bool(self.api_id and self.api_hash)

    def is_allowed_user(self, user_id: str) -> bool:
        return int(user_id or 0) in self.allowed_users

    async def health_check(self) -> dict:
        if not self.is_configured():
            return {
                "ok": False,
                "detail": "Not configured (set TELEGRAM_API_ID / TELEGRAM_API_HASH)",
            }
        if self.client is None or not self.client.is_connected():
            return {"ok": False, "detail": "Not connected"}
        return {
            "ok": True,
            "detail": f"Connected as {await self._me()} (allowed: {sorted(self.allowed_users)})",
        }
