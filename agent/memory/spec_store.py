"""
SQLite-backed spec store: persists Spec objects across sessions.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import aiosqlite

from ..core.config import settings
from ..core.models import Spec, SpecPhase, SpecTask, TaskStatus

DB_PATH = settings.workspace_root / settings.memory_db


class SpecStore:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS specs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    requirements_md TEXT DEFAULT '',
                    design_md TEXT DEFAULT '',
                    tasks_json TEXT DEFAULT '[]',
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            await db.commit()

    async def save(self, spec: Spec):
        spec.updated_at = datetime.utcnow()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO specs
                   (id, name, goal, phase, requirements_md, design_md, tasks_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    spec.id,
                    spec.name,
                    spec.goal,
                    spec.phase.value,
                    spec.requirements_md,
                    spec.design_md,
                    json.dumps([t.model_dump() for t in spec.tasks], default=str),
                    spec.created_at.isoformat(),
                    spec.updated_at.isoformat(),
                ),
            )
            await db.commit()

    async def get(self, spec_id: str) -> Optional[Spec]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT * FROM specs WHERE id=?", (spec_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return self._row_to_spec(row)

    async def list_all(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, name, goal, phase, created_at FROM specs ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {"id": r[0], "name": r[1], "goal": r[2], "phase": r[3], "created_at": r[4]}
                    for r in rows
                ]

    def _row_to_spec(self, row) -> Spec:
        tasks_data = json.loads(row[6] or "[]")
        tasks = []
        for td in tasks_data:
            # Convert string enums back
            td["status"] = TaskStatus(td.get("status", "pending"))
            tasks.append(SpecTask(**td))

        return Spec(
            id=row[0],
            name=row[1],
            goal=row[2],
            phase=SpecPhase(row[3]),
            requirements_md=row[4] or "",
            design_md=row[5] or "",
            tasks=tasks,
            created_at=datetime.fromisoformat(row[7]),
            updated_at=datetime.fromisoformat(row[8]),
        )
