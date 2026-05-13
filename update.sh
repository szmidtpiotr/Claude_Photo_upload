#!/usr/bin/env bash
# Pull latest changes and restart the tray app.
# Run from any directory: bash ~/Claude_Photo_upload/update.sh
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/claude-photo"

echo "Pulling latest..."
git -C "$REPO_DIR" pull

echo "Updating installed files..."
cp "$REPO_DIR/tray_app.py" "$INSTALL_DIR/tray_app.py"

echo "Restarting tray app..."
pkill -f "$INSTALL_DIR/tray_app.py" 2>/dev/null || true
sleep 0.5
nohup python3 "$INSTALL_DIR/tray_app.py" >> /tmp/claude-photo-tray.log 2>&1 &

sleep 1
if pgrep -f "$INSTALL_DIR/tray_app.py" > /dev/null; then
    echo "Done — tray app running."
else
    echo "Failed to start. Log:"
    tail -20 /tmp/claude-photo-tray.log
fi
