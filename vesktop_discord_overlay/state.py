"""Small things remembered between runs (currently the panel opacity), kept in a JSON file."""

import json

from .config import STATE_FILE


def load():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save(**changes):
    state = load()
    state.update(changes)
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except OSError:
        pass  # not being able to remember a preference shouldn't break anything
