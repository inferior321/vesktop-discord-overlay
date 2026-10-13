"""Read-only check against your real, running Vesktop (port 9222), for before a release: runs every read-only
bridge call over all your servers, channels and forums, checks the shape of each answer and how long it took,
and prints only counts and timings: no names, no messages. It never sends, marks or joins anything, and loads
nothing from Discord beyond what looking at a server does in Discord's app (its active forum posts, the first
page of a channel's member list): no messages, no older posts.

    python3 dev/smoke_real.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vesktop_discord_overlay.bridge import VesktopBridge  # noqa: E402

CARD = {"id", "name", "unread", "mentions", "last"}
KINDS = {"category": {"id", "name", "collapsed"}, "thread": CARD | {"parentId"}, "post": CARD | {"replies", "unread"}}
SLOW_MS = 250  # a call slower than this is reported
bridge = VesktopBridge(9222)
problems, slowest = [], {}


def call(method, *args):
    started = time.monotonic()
    result = bridge.call(method, *args, timeout=20).result()
    ms = (time.monotonic() - started) * 1000
    slowest[method] = max(slowest.get(method, 0), ms)
    if ms > SLOW_MS:
        problems.append(f"{method} took {ms:.0f} ms")
    return result


def need(item, keys, what):
    missing = keys - item.keys()
    if missing:
        problems.append(f"{what} lacks {sorted(missing)}")


health = call("health")
if health:
    problems.append(f"health reports: {health}")
for card in call("friends"):
    need(card, CARD, "a friend card")
servers = call("servers")
for card in servers:
    need(card, CARD, "a server card")
counts = {"servers": len(servers), "rows": 0, "forums": 0, "posts": 0, "threads": 0, "voice": 0}
for server in servers:
    rows = call("channels", server["id"])
    counts["rows"] += len(rows)
    for i, row in enumerate(rows):
        kind = row.get("kind") or ("forum" if row.get("forum") else "voice" if row.get("voice") else "text")
        need(row, KINDS.get(kind, CARD), f"a {kind} row")
        after = rows[i + 1] if i + 1 < len(rows) else None
        if kind == "category" and not row["collapsed"] and (after is None or after.get("kind") == "category"):
            problems.append("an open category heading with nothing under it")
        if kind == "thread":
            counts["threads"] += 1
        if kind == "voice":
            counts["voice"] += 1
            need(row, {"members", "limit", "full"}, "a voice row")
        if kind == "forum":
            counts["forums"] += 1
            need(row, {"newPosts"}, "a forum row")
            posts = call("posts", row["id"])
            need(posts, {"posts", "more", "loading"}, "a forum's posts")
            counts["posts"] += len(posts["posts"])
            for post in posts["posts"]:
                need(post, KINDS["post"], "a post")
    text = next((r for r in rows if not r.get("kind") and not r.get("voice") and not r.get("forum")), None)
    if text:
        members = call("members", text["id"])
        need(members, {"rows", "total", "online", "members"}, "a member list")
        for member in (m for m in members["rows"] if m and m["kind"] == "member"):
            need(member, {"id", "name", "username", "status", "color", "activity"}, "a member")
        for query in ("", "a"):
            for method in ("suggestPeople", "suggestChannels"):
                for item in call(method, text["id"], query):
                    need(item, {"kind", "id", "name", "insert"}, f"a {method} answer")
call("overview", None)  # (stop watching the last server's voice channels)
voice = call("voice")
need(voice, {"mute", "deaf", "channel", "members", "status", "custom", "me"}, "the voice state")
call("emojiForStatus")

print("counts:", counts)
print("slowest (ms):", {k: round(v) for k, v in sorted(slowest.items(), key=lambda kv: -kv[1])[:6]})
print("PASS" if not problems else "PROBLEMS:\n  " + "\n  ".join(dict.fromkeys(problems)))
sys.exit(1 if problems else 0)
