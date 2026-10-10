"""Helpers that look at or drive the desktop: is Vesktop running, xdotool, launching."""

import os
import signal
import subprocess
import time
import urllib.request

from .config import DEBUG_PORT, VESKTOP_APP, VESKTOP_LAUNCH


def vesktop_running():
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() == "vesktop.bin":
                    return True
        except OSError:
            continue
    return False


def other_vesktop_running():
    """Is a Vesktop running that isn't the Flatpak (a .deb, AppImage or AUR install)? Best effort."""
    own = str(os.getpid())
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or pid == own:
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                args = f.read().decode(errors="replace").lower().split("\0")
        except OSError:
            continue
        flatpak = comm in ("vesktop.bin", "bwrap") or any(a.startswith("/app/") or VESKTOP_APP.lower() in a
                                                          for a in args)  # (/app/ is inside a Flatpak)
        if flatpak or any("vesktop-discord-overlay" in a or "vesktop_discord_overlay" in a for a in args):
            continue  # the Flatpak, or this overlay
        if comm == "vesktop" or any(a.endswith("/vesktop") or "/vesktop/" in a for a in args):
            return True
    return False


def flatpak_vesktop_installed():
    try:
        return subprocess.run(["flatpak", "info", VESKTOP_APP], capture_output=True).returncode == 0
    except OSError:
        return False


def vesktop_main_pid():
    """The main Vesktop process (not its renderer/GPU helpers, which carry a --type= flag), or None."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() != "vesktop.bin":
                    continue
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                if b"--type=" not in f.read():
                    return int(pid)
        except OSError:
            continue
    return None


def debug_port_open():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=1):
            return True
    except OSError:
        return False


def start_vesktop():
    """Start Vesktop with the DevTools port the overlay talks through, detached from us."""
    subprocess.Popen(VESKTOP_LAUNCH + [f"--remote-debugging-port={DEBUG_PORT}"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def quit_vesktop(timeout=15):
    """Ask Vesktop to quit (like Quit in its tray menu) and wait for it; force it only if it won't."""
    pid = vesktop_main_pid()
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(timeout * 4):
        if not vesktop_running():
            return True
        time.sleep(0.25)
    subprocess.run(["flatpak", "kill", "dev.vencord.Vesktop"], capture_output=True)
    time.sleep(1)
    return not vesktop_running()


def run_quiet(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def activate_vesktop_window():
    windows = run_quiet(["xdotool", "search", "--onlyvisible", "--class", "vesktop"]).split()
    if windows:
        run_quiet(["xdotool", "windowactivate", windows[-1]])
    else:
        # Hidden in the tray: launching again tells the running instance to show its window.
        subprocess.Popen(VESKTOP_LAUNCH, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
