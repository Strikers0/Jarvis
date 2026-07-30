from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from core.llm import LLMMessage

logger = logging.getLogger(__name__)


class ConversationManager:
    def __init__(self, db_path: str | Path = "conversations.db", max_history: int = 50):
        self.db_path = Path(db_path)
        self.max_history = max_history
        self._current_session_id: Optional[str] = None
        self._messages: list[LLMMessage] = []
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT,
                created_at TEXT,
                updated_at TEXT,
                metadata TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                timestamp TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        self._conn.commit()

    def create_session(self, name: str = "") -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO sessions (id, name, created_at, updated_at, metadata) VALUES (?, ?, ?, ?, ?)",
            (session_id, name or f"Session {session_id[:8]}", now, now, "{}"),
        )
        self._conn.commit()
        self._current_session_id = session_id
        self._messages = []
        return session_id

    def load_session(self, session_id: str) -> bool:
        row = self._conn.execute(
            "SELECT id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return False
        self._current_session_id = session_id
        self._messages = self._load_messages(session_id)
        return True

    def _load_messages(self, session_id: str) -> list[LLMMessage]:
        rows = self._conn.execute(
            "SELECT role, content, tool_calls, tool_call_id FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        messages = []
        for row in rows:
            role, content, tool_calls_json, tool_call_id = row
            tool_calls = json.loads(tool_calls_json) if tool_calls_json else None
            messages.append(LLMMessage(
                role=role,
                content=content,
                tool_calls=tool_calls,
                tool_call_id=tool_call_id,
            ))
        return messages

    def add_message(self, message: LLMMessage) -> None:
        self._messages.append(message)
        if self._current_session_id:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls, tool_call_id, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self._current_session_id,
                    message.role,
                    message.content,
                    json.dumps(message.tool_calls) if message.tool_calls else None,
                    message.tool_call_id,
                    now,
                ),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, self._current_session_id),
            )
            self._conn.commit()
        self._trim_history()

    def _trim_history(self) -> None:
        if len(self._messages) > self.max_history:
            self._messages = self._messages[-self.max_history:]

    def get_messages(self) -> list[LLMMessage]:
        return self._messages.copy()

    def get_history(self, limit: Optional[int] = None) -> list[LLMMessage]:
        messages = self._messages.copy()
        if limit and len(messages) > limit:
            return messages[-limit:]
        return messages

    def clear_history(self) -> None:
        self._messages = []
        if self._current_session_id:
            self._conn.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (self._current_session_id,),
            )
            self._conn.commit()

    def list_sessions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "created_at": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()
        if self._current_session_id == session_id:
            self._current_session_id = None
            self._messages = []
        return True

    def rename_session(self, session_id: str, name: str) -> bool:
        self._conn.execute(
            "UPDATE sessions SET name = ?, updated_at = ? WHERE id = ?",
            (name, datetime.now(timezone.utc).isoformat(), session_id),
        )
        self._conn.commit()
        return True

    def get_current_session_id(self) -> Optional[str]:
        return self._current_session_id

    def export_session(self, session_id: str) -> Optional[dict]:
        session = self._conn.execute(
            "SELECT id, name, created_at, updated_at, metadata FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not session:
            return None
        messages = self._load_messages(session_id)
        return {
            "session": {
                "id": session[0],
                "name": session[1],
                "created_at": session[2],
                "updated_at": session[3],
                "metadata": json.loads(session[4]) if session[4] else {},
            },
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "tool_calls": m.tool_calls,
                    "tool_call_id": m.tool_call_id,
                }
                for m in messages
            ],
        }

    def import_session(self, data: dict) -> Optional[str]:
        session = data.get("session", {})
        messages_data = data.get("messages", [])
        session_id = self.create_session(session.get("name", ""))
        for msg_data in messages_data:
            message = LLMMessage(
                role=msg_data.get("role", "user"),
                content=msg_data.get("content", ""),
                tool_calls=msg_data.get("tool_calls"),
                tool_call_id=msg_data.get("tool_call_id"),
            )
            self.add_message(message)
        return session_id

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


class SensitiveFactConfirmation:
    def __init__(
        self,
        category: str,
        key: str,
        value: str,
        callback: Optional[Callable[[bool], None]] = None,
    ):
        self.category = category
        self.key = key
        self.value = value
        self.callback = callback
        self.confirmed: Optional[bool] = None


SensitiveFactCallback = Callable[[SensitiveFactConfirmation], None]


