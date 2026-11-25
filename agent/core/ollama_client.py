"""
Async Ollama client wrapper.

Tool-use strategy
-----------------
We use Ollama's NATIVE tool-calling API (available since Ollama 0.3.x).
When tools are provided, we pass them as `tools` in the request payload and
read `message.tool_calls` from the response — no custom prompt injection needed.

Fallback: if the model doesn't support native tool calls, we extract them
from the text using multiple pattern strategies.
"""

from __future__ import annotations

import json
import logging
import re
from typing import AsyncIterator, Optional

import httpx

from .config import settings
from .models import Message, Role, ToolCall

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str = settings.ollama_base_url):
        self._base = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=600)

    # ── Public API ────────────────────────────────────────────────────────────

    async def list_models(self) -> list[str]:
        resp = await self._http.get(f"{self._base}/api/tags")
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]

    async def is_running(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            await self._http.get(f"{self._base}/api/tags", timeout=3)
            return True
        except Exception:
            return False

    async def warm_model(self, model: str) -> bool:
        """
        Preload a model into Ollama memory so the first real request is fast.
        Sends a trivial 1-token prompt to force model load. Returns True on success.
        """
        try:
            resp = await self._http.post(
                f"{self._base}/api/generate",
                json={"model": model, "prompt": "", "stream": False,
                      "options": {"num_predict": 1}},
                timeout=120,
            )
            resp.raise_for_status()
            logger.info("warmed model: %s", model)
            return True
        except Exception as e:
            logger.warning("warm model %s failed: %s", model, e)
            return False

    async def chat(
        self,
        messages: list[Message],
        model: str = settings.default_model,
        tools: Optional[list[dict]] = None,
        system_prompt: str = "",
        temperature: float = 0.2,
    ) -> Message:
        """Non-streaming chat using Ollama native tool-calling API."""
        payload = self._build_payload(
            messages, model, tools, system_prompt, temperature, stream=False
        )
        resp = await self._http.post(f"{self._base}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        msg = data.get("message", {})
        content: str = msg.get("content", "")

        # ── 1. Native Ollama tool_calls (best — works on supported models) ──
        native_calls = msg.get("tool_calls", [])
        if native_calls:
            tool_calls = []
            for tc in native_calls:
                fn = tc.get("function", tc)
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except:
                        args = {}
                tool_calls.append(ToolCall(name=name, arguments=args))
            return Message(
                role=Role.ASSISTANT,
                content=content.strip(),
                tool_calls=tool_calls,
                tokens=data.get("eval_count", 0),
            )

        # ── 2. Text-based extraction fallback ─────────────────────────────
        tool_calls = self._extract_tool_calls(content)
        clean = self._strip_tool_calls(content) if tool_calls else content.strip()
        return Message(
            role=Role.ASSISTANT,
            content=clean,
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
        """Streaming — yields visible text tokens only."""
        payload = self._build_payload(
            messages,
            model,
            None,  # no tools in stream mode (use REST for agentic)
            system_prompt,
            temperature,
            stream=True,
        )
        async with self._http.stream(
            "POST", f"{self._base}/api/chat", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token: str = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
                if chunk.get("done"):
                    break

    # ── Payload builder ───────────────────────────────────────────────────────

    def _build_payload(
        self,
        messages: list[Message],
        model: str,
        tools: Optional[list[dict]],
        system_prompt: str,
        temperature: float,
        stream: bool,
    ) -> dict:
        ollama_messages: list[dict] = []

        # System prompt (no tool injection — using native tool API instead)
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})

        for m in messages:
            role = (
                m.role.value
                if m.role.value in ("user", "assistant", "tool")
                else "user"
            )
            ollama_messages.append({"role": role, "content": m.content})
            for tr in m.tool_results:
                body = (
                    json.dumps(tr.output, default=str)
                    if not tr.error
                    else f"ERROR: {tr.error}"
                )
                ollama_messages.append(
                    {
                        "role": "tool",
                        "content": f"[{tr.name}]\n{body}",
                    }
                )

        payload: dict = {
            "model": model,
            "messages": ollama_messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_ctx": settings.context_window,
                "num_predict": settings.max_response_tokens,
            },
        }

        # Attach tools in Ollama's native format when provided
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {}),
                    },
                }
                for t in tools
            ]

        return payload

    # ── Text-based tool call extraction (fallback) ────────────────────────────

    def _extract_tool_calls(self, content: str) -> list[ToolCall]:
        """
        Try multiple patterns to extract tool calls from model text output.
        Models use different formats; we handle all common ones.
        """
        calls: list[ToolCall] = []

        # Pattern 1: <tool_call>{"name":..., "arguments":{...}}</tool_call>
        for m in re.finditer(r"<tool_call>(.*?)</tool_call>", content, re.DOTALL):
            call = self._parse_tc_json(m.group(1).strip())
            if call:
                calls.append(call)

        if calls:
            return calls

        # Pattern 2: ```json\n{"name":..., "arguments":{...}}\n```
        for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL):
            call = self._parse_tc_json(m.group(1).strip())
            if call:
                calls.append(call)

        if calls:
            return calls

        # Pattern 3: Bare JSON object on its own line with "name" and "arguments"
        for line in content.splitlines():
            line = line.strip()
            if (
                line.startswith("{")
                and '"name"' in line
                and ('"arguments"' in line or '"path"' in line)
            ):
                call = self._parse_tc_json(line)
                if call:
                    calls.append(call)

        if calls:
            return calls

        # Pattern 4: TOOL_CALL: {"name":...} (legacy)
        for line in content.splitlines():
            if line.strip().startswith("TOOL_CALL:"):
                call = self._parse_tc_json(line.strip()[len("TOOL_CALL:") :].strip())
                if call:
                    calls.append(call)

        return calls

    def _parse_tc_json(self, raw: str) -> Optional[ToolCall]:
        try:
            data = json.loads(raw)
            name = data.get("name") or data.get("function", {}).get("name")
            if not name:
                return None
            args = (
                data.get("arguments")
                or data.get("parameters")
                or data.get("args")
                or {}
            )
            if isinstance(args, str):
                args = json.loads(args)
            return ToolCall(name=name, arguments=args)
        except Exception:
            return None

    def _strip_tool_calls(self, content: str) -> str:
        """Remove all tool call syntax from visible text."""
        # Remove XML tags
        content = re.sub(r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL)
        # Remove JSON code blocks that look like tool calls
        content = re.sub(
            r"```(?:json|xml)?\s*\{[^`]*\"name\"[^`]*\}\s*```",
            "",
            content,
            flags=re.DOTALL,
        )
        # Remove bare JSON tool call lines
        lines = []
        for line in content.splitlines():
            s = line.strip()
            if (
                s.startswith("{")
                and '"name"' in s
                and ('"arguments"' in s or '"path"' in s)
            ):
                continue
            if s.startswith("TOOL_CALL:"):
                continue
            lines.append(line)
        return "\n".join(lines).strip()


# Module-level singleton
ollama = OllamaClient()
