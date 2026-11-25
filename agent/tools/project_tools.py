"""
Project tools — understand, prepare and run a project or a single file.

These give the agent Cursor/Kiro-style project awareness:

  detect_project  → what kind of project is this, and how do I build/run it
  read_project    → tree + key files, so the model "knows what the project is"
  run_file        → execute one file (auto-detects the interpreter)
  setup_env       → create a venv / install dependencies
  search_code     → regex search across a project
"""
from __future__ import annotations

import asyncio
import re
import shlex
import tempfile
from pathlib import Path

from ._paths import resolve_path
from .registry import tool_registry

# ── Shared helpers ────────────────────────────────────────────────────────────

IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".dart_tool", "target", "vendor",
    ".idea", ".vscode", ".mypy_cache", ".pytest_cache",
}

_TEXT_SKIP_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".whl", ".so", ".o", ".a", ".class", ".exe", ".dll", ".bin",
    ".mp3", ".mp4", ".woff", ".woff2", ".ttf", ".lock",
}

# Marker file → project type
_PROJECT_MARKERS: dict[str, str] = {
    "package.json": "node",
    "requirements.txt": "python",
    "pyproject.toml": "python",
    "setup.py": "python",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "Gemfile": "ruby",
    "composer.json": "php",
    "pubspec.yaml": "flutter",
    "CMakeLists.txt": "cpp",
    "Makefile": "make",
}

_ENTRY_CANDIDATES = [
    "main.py", "app.py", "run.py", "manage.py", "cli.py", "server.py",
    "index.js", "main.js", "server.js", "app.js", "index.mjs",
    "index.ts", "main.ts", "server.ts",
    "main.go", "main.rs", "Main.java",
    "lib/main.dart",
    "src/main.py", "src/main.js", "src/main.ts", "src/index.js",
    "src/index.ts", "src/main.rs", "src/main.go",
]

_KEY_FILES = [
    "README.md", "README.rst", "README", "package.json", "requirements.txt",
    "pyproject.toml", "Cargo.toml", "go.mod", "Makefile", "docker-compose.yml",
    "Dockerfile", ".env.example",
]