class MemoryAwareConversationManager(ConversationManager):
    def __init__(
        self,
        db_path: str | Path = "conversations.db",
        max_history: int = 50,
        memory_manager: Optional[Any] = None,
        auto_extract: bool = True,
        max_facts_in_context: int = 20,
        sensitive_fact_callback: Optional[SensitiveFactCallback] = None,
    ):
        super().__init__(db_path, max_history)
        self.memory_manager = memory_manager
        self.auto_extract = auto_extract
        self.max_facts_in_context = max_facts_in_context
        self.sensitive_fact_callback = sensitive_fact_callback
        self._pending_confirmations: list[SensitiveFactConfirmation] = []

    SENSITIVE_CATEGORIES = {"personal_info", "health", "finance", "credential"}

    def set_memory_manager(self, memory_manager: Any) -> None:
        self.memory_manager = memory_manager

    def add_message(self, message: LLMMessage) -> None:
        super().add_message(message)
        if self.auto_extract and self.memory_manager and message.role == "user":
            self._extract_and_store_facts(message.content)

    def get_context_with_memory(self, user_id: str = "default") -> str:
        if not self.memory_manager:
            return ""
        return self.memory_manager.get_formatted_context(user_id=user_id)

    def build_system_prompt_with_memory(
        self, base_system_prompt: str, user_id: str = "default"
    ) -> str:
        memory_context = self.get_context_with_memory(user_id=user_id)
        if memory_context:
            return f"{base_system_prompt}\n\n## Memory Context\n{memory_context}\n\nUse the memory context above to personalize your responses. Update facts when you learn new information."
        return base_system_prompt

    def _extract_and_store_facts(self, text: str, user_id: str = "default") -> None:
        if not self.memory_manager:
            return
        try:
            entities = self.memory_manager.extract_entities_from_text(text)
            for entity in entities:
                self.memory_manager.store_entity(
                    name=entity["name"],
                    entity_type=entity["type"],
                    user_id=user_id,
                )
            extracted = self._extract_facts_llm(text)
            for fact in extracted:
                category = fact.get("category", "general")
                key = fact.get("key", "")
                value = fact.get("value", "")
                confidence = fact.get("confidence", 0.7)
                if category in self.SENSITIVE_CATEGORIES and self.sensitive_fact_callback:
                    confirmation = SensitiveFactConfirmation(
                        category=category,
                        key=key,
                        value=value,
                        callback=lambda accepted: self._on_fact_confirmation(
                            accepted, category, key, value, user_id
                        ),
                    )
                    self._pending_confirmations.append(confirmation)
                    self.sensitive_fact_callback(confirmation)
                else:
                    self.memory_manager.store_fact(
                        category=category,
                        key=key,
                        value=value,
                        confidence=confidence,
                        user_id=user_id,
                    )
        except Exception as e:
            logger.warning("Failed to extract and store facts: %s", e)

    def _extract_facts_llm(self, text: str) -> list[dict]:
        import re
        facts = []
        patterns = [
            (r"(?:my name is|I'm|I am|call me) (\w+)", "personal_info", "user_name"),
            (r"(?:I am|I'm) (\d+) (?:years old|year old)", "personal_info", "age"),
            (r"(?:I live in|I'm from|my (?:city|town) is) (\w+)", "personal_info", "location"),
            (r"(?:I like|I love|I enjoy|my favorite) (\w+)", "preference", "likes"),
            (r"(?:I don't like|I hate|I dislike) (\w+)", "preference", "dislikes"),
            (r"(?:my (?:email|e-mail) is) ([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", "personal_info", "email"),
            (r"(?:my (?:phone|number|mobile) is) (\+?\d[\d\s-]{7,})", "personal_info", "phone"),
            (r"(?:I work (?:as|at)|my job is|I'm a(n)?) (\w+(?:\s+\w+)?)", "personal_info", "occupation"),
        ]
        stopwords = {"i", "am", "me", "my", "the", "a", "an", "is", "are", "was", "were",
                     "it", "he", "she", "they", "we", "you", "this", "that", "going",
                     "doing", "being", "having", "been", "have", "has", "had",
                     "but", "not", "no", "yes", "ok", "okay", "hi", "hello", "hey",
                     "thanks", "thank", "please", "sorry", "there", "here", "some"}
        for pattern, category, key in patterns:
            match = re.search(pattern, text.lower())
            if match:
                value = match.group(1).strip()
                if value not in stopwords:
                    facts.append({
                        "category": category,
                        "key": key,
                        "value": value,
                        "confidence": 1.0,
                    })
        return facts

    def _on_fact_confirmation(
        self, accepted: bool, category: str, key: str, value: str, user_id: str
    ) -> None:
        if accepted and self.memory_manager:
            self.memory_manager.store_fact(
                category=category, key=key, value=value, confidence=0.9, user_id=user_id
            )

    def get_pending_confirmations(self) -> list[SensitiveFactConfirmation]:
        return self._pending_confirmations.copy()

    def resolve_confirmation(self, confirmation: SensitiveFactConfirmation, accepted: bool) -> None:
        if confirmation.callback:
            confirmation.callback(accepted)
        self._pending_confirmations.remove(confirmation)
