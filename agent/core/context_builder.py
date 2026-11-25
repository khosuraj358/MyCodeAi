"""
context_builder.py  — Builds the full situational context injected into every
agent turn so the model always knows:

  1. WORKSPACE   — what projects/files exist on the Desktop
  2. SESSION     — what happened in this conversation so far
  3. HISTORY     — brief summary of recent past sessions
  4. ENVIRONMENT — OS, shell, available tools, running processes
  5. SPECS       — any active specs and their current phase
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)

DESKTOP = Path.home() / "Desktop"
MAX_HISTORY_SESSIONS = 5
MAX_WORKSPACE_FILES  = 40
_CACHE_TTL = 30.0  # seconds for expensive context parts


class ContextBuilder:
    """Call build() before every agent turn to get a rich system-prompt injection."""

    def __init__(self):
        self._workspace_cache: Optional[str] = None
        self._workspace_mtime: float = 0.0
        self._env_cache: str = ""
        self._env_cache_ts: float = 0.0
        self._past_cache: str = ""
        self._past_cache_ts: float = 0.0

    # ── Public API ─────────────────────────────────────────────────────────────

    async def build(
        self,
        session_id:   str,
        session_msgs: list,          # list of Message objects from current session
        spec_id:      Optional[str] = None,
        lightweight:  bool = False,  # True = skip heavy parts for quick chat
    ) -> str:
        """
        Return a markdown context block to prepend to the system prompt.
        When lightweight=True, skip filesystem scans, DB queries and subprocess
        calls — used for simple chat/greetings to keep latency low.
        """
        parts: list[str] = []

        # 1. Date/time
        parts.append(f"**Current date/time:** {datetime.now().strftime('%A %B %d %Y, %H:%M')}")

        if lightweight:
            # For quick chat: only session summary + cached env, no disk/DB hits
            sess_summary = self._summarise_session(session_msgs)
            if sess_summary:
                parts.append(sess_summary)
            parts.append(self._env_context())
            return "\n\n".join(parts)

        # 2. Workspace scan
        ws = self._scan_workspace()
        if ws:
            parts.append(ws)

        # 3. Session history (what happened earlier in this conversation)
        sess_summary = self._summarise_session(session_msgs)
        if sess_summary:
            parts.append(sess_summary)

        # 4. Active spec
        spec_ctx = await self._spec_context(spec_id)
        if spec_ctx:
            parts.append(spec_ctx)

        # 5. Recent past sessions (cross-session memory) — cached
        past = await self._past_sessions(exclude=session_id)
        if past:
            parts.append(past)

        # 6. Environment — cached
        parts.append(self._env_context())

        return "\n\n".join(parts)

    # ── Workspace scan ─────────────────────────────────────────────────────────

    def _scan_workspace(self) -> str:
        """List projects and key files on the Desktop."""
        try:
            if not DESKTOP.exists():
                return ""

            mtime = DESKTOP.stat().st_mtime
            if self._workspace_cache and mtime == self._workspace_mtime:
                return self._workspace_cache  # cached

            projects: list[str] = []
            loose_files: list[str] = []

            for item in sorted(DESKTOP.iterdir()):
                name = item.name
                # Skip clutter
                if name.startswith(".") or name.endswith((".deb", ".vsix", ".zip", ".bak")):
                    continue
                if item.is_dir():
                    # List top-level files inside each project dir
                    children = []
                    for f in sorted(item.iterdir())[:8]:
                        if not f.name.startswith(".") and f.is_file():
                            children.append(f.name)
                    projects.append(
                        f"  📁 {name}/"
                        + (f"  ({', '.join(children[:5])})" if children else "")
                    )
                elif item.is_file():
                    loose_files.append(f"  📄 {name}")

            lines = ["**Workspace (Desktop):**"]
            lines += projects[:MAX_WORKSPACE_FILES]
            if loose_files:
                lines.append("  Loose files: " + ", ".join(
                    f.strip() for f in loose_files[:10]
                ))

            result = "\n".join(lines)
            self._workspace_cache = result
            self._workspace_mtime = mtime
            return result

        except Exception as e:
            logger.debug("workspace scan failed: %s", e)
            return ""

    # ── Session history ─────────────────────────────────────────────────────────

    def _summarise_session(self, messages: list) -> str:
        """Summarise what has happened so far in the current session."""
        if len(messages) < 2:
            return ""

        lines = ["**This conversation so far:**"]
        # Show the last 6 exchange pairs condensed
        for m in messages[-12:]:
            role    = getattr(m, "role", None)
            content = getattr(m, "content", "") or ""
            if not content.strip():
                continue
            role_str = "You" if str(role) in ("user", "Role.USER") else "Agent"
            snippet  = content.strip()[:120].replace("\n", " ")
            lines.append(f"  {role_str}: {snippet}{'…' if len(content) > 120 else ''}")

        # Collect files modified in this session
        files_created: list[str] = []
        for m in messages:
            for tr in getattr(m, "tool_results", []):
                if getattr(tr, "name", "") in ("write_file", "edit_file") \
                        and not getattr(tr, "error", None):
                    out = str(getattr(tr, "output", "") or "")
                    if " to " in out:
                        path = out.split(" to ", 1)[-1].strip()
                        if path not in files_created:
                            files_created.append(path)

        if files_created:
            lines.append(f"  Files created/edited: {', '.join(files_created[-5:])}")

        return "\n".join(lines)

    # ── Spec context ────────────────────────────────────────────────────────────

    async def _spec_context(self, spec_id: Optional[str]) -> str:
        if not spec_id:
            return ""
        try:
            from .session_manager import SessionManager
            from ..memory.spec_store import SpecStore
            store = SpecStore()
            spec  = await store.get(spec_id)
            if not spec:
                return ""
            pending = [t for t in spec.tasks if t.status.value == "pending"]
            done    = [t for t in spec.tasks if t.status.value == "completed"]
            lines   = [
                f"**Active Spec:** {spec.name} — Phase: {spec.phase.value}",
                f"  Goal: {spec.goal[:120]}",
                f"  Tasks: {len(done)} completed, {len(pending)} pending",
            ]
            if pending:
                lines.append(f"  Next task: {pending[0].id} — {pending[0].title}")
            return "\n".join(lines)
        except Exception as e:
            logger.debug("spec context failed: %s", e)
            return ""

    # ── Past sessions ───────────────────────────────────────────────────────────

    async def _past_sessions(self, exclude: str) -> str:
        """Pull summaries or last-message previews from recent sessions. Cached."""
        now = time.monotonic()
        if self._past_cache and now - self._past_cache_ts < _CACHE_TTL:
            return self._past_cache
        try:
            import aiosqlite
            db_path = settings.memory_db
            if not db_path.exists():
                self._past_cache = ""
                self._past_cache_ts = now
                return ""

            async with aiosqlite.connect(db_path) as db:
                rows = await (await db.execute(
                    """SELECT s.id, s.summary, s.created_at,
                              m.content, m.role
                       FROM sessions s
                       LEFT JOIN messages m ON m.session_id = s.id
                         AND m.role = 'assistant'
                         AND m.timestamp = (
                             SELECT MAX(m2.timestamp) FROM messages m2
                             WHERE m2.session_id = s.id AND m2.role = 'assistant'
                         )
                       WHERE s.id != ?
                       ORDER BY s.created_at DESC
                       LIMIT ?""",
                    (exclude, MAX_HISTORY_SESSIONS),
                )).fetchall()

            if not rows:
                self._past_cache = ""
                self._past_cache_ts = now
                return ""

            lines = ["**Recent session history:**"]
            seen  = set()
            for r in rows:
                sid, summary, created_at, last_msg, _ = r
                if sid in seen:
                    continue
                seen.add(sid)
                date = created_at[:16] if created_at else "?"
                if summary:
                    snippet = summary[:100]
                elif last_msg:
                    snippet = last_msg.strip()[:100].replace("\n", " ")
                else:
                    snippet = "(no content)"
                lines.append(f"  [{date}] {snippet}…")

            self._past_cache = "\n".join(lines)
            self._past_cache_ts = now
            return self._past_cache
        except Exception as e:
            logger.debug("past sessions failed: %s", e)
            self._past_cache = ""
            self._past_cache_ts = now
            return ""

    # ── Environment ─────────────────────────────────────────────────────────────

    def _env_context(self) -> str:
        now = time.monotonic()
        if self._env_cache and now - self._env_cache_ts < _CACHE_TTL:
            return self._env_cache
        lines = [
            "**Environment:**",
            f"  OS: Ubuntu 22.04 LTS  |  Shell: bash  |  Python: 3.10",
            f"  Home: {Path.home()}  |  Desktop: {DESKTOP}",
            f"  Agent API: http://127.0.0.1:8765",
        ]
        # Detect running services
        services = []
        try:
            import subprocess
            out = subprocess.run(
                ["pgrep", "-a", "-f", "agent.core.server|ollama|npm.*dev|python.*manage"],
                capture_output=True, text=True, timeout=2
            ).stdout
            for line in out.splitlines():
                if "agent.core.server" in line:
                    services.append("MyCodeAI agent server (:8765)")
                elif "ollama" in line and "serve" in line:
                    services.append("Ollama (:11434)")
        except Exception:
            pass
        if services:
            lines.append(f"  Running: {', '.join(services)}")
        self._env_cache = "\n".join(lines)
        self._env_cache_ts = now
        return self._env_cache


# Module-level singleton
context_builder = ContextBuilder()
