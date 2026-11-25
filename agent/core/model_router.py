"""
model_router.py — Automatic model selection for MyCodeAI.

Chooses the smallest, fastest model that can handle the task,
staying within the available RAM budget on the current machine.

Decision tree
─────────────
1. Image attached?
      → moondream:1.8b  (1.7 GB, fastest vision)
      → fallback: gemma3:4b  (3.4 GB, if moondream not available)

2. Code task (write/create/fix/build a file or project)?
      → qwen2.5-coder:3b  (1.9 GB, fast, native tools)
      → fallback: qwen2.5-coder:7b  (4.7 GB, strongest code)

3. Long context needed (> 4000 tokens, large file/document)?
      → llama3.1:8b  (131K ctx — the only model with real long context)

4. Quick chat / question / explanation?
      → qwen3:1.7b  (1.4 GB, thinking model, fastest)

5. Planning / spec / structured text?
      → qwen3:1.7b  (fast + chain-of-thought)

6. Default fallback
      → qwen2.5-coder:3b  (best balance of speed + capability)

RAM budget logic
────────────────
Total RAM < 6 GB available  → prefer <2 GB models only
Total RAM 6-10 GB available → prefer <4 GB models
Total RAM > 10 GB available → allow 7b+ models freely
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Caching ───────────────────────────────────────────────────────────────────
# Installed models and available RAM don't change between requests. Cache them
# to avoid an HTTP round-trip to Ollama on every user message.
_INSTALLED_CACHE: Optional[set[str]] = None
_INSTALLED_CACHE_TS: float = 0.0
_RAM_CACHE: float = 0.0
_RAM_CACHE_TS: float = 0.0
_CACHE_TTL: float = 30.0  # seconds


# ── Model registry ─────────────────────────────────────────────────────────────
# name → { size_gb, capabilities, context, speed_rank (lower=faster) }
MODELS: dict[str, dict] = {
    "moondream:1.8b": {
        "size_gb": 1.7,
        "caps": {"vision"},
        "ctx": 2048,
        "speed": 1,
        "code": False,
    },
    "qwen3:1.7b": {
        "size_gb": 1.4,
        "caps": {"tools", "thinking"},
        "ctx": 4096,
        "speed": 1,
        "code": False,
    },
    "qwen2.5-coder:3b": {
        "size_gb": 1.9,
        "caps": {"tools", "insert", "code"},
        "ctx": 4096,
        "speed": 2,
        "code": True,
    },
    "gemma3:4b": {
        "size_gb": 3.4,
        "caps": {"vision"},
        "ctx": 4096,
        "speed": 3,
        "code": False,
    },
    "qwen2.5-coder:7b": {
        "size_gb": 4.7,
        "caps": {"tools", "insert", "code"},
        "ctx": 4096,
        "speed": 4,
        "code": True,
    },
    "llama3.1:8b": {
        "size_gb": 4.9,
        "caps": {"tools"},
        "ctx": 131072,
        "speed": 5,
        "code": False,
    },
}

# Keywords that signal a code/action task
_CODE_SIGNALS = {
    "create",
    "write",
    "make",
    "build",
    "generate",
    "implement",
    "fix",
    "debug",
    "refactor",
    "edit",
    "run",
    "execute",
    "compile",
    "install",
    "setup",
    ".py",
    ".js",
    ".ts",
    ".cpp",
    ".dart",
    ".go",
    ".rs",
    ".java",
    "function",
    "class",
    "method",
    "code",
    "script",
    "file",
    "folder",
    "directory",
    "project",
}


def _available_ram_gb() -> float:
    """Get available (free + cached) RAM in GB. Cached for 30s."""
    global _RAM_CACHE, _RAM_CACHE_TS
    now = time.monotonic()
    if now - _RAM_CACHE_TS < _CACHE_TTL:
        return _RAM_CACHE
    try:
        with open("/proc/meminfo") as f:
            info = dict(
                line.split(":") for line in f.read().splitlines() if ":" in line
            )
        available_kb = int(info.get("MemAvailable", "0 kB").strip().split()[0])
        _RAM_CACHE = available_kb / 1024 / 1024
    except Exception:
        _RAM_CACHE = 4.0
    _RAM_CACHE_TS = now
    return _RAM_CACHE


def _installed_models() -> set[str]:
    """Return set of model names currently installed in Ollama. Cached for 30s."""
    global _INSTALLED_CACHE, _INSTALLED_CACHE_TS
    now = time.monotonic()
    if _INSTALLED_CACHE is not None and now - _INSTALLED_CACHE_TS < _CACHE_TTL:
        return _INSTALLED_CACHE
    try:
        import json
        import urllib.request

        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        _INSTALLED_CACHE = {m["name"] for m in data.get("models", [])}
    except Exception:
        _INSTALLED_CACHE = set(MODELS.keys())
    _INSTALLED_CACHE_TS = now
    return _INSTALLED_CACHE


def select_model(
    message: str,
    has_image: bool = False,
    has_file: bool = False,
    estimated_tokens: int = 0,
    intent: str = "chat",  # "chat" | "action" | "spec"
    force: Optional[str] = None,  # user explicitly chose a model
) -> tuple[str, str]:
    """
    Returns (model_name, reason) — the best model for this request.
    """
    if force:
        return force, "user selected"

    available_ram = _available_ram_gb()
    installed = _installed_models()
    lower = message.lower()

    def _pick(preferred: list[str], reason: str) -> tuple[str, str]:
        """Pick the first preferred model that is installed and fits in RAM.
        On a loaded system (< 2 GB free) we still allow running since Ollama
        manages memory via mmap and model swapping internally.
        """
        for m in preferred:
            if m not in installed:
                continue
            info = MODELS.get(m, {})
            # On tight RAM, still allow if Ollama is already running (it manages memory)
            # Only hard-block if we'd need > total system RAM
            if available_ram < 1.0:
                # Very tight — only allow smallest models
                if info.get("size_gb", 99) <= 2.5:
                    return m, reason
            else:
                return m, reason
        # Fallback: smallest installed model
        fallback = min(
            (m for m in installed if m in MODELS),
            key=lambda m: MODELS[m]["size_gb"],
            default="qwen3:1.7b",
        )
        return fallback, f"{reason} (memory-managed fallback)"

    # ── 1. Image: needs vision ────────────────────────────────────────────────
    if has_image:
        return _pick(
            ["moondream:1.8b", "gemma3:4b"], "image attached — using vision model"
        )

    # ── 2. Very long context needed ───────────────────────────────────────────
    if estimated_tokens > 3500:
        return _pick(
            ["llama3.1:8b", "qwen2.5-coder:7b"],
            f"long context ({estimated_tokens} tokens) — using large context model",
        )

    # ── 3. Code / action task ─────────────────────────────────────────────────
    if intent == "action" or any(sig in lower for sig in _CODE_SIGNALS):
        return _pick(
            ["qwen2.5-coder:3b", "qwen2.5-coder:7b"], "code task — using coding model"
        )

    # ── 4. Spec / planning ────────────────────────────────────────────────────
    if intent == "spec":
        return _pick(
            ["qwen3:1.7b", "qwen2.5-coder:3b"],
            "planning task — using fast thinking model",
        )

    # ── 5. Quick chat / Q&A ───────────────────────────────────────────────────
    return _pick(
        ["qwen3:1.7b", "qwen2.5-coder:3b"], "conversational — using fast model"
    )


def ram_status() -> dict:
    """Return current RAM usage and model recommendations."""
    available = _available_ram_gb()
    installed = _installed_models()

    can_run = []
    too_big = []
    for name, info in sorted(MODELS.items(), key=lambda x: x[1]["size_gb"]):
        if name not in installed:
            continue
        if info["size_gb"] + 1.5 <= available:
            can_run.append({"model": name, "size_gb": info["size_gb"]})
        else:
            too_big.append({"model": name, "size_gb": info["size_gb"]})

    return {
        "available_ram_gb": round(available, 1),
        "can_run": can_run,
        "too_big_for_ram": too_big,
    }
