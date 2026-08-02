from __future__ import annotations

from pathlib import Path

import pytest

from core.services.messaging import (
    Attachment,
    InboundMessage,
    MessagingService,
    OutboundMessage,
)


def test_attachment_model():
    att = Attachment(path=Path("/tmp/a.wav"), mime_type="audio/wav", caption="hi")
    assert att.path == Path("/tmp/a.wav")
    assert att.mime_type == "audio/wav"
    assert att.caption == "hi"


def test_inbound_message_defaults():
    msg = InboundMessage(text="hello", sender_id="1", chat_id="2", recipient_id="2")
    assert msg.platform == "generic"
    assert msg.attachments == []
    assert not msg.is_command


def test_inbound_message_detects_command():
    msg = InboundMessage(text="/help", sender_id="1", chat_id="2", recipient_id="2")
    assert msg.is_command


def test_outbound_message_model():
    voice = Path("/tmp/r.wav")
    msg = OutboundMessage(recipient_id="42", text="hi", voice=voice)
    assert msg.recipient_id == "42"
    assert msg.voice == voice
    assert msg.attachments == []


class _DummyService(MessagingService):
    name = "dummy"

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def send_message(self, recipient_id: str, text: str) -> bool:
        return True

    async def send_file(self, recipient_id: str, path: Path, caption: str = "") -> bool:
        return True

    async def send_voice(self, recipient_id: str, path: Path, caption: str = "") -> bool:
        return True

    async def health_check(self) -> dict:
        return {"ok": True, "detail": "dummy"}


@pytest.mark.asyncio
async def test_on_message_registration_and_dispatch():
    service = _DummyService()
    received = []

    async def handler(msg: InboundMessage) -> str:
        received.append(msg.text)
        return "replied"

    service.on_message(handler)
    result = await service._dispatch_inbound(
        InboundMessage(text="ping", sender_id="1", chat_id="2", recipient_id="2")
    )
    assert result == "replied"
    assert received == ["ping"]


@pytest.mark.asyncio
async def test_dispatch_without_handler_returns_none():
    service = _DummyService()
    assert await service._dispatch_inbound(
        InboundMessage(text="x", sender_id="1", chat_id="2", recipient_id="2")
    ) is None


@pytest.mark.asyncio
async def test_close_calls_stop():
    service = _DummyService()
    await service.start()
    assert service.started
    await service.close()
    assert not service.started
