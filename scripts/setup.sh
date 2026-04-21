#!/bin/bash
# Clones chives from GitHub and installs it as a launchd service, keeping the
# deploy directory separate from the development working tree.
set -euo pipefail

REPO_URL="git@github.com:awfulwoman/chives.git"
PLIST_LABEL="com.chives.agent"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
INSTALL_DIR="${1:-$HOME/services/chives}"
DEV_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# ── Prerequisites ──────────────────────────────────────────────────────────────

if ! command -v git &>/dev/null; then
    echo "Error: git not found." && exit 1
fi

UV_PATH="$(which uv 2>/dev/null || true)"
if [ -z "$UV_PATH" ]; then
    echo "Error: uv not found on PATH. Install uv first." && exit 1
fi

# ── Stop any running service ───────────────────────────────────────────────────

if [ -f "$PLIST_PATH" ]; then
    echo "Stopping existing service..."
    launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
fi

# ── Clone ──────────────────────────────────────────────────────────────────────

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing clone at $INSTALL_DIR..."
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" reset --hard origin/main
else
    echo "Cloning $REPO_URL into $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# ── Config ────────────────────────────────────────────────────────────────────
# Copy .env from the dev tree if present; otherwise fall back to .env.example.

if [ -f "$DEV_DIR/.env" ] && [ "$INSTALL_DIR" != "$DEV_DIR" ]; then
    echo "Copying .env from dev directory..."
    cp "$DEV_DIR/.env" "$INSTALL_DIR/.env"
elif [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ""
    echo "  !! No .env found. A template has been placed at $INSTALL_DIR/.env"
    echo "  !! Edit it before starting the service."
    echo ""
fi

# Copy profile/ from the dev tree if it has been customised and the deploy
# directory doesn't yet have one.
if [ -d "$DEV_DIR/profile" ] && [ ! -d "$INSTALL_DIR/profile" ] && [ "$INSTALL_DIR" != "$DEV_DIR" ]; then
    echo "Copying profile/ from dev directory..."
    cp -r "$DEV_DIR/profile" "$INSTALL_DIR/profile"
fi

# ── Dependencies ──────────────────────────────────────────────────────────────

echo "Installing dependencies..."
(cd "$INSTALL_DIR" && "$UV_PATH" sync)

# ── Runtime directories ───────────────────────────────────────────────────────

mkdir -p "$INSTALL_DIR/logs" "$INSTALL_DIR/state"

# ── launchd plist ─────────────────────────────────────────────────────────────

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${UV_PATH}</string>
        <string>run</string>
        <string>python</string>
        <string>-m</string>
        <string>chives.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${INSTALL_DIR}/logs/chives.log</string>
    <key>StandardErrorPath</key>
    <string>${INSTALL_DIR}/logs/chives.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
PLIST

launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
echo "Chives service installed and started from $INSTALL_DIR."
