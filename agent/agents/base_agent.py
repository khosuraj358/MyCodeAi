"""
Base class for all MyCodeAI agents.

Tool-use loop per turn:
  think → [call tool → observe] × N → final answer

Tool schemas are only injected when the agent class sets `use_tools = True`,
keeping plain-chat turns lean.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from ..core.config import settings
from ..core.context_engine import ContextEngine
from ..core.models import Message, Role, Session
from ..core.ollama_client import ollama
from ..tools.registry import tool_registry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 12   # hard cap per single user turn


class BaseAgent:
    name: str = "base"
    system_prompt: str = "You are a helpful AI coding assistant."
    model: str = settings.default_model

    # Set to True in subclasses that need file/shell tools
    use_tools: bool = False

    def __init__(self):
        self.context_engine = ContextEngine()

    # ── Non-streaming run ─────────────────────────────────────────────────────

    async def run(
        self,
        session: Session,
        user_message: str,
        extra_context: str = "",
        model: Optional[str] = None,
    ) -> Message:
        effective_model = model or self.model
        tools = tool_registry.all_schemas() if self.use_tools else None

        # Append user turn
        user_msg = Message(role=Role.USER, content=user_message)
        session.messages.append(user_msg)

        for _round in range(MAX_TOOL_ROUNDS):
            system_prompt, window = self.context_engine.build_window(
                session, self.system_prompt, extra_context
            )
            response = await ollama.chat(
                messages=window,
                model=effective_model,
                tools=tools,
                system_prompt=system_prompt,
            )
            session.messages.append(response)

            # No tool calls → done
            if not response.tool_calls:
                return response

            # Execute each tool call and feed results back
            for call in response.tool_calls:
                logger.info("[%s] tool call: %s(%s)", self.name, call.name, call.arguments)
                result = await tool_registry.dispatch(call)
                response.tool_results.append(result)

                result_text = (
                    f"[{call.name} result]\n{result.output}"
                    if not result.error
                    else f"[{call.name} error]\n{result.error}"
                )
                session.messages.append(Message(role=Role.TOOL, content=result_text))

        logger.warning("[%s] hit MAX_TOOL_ROUNDS=%d", self.name, MAX_TOOL_ROUNDS)
        return session.messages[-1]

    # ── Streaming run ─────────────────────────────────────────────────────────

    async def stream_run(
        self,
        session: Session,
        user_message: str,
        extra_context: str = "",
        model: Optional[str] = None,
    ) -> AsyncIterator[dict]:
        effective_model = model or self.model

        user_msg = Message(role=Role.USER, content=user_message)
        session.messages.append(user_msg)

        # Stream first response
        system_prompt, window = self.context_engine.build_window(
            session, self.system_prompt, extra_context
        )

        buffer = ""
        async for token in ollama.stream_chat(
            messages=window,
            model=effective_model,
            system_prompt=system_prompt,
        ):
            buffer += token
            yield {"type": "token", "content": token}

        # Parse and execute any tool calls from the full buffer
        response = Message(role=Role.ASSISTANT, content=buffer)
        response.tool_calls = ollama._extract_tool_calls(buffer)
        response.content    = ollama._strip_tool_calls(buffer) if response.tool_calls else buffer.strip()
        session.messages.append(response)

        for call in response.tool_calls:
            yield {"type": "tool_call", "name": call.name, "arguments": call.arguments}
            result = await tool_registry.dispatch(call)
            yield {"type": "tool_result", "name": call.name,
                   "output": str(result.output or ""), "error": result.error}

            session.messages.append(Message(
                role=Role.TOOL,
                content=f"[{call.name}]\n{result.output or result.error}",
            ))

        yield {"type": "done", "session_id": session.id}
