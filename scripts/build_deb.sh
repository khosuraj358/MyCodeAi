#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# MyCodeAI IDE — build a .deb installer
# Usage:   ./scripts/build_deb.sh [VERSION]
# Example: ./scripts/build_deb.sh 0.3.7
# Output:  ./mycodeai_<VERSION>_amd64.deb
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-0.3.8}"
PKG="mycodeai"
ARCH="amd64"
OUT="$REPO/${PKG}_${VERSION}_${ARCH}.deb"
STAGE="$(mktemp -d /tmp/${PKG}-build.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT

echo "════════════════════════════════════════"
echo "  Building $PKG $VERSION ($ARCH)"
echo "════════════════════════════════════════"

# ── 1. Payload → /opt/mycodeai ───────────────────────────────
mkdir -p "$STAGE/opt/mycodeai"
rsync -a \
  --exclude='.git/' --exclude='__pycache__/' --exclude='*.pyc' \
  --exclude='node_modules/' --exclude='.kiro/memory.db' \
  --exclude='*.deb' \
  "$REPO"/ "$STAGE/opt/mycodeai"/

# ── 2. System files ──────────────────────────────────────────
mkdir -p "$STAGE/usr/bin" "$STAGE/usr/lib/systemd/user" \
         "$STAGE/usr/share/applications" "$STAGE/usr/share/pixmaps"
for s in 16 32 48 128 256 512; do
  mkdir -p "$STAGE/usr/share/icons/hicolor/${s}x${s}/apps"
  cp -f "$REPO/resources/icon-${s}.png" \
        "$STAGE/usr/share/icons/hicolor/${s}x${s}/apps/mycodeai.png"
done
cp -f "$REPO/resources/mycodeai.png" "$STAGE/usr/share/pixmaps/mycodeai.png"

cat > "$STAGE/usr/bin/mycodeai" <<'EOF'
#!/bin/bash
exec bash /opt/mycodeai/scripts/start.sh "$@"
EOF
chmod 755 "$STAGE/usr/bin/mycodeai"

cat > "$STAGE/usr/lib/systemd/user/mycodeai-agent.service" <<'EOF'
[Unit]
Description=MyCodeAI Agent Server
After=network.target
[Service]
Type=simple
WorkingDirectory=/opt/mycodeai
Environment=PYTHONPATH=/opt/mycodeai
ExecStart=/usr/bin/python3 -m agent.core.server
Restart=on-failure
RestartSec=5
[Install]
WantedBy=default.target
EOF

cat > "$STAGE/usr/share/applications/mycodeai.desktop" <<'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=MyCodeAI IDE
GenericName=AI Coding Assistant
Comment=Autonomous AI coding agent — no cloud, no API keys
Exec=/usr/bin/mycodeai
Icon=/opt/mycodeai/resources/mycodeai.png
Terminal=false
Categories=Development;IDE;
Keywords=AI;coding;agent;llm;ollama;
StartupNotify=true
StartupWMClass=VSCodium
EOF

# ── 3. DEBIAN control + maintainer scripts ───────────────────
mkdir -p "$STAGE/DEBIAN"
SIZE=$(du -sk "$STAGE" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: devel
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.10), python3-pip, git, curl, codium | code
Recommends: ollama
Maintainer: MyCodeAI <mycodeai@local>
Installed-Size: $SIZE
Description: MyCodeAI IDE v$VERSION - Autonomous AI coding agent
 Builds complete projects from a single prompt with automatic
 agent/model routing (Cursor/Kiro/Trae style): picks the right
 agent and model per message, and can create, edit and run files,
 set up environments and read whole projects.
 .
 No API keys. No cloud. No monthly quota.
EOF

cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/bash
REAL_USER="${SUDO_USER:-$USER}"
UID_N=$(id -u "$REAL_USER" 2>/dev/null || echo "")
[ -n "$UID_N" ] && sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$UID_N" \
  systemctl --user stop mycodeai-agent 2>/dev/null || true
