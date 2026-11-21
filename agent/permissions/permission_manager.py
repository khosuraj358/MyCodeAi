"""
Permission manager — decides whether a tool call is allowed before execution.

Decisions: allow | deny | ask (ask = send to frontend for user confirmation)

Configuration via settings and per-tool rules in .kiro/steering/permissions.md
or the agent settings API.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable, Optional

from ..core.config import settings
from ..core.models import PermissionDecision, ToolCall

logger = logging.getLogger(__name__)

# Default rules: tool name → decision
DEFAULT_RULES: dict[str, PermissionDecision] = {
    "read_file": PermissionDecision.ALLOW,
    "list_directory": PermissionDecision.ALLOW,
    "search_files": PermissionDecision.ALLOW,
    "git_log": PermissionDecision.ALLOW,
    "git_diff": PermissionDecision.ALLOW,
    "write_file": PermissionDecision.ASK,
    "edit_file": PermissionDecision.ASK,
    "delete_file": PermissionDecision.ASK,
    "run_command": PermissionDecision.ASK,
    "git_checkpoint": PermissionDecision.ALLOW,
    "git_rewind": PermissionDecision.ASK,
}


class PermissionManager:
    """
    Wraps the tool registry dispatcher with permission checks.
    The `ask_callback` is called when a tool needs user confirmation;
    the VS Code extension wires this to a UI prompt.
    """

    def __init__(
        self,
        ask_callback: Optional[Callable[[str, dict], Awaitable[bool]]] = None,
    ):
        self._rules: dict[str, PermissionDecision] = dict(DEFAULT_RULES)
        self._ask_callback = ask_callback or self._default_ask

    def set_rule(self, tool_name: str, decision: PermissionDecision):
        self._rules[tool_name] = decision

    def set_autopilot(self, enabled: bool):
        """In autopilot mode, ASK rules become ALLOW."""
        for name in list(self._rules):
            if self._rules[name] == PermissionDecision.ASK:
                self._rules[name] = PermissionDecision.ALLOW if enabled else PermissionDecision.ASK

    async def check(self, call: ToolCall) -> bool:
        """Returns True if the tool call is permitted."""
        rule = self._rules.get(call.name, PermissionDecision(settings.default_permission))

        if rule == PermissionDecision.ALLOW:
            return True
        if rule == PermissionDecision.DENY:
            logger.warning("Tool %s denied by permission rule", call.name)
            return False
        # ASK
        return await self._ask_callback(call.name, call.arguments)

    async def _default_ask(self, tool_name: str, args: dict) -> bool:
        """Default: allow in server mode (frontend provides real callback)."""
        logger.info("Permission asked for %s — auto-allowing (no UI callback)", tool_name)
        return True
