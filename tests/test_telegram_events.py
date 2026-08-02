from __future__ import annotations

import pytest

from core.services.telegram_events import TelegramEventHandler


class FakeService:
    def __init__(self, allowed_users: set, self_user_id: int = 0):
        self.allowed_users = allowed_users
        self.sent: list[tuple[str, str]] = []
        self._self_user_id = self_user_id
        self._sent_ids: set[int] = set()

    def is_allowed_user(self, user_id: str) -> bool:
        return int(user_id or 0) in self.allowed_users

    async def send_message(self, recipient_id: str, text: str) -> bool:
        self.sent.append((recipient_id, text))
        return True

    async def self_user_id(self) -> int:
        return self._self_user_id

    def was_sent_by_us(self, message_id: int) -> bool:
        return int(message_id) in self._sent_ids

    def mark_sent(self, message_id: int) -> None:
        self._sent_ids.add(int(message_id))


class FakeSession:
    def __init__(self):
        self.calls: list[str] = []
        self.personality_manager = FakePersonalityManager()
        self.service_manager = FakeServiceManager()
        self.memory_manager = FakeMemory()
        self.config = SimpleNamespace(llm=SimpleNamespace(model="openai/gpt-4o-mini"))
        self._user_sessions: dict[str, str] = {}
        self.conversation = FakeConversation()
        self.tool_dispatcher = None

    async def chat(self, text: str, user_id: str = "default") -> str:
        self.calls.append(text)
        return f"echo: {text}"

    def _ensure_user_session(self, user_id: str) -> str:
        sid = self._user_sessions.get(user_id)
        if not sid:
            sid = f"sid-{user_id}"
            self._user_sessions[user_id] = sid
        return sid


class SimpleNamespace:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeConversation:
    def __init__(self):
        self._cleared = False

    def load_session(self, sid: str) -> bool:
        return True

    def clear_history(self) -> None:
        self._cleared = True


class FakePersonalityManager:
    def __init__(self):
        self._active = SimpleNamespace(name="jarvis")

    def list_names(self):
        return ["jarvis", "kaaya"]

    def get(self, name: str):
        if name in ("jarvis", "kaaya"):
            return SimpleNamespace(name=name)
        return None

    def set_active(self, name: str):
        self._active = SimpleNamespace(name=name)
        return self._active

    def get_active(self):
        return self._active

    def get_sarvam_voice(self, name=None):
        return "tanya"


class FakeServiceManager:
    def __init__(self):
        self.services = {}

    def get(self, name: str):
        return self.services.get(name)

    async def health_report(self):
        return {"notes": {"ok": True, "detail": "ready"}}


class FakeMemory:
    def get_formatted_context(self, user_id: str = "default"):
        return "mem: favorite color is blue"


class FakeCalendar:
    def list_reminders(self):
        return [{"title": "Water plants", "time": "18:00"}]

    def format_reminders(self, reminders):
        return "Reminders:\n- Water plants at 18:00"


class FakeNotes:
    def list_notes(self):
        return [{"title": "Grocery", "content": "milk"}]

    def format_notes(self, notes):
        return "Notes:\n- Grocery"

    def list_todos(self):
        return [{"title": "Buy milk", "done": False}]

    def format_todos(self, todos):
        return "Todos:\n- [ ] Buy milk"


def _make_event(
    text: str,
    sender_id: int = 777,
    chat_id: int = 888,
    out: bool = False,
    message_id: int = 1,
):
    return SimpleNamespace(
        message=SimpleNamespace(
            text=text,
            out=out,
            id=message_id,
            voice=None,
            audio=None,
        ),
        chat=SimpleNamespace(id=chat_id),
        sender=SimpleNamespace(id=sender_id, username="test_user"),
    )


def _handler(service, session):
    return TelegramEventHandler(service, session)


@pytest.mark.asyncio
async def test_denied_user_silently_ignored():
    svc = FakeService(allowed_users={111})
    handler = _handler(svc, FakeSession())
    await handler.handle(_make_event("hi", sender_id=999))
    assert svc.sent == []


@pytest.mark.asyncio
async def test_allowed_user_chat():
    svc = FakeService(allowed_users={777})
    session = FakeSession()
    handler = _handler(svc, session)
    await handler.handle(_make_event("hello jarvis", sender_id=777))
    assert session.calls == ["hello jarvis"]
    assert svc.sent[-1][1] == "echo: hello jarvis"


@pytest.mark.asyncio
async def test_command_help():
    svc = FakeService(allowed_users={777})
    handler = _handler(svc, FakeSession())
    await handler.handle(_make_event("/help", sender_id=777))
    assert len(svc.sent) == 1
    assert "/personality" in svc.sent[0][1]


