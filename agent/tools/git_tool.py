"""
Git tools: checkpoint (commit), rewind (restore), diff, log.
Also provides a standalone GitTool class for the server.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core.config import settings
from .registry import tool_registry

WORKSPACE = settings.workspace_root


async def _git(args: list[str], cwd: Path = WORKSPACE) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode,
        stdout.decode("utf-8", errors="replace").strip(),
        stderr.decode("utf-8", errors="replace").strip(),
    )


@tool_registry.register(
    name="git_checkpoint",
    description="Stage all changes and create a Git commit (checkpoint) with a message.",
    parameters={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Commit message"},
        },
        "required": ["message"],
    },
    requires_permission=True,
)
async def git_checkpoint(message: str) -> str:
    # Ensure we're in a git repo
    code, _, err = await _git(["rev-parse", "--is-inside-work-tree"])
    if code != 0:
        await _git(["init"])
        await _git(["config", "user.email", "mycodeai@local"])
        await _git(["config", "user.name", "MyCodeAI"])

    await _git(["add", "-A"])
    full_msg = f"{settings.checkpoint_prefix}: {message}"
    code, sha, err = await _git(["commit", "-m", full_msg])
    if code != 0:
        if "nothing to commit" in err:
            return "Nothing to commit"
        raise RuntimeError(f"Git commit failed: {err}")

    code, sha, _ = await _git(["rev-parse", "--short", "HEAD"])
    return f"Checkpoint created: {sha}"


@tool_registry.register(
    name="git_diff",
    description="Show uncommitted changes (git diff) or diff between two commits.",
    parameters={
        "type": "object",
        "properties": {
            "from_ref": {"type": "string", "description": "Base commit/branch (optional)"},
            "to_ref": {"type": "string", "description": "Target commit/branch (optional)"},
            "path": {"type": "string", "description": "Limit diff to this file path (optional)"},
        },
        "required": [],
    },
)
async def git_diff(from_ref: str = None, to_ref: str = None, path: str = None) -> str:
    args = ["diff"]
    if from_ref and to_ref:
        args += [from_ref, to_ref]
    elif from_ref:
        args += [from_ref]
    if path:
        args += ["--", path]
    _, output, _ = await _git(args)
    return output or "(no changes)"


@tool_registry.register(
    name="git_log",
    description="Show recent Git commit history.",
    parameters={
        "type": "object",
        "properties": {
            "n": {"type": "integer", "description": "Number of commits to show (default 10)"},
        },
        "required": [],
    },
)
async def git_log(n: int = 10) -> list[dict]:
    _, output, _ = await _git(["log", f"-{n}", "--pretty=format:%H|%s|%ai"])
    if not output:
        return []
    commits = []
    for line in output.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"sha": parts[0][:8], "message": parts[1], "date": parts[2]})
    return commits


@tool_registry.register(
    name="git_rewind",
    description="Restore the workspace to a previous Git checkpoint (commit SHA).",
    parameters={
        "type": "object",
        "properties": {
            "sha": {"type": "string", "description": "Commit SHA to restore to"},
            "hard": {"type": "boolean", "description": "Hard reset (discards all uncommitted changes)"},
        },
        "required": ["sha"],
    },
    requires_permission=True,
)
async def git_rewind(sha: str, hard: bool = False) -> str:
    if hard:
        code, _, err = await _git(["reset", "--hard", sha])
    else:
        code, _, err = await _git(["checkout", sha])
    if code != 0:
        raise RuntimeError(f"Git rewind failed: {err}")
    return f"Rewound to {sha[:8]}"


# ── Standalone class (used by the server endpoint) ────────────────────────────

class GitTool:
    def __init__(self, workspace: Path = WORKSPACE):
        self.workspace = workspace

    async def checkpoint(self, message: str) -> str:
        return await git_checkpoint(message)

    async def diff(self) -> str:
        return await git_diff()

    async def log(self, n: int = 10) -> list[dict]:
        return await git_log(n)
