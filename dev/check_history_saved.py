"""Check: the Ctrl+Left / Right history is remembered across restarts, chats that can't open any more are
skipped and dropped, and Ctrl+Shift+Down clears it after asking (Esc cancels, Enter clears)."""

import json
import os
import subprocess

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

# What a previous run left behind: three chats, one of which no longer exists.
fb.SAVED_STATE.update(opacity=1.0, history=[{"id": "F2", "guildId": None, "name": "Friend 2"},
                                            {"id": "GONE", "guildId": None, "name": "Old chat"},
                                            {"id": "F3", "guildId": None, "name": "Friend 3"}])
fb.install(main, lambda method, args: {"error": "Channel not found"}
           if method == "messages" and args[0] == "GONE" else None)


def saved():
    return [e["id"] for e in json.loads(main.state.STATE_FILE.read_text()).get("history", [])]


def ids(o):
    return [e["id"] for e in o.history]


def keys(*combos):
    subprocess.run(["xdotool", "key", "--delay", "80", *combos], env=dict(os.environ))


def loaded(o):
    # The first open shows what Vesktop shows (F1), which becomes the newest entry after the remembered ones.
    print(f"after a restart: history {ids(o)}", flush=True)
    assert ids(o) == ["F2", "GONE", "F3", "F1"] and saved() == ids(o)
    o._step_history(-1)  # F3


def back_twice(o):
    assert o.channel_id == "F3"
    o._step_history(-1)  # GONE: can't open, so it's dropped and the step continues to F2


def skipped(o):
    print(f"stepped onto a chat that's gone: now in {o.channel_id}, history {ids(o)}", flush=True)
    assert o.channel_id == "F2" and "GONE" not in ids(o) and "GONE" not in saved()
    o._focus_reply()
    keys("ctrl+shift+Down")


def asked(o):
    assert o.clearing_history and o.clear_note.get_visible(), "asks first"
    print(f"Ctrl+Shift+Down asks: {o.clear_note_label.get_text()!r}", flush=True)
    keys("Escape")


def cancelled(o):
    assert not o.clearing_history and ids(o) == ["F2", "F3", "F1"], "Esc keeps the history"
    keys("ctrl+shift+Down")


def ask_again(o):
    keys("Return")


def cleared(o):
    focus = "list" if o.win.get_focus() is o.listbox else "elsewhere"
    print(f"Enter clears: history {ids(o)}, saved {saved()}, open chat {o.channel_id}, cursor in the {focus}",
          flush=True)
    assert ids(o) == [] and saved() == [] and not o.clear_note.get_visible()
    assert o.channel_id is None and focus == "list", "clearing everything leaves the empty pane"
    for chat in ("F2", "F3", "F4"):  # a fresh history: F2, F3, F4 (F4 open, the most recent)
        o._open_conversation(chat)
    o._step_history(-1)  # to F3, in the middle
    keys("ctrl+shift+Left")


def removed_middle(o):
    print(f"Ctrl+Shift+Left on F3 (middle): now in {o.channel_id}, history {ids(o)}", flush=True)
    assert ids(o) == ["F2", "F4"] and o.channel_id == "F4", "the more recent chat opens, like closing a tab"
    assert o.win.get_focus() is o.reply, "ready to type"
    keys("ctrl+shift+Left")


def removed_newest(o):
    print(f"Ctrl+Shift+Left on F4 (most recent): now in {o.channel_id}, history {ids(o)}", flush=True)
    assert ids(o) == ["F2"] and o.channel_id == "F2", "the one before opens when there's nothing more recent"
    keys("ctrl+shift+Left")


def removed_last(o):
    print(f"Ctrl+Shift+Left on F2 (the only one): open chat {o.channel_id}, history {ids(o)}", flush=True)
    assert ids(o) == [] and o.channel_id is None, "nothing left: the empty pane"


def wait(o):
    pass


fb.run_steps(main, [wait, loaded, back_twice, wait, skipped, wait, asked, cancelled, wait, ask_again, wait,
                    cleared, wait, removed_middle, wait, removed_newest, wait, removed_last],
             interval_ms=600)