@pytest.mark.asyncio
async def test_command_unknown():
    svc = FakeService(allowed_users={777})
    handler = _handler(svc, FakeSession())
    await handler.handle(_make_event("/nope", sender_id=777))
    assert len(svc.sent) == 1
    assert "Unknown command" in svc.sent[0][1]


@pytest.mark.asyncio
async def test_command_personality_list_and_switch():
    svc = FakeService(allowed_users={777})
    session = FakeSession()
    handler = _handler(svc, session)
    await handler.handle(_make_event("/personality", sender_id=777))
    assert "jarvis" in svc.sent[-1][1]
    await handler.handle(_make_event("/personality kaaya", sender_id=777))
    assert svc.sent[-1][1] == "Switched to personality: kaaya"
    assert session.personality_manager._active.name == "kaaya"


@pytest.mark.asyncio
async def test_command_voice():
    svc = FakeService(allowed_users={777})
    handler = _handler(svc, FakeSession())
    await handler.handle(_make_event("/voice", sender_id=777))
    assert "tanya" in svc.sent[-1][1]


@pytest.mark.asyncio
async def test_command_services():
    svc = FakeService(allowed_users={777})
    handler = _handler(svc, FakeSession())
    await handler.handle(_make_event("/services", sender_id=777))
    assert "notes" in svc.sent[-1][1]


@pytest.mark.asyncio
async def test_command_notes_todos_remind():
    svc = FakeService(allowed_users={777})
    session = FakeSession()
    session.service_manager.services["notes"] = FakeNotes()
    session.service_manager.services["calendar"] = FakeCalendar()
    handler = _handler(svc, session)

    await handler.handle(_make_event("/notes", sender_id=777))
    assert "Grocery" in svc.sent[-1][1]
    await handler.handle(_make_event("/todos", sender_id=777))
    assert "Buy milk" in svc.sent[-1][1]
    await handler.handle(_make_event("/remind", sender_id=777))
    assert "Water plants" in svc.sent[-1][1]


@pytest.mark.asyncio
async def test_command_memory():
    svc = FakeService(allowed_users={777})
    handler = _handler(svc, FakeSession())
    await handler.handle(_make_event("/memory", sender_id=777))
    assert "favorite color" in svc.sent[-1][1]


@pytest.mark.asyncio
async def test_voice_unsupported():
    svc = FakeService(allowed_users={777})
    handler = _handler(svc, FakeSession())
    event = _make_event("", sender_id=777)
    event.message.voice = {"duration": 2}
    await handler.handle(event)
    assert len(svc.sent) == 1
    assert "not supported" in svc.sent[0][1]


@pytest.mark.asyncio
async def test_service_attach_and_handler_registration():
    from core.services import TelegramService

    svc = TelegramService(api_id=1, api_hash="h")
    handler = _handler(FakeService(allowed_users={777}), FakeSession())
    svc.attach_event_handler(handler)
    assert svc._event_handler is handler


@pytest.mark.asyncio
async def test_saved_messages_command_processed():
    svc = FakeService(allowed_users={7851880881}, self_user_id=7851880881)
    session = FakeSession()
    handler = _handler(svc, session)
    await handler.handle(
        _make_event(
            "open youtube",
            sender_id=7851880881,
            chat_id=7851880881,
            out=True,
        )
    )
    assert session.calls == ["open youtube"]
    assert svc.sent[-1][1] == "echo: open youtube"


@pytest.mark.asyncio
async def test_saved_messages_slash_command():
    svc = FakeService(allowed_users={7851880881}, self_user_id=7851880881)
    handler = _handler(svc, FakeSession())
    await handler.handle(
        _make_event(
            "/notes",
            sender_id=7851880881,
            chat_id=7851880881,
            out=True,
        )
    )
    assert len(svc.sent) == 1
    assert "Notes service unavailable" in svc.sent[-1][1]


@pytest.mark.asyncio
async def test_own_reply_to_saved_messages_ignored():
    svc = FakeService(allowed_users={7851880881}, self_user_id=7851880881)
    svc.mark_sent(55)
    session = FakeSession()
    handler = _handler(svc, session)
    await handler.handle(
        _make_event(
            "open youtube",
            sender_id=7851880881,
            chat_id=7851880881,
            out=True,
            message_id=55,
        )
    )
    assert session.calls == []
    assert svc.sent == []


@pytest.mark.asyncio
async def test_outgoing_in_normal_chat_still_ignored():
    svc = FakeService(allowed_users={777})
    session = FakeSession()
    handler = _handler(svc, session)
    await handler.handle(_make_event("hi", sender_id=777, out=True))
    assert session.calls == []
    assert svc.sent == []
