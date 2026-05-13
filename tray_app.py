#!/usr/bin/env python3
"""
System tray icon for the Claude screenshot upload service.

Modes:
  python3 tray_app.py             — normal tray icon
  python3 tray_app.py --screenshot — one-shot: capture → upload → popup → exit
                                     (used by keyboard shortcut)
"""

import os, sys, json, mimetypes, threading, subprocess, tempfile, re
import urllib.request, webbrowser
from pathlib import Path

if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    print("ERROR: No display found. Run on your desktop/laptop, not via SSH.")
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
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────

CONFIG_PATH      = Path.home() / ".config" / "claude-photo" / "config.json"
DEFAULT_SERVER   = "https://claude-photo.studio-colorbox.com"
DEFAULT_SHORTCUT = "<Ctrl><Super>s"
BINDING_KEY      = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/claude-photo-upload/"
GSBASE           = "org.gnome.settings-daemon.plugins.media-keys"
INSTALL_DIR      = Path.home() / ".local" / "share" / "claude-photo"

def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}

def save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))

def cfg_get(key: str, default: str = "") -> str:
    return load_config().get(key, default)

APP_ID     = "claude-photo-upload"
STANDALONE = "--screenshot" in sys.argv

recent_files: list[str]               = []
_first_poll                           = True
indicator                             = None
_thumb_cache: dict[str, GdkPixbuf.Pixbuf] = {}
THUMB_W, THUMB_H = 120, 90


# ── Clipboard ──────────────────────────────────────────────────────────────────

def copy_to_clipboard(text: str):
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    cb.set_text(text, -1)
    cb.store()


# ── Keyboard shortcut ──────────────────────────────────────────────────────────

def register_shortcut(shortcut: str) -> str:
    """Register GNOME custom keybinding. Returns '' on success or error message."""
    try:
        existing = subprocess.run(
            ["gsettings", "get", GSBASE, "custom-keybindings"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()

        if "claude-photo-upload" not in existing:
            if re.match(r"@?as\s*\[\]|\[\]", existing):
                new_list = f"['{BINDING_KEY}']"
            else:
                new_list = existing.rstrip("]").rstrip() + f", '{BINDING_KEY}']"
            subprocess.run(["gsettings", "set", GSBASE, "custom-keybindings", new_list], timeout=5)

        cmd = f"python3 {INSTALL_DIR}/tray_app.py --screenshot"
        for key, val in [("name", "Claude Screenshot Upload"), ("command", cmd), ("binding", shortcut)]:
            subprocess.run(["gsettings", "set", f"{GSBASE}.custom-keybinding:{BINDING_KEY}", key, val], timeout=5)
        return ""
    except Exception as e:
        return str(e)


# ── Preferences dialog ─────────────────────────────────────────────────────────

def open_preferences(_item=None):
    cfg = load_config()

    dlg = Gtk.Dialog(title="Claude Photo Upload — Preferences")
    dlg.set_default_size(440, 10)
    dlg.set_resizable(False)
    dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
    btn_save = dlg.add_button("Save", Gtk.ResponseType.OK)
    btn_save.get_style_context().add_class("suggested-action")

    area = dlg.get_content_area()
    area.set_spacing(0)

    grid = Gtk.Grid(column_spacing=12, row_spacing=10)
    grid.set_margin_top(16); grid.set_margin_bottom(16)
    grid.set_margin_start(16); grid.set_margin_end(16)

    def row(r, label_text, widget, hint=None):
        lbl = Gtk.Label(label=label_text)
        lbl.set_xalign(1.0)
        lbl.set_valign(Gtk.Align.CENTER)
        grid.attach(lbl, 0, r, 1, 1)
        widget.set_hexpand(True)
        grid.attach(widget, 1, r, 1, 1)
        if hint:
            h = Gtk.Label()
            h.set_markup(f'<small><span foreground="#888">{hint}</span></small>')
            h.set_xalign(0.0)
            grid.attach(h, 1, r + 1, 1, 1)

    # Server URL
    url_entry = Gtk.Entry()
    url_entry.set_text(cfg.get("server_url", DEFAULT_SERVER))
    row(0, "Server URL:", url_entry)

    # Save subfolder
    folder_entry = Gtk.Entry()
    folder_entry.set_text(cfg.get("subfolder", ""))
    folder_entry.set_placeholder_text("e.g.  project1  or  work/designs")
    row(2, "Save subfolder:", folder_entry, "Relative to ~/screenshots on the server. Leave empty for default.")

    # Keyboard shortcut
    sc_box = Gtk.Box(spacing=8)
    sc_entry = Gtk.Entry()
    sc_entry.set_text(cfg.get("shortcut", DEFAULT_SHORTCUT))
    sc_entry.set_placeholder_text(DEFAULT_SHORTCUT)
    sc_entry.set_hexpand(True)
    sc_box.pack_start(sc_entry, True, True, 0)

    reg_btn = Gtk.Button(label="Register")
    reg_btn.set_tooltip_text("Apply this shortcut in GNOME now")
    sc_box.pack_start(reg_btn, False, False, 0)
    row(4, "Keyboard shortcut:", sc_box, "GTK format, e.g.  &lt;Ctrl&gt;&lt;Super&gt;s  or  &lt;Alt&gt;&lt;Shift&gt;u")

    reg_status = Gtk.Label(label="")
    reg_status.set_xalign(0.0)
    grid.attach(reg_status, 1, 6, 1, 1)

    def on_register(_btn):
        sc = sc_entry.get_text().strip()
        err = register_shortcut(sc)
        if err:
            reg_status.set_markup(f'<span foreground="red">✗ {err}</span>')
        else:
            reg_status.set_markup(f'<span foreground="green">✓ Registered {sc}</span>')

    reg_btn.connect("clicked", on_register)

    area.pack_start(grid, True, True, 0)
    dlg.show_all()
    response = dlg.run()

    if response == Gtk.ResponseType.OK:
        new_cfg = {
            "server_url": url_entry.get_text().strip().rstrip("/") or DEFAULT_SERVER,
            "subfolder":  folder_entry.get_text().strip(),
            "shortcut":   sc_entry.get_text().strip() or DEFAULT_SHORTCUT,
        }
        save_config(new_cfg)
        # Re-register shortcut with saved value
        register_shortcut(new_cfg["shortcut"])

    dlg.destroy()


# ── Screenshot capture ─────────────────────────────────────────────────────────

def _capture_screenshot() -> str | None:
    tmp     = tempfile.mktemp(suffix=".png")
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))

    if wayland:
        try:
            sel = subprocess.run(["slurp"], capture_output=True, text=True, timeout=30)
            if sel.returncode == 0 and sel.stdout.strip():
                r = subprocess.run(["grim", "-g", sel.stdout.strip(), tmp], timeout=15)
                if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                    return tmp
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        candidates = [["gnome-screenshot", "-a", "-f", tmp]]
    else:
        candidates = [
            ["gnome-screenshot", "-a", "-f", tmp],
            ["scrot", "-s", tmp],
            ["import", tmp],
        ]

    for cmd in candidates:
        try:
            r = subprocess.run(cmd, timeout=60)
            if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                return tmp
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


