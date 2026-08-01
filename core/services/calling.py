from __future__ import annotations

import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from core.services.base import Service, service_tool
from core.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-()]{6,}$")


class CallingService(Service):
    """Phone calling via Twilio (optional) plus local contacts and call logging."""

    name = "calling"
    description = "Make phone calls (Twilio VoIP) and look up contacts."

    def __init__(
        self,
        db_path: str | Path = "calls.db",
        provider: str = "local",
        twilio_account_sid: str = "",
        twilio_auth_token: str = "",
        twilio_from_number: str = "",
    ):
        self.db_path = Path(db_path)
        self.provider = provider
        self.twilio_account_sid = twilio_account_sid or os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_auth_token = twilio_auth_token or os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from_number = twilio_from_number or os.getenv("TWILIO_FROM_NUMBER", "")
        self._conn: Optional[sqlite3.Connection] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                created_at TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS call_log (
                id TEXT PRIMARY KEY,
                to_number TEXT NOT NULL,
                contact_name TEXT,
                status TEXT,
                started_at TEXT,
                duration INTEGER DEFAULT 0,
                notes TEXT
            )
        """)
        self._conn.commit()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    def is_configured(self) -> bool:
        return self.provider == "twilio" and bool(
            self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number
        )

    # ---- contacts ----

    def save_contact(self, name: str, phone: str) -> str:
        contact_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO contacts (id, name, phone, created_at) VALUES (?, ?, ?, ?)",
            (contact_id, name.strip(), phone.strip(), datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return contact_id

    def list_contacts(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, phone FROM contacts ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [{"id": r[0], "name": r[1], "phone": r[2]} for r in rows]

    def lookup_contact(self, name_or_number: str) -> Optional[str]:
        value = name_or_number.strip()
        if _PHONE_RE.match(value.replace(" ", "")):
            return value
        row = self._conn.execute(
            "SELECT phone FROM contacts WHERE lower(name) = lower(?)",
            (value,),
        ).fetchone()
        if row:
            return row[0]
        rows = self._conn.execute(
            "SELECT phone FROM contacts WHERE lower(name) LIKE lower(?)",
            (f"%{value}%",),
        ).fetchall()
        return rows[0][0] if rows else None

    # ---- calling ----

    async def make_call(self, to: str, message: str = "") -> ToolResult:
        if not to:
            return ToolResult(success=False, error="No recipient provided.")
        contact_name = ""
        number = self.lookup_contact(to)
        if number:
            if number != to:
                contact_name = to
        else:
            number = to

        if self.provider == "twilio" and self.is_configured():
            try:
                twiml = message or "Hello! This is JARVIS calling."
                twiml_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Say>{twiml}</Say></Response>'
                resp = await self.client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Calls.json",
                    data={
                        "From": self.twilio_from_number,
                        "To": number,
                        "Twiml": twiml_xml,
                    },
                    auth=(self.twilio_account_sid, self.twilio_auth_token),
                )
                resp.raise_for_status()
                call_sid = resp.json().get("sid", "")
                self._log_call(number, contact_name, f"twilio:{call_sid}", notes=message)
                return ToolResult(
                    success=True,
                    output=f"Call initiated to {to} ({number}). Call SID: {call_sid}",
                )
            except Exception as e:
                logger.exception("Twilio call failed")
                return ToolResult(success=False, error=f"Failed to place Twilio call: {e}")

        self._log_call(number, contact_name, "local-only", notes="No VoIP provider configured")
        return ToolResult(
            success=False,
            error=(
                "No calling provider configured. To enable calls, set TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER and provider: twilio."
            ),
        )

    def _log_call(self, to_number: str, contact_name: str, status: str, duration: int = 0, notes: str = "") -> None:
        call_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO call_log (id, to_number, contact_name, status, started_at, duration, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                call_id, to_number, contact_name, status,
                datetime.now(timezone.utc).isoformat(), duration, notes,
            ),
        )
        self._conn.commit()

    def call_logs(self, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, to_number, contact_name, status, started_at, duration FROM call_log ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0], "to": r[1], "contact": r[2],
                "status": r[3], "started_at": r[4], "duration": r[5],
            }
            for r in rows
        ]

    def get_tools(self) -> list[Tool]:
        return [
            service_tool(
                name="make_call",
                description="Place a phone call to a contact name or number.",
                parameters={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Contact name (e.g. 'Mom') or phone number"},
                        "message": {"type": "string", "description": "Optional message to speak", "default": ""},
                    },
                    "required": ["to"],
                },
                handler=self.make_call,
                category="services",
                permission_level="confirm",
            ),
            service_tool(
                name="save_contact",
                description="Save a contact name and phone number for future calls.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Contact name"},
                        "phone": {"type": "string", "description": "Phone number"},
                    },
                    "required": ["name", "phone"],
                },
                handler=self._save_contact_tool,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="list_contacts",
                description="List saved contacts.",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=self._list_contacts_tool,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="call_logs",
                description="List recent call history.",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of entries", "default": 10},
                    },
                    "required": [],
                },
                handler=lambda limit=10: self._format_call_logs(self.call_logs(limit)),
                category="services",
                permission_level="auto",
            ),
        ]

    async def _save_contact_tool(self, name: str, phone: str) -> str:
        contact_id = self.save_contact(name, phone)
        return f"Saved contact {name} ({phone}). id: {contact_id[:8]}"

    async def _list_contacts_tool(self) -> str:
        contacts = self.list_contacts()
        if not contacts:
            return "No contacts saved."
        return "\n".join(f"- {c['name']}: {c['phone']} (id: {c['id'][:8]})" for c in contacts)

    @staticmethod
    def _format_call_logs(logs: list[dict]) -> str:
        if not logs:
            return "No calls logged."
        return "\n".join(
            f"- {entry['started_at'][:19]} {entry['to']} ({entry['contact'] or 'unknown'}) -> {entry['status']}"
            for entry in logs
        )

    async def health_check(self) -> dict:
        if self.is_configured():
            return {"ok": True, "detail": f"Twilio provider ready ({len(self.list_contacts())} contacts)"}
        return {"ok": True, "detail": f"Local contacts ({len(self.list_contacts())}); no VoIP provider configured"}

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._conn:
            self._conn.close()
            self._conn = None
