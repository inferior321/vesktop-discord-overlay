"""Check: keyboard flow with real key presses. The panel opens in the open chat's reply box; → opens a chat and
goes to its reply box; ← at the start of the reply box and Tab go back to the list; Enter in the list does
nothing; → on a server opens its channels."""

import os
import subprocess

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

fb.install(main)


def keys(*combos):
    subprocess.run(["xdotool", "key", "--delay", "80", *combos], env=dict(os.environ))


def where(o):
    focus = o.win.get_focus()
    return "reply" if focus is o.reply else "list" if focus is o.listbox else type(focus).__name__


def expect(o, focus, chat, label):
    print(f"{label}: focus {where(o)}, chat {o.channel_id}", flush=True)
    assert where(o) == focus and o.channel_id == chat, f"expected focus {focus}, chat {chat}"


def opened(o):
    expect(o, "reply", "F1", "panel opened")
    keys("Tab")


def tab_to_list(o):
    expect(o, "list", "F1", "Tab")
    keys("Down", "Down", "Right")


def right_opens(o):
    expect(o, "reply", "F3", "→ on Friend 3")
    keys("Left")


def left_back(o):
    expect(o, "list", "F3", "← in the empty reply box")
    keys("Return")


def enter_nothing(o):
    expect(o, "list", "F3", "Enter in the list (does nothing)")
    keys("Down", "Right", "h", "i", "Left")


def left_in_text(o):
    expect(o, "reply", "F4", "typed 'hi', one ← (the cursor moves inside the text)")
    keys("Left")


def at_start(o):
    expect(o, "reply", "F4", "second ← (the cursor reaches the start; still typing)")
    keys("Left")


def left_at_start(o):
    expect(o, "list", "F4", "third ← (already at the start: back to the list)")
    assert o.drafts.get("F4") == "hi" or o.reply.get_text() == "hi", "the text is kept"
    keys("Tab")


def tab_to_reply(o):
    expect(o, "reply", "F4", "Tab from the list")
    o.hide()


def reopen(o):
    o.show()


def reopened(o):
    expect(o, "reply", "F4", "panel reopened")
    keys("ctrl+Tab")


def servers(o):
    expect(o, "list", "F4", "Ctrl+Tab to Servers")
    keys("Right")


def in_server(o):
    assert o.server and o.server["id"] == "S1", "→ on a server opens its channels"
    print(f"→ on a server: channels of {o.server['id']}, focus {where(o)}", flush=True)
    keys("Right")


def channel_open(o):
    expect(o, "reply", "C1", "→ on a channel")


def wait(o):
    pass


fb.run_steps(main, [wait, opened, tab_to_list, right_opens, left_back, enter_nothing, left_in_text, at_start,
                    left_at_start, tab_to_reply, reopen, wait, reopened, servers, wait, in_server, wait, channel_open],
             interval_ms=700)
