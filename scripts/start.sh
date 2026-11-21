#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# MyCodeAI IDE — start script
# Opens VSCodium with the workspace AND starts the agent server
# ─────────────────────────────────────────────────────────────
set -e

WORKSPACE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE"

echo "════════════════════════════════════════"
echo "  MyCodeAI IDE"
echo "  Workspace: $WORKSPACE"
echo "════════════════════���═══════════════════"

# 1. Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install Python 3.11+"
  exit 1
fi

# 2. Check/install pip deps
echo "→ Checking Python dependencies..."
if ! python3 -c "import fastapi, uvicorn, aiosqlite" 2>/dev/null; then
  echo "→ Installing Python dependencies..."
  pip3 install -r agent/requirements.txt --quiet
fi

# 3. Check Ollama
if ! command -v ollama &>/dev/null; then
  echo "⚠  Ollama not found. The agent will not work without it."
  echo "   Install: curl -fsSL https://ollama.com/install.sh | sh"
  echo "   Then:    ollama pull qwen2.5-coder:7b"
else
  # Start ollama serve in background if not running
  if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "→ Starting Ollama..."
    ollama serve &>/tmp/ollama.log &
    sleep 2
  fi
  echo "✓ Ollama running"
fi

# 4. Init git repo if needed
if [ ! -d ".git" ]; then
  echo "→ Initialising Git repository..."
  git init
  git config user.email "mycodeai@local"
  git config user.name "MyCodeAI"
  git add -A
  git commit -m "mycodeai/checkpoint: initial project scaffold" --allow-empty
fi

# 5. Start agent server in background
echo "→ Starting MyCodeAI agent server on port 8765..."
PYTHONPATH="$WORKSPACE" python3 -m agent.core.server &
AGENT_PID=$!
echo "  Agent PID: $AGENT_PID"
sleep 2

# Check server started
if curl -s http://127.0.0.1:8765/health | grep -q '"ok"'; then
  echo "✓ Agent server ready"
else
  echo "⚠  Agent server may still be starting (check terminal output)"
fi

# 6. Open VSCodium
echo "→ Opening VSCodium..."
codium --no-sandbox "$WORKSPACE" &

echo ""
echo "✓ MyCodeAI IDE started"
echo ""
echo "  Agent API: http://127.0.0.1:8765"
echo "  API docs:  http://127.0.0.1:8765/docs"
echo "  Health:    http://127.0.0.1:8765/health"
echo ""
echo "  Stop agent: kill $AGENT_PID"
