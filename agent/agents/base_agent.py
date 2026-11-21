"""
Base class for all MyCodeAI agents.
Provides the tool-use loop: think → call tool → observe → repeat.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from ..core.config import settings
from ..core.context_engine import ContextEngine
from ..core.models import Message, Role, Session, ToolResult
from ..core.ollama_client import ollama
from ..tools.registry import tool_registry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 20  # safety limit per turn


class BaseAgent:
    name: str = "base"
    system_prompt: str = "You are a helpful AI assistant."
    model: str = settings.default_model

    def __init__(self):
        self.context_engine = ContextEngine()

    async def run(
        self,
        session: Session,
        user_message: str,
        extra_context: str = "",
        model: Optional[str] = None,
    ) -> Message:
        """
        Single-turn execution:
        1. Build context window
        2. Send to LLM
        3. Execute any tool calls
        4. Loop until no more tool calls or max rounds reached
        5. Return final assistant message
        """
        from ..core.models import Message as Msg

        effective_model = model or self.model

        # Add the user message to session
        user_msg = Msg(role=Role.USER, content=user_message)
        session.messages.append(user_msg)

        for _round in range(MAX_TOOL_ROUNDS):
            system, window = self.context_engine.build_window(
                session, self.system_prompt, extra_context
            )
            response = await ollama.chat(
                messages=window,
                model=effective_model,
                tools=tool_registry.all_schemas(),
                system_prompt=system,
            )

            session.messages.append(response)

            if not response.tool_calls:
                # No more tool calls — we're done
                return response

            # Execute tool calls
            for call in response.tool_calls:
                logger.info("Tool call: %s(%s)", call.name, call.arguments)
                result = await self._execute_tool(call)
                response.tool_results.append(result)

                # Add tool result back as a message so the LLM sees it
                tool_msg = Msg(
                    role=Role.TOOL,
                    content=f"Tool {call.name} result:\n{result.output or result.error}",
                )
                session.messages.append(tool_msg)

        logger.warning("Max tool rounds (%d) reached for agent %s", MAX_TOOL_ROUNDS, self.name)
        return session.messages[-1]

    async def stream_run(
        self,
        session: Session,
        user_message: str,
        extra_context: str = "",
        model: Optional[str] = None,
    ) -> AsyncIterator[dict]:
        """
        Streaming version — yields dicts with type "token" | "tool_call" | "tool_result" | "done".
        """
        from ..core.models import Message as Msg

        effective_model = model or self.model
        user_msg = Msg(role=Role.USER, content=user_message)
        session.messages.append(user_msg)

        buffer = ""
        system, window = self.context_engine.build_window(session, self.system_prompt)

        async for token in ollama.stream_chat(
            messages=window,
            model=effective_model,
            system_prompt=system,
        ):
            buffer += token
            yield {"type": "token", "content": token}

        # Parse tool calls from full buffer and execute
        response = Msg(role=Role.ASSISTANT, content=buffer)
        from ..core.ollama_client import TOOL_CALL_MARKER, OllamaClient
        client = OllamaClient()
        response.tool_calls = client._extract_tool_calls(buffer)
        response.content = client._strip_tool_calls(buffer) if response.tool_calls else buffer
        session.messages.append(response)

        for call in response.tool_calls:
            yield {"type": "tool_call", "name": call.name, "arguments": call.arguments}
            result = await self._execute_tool(call)
            yield {"type": "tool_result", "name": call.name, "output": str(result.output), "error": result.error}

        yield {"type": "done", "session_id": session.id}

    async def _execute_tool(self, call):
        return await tool_registry.dispatch(call)
