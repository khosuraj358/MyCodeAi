"""
Shared path resolution + safety checks for all file/shell/project tools.

Every tool that touches the disk resolves its paths through here so the
allowed-roots policy is defined in exactly one place.
"""
from __future__ import annotations

from pathlib import Path

from ..core.config import settings

WORKSPACE = settings.workspace_root

# Directories the agent is allowed to read/write/execute inside.
# This is what lets the agent build and run projects on the Desktop.
ALLOWED_ROOTS: list[Path] = [
    Path("/home"),
    Path("/tmp"),
    Path("/opt/mycodeai"),
]


def allowed_roots() -> list[Path]:
    roots = list(ALLOWED_ROOTS)
    try:
        roots.append(WORKSPACE.resolve())
    except Exception:
        pass
    return roots


def resolve_path(path: str) -> Path:
    """
    Resolve any path the model provides to an absolute Path.
    - Absolute paths used directly   (e.g. /home/ubuntu/Desktop/add.cpp)
    - Relative paths resolved from WORKSPACE (e.g. add/add.cpp)
    - ~ expanded (e.g. ~/Desktop/add.cpp)
    Blocks anything outside the allowed roots.
    """
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = WORKSPACE / p
    p = p.resolve()

    roots = allowed_roots()
    if not any(str(p) == str(r) or str(p).startswith(str(r) + "/") for r in roots):
        raise PermissionError(f"Path outside allowed directories: {p}")
    return p
