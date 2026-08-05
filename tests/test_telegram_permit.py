from __future__ import annotations

import pytest

from core.services.telegram_events import TelegramEventHandler
from core.tools.base import PermissionManager, Tool, ToolResult


def _stub_tool(name: str, level: str = "confirm"):
    class T(Tool):
        async def execute(self, **kwargs):
            return ToolResult(success=True)

    t = T(name=name, description=name, input_schema={"type": "object"}, permission_level=level)
    return t


class _Registry:
    def __init__(self, tools):
        self._tools = {t.name: t for t in tools}

    def list_tools(self):
        return list(self._tools.values())

    def get(self, name):
        return self._tools.get(name)


class _Session:
    def __init__(self, tools):
        self.tool_registry = _Registry(tools)
        self.permission_manager = PermissionManager()


class _Msg:
    def __init__(self, sender_id="1"):
        self.sender_id = sender_id
        self.recipient_id = "1"


@pytest.mark.asyncio
async def test_permit_lists_tools_with_levels():
    handler = TelegramEventHandler(
        service=None,
        session=_Session([_stub_tool("alpha", "confirm"), _stub_tool("beta", "auto")]),
    )
    out = await handler._cmd_permit_tools(_Msg(), "")
    assert "alpha: confirm" in out
    assert "beta: auto" in out


@pytest.mark.asyncio
async def test_permit_sets_level():
    handler = TelegramEventHandler(
        service=None, session=_Session([_stub_tool("alpha", "confirm")])
    )
    out = await handler._cmd_permit(_Msg(), "alpha deny")
    assert out == "Set 'alpha' permission to deny."
    assert handler.session.permission_manager.get_permission_level("alpha") == "deny"


@pytest.mark.asyncio
async def test_permit_no_args_lists_tools():
    handler = TelegramEventHandler(
        service=None, session=_Session([_stub_tool("alpha", "confirm")])
    )
    out = await handler._cmd_permit(_Msg(), "")
    assert "alpha: confirm" in out


@pytest.mark.asyncio
async def test_permit_rejects_unknown_tool():
    handler = TelegramEventHandler(service=None, session=_Session([]))
    out = await handler._cmd_permit(_Msg(), "nope auto")
    assert "Unknown tool" in out


@pytest.mark.asyncio
async def test_permit_rejects_bad_level():
    handler = TelegramEventHandler(
        service=None, session=_Session([_stub_tool("alpha", "confirm")])
    )
    out = await handler._cmd_permit(_Msg(), "alpha atomic")
    assert "must be one of" in out


@pytest.mark.asyncio
async def test_text_uses_auto_confirm():
    handler = TelegramEventHandler(service=None, session=_Session([]))
    cb = handler._make_auto_confirm_callback()
    assert await cb("telegram_delete_recent", {}) is True


@pytest.mark.asyncio
async def test_voice_uses_real_confirm():
    class Conf:
        def __init__(self):
            self.calls = 0

        async def request(self, chat_id, tool_name, args):
            self.calls += 1
            return False

    conf = Conf()
    handler = TelegramEventHandler(
        service=None,
        session=_Session([]),
        confirmation_manager=conf,
    )
    msg = _Msg()
    cb = handler._make_confirm_callback(msg)
    result = await cb("telegram_block", {"chat_lookup": "x"})
    assert result is False
    assert conf.calls == 1