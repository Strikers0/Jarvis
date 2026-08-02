from __future__ import annotations

import asyncio

import pytest

from core.services.telegram_reminders import ReminderPoller


class FakeCalendar:
    def __init__(self, due=None, enabled=True):
        self._due = due or []
        self.reminders_enabled = enabled
        self.calls = 0

    def check_due_reminders(self):
        self.calls += 1
        due, self._due = self._due, []
        return due


class FakeService:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))
        return True


def test_enabled_logic():
    assert ReminderPoller(FakeCalendar(), FakeService(), owner_chat_id=123).enabled
    assert not ReminderPoller(FakeCalendar(), FakeService(), owner_chat_id=0).enabled
    assert not ReminderPoller(FakeCalendar(enabled=False), FakeService(), owner_chat_id=123).enabled
    assert not ReminderPoller(FakeCalendar(), None, owner_chat_id=123).enabled


@pytest.mark.asyncio
async def test_poll_once_pushes_to_owner_and_allowed():
    cal = FakeCalendar(due=[{"id": "r1", "title": "Water plants", "remind_at": "2026-08-01T18:00"}])
    svc = FakeService()
    poller = ReminderPoller(cal, svc, owner_chat_id=123, allowed_users=[456])
    pushed = await poller.poll_once()
    assert len(pushed) == 1
    assert ("123", "⏰ Reminder: Water plants") in svc.sent
    assert ("456", "⏰ Reminder: Water plants") in svc.sent


@pytest.mark.asyncio
async def test_poll_once_no_due():
    cal = FakeCalendar(due=[])
    svc = FakeService()
    poller = ReminderPoller(cal, svc, owner_chat_id=123)
    assert await poller.poll_once() == []
    assert svc.sent == []


@pytest.mark.asyncio
async def test_poll_once_not_enabled():
    svc = FakeService()
    poller = ReminderPoller(FakeCalendar(due=[{"id": "r", "title": "x"}]), svc, owner_chat_id=0)
    assert await poller.poll_once() == []
    assert svc.sent == []


@pytest.mark.asyncio
async def test_poll_once_calendar_error():
    class BadCalendar(FakeCalendar):
        def check_due_reminders(self):
            raise RuntimeError("db locked")

    svc = FakeService()
    poller = ReminderPoller(BadCalendar(), svc, owner_chat_id=123)
    assert await poller.poll_once() == []
    assert svc.sent == []


@pytest.mark.asyncio
async def test_poller_start_stop():
    cal = FakeCalendar(due=[{"id": "r1", "title": "Stretch", "remind_at": "now"}])
    svc = FakeService()
    poller = ReminderPoller(cal, svc, owner_chat_id=123, interval=0.01)
    poller.start()
    assert poller._task is not None
    await asyncio.sleep(0.1)
    await poller.stop()
    assert not poller._running
    assert svc.sent, "expected at least one push from the loop"
