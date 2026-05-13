#!/usr/bin/env python3
"""
System tray icon for the Claude screenshot upload service.
Uses AppIndicator3 (Ubuntu/GNOME native) with GTK3 menu.
Recent uploads show inline thumbnail previews inside the dropdown.
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

# Optional: system notification on new upload
try:
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify
    Notify.init("Claude Photo Upload")
    HAS_NOTIFY = True
except Exception:
    HAS_NOTIFY = False

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


# ── Thumbnail loader ───────────────────────────────────────────────────────────

def _load_thumb_async(url: str, img_widget: Gtk.Image, size: tuple[int, int] = (120, 90)):
    """Download image in background, set pixbuf on img_widget when ready."""
    def _fetch():
        try:
            suffix = Path(url).suffix or ".png"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                urllib.request.urlretrieve(url, f.name)
                local = f.name
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(local, size[0], size[1], True)
            GLib.idle_add(img_widget.set_from_pixbuf, pixbuf)
        except Exception:
            pass

    threading.Thread(target=_fetch, daemon=True).start()


# ── Recent item widget ─────────────────────────────────────────────────────────

def _make_recent_item(path: str) -> Gtk.MenuItem:
    """Build a menu item with inline thumbnail + filename + 'copy path' hint."""
    item = Gtk.MenuItem()

    outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    outer.set_margin_top(4)
    outer.set_margin_bottom(4)
    outer.set_margin_start(4)
    outer.set_margin_end(8)

    # Thumbnail placeholder — filled async
    img = Gtk.Image()
    img.set_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG)
    img.set_size_request(120, 90)
    outer.pack_start(img, False, False, 0)

    # Text column
    txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    txt.set_valign(Gtk.Align.CENTER)

    name = Gtk.Label(label=Path(path).name)
    name.set_xalign(0.0)
    name.set_max_width_chars(24)
    name.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
    txt.pack_start(name, False, False, 0)

    hint = Gtk.Label()
    hint.set_markup('<small><span foreground="#888">click to copy path</span></small>')
    hint.set_xalign(0.0)
    txt.pack_start(hint, False, False, 0)

    outer.pack_start(txt, True, True, 0)
    item.add(outer)

    item.connect("activate", lambda _, p=path: _on_recent_click(p))

    # Kick off thumbnail download
    url = f"{API_BASE}/files/{Path(path).name}"
    _load_thumb_async(url, img)

    return item


# ── Actions ────────────────────────────────────────────────────────────────────

def _on_recent_click(path: str):
    copy_to_clipboard(path)


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


# ── Menu builder ───────────────────────────────────────────────────────────────

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
            sub.append(_make_recent_item(path))
        recent_root.set_submenu(sub)
        menu.append(recent_root)

    menu.append(Gtk.SeparatorMenuItem())

    item_quit = Gtk.MenuItem(label="Quit")
    item_quit.connect("activate", _quit)
    menu.append(item_quit)

    menu.show_all()
    return menu


# ── Polling ────────────────────────────────────────────────────────────────────

def _fetch_recent() -> list[str]:
    try:
        with urllib.request.urlopen(f"{API_BASE}/recent", timeout=5) as r:
            return json.loads(r.read())["files"]
    except Exception:
        return []


def poll_recent() -> bool:
    threading.Thread(target=_poll_bg, daemon=True).start()
    return True


def _poll_bg():
    global recent_files, _first_poll
    files = _fetch_recent()
    new_files = [f for f in files if f not in recent_files]

    if new_files and not _first_poll and HAS_NOTIFY:
        for path in new_files:
            try:
                n = Notify.Notification.new(
                    "Screenshot uploaded",
                    Path(path).name,
                    "camera-photo",
                )
                n.show()
            except Exception:
                pass

    changed = files != recent_files
    recent_files = files
    _first_poll = False

    if changed and indicator:
        GLib.idle_add(_refresh_menu)


def _refresh_menu():
    if indicator:
        indicator.set_menu(build_menu())
    return False


# ── Main ───────────────────────────────────────────────────────────────────────

def _initial_load():
    poll_recent()
    return False


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

    GLib.timeout_add(800, _initial_load)
    GLib.timeout_add_seconds(5, poll_recent)

    Gtk.main()


if __name__ == "__main__":
    main()