# ── HTTP upload ────────────────────────────────────────────────────────────────

def _upload_file(filepath: str) -> str:
    cfg        = load_config()
    api_base   = cfg.get("server_url", DEFAULT_SERVER).rstrip("/")
    subfolder  = cfg.get("subfolder", "").strip()
    ct         = mimetypes.guess_type(filepath)[0] or "image/png"
    filename   = os.path.basename(filepath)
    boundary   = b"----PythonBoundary" + os.urandom(8).hex().encode()

    with open(filepath, "rb") as f:
        file_data = f.read()

    parts = [
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="' + filename.encode() + b'"\r\n'
        b"Content-Type: " + ct.encode() + b"\r\n\r\n"
        + file_data + b"\r\n"
    ]
    if subfolder:
        parts.append(
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="folder"\r\n\r\n'
            + subfolder.encode() + b"\r\n"
        )
    body = b"".join(parts) + b"--" + boundary + b"--\r\n"

    req = urllib.request.Request(
        f"{api_base}/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["path"]


# ── Upload result popup ────────────────────────────────────────────────────────

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
    for m in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{m}")(12)

    try:
        px = GdkPixbuf.Pixbuf.new_from_file_at_scale(local_image, 256, 192, True)
        box.pack_start(Gtk.Image.new_from_pixbuf(px), False, False, 0)
    except Exception:
        pass

    lbl = Gtk.Label()
    lbl.set_markup("<b>✓ Uploaded — path copied!</b>")
    box.pack_start(lbl, False, False, 0)

    name_lbl = Gtk.Label(label=Path(path).name)
    name_lbl.set_max_width_chars(32)
    name_lbl.set_ellipsize(3)
    box.pack_start(name_lbl, False, False, 0)

    btn = Gtk.Button(label="Copy Path Again")
    btn.connect("clicked", lambda _: copy_to_clipboard(path))
    box.pack_start(btn, False, False, 0)

    def _close():
        win.destroy()
        if STANDALONE:
            Gtk.main_quit()
        return False

    win.connect("destroy", lambda _: Gtk.main_quit() if STANDALONE else None)
    win.add(box)
    win.show_all()
    copy_to_clipboard(path)
    GLib.timeout_add_seconds(6, _close)
    return False


def _show_error(msg: str):
    dlg = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.CLOSE, text="Upload failed")
    dlg.format_secondary_text(msg)
    dlg.run(); dlg.destroy()
    if STANDALONE:
        Gtk.main_quit()
    return False


# ── Screenshot → upload ────────────────────────────────────────────────────────

def _do_screenshot_upload(_item=None):
    threading.Thread(target=_screenshot_upload_bg, daemon=True).start()


