#!/usr/bin/env python3
"""
System tray icon for the Claude screenshot upload service.
Left-click or "Open Upload Page" opens the web UI.
"Upload Screenshot" takes a screenshot and auto-uploads it via the web UI.
"""

import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

try:
    from PIL import Image, ImageDraw
    import pystray
except ImportError:
    print("Missing dependencies. Run: pip install pystray Pillow")
    sys.exit(1)

UPLOAD_URL = "https://claude-photo.studio-colorbox.com/"


def make_icon():
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark background circle
    draw.ellipse([2, 2, size - 2, size - 2], fill="#141821", outline="#4dc9f6", width=3)

    # Camera body
    body_x1, body_y1 = 12, 22
    body_x2, body_y2 = 52, 46
    draw.rounded_rectangle([body_x1, body_y1, body_x2, body_y2], radius=4, fill="#4dc9f6")

    # Viewfinder bump
    draw.rectangle([24, 16, 40, 23], fill="#4dc9f6")

    # Lens ring (dark)
    cx, cy = 32, 34
    draw.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill="#141821")
    draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill="#7dd8f8")

    return img


def open_browser(_icon=None, _item=None):
    webbrowser.open(UPLOAD_URL)


def take_and_upload(_icon=None, _item=None):
    """Take a screenshot with gnome-screenshot and open the upload page."""
    try:
        # Try gnome-screenshot first, fall back to scrot, then import
        tools = ["gnome-screenshot -c", "scrot -", "import -window root /tmp/tray_shot.png"]
        for tool in tools:
            result = subprocess.run(
                tool.split(), capture_output=True, timeout=5
            )
            if result.returncode == 0:
                break
    except Exception:
        pass
    # Always open the upload page — user can paste the clipboard screenshot
    webbrowser.open(UPLOAD_URL)


def quit_app(icon, _item):
    icon.stop()


def build_menu():
    return pystray.Menu(
        pystray.MenuItem("Open Upload Page", open_browser, default=True),
        pystray.MenuItem("Take & Upload Screenshot", take_and_upload),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )


def main():
    icon = pystray.Icon(
        name="claude-photo",
        icon=make_icon(),
        title="Claude Photo Upload",
        menu=build_menu(),
    )
    icon.run()


if __name__ == "__main__":
    main()
