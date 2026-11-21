"""
Context compactor — summarises the session history when it grows too large,
allowing the agent to continue long coding sessions without losing context.

This mirrors Kiro's /compact command behaviour.
"""
from __future__ import annotations

import logging

from ..core.config import settings
from ..core.models import Message, Role, Session
from ..core.ollama_client import ollama

logger = logging.getLogger(__name__)

COMPACTION_SYSTEM = """
You are a session summariser for an AI coding assistant.
Given a conversation history between a user and an AI coding agent,
produce a concise summary that preserves:

1. The overall goal / spec being worked on
2. What has been implemented so far (files created/modified)
3. Key decisions made
4. Current task / what was happening when this compaction occurred
5. Any open issues or next steps

The summary will be injected into future context as background information.
Be thorough but concise. Use bullet points.
"""


class Compactor:
    async def compact(self, session: Session) -> str:
        """
        Summarise session messages and return the summary string.
        The caller is responsible for storing the summary and
        trimming old messages from the session.
        """
        if len(session.messages) < 6:
            return session.summary  # Nothing to compact yet

        history = self._format_history(session.messages)
        summary_request = Message(
            role=Role.USER,
            content=f"Please summarise this coding session:\n\n{history}",
        )

        try:
            response = await ollama.chat(
                messages=[summary_request],
                model=settings.default_model,
                system_prompt=COMPACTION_SYSTEM,
                temperature=0.1,
            )
            summary = response.content
            logger.info(
                "Compacted session %s: %d messages → %d chars summary",
                session.id,
                len(session.messages),
                len(summary),
            )
            # Keep only last 4 messages after compaction
            session.messages = session.messages[-4:]
            return summary
        except Exception as e:
            logger.error("Compaction failed: %s", e)
            return session.summary

    def _format_history(self, messages: list[Message]) -> str:
        lines = []
        for m in messages:
            prefix = m.role.value.upper()
            lines.append(f"[{prefix}]: {m.content[:500]}")
        return "\n\n".join(lines)
