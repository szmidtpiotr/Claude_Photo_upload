#!/usr/bin/env bash
# Installer for Claude Photo Upload tray app (Ubuntu/Debian with GNOME)
# Run this ON YOUR DESKTOP/LAPTOP — not on the Claude VM.
set -e

INSTALL_DIR="$HOME/.local/share/claude-photo"
BIN_LINK="$HOME/.local/bin/claude-photo-tray"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/claude-photo-tray.desktop"
APPDIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APPDIR/claude-photo-tray.desktop"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Uninstall path ---
if [[ "${1:-}" == "--uninstall" ]]; then
    echo "Uninstalling Claude Photo Upload tray app..."
    pkill -f "$INSTALL_DIR/tray_app.py" 2>/dev/null || true
    rm -rf "$INSTALL_DIR"
    rm -f "$BIN_LINK"
    rm -f "$DESKTOP_FILE"
    rm -f "$AUTOSTART_FILE"
    echo "Done."
    exit 0
fi

echo "=== Claude Photo Upload — Tray App Installer ==="
echo ""

# --- System dependencies ---
echo "[1/4] Installing system dependencies..."
if ! python3 -c "import gi; gi.require_version('AppIndicator3','0.1')" 2>/dev/null; then
    sudo apt-get install -y -q gir1.2-appindicator3-0.1 python3-gi python3-gi-cairo gir1.2-gtk-3.0
else
    echo "      Already installed."
fi
echo "      OK"

# --- Install files ---
echo "[2/4] Installing app to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/tray_app.py" "$INSTALL_DIR/tray_app.py"
chmod +x "$INSTALL_DIR/tray_app.py"

mkdir -p "$HOME/.local/bin"
ln -sf "$INSTALL_DIR/tray_app.py" "$BIN_LINK"
echo "      OK"

# --- Desktop entry ---
echo "[3/4] Creating app shortcuts..."
mkdir -p "$APPDIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Claude Photo Upload
Comment=Upload screenshots to Claude Code agent
Exec=python3 $INSTALL_DIR/tray_app.py
Icon=camera-photo
Terminal=false
Categories=Utility;
Keywords=screenshot;upload;claude;
StartupNotify=false
EOF

mkdir -p "$AUTOSTART_DIR"
cp "$DESKTOP_FILE" "$AUTOSTART_FILE"
echo "      OK"

# --- Launch ---
echo "[4/4] Setup complete!"
echo ""
echo "  The tray icon will auto-start on next login."
echo ""
read -r -p "Start the tray icon now? [Y/n] " ans
ans="${ans:-Y}"
if [[ "$ans" =~ ^[Yy]$ ]]; then
    pkill -f "$INSTALL_DIR/tray_app.py" 2>/dev/null || true
    nohup python3 "$INSTALL_DIR/tray_app.py" >/tmp/claude-photo-tray.log 2>&1 &
    sleep 1
    if pgrep -f "$INSTALL_DIR/tray_app.py" >/dev/null; then
        echo "  Started! Look for the camera icon in your system tray."
    else
        echo "  Failed to start. Check /tmp/claude-photo-tray.log for errors."
        cat /tmp/claude-photo-tray.log
    fi
fi

echo ""
echo "=== Done ==="
echo "  Uninstall: bash $SCRIPT_DIR/install.sh --uninstall"
