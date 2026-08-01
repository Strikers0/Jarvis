from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from core.config import ConfigManager
from core.services import (
    CalendarService,
    CallingService,
    EmailService,
    NotesService,
    ServiceManager,
    service_tool,
)
from core.services.calendar import parse_datetime
from core.tools.base import PermissionManager, ToolDispatcher, ToolRegistry


@pytest.fixture
def notes(tmp_path):
    return NotesService(db_path=tmp_path / "notes.db")


@pytest.fixture
def calendar(tmp_path):
    return CalendarService(db_path=tmp_path / "calendar.db")


@pytest.fixture
def calling(tmp_path):
    return CallingService(db_path=tmp_path / "calls.db")


# ---- parse_datetime ----

@pytest.mark.parametrize(
    "value",
    [
        "2026-08-05 10:30",
        "2026-08-05T14:00:00",
        "tomorrow at 10am",
        "tomorrow at 9:30pm",
        "today at 5pm",
        "in 2 hours",
        "in 30 minutes",
        "next friday at 3pm",
        "5/12/2026",
    ],
)
def test_parse_datetime_valid(value):
    dt = parse_datetime(value)
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_datetime_tomorrow():
    base = datetime(2026, 8, 1, 12, 0)
    dt = parse_datetime("tomorrow at 10am", base=base)
    assert dt is not None
    assert dt.day == 2
    assert dt.hour == 10
    assert dt.minute == 0


def test_parse_datetime_invalid():
    assert parse_datetime("") is None
    assert parse_datetime("not a date") is None


# ---- NotesService ----

def test_notes_crud(notes):
    note_id = notes.create_note("Groceries", "milk, eggs", ["errands"])
    assert notes.get_note(note_id)["title"] == "Groceries"
    found = notes.search_notes("milk")
    assert len(found) == 1
    assert notes.update_note(note_id, title="Groceries Updated")
    assert notes.get_note(note_id)["title"] == "Groceries Updated"
    assert notes.delete_note(note_id)
    assert notes.get_note(note_id) is None


def test_todos_crud(notes):
    todo_id = notes.create_todo("Ship feature", "tomorrow at 5pm", "high")
    todos = notes.list_todos("pending")
    assert len(todos) == 1
    assert todos[0]["priority"] == "high"
    assert notes.update_todo(todo_id, done=True)
    assert notes.list_todos("done")[0]["done"] is True
    assert notes.delete_todo(todo_id)
    assert notes.list_todos() == []


def test_notes_tools_registered(notes):
    names = {t.name for t in notes.get_tools()}
    assert {"create_note", "list_notes", "search_notes", "create_todo", "list_todos", "mark_todo"} <= names


# ---- CalendarService ----

def test_create_and_list_events(calendar):
    event_id = calendar.create_event("Standup", "tomorrow at 9am")
    events = calendar.list_events("week")
    assert len(events) == 1
    assert events[0]["id"] == event_id
    assert calendar.search_events("standup")[0]["title"] == "Standup"
    assert calendar.delete_event(event_id)
    assert calendar.list_events() == []


def test_create_event_invalid_time(calendar):
    with pytest.raises(ValueError):
        calendar.create_event("Bad", "not a time")


def test_reminders(calendar):
    reminder_id = calendar.create_reminder("Drink water", "2020-01-01 10:00")
    due = calendar.check_due_reminders()
    assert len(due) == 1
    assert due[0]["id"] == reminder_id
    assert calendar.check_due_reminders() == []
    assert calendar.delete_reminder(reminder_id)
    assert calendar.list_reminders() == []


# ---- EmailService ----

def test_email_not_configured(monkeypatch):
    monkeypatch.delenv("EMAIL_USERNAME", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
    service = EmailService()
    assert not service.is_configured()


@pytest.mark.asyncio
async def test_email_send_not_configured(monkeypatch):
    monkeypatch.delenv("EMAIL_USERNAME", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
    service = EmailService()
    result = await service.send_email("a@b.com", "hi", "body")
    assert not result.success
    assert "not configured" in result.error


def test_email_format_list():
    items = [{"id": "1", "subject": "Hello", "from": "x@y.z", "date": "now", "body": "Body text"}]
    out = EmailService.format_email_list(items)
    assert "Hello" in out
    assert "x@y.z" in out


# ---- CallingService ----

def test_contacts(calling):
    calling.save_contact("Mom", "+15551234567")
    assert calling.lookup_contact("Mom") == "+15551234567"
    assert calling.lookup_contact("+15551234567") == "+15551234567"
    assert calling.lookup_contact("unknown person") is None
    assert calling.list_contacts()[0]["name"] == "Mom"


@pytest.mark.asyncio
async def test_make_call_no_provider(calling):
    result = await calling.make_call("Mom")
    assert not result.success
    assert "No calling provider configured" in result.error
    assert len(calling.call_logs()) == 1


# ---- service_tool wrapper ----

def test_service_tool_sync_handler():
    def handler(x: int = 1) -> str:
        return f"got {x}"

    tool = service_tool(
        name="test_sync",
        description="test",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=handler,
        permission_level="auto",
    )
    assert tool.name == "test_sync"


@pytest.mark.asyncio
async def test_service_tool_async_handler():
    async def handler(x: int = 1) -> str:
        await asyncio.sleep(0)
        return f"async {x}"

    tool = service_tool(
        name="test_async",
        description="test",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=handler,
        permission_level="auto",
    )
    result = await tool.execute(x=5)
    assert result.success
    assert result.output == "async 5"


@pytest.mark.asyncio
async def test_service_tool_error():
    def handler():
        raise ValueError("boom")

    tool = service_tool(
        name="test_error",
        description="test",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=handler,
        permission_level="auto",
    )
    result = await tool.execute()
    assert not result.success
    assert "boom" in result.error


# ---- ServiceManager integration ----

@pytest.mark.asyncio
async def test_service_manager(tmp_path):
    cm = ConfigManager(config_path=str(tmp_path / "nope.yaml"))
    sm = ServiceManager(cm.config)
    assert {"notes", "email", "calendar", "external", "calling"} <= set(sm.list_names())
    assert sm.get("notes") is not None

    registry = ToolRegistry()
    registry.register_set(sm)
    dispatcher = ToolDispatcher(registry, PermissionManager())

    result = await dispatcher.dispatch("create_note", {"title": "From manager"})
    assert result.success

    health = await sm.health_report()
    assert set(health) == set(sm.list_names())
    await sm.close()


def test_config_loads_services_section():
    cm = ConfigManager()
    svc = cm.config.services
    assert svc.notes.db_path.endswith("notes.db")
    assert svc.calendar.provider in ("local", "google")
