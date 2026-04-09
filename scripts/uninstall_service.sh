#!/bin/bash
set -euo pipefail

PLIST_LABEL="com.chives.agent"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

launchctl bootout gui/$(id -u) "$PLIST_PATH" 2>/dev/null || true
rm -f "$PLIST_PATH"
echo "Chives service removed."
