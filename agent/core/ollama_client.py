"""
Async Ollama client wrapper.
Handles chat completions with tool/function-call support via
a JSON-mode prompt strategy (Ollama does not expose OpenAI-style
function calling for all models, so we implement it ourselves).
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Optional

import httpx

from .config import settings
from .models import Message, Role, ToolCall

logger = logging.getLogger(__name__)

TOOL_CALL_MARKER = "TOOL_CALL:"


def _build_tool_system_prompt(tools: list[dict]) -> str:
    """Append tool descriptions to the system prompt."""
    if not tools:
        return ""
    tool_docs = json.dumps(tools, indent=2)
    return f"""
You have access to the following tools. To call a tool, output a line starting
with exactly `{TOOL_CALL_MARKER}` followed by a JSON object with keys
"name" and "arguments". Only one tool call per response turn.

Available tools:
{tool_docs}

When you need information or want to take an action, call the appropriate tool.
Wait for the tool result before continuing.
"""


class OllamaClient:
    def __init__(self, base_url: str = settings.ollama_base_url):
        self._base = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=300)

    async def list_models(self) -> list[str]:
        resp = await self._http.get(f"{self._base}/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]

    async def chat(
        self,
        messages: list[Message],
        model: str = settings.default_model,
        tools: Optional[list[dict]] = None,
        system_prompt: str = "",
        temperature: float = 0.2,
    ) -> Message:
        """Non-streaming chat. Returns a single assistant Message."""
        payload = self._build_payload(
            messages, model, tools, system_prompt, temperature, stream=False
        )
        resp = await self._http.post(f"{self._base}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data["message"]["content"]
        tool_calls = self._extract_tool_calls(content)
        clean_content = self._strip_tool_calls(content) if tool_calls else content
        return Message(
            role=Role.ASSISTANT,
            content=clean_content,
            tool_calls=tool_calls,
            tokens=data.get("eval_count", 0),
        )

    async def stream_chat(
        self,
        messages: list[Message],
        model: str = settings.default_model,
        tools: Optional[list[dict]] = None,
        system_prompt: str = "",
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Streaming chat. Yields text chunks as they arrive."""
        payload = self._build_payload(
            messages, model, tools, system_prompt, temperature, stream=True
        )
        async with self._http.stream(
            "POST", f"{self._base}/api/chat", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_payload(
        self,
        messages: list[Message],
        model: str,
        tools: Optional[list[dict]],
        system_prompt: str,
        temperature: float,
        stream: bool,
    ) -> dict:
        tool_addition = _build_tool_system_prompt(tools or [])
        full_system = (system_prompt + "\n" + tool_addition).strip()

        ollama_messages = []
        if full_system:
            ollama_messages.append({"role": "system", "content": full_system})

        for m in messages:
            ollama_messages.append({"role": m.role.value, "content": m.content})
            for tr in m.tool_results:
                result_text = (
                    f"Tool result for {tr.name}:\n{json.dumps(tr.output, indent=2)}"
                    if not tr.error
                    else f"Tool error for {tr.name}: {tr.error}"
                )
                ollama_messages.append({"role": "tool", "content": result_text})

        return {
            "model": model,
            "messages": ollama_messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_ctx": settings.context_window,
                "num_predict": settings.max_response_tokens,
            },
        }

    def _extract_tool_calls(self, content: str) -> list[ToolCall]:
        calls = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith(TOOL_CALL_MARKER):
                json_str = line[len(TOOL_CALL_MARKER):].strip()
                try:
                    data = json.loads(json_str)
                    calls.append(ToolCall(name=data["name"], arguments=data.get("arguments", {})))
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Failed to parse tool call: %s — %s", json_str, e)
        return calls

    def _strip_tool_calls(self, content: str) -> str:
        return "\n".join(
            line for line in content.splitlines()
            if not line.strip().startswith(TOOL_CALL_MARKER)
        ).strip()


# Singleton
ollama = OllamaClient()
