from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

from core.services.base import Service, service_tool
from core.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)
_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})")
_DATE_ONLY_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DMY_RE = re.compile(r"(\d{1,2})[-/](\d{1,2})(?:[-/](\d{2,4}))?")


def _local_now() -> datetime:
    return datetime.now().astimezone()


def parse_datetime(value: str, base: Optional[datetime] = None) -> Optional[datetime]:
    """Parse common natural-language datetimes into a timezone-aware datetime."""
    if not value or not value.strip():
        return None
    base = base or _local_now()
    text = value.strip().lower()

    if _ISO_RE.search(text):
        m = _ISO_RE.search(text)
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)),
            tzinfo=base.tzinfo,
        )

    dt: Optional[datetime] = None

    def _apply_time(d: datetime) -> datetime:
        tm = _TIME_RE.search(text)
        if tm:
            hour = int(tm.group(1)) % 12
            minute = int(tm.group(2) or 0)
            if tm.group(3).lower() == "pm":
                hour += 12
            return d.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return d

    if "tomorrow" in text:
        dt = _apply_time(base + timedelta(days=1))
    elif "tonight" in text:
        dt = base.replace(hour=20, minute=0, second=0, microsecond=0)
    elif "today" in text:
        dt = _apply_time(base)
    elif text.startswith("in "):
        m = re.search(r"in\s+(\d+)\s*(minute|minutes|hour|hours|day|days|week|weeks|month|months)?", text)
        if m:
            n = int(m.group(1))
            unit = m.group(2) or "minutes"
            delta = {
                "minute": timedelta(minutes=n), "minutes": timedelta(minutes=n),
                "hour": timedelta(hours=n), "hours": timedelta(hours=n),
                "day": timedelta(days=n), "days": timedelta(days=n),
                "week": timedelta(weeks=n), "weeks": timedelta(weeks=n),
                "month": timedelta(days=30 * n), "months": timedelta(days=30 * n),
            }.get(unit, timedelta(minutes=n))
            dt = _apply_time(base + delta)
    else:
        for name, wd in _WEEKDAYS.items():
            if name in text:
                days_ahead = (wd - base.weekday()) % 7
                if "next" in text:
                    days_ahead += 7
                if days_ahead == 0 and "next" not in text:
                    days_ahead = 7
                dt = _apply_time(base + timedelta(days=days_ahead))
                break

    if dt is None and _DATE_ONLY_RE.search(text):
        m = _DATE_ONLY_RE.search(text)
        dt = _apply_time(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=base.tzinfo))
    if dt is None and _DMY_RE.search(text):
        m = _DMY_RE.search(text)
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else base.year
        if year < 100:
            year += 2000
        try:
            dt = _apply_time(datetime(year, month, day, tzinfo=base.tzinfo))
        except ValueError:
            return None

    if dt is None and _TIME_RE.search(text):
        dt = _apply_time(base)
        if dt <= base:
            dt += timedelta(days=1)

    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=base.tzinfo)
    return dt


