"""
Shell execution tool: run terminal commands inside the workspace.
"""
from __future__ import annotations

import asyncio
import shlex
from pathlib import Path

from ..core.config import settings
from .registry import tool_registry

WORKSPACE = settings.workspace_root
TIMEOUT = 120  # seconds


@tool_registry.register(
    name="run_command",
    description=(
        "Execute a shell command in the workspace directory. "
        "Use this to run build tools, tests, linters, package managers, etc. "
        "Avoid interactive commands."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run"},
            "cwd": {
                "type": "string",
                "description": "Working directory relative to workspace root (default: workspace root)",
            },
            "timeout": {
                "type": "integer",
                "description": f"Timeout in seconds (default: {TIMEOUT})",
            },
        },
        "required": ["command"],
    },
    requires_permission=True,
)
async def run_command(command: str, cwd: str = ".", timeout: int = TIMEOUT) -> dict:
    work_dir = (WORKSPACE / cwd).resolve()
    if not str(work_dir).startswith(str(WORKSPACE.resolve())):
        raise PermissionError("Working directory outside workspace")

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(work_dir),
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "success": False,
        }

    return {
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[:20_000],
        "stderr": stderr.decode("utf-8", errors="replace")[:5_000],
        "success": proc.returncode == 0,
    }