pkill -f "agent.core.server" 2>/dev/null || true
exit 0
EOF

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/bash
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
rm -f "$REAL_HOME/Desktop/MyCodeAI-IDE.desktop" /usr/bin/mycodeai
update-desktop-database /usr/share/applications/ 2>/dev/null || true
exit 0
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e
INSTALL_DIR="/opt/mycodeai"
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

echo "→ Installing Python dependencies..."
pip3 install --quiet \
  fastapi uvicorn httpx pydantic pydantic-settings \
  aiofiles aiosqlite GitPython rich typer \
  watchdog pathspec jinja2 toml python-dotenv websockets \
  pymupdf cairosvg Pillow python-docx openpyxl 2>&1 | tail -5 || true

chmod +x "$INSTALL_DIR/scripts/start.sh" 2>/dev/null || true
chown -R "$REAL_USER:$REAL_USER" "$INSTALL_DIR" 2>/dev/null || true

cat > /usr/bin/mycodeai << 'LAUNCHER'
#!/bin/bash
exec bash /opt/mycodeai/scripts/start.sh "$@"
LAUNCHER
chmod +x /usr/bin/mycodeai

DESK="$REAL_HOME/Desktop/MyCodeAI-IDE.desktop"
cat > "$DESK" << 'DESKEOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=MyCodeAI IDE
Comment=Autonomous AI coding agent — no cloud, no API keys
Exec=/usr/bin/mycodeai
Icon=/opt/mycodeai/resources/mycodeai.png
Terminal=false
Categories=Development;IDE;
StartupNotify=true
StartupWMClass=VSCodium
DESKEOF
chmod +x "$DESK"; chown "$REAL_USER:$REAL_USER" "$DESK" 2>/dev/null || true

VCFG="$REAL_HOME/.config/VSCodium"
mkdir -p "$VCFG/User"
[ ! -f "$VCFG/argv.json" ] && printf '{"password-store":"basic","no-sandbox":true}\n' > "$VCFG/argv.json"
chown -R "$REAL_USER:$REAL_USER" "$VCFG" 2>/dev/null || true

VSIX=$(ls "$INSTALL_DIR"/extension/mycodeai-*.vsix 2>/dev/null | sort -V | tail -1)
if command -v codium &>/dev/null && [ -n "$VSIX" ]; then
  sudo -u "$REAL_USER" codium --no-sandbox --uninstall-extension mycodeai.mycodeai 2>/dev/null || true
  sudo -u "$REAL_USER" codium --no-sandbox --install-extension "$VSIX" --force 2>/dev/null \
    && echo "✓ MyCodeAI extension installed ($VSIX)"
fi

gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
update-desktop-database /usr/share/applications/ 2>/dev/null || true

if command -v systemctl &>/dev/null && [ "$REAL_USER" != "root" ]; then
  UID_N=$(id -u "$REAL_USER" 2>/dev/null || echo "")
  [ -n "$UID_N" ] && sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$UID_N" \
    systemctl --user daemon-reload 2>/dev/null || true
  [ -n "$UID_N" ] && sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$UID_N" \
    systemctl --user enable --now mycodeai-agent 2>/dev/null || true
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
  cd "$INSTALL_DIR"
  sudo -u "$REAL_USER" git init -q
  sudo -u "$REAL_USER" git config user.email "mycodeai@local"
  sudo -u "$REAL_USER" git config user.name "MyCodeAI"
  sudo -u "$REAL_USER" git add -A
  sudo -u "$REAL_USER" git commit -qm "mycodeai/checkpoint: installed" 2>/dev/null || true
fi

echo "✓ MyCodeAI IDE installed. Launch with: mycodeai"
exit 0
EOF

chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm" "$STAGE/DEBIAN/postrm"
chmod 644 "$STAGE/DEBIAN/control"

# ── 4. Build the package ─────────────────────────────────────
rm -f "$OUT"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
echo ""
echo "✓ Done: $OUT"
echo "  Install:  sudo apt install \"$OUT\""
