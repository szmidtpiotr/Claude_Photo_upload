#!/usr/bin/env python3
"""
System tray icon for the Claude screenshot upload service.
- "Screenshot → Upload": captures screen, uploads directly, shows preview popup.
- "Recent Uploads": submenu with inline thumbnails, click to copy path.
- Polls /recent every 5s and pre-fetches thumbnails in background.
"""

import os
import sys
import json
import mimetypes
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
_first_poll  = True
indicator    = None
_thumb_cache: dict[str, GdkPixbuf.Pixbuf] = {}
THUMB_W, THUMB_H = 120, 90


# ── Clipboard ──────────────────────────────────────────────────────────────────

def copy_to_clipboard(text: str):
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    cb.set_text(text, -1)
    cb.store()


# ── Screenshot capture ─────────────────────────────────────────────────────────

def _capture_screenshot() -> str | None:
    """Save a full-screen screenshot to a temp file. Returns path or None."""
    tmp = tempfile.mktemp(suffix=".png")
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    candidates = (
        [["grim", tmp], ["gnome-screenshot", "-f", tmp]]
        if wayland else
        [["gnome-screenshot", "-f", tmp], ["scrot", tmp], ["import", "-window", "root", tmp]]
    )
    for cmd in candidates:
        try:
            r = subprocess.run(cmd, timeout=15, capture_output=True)
            if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                return tmp
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


# ── Direct HTTP upload ─────────────────────────────────────────────────────────

