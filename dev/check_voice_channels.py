"""Check: a server's voice channels in its channel list: after the text channels under a "VOICE" heading, with
who's in them; the arrows go channel to channel, → opens a voice channel's text chat, and the bottom-right button
(Ctrl+Shift+D) is "Join <channel>" for it, or Disconnect while in a call."""

from types import SimpleNamespace

import fakebridge as fb
import vesktop_discord_overlay.overlay as main


def person(pid, name, speaking=False, mute=False, me=False):
    return dict(id=pid, name=name, avatar=None, speaking=speaking, mute=mute, deaf=False, me=me)


def voice_channel(cid, name, members):
    return dict(fb.card(cid, name), preview=None, voice=True, members=members)


fb.CHANNELS[:] = fb.CHANNELS + [voice_channel("V1", "Lounge", [person("u1", "Friend 1", speaking=True),
                                                              person("u2", "Friend 2", mute=True)]),
                                voice_channel("V2", "Quiet Room", [])]


def respond(method, args):
    if method == "joinVoice":  # you move into that channel (leaving any other)
        for ch in fb.CHANNELS:
            if ch.get("voice"):
                ch["members"] = [p for p in ch["members"] if not p["me"]]
                if ch["id"] == args[0]:
                    ch["members"] = ch["members"] + [person("me", "You", me=True)]
        fb.VOICE["channel"] = next(c["name"] for c in fb.CHANNELS if c["id"] == args[0])
        fb.push_voice()
        main.GLib.idle_add(lambda: fb.push_lists() or False)  # Vesktop reports the channel list changed
        return True
    if method == "messages" and args[0].startswith("V"):
        ch = next(c for c in fb.CHANNELS if c["id"] == args[0])
        return {"id": args[0], "name": "🔊 " + ch["name"], "place": "Fake Server", "guildId": "S1", "icon": None,
                "typing": [], "firstUnreadId": None, "messages": [dict(m) for m in fb.MESSAGES[-5:]]}


fb.install(main, respond)


def texts(widget):
    own = [widget.get_text()] if isinstance(widget, main.Gtk.Label) and widget.get_visible() else []
    kids = widget.get_children() if isinstance(widget, main.Gtk.Container) and widget.get_visible() else []
    return own + [t for kid in kids for t in texts(kid)]


def row(o, cid):
    return next(r for r in o.rows if r.data["id"] == cid)


def menu_items(o, r):
    """What right-clicking the row offers."""
    shown = []
    o._popup_menu = lambda items, _event: shown.extend(name for name, _ in items) or True
    event = SimpleNamespace(button=3, y=r.get_allocation().y + 5)  # a right-click on the row
    o._list_menu(o.listbox, event)
    del o._popup_menu
    return shown


def wait(o):
    pass


def open_server(o):
    o._set_tab("servers")
    o._activate(row(o, "S1"))


def listed(o):
    ids = [r.data["id"] for r in o.rows]
    assert ids == ["C1", "C2", "V1", "V2"], f"text channels, then voice channels: {ids}"
    lounge, quiet = row(o, "V1"), row(o, "V2")
    assert lounge.hash.get_text() == "🔊" and row(o, "C1").hash.get_text() == "#"
    headings = [r.get_header().get_text() if r.get_header() else None for r in o.rows]
    assert headings == [None, None, "VOICE", None], f"one VOICE heading above the voice channels: {headings}"
    people = texts(lounge.people)
    assert people == ["Friend 1", "speaking", "Friend 2", "muted"], people
    rings = [p.get_children()[0].get_style_context().has_class("speaking") for p in lounge.people.get_children()]
    assert rings == [True, False], rings
    assert not quiet.people.get_visible(), "an empty voice channel is a single line"
    print(f"listed {ids}; VOICE heading; Lounge shows {people}", flush=True)


