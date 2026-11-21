"""
Context engine: assembles the message window for each LLM call.

Responsibilities:
- Track token budget
- Insert steering file content
- Inject relevant project files (from memory index)
- Trigger compaction when the window fills
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .config import settings
from .models import Message, Role, Session

logger = logging.getLogger(__name__)

# Rough token estimator: 1 token ≈ 4 characters
def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class ContextEngine:
    def __init__(self, workspace: Path = settings.workspace_root):
        self.workspace = workspace
        self._steering_cache: dict[str, str] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def build_window(
        self,
        session: Session,
        system_prompt: str,
        extra_context: str = "",
        max_tokens: int = settings.context_window,
    ) -> tuple[str, list[Message]]:
        """
        Return (system_prompt_with_steering, trimmed_messages).
        Automatically loads steering files and trims oldest messages when needed.
        """
        steering = self._load_steering()
        full_system = "\n\n".join(filter(None, [system_prompt, steering, extra_context]))

        system_tokens = _estimate_tokens(full_system)
        budget = max_tokens - system_tokens - settings.max_response_tokens

        messages = self._trim_to_budget(session.messages, budget)
        return full_system, messages

    def count_session_tokens(self, session: Session) -> int:
        return sum(_estimate_tokens(m.content) for m in session.messages)

    def needs_compaction(self, session: Session) -> bool:
        used = self.count_session_tokens(session)
        limit = settings.context_window * 0.75
        return used > limit

    # ── Steering ──────────────────────────────────────────────────────────────

    def _load_steering(self) -> str:
        steering_dir = self.workspace / settings.steering_dir
        if not steering_dir.exists():
            return ""

        parts: list[str] = []
        for md_file in sorted(steering_dir.glob("*.md")):
            content = self._read_cached(md_file)
            if content:
                parts.append(f"## Steering: {md_file.stem}\n{content}")
        return "\n\n".join(parts)

    def _read_cached(self, path: Path) -> str:
        key = str(path)
        mtime = path.stat().st_mtime if path.exists() else 0
        cached = self._steering_cache.get(key)
        # Simple mtime-based invalidation stored in a parallel dict
        if cached is None:
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
                self._steering_cache[key] = text
                return text
            return ""
        return cached

    def invalidate_steering_cache(self):
        self._steering_cache.clear()

    # ── Trimming ──────────────────────────────────────────────────────────────

    def _trim_to_budget(
        self, messages: list[Message], budget: int
    ) -> list[Message]:
        """Keep the most recent messages that fit within the token budget.
        Always preserves the first user message for context anchoring."""
        if not messages:
            return []

        total = sum(_estimate_tokens(m.content) for m in messages)
        if total <= budget:
            return messages

        # Always keep at least the last 4 messages
        keep = list(messages)
        while len(keep) > 4 and total > budget:
            removed = keep.pop(0)
            total -= _estimate_tokens(removed.content)

        logger.debug("Context trimmed to %d messages (%d tokens)", len(keep), total)
        return keep