class GoogleCalendarClient:
    """OAuth2 client for the Google Calendar API via httpx."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_URL = "https://www.googleapis.com/calendar/v3"

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        refresh_token: str = "",
        calendar_id: str = "primary",
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.calendar_id = calendar_id
        self._access_token: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    async def _token(self) -> str:
        if self._access_token:
            return self._access_token
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            self._access_token = resp.json().get("access_token")
        if not self._access_token:
            raise RuntimeError("Failed to obtain Google access token")
        return self._access_token

    async def list_events(self, time_min: str, time_max: str, max_results: int = 10) -> list[dict]:
        token = await self._token()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{self.API_URL}/calendars/{self.calendar_id}/events",
                params={
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "maxResults": max_results,
                    "singleEvents": "true",
                    "orderBy": "startTime",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
        items = []
        for ev in resp.json().get("items", []):
            items.append({
                "id": ev.get("id", ""),
                "title": ev.get("summary", ""),
                "description": ev.get("description", ""),
                "start": ev.get("start", {}).get("dateTime", ev.get("start", {}).get("date", "")),
                "end": ev.get("end", {}).get("dateTime", ev.get("end", {}).get("date", "")),
                "location": ev.get("location", ""),
            })
        return items

    async def create_event(self, title: str, start: str, end: str, description: str = "", location: str = "") -> str:
        token = await self._token()
        body = {
            "summary": title,
            "description": description or None,
            "location": location or None,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{self.API_URL}/calendars/{self.calendar_id}/events",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
        return resp.json().get("id", "")

    async def delete_event(self, event_id: str) -> bool:
        token = await self._token()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.delete(
                f"{self.API_URL}/calendars/{self.calendar_id}/events/{event_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.status_code in (200, 204)


class CalendarService(Service):
    """Calendar events and reminders. Local SQLite by default, optional Google Calendar sync."""

    name = "calendar"
    description = "Manage calendar events and reminders (local storage, optional Google Calendar)."

    def __init__(
        self,
        db_path: str | Path = "calendar.db",
        provider: str = "local",
        google: Optional[GoogleCalendarClient] = None,
        reminders_enabled: bool = True,
    ):
        self.db_path = Path(db_path)
        self.provider = provider
        self.google = google
        self.reminders_enabled = reminders_enabled
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                start_time TEXT NOT NULL,
                end_time TEXT,
                attendees_json TEXT NOT NULL DEFAULT '[]',
                google_id TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                event_id TEXT,
                notified INTEGER NOT NULL DEFAULT 0,
                created_at TEXT
            )
        """)
        self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat()

    # ---- local events ----

    def create_event(
        self,
        title: str,
        start: str,
        end: str = "",
        description: str = "",
        location: str = "",
        attendees: Optional[list[str]] = None,
    ) -> str:
        return self._store_event_locally(title, start, end, description, location, attendees)

    async def create_event_async(
        self,
        title: str,
        start: str,
        end: str = "",
        description: str = "",
        location: str = "",
        attendees: Optional[list[str]] = None,
    ) -> str:
        start_dt = parse_datetime(start)
        if not start_dt:
            raise ValueError(f"Could not parse start datetime: {start}")
        end_dt = parse_datetime(end) or start_dt + timedelta(hours=1)
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(hours=1)

        google_id = ""
        if self.google and self.google.is_configured():
            try:
                google_id = await self.google.create_event(
                    title, start_dt.isoformat(), end_dt.isoformat(), description, location,
                )
            except Exception as e:
                logger.warning("Google Calendar create failed, storing locally: %s", e)

        event_id = str(uuid.uuid4())
        now = self._now()
        self._conn.execute(
            "INSERT INTO events (id, title, description, location, start_time, end_time, attendees_json, google_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id, title, description, location,
                start_dt.isoformat(), end_dt.isoformat(),
                json.dumps(attendees or []), google_id, now, now,
            ),
        )
        self._conn.commit()
        return event_id

    def _store_event_locally(
        self,
        title: str,
        start: str,
        end: str = "",
        description: str = "",
        location: str = "",
        attendees: Optional[list[str]] = None,
    ) -> str:
        start_dt = parse_datetime(start)
        if not start_dt:
            raise ValueError(f"Could not parse start datetime: {start}")
        end_dt = parse_datetime(end) or start_dt + timedelta(hours=1)
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(hours=1)

        event_id = str(uuid.uuid4())
        now = self._now()
        self._conn.execute(
            "INSERT INTO events (id, title, description, location, start_time, end_time, attendees_json, google_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id, title, description, location,
                start_dt.isoformat(), end_dt.isoformat(),
                json.dumps(attendees or []), "", now, now,
            ),
        )
        self._conn.commit()
        return event_id

    def list_events(self, date_range: str = "week", limit: int = 20) -> list[dict]:
        now = _local_now()
        if date_range == "day":
            start, end = now, now + timedelta(days=1)
        elif date_range == "month":
            start, end = now, now + timedelta(days=30)
        else:
            start, end = now, now + timedelta(days=7)
        rows = self._conn.execute(
            "SELECT id, title, description, location, start_time, end_time, attendees_json, google_id FROM events WHERE start_time >= ? AND start_time < ? ORDER BY start_time ASC LIMIT ?",
            (start.isoformat(), end.isoformat(), limit),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def search_events(self, query: str, limit: int = 20) -> list[dict]:
        pattern = f"%{query}%"
        rows = self._conn.execute(
            "SELECT id, title, description, location, start_time, end_time, attendees_json, google_id FROM events WHERE title LIKE ? OR description LIKE ? OR location LIKE ? ORDER BY start_time ASC LIMIT ?",
            (pattern, pattern, pattern, limit),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_event(self, event_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT id, title, description, location, start_time, end_time, attendees_json, google_id FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        return self._row_to_event(row) if row else None

    def delete_event(self, event_id: str) -> bool:
        event = self.get_event(event_id)
        if not event:
            return False
        self._conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        self._conn.execute("DELETE FROM reminders WHERE event_id = ?", (event_id,))
        self._conn.commit()
        return True

    async def delete_event_async(self, event_id: str) -> bool:
        event = self.get_event(event_id)
        if not event:
            return False
        if event.get("google_id") and self.google and self.google.is_configured():
            try:
                await self.google.delete_event(event["google_id"])
            except Exception as e:
                logger.warning("Google Calendar delete failed: %s", e)
        self._conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        self._conn.execute("DELETE FROM reminders WHERE event_id = ?", (event_id,))
        self._conn.commit()
        return True

    def _row_to_event(self, row: tuple) -> dict:
        return {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "location": row[3],
            "start": row[4],
            "end": row[5],
            "attendees": json.loads(row[6]) if row[6] else [],
            "google_id": row[7],
        }

    # ---- reminders ----

    def create_reminder(self, title: str, remind_at: str) -> str:
        dt = parse_datetime(remind_at)
        if not dt:
            raise ValueError(f"Could not parse reminder time: {remind_at}")
        reminder_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO reminders (id, title, remind_at, notified, created_at) VALUES (?, ?, ?, 0, ?)",
            (reminder_id, title, dt.isoformat(), self._now()),
        )
        self._conn.commit()
        return reminder_id

    def list_reminders(self, upcoming_only: bool = True, limit: int = 20) -> list[dict]:
        if upcoming_only:
            rows = self._conn.execute(
                "SELECT id, title, remind_at, notified FROM reminders WHERE remind_at >= ? ORDER BY remind_at ASC LIMIT ?",
                (_local_now().isoformat(), limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, title, remind_at, notified FROM reminders ORDER BY remind_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": r[0], "title": r[1], "remind_at": r[2], "notified": bool(r[3])}
            for r in rows
        ]

    def delete_reminder(self, reminder_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def check_due_reminders(self) -> list[dict]:
        """Return reminders whose time has arrived and mark them notified."""
        now = _local_now().isoformat()
        rows = self._conn.execute(
            "SELECT id, title, remind_at FROM reminders WHERE remind_at <= ? AND notified = 0 ORDER BY remind_at ASC",
            (now,),
        ).fetchall()
        due = [{"id": r[0], "title": r[1], "remind_at": r[2]} for r in rows]
        if due:
            ids = [r["id"] for r in due]
            self._conn.executemany(
                "UPDATE reminders SET notified = 1 WHERE id = ?",
                [(i,) for i in ids],
            )
            self._conn.commit()
        return due

    # ---- presentation ----

    @staticmethod
    def format_events(events: list[dict]) -> str:
        if not events:
            return "No events found."
        lines = []
        for ev in events:
            start = ev["start"].replace("T", " ")[:16]
            lines.append(f"[{ev['id'][:8]}] {ev['title']} at {start} ({ev.get('location', '')})")
        return "\n".join(lines)

    @staticmethod
    def format_reminders(reminders: list[dict]) -> str:
        if not reminders:
            return "No reminders found."
        lines = []
        for r in reminders:
            at = r["remind_at"].replace("T", " ")[:16]
            notified = " (notified)" if r.get("notified") else ""
            lines.append(f"[{r['id'][:8]}] {r['title']} at {at}{notified}")
        return "\n".join(lines)

    # ---- tools ----

    def get_tools(self) -> list[Tool]:
        return [
            service_tool(
                name="create_event",
                description="Create a calendar event. Times can be natural language like 'tomorrow at 10am' or ISO format.",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Event title"},
                        "start": {"type": "string", "description": "Start time, e.g. 'tomorrow at 10am', '2026-08-05 14:00'"},
                        "end": {"type": "string", "description": "End time (optional)", "default": ""},
                        "description": {"type": "string", "description": "Event description", "default": ""},
                        "location": {"type": "string", "description": "Event location", "default": ""},
                        "attendees": {"type": "array", "items": {"type": "string"}, "description": "Attendee emails", "default": []},
                    },
                    "required": ["title", "start"],
                },
                handler=self._create_event_tool,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="list_events",
                description="List upcoming calendar events for the next week (or day/month).",
                parameters={
                    "type": "object",
                    "properties": {
                        "date_range": {"type": "string", "enum": ["day", "week", "month"], "description": "Range", "default": "week"},
                    },
                    "required": [],
                },
                handler=lambda date_range="week": self.format_events(self.list_events(date_range)),
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="search_events",
                description="Search calendar events by title, description or location.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search text"},
                    },
                    "required": ["query"],
                },
                handler=lambda query: self.format_events(self.search_events(query)),
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="delete_event",
                description="Delete a calendar event by its id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Event id (first 8 chars is enough)"},
                    },
                    "required": ["event_id"],
                },
                handler=self._delete_event_tool,
                category="services",
                permission_level="confirm",
            ),
            service_tool(
                name="create_reminder",
                description="Create a reminder. Time can be natural language like 'in 2 hours' or 'tomorrow at 9am'.",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Reminder text"},
                        "remind_at": {"type": "string", "description": "When to remind, e.g. 'tomorrow at 10am'"},
                    },
                    "required": ["title", "remind_at"],
                },
                handler=self._create_reminder_tool,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="list_reminders",
                description="List upcoming reminders.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                handler=lambda: self.format_reminders(self.list_reminders()),
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="delete_reminder",
                description="Delete a reminder by its id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "reminder_id": {"type": "string", "description": "Reminder id (first 8 chars is enough)"},
                    },
                    "required": ["reminder_id"],
                },
                handler=self._delete_reminder_tool,
                category="services",
                permission_level="confirm",
            ),
        ]

    async def _create_event_tool(
        self,
        title: str,
        start: str,
        end: str = "",
        description: str = "",
        location: str = "",
        attendees: Optional[list[str]] = None,
    ) -> ToolResult:
        try:
            event_id = await self.create_event_async(title, start, end, description, location, attendees)
            return ToolResult(success=True, output=f"Event created: {title} at {start} (id: {event_id[:8]})")
        except ValueError as e:
            return ToolResult(success=False, error=str(e))

    async def _create_reminder_tool(self, title: str, remind_at: str) -> ToolResult:
        try:
            reminder_id = self.create_reminder(title, remind_at)
            return ToolResult(success=True, output=f"Reminder created: {title} at {remind_at} (id: {reminder_id[:8]})")
        except ValueError as e:
            return ToolResult(success=False, error=str(e))

    async def _delete_event_tool(self, event_id: str) -> ToolResult:
        ok = await self.delete_event_async(event_id)
        return ToolResult(success=ok, output=f"Deleted event {event_id}" if ok else f"Event {event_id} not found")

    async def _delete_reminder_tool(self, reminder_id: str) -> ToolResult:
        ok = self.delete_reminder(reminder_id)
        return ToolResult(success=ok, output=f"Deleted reminder {reminder_id}" if ok else f"Reminder {reminder_id} not found")

    async def health_check(self) -> dict:
        if self.google and self.google.is_configured():
            try:
                events = await self.google.list_events(
                    _local_now().isoformat(),
                    (_local_now() + timedelta(days=1)).isoformat(),
                    1,
                )
                return {"ok": True, "detail": f"Google Calendar connected ({len(events)} events today), local db at {self.db_path}"}
            except Exception as e:
                return {"ok": False, "detail": f"Google Calendar error: {e}; local db at {self.db_path}"}
        return {"ok": True, "detail": f"Local calendar at {self.db_path}"}

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
