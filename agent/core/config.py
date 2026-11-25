from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── Ollama ────────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    # Smart routing picks the right model automatically.
    # These are fallback defaults; model_router.select_model() overrides them.
    default_model: str = "qwen2.5-coder:3b"  # fast coding (was 7b)
    fast_model: str = "qwen3:1.7b"  # fastest chat/planning
    vision_model: str = "moondream:1.8b"  # fastest vision (was gemma3:4b)
    vision_fallback: str = "gemma3:4b"  # vision fallback if moondream missing
    code_model: str = "qwen2.5-coder:3b"  # default code model
    code_model_large: str = "qwen2.5-coder:7b"  # large code model for complex tasks
    long_ctx_model: str = "llama3.1:8b"  # 131K context
    planner_model: str = "qwen3:1.7b"
    reviewer_model: str = "qwen2.5-coder:3b"
    # Auto-route: when True, model_router picks the model per request
    auto_route_model: bool = True
    # Router: hybrid intent/agent routing (heuristic fast-path + LLM fallback)
    llm_router: bool = True            # use a small model when heuristics are unsure
    router_model: str = "qwen3:1.7b"   # fast model used for LLM classification
    context_window: int = 4_096
    max_response_tokens: int = 1_024

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "info"

    # ── Paths ─────────────────────────────────────────────────────────────────
    # workspace_root = where MyCodeAI stores its own specs/git/steering
    # File tools accept absolute paths anywhere under /home or /tmp
    workspace_root: Path = Path("/opt/mycodeai")
    specs_dir: Path = Path("specs")
    steering_dir: Path = Path(".kiro/steering")
    hooks_dir: Path = Path(".kiro/hooks")
    memory_db: Path = Path("/opt/mycodeai/.kiro/memory.db")

    # ── Permissions ───────────────────────────────────────────────────────────
    default_permission: str = "allow"  # allow all — user controls via UI
    auto_allow_reads: bool = True
    auto_allow_writes: bool = True  # agent can write without asking
    auto_allow_shell: bool = True  # agent can run commands
    # "auto" = execute immediately (Cursor autopilot style)
    # "ask"  = show Accept/Decline for each file/command (Kiro supervised style)
    permission_mode: str = "auto"

    # ── Git ───────────────────────────────────────────────────────────────────
    auto_checkpoint: bool = True
    checkpoint_prefix: str = "mycodeai/checkpoint"


settings = Settings()
