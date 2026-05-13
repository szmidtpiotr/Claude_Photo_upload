#!/usr/bin/env bash
# Claude Photo Upload — installer
# Run ON YOUR DESKTOP/LAPTOP (not on the Claude VM):
#   git clone https://github.com/szmidtpiotr/Claude_Photo_upload
#   cd Claude_Photo_upload && bash install.sh
set -e

INSTALL_DIR="$HOME/.local/share/claude-photo"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
BIN_DIR="$HOME/.local/bin"
APPDIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Uninstall ──────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--uninstall" ]]; then
    echo "Uninstalling Claude Photo Upload..."
    pkill -f "$INSTALL_DIR/tray_app.py" 2>/dev/null || true
    rm -rf  "$INSTALL_DIR"
    rm -f   "$BIN_DIR/claude-photo-tray"
    rm -f   "$ICON_DIR/claude-photo-upload.png"
    rm -f   "$APPDIR/claude-photo-tray.desktop"
    rm -f   "$AUTOSTART_DIR/claude-photo-tray.desktop"
    update-desktop-database "$APPDIR" 2>/dev/null || true
    # Remove keyboard shortcut
    BINDING_KEY="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/claude-photo-upload/"
    GSBASE="org.gnome.settings-daemon.plugins.media-keys"
    EXISTING=$(gsettings get "$GSBASE" custom-keybindings 2>/dev/null || echo "[]")
    NEW=$(echo "$EXISTING" | sed "s|, '$BINDING_KEY'||;s|'$BINDING_KEY', ||;s|'$BINDING_KEY'||")
    gsettings set "$GSBASE" custom-keybindings "$NEW" 2>/dev/null || true
    echo "Done."
    exit 0
fi

echo "=== Claude Photo Upload — Installer ==="
echo ""

# ── 1. System packages ─────────────────────────────────────────────────────────
echo "[1/5] Installing system packages..."
sudo apt-get install -y -q \
    gir1.2-appindicator3-0.1 \
    gir1.2-gtk-3.0 \
    python3-gi \
    python3-gi-cairo \
    python3-pil
echo "      OK"

# ── 2. App files ───────────────────────────────────────────────────────────────
echo "[2/5] Installing app files..."
mkdir -p "$INSTALL_DIR" "$BIN_DIR"
cp "$SCRIPT_DIR/tray_app.py" "$INSTALL_DIR/tray_app.py"
chmod +x "$INSTALL_DIR/tray_app.py"
ln -sf "$INSTALL_DIR/tray_app.py" "$BIN_DIR/claude-photo-tray"
echo "      OK"

# ── 3. Icon ────────────────────────────────────────────────────────────────────
echo "[3/5] Generating icon..."
mkdir -p "$ICON_DIR"
python3 - "$ICON_DIR/claude-photo-upload.png" <<'PYEOF'
import sys
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Background circle
d.ellipse([4, 4, S-4, S-4], fill="#141821", outline="#4dc9f6", width=8)
# Camera body
d.rounded_rectangle([40, 90, 216, 182], radius=18, fill="#4dc9f6")
# Viewfinder bump
d.rectangle([96, 62, 160, 94], fill="#4dc9f6")
# Lens
cx, cy = 128, 136
d.ellipse([cx-46, cy-46, cx+46, cy+46], fill="#141821")
d.ellipse([cx-30, cy-30, cx+30, cy+30], fill="#7dd8f8")
# Shutter button
d.ellipse([186, 96, 208, 118], fill="#ffffff", outline="#7dd8f8", width=2)

img.save(sys.argv[1])
PYEOF

gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "      OK"

# ── 4. App menu + autostart ────────────────────────────────────────────────────
echo "[4/5] Registering in app menu..."
mkdir -p "$APPDIR" "$AUTOSTART_DIR"

cat > "$APPDIR/claude-photo-tray.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Claude Photo Upload
GenericName=Screenshot Uploader
Comment=Upload screenshots to Claude Code agent
Exec=python3 $INSTALL_DIR/tray_app.py
Icon=claude-photo-upload
Terminal=false
Categories=Utility;Graphics;
Keywords=screenshot;upload;claude;photo;
StartupNotify=false
EOF

cp "$APPDIR/claude-photo-tray.desktop" "$AUTOSTART_DIR/claude-photo-tray.desktop"
update-desktop-database "$APPDIR" 2>/dev/null || true
echo "      OK  (search 'Claude' in your app launcher)"

# ── 5. Keyboard shortcut (Ctrl+Super+S) ───────────────────────────────────────
echo "[5/6] Registering keyboard shortcut..."

BINDING_KEY="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/claude-photo-upload/"
GSBASE="org.gnome.settings-daemon.plugins.media-keys"

# Read existing list and add our binding if not already there
EXISTING=$(gsettings get "$GSBASE" custom-keybindings 2>/dev/null || echo "[]")
if echo "$EXISTING" | grep -q "claude-photo-upload"; then
    echo "      Already registered."
else
    if echo "$EXISTING" | grep -q "^\[\]"; then
        gsettings set "$GSBASE" custom-keybindings "['$BINDING_KEY']" 2>/dev/null || true
    else
        # Append to existing list: remove trailing ] and add ours
        NEW=$(echo "$EXISTING" | sed "s|]$|, '$BINDING_KEY']|")
        gsettings set "$GSBASE" custom-keybindings "$NEW" 2>/dev/null || true
    fi
fi

gsettings set "${GSBASE}.custom-keybinding:${BINDING_KEY}" name    'Claude Screenshot Upload'                   2>/dev/null || true
gsettings set "${GSBASE}.custom-keybinding:${BINDING_KEY}" command "python3 $INSTALL_DIR/tray_app.py --screenshot" 2>/dev/null || true
gsettings set "${GSBASE}.custom-keybinding:${BINDING_KEY}" binding '<Ctrl><Super>s'                              2>/dev/null || true

echo "      OK  (Ctrl+Super+S triggers screenshot → upload)"

# ── 6. Launch ──────────────────────────────────────────────────────────────────
echo "[6/6] Launching tray app..."
pkill -f "$INSTALL_DIR/tray_app.py" 2>/dev/null || true
nohup python3 "$INSTALL_DIR/tray_app.py" > /tmp/claude-photo-tray.log 2>&1 &
sleep 1

if pgrep -f "$INSTALL_DIR/tray_app.py" > /dev/null; then
    echo "      Started! Camera icon should appear in your system tray."
else
    echo "      ERROR — could not start. Log output:"
    cat /tmp/claude-photo-tray.log
    exit 1
fi

echo ""
echo "=== Done ==="
echo "  Tray icon:   camera icon, top-right panel"
echo "  Shortcut:    Ctrl+Super+S  →  interactive screenshot → upload"
echo "  App menu:    search 'Claude Photo Upload'"
echo "  Autostart:   enabled (survives reboot)"
echo "  Uninstall:   bash $SCRIPT_DIR/install.sh --uninstall"
