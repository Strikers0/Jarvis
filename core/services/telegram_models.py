from __future__ import annotations

from dataclasses import dataclass

from core.services.messaging import InboundMessage


@dataclass
class TelegramRecipient:
    """Identifies a Telegram chat/peer to send messages to."""

    chat_id: int

    @property
    def recipient_id(self) -> str:
        return str(self.chat_id)


@dataclass
class TelegramInboundMessage(InboundMessage):
    """A Telegram message adapted to the platform-neutral InboundMessage."""

    platform: str = "telegram"
    message_id: int = 0
    sender_username: str = ""
    is_voice: bool = False
    voice_path: str = ""
    raw: object = None
    from_: object = None
    peer_id: int = 0
    reply_recipient_id: str = ""

    @classmethod
    def from_telethon_event(
        cls, event: object, self_user_id: int = 0
    ) -> "TelegramInboundMessage | None":
        """Build a TelegramInboundMessage from a Telethon NewMessage event.

        Returns None for messages that should be ignored (commands sent by us
        outside Saved Messages, non-text non-voice content, etc.).

        `self_user_id` is the account's own user id: when set, outgoing messages
        in the Saved Messages chat (chat id == self user id) are treated as
        inbound commands, so you can message yourself and JARVIS reacts there.
        """
        message = getattr(event, "message", None)
        if message is None:
            return None

        peer = getattr(event, "chat", None)
        chat_id = int(getattr(peer, "id", 0) or 0)

        if getattr(message, "out", False) and chat_id != self_user_id:
            return None

        text = (getattr(message, "text", "") or "").strip()
        peer = getattr(event, "chat", None)
        sender = getattr(event, "sender", None)
        chat_id = int(getattr(peer, "id", 0) or 0)
        sender_id = int(getattr(sender, "id", 0) or chat_id)
        message_id = int(getattr(message, "id", 0) or 0)

        is_voice = bool(getattr(message, "voice", None)) or bool(getattr(message, "audio", None))
        voice_path = ""

        if not text and not is_voice:
            return None

        return cls(
            text=text,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            recipient_id=str(chat_id),
            message_id=message_id,
            sender_username=str(getattr(sender, "username", "") or ""),
            is_voice=is_voice,
            voice_path=voice_path,
            raw=event,
            from_=sender,
            peer_id=chat_id,
            reply_recipient_id=str(chat_id),
        )
