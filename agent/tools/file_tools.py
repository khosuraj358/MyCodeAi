"""
File system tools: read, write, list, search, delete.
All paths are resolved relative to the workspace root.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from ..core.config import settings
from .registry import tool_registry

WORKSPACE = settings.workspace_root


def _safe_path(relative: str) -> Path:
    """Resolve a relative path inside the workspace, blocking path traversal."""
    resolved = (WORKSPACE / relative).resolve()
    if not str(resolved).startswith(str(WORKSPACE.resolve())):
        raise PermissionError(f"Path traversal blocked: {relative}")
    return resolved


@tool_registry.register(
    name="read_file",
    description="Read the content of a file in the workspace.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path"},
            "start_line": {"type": "integer", "description": "First line to read (1-indexed, optional)"},
            "end_line": {"type": "integer", "description": "Last line to read (inclusive, optional)"},
        },
        "required": ["path"],
    },
)
async def read_file(path: str, start_line: int = None, end_line: int = None) -> str:
    p = _safe_path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    text = p.read_text(encoding="utf-8", errors="replace")
    if start_line or end_line:
        lines = text.splitlines()
        sl = (start_line or 1) - 1
        el = end_line or len(lines)
        text = "\n".join(lines[sl:el])
    return text


@tool_registry.register(
    name="write_file",
    description="Write content to a file, creating parent directories as needed.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
    requires_permission=True,
)
async def write_file(path: str, content: str) -> str:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written {len(content)} bytes to {path}"


@tool_registry.register(
    name="edit_file",
    description="Replace a specific string in a file with new content.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_str": {"type": "string", "description": "Exact string to replace"},
            "new_str": {"type": "string", "description": "Replacement string"},
        },
        "required": ["path", "old_str", "new_str"],
    },
    requires_permission=True,
)
async def edit_file(path: str, old_str: str, new_str: str) -> str:
    p = _safe_path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    if old_str not in text:
        raise ValueError(f"String not found in {path}: {old_str[:80]!r}")
    updated = text.replace(old_str, new_str, 1)
    p.write_text(updated, encoding="utf-8")
    return f"Edited {path}"


@tool_registry.register(
    name="list_directory",
    description="List files and directories at a path.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative directory path (default: '.')"},
            "recursive": {"type": "boolean", "description": "Recurse into subdirectories"},
        },
        "required": [],
    },
)
async def list_directory(path: str = ".", recursive: bool = False) -> list[str]:
    p = _safe_path(path)
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    if recursive:
        return [
            str(f.relative_to(WORKSPACE))
            for f in p.rglob("*")
            if not any(part.startswith(".") for part in f.parts)
        ]
    return [str(f.relative_to(WORKSPACE)) for f in sorted(p.iterdir())]


@tool_registry.register(
    name="search_files",
    description="Search for files matching a glob pattern or containing a text string.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern like '**/*.py'"},
            "contains": {"type": "string", "description": "Text to search inside files"},
        },
        "required": ["pattern"],
    },
)
async def search_files(pattern: str, contains: str = None) -> list[str]:
    matches = [
        str(p.relative_to(WORKSPACE))
        for p in WORKSPACE.rglob(pattern)
        if p.is_file() and not any(part.startswith(".") for part in p.parts)
    ]
    if contains:
        filtered = []
        for m in matches:
            try:
                content = _safe_path(m).read_text(encoding="utf-8", errors="replace")
                if contains in content:
                    filtered.append(m)
            except Exception:
                pass
        return filtered
    return matches


@tool_registry.register(
    name="delete_file",
    description="Delete a file from the workspace.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    },
    requires_permission=True,
)
async def delete_file_tool(path: str) -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"File does not exist: {path}"
    p.unlink()
    return f"Deleted {path}"