def _upload_file(filepath: str) -> str:
    """POST file as multipart/form-data. Returns the server-saved absolute path."""
    content_type = mimetypes.guess_type(filepath)[0] or "image/png"
    filename     = os.path.basename(filepath)
    boundary     = b"----PythonFormBoundary" + os.urandom(8).hex().encode()

    with open(filepath, "rb") as f:
        file_data = f.read()

    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="' + filename.encode() + b'"\r\n'
        b"Content-Type: " + content_type.encode() + b"\r\n"
        b"\r\n"
        + file_data
        + b"\r\n--" + boundary + b"--\r\n"
    )

    req = urllib.request.Request(
        f"{API_BASE}/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["path"]


# ── Upload preview popup ───────────────────────────────────────────────────────

def _show_upload_popup(path: str, local_image: str):
    win = Gtk.Window()
    win.set_title("Screenshot Uploaded")
    win.set_keep_above(True)
    win.set_resizable(False)
    win.set_default_size(280, 50)

    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() if display else None
    if monitor:
        g = monitor.get_geometry()
        win.move(g.x + g.width - 300, g.y + g.height - 340)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_margin_top(12)
    box.set_margin_bottom(12)
    box.set_margin_start(12)
    box.set_margin_end(12)

    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(local_image, 256, 192, True)
        box.pack_start(Gtk.Image.new_from_pixbuf(pixbuf), False, False, 0)
    except Exception:
        pass

    status = Gtk.Label()
    status.set_markup("<b>✓ Uploaded — path copied!</b>")
    box.pack_start(status, False, False, 0)

    name_lbl = Gtk.Label(label=Path(path).name)
    name_lbl.set_max_width_chars(32)
    name_lbl.set_ellipsize(3)
    box.pack_start(name_lbl, False, False, 0)

    btn = Gtk.Button(label="Copy Path Again")
    btn.connect("clicked", lambda _: copy_to_clipboard(path))
    box.pack_start(btn, False, False, 0)

    win.add(box)
    win.show_all()
    copy_to_clipboard(path)
    GLib.timeout_add_seconds(6, lambda: win.destroy() or False)
    return False  # for GLib.idle_add


def _show_error_popup(msg: str):
    dlg = Gtk.MessageDialog(
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE,
        text="Screenshot upload failed",
    )
    dlg.format_secondary_text(msg)
    dlg.run()
    dlg.destroy()
    return False


# ── Screenshot → upload action ─────────────────────────────────────────────────

def _do_screenshot_upload(_item):
    threading.Thread(target=_screenshot_upload_bg, daemon=True).start()


def _screenshot_upload_bg():
    tmp = _capture_screenshot()
    if tmp is None:
        GLib.idle_add(_show_error_popup,
                      "No screenshot tool found.\nInstall gnome-screenshot or scrot.")
        return
    try:
        path = _upload_file(tmp)
        name = Path(path).name
        # Cache thumbnail from the local file (fast, no download needed)
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(tmp, THUMB_W, THUMB_H, True)
            _thumb_cache[name] = pixbuf
        except Exception:
            pass
        GLib.idle_add(_show_upload_popup, path, tmp)
        GLib.idle_add(_refresh_menu)
    except Exception as e:
        GLib.idle_add(_show_error_popup, str(e))


# ── Thumbnail cache ────────────────────────────────────────────────────────────

def _fetch_thumb(name: str):
    if name in _thumb_cache:
        return
    url = f"{API_BASE}/files/{name}"
    try:
        suffix = Path(name).suffix or ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            urllib.request.urlretrieve(url, f.name)
            local = f.name
        _thumb_cache[name] = GdkPixbuf.Pixbuf.new_from_file_at_scale(local, THUMB_W, THUMB_H, True)
    except Exception:
        pass


def _prefetch_and_refresh(paths: list[str]):
    threads = [
        threading.Thread(target=_fetch_thumb, args=(Path(p).name,), daemon=True)
        for p in paths if Path(p).name not in _thumb_cache
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=8)
    GLib.idle_add(_refresh_menu)


# ── Menu ───────────────────────────────────────────────────────────────────────

def _make_recent_item(path: str) -> Gtk.MenuItem:
    name = Path(path).name
    item = Gtk.MenuItem()

    outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    outer.set_margin_top(4); outer.set_margin_bottom(4)
    outer.set_margin_start(4); outer.set_margin_end(8)

    img = Gtk.Image()
    img.set_size_request(THUMB_W, THUMB_H)
    if name in _thumb_cache:
        img.set_from_pixbuf(_thumb_cache[name])
    else:
        img.set_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG)
    outer.pack_start(img, False, False, 0)

    txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    txt.set_valign(Gtk.Align.CENTER)
    lbl = Gtk.Label(label=name)
    lbl.set_xalign(0.0); lbl.set_max_width_chars(24); lbl.set_ellipsize(3)
    hint = Gtk.Label()
    hint.set_markup('<small><span foreground="#888">click to copy path</span></small>')
    hint.set_xalign(0.0)
    txt.pack_start(lbl, False, False, 0)
    txt.pack_start(hint, False, False, 0)
    outer.pack_start(txt, True, True, 0)

    item.add(outer)
    item.connect("activate", lambda _, p=path: copy_to_clipboard(p))
    return item


def build_menu() -> Gtk.Menu:
    menu = Gtk.Menu()

    item_open = Gtk.MenuItem(label="Open Upload Page")
    item_open.connect("activate", lambda _: webbrowser.open(UPLOAD_URL))
    menu.append(item_open)

    item_shot = Gtk.MenuItem(label="Screenshot → Upload")
    item_shot.connect("activate", _do_screenshot_upload)
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
    item_quit.connect("activate", lambda _: Gtk.main_quit())
    menu.append(item_quit)

    menu.show_all()
    return menu


def _refresh_menu():
    if indicator:
        indicator.set_menu(build_menu())
    return False


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
    recent_files = files
    _first_poll = False
    threading.Thread(target=_prefetch_and_refresh, args=(files,), daemon=True).start()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global indicator

    indicator = AppIndicator3.Indicator.new(
        APP_ID, "camera-photo",
        AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("Claude Photo Upload")
    indicator.set_menu(build_menu())

    GLib.timeout_add(800, lambda: [poll_recent(), False][1])
    GLib.timeout_add_seconds(5, poll_recent)

    Gtk.main()


if __name__ == "__main__":
    main()
