"""Keeps a single overlay running: the first one holds a lock file; later ones see it and back off."""

import fcntl
import os
from pathlib import Path

LOCK_PATH = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "vesktop-discord-overlay.lock"


def acquire():
    """Take the lock for this process. Returns the open lock file (keep it open), or None if already held."""
    handle = open(LOCK_PATH, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def overlay_running():
    handle = acquire()
    if handle is None:
        return True
    handle.close()  # closing releases it again
    return False
