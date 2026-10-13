"""Check: '@' and '#' suggestions in the reply box (real key presses, through xdotool): people / channels show
while typing, ↓ / Tab / Enter pick, Esc closes, an answer that arrives after you typed on is ignored, '#' in a
DM and an @ inside a word suggest nothing, ':' emoji suggestions still work, and what's sent has the mention."""

import os
import subprocess

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

PEOPLE = [{"kind": "person", "id": f"u{i}", "name": f"Friend {i}", "username": f"friend{i}", "avatar": None,
           "insert": f"@friend{i} "} for i in range(1, 4)]
CHANNELS = [{"kind": "channel", "id": c["id"], "name": c["name"], "insert": f"#{c['name']} ", "icon": "text"}
            for c in fb.CHANNELS]
held = {}  # query -> answer held back (to answer late)


def respond(method, args):
    if method == "suggestPeople":
        query = args[1]
        found = [p for p in PEOPLE if p["username"].startswith(query) or p["name"].lower().startswith(query)]
        if query == "slow":
            held["slow"] = found
        return found
    if method == "suggestChannels":
        return [] if not args[0].startswith("C") else [c for c in CHANNELS if c["name"].startswith(args[1])]


fb.install(main, respond)


def key(*keys):
    subprocess.run(["xdotool", "key", "--delay", "40", *keys], env=dict(os.environ))


def type_text(text):
    subprocess.run(["xdotool", "type", "--delay", "30", text], env=dict(os.environ))


def shown(o):
    """The suggestion rows' main labels, or None when the list is hidden."""
    if not o.suggestions.get_visible():
        return None
    names = []
    for row in o.suggestions.listbox.get_children():
        texts = [w.get_text() for w in row.get_child().get_children() if isinstance(w, main.Gtk.Label)]
        names.append(texts[0] if row.item.get("kind") == "person" else " ".join(texts))
    return names


def calls(method):
    return [args for m, args in fb.CALLS if m == method]


def wait(o):
    pass


def start(o):
    o._focus_reply()
    o.reply.set_text("")
    type_text("hi @fr")


def people(o):
    assert shown(o) == ["Friend 1", "Friend 2", "Friend 3"], shown(o)
    assert calls("suggestPeople")[-1] == ("F1", "fr")
    key("Down", "Tab")


def picked(o):
    assert o.reply.get_text() == "hi @friend2 ", repr(o.reply.get_text())
    assert shown(o) is None, "picking closes the list"
    print("'@fr' suggests people; ↓ then Tab inserts '@friend2 '", flush=True)
    type_text("and #")


def no_channels_in_dm(o):
    assert shown(o) is None, "a DM has no channels to suggest"
    key("BackSpace")
    type_text("me@x")


def no_mid_word(o):
    assert shown(o) is None and calls("suggestPeople")[-1][1] != "x", "an @ inside a word isn't a mention"
    print("'#' in a DM and 'me@x' suggest nothing", flush=True)
    o.reply.set_text("")
    o._open_conversation("C1")


def in_channel(o):
    o._focus_reply()
    type_text("see #me")


def channels(o):
    assert shown(o) == ["# memes"], shown(o)
    key("Return")


def channel_picked(o):
    assert o.reply.get_text() == "see #memes ", repr(o.reply.get_text())
    assert not calls("send"), "Enter picked the suggestion; it didn't send"
    print("'#me' suggests #memes; Enter inserts it (and doesn't send)", flush=True)
    type_text("@f")


def esc(o):
    assert shown(o), "suggestions for '@f'"
    key("Escape")


def esc_closed(o):
    assert shown(o) is None and o.win.get_visible(), "Esc closes the list, not the panel"
    assert o.reply.get_text() == "see #memes @f"
    # An answer for an earlier query arriving late is ignored: ask for "slow", then type on before it shows.
    o._suggest_mentions("@", "slow", 0)
    o._suggest_mentions("@", "friend3", 0)


def stale(o):
    assert shown(o) == ["Friend 3"], f"only the latest query's answer shows: {shown(o)}"
    o.suggestions.hide()
    o.reply.set_text("")
    type_text("hey @friend1")


def tab(o):
    key("Tab")


def send(o):
    assert o.reply.get_text() == "hey @friend1 ", repr(o.reply.get_text())
    key("Return")


def sent(o):
    assert calls("send")[-1][1] == "hey @friend1", calls("send")[-1]
    print("Esc closes the list; a late answer is ignored; Enter sends 'hey @friend1' (a mention in Discord)",
          flush=True)
    type_text(":sk")


def emoji_still(o):
    assert shown(o) == ["💀 :skull:"], shown(o)
    print("':' emoji suggestions still work", flush=True)


fb.run_steps(main, [wait, start, wait, people, wait, picked, wait, no_channels_in_dm, wait, no_mid_word, wait,
                    in_channel, wait, channels, wait, channel_picked, wait, esc, wait, esc_closed, wait, stale,
                    wait, tab, wait, send, wait, sent, wait, emoji_still], interval_ms=600)
