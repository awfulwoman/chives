#!/bin/bash
set -euo pipefail

PLIST_LABEL="com.chives.agent"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

if [ ! -f "$PLIST_PATH" ]; then
    echo "Error: service not installed (no plist at $PLIST_PATH). Run install_service.sh first."
    exit 1
fi

launchctl kickstart -k "gui/$(id -u)/${PLIST_LABEL}"
echo "Chives service restarted."
