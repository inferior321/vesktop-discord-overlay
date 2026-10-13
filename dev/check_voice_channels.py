"""Check: a server's voice channels in its channel list: in their category (as Discord's sidebar has them), with
who's in them; the arrows go channel to channel, → opens a voice channel's text chat, and the bottom-right button
(Ctrl+Shift+D) is "Join <channel>" for it, or Disconnect while in a call."""

from types import SimpleNamespace

import fakebridge as fb
import vesktop_discord_overlay.overlay as main


def person(pid, name, speaking=False, mute=False, me=False):
    return dict(id=pid, name=name, avatar=None, speaking=speaking, mute=mute, deaf=False, me=me)


def voice_channel(cid, name, members):
    return dict(fb.card(cid, name), preview=None, voice=True, members=members)


fb.CHANNELS[:] = fb.CHANNELS + [{"kind": "category", "id": "K1", "name": "Voice Channels", "collapsed": False,
                                 "canCollapse": True},
                                voice_channel("V1", "Lounge", [person("u1", "Friend 1", speaking=True),
                                                              person("u2", "Friend 2", mute=True)]),
                                voice_channel("V2", "Quiet Room", [])]


def channel(cid):
    return next(c for c in fb.CHANNELS if c["id"] == cid)


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
                "typing": [], "firstUnreadId": None, "messages": [dict(m) for m in fb.MESSAGES[-5:]],
                "voice": {"id": ch["id"], "name": ch["name"]}}


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
    assert ids == ["C1", "C2", "K1", "V1", "V2"], f"in Discord's order, the voice channels in their category: {ids}"
    lounge, quiet = row(o, "V1"), row(o, "V2")
    assert lounge.icons["voice"].get_visible() and not lounge.icons["text"].get_visible(), "a speaker instead of #"
    assert row(o, "C1").icons["text"].get_visible() and not row(o, "C1").icons["voice"].get_visible()
    assert not lounge.count.get_visible(), "no count without a user limit"
    assert row(o, "K1").name.get_text() == "VOICE CHANNELS" and row(o, "K1").kind == "category"
    people = texts(lounge.people)
    assert people == ["Friend 1", "speaking", "Friend 2", "muted"], people
    rings = [p.get_children()[0].get_style_context().has_class("speaking") for p in lounge.people.get_children()]
    assert rings == [True, False], rings
    assert not quiet.people.get_visible(), "an empty voice channel is a single line"
    print(f"listed {ids}; a category heading; Lounge shows {people}", flush=True)


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
    lounge = channel("V1")  # Friend 1 stops talking (new lists, as each real update brings)
    lounge["members"] = [dict(p, speaking=False) for p in lounge["members"]]
    channel("V2").update(members=[person("u3", "Friend 3")], limit=1, full=True)  # Quiet Room fills up (1 max)
    fb.push_lists()


def live(o):
    rings = [p.get_children()[0].get_style_context().has_class("speaking") for p in row(o, "V1").people.get_children()]
    assert rings == [False, False, False], f"speaking follows live: {rings}"
    assert texts(row(o, "V2").people) == ["Friend 3"], "joins show live"
    o.search.set_text("quiet")


def searched(o):
    visible = o._visible_rows()
    assert visible == [row(o, "V2")], visible
    assert not o._filter_row(row(o, "K1")), "headings hide while searching"
    print("who's in each channel updates live; searching hides the headings", flush=True)
    assert row(o, "V2").count.get_text() == "1/1" and row(o, "V2").count.get_visible()
    o._focus_search()
    o._highlight(row(o, "V2"))
    o._on_voice(dict(o.voice_state, channel=None))  # (as if not in a call, for a moment)
    assert button(o) == ("Quiet Room is full", False) and not o.call_btn.get_sensitive(), button(o)
    joins = len(fb.CALLS)
    o._call_button_pressed()
    assert not any(m == "joinVoice" for m, _ in fb.CALLS[joins:]), "a full channel can't be joined"
    print("a user limit shows as 1/1; full: a grey, unclickable 'Quiet Room is full'", flush=True)
    o._refresh_voice(skip_if_busy=False)  # back in the call
    o._focus_reply()


def disconnect(o):
    assert button(o) == ("Disconnect", False) and o.call_btn.get_sensitive(), button(o)
    o._call_button_pressed()


def left(o):
    assert ("disconnectVoice", ()) in fb.CALLS
    assert button(o) == ("Join Lounge", True), f"after leaving, Join is back for the open chat ({button(o)})"
    print("the button leaves the call, then offers Join again", flush=True)
    o.search.set_text("")
    o._focus_list()
    o._highlight(row(o, "V1"))
    assert button(o) == ("Join Lounge", True), button(o)
    o._on_key(o.win, key_event(main.Gdk.KEY_Left, ctrl=True))  # Ctrl+←: back to the DM opened first


def history_step(o):
    assert o.channel_id == "F1" and o._highlighted() is row(o, "V1"), (o.channel_id, o._highlighted())
    assert button(o) is None, f"typing in a DM: no Join, though the list still highlights a voice channel"
    o._focus_list()
    assert button(o) == ("Join Lounge", True), f"back in the list on it: Join again ({button(o)})"
    print("Join follows where you are: Ctrl+← to a DM hides it, back in the list on the channel shows it",
          flush=True)
    o._leave_server()
    o._set_tab("friends")
    o.channels = []  # as if another server's channels were open
    o._open_conversation("V2")
    o._focus_reply()


def other_server_voice(o):
    assert button(o) == ("Join Quiet Room", True), f"a voice chat from elsewhere still offers Join ({button(o)})"
    print("a voice channel's chat reached from elsewhere (not in the open list) offers Join too", flush=True)


def key_event(key, ctrl=False, shift=False):
    """A key press: a character ("d") or a key value (Gdk.KEY_Left)."""
    event = main.Gdk.Event.new(main.Gdk.EventType.KEY_PRESS)
    event.keyval = main.Gdk.unicode_to_keyval(ord(key.upper() if shift else key)) if isinstance(key, str) else key
    event.state = (main.Gdk.ModifierType.CONTROL_MASK if ctrl else 0) | (
        main.Gdk.ModifierType.SHIFT_MASK if shift else 0)
    return event


fb.run_steps(main, [wait, open_server, wait, listed, arrows, wait, opened_voice_chat, join, wait, joined, wait,
                    wait, live, wait, searched, wait, disconnect, wait, left, wait, history_step, wait, other_server_voice], interval_ms=600)
