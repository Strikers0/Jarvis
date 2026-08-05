from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
from typing import Any, Optional

from core.services.base import service_tool
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
        self._sent_log: deque[tuple[int, int]] = deque(maxlen=1000)

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
            chat_id = getattr(sent, "chat_id", None)
            if chat_id is not None:
                self._sent_log.append((int(chat_id), int(msg_id)))

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

    # ---- user-facing tools ----

    async def _resolve_target(self, recipient: str) -> Any:
        t = (recipient or "").strip()
        try:
            return int(t)
        except ValueError:
            return t

    async def _find_by_name(self, low: str) -> Any:
        """Case-insensitive lookup of a contact/chat by name (exact, then substring).

        Searches open dialogs first, then saved contacts (which covers people you
        have never messaged), so "dr pushpa" finds a contact stored as "Dr. Pushpa".
        """
        low = (low or "").strip().lower()

        async for dialog in self.client.iter_dialogs():
            title = (dialog.title or "").strip() or str(dialog.id)
            if low == title.lower():
                return dialog.entity
        async for dialog in self.client.iter_dialogs():
            title = (dialog.title or "").strip() or str(dialog.id)
            if low in title.lower():
                return dialog.entity

        for contact in await self.client.get_contacts():
            full = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
            if not full:
                continue
            if low == full.lower():
                return contact
            if low in full.lower():
                return contact

        return None

    async def _resolve_entity(self, recipient: str) -> Any:
        """Resolve a recipient (id, @username, or name) to a sendable entity."""
        t = (recipient or "").strip()
        if not t:
            raise ValueError("No recipient specified.")

        if t.lstrip("-").isdigit() or t.startswith("@"):
            return await self.client.get_entity(t)

        try:
            return await self.client.get_entity(t)
        except Exception:
            pass

        found = await self._find_by_name(t.lower())
        if found is not None:
            return found

        raise ValueError(f"Recipient '{recipient}' not found in your Telegram.")

    async def send_message_to(self, recipient: str, text: str) -> bool:
        """Send a plain text message to a user/chat (by id, @username, or name)."""
        if self.client is None or not text.strip():
            return False
        try:
            target = await self._resolve_entity(recipient)
            sent = await self.client.send_message(target, text.strip())
            self._record_sent(sent)
            return True
        except Exception as e:
            logger.warning("Telegram send_message_to failed: %s", e)
            return False

    async def delete_messages(self, chat_id: str, message_ids: list[int]) -> bool:
        """Delete specific messages in a chat (own messages only anywhere, others need admin)."""
        if self.client is None or not message_ids:
            return False
        try:
            target = await self._resolve_target(chat_id)
            ids = [int(m) for m in message_ids]
            await self.client.delete_messages(target, ids, revoke=True)
            return True
        except Exception as e:
            logger.warning("Telegram delete_messages failed: %s", e)
            return False

    async def delete_recent_own(self, chat_id: str, count: int = 10) -> bool:
        """Delete the last `count` messages the assistant itself sent in a chat."""
        if self.client is None:
            return False
        try:
            target = await self._resolve_target(chat_id)
            count = max(1, min(int(count) if count else 10, len(self._sent_log)))
            ids = [msg_id for cid, msg_id in list(self._sent_log)[-count:] if cid == int(target)]
            ids = ids[:count]  # only the most recent `count` for this chat
            if not ids:
                return False
            await self.client.delete_messages(target, ids, revoke=True)
            return True
        except Exception as e:
            logger.warning("Telegram delete_recent_own failed: %s", e)
            return False

    async def _resolve_peer(self, lookup: str) -> Any:
        """Resolve a lookup to a real Telegram entity (id, @username, or name).

        Returns a full entity (User/Chat/Channel) or a valid input peer so it can
        be passed to any request (e.g. DeleteHistoryRequest) which requires a
        concrete peer with a valid access hash.
        """
        from telethon.utils import get_input_peer

        t = (lookup or "").strip()
        if not t:
            raise ValueError("No chat specified.")
        low = t.lower()

        if t.lstrip("-").isdigit():
            try:
                return await self.client.get_entity(int(t))
            except Exception:
                return get_input_peer(int(t))

        if low in {
            "saved messages", "saved message", "saved",
            "with myself", "with me", "me", "self",
        }:
            return await self.client.get_me()

        try:
            return await self.client.get_entity(t)
        except Exception:
            pass

        found = await self._find_by_name(t.lower())
        if found is not None:
            return found

        raise ValueError(f"Chat '{lookup}' not found in your Telegram.")

    async def list_chats(self, query: str = "", limit: int = 50) -> str:
        """List your Telegram chats/dialogs, optionally filtered by a name substring."""
        if self.client is None:
            return "Telegram is not connected."
        try:
            q = (query or "").strip().lower()
            out = []
            async for dialog in self.client.iter_dialogs():
                title = (dialog.title or "").strip() or str(dialog.id)
                if q and q not in title.lower():
                    continue
                kind = (
                    "user"
                    if dialog.is_user
                    else "group"
                    if dialog.is_group
                    else "channel"
                    if dialog.is_channel
                    else "chat"
                )
                out.append(f"{title} (id={dialog.id}, {kind})")
                if len(out) >= max(1, int(limit or 50)):
                    break
            return "\n".join(out) if out else "No matching chats found."
        except Exception as e:
            logger.warning("Telegram list_chats failed: %s", e)
            return f"Failed to list chats: {e}"

    async def read_chat(self, chat_lookup: str, limit: int = 30) -> str:
        """Read the most recent messages of a chat. Returns 'message_id: text' lines."""
        if self.client is None:
            return "Telegram is not connected."
        try:
            peer = await self._resolve_peer(chat_lookup)
            msgs = await self.client.get_messages(peer, limit=max(1, int(limit or 30)))
            lines = []
            for m in msgs:
                text = (getattr(m, "message", "") or "").replace("\n", " ").strip()
                if not text:
                    continue
                marker = "me" if getattr(m, "out", False) else "them"
                lines.append(f"[{getattr(m, 'id', '?')}][{marker}] {text}")
            return "\n".join(lines) if lines else "No readable messages in that chat."
        except Exception as e:
            logger.warning("Telegram read_chat failed: %s", e)
            return f"Failed to read chat: {e}"

    async def _resolve_input_peer(self, lookup: str) -> Any:
        """Resolve a lookup to a pre-resolved InputPeer/InputUser ready for raw requests."""
        entity = await self._resolve_peer(lookup)
        return await self.client.get_input_entity(entity)

    async def block_user(self, chat_lookup: str) -> bool:
        """Block a Telegram user/chat so they can't message you."""
        if self.client is None:
            return False
        try:
            from telethon.tl.functions.channels import LeaveChannelRequest
            from telethon.tl.functions.contacts import BlockRequest
            from telethon.tl.types import InputPeerChannel

            peer = await self._resolve_input_peer(chat_lookup)
            if isinstance(peer, InputPeerChannel):
                await self.client(LeaveChannelRequest(peer))
                return True
            await self.client(BlockRequest(id=peer))
            return True
        except Exception as e:
            logger.warning("Telegram block_user failed: %s", e)
            return False

    async def unblock_user(self, chat_lookup: str) -> bool:
        """Unblock a Telegram user/chat."""
        if self.client is None:
            return False
        try:
            from telethon.tl.functions.contacts import UnblockRequest

            peer = await self._resolve_input_peer(chat_lookup)
            await self.client(UnblockRequest(id=peer))
            return True
        except Exception as e:
            logger.warning("Telegram unblock_user failed: %s", e)
            return False

    async def clear_chat_history(self, chat_lookup: str) -> bool:
        """Delete the entire message history of a chat (Saved Messages or any user chat)."""
        if self.client is None:
            return False
        try:
            from telethon.tl.functions.channels import (
                DeleteChannelRequest,
                LeaveChannelRequest,
            )
            from telethon.tl.functions.messages import DeleteHistoryRequest
            from telethon.tl.types import InputPeerChannel

            peer = await self._resolve_input_peer(chat_lookup)
            if isinstance(peer, InputPeerChannel) or isinstance(peer, int):
                # Channels can't be cleared via deleteHistory and can only be
                # removed if we admin them; otherwise we leave the channel.
                try:
                    await self.client(DeleteChannelRequest(peer))
                except Exception as leave_err:
                    logger.warning("DeleteChannel failed, leaving instead: %s", leave_err)
                    await self.client(LeaveChannelRequest(peer))
                return True

            await self.client(DeleteHistoryRequest(peer=peer, max_id=0, revoke=True))
            return True
        except Exception as e:
            logger.warning("Telegram clear_chat_history failed: %s", e)
            return False

    def get_tools(self) -> list[Any]:
        return [
            service_tool(
                name="telegram_send_message",
                description=(
                    "Send a Telegram message to a person by NAME. Call this directly with the "
                    "person's name exactly as the user said it - NEVER ask the user for an id, "
                    "@username, or clarifying details. The recipient is resolved automatically "
                    "and case-insensitively (e.g. 'dr pushpa' finds 'Dr. Pushpa'). "
                    "Use for 'send a message to ...'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "recipient": {
                            "type": "string",
                            "description": "The contact/chat name, @username, or id. Just use the name the user gave.",
                        },
                        "text": {
                            "type": "string",
                            "description": "The message text to send.",
                        },
                    },
                    "required": ["recipient", "text"],
                },
                handler=self.send_message_to,
                category="telegram",
                permission_level="auto",
            ),
            service_tool(
                name="telegram_delete_messages",
                description=(
                    "Delete specific messages by id from a Telegram chat. "
                    "Own messages can always be deleted; deleting others' "
                    "messages requires admin rights in that chat."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "string", "description": "Numeric chat id."},
                        "message_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of message ids to delete.",
                        },
                    },
                    "required": ["chat_id", "message_ids"],
                },
                handler=self.delete_messages,
                category="telegram",
                permission_level="confirm",
            ),
            service_tool(
                name="telegram_delete_recent",
                description=(
                    "Delete the last N messages the assistant itself sent in a chat by NAME. "
                    "Pass the chat name the user gave; resolution is automatic and case-insensitive. "
                    "Handy for cleaning up the Saved Messages conversation."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "chat_id": {
                            "type": "string",
                            "description": "Chat id or name. Use the name the user gave.",
                        },
                        "count": {
                            "type": "integer",
                            "description": "How many recent messages to delete.",
                            "default": 10,
                        },
                    },
                    "required": ["chat_id"],
                },
                handler=self.delete_recent_own,
                category="telegram",
                permission_level="confirm",
            ),
            service_tool(
                name="telegram_list_chats",
                description=(
                    "List the user's Telegram chats/dialogs to find a chat. "
                    "query is an optional name substring (e.g. 'bitcoin'). "
                    "Returns 'name (id=..., type)'. Use this before delete or block."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional name substring to filter by.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max chats to return.",
                            "default": 50,
                        },
                    },
                },
                handler=self.list_chats,
                category="telegram",
                permission_level="auto",
            ),
            service_tool(
                name="telegram_read_chat",
                description=(
                    "Read the most recent messages of a chat. chat_lookup can be a "
                    "numeric id, @username, or chat name. Use before deleting to know message ids."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "chat_lookup": {
                            "type": "string",
                            "description": "Chat id, name, or @username.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "How many recent messages to read.",
                            "default": 30,
                        },
                    },
                    "required": ["chat_lookup"],
                },
                handler=self.read_chat,
                category="telegram",
                permission_level="auto",
            ),
            service_tool(
                name="telegram_block",
                description=(
                    "Block a Telegram user/chat by NAME so they can no longer message you. "
                    "Use the name the user gave; resolution is automatic and case-insensitive. "
                    "Do not ask for an id or @username."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "chat_lookup": {
                            "type": "string",
                            "description": "Chat id, name, or @username to block. Use the name given.",
                        },
                    },
                    "required": ["chat_lookup"],
                },
                handler=self.block_user,
                category="telegram",
                permission_level="confirm",
            ),
            service_tool(
                name="telegram_unblock",
                description=(
                    "Unblock a previously blocked Telegram user/chat by name. "
                    "Use the name the user gave; resolution is automatic."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "chat_lookup": {
                            "type": "string",
                            "description": "Chat id, name, or @username to unblock. Use the name given.",
                        },
                    },
                    "required": ["chat_lookup"],
                },
                handler=self.unblock_user,
                category="telegram",
                permission_level="confirm",
            ),
            service_tool(
                name="telegram_clear_chat",
                description=(
                    "Delete the entire message history of a chat by NAME (e.g. Saved Messages or "
                    "any user chat). Use the name the user gave; resolution is automatic and "
                    "case-insensitive. Do not require a numeric id."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "chat_lookup": {
                            "type": "string",
                            "description": "Chat id or name to clear. Use the name the user gave.",
                        },
                    },
                    "required": ["chat_lookup"],
                },
                handler=self.clear_chat_history,
                category="telegram",
                permission_level="confirm",
            ),
        ]
