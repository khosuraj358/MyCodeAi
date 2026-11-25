"""
Shell execution tool: run terminal commands inside the workspace.
"""
from __future__ import annotations

import asyncio

from ._paths import resolve_path
from .registry import tool_registry

TIMEOUT = 120  # seconds


@tool_registry.register(
    name="run_command",
    description=(
        "Execute a shell command. Can run anywhere inside /home, /tmp or the "
        "workspace — set cwd to the project directory (e.g. "
        "/home/ubuntu/Desktop/myapp) to install deps, build, test or run code. "
        "Avoid interactive commands."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run"},
            "cwd": {
                "type": "string",
                "description": "Working directory (absolute, or relative to workspace root). Default: workspace root",
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
    work_dir = resolve_path(cwd or ".")
    if not work_dir.is_dir():
        raise NotADirectoryError(f"Working directory does not exist: {work_dir}")

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
