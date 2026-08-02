from __future__ import annotations

import pytest

from core.services.telegram_runner import _sarvam_api_key


def test_sarvam_key_from_config():
    class Sarvam:
        api_key = "cfg-key"

    class Config:
        sarvam = Sarvam()

    assert _sarvam_api_key(Config()) == "cfg-key"


def test_sarvam_key_falls_back_to_env(monkeypatch):
    class Sarvam:
        api_key = ""

    class Config:
        sarvam = Sarvam()

    monkeypatch.setenv("SARVAM_API_KEY", "env-key")
    assert _sarvam_api_key(Config()) == "env-key"


def test_sarvam_key_missing_config():
    class Config:
        pass

    assert _sarvam_api_key(Config()) == ""


@pytest.mark.asyncio
async def test_runner_requires_telegram_service(tmp_path, monkeypatch):
    import yaml

    from core.services.telegram_runner import run_telegram

    monkeypatch.delenv("TELEGRAM_ENABLED", raising=False)
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "services": {
            "enabled": True,
            "telegram": {"enabled": False},
        },
        "tool": {"enabled": False},
    }), encoding="utf-8")

    with pytest.raises(RuntimeError, match="not enabled"):
        await run_telegram(config_path=cfg_path)
