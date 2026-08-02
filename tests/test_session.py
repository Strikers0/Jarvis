from __future__ import annotations

import pytest

from core.session import JarvisSession


async def _cleanup(session):
    await session.cleanup()


@pytest.fixture
def session(tmp_path):
    return JarvisSession(create_conversation=True)


def test_init_active_personality(session):
    assert session.get_active_personality() in ("jarvis",)


def test_system_prompt_buildable(session):
    prompt = session.get_system_prompt(user_id="testuser")
    assert "JARVIS" in prompt or "assistant" in prompt.lower()


def test_per_user_sessions_isolated(tmp_path):
    import asyncio

    s = JarvisSession(create_conversation=True)
    id_a = s._ensure_user_session("alice")
    s.conversation.add_message(__import__("core.llm", fromlist=["LLMMessage"]).LLMMessage(
        role="user", content="hello from alice"
    ))
    id_b = s._ensure_user_session("bob")
    assert id_a != id_b
    assert len(s.conversation.get_history()) == 0
    s._ensure_user_session("alice")
    assert len(s.conversation.get_history()) == 1
    asyncio.run(_cleanup(s))


@pytest.mark.asyncio
async def test_health_report_empty_without_services(tmp_path):
    import yaml

    from core.session import JarvisSession

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "services": {"enabled": False},
        "tool": {"enabled": False},
        "memory": {"enabled": False},
    }), encoding="utf-8")
    s = JarvisSession(config_path=cfg_path)
    report = await s.health_report()
    assert report == {}
    await _cleanup(s)
