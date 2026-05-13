#!/usr/bin/env python3
"""
System tray icon for the Claude screenshot upload service.
Uses AppIndicator3 (Ubuntu/GNOME native) with GTK3 menu.
"""

import sys
import webbrowser
import subprocess

try:
    import gi
    gi.require_version("AppIndicator3", "0.1")
    gi.require_version("Gtk", "3.0")
    from gi.repository import AppIndicator3, Gtk
except (ImportError, ValueError) as e:
    print(f"Missing dependency: {e}")
    print("Run: sudo apt install gir1.2-appindicator3-0.1 python3-gi")
    sys.exit(1)

UPLOAD_URL = "https://claude-photo.studio-colorbox.com/"
APP_ID = "claude-photo-upload"


def open_browser(_item):
    webbrowser.open(UPLOAD_URL)


def take_screenshot(_item):
    """Grab screen to clipboard via gnome-screenshot, then open upload page."""
    try:
        subprocess.Popen(["gnome-screenshot", "--clipboard"])
    except FileNotFoundError:
        try:
            subprocess.Popen(["scrot", "-z", "/tmp/claude_shot.png"])
        except FileNotFoundError:
            pass
    webbrowser.open(UPLOAD_URL)


def quit_app(_item):
    Gtk.main_quit()


def build_menu():
    menu = Gtk.Menu()

    item_open = Gtk.MenuItem(label="Open Upload Page")
    item_open.connect("activate", open_browser)
    menu.append(item_open)

    item_shot = Gtk.MenuItem(label="Screenshot → Upload")
    item_shot.connect("activate", take_screenshot)
    menu.append(item_shot)

    menu.append(Gtk.SeparatorMenuItem())

    item_quit = Gtk.MenuItem(label="Quit")
    item_quit.connect("activate", quit_app)
    menu.append(item_quit)

    menu.show_all()
    return menu


def main():
    indicator = AppIndicator3.Indicator.new(
        APP_ID,
        "camera-photo",                                    # standard freedesktop icon
        AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("Claude Photo Upload")
    indicator.set_menu(build_menu())

    Gtk.main()


if __name__ == "__main__":
    main()
