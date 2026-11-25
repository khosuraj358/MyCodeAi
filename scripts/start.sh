#!/usr/bin/env bash
# MyCodeAI IDE — launcher (installed version)
# Starts the agent server in the background, then opens VSCodium in the foreground.
# The desktop shortcut uses Terminal=false so this script is the only process
# keeping the session alive — VSCodium itself stays open.

INSTALL_DIR="/opt/mycodeai"
LOG_DIR="$HOME/.local/share/mycodeai"
mkdir -p "$LOG_DIR"

# ── 1. Start Ollama if installed but not running ───────────────────────────
if command -v ollama &>/dev/null; then
    if ! curl -s --max-time 2 http://localhost:11434/api/tags &>/dev/null; then
        ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
        sleep 1
    fi
fi

# ── 2. Start agent server if not already running ──────────────────────────
if ! curl -s --max-time 1 http://127.0.0.1:8765/health 2>/dev/null | grep -q '"ok"'; then
    PYTHONPATH="$INSTALL_DIR" python3 -m agent.core.server \
        > "$LOG_DIR/agent.log" 2>&1 &
    # Give it a moment to bind the port before VSCodium opens
    sleep 2
fi

# ── 3. Launch VSCodium in the foreground (exec replaces this process) ─────
# exec means VSCodium becomes the launcher process — the desktop entry
# stays alive exactly as long as VSCodium is open, so the window never
# vanishes unexpectedly.
if command -v codium &>/dev/null; then
    exec codium --no-sandbox "$INSTALL_DIR"
elif command -v code &>/dev/null; then
    exec code "$INSTALL_DIR"
else
    if command -v notify-send &>/dev/null; then
        notify-send "MyCodeAI IDE" \
            "VSCodium not found. Install it from https://vscodium.com\nAgent server is running at http://127.0.0.1:8765"
    fi
    echo "ERROR: codium / code not found. Install VSCodium from https://vscodium.com" >&2
    exit 1
fi
