"""
Hook runner — loads hook definitions from .kiro/hooks/*.json and fires them
on events, mirroring Kiro's hook system.

Hook JSON format:
{
  "version": "v1",
  "hooks": [{
    "name": "My Hook",
    "trigger": "PostFileSave",
    "matcher": "\\.py$",
    "action": {
      "type": "command",
      "command": "python -m pytest --tb=short -q"
    }
  }]
}

Action types:
  command — run a shell command; stdin receives JSON event context
  agent   — appends a prompt to the current agent context (handled by orchestrator)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from ..core.config import settings

logger = logging.getLogger(__name__)

HOOKS_DIR = settings.workspace_root / settings.hooks_dir


class HookRunner:
    def __init__(self, hooks_dir: Path = HOOKS_DIR):
        self.hooks_dir = hooks_dir
        self._hooks: list[dict] = []
        self._loaded = False

    def _load(self):
        self._hooks = []
        if not self.hooks_dir.exists():
            return
        for f in self.hooks_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                for hook in data.get("hooks", []):
                    hook["_source"] = f.name
                    self._hooks.append(hook)
            except Exception as e:
                logger.warning("Failed to load hook %s: %s", f.name, e)
        self._loaded = True
        logger.debug("Loaded %d hooks from %s", len(self._hooks), self.hooks_dir)

    async def fire(self, trigger: str, context: dict[str, Any] = {}):
        """Fire all hooks matching the given trigger."""
        if not self._loaded:
            self._load()

        matching = [
            h for h in self._hooks
            if h.get("trigger") == trigger
        ]

        for hook in matching:
            matcher = hook.get("matcher")
            if matcher:
                target = context.get("path", context.get("message", ""))
                if not re.search(matcher, str(target)):
                    continue
            await self._execute_hook(hook, context)

    async def _execute_hook(self, hook: dict, context: dict):
        action = hook.get("action", {})
        atype = action.get("type")

        if atype == "command":
            await self._run_command_hook(hook["name"], action["command"], context)
        elif atype == "agent":
            # Agent hooks inject a prompt — returned to caller via context
            logger.info("Agent hook '%s' fired: %s", hook["name"], action.get("prompt", "")[:80])
        else:
            logger.warning("Unknown hook action type: %s", atype)

    async def _run_command_hook(self, name: str, command: str, context: dict):
        ctx_json = json.dumps(context).encode()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(settings.workspace_root),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=ctx_json), timeout=60
            )
            if proc.returncode == 0:
                logger.info("Hook '%s' succeeded", name)
            elif proc.returncode == 2:
                logger.warning("Hook '%s' blocked action: %s", name, stderr.decode()[:200])
            else:
                logger.debug("Hook '%s' exited %d: %s", name, proc.returncode, stderr.decode()[:200])
        except asyncio.TimeoutError:
            logger.error("Hook '%s' timed out", name)
        except Exception as e:
            logger.error("Hook '%s' error: %s", name, e)