def _screenshot_upload_bg():
    tmp = _capture_screenshot()
    if tmp is None:
        GLib.idle_add(_show_error, "No screenshot tool found.\nInstall gnome-screenshot or scrot.")
        return
    try:
        path = _upload_file(tmp)
        name = Path(path).name
        try:
            _thumb_cache[name] = GdkPixbuf.Pixbuf.new_from_file_at_scale(tmp, THUMB_W, THUMB_H, True)
        except Exception:
            pass
        GLib.idle_add(_show_upload_popup, path, tmp)
        if not STANDALONE:
            GLib.idle_add(_refresh_menu)
    except Exception as e:
        GLib.idle_add(_show_error, str(e))


# ── Thumbnails ─────────────────────────────────────────────────────────────────

def _fetch_thumb(name: str):
    if name in _thumb_cache:
        return
    api_base = load_config().get("server_url", DEFAULT_SERVER).rstrip("/")
    try:
        suffix = Path(name).suffix or ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            urllib.request.urlretrieve(f"{api_base}/files/{name}", f.name)
            _thumb_cache[name] = GdkPixbuf.Pixbuf.new_from_file_at_scale(f.name, THUMB_W, THUMB_H, True)
    except Exception:
        pass


def _prefetch_and_refresh(paths: list[str]):
    threads = [threading.Thread(target=_fetch_thumb, args=(Path(p).name,), daemon=True)
               for p in paths if Path(p).name not in _thumb_cache]
    for t in threads: t.start()
    for t in threads: t.join(timeout=8)
    GLib.idle_add(_refresh_menu)


# ── Tray menu ──────────────────────────────────────────────────────────────────

def _make_recent_item(path: str) -> Gtk.MenuItem:
    name = Path(path).name
    item = Gtk.MenuItem()
    outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    for m in ("top", "bottom", "start"): getattr(outer, f"set_margin_{m}")(4)
    outer.set_margin_end(8)

    img = Gtk.Image()
    img.set_size_request(THUMB_W, THUMB_H)
    (img.set_from_pixbuf(_thumb_cache[name]) if name in _thumb_cache
     else img.set_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG))
    outer.pack_start(img, False, False, 0)

    txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    txt.set_valign(Gtk.Align.CENTER)
    lbl = Gtk.Label(label=name); lbl.set_xalign(0.0)
    lbl.set_max_width_chars(24); lbl.set_ellipsize(3)
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
    cfg      = load_config()
    shortcut = cfg.get("shortcut", DEFAULT_SHORTCUT)
    # Convert GTK modifier format to readable: <Ctrl><Super>s → Ctrl+⊞+S
    human = (shortcut.replace("<Ctrl>", "Ctrl+").replace("<Super>", "⊞+")
             .replace("<Alt>", "Alt+").replace("<Shift>", "Shift+"))

    menu = Gtk.Menu()

    item_open = Gtk.MenuItem(label="Open Upload Page")
    item_open.connect("activate", lambda _: webbrowser.open(
        cfg.get("server_url", DEFAULT_SERVER)))
    menu.append(item_open)

    item_shot = Gtk.MenuItem(label=f"Screenshot → Upload  ({human})")
    item_shot.connect("activate", _do_screenshot_upload)
    menu.append(item_shot)

    if recent_files:
        menu.append(Gtk.SeparatorMenuItem())
        root = Gtk.MenuItem(label="Recent Uploads")
        sub  = Gtk.Menu()
        for p in recent_files[:5]:
            sub.append(_make_recent_item(p))
        root.set_submenu(sub)
        menu.append(root)

    menu.append(Gtk.SeparatorMenuItem())

    item_prefs = Gtk.MenuItem(label="Preferences…")
    item_prefs.connect("activate", open_preferences)
    menu.append(item_prefs)

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
    api_base = load_config().get("server_url", DEFAULT_SERVER).rstrip("/")
    try:
        with urllib.request.urlopen(f"{api_base}/recent", timeout=5) as r:
            return json.loads(r.read())["files"]
    except Exception:
        return []


def poll_recent() -> bool:
    threading.Thread(target=_poll_bg, daemon=True).start()
    return True


def _poll_bg():
    global recent_files, _first_poll
    recent_files = _fetch_recent()
    _first_poll  = False
    threading.Thread(target=_prefetch_and_refresh, args=(recent_files,), daemon=True).start()


# ── Entry points ───────────────────────────────────────────────────────────────

def main_tray():
    global indicator
    indicator = AppIndicator3.Indicator.new(
        APP_ID, "camera-photo", AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("Claude Photo Upload")
    indicator.set_menu(build_menu())
    GLib.timeout_add(800, lambda: [poll_recent(), False][1])
    GLib.timeout_add_seconds(5, poll_recent)
    Gtk.main()


def main_screenshot():
    _do_screenshot_upload()
    Gtk.main()


if __name__ == "__main__":
    if STANDALONE:
        main_screenshot()
    else:
        main_tray()
