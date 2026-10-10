"""Checks run before anything else, so a missing package or a Wayland session gets a plain explanation instead
of a Python traceback or a hotkey that silently does nothing. Standard library only: it has to work even when
the packages it checks for are missing."""

import importlib
import os
import shutil
import subprocess
import sys

TITLE = "Vesktop Discord Overlay"

# What the overlay can't run without: (what Python loads, the Debian / Ubuntu / Mint package that provides it).
REQUIRED = [
    ("gi", "python3-gi"),
    ("gi:Gtk:3.0", "gir1.2-gtk-3.0"),
    ("gi:Gdk:3.0", "gir1.2-gtk-3.0"),
    ("gi:GdkX11:3.0", "gir1.2-gtk-3.0"),
    ("gi:PangoCairo:1.0", "gir1.2-pango-1.0"),
    ("gi:cairo", "python3-gi-cairo"),
    ("Xlib", "python3-xlib"),
    ("websockets", "python3-websockets"),
]


def _loads(what):
    try:
        if not what.startswith("gi:"):
            importlib.import_module(what)
            return True
        import gi
        parts = what.split(":")
        if parts[1] == "cairo":
            gi.require_foreign("cairo")
        else:
            gi.require_version(parts[1], parts[2])
            importlib.import_module(f"gi.repository.{parts[1]}")
        return True
    except (ImportError, ValueError):
        return False


def problems():
    """What stops the overlay from working on this computer, as messages saying how to fix it."""
    found = []
    session = os.environ.get("XDG_SESSION_TYPE", "")
    if session == "wayland":
        found.append("This is a Wayland session, and the overlay needs X11 (its hotkey can't work on Wayland). "
                     "Log out and choose an X11 / Xorg session on the login screen.")
    elif not os.environ.get("DISPLAY"):
        found.append("No X11 display found (DISPLAY isn't set). The overlay needs an X11 desktop session.")
    missing = []
    for what, package in REQUIRED:
        if package not in missing and not _loads(what):
            missing.append(package)
    if missing:
        found.append(f"Missing: {', '.join(missing)}. Run ./install.sh, or: sudo apt install {' '.join(missing)}")
    return found


def tell(message):
    """Say it in the terminal and, since there may not be one (the app-menu entry), as a desktop notification."""
    print(f"vesktop-discord-overlay: {message}", file=sys.stderr, flush=True)
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "--app-name", TITLE, "--icon", "vesktop-discord-overlay", TITLE, message],
                       check=False)


def check_or_exit():
    found = problems()
    for message in found:
        tell(message)
    if found:
        sys.exit(1)
