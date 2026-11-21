"""
Global configuration for the MyCodeAI agent engine.
Values can be overridden via environment variables or a .env file.
"""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Ollama ──────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    default_model: str = "qwen2.5-coder:7b"
    planner_model: str = "qwen2.5-coder:7b"
    reviewer_model: str = "qwen2.5-coder:7b"
    context_window: int = 32_000      # tokens
    max_response_tokens: int = 8_000

    # ── Server ───────────────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "info"

    # ── Paths ────────────────────────────────────────────────────────────────
    workspace_root: Path = Path.cwd()
    specs_dir: Path = Path("specs")
    steering_dir: Path = Path(".kiro/steering")
    hooks_dir: Path = Path(".kiro/hooks")
    memory_db: Path = Path(".kiro/memory.db")

    # ── Permissions ───────────────────────────────────────────────────────────
    # "allow", "deny", "ask"
    default_permission: str = "ask"
    auto_allow_reads: bool = True
    auto_allow_writes: bool = False
    auto_allow_shell: bool = False

    # ── Git checkpoints ───────────────────────────────────────────────────────
    auto_checkpoint: bool = True
    checkpoint_prefix: str = "mycodeai/checkpoint"


settings = Settings()
