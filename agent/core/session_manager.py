"""
Session manager: creates, persists and retrieves sessions from SQLite.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

import aiosqlite

from .config import settings
from .models import Message, Role, Session, ToolCall, ToolResult

logger = logging.getLogger(__name__)

DB_PATH = settings.workspace_root / settings.memory_db


class SessionManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    spec_id TEXT,
                    context_tokens INTEGER DEFAULT 0,
                    summary TEXT DEFAULT '',
                    created_at TEXT,
                    compacted_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT DEFAULT '[]',
                    tool_results TEXT DEFAULT '[]',
                    tokens INTEGER DEFAULT 0,
                    timestamp TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            await db.commit()

    async def create_session(self, spec_id: Optional[str] = None) -> Session:
        session = Session(id=str(uuid4()), spec_id=spec_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (id, spec_id, context_tokens, summary, created_at) VALUES (?,?,?,?,?)",
                (session.id, spec_id, 0, "", session.created_at.isoformat()),
            )
            await db.commit()
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT * FROM sessions WHERE id=?", (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                session = Session(
                    id=row[0],
                    spec_id=row[1],
                    context_tokens=row[2],
                    summary=row[3] or "",
                    created_at=datetime.fromisoformat(row[4]),
                    compacted_at=datetime.fromisoformat(row[5]) if row[5] else None,
                )

            async with db.execute(
                "SELECT * FROM messages WHERE session_id=? ORDER BY timestamp",
                (session_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                session.messages = [self._row_to_message(r) for r in rows]

        return session

    async def add_message(self, session_id: str, message: Message):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO messages
                   (id, session_id, role, content, tool_calls, tool_results, tokens, timestamp)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    message.id,
                    session_id,
                    message.role.value,
                    message.content,
                    json.dumps([tc.model_dump() for tc in message.tool_calls]),
                    json.dumps([tr.model_dump() for tr in message.tool_results]),
                    message.tokens,
                    message.timestamp.isoformat(),
                ),
            )
            await db.commit()

    async def update_summary(self, session_id: str, summary: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET summary=?, compacted_at=? WHERE id=?",
                (summary, datetime.utcnow().isoformat(), session_id),
            )
            await db.commit()

    async def list_sessions(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, spec_id, created_at FROM sessions ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [{"id": r[0], "spec_id": r[1], "created_at": r[2]} for r in rows]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _row_to_message(self, row) -> Message:
        return Message(
            id=row[0],
            role=Role(row[2]),
            content=row[3],
            tool_calls=[ToolCall(**tc) for tc in json.loads(row[4] or "[]")],
            tool_results=[ToolResult(**tr) for tr in json.loads(row[5] or "[]")],
            tokens=row[6],
            timestamp=datetime.fromisoformat(row[7]),
        )
