#!/usr/bin/env python3
"""
System tray icon for the Claude screenshot upload service.
Uses AppIndicator3 (Ubuntu/GNOME native) with GTK3 menu.
- Polls /recent every 5s; shows a preview popup when a new upload is detected.
- "Recent Uploads" submenu lets you re-copy any of the last 5 paths + preview.
"""

import os
import sys
import json
import threading
import urllib.request
import webbrowser
import subprocess
import tempfile
from pathlib import Path

if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    print("ERROR: No display found.")
    print("Run this on your local desktop/laptop, not via SSH to the Claude VM.")
    sys.exit(1)

try:
    import gi
    gi.require_version("AppIndicator3", "0.1")
    gi.require_version("Gtk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import AppIndicator3, Gtk, GLib, GdkPixbuf, Gdk
except (ImportError, ValueError) as e:
    print(f"Missing dependency: {e}")
    print("Run: sudo apt install gir1.2-appindicator3-0.1 python3-gi gir1.2-gtk-3.0")
    sys.exit(1)

UPLOAD_URL = "https://claude-photo.studio-colorbox.com/"
API_BASE   = "https://claude-photo.studio-colorbox.com"
APP_ID     = "claude-photo-upload"

recent_files: list[str] = []
_first_poll = True
indicator   = None


# ── Clipboard ──────────────────────────────────────────────────────────────────

def copy_to_clipboard(text: str):
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    cb.set_text(text, -1)
    cb.store()


# ── Preview popup ──────────────────────────────────────────────────────────────

def show_preview_popup(path: str, image_url: str):
    """Fetch thumbnail in a thread, open GTK popup on the main thread."""
    def _fetch():
        try:
            suffix = Path(path).suffix or ".png"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            urllib.request.urlretrieve(image_url, tmp.name)
            local = tmp.name
        except Exception:
            local = None
        GLib.idle_add(_open_popup, path, local)

    threading.Thread(target=_fetch, daemon=True).start()


def _open_popup(path: str, image_file: str | None):
    win = Gtk.Window()
    win.set_title("Claude Photo Upload")
    win.set_default_size(260, 50)
    win.set_keep_above(True)
    win.set_resizable(False)

    # Position: bottom-right of primary monitor
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() if display else None
    if monitor:
        g = monitor.get_geometry()
        win.move(g.x + g.width - 280, g.y + g.height - 330)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_margin_top(10)
    box.set_margin_bottom(10)
    box.set_margin_start(10)
    box.set_margin_end(10)

    if image_file:
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(image_file, 240, 180, True)
            box.pack_start(Gtk.Image.new_from_pixbuf(pixbuf), False, False, 0)
        except Exception:
            pass

    name_label = Gtk.Label(label=Path(path).name)
    name_label.set_max_width_chars(32)
    name_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
    box.pack_start(name_label, False, False, 0)

    copied_label = Gtk.Label(label="✓ Path copied to clipboard")
    box.pack_start(copied_label, False, False, 0)

    copy_btn = Gtk.Button(label="Copy Path Again")
    copy_btn.connect("clicked", lambda _: copy_to_clipboard(path))
    box.pack_start(copy_btn, False, False, 0)

    win.add(box)
    win.show_all()

    copy_to_clipboard(path)
    GLib.timeout_add_seconds(6, lambda: win.destroy() or False)

    return False  # consumed by GLib.idle_add


# ── Polling ────────────────────────────────────────────────────────────────────

def _fetch_recent() -> list[str]:
    try:
        with urllib.request.urlopen(f"{API_BASE}/recent", timeout=5) as r:
            return json.loads(r.read())["files"]
    except Exception:
        return []


def poll_recent() -> bool:
    threading.Thread(target=_poll_bg, daemon=True).start()
    return True  # keep GLib timer alive


def _poll_bg():
    global recent_files, _first_poll
    files = _fetch_recent()
    new_files = [f for f in files if f not in recent_files]

    if new_files and not _first_poll:
        for path in new_files:
            url = f"{API_BASE}/files/{Path(path).name}"
            show_preview_popup(path, url)

    changed = files != recent_files
    recent_files = files
    _first_poll = False

    if changed and indicator:
        GLib.idle_add(_refresh_menu)


def _refresh_menu():
    if indicator:
        indicator.set_menu(build_menu())
    return False


# ── Menu ───────────────────────────────────────────────────────────────────────

def _on_recent_click(path: str):
    url = f"{API_BASE}/files/{Path(path).name}"
    show_preview_popup(path, url)


def _open_browser(_item):
    webbrowser.open(UPLOAD_URL)


def _take_screenshot(_item):
    try:
        subprocess.Popen(["gnome-screenshot", "--clipboard"])
    except FileNotFoundError:
        try:
            subprocess.Popen(["scrot", "-z", "/tmp/claude_shot.png"])
        except FileNotFoundError:
            pass
    webbrowser.open(UPLOAD_URL)


def _quit(_item):
    Gtk.main_quit()


def build_menu() -> Gtk.Menu:
    menu = Gtk.Menu()

    item_open = Gtk.MenuItem(label="Open Upload Page")
    item_open.connect("activate", _open_browser)
    menu.append(item_open)

    item_shot = Gtk.MenuItem(label="Screenshot → Upload")
    item_shot.connect("activate", _take_screenshot)
    menu.append(item_shot)

    if recent_files:
        menu.append(Gtk.SeparatorMenuItem())
        recent_root = Gtk.MenuItem(label="Recent Uploads")
        sub = Gtk.Menu()
        for path in recent_files[:5]:
            item = Gtk.MenuItem(label=Path(path).name)
            item.connect("activate", lambda _, p=path: _on_recent_click(p))
            sub.append(item)
        recent_root.set_submenu(sub)
        menu.append(recent_root)

    menu.append(Gtk.SeparatorMenuItem())

    item_quit = Gtk.MenuItem(label="Quit")
    item_quit.connect("activate", _quit)
    menu.append(item_quit)

    menu.show_all()
    return menu


# ── Main ───────────────────────────────────────────────────────────────────────

def _initial_load():
    poll_recent()
    return False  # one-shot


def main():
    global indicator

    indicator = AppIndicator3.Indicator.new(
        APP_ID,
        "camera-photo",
        AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("Claude Photo Upload")
    indicator.set_menu(build_menu())

    GLib.timeout_add(800, _initial_load)          # load recent once on startup
    GLib.timeout_add_seconds(5, poll_recent)      # then poll every 5s

    Gtk.main()


if __name__ == "__main__":
    main()
