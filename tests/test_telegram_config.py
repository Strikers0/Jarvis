from __future__ import annotations

import sys
import types

import pytest

from core.config import ConfigManager
from core.services.telegram_client import TelegramClientFactory


def test_telegram_config_defaults():
    config = ConfigManager(config_path="nonexistent.yaml").config
    t = config.services.telegram
    assert t.enabled is False
    assert t.api_id == 0
    assert t.api_hash == ""
    assert t.session_name == "jarvis_telegram"
    assert t.allowed_users == []
    assert t.owner_chat_id == 0
    assert t.voice_enabled is True


def test_telegram_config_env_overrides(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc123")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "111, 222,333")
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_ID", "999")
    monkeypatch.setenv("TELEGRAM_VOICE_ENABLED", "false")
    config = ConfigManager(config_path="nonexistent.yaml").config
    t = config.services.telegram
    assert t.enabled is True
    assert t.api_id == 12345
    assert t.api_hash == "abc123"
    assert t.allowed_users == [111, 222, 333]
    assert t.owner_chat_id == 999
    assert t.voice_enabled is False


def test_factory_requires_credentials():
    TelegramClientFactory.reset()
    with pytest.raises(ValueError):
        TelegramClientFactory.create(0, "")


def test_factory_requires_telethon(monkeypatch):
    TelegramClientFactory.reset()
    monkeypatch.delitem(sys.modules, "telethon", raising=False)

    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "telethon":
            raise ImportError("No module named 'telethon'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="Telethon is not installed"):
        TelegramClientFactory.create(1, "hash")
    TelegramClientFactory.reset()


def test_factory_caches_singleton(monkeypatch):
    TelegramClientFactory.reset()
    calls = {"n": 0}

    class FakeTelegramClient:
        def __init__(self, session, api_id, api_hash):
            calls["n"] += 1
            self.session = session

    mod = types.ModuleType("telethon")
    mod.TelegramClient = FakeTelegramClient
    monkeypatch.setitem(sys.modules, "telethon", mod)

    client1 = TelegramClientFactory.create(1, "hash", "sess")
    client2 = TelegramClientFactory.create(1, "hash", "sess")
    assert client1 is client2
    assert calls["n"] == 1
    TelegramClientFactory.reset()
