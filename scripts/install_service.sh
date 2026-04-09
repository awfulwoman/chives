#!/bin/bash
set -euo pipefail

PLIST_LABEL="com.chives.agent"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

UV_PATH="$(which uv 2>/dev/null || true)"
if [ -z "$UV_PATH" ]; then
    echo "Error: uv not found on PATH. Install uv first."
    exit 1
fi

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
    <string>${REPO_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${REPO_DIR}/logs/chives.log</string>
    <key>StandardErrorPath</key>
    <string>${REPO_DIR}/logs/chives.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
PLIST

mkdir -p "${REPO_DIR}/logs"
launchctl bootstrap gui/$(id -u) "$PLIST_PATH" || true
echo "Chives service installed and started."
