"""A simulated Vesktop for testing: fake friends, servers and messages. Never touches real Discord data.

install(overlay_module) swaps the real Vesktop connection for this one. Tests change FRIENDS / SERVERS /
MESSAGES (or pass respond_extra) and call push_chats() to act like Vesktop reporting a change.
"""

import json
import os
import sys
import time
import traceback
from concurrent.futures import Future
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # the repo, for vesktop_discord_overlay


def text(v):
    return {"t": "text", "v": v}


def card(cid, name, unread=False, mentions=0, muted=False, status="online"):
    return dict(id=cid, name=name, unread=unread, mentions=mentions, muted=muted, last=time.time() * 1000,
                lastId=None, preview={"author": name, "self": False, "text": "hello"}, icon=None, status=status,
                typing=False, acronym=name[:2])


def msg(i, content, author="Friend 1", **extra):
    """Message number i (higher is newer), i minutes before a fixed point a little in the past."""
    m = dict(id=str(10**18 + i), authorId=author, author=author, avatar=None, self=author == "You",
             time=time.time() * 1000 - (100 - i) * 60_000, content=content, ast=[text(content)], mentionsMe=False,
             media=[], extras=[], reply=None)
    m.update(extra)
    return m


FRIENDS = [card(f"F{i}", f"Friend {i}") for i in range(1, 15)]
SERVERS = [card("S1", "Fake Server", unread=True), card("S2", "Other Server")]
CHANNELS = [card("C1", "general"), card("C2", "memes", unread=True)]
MESSAGES = [msg(i, f"message number {i}") for i in range(40)]
OLDER = []  # what scrolling up loads, oldest first (served in batches like Discord)
VOICE = {"mute": False, "deaf": False, "channel": None, "status": "online",
         "me": {"name": "You", "avatar": None}}
CALLS = []  # (method, args) of every call the overlay made
SAVED_STATE = {}  # what state.json holds when the overlay starts (e.g. a remembered chat history)
HEALTH = []  # features the fake Vesktop reports as broken by a Discord update
overlay = None  # the running Overlay, once created


def install(main, respond_extra=None):
    """Point the overlay module at the fake Vesktop. respond_extra(method, args) can override any answer."""
    main.vesktop_running = lambda: True
    main.instance.acquire = lambda: object()
    # Remembered settings (opacity, chat history) go to a throwaway file, never the real one.
    import tempfile
    main.state.STATE_FILE = Path(tempfile.mkdtemp(prefix="vdo-test-state-")) / "state.json"
    if SAVED_STATE:
        main.state.STATE_FILE.write_text(json.dumps(SAVED_STATE))
    bridge = main.VesktopBridge
    bridge.port_open = lambda self: True

    def respond(method, args):
        CALLS.append((method, args))
        if respond_extra:
            answer = respond_extra(method, args)
            if answer is not None:
                return answer
        if method == "current":
            return {"id": "F1", "guildId": None}
        if method == "overview":
            return {"friends": [dict(f) for f in FRIENDS], "servers": [dict(s) for s in SERVERS],
                    "channels": [dict(c) for c in CHANNELS] if args and args[0] else None}
        if method == "voice":
            return dict(VOICE)
        if method == "health":
            return list(HEALTH)
        if method == "setStatus":
            VOICE["status"] = args[0]
            return True
        if method == "disconnectVoice":
            VOICE["channel"] = None
            return True
        if method == "messages":  # every chat shows MESSAGES; channels (C...) are in server S1
            channel = next((c for c in CHANNELS if c["id"] == args[0]), None)
            friend = next((f for f in FRIENDS if f["id"] == args[0]), None)
            header = ({"name": "#" + channel["name"], "place": "Fake Server", "guildId": "S1"} if channel else
                      {"name": friend["name"] if friend else args[0], "place": "Direct Message", "guildId": None})
            return {"id": args[0], "icon": None, "typing": [], "firstUnreadId": None,
                    "messages": [dict(m) for m in MESSAGES[-30:]], **header}
        if method == "olderMessages":  # (channel, before id, limit)
            before = [m for m in OLDER if int(m["id"]) < int(args[1])]
            batch = before[-args[2]:]
            return {"messages": [dict(m) for m in batch], "more": len(before) > len(batch)}
        if method in ("message", "editText", "editMessage", "deleteMessage", "react"):
            return change_message(method, args)
        if method == "channels":
            return [dict(c) for c in CHANNELS]
        if method == "emojiCatalog":
            return {"categories": [{"id": "people", "emojis": [{"name": "skull", "char": "💀", "names": ["skull"]}]}]}
        if method == "emojiForChannel":
            return {"frecent": [], "custom": []}
        if method == "gifs":
            return {"categories": []}
        return False

    def call(self, method, *args, timeout=10):
        future = Future()
        future.set_result(respond(method, args))
        return future

    bridge.call = call

    original_init = main.Overlay.__init__

    def init(self):
        global overlay
        original_init(self)
        overlay = self

    main.Overlay.__init__ = init


