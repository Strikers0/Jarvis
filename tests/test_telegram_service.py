from __future__ import annotations

from pathlib import Path

import pytest

from core.services import ServiceManager, TelegramService
from core.services.telegram_models import (
    TelegramInboundMessage,
    TelegramRecipient,
)


def test_telegram_recipient():
    r = TelegramRecipient(chat_id=123)
    assert r.recipient_id == "123"


def test_service_is_configured():
    svc = TelegramService(api_id=0, api_hash="")
    assert not svc.is_configured()
    svc2 = TelegramService(api_id=1, api_hash="h")
    assert svc2.is_configured()


def test_allowed_users():
    svc = TelegramService(allowed_users=[111, 222])
    assert svc.is_allowed_user("111")
    assert svc.is_allowed_user("222")
    assert not svc.is_allowed_user("333")
    assert not svc.is_allowed_user("")


@pytest.mark.asyncio
async def test_sends_fail_when_not_started():
    svc = TelegramService(api_id=1, api_hash="h")
    assert await svc.send_message("1", "hi") is False
    assert await svc.send_file("1", Path("nope.wav")) is False
    assert await svc.send_voice("1", Path("nope.wav")) is False


@pytest.mark.asyncio
async def test_health_check_not_configured():
    svc = TelegramService(api_id=0, api_hash="")
    report = await svc.health_check()
    assert report["ok"] is False


def test_telegram_tools_registered():
    svc = TelegramService(api_id=1, api_hash="h")
    tools = svc.get_tools()
    names = {t.name for t in tools}
    assert {
        "telegram_send_message",
        "telegram_delete_messages",
        "telegram_delete_recent",
        "telegram_list_chats",
        "telegram_read_chat",
        "telegram_block",
        "telegram_unblock",
        "telegram_clear_chat",
    } <= names
    for tool in tools:
        assert tool.category == "telegram"


@pytest.mark.asyncio
async def test_new_telegram_tools_fail_when_not_started():
    svc = TelegramService(api_id=1, api_hash="h")
    assert await svc.send_message_to("123", "hi") is False
    assert await svc.delete_messages("123", [1, 2]) is False
    assert await svc.delete_recent_own("123", 5) is False
    assert await svc.delete_messages("123", []) is False
    assert await svc.delete_recent_own("123", 0) is False
    assert await svc.block_user("123") is False
    assert await svc.unblock_user("123") is False
    assert await svc.clear_chat_history("123") is False
    assert await svc.list_chats() == "Telegram is not connected."
    assert await svc.read_chat("123") == "Telegram is not connected."


@pytest.mark.asyncio
async def test_permission_levels_per_tool():
    svc = TelegramService(api_id=1, api_hash="h")
    by_name = {t.name: t for t in svc.get_tools()}
    # Full-control tools run without confirmation; destructive ones confirm via callback.
    assert by_name["telegram_send_message"].permission_level == "auto"
    assert by_name["telegram_list_chats"].permission_level == "auto"
    assert by_name["telegram_read_chat"].permission_level == "auto"
    assert by_name["telegram_delete_messages"].permission_level == "confirm"
    assert by_name["telegram_block"].permission_level == "confirm"
    assert by_name["telegram_clear_chat"].permission_level == "confirm"


@pytest.mark.asyncio
async def test_resolve_target():
    svc = TelegramService(api_id=1, api_hash="h")
    assert await svc._resolve_target("123") == 123
    assert await svc._resolve_target("0001") == 1
    assert await svc._resolve_target("@username") == "@username"
    assert await svc._resolve_target("First Name") == "First Name"


def _fake_event(text: str = "", voice: bool = False, out: bool = False):
    message = type("Msg", (), {})()
    message.text = text
    message.out = out
    message.id = 7
    message.voice = {"duration": 2} if voice else None
    message.audio = None

    peer = type("Peer", (), {})()
    peer.id = 424242

    sender = type("Sender", (), {})()
    sender.id = 777
    sender.username = "test_user"

    event = type("Event", (), {})()
    event.message = message
    event.chat = peer
    event.sender = sender
    return event


def test_from_telethon_event_text():
    msg = TelegramInboundMessage.from_telethon_event(_fake_event(text="hello"))
    assert msg is not None
    assert msg.text == "hello"
    assert msg.platform == "telegram"
    assert msg.chat_id == "424242"
    assert msg.sender_id == "777"
    assert msg.recipient_id == "424242"
    assert not msg.is_command


def test_from_telethon_event_command():
    msg = TelegramInboundMessage.from_telethon_event(_fake_event(text="/help"))
    assert msg is not None
    assert msg.is_command


def test_from_telethon_event_voice():
    msg = TelegramInboundMessage.from_telethon_event(_fake_event(text="", voice=True))
    assert msg is not None
    assert msg.is_voice
    assert msg.text == ""


def test_from_telethon_event_outgoing_ignored():
    assert TelegramInboundMessage.from_telethon_event(_fake_event(text="hi", out=True)) is None


def test_from_telethon_event_empty_ignored():
    assert TelegramInboundMessage.from_telethon_event(_fake_event(text="")) is None


def test_service_manager_registers_telegram(tmp_path, monkeypatch):
    import yaml

    from core.config import ConfigManager

    monkeypatch.delenv("TELEGRAM_ENABLED", raising=False)
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USERS", raising=False)
    monkeypatch.delenv("TELEGRAM_OWNER_CHAT_ID", raising=False)

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "services": {
            "telegram": {
                "enabled": True,
                "api_id": 1,
                "api_hash": "h",
                "allowed_users": [1],
                "owner_chat_id": 2,
            }
        }
    }), encoding="utf-8")
    config = ConfigManager(config_path=cfg_path).config
    manager = ServiceManager(config)
    svc = manager.get("telegram")
    assert svc is not None
    assert isinstance(svc, TelegramService)
    assert svc.is_configured()
    assert svc.is_allowed_user("1")


def test_service_manager_skips_disabled_telegram(tmp_path, monkeypatch):
    import yaml

    from core.config import ConfigManager

    monkeypatch.delenv("TELEGRAM_ENABLED", raising=False)
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "services": {"telegram": {"enabled": False}}
    }), encoding="utf-8")
    config = ConfigManager(config_path=cfg_path).config
    manager = ServiceManager(config)
    assert manager.get("telegram") is None
