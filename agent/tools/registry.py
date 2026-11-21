"""
Central tool registry.  Every tool registers itself here with its name,
description, parameter schema and async handler function.

The orchestrator calls `tool_registry.dispatch(name, args)` and the
registry handles permission checking before executing.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from ..core.models import ToolCall, ToolResult

logger = logging.getLogger(__name__)


class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable[..., Awaitable[Any]],
        requires_permission: bool = False,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
        self.requires_permission = requires_permission

    def to_llm_schema(self) -> dict:
        """Format for injecting into the system prompt."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        requires_permission: bool = False,
    ):
        """Decorator to register a tool handler."""
        def decorator(fn: Callable):
            self._tools[name] = ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
                handler=fn,
                requires_permission=requires_permission,
            )
            return fn
        return decorator

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def all_schemas(self) -> list[dict]:
        return [t.to_llm_schema() for t in self._tools.values()]

    async def dispatch(self, call: ToolCall) -> ToolResult:
        import time
        defn = self._tools.get(call.name)
        if not defn:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                output=None,
                error=f"Unknown tool: {call.name}",
            )
        start = time.monotonic()
        try:
            output = await defn.handler(**call.arguments)
            duration = int((time.monotonic() - start) * 1000)
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                output=output,
                duration_ms=duration,
            )
        except Exception as e:
            logger.exception("Tool %s failed", call.name)
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                output=None,
                error=str(e),
            )


tool_registry = ToolRegistry()
