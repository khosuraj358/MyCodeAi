#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# MyCodeAI IDE — first-time setup
# Run once after cloning / extracting the project
# ─────────────────────────────────────────────────────────────
set -e

WORKSPACE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE"

echo "════════════════════════════════════════"
echo "  MyCodeAI IDE — Setup"
echo "════════════════════════════════════════"

# 1. Python deps
echo ""
echo "[1/5] Installing Python dependencies..."
pip3 install -r agent/requirements.txt

# 2. Ollama
echo ""
echo "[2/5] Checking Ollama..."
if command -v ollama &>/dev/null; then
  echo "✓ Ollama already installed: $(ollama --version 2>/dev/null || echo 'unknown version')"
else
  echo "→ Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
fi

# 3. Pull model
echo ""
echo "[3/5] Pulling default model (qwen2.5-coder:7b)..."
echo "  This may take several minutes on first run (~4GB download)"
ollama pull qwen2.5-coder:7b

# 4. Node / npm for extension
echo ""
echo "[4/5] Setting up VS Code extension..."
if command -v npm &>/dev/null; then
  cd extension && npm install && npm run compile && cd ..
  echo "✓ Extension compiled"
else
  echo "⚠  npm not found — skipping extension build"
  echo "   Install Node.js from https://nodejs.org to build the extension"
fi

# 5. Git init
echo ""
echo "[5/5] Initialising Git repository..."
if [ ! -d ".git" ]; then
  git init
  git config user.email "mycodeai@local"
  git config user.name "MyCodeAI"
  git add -A
  git commit -m "mycodeai/checkpoint: initial project scaffold"
  echo "✓ Git repository initialised"
else
  echo "✓ Git repository already exists"
fi

# 6. Create .kiro dirs
mkdir -p .kiro/hooks .kiro/steering

echo ""
echo "════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Start MyCodeAI IDE:"
echo "    ./scripts/start.sh"
echo ""
echo "  Or open VSCodium directly:"
echo "    codium ."
echo "════════════════════════════════════════"
