from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class Fact:
    def __init__(
        self,
        category: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        user_id: str = "default",
        fact_id: Optional[int] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ):
        self.id = fact_id
        self.user_id = user_id
        self.category = category
        self.key = key
        self.value = value
        self.confidence = confidence
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.updated_at = updated_at or self.created_at


class Preference:
    def __init__(
        self,
        key: str,
        value: str,
        user_id: str = "default",
        pref_id: Optional[int] = None,
        updated_at: Optional[str] = None,
    ):
        self.id = pref_id
        self.user_id = user_id
        self.key = key
        self.value = value
        self.updated_at = updated_at or datetime.now(timezone.utc).isoformat()


class Entity:
    def __init__(
        self,
        name: str,
        entity_type: str,
        attributes: Optional[dict] = None,
        user_id: str = "default",
        entity_id: Optional[int] = None,
        updated_at: Optional[str] = None,
    ):
        self.id = entity_id
        self.user_id = user_id
        self.name = name
        self.type = entity_type
        self.attributes = attributes or {}
        self.updated_at = updated_at or datetime.now(timezone.utc).isoformat()


class MemoryManager:
    def __init__(self, db_path: str | Path = "memory.db"):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default',
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default',
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                updated_at TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default',
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                attributes_json TEXT,
                updated_at TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_session TEXT,
                summary TEXT,
                created_at TEXT,
                token_count INTEGER DEFAULT 0
            )
        """)
        self._conn.commit()

    def store_fact(
        self,
        category: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        user_id: str = "default",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        existing = self._conn.execute(
            "SELECT id FROM facts WHERE user_id = ? AND category = ? AND key = ?",
            (user_id, category, key),
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE facts SET value = ?, confidence = ?, updated_at = ? WHERE id = ?",
                (value, confidence, now, existing[0]),
            )
            self._conn.commit()
            return existing[0]
        cursor = self._conn.execute(
            "INSERT INTO facts (user_id, category, key, value, confidence, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, category, key, value, confidence, now, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def recall_fact(
        self,
        category: str,
        key: str,
        user_id: str = "default",
    ) -> Optional[Fact]:
        row = self._conn.execute(
            "SELECT id, user_id, category, key, value, confidence, created_at, updated_at FROM facts WHERE user_id = ? AND category = ? AND key = ?",
            (user_id, category, key),
        ).fetchone()
        if not row:
            return None
        return Fact(
            fact_id=row[0], user_id=row[1], category=row[2],
            key=row[3], value=row[4], confidence=row[5],
            created_at=row[6], updated_at=row[7],
        )

    def search_facts(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 10,
    ) -> list[Fact]:
        pattern = f"%{query}%"
        rows = self._conn.execute(
            "SELECT id, user_id, category, key, value, confidence, created_at, updated_at FROM facts WHERE user_id = ? AND (key LIKE ? OR value LIKE ? OR category LIKE ?) ORDER BY confidence DESC LIMIT ?",
            (user_id, pattern, pattern, pattern, limit),
        ).fetchall()
        return [
            Fact(fact_id=r[0], user_id=r[1], category=r[2], key=r[3],
                 value=r[4], confidence=r[5], created_at=r[6], updated_at=r[7])
            for r in rows
        ]

    def store_preference(self, key: str, value: str, user_id: str = "default") -> int:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO preferences (user_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, key, value, now),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM preferences WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
        return row[0] if row else 0

    def get_preference(self, key: str, user_id: str = "default") -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM preferences WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
        return row[0] if row else None

    def get_all_preferences(self, user_id: str = "default") -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT key, value FROM preferences WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def store_entity(
        self,
        name: str,
        entity_type: str,
        attributes: Optional[dict] = None,
        user_id: str = "default",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        existing = self._conn.execute(
            "SELECT id FROM entities WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        attrs_json = json.dumps(attributes or {})
        if existing:
            self._conn.execute(
                "UPDATE entities SET type = ?, attributes_json = ?, updated_at = ? WHERE id = ?",
                (entity_type, attrs_json, now, existing[0]),
            )
            self._conn.commit()
            return existing[0]
        cursor = self._conn.execute(
            "INSERT INTO entities (user_id, name, type, attributes_json, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, entity_type, attrs_json, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_entity(self, name: str, user_id: str = "default") -> Optional[Entity]:
        row = self._conn.execute(
            "SELECT id, user_id, name, type, attributes_json, updated_at FROM entities WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        if not row:
            return None
        return Entity(
            entity_id=row[0], user_id=row[1], name=row[2],
            entity_type=row[3], attributes=json.loads(row[4]) if row[4] else {},
            updated_at=row[5],
        )

    def search_entities(self, query: str, user_id: str = "default") -> list[Entity]:
        pattern = f"%{query}%"
        rows = self._conn.execute(
            "SELECT id, user_id, name, type, attributes_json, updated_at FROM entities WHERE user_id = ? AND (name LIKE ? OR type LIKE ?)",
            (user_id, pattern, pattern),
        ).fetchall()
        return [
            Entity(entity_id=r[0], user_id=r[1], name=r[2], entity_type=r[3],
                   attributes=json.loads(r[4]) if r[4] else {}, updated_at=r[5])
            for r in rows
        ]

    def extract_entities_from_text(self, text: str) -> list[dict]:
        import re
        entities = []
        patterns = {
            "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "phone": r"\+?\d{1,4}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}",
            "date": r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
            "url": r"https?://[^\s]+",
        }
        for entity_type, pattern in patterns.items():
            matches = re.findall(pattern, text)
            for match in matches[:3]:
                entities.append({"name": match, "type": entity_type})
        name_patterns = [
            r"(?:my name is|I'm|I am|call me) (\w+)",
            r"(?:my|the) (?:friend|colleague|brother|sister|mom|dad|mother|father) (\w+)",
        ]
        stopwords = {"i", "am", "me", "my", "the", "a", "an", "is", "are", "was", "were",
                     "it", "he", "she", "they", "we", "you", "this", "that", "going",
                     "doing", "being", "having", "been", "have", "has", "had", "do",
                     "does", "did", "but", "not", "no", "yes", "ok", "okay", "hi",
                     "hello", "hey", "thanks", "thank", "please", "sorry"}
        for pattern in name_patterns:
            matches = re.findall(pattern, text.lower())
            for match in matches:
                if match not in stopwords and len(match) > 1:
                    entities.append({"name": match.capitalize(), "type": "person"})
        return entities

    def store_extracted_entities(self, text: str, user_id: str = "default") -> list[int]:
        ids = []
        for entity_data in self.extract_entities_from_text(text):
            eid = self.store_entity(
                name=entity_data["name"],
                entity_type=entity_data["type"],
                user_id=user_id,
            )
            ids.append(eid)
        return ids

    def add_memory_summary(self, session_id: str, summary: str, token_count: int = 0) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "INSERT INTO memory_index (source_session, summary, created_at, token_count) VALUES (?, ?, ?, ?)",
            (session_id, summary, now, token_count),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_recent_memories(self, limit: int = 5) -> list[dict]:
        rows = self._conn.execute(
            "SELECT source_session, summary, created_at, token_count FROM memory_index ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"session": r[0], "summary": r[1], "created_at": r[2], "tokens": r[3]}
            for r in rows
        ]

    def get_formatted_context(self, user_id: str = "default") -> str:
        parts = []
        prefs = self.get_all_preferences(user_id)
        if prefs:
            pref_lines = [f"  - {k}: {v}" for k, v in prefs.items()]
            parts.append("User Preferences:\n" + "\n".join(pref_lines))
        facts = self._conn.execute(
            "SELECT category, key, value FROM facts WHERE user_id = ? AND confidence > 0.5 ORDER BY updated_at DESC LIMIT 20",
            (user_id,),
        ).fetchall()
        if facts:
            fact_lines = [f"  [{r[0]}] {r[1]}: {r[2]}" for r in facts]
            parts.append("Known Facts:\n" + "\n".join(fact_lines))
        entities = self._conn.execute(
            "SELECT name, type, attributes_json FROM entities WHERE user_id = ? ORDER BY updated_at DESC LIMIT 10",
            (user_id,),
        ).fetchall()
        if entities:
            entity_lines = []
            for r in entities:
                attrs = json.loads(r[2]) if r[2] else {}
                attrs_str = f" ({attrs})" if attrs else ""
                entity_lines.append(f"  {r[1]}: {r[0]}{attrs_str}")
            parts.append("Known Contacts/Entities:\n" + "\n".join(entity_lines))
        recent = self.get_recent_memories(3)
        if recent:
            summary_lines = [f"  [{r['created_at'][:10]}] {r['summary']}" for r in recent]
            parts.append("Recent Conversation Summaries:\n" + "\n".join(summary_lines))
        return "\n\n".join(parts) if parts else ""

    def delete_fact(self, fact_id: int) -> bool:
        self._conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        self._conn.commit()
        return True

    def clear_user_data(self, user_id: str = "default") -> None:
        for table in ("facts", "preferences", "entities"):
            self._conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