def button(o):
    """The bottom-right call button as shown: None if hidden, else (its text, whether it's the green Join)."""
    if not o.call_btn.get_visible():
        return None
    return o.call_text.get_text(), o.call_btn.get_style_context().has_class("join")


def arrows(o):
    o._focus_list()
    o._highlight(row(o, "C2"))
    assert button(o) is None, "no call button on a text channel when you're not in a call"
    o._move(1)
    assert o._highlighted() is row(o, "V1"), "↓ from the last text channel goes to the first voice channel"
    assert button(o) == ("Join Lounge", True), button(o)
    o._move(1)
    assert o._highlighted() is row(o, "V2"), "↓ skips the people in a channel"
    assert button(o) == ("Join Quiet Room", True), button(o)
    o._move(-1)
    assert o._highlighted() is row(o, "V1")
    o._list_key("Right", None)


def opened_voice_chat(o):
    assert o.channel_id == "V1", f"→ opens the voice channel's text chat ({o.channel_id})"
    assert o.reply.has_focus(), "ready to type"
    assert not any(m == "joinVoice" for m, _ in fb.CALLS), "opening its chat doesn't join"
    print("arrows go channel to channel, the button offers Join on voice channels; → opens the chat without "
          "joining", flush=True)


def join(o):
    for cid in ("C1", "V1"):
        items = menu_items(o, row(o, cid))
        assert items == ["Mark as read", "Open in Vesktop"], f"right-click has no Join ({cid}: {items})"
    o._highlight(row(o, "C1"))
    assert button(o) == ("Join Lounge", True), f"its chat is still open: Join stays ({button(o)})"
    o._on_key(o.win, key_event("d", ctrl=True, shift=True))


def joined(o):
    assert ("joinVoice", ("V1",)) in fb.CALLS, "Ctrl+Shift+D joined"
    assert "You (you)" in texts(row(o, "V1").people), "you show in the channel"
    assert button(o) == ("Disconnect", False), button(o)
    o._highlight(row(o, "V2"))
    assert button(o) == ("Disconnect", False), f"in a call, another channel doesn't change it ({button(o)})"
    print("Ctrl+Shift+D joins the open voice channel; in the call the button is Disconnect", flush=True)
    lounge = fb.CHANNELS[2]  # Friend 1 stops talking (new lists, as each real update brings)
    lounge["members"] = [dict(p, speaking=False) for p in lounge["members"]]
    fb.CHANNELS[3]["members"] = [person("u3", "Friend 3")]  # someone joins Quiet Room
    fb.push_lists()


def live(o):
    rings = [p.get_children()[0].get_style_context().has_class("speaking") for p in row(o, "V1").people.get_children()]
    assert rings == [False, False, False], f"speaking follows live: {rings}"
    assert texts(row(o, "V2").people) == ["Friend 3"], "joins show live"
    o.search.set_text("quiet")


def searched(o):
    visible = o._visible_rows()
    assert visible == [row(o, "V2")], visible
    assert row(o, "V2").get_header() is not None, "the heading follows the search"
    print("who's in each channel updates live; search keeps the heading", flush=True)
    o._call_button_pressed()


def left(o):
    assert ("disconnectVoice", ()) in fb.CALLS
    assert button(o) == ("Join Quiet Room", True), f"after leaving, Join is back ({button(o)})"
    print("the button leaves the call, then offers Join again", flush=True)


def key_event(char, ctrl=False, shift=False):
    event = main.Gdk.Event.new(main.Gdk.EventType.KEY_PRESS)
    event.keyval = main.Gdk.unicode_to_keyval(ord(char.upper() if shift else char))
    event.state = (main.Gdk.ModifierType.CONTROL_MASK if ctrl else 0) | (
        main.Gdk.ModifierType.SHIFT_MASK if shift else 0)
    return event


fb.run_steps(main, [wait, open_server, wait, listed, arrows, wait, opened_voice_chat, join, wait, joined, wait,
                    wait, live, wait, searched, wait, left], interval_ms=600)
