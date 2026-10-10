#!/usr/bin/env python3
"""Start Vesktop (with the DevTools port the overlay needs) and the overlay. Run by the app-menu / panel icon.

- Vesktop not running: start it with the port.
- Vesktop running with the port: just bring its window up.
- Vesktop running without the port: ask, then restart it with the port.
- Overlay not running: start it, following Vesktop (it quits once Vesktop fully exits). Its output goes to
  ~/.cache/vesktop-discord-overlay/overlay.log since there's no terminal.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from vesktop_discord_overlay import instance  # noqa: E402
from vesktop_discord_overlay.config import CACHE_DIR  # noqa: E402
from vesktop_discord_overlay.system import (  # noqa: E402
    activate_vesktop_window, debug_port_open, quit_vesktop, start_vesktop, vesktop_running)

TITLE = "Vesktop Discord Overlay"


def ask_restart():
    text = ("Vesktop is already running without the connection the overlay needs.\n\n"
            "Restart Vesktop now? If you're in a voice call it will drop for a few seconds.")
    result = subprocess.run(["zenity", "--question", f"--title={TITLE}", f"--text={text}",
                             "--ok-label=Restart Vesktop", "--cancel-label=Not now",
                             "--icon-name=vesktop-discord-overlay"])
    return result.returncode == 0


def notify(text):
    subprocess.run(["notify-send", "--app-name", TITLE, "--icon", "vesktop-discord-overlay", TITLE, text])


def start_overlay():
    if instance.overlay_running():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(CACHE_DIR / "overlay.log", "a")
    subprocess.Popen([sys.executable, str(HERE / "main.py"), "--follow-vesktop"], cwd=HERE, stdout=log,
                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)


def main():
    if not vesktop_running():
        start_vesktop()
    elif debug_port_open():
        activate_vesktop_window()
    elif ask_restart():
        if not quit_vesktop():
            notify("Couldn't close Vesktop. Quit it from its tray icon, then click again.")
            return
        start_vesktop()
    else:
        return  # left as is; the overlay couldn't talk to this Vesktop anyway
    start_overlay()


if __name__ == "__main__":
    main()
