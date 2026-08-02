from __future__ import annotations

import asyncio

import pytest

from core.services.telegram_confirmation import ConfirmationManager
from core.tools import PermissionManager, ToolDispatcher, ToolRegistry
from core.tools.base import Tool, ToolResult


class EchoTool(Tool):
    def __init__(self, name="echo", permission_level="confirm"):
        super().__init__(
            name=name,
            description="echo",
            input_schema={"type": "object", "properties": {}},
            permission_level=permission_level,
        )

    async def execute(self, **kwargs):
        return ToolResult(success=True, output="echoed")


def test_permission_level_resolution():
    pm = PermissionManager({"echo": "deny"})
    assert pm.get_permission_level("echo") == "deny"
    pm = PermissionManager()
    assert pm.get_permission_level("echo", "confirm") == "confirm"
    assert pm.is_dangerous("execute_command")
    assert not pm.is_dangerous("echo")


@pytest.mark.asyncio
async def test_dispatcher_deny_without_confirmation():
    registry = ToolRegistry()
    registry.register(EchoTool())
    dispatcher = ToolDispatcher(registry, PermissionManager())
    result = await dispatcher.dispatch("echo", {})
    assert not result.success
    assert "cancelled" in result.error


@pytest.mark.asyncio
async def test_dispatcher_sync_confirm_yes():
    registry = ToolRegistry()
    registry.register(EchoTool())
    dispatcher = ToolDispatcher(
        registry, PermissionManager(), confirm_callback=lambda name, args: True
    )
    result = await dispatcher.dispatch("echo", {})
    assert result.success


@pytest.mark.asyncio
async def test_dispatcher_auto_level_skips_confirm():
    registry = ToolRegistry()
    registry.register(EchoTool(permission_level="auto"))
    dispatcher = ToolDispatcher(registry, PermissionManager())
    result = await dispatcher.dispatch("echo", {})
    assert result.success


@pytest.mark.asyncio
async def test_confirmation_manager_flow():
    sent = []

    class FakeService:
        async def send_message(self, chat_id, text):
            sent.append((chat_id, text))
            return True

    svc = FakeService()
    cm = ConfirmationManager(svc, timeout=5)
    assert not cm.has_pending("1")

    async def run():
        result = await cm.request("1", "close_app", {"app": "calc"})
        return result

    async def reply():
        await asyncio.sleep(0.05)
        assert await cm.resolve("1", "yes")

    req = asyncio.ensure_future(run())
    await asyncio.sleep(0)
    assert cm.has_pending("1")
    await reply()
    assert await req is True
    assert not cm.has_pending("1")
    assert sent[0][1].startswith("Allow this action?")


@pytest.mark.asyncio
async def test_confirmation_manager_no():
    class FakeService:
        async def send_message(self, chat_id, text):
            return True

    cm = ConfirmationManager(FakeService(), timeout=5)

    async def run():
        return await cm.request("2", "delete_file", {"path": "/tmp/x"})

    async def reply():
        await asyncio.sleep(0.05)
        assert await cm.resolve("2", "nope")

    req = asyncio.ensure_future(run())
    await asyncio.sleep(0)
    await reply()
    assert await req is False


@pytest.mark.asyncio
async def test_confirmation_manager_timeout():
    class FakeService:
        async def send_message(self, chat_id, text):
            return True

    cm = ConfirmationManager(FakeService(), timeout=0.05)
    assert await cm.request("3", "shutdown", {}) is False
    assert not cm.has_pending("3")


@pytest.mark.asyncio
async def test_handler_confirmation_flow():
    from core.services.telegram_confirmation import ConfirmationManager
    from core.services.telegram_events import TelegramEventHandler

    sent = []

    class FakeService:
        async def send_message(self, chat_id, text):
            sent.append((chat_id, text))
            return True

    sent2 = []

    class FakeService2:
        def is_allowed_user(self, user_id):
            return True

        async def send_message(self, chat_id, text):
            sent2.append((chat_id, text))
            return True

        def was_sent_by_us(self, message_id):
            return False

    # Fake session whose chat() triggers an async confirm on the dispatcher.
    from core.tools import PermissionManager, ToolDispatcher, ToolRegistry

    registry = ToolRegistry()
    registry.register(EchoTool())

    class FakeJarvisSession:
        def __init__(self):
            self.dispatcher = ToolDispatcher(registry, PermissionManager())
            self.tool_dispatcher = self.dispatcher

        async def chat(self, text, user_id="default"):
            return await self.dispatcher.dispatch("echo", {})

    cm = ConfirmationManager(FakeService(), timeout=5)
    handler = TelegramEventHandler(FakeService2(), FakeJarvisSession(), confirmation_manager=cm)

    def _event(text):
        return type("E", (), {
            "message": type("M", (), {
                "text": text, "out": False, "id": 1, "voice": None, "audio": None
            })(),
            "chat": type("C", (), {"id": 424242})(),
            "sender": type("S", (), {"id": 777, "username": "u"})(),
        })()

    async def drive():
        task = asyncio.ensure_future(handler.handle(_event("do it")))
        await asyncio.sleep(0)
        await cm.resolve("424242", "yes")
        await task

    await drive()
    # The pending confirmation was resolved as yes, so echo ran; a reply was sent.
    assert sent2, "expected a final reply"
