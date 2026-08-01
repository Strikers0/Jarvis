from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.services.base import Service, service_tool
from core.tools.base import Tool, ToolResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NotesService(Service):
    """Local notes and to-do list management backed by SQLite."""

    name = "notes"
    description = "Notes and to-do list management with local SQLite storage."

    def __init__(self, db_path: str | Path = "notes.db"):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT,
                updated_at TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                due_date TEXT,
                priority TEXT NOT NULL DEFAULT 'medium',
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        self._conn.commit()

    # ---- notes ----

    def create_note(self, title: str, content: str = "", tags: Optional[list[str]] = None) -> str:
        note_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            "INSERT INTO notes (id, title, content, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, title, content, json.dumps(tags or []), now, now),
        )
        self._conn.commit()
        return note_id

    def list_notes(self, tag: str = "", limit: int = 50) -> list[dict]:
        if tag:
            rows = self._conn.execute(
                "SELECT id, title, content, tags, created_at, updated_at FROM notes WHERE tags LIKE ? ORDER BY updated_at DESC LIMIT ?",
                (f"%{tag}%", limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, title, content, tags, created_at, updated_at FROM notes ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_note(r) for r in rows]

    def search_notes(self, query: str, limit: int = 20) -> list[dict]:
        pattern = f"%{query}%"
        rows = self._conn.execute(
            "SELECT id, title, content, tags, created_at, updated_at FROM notes "
            "WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (pattern, pattern, pattern, limit),
        ).fetchall()
        return [self._row_to_note(r) for r in rows]

    def get_note(self, note_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT id, title, content, tags, created_at, updated_at FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        return self._row_to_note(row) if row else None

    def update_note(self, note_id: str, title: Optional[str] = None, content: Optional[str] = None, tags: Optional[list[str]] = None) -> bool:
        existing = self.get_note(note_id)
        if not existing:
            return False
        new_title = title if title is not None else existing["title"]
        new_content = content if content is not None else existing["content"]
        new_tags = json.dumps(tags if tags is not None else existing["tags"])
        self._conn.execute(
            "UPDATE notes SET title = ?, content = ?, tags = ?, updated_at = ? WHERE id = ?",
            (new_title, new_content, new_tags, _now(), note_id),
        )
        self._conn.commit()
        return True

    def delete_note(self, note_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_note(self, row: tuple) -> dict:
        return {
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "tags": json.loads(row[3]) if row[3] else [],
            "created_at": row[4],
            "updated_at": row[5],
        }

    # ---- todos ----

    def create_todo(self, task: str, due_date: str = "", priority: str = "medium") -> str:
        todo_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            "INSERT INTO todos (id, task, due_date, priority, done, created_at, updated_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
            (todo_id, task, due_date or None, priority, now, now),
        )
        self._conn.commit()
        return todo_id

    def list_todos(self, status: str = "all", limit: int = 50) -> list[dict]:
        where = ""
        if status in ("open", "pending"):
            where = "WHERE done = 0"
        elif status == "done":
            where = "WHERE done = 1"
        rows = self._conn.execute(
            f"SELECT id, task, due_date, priority, done, created_at, updated_at FROM todos {where} ORDER BY done ASC, due_date IS NULL, due_date ASC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_todo(r) for r in rows]

    def update_todo(
        self,
        todo_id: str,
        done: Optional[bool] = None,
        task: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> bool:
        existing = self.get_todo(todo_id)
        if not existing:
            return False
        sets = []
        params: list[Any] = []
        if done is not None:
            sets.append("done = ?")
            params.append(1 if done else 0)
        if task is not None:
            sets.append("task = ?")
            params.append(task)
        if due_date is not None:
            sets.append("due_date = ?")
            params.append(due_date or None)
        if priority is not None:
            sets.append("priority = ?")
            params.append(priority)
        if not sets:
            return True
        sets.append("updated_at = ?")
        params.append(_now())
        params.append(todo_id)
        self._conn.execute(f"UPDATE todos SET {', '.join(sets)} WHERE id = ?", params)
        self._conn.commit()
        return True

    def get_todo(self, todo_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT id, task, due_date, priority, done, created_at, updated_at FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()
        return self._row_to_todo(row) if row else None

    def delete_todo(self, todo_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_todo(self, row: tuple) -> dict:
        return {
            "id": row[0],
            "task": row[1],
            "due_date": row[2],
            "priority": row[3],
            "done": bool(row[4]),
            "created_at": row[5],
            "updated_at": row[6],
        }

    # ---- presentation helpers ----

    @staticmethod
    def format_notes(notes: list[dict]) -> str:
        if not notes:
            return "No notes found."
        lines = []
        for n in notes:
            tags = ", ".join(n["tags"]) if n["tags"] else "-"
            snippet = (n["content"] or "").replace("\n", " ")[:120]
            lines.append(f"[{n['id'][:8]}] {n['title']} (tags: {tags})")
            if snippet:
                lines.append(f"    {snippet}")
        return "\n".join(lines)

    @staticmethod
    def format_todos(todos: list[dict]) -> str:
        if not todos:
            return "No to-do items found."
        lines = []
        for t in todos:
            status = "[x]" if t["done"] else "[ ]"
            due = f" due: {t['due_date']}" if t.get("due_date") else ""
            lines.append(f"{status} [{t['priority']}] {t['task']}{due} (id: {t['id'][:8]})")
        return "\n".join(lines)

    # ---- tools ----

    def get_tools(self) -> list[Tool]:
        return [
            service_tool(
                name="create_note",
                description="Create a new note with a title, optional content and tags.",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Note title"},
                        "content": {"type": "string", "description": "Note body text", "default": ""},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags", "default": []},
                    },
                    "required": ["title"],
                },
                handler=self.create_note,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="list_notes",
                description="List saved notes, optionally filtered by a tag.",
                parameters={
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string", "description": "Filter notes by tag", "default": ""},
                    },
                    "required": [],
                },
                handler=lambda tag="": self.format_notes(self.list_notes(tag)),
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="search_notes",
                description="Search notes by title, content or tag.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search text"},
                    },
                    "required": ["query"],
                },
                handler=lambda query: self.format_notes(self.search_notes(query)),
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="delete_note",
                description="Delete a note by its id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "note_id": {"type": "string", "description": "Note id (first 8 chars is enough)"},
                    },
                    "required": ["note_id"],
                },
                handler=self._delete_note_tool,
                category="services",
                permission_level="confirm",
            ),
            service_tool(
                name="create_todo",
                description="Create a to-do item with an optional due date and priority (low/medium/high).",
                parameters={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Task description"},
                        "due_date": {"type": "string", "description": "Due date (e.g. '2026-08-05', 'tomorrow at 5pm')", "default": ""},
                        "priority": {"type": "string", "enum": ["low", "medium", "high"], "description": "Priority", "default": "medium"},
                    },
                    "required": ["task"],
                },
                handler=self.create_todo,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="list_todos",
                description="List to-do items, optionally filtered (all/pending/done).",
                parameters={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["all", "pending", "done"], "description": "Filter", "default": "all"},
                    },
                    "required": [],
                },
                handler=lambda status="all": self.format_todos(self.list_todos(status)),
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="mark_todo",
                description="Mark a to-do item as done or open.",
                parameters={
                    "type": "object",
                    "properties": {
                        "todo_id": {"type": "string", "description": "To-do id (first 8 chars is enough)"},
                        "done": {"type": "boolean", "description": "True to mark done, False to reopen", "default": True},
                    },
                    "required": ["todo_id"],
                },
                handler=self._mark_todo_tool,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="delete_todo",
                description="Delete a to-do item by its id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "todo_id": {"type": "string", "description": "To-do id (first 8 chars is enough)"},
                    },
                    "required": ["todo_id"],
                },
                handler=self._delete_todo_tool,
                category="services",
                permission_level="confirm",
            ),
        ]

    async def _delete_note_tool(self, note_id: str) -> ToolResult:
        ok = self.delete_note(note_id)
        return ToolResult(success=ok, output=f"Deleted note {note_id}" if ok else f"Note {note_id} not found")

    async def _delete_todo_tool(self, todo_id: str) -> ToolResult:
        ok = self.delete_todo(todo_id)
        return ToolResult(success=ok, output=f"Deleted to-do {todo_id}" if ok else f"To-do {todo_id} not found")

    async def _mark_todo_tool(self, todo_id: str, done: bool = True) -> ToolResult:
        ok = self.update_todo(todo_id, done=done)
        return ToolResult(success=ok, output=f"Marked to-do {todo_id} done" if ok and done else f"Marked to-do {todo_id} open" if ok else f"To-do {todo_id} not found")

    async def health_check(self) -> dict:
        return {"ok": True, "detail": f"Notes db at {self.db_path}"}

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
