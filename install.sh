#!/usr/bin/env bash
# Installer for Claude Photo Upload tray app (Ubuntu/Debian)
set -e

INSTALL_DIR="$HOME/.local/share/claude-photo"
BIN_LINK="$HOME/.local/bin/claude-photo-tray"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/claude-photo-tray.desktop"
APPDIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APPDIR/claude-photo-tray.desktop"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Claude Photo Upload — Tray App Installer ==="

# --- Dependencies ---
echo "[1/4] Installing Python dependencies..."
pip install --quiet --user pystray Pillow 2>&1 | tail -1
echo "      OK"

# --- Install files ---
echo "[2/4] Installing app files to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/tray_app.py" "$INSTALL_DIR/tray_app.py"
chmod +x "$INSTALL_DIR/tray_app.py"

# Symlink to ~/bin so it's on PATH
mkdir -p "$HOME/.local/bin"
ln -sf "$INSTALL_DIR/tray_app.py" "$BIN_LINK"
echo "      OK"

# --- App icon (Desktop entry) ---
echo "[3/4] Creating application shortcuts..."
mkdir -p "$APPDIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Claude Photo Upload
Comment=Upload screenshots to Claude Code agent
Exec=python3 $INSTALL_DIR/tray_app.py
Icon=camera
Terminal=false
Categories=Utility;
Keywords=screenshot;upload;claude;
EOF

# --- Autostart ---
mkdir -p "$AUTOSTART_DIR"
cp "$DESKTOP_FILE" "$AUTOSTART_FILE"
echo "      OK"

# --- Launch now? ---
echo "[4/4] Setup complete!"
echo ""
echo "  The tray icon will start automatically on next login."
echo "  To start it now:"
echo ""
echo "    python3 $INSTALL_DIR/tray_app.py &"
echo ""
read -r -p "Start the tray icon now? [Y/n] " ans
ans="${ans:-Y}"
if [[ "$ans" =~ ^[Yy]$ ]]; then
    nohup python3 "$INSTALL_DIR/tray_app.py" >/dev/null 2>&1 &
    echo "  Started! Look for the camera icon in your system tray."
fi

echo ""
echo "=== Done ==="
echo "  To uninstall: bash $SCRIPT_DIR/install.sh --uninstall"
echo ""

# --- Uninstall path ---
if [[ "${1:-}" == "--uninstall" ]]; then
    echo "Uninstalling..."
    pkill -f "$INSTALL_DIR/tray_app.py" 2>/dev/null || true
    rm -rf "$INSTALL_DIR"
    rm -f "$BIN_LINK"
    rm -f "$DESKTOP_FILE"
    rm -f "$AUTOSTART_FILE"
    echo "Uninstalled."
    exit 0
fi