def find(message_id):
    """The list holding a message (MESSAGES or OLDER) and its index there."""
    for store in (MESSAGES, OLDER):
        for i, m in enumerate(store):
            if m["id"] == message_id:
                return store, i
    return None, None


def change_message(method, args):
    """Reacting, editing and deleting, applied to the fake messages (like Discord would)."""
    store, i = find(args[1])
    if store is None:
        return None
    m = store[i]
    if method == "message":
        return dict(m)
    if method == "editText":
        return m["content"]
    if method == "editMessage":
        store[i] = dict(m, content=args[2], ast=[text(args[2])], edited=True)
    elif method == "deleteMessage":
        del store[i]
    elif method == "react":
        emoji, add = args[2], args[3]
        reactions = [dict(r) for r in m.get("reactions", [])]
        same = next((r for r in reactions if r["emoji"].get("char", r["emoji"].get("id")) ==
                     emoji.get("char", emoji.get("id"))), None)
        if add and not (same and same["me"]):
            if same:
                same.update(count=same["count"] + 1, me=True)
            else:
                reactions.append({"emoji": emoji, "count": 1, "me": True})
        elif not add and same and same["me"]:
            same.update(count=same["count"] - 1, me=False)
            reactions = [r for r in reactions if r["count"] > 0]
        store[i] = dict(m, reactions=reactions)
    if overlay is not None:  # Discord would report the change; the overlay re-reads the chat
        from vesktop_discord_overlay.gtk import GLib
        GLib.idle_add(lambda: push_chats(overlay.channel_id) or False)
    return True


def push_chats(*channel_ids):
    """Act like Vesktop reporting that these chats changed (a message arrived, was edited, ...)."""
    overlay.bridge.on_event(json.dumps({"type": "chats", "channels": list(channel_ids)}))


def run_steps(main, steps, interval_ms=800, timeout_s=60):
    """Open the panel, wait for the first chat to show, then run each step(overlay) in turn, interval_ms apart.

    A step fails by raising (e.g. assert). Exits the process: 0 if every step passed, 1 otherwise.
    """
    from vesktop_discord_overlay.gtk import GLib
    pending = list(steps)
    started = time.monotonic()

    def finish(code):
        print("PASS" if code == 0 else "FAIL", flush=True)
        os._exit(code)

    def tick():
        if time.monotonic() - started > timeout_s:
            print(f"timed out with {len(pending)} step(s) left", flush=True)
            finish(1)
        if overlay is None or not overlay.blocks:
            return True  # still opening
        try:
            pending.pop(0)(overlay)
        except Exception:  # noqa: BLE001 - reported as the failure
            traceback.print_exc()
            finish(1)
        if not pending:
            finish(0)
        return True

    def open_panel():
        if overlay is None:
            return True
        overlay.show()
        return False

    GLib.timeout_add(300, open_panel)
    GLib.timeout_add(interval_ms, tick)
    main.main()
