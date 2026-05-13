#!/usr/bin/env bash
# Installer for Claude Photo Upload tray app (Ubuntu/Debian with GNOME)
# Run this ON YOUR DESKTOP/LAPTOP — not on the Claude VM.
set -e

INSTALL_DIR="$HOME/.local/share/claude-photo"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
ICON_FILE="$ICON_DIR/claude-photo-upload.png"
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
    rm -f "$ICON_FILE"
    rm -f "$DESKTOP_FILE"
    rm -f "$AUTOSTART_FILE"
    update-desktop-database "$APPDIR" 2>/dev/null || true
    echo "Done."
    exit 0
fi

echo "=== Claude Photo Upload — Tray App Installer ==="
echo ""

# --- System dependencies ---
echo "[1/5] Installing system dependencies..."
if ! python3 -c "import gi; gi.require_version('AppIndicator3','0.1')" 2>/dev/null; then
    sudo apt-get install -y -q gir1.2-appindicator3-0.1 python3-gi python3-gi-cairo gir1.2-gtk-3.0
else
    echo "      Already installed."
fi
echo "      OK"

# --- Install files ---
echo "[2/5] Installing app to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/tray_app.py" "$INSTALL_DIR/tray_app.py"
chmod +x "$INSTALL_DIR/tray_app.py"
mkdir -p "$HOME/.local/bin"
ln -sf "$INSTALL_DIR/tray_app.py" "$BIN_LINK"
echo "      OK"

# --- Generate icon ---
echo "[3/5] Generating app icon..."
mkdir -p "$ICON_DIR"
python3 - "$ICON_FILE" <<'PYEOF'
import sys
try:
    from PIL import Image, ImageDraw
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Background circle
    draw.ellipse([4, 4, size-4, size-4], fill="#141821", outline="#4dc9f6", width=8)
    # Camera body
    draw.rounded_rectangle([40, 90, 216, 182], radius=18, fill="#4dc9f6")
    # Viewfinder bump
    draw.rectangle([96, 62, 160, 94], fill="#4dc9f6")
    # Lens outer ring (dark)
    cx, cy = 128, 136
    draw.ellipse([cx-46, cy-46, cx+46, cy+46], fill="#141821")
    # Lens inner
    draw.ellipse([cx-30, cy-30, cx+30, cy+30], fill="#7dd8f8")
    img.save(sys.argv[1])
    print("      Generated custom icon.")
except ImportError:
    print("      Pillow not found, using system icon fallback.")
    sys.exit(1)
PYEOF
if [ $? -ne 0 ]; then
    ICON_NAME="camera-photo"
else
    ICON_NAME="claude-photo-upload"
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi
echo "      OK"

# --- Desktop entry ---
echo "[4/5] Registering in app menu..."
mkdir -p "$APPDIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Claude Photo Upload
GenericName=Screenshot Uploader
Comment=Upload screenshots to Claude Code agent
Exec=python3 $INSTALL_DIR/tray_app.py
Icon=$ICON_NAME
Terminal=false
Categories=Utility;Graphics;
Keywords=screenshot;upload;claude;photo;
StartupNotify=false
EOF

mkdir -p "$AUTOSTART_DIR"
cp "$DESKTOP_FILE" "$AUTOSTART_FILE"

# Refresh app menu database
update-desktop-database "$APPDIR" 2>/dev/null || true
echo "      OK — search 'Claude' in your app launcher"

# --- Launch ---
echo "[5/5] Setup complete!"
echo ""
echo "  Auto-starts on next login."
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