async def _exec(argv: list[str], cwd: Path, timeout: int) -> dict:
    """Run an argv list, capturing output. Returns a uniform result dict."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
    except FileNotFoundError as e:
        return {"command": " ".join(argv), "exit_code": 127,
                "stdout": "", "stderr": str(e), "success": False}
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"command": " ".join(argv), "exit_code": -1, "stdout": "",
                "stderr": f"Timed out after {timeout}s", "success": False}
    return {
        "command": " ".join(argv),
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[:20_000],
        "stderr": stderr.decode("utf-8", errors="replace")[:5_000],
        "success": proc.returncode == 0,
    }


def _venv_python(root: Path) -> str:
    candidate = root / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else "python3"


def _find_entry_points(root: Path) -> list[str]:
    found: list[str] = []
    for rel in _ENTRY_CANDIDATES:
        if (root / rel).is_file():
            found.append(rel)
    # Shallow fallback: any */main.py or */app.py one level down
    if not found:
        for pat in ("*/main.py", "*/app.py", "*/index.js", "*/main.go"):
            for f in root.glob(pat):
                if f.is_file() and not any(p in IGNORE_DIRS for p in f.parts):
                    found.append(str(f.relative_to(root)))
    return found[:5]


# ── detect_project ────────────────────────────────────────────────────────────

@tool_registry.register(
    name="detect_project",
    description=(
        "Inspect a directory and report its project type (python/node/rust/go/…), "
        "entry point, package manager, and the exact install/run/test/build commands. "
        "Use this before building or running a project."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Project directory (absolute or relative)"},
        },
        "required": ["path"],
    },
)
async def detect_project(path: str) -> dict:
    root = resolve_path(path)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    markers = [m for m in _PROJECT_MARKERS if (root / m).exists()]
    ptype = _PROJECT_MARKERS[markers[0]] if markers else "unknown"
    entries = _find_entry_points(root)
    entry = entries[0] if entries else ""

    install = run = test = build = ""
    if ptype == "python":
        py = _venv_python(root)
        install = (f"{py} -m venv .venv && .venv/bin/pip install -r requirements.txt"
                   if (root / "requirements.txt").exists()
                   else f"{py} -m venv .venv && .venv/bin/pip install -e ."
                   if (root / "pyproject.toml").exists()
                   else "python3 -m venv .venv")
        run = f".venv/bin/python {entry}" if entry else ".venv/bin/python -m <module>"
        test = "pytest"
    elif ptype == "node":
        pm = ("pnpm" if (root / "pnpm-lock.yaml").exists()
              else "yarn" if (root / "yarn.lock").exists() else "npm")
        install = f"{pm} install"
        run = f"{pm} start" if _has_script(root, "start") else f"node {entry or 'index.js'}"
        test = f"{pm} test"
        build = f"{pm} run build" if _has_script(root, "build") else ""
    elif ptype == "rust":
        install, run, test, build = "cargo build", "cargo run", "cargo test", "cargo build --release"
    elif ptype == "go":
        install, run, test, build = "go mod download", "go run .", "go test ./...", "go build ./..."
    elif ptype == "java":
        tool = "mvn" if (root / "pom.xml").exists() else "gradle"
        install, run, test, build = f"{tool} install", f"{tool} run", f"{tool} test", f"{tool} build"
    elif ptype == "ruby":
        install, run, test = "bundle install", f"ruby {entry or 'main.rb'}", "bundle exec rspec"
    elif ptype == "php":
        install, run, test = "composer install", f"php {entry or 'index.php'}", "phpunit"
    elif ptype == "flutter":
        install, run, test, build = "flutter pub get", "flutter run", "flutter test", "flutter build"
    elif ptype == "cpp":
        install, run = "", f"g++ -o app {entry or 'main.cpp'} && ./app"

    return {
        "path": str(root),
        "type": ptype,
        "markers": markers,
        "entry_points": entries,
        "entry_point": entry,
        "package_manager": _pkg_manager(ptype, root),
        "install_cmd": install,
        "run_cmd": run,
        "test_cmd": test,
        "build_cmd": build,
    }


def _has_script(root: Path, name: str) -> bool:
    import json
    pkg = root / "package.json"
    if not pkg.exists():
        return False
    try:
        return name in json.loads(pkg.read_text()).get("scripts", {})
    except Exception:
        return False


def _pkg_manager(ptype: str, root: Path) -> str:
    if ptype == "node":
        if (root / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (root / "yarn.lock").exists():
            return "yarn"
        return "npm"
    return {"python": "pip", "rust": "cargo", "go": "go modules",
            "java": "maven" if (root / "pom.xml").exists() else "gradle",
            "ruby": "bundler", "php": "composer", "flutter": "pub"}.get(ptype, "n/a")


# ── read_project ──────────────────────────────────────────────────────────────

@tool_registry.register(
    name="read_project",
    description=(
        "Read a whole project at once: a directory tree plus the contents of its "
        "key files (README, package.json, requirements.txt, entry points). Use this "
        "to understand what an existing project is before editing it."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Project root directory"},
            "max_tree_entries": {"type": "integer", "description": "Max tree entries (default 200)"},
        },
        "required": ["path"],
    },
)
async def read_project(path: str, max_tree_entries: int = 200) -> str:
    root = resolve_path(path)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    lines = [f"# Project: {root.name}", f"Path: {root}", ""]

    # Tree (depth-limited)
    lines.append("## Structure")
    lines.extend(_tree(root, max_tree_entries))
    lines.append("")

    # Key files
    seen: set[str] = set()
    for name in _KEY_FILES:
        f = root / name
        if f.is_file():
            seen.add(name)
            lines.append(f"## {name}")
            lines.append("```")
            lines.append(_read_capped(f, 4000))
            lines.append("```")
            lines.append("")

    # Entry points
    for entry in _find_entry_points(root)[:3]:
        if entry in seen:
            continue
        f = root / entry
        lines.append(f"## {entry} (entry point)")
        lines.append("```")
        lines.append(_read_capped(f, 4000))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _tree(root: Path, max_entries: int, max_depth: int = 3) -> list[str]:
    out: list[str] = []
    count = 0

    def walk(d: Path, prefix: str, depth: int):
        nonlocal count
        if depth > max_depth or count >= max_entries:
            return
        try:
            items = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name))
        except Exception:
            return
        for item in items:
            if count >= max_entries:
                out.append(prefix + "… (truncated)")
                return
            if item.name.startswith(".") and item.name not in (".env.example",):
                continue
            if item.is_dir():
                if item.name in IGNORE_DIRS:
                    continue
                out.append(f"{prefix}{item.name}/")
                count += 1
                walk(item, prefix + "  ", depth + 1)
            else:
                out.append(f"{prefix}{item.name}")
                count += 1

    walk(root, "", 1)
    return out


def _read_capped(f: Path, cap: int) -> str:
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"<could not read: {e}>"
    return text if len(text) <= cap else text[:cap] + "\n… (truncated)"


# ── run_file ──────────────────────────────────────────────────────────────────

@tool_registry.register(
    name="run_file",
    description=(
        "Execute a single source file, automatically choosing the right interpreter "
        "by extension (python/node/bash/ruby/php/go, compiling c/cpp/rust/java). "
        "Runs in the file's own directory unless cwd is given."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to run"},
            "args": {"type": "string", "description": "Space-separated CLI args (optional)"},
            "cwd": {"type": "string", "description": "Working directory (default: the file's directory)"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)"},
        },
        "required": ["path"],
    },
    requires_permission=True,
)
async def run_file(
    path: str, args: str = "", cwd: str = None, timeout: int = 120
) -> dict:
    p = resolve_path(path)
    if not p.is_file():
        return {"command": "", "exit_code": -1, "stdout": "",
                "stderr": f"File not found: {p}", "success": False}

    work_dir = resolve_path(cwd) if cwd else p.parent
    extra = shlex.split(args) if args else []
    ext = p.suffix.lower()
    name = p.name

    # Compile-then-run languages
    if ext in (".c", ".cpp", ".cc", ".cxx", ".rs"):
        return await _compile_and_run(p, ext, work_dir, extra, timeout)

    table = {
        ".py": lambda: ["python3", name],
        ".js": lambda: ["node", name],
        ".mjs": lambda: ["node", name],
        ".cjs": lambda: ["node", name],
        ".ts": lambda: ["npx", "--yes", "ts-node", name],
        ".sh": lambda: ["bash", name],
        ".bash": lambda: ["bash", name],
        ".rb": lambda: ["ruby", name],
        ".php": lambda: ["php", name],
        ".go": lambda: ["go", "run", name],
        ".java": lambda: ["java", name],  # single-file source launch (Java 11+)
        ".pl": lambda: ["perl", name],
        ".lua": lambda: ["lua", name],
    }
    builder = table.get(ext)
    if not builder:
        if ext in (".html", ".htm"):
            return {"command": "", "exit_code": 0, "stdout":
                    f"{name} is a web page — open it in a browser; it cannot be run headless.",
                    "stderr": "", "success": True}
        return {"command": "", "exit_code": -1, "stdout": "",
                "stderr": f"Don't know how to run '{ext}' files. "
                          "Use run_command with an explicit interpreter instead.",
                "success": False}

    return await _exec(builder() + extra, work_dir, timeout)


async def _compile_and_run(
    p: Path, ext: str, work_dir: Path, extra: list[str], timeout: int
) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="mycodeai_run_"))
    out_bin = tmp / p.stem
    if ext == ".c":
        compiler, argv = "gcc", ["gcc", str(p), "-o", str(out_bin)]
    elif ext == ".rs":
        compiler, argv = "rustc", ["rustc", str(p), "-o", str(out_bin)]
    else:
        compiler, argv = "g++", ["g++", str(p), "-o", str(out_bin)]

    comp = await _exec(argv, work_dir, timeout)
    if not comp["success"]:
        return {"command": comp["command"], "exit_code": comp["exit_code"],
                "stdout": comp["stdout"], "stderr": f"Compile failed:\n{comp['stderr']}",
                "success": False}
    return await _exec([str(out_bin), *extra], work_dir, timeout)


# ── setup_env ─────────────────────────────────────────────────────────────────

@tool_registry.register(
    name="setup_env",
    description=(
        "Prepare a project's execution environment: create a Python venv, or run "
        "npm/cargo/go/composer/bundle install etc. based on the detected project type. "
        "Call this before running a project for the first time."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Project root directory"},
            "timeout": {"type": "integer", "description": "Per-step timeout in seconds (default 300)"},
        },
        "required": ["path"],
    },
    requires_permission=True,
)
async def setup_env(path: str, timeout: int = 300) -> dict:
    root = resolve_path(path)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    det = await detect_project(str(root))
    ptype = det["type"]
    steps: list[dict] = []

    async def step(argv: list[str]):
        res = await _exec(argv, root, timeout)
        steps.append({"cmd": res["command"], "exit_code": res["exit_code"],
                      "ok": res["success"], "output": (res["stdout"] + res["stderr"])[-1500:]})
        return res["success"]

    if ptype == "python":
        if not (root / ".venv").exists():
            await step(["python3", "-m", "venv", ".venv"])
        py = str(root / ".venv" / "bin" / "python")
        await step([py, "-m", "pip", "install", "--upgrade", "pip"])
        if (root / "requirements.txt").exists():
            await step([py, "-m", "pip", "install", "-r", "requirements.txt"])
        elif (root / "pyproject.toml").exists():
            await step([py, "-m", "pip", "install", "-e", "."])
    elif ptype == "node":
        pm = _pkg_manager(ptype, root)
        await step([pm, "install"])
    elif ptype == "rust":
        await step(["cargo", "build"])
    elif ptype == "go":
        await step(["go", "mod", "download"])
    elif ptype == "ruby":
        await step(["bundle", "install"])
    elif ptype == "php":
        await step(["composer", "install"])
    elif ptype == "flutter":
        await step(["flutter", "pub", "get"])
    elif ptype == "java":
        await step(["mvn", "install", "-DskipTests"]
                   if (root / "pom.xml").exists() else ["gradle", "build", "-x", "test"])
    else:
        return {"project_type": ptype, "steps": [],
                "note": f"No known environment setup for project type '{ptype}'. "
                        f"Markers found: {det['markers']}"}

    return {
        "project_type": ptype,
        "steps": steps,
        "success": all(s["ok"] for s in steps) if steps else True,
    }


# ── search_code ───────────────────────────────────────────────────────────────

@tool_registry.register(
    name="search_code",
    description=(
        "Search file contents across a project with a regular expression "
        "(grep-style). Returns matching file:line: text lines."
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regular expression to search for"},
            "path": {"type": "string", "description": "Directory to search (default: workspace)"},
            "file_glob": {"type": "string", "description": "Limit to files, e.g. '*.py'"},
            "ignore_case": {"type": "boolean", "description": "Case-insensitive search"},
            "max_results": {"type": "integer", "description": "Max matches (default 100)"},
        },
        "required": ["pattern"],
    },
)
async def search_code(
    pattern: str,
    path: str = ".",
    file_glob: str = None,
    ignore_case: bool = False,
    max_results: int = 100,
) -> list[str]:
    root = resolve_path(path)
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error:
        rx = re.compile(re.escape(pattern), flags)

    results: list[str] = []
    for f in root.rglob(file_glob or "*"):
        if not f.is_file() or any(part in IGNORE_DIRS for part in f.parts):
            continue
        if f.suffix.lower() in _TEXT_SKIP_EXT or f.stat().st_size > 1_000_000:
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if rx.search(line):
                    results.append(f"{f.relative_to(root)}:{i}: {line.strip()[:200]}")
                    if len(results) >= max_results:
                        return results
        except Exception:
            continue
    return results
