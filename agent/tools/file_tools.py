"""
File system tools: read, write, list, search, delete.

Path handling:
- Absolute paths are used as-is (after safety check stays on same machine)
- Relative paths are resolved from WORKSPACE root
- Paths starting with ~ are expanded
"""
from __future__ import annotations

from pathlib import Path

from ._paths import WORKSPACE, resolve_path as _resolve_path
from .registry import tool_registry


@tool_registry.register(
    name="read_file",
    description="Read the content of a file. Accepts absolute or relative paths.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path (absolute or relative to workspace)"},
            "start_line": {"type": "integer", "description": "First line (1-indexed, optional)"},
            "end_line":   {"type": "integer", "description": "Last line (inclusive, optional)"},
        },
        "required": ["path"],
    },
)
async def read_file(path: str, start_line: int = None, end_line: int = None) -> str:
    p = _resolve_path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    text = p.read_text(encoding="utf-8", errors="replace")
    if start_line or end_line:
        lines = text.splitlines()
        sl = (start_line or 1) - 1
        el = end_line or len(lines)
        text = "\n".join(lines[sl:el])
    return text


@tool_registry.register(
    name="write_file",
    description=(
        "Write content to a file, creating parent directories automatically. "
        "Use absolute paths like /home/ubuntu/Desktop/myproject/main.py"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path":    {"type": "string", "description": "Absolute or relative file path"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
    requires_permission=True,
)
async def write_file(path: str, content: str) -> str:
    p = _resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written {len(content)} bytes to {p}"


@tool_registry.register(
    name="edit_file",
    description="Replace a specific string in a file with new content.",
    parameters={
        "type": "object",
        "properties": {
            "path":    {"type": "string"},
            "old_str": {"type": "string", "description": "Exact string to replace"},
            "new_str": {"type": "string", "description": "Replacement string"},
            "replace_all": {
                "type": "boolean",
                "description": "Replace every occurrence instead of just the first (default false)",
            },
        },
        "required": ["path", "old_str", "new_str"],
    },
    requires_permission=True,
)
async def edit_file(
    path: str, old_str: str, new_str: str, replace_all: bool = False
) -> str:
    p = _resolve_path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    count = text.count(old_str)
    if count == 0:
        raise ValueError(f"String not found in {p}: {old_str[:80]!r}")
    if replace_all:
        p.write_text(text.replace(old_str, new_str), encoding="utf-8")
        return f"Edited {p} ({count} replacement{'s' if count != 1 else ''})"
    p.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")
    extra = (
        f" ({count} matches found — replaced only the first; "
        "pass replace_all=true to replace all)"
        if count > 1
        else ""
    )
    return f"Edited {p}{extra}"


@tool_registry.register(
    name="list_directory",
    description="List files and directories at a given path.",
    parameters={
        "type": "object",
        "properties": {
            "path":      {"type": "string", "description": "Directory path (default: workspace root)"},
            "recursive": {"type": "boolean", "description": "Recurse into subdirectories"},
        },
        "required": [],
    },
)
async def list_directory(path: str = ".", recursive: bool = False) -> list[str]:
    p = _resolve_path(path)
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {p}")
    if recursive:
        return [str(f) for f in sorted(p.rglob("*"))
                if f.is_file() and not any(part.startswith(".") for part in f.parts[-3:])]
    return [str(f) for f in sorted(p.iterdir())]


@tool_registry.register(
    name="search_files",
    description="Search for files by glob pattern, optionally filtering by content.",
    parameters={
        "type": "object",
        "properties": {
            "pattern":  {"type": "string", "description": "Glob like '**/*.py'"},
            "path":     {"type": "string", "description": "Directory to search in (default: workspace root)"},
            "contains": {"type": "string", "description": "Text substring to search inside files"},
        },
        "required": ["pattern"],
    },
)
async def search_files(pattern: str, contains: str = None, path: str = None) -> list[str]:
    root = _resolve_path(path) if path else WORKSPACE
    skip = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
    matches = [
        str(p) for p in root.rglob(pattern)
        if p.is_file() and not any(part in skip for part in p.parts)
    ]
    if contains:
        matches = [m for m in matches if contains in Path(m).read_text(errors="replace")]
    return matches


@tool_registry.register(
    name="delete_file",
    description="Delete a file.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    requires_permission=True,
)
async def delete_file_tool(path: str) -> str:
    p = _resolve_path(path)
    if not p.exists():
        return f"File does not exist: {p}"
    p.unlink()
    return f"Deleted {p}"
