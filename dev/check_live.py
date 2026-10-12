"""Check: changes Vesktop reports show at once, even one arriving while the chat is still being read."""

import threading
import time
from concurrent.futures import Future

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

fb.MESSAGES[:] = [fb.msg(i, f"message {i}") for i in range(10)]
fb.install(main)

# Make reading a chat slow (0.6 s), like a busy Vesktop, so a change can arrive mid-read.
reads = []
fast_call = main.VesktopBridge.call


def slow_call(self, method, *args, timeout=10):
    if method != "messages":
        return fast_call(self, method, *args, timeout=timeout)
    reads.append(time.monotonic())
    answer = fast_call(self, method, *args).result()  # what Vesktop has at the moment it's asked
    future = Future()
    threading.Timer(0.6, lambda: future.set_result(answer)).start()
    return future


main.VesktopBridge.call = slow_call
mark = {}


def newest(o, n=2):
    return [k[1][-2:] for k in o.blocks if k[0] == "msg"][-n:]


def arrive(o):
    mark["reads"] = len(reads)
    fb.MESSAGES.append(fb.msg(50, "live one", author="You"))
    fb.push_chats("F1")  # starts a read


def arrive_mid_read(o):
    fb.MESSAGES.append(fb.msg(51, "live two", author="You"))
    fb.push_chats("F1")  # the first read is still under way


def both_shown(o):
    print(f"newest shown: {newest(o)}, reads: {len(reads) - mark['reads']}", flush=True)
    assert newest(o) == ["50", "51"], "both live messages shown"
    assert len(reads) - mark["reads"] == 2, "one read, plus one more for the change during it"


def other_chat(o):
    mark["reads"] = len(reads)
    fb.push_chats("F9")


def not_reread(o):
    assert len(reads) == mark["reads"], "a change elsewhere doesn't re-read the open chat"
    o.hide()
    fb.push_chats("F1")


def wait(o):
    pass


def friend_online(o):
    o.show()
    mark["overviews"] = sum(1 for name, _ in fb.CALLS if name == "overview")
    fb.FRIENDS[4]["status"] = "offline"  # e.g. Friend 5 went offline
    for _ in range(5):
        fb.push_lists()  # a burst of changes


def lists_refreshed(o):
    reads = sum(1 for name, _ in fb.CALLS if name == "overview") - mark["overviews"]
    row = o.row_cache[("friend", "F5")]
    print(f"a burst of 5 list changes: sidebar re-read {reads} time(s); Friend 5 shows {row.data['status']}",
          flush=True)
    assert reads == 1 and row.data["status"] == "offline", "one prompt refresh for the whole burst"


def open_friend(o):
    o._open_conversation("F5")  # Friend 5, who just went offline


def header_shows_status(o):
    assert o.header_avatar.status == "offline", o.header_avatar.status
    fb.FRIENDS[4]["status"] = "dnd"  # now Do Not Disturb
    fb.push_lists()


def header_follows(o):
    dot = o.header_avatar.status
    print(f"open DM with Friend 5: header picture's status dot went offline -> {dot}", flush=True)
    assert o.header_avatar.status == "dnd", "the header's dot changes live, like the list's"


def activity_set(o):
    fb.FRIENDS[4]["activity"] = "🍕 brb dinner"  # Friend 5 sets a custom status...
    fb.FRIENDS[6].update(preview=None, activity="Playing Valorant")  # ...Friend 7 (no message loaded) plays
    fb.push_lists()


def activity_shown(o):
    header = o.typing.get_text()
    row = o.row_cache[("friend", "F7")]
    listed = row.preview.get_text() if row.preview.get_visible() else ""
    dim = row.preview.get_style_context().has_class("activity")
    print(f"header under Friend 5's name: {header!r}; list line for Friend 7 (no preview): {listed!r} (dim {dim})",
          flush=True)
    assert header == "🍕 brb dinner" and listed == "Playing Valorant" and dim
    o._set_typing(["Friend 5"])  # typing takes the line over...
    assert o.typing.get_text() == "Friend 5 is typing…"
    o._set_typing([])  # ...and gives it back
    assert o.typing.get_text() == "🍕 brb dinner"


def muted_elsewhere(o):
    fb.VOICE["mute"] = True  # muted with Discord's own button
    fb.push_voice()


def panel_caught_up(o):
    on = o.mute_btn.get_style_context().has_class("on")
    state = "red" if on else "NOT updated"
    print(f"muted in Discord itself: the panel's Mute button is {state} right away", flush=True)
    assert on, "a mute change made elsewhere shows at once"
    o._voice("toggleMute")  # Ctrl+M straight after: unmutes, starting from the right state


def unmuted(o):
    on = o.mute_btn.get_style_context().has_class("on")
    print(f"then Ctrl+M: Discord muted={fb.VOICE['mute']}, button {'red' if on else 'normal'}", flush=True)
    assert not fb.VOICE["mute"] and not on, "button and Discord agree"


def hidden(o):
    assert len(reads) == mark["reads"], "nothing is read while the panel is hidden"
    print("changes elsewhere and while hidden: no reads", flush=True)


fb.run_steps(main, [arrive, arrive_mid_read, wait, wait, wait, both_shown,
                    other_chat, wait, not_reread, wait, hidden, friend_online, wait, wait, wait, wait,
                    lists_refreshed, open_friend, wait, header_shows_status, wait, wait, wait, wait,
                    header_follows, activity_set, wait, wait, wait, wait, activity_shown, muted_elsewhere, wait,
                    panel_caught_up, wait, unmuted], interval_ms=300)
