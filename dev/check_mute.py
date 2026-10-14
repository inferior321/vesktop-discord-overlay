"""Check: muting from the list's right-click menu. Servers, channels and DMs offer 'Mute … ▸' with Discord's
durations; muted ones dim and offer 'Unmute … (until HH:MM)' (or just 'Unmute …' when muted until unmuted);
threads and forum posts have no Mute (they follow their channel); what's sent is what Discord's menu sends."""

from types import SimpleNamespace

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

fb.CHANNELS.append(dict(fb.card("T1", "a thread"), kind="thread", parentId="C1", preview=None))
fb.install(main)


def row(o, rid):
    return next(r for r in o.rows if r.data["id"] == rid)


def menu(o, r):
    """The row's right-click menu: [(text, action or [submenu items])]."""
    shown = []
    o._popup_menu = lambda items, _event: shown.extend(items) or True
    o._list_menu(o.listbox, SimpleNamespace(button=3, y=r.get_allocation().y + 5))
    del o._popup_menu
    return shown


def item(o, r, starts):
    return next(entry for entry in menu(o, r) if entry and entry[0].startswith(starts))


def dimmed(r):
    return r.get_style_context().has_class("muted")


def calls(method):
    return [args for m, args in fb.CALLS if m == method]


def wait(o):
    pass


def dm(o):
    fb.FRIENDS[1].update(unread=True, mentions=2)  # Friend 2 has pinged you...
    fb.push_lists()


def dm_counted(o):
    assert o.tab_badges["friends"].get_text() == "2" and o.tab_badges["friends"].get_visible()
    friend = row(o, "F2")
    text, durations = item(o, friend, "Mute")
    assert text == "Mute conversation" and [t for t, _ in durations] == [
        "For 15 minutes", "For 1 hour", "For 3 hours", "For 8 hours", "For 24 hours", "Until I turn it back on"]
    dict(durations)["Until I turn it back on"]()


def dm_muted(o):
    assert calls("setMuted")[-1] == ("channel", "F2", -1), calls("setMuted")
    friend = row(o, "F2")
    assert dimmed(friend), "a muted DM dims"
    assert not o.tab_badges["friends"].get_visible(), "...and once muted, its pings don't count on the Friends tab"
    text, action = item(o, friend, "Unmute")
    assert text == "Unmute conversation", text  # (until unmuted: no end time)
    print("DM: Mute conversation ▸ Until I turn it back on: dimmed; menu offers 'Unmute conversation'", flush=True)
    action()


def dm_unmuted(o):
    assert calls("setMuted")[-1] == ("channel", "F2", None) and not dimmed(row(o, "F2"))
    o._set_tab("servers")


def server(o):
    text, durations = item(o, row(o, "S1"), "Mute")
    assert text == "Mute server"
    dict(durations)["For 1 hour"]()


def server_muted(o):
    assert calls("setMuted")[-1] == ("server", "S1", 3600)
    text, _ = item(o, row(o, "S1"), "Unmute")
    assert text.startswith("Unmute server (until ") and dimmed(row(o, "S1")), text
    print(f"server: Mute server ▸ For 1 hour: dimmed; menu offers '{text}'", flush=True)
    o._activate(row(o, "S1"))


def channels(o):
    text, durations = item(o, row(o, "C2"), "Mute")
    assert text == "Mute channel"
    assert not [e for e in menu(o, row(o, "T1")) if e and "ute" in e[0]], "a thread has no Mute (follows its channel)"
    dict(durations)["For 15 minutes"]()


def channel_muted(o):
    assert calls("setMuted")[-1] == ("channel", "C2", 900) and dimmed(row(o, "C2"))
    assert item(o, row(o, "C2"), "Unmute")[0].startswith("Unmute channel (until ")
    print("channel: Mute channel ▸ For 15 minutes: dimmed; threads have no Mute", flush=True)
    o._set_muted("channel", "C1", 3)  # a mute about to end


def short_mute(o):
    assert dimmed(row(o, "C1"))
    # Discord ends the mute quietly when its time is up (no change is reported to the overlay):
    def unmute():
        next(c for c in fb.CHANNELS if c["id"] == "C1").update(muted=False, mutedSelf=False, muteEnds=None)
        return False
    main.GLib.timeout_add(2500, unmute)


def still_muted(o):
    assert dimmed(row(o, "C1")), "not yet"


def mute_ended(o):
    assert not dimmed(row(o, "C1")), "un-dimmed right when the mute ended (not at the next routine check)"
    print("a timed mute ending: the row un-dims right then", flush=True)


fb.run_steps(main, [wait, dm, wait, wait, dm_counted, wait, dm_muted, wait, dm_unmuted, wait, server, wait,
                    server_muted, wait, channels, wait, channel_muted, wait, short_mute, wait, still_muted,
                    wait, wait, wait, wait, mute_ended], interval_ms=600)
