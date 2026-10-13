"""Check: the panel keeps its size whatever it shows. Very long names and texts everywhere (channel / thread /
forum / post / voice names and their headers, someone typing, your custom status, the Join button, the history
note, every kind of message, the reply / edit notes) are cut short or wrapped; none may widen the window."""

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

LONG = "an extremely long name that just keeps going and going and going well past any sensible width at all"
WORD = "x" * 300  # one unbroken "word": a long link, a hash, a key smash
T = fb.text
fb.CHANNELS[:] = [{"kind": "category", "id": "K1", "name": LONG, "collapsed": False, "canCollapse": True},
                  dict(fb.card("C1", LONG), preview={"author": LONG, "self": False, "text": LONG}),
                  dict(fb.card("T1", LONG), kind="thread", parentId="C1", preview=None),
                  dict(fb.card("F1", LONG), forum=True, newPosts=3, preview=None),
                  dict(fb.card("V1", LONG), voice=True, members=[], limit=5, full=False, preview=None)]
fb.SERVERS[0]["name"] = LONG
fb.POSTS["F1"] = {"posts": [fb.post("P1", LONG, starter=LONG, replies=3, new_count=2)], "older": []}
fb.MESSAGES[:] = [fb.msg(i, f"message {i}") for i in range(20)] + [
    fb.msg(20, LONG * 3, author=LONG),
    fb.msg(21, WORD, ast=[T(WORD)]),
    fb.msg(22, "", ast=[{"t": "link", "href": "https://example.com/" + WORD, "c": [T("https://example.com/" + WORD)]}]),
    fb.msg(23, "", ast=[{"t": "codeBlock", "v": WORD + "\n" + LONG}, {"t": "inlineCode", "v": WORD}]),
    fb.msg(24, "a reply", reply={"id": str(10**18 + 21), "author": LONG, "text": WORD}),
    fb.msg(25, "", system={"icon": "📞", "text": LONG + " " + WORD}),
    fb.msg(26, "", author="You", forwarded={"content": WORD, "ast": [T(WORD)], "media": [], "extras": []}),
    fb.msg(27, WORD, command={"user": LONG, "name": WORD}),
    fb.msg(28, "", poll={"question": WORD, "total": 1, "closed": False, "expiry": None,
                         "answers": [{"text": LONG + WORD, "emoji": "", "count": 1, "me": True}]}),
    fb.msg(29, LONG, reactions=[{"emoji": {"char": "👍", "name": "thumbsup"}, "count": 123456789, "me": True}]),
    # Dozens of different reactions (a big server's announcement): they wrap.
    fb.msg(30, "we hit 10k!", reactions=[{"emoji": {"char": chr(0x1F600 + i), "name": f"e{i}"}, "count": 10 + i,
                                          "me": i % 5 == 0} for i in range(40)]),
    fb.msg(32, "", ast=[{"t": "emoji", "v": chr(0x1F600 + i)} for i in range(27)]),  # emoji-only: shown large
    fb.msg(31, "server emoji too", reactions=[{"emoji": {"id": str(10**17 + i), "name": f"custom{i}"}, "count": i,
                                               "me": False} for i in range(40)]),
]


NORMAL = [fb.msg(i, f"message {i}") for i in range(20)]
LONG_MESSAGES = fb.MESSAGES[:]
fb.MESSAGES[:] = NORMAL  # (the chat the panel opens on is ordinary: its size then is the one to keep)


def respond(method, args):
    if method == "messages" and args[0] in ("C1", "T1", "V1", "P1"):
        return {"id": args[0], "name": LONG, "place": f"{LONG} › {LONG}", "icon": None, "guildId": "S1",
                "forum": {"id": "F1", "name": LONG} if args[0] == "P1" else None,
                "voice": {"id": "V1", "name": LONG, "limit": 5, "full": True} if args[0] == "V1" else None,
                "typing": [], "firstUnreadId": None, "messages": [dict(m) for m in LONG_MESSAGES]}


fb.install(main, respond)
widths = {}


def row(o, rid):
    return next(r for r in o.rows if r.data["id"] == rid)


def measure(name):
    def step(o):
        widths[name] = (o.win.get_allocated_width(), o.win.get_allocated_height())
    return step


def wait(o):
    pass


def start(o):
    widths["start"] = (o.win.get_allocated_width(), o.win.get_allocated_height())
    o._set_tab("servers")
    o._activate(row(o, "S1"))


def channel(o):
    o._activate(row(o, "C1"))


def long_bits(o):
    o._set_typing([LONG, LONG, LONG])
    o._show_custom({"text": LONG, "emoji": {"char": "🎮", "name": "🎮"}, "expires": None})
    o._start_reply(dict(LONG_MESSAGES[21]))
    o._flash(LONG + " " + WORD, 2000)


def edit(o):
    o._cancel_reply()
    o._begin_edit(dict(LONG_MESSAGES[-1], self=True), WORD)


def voice_chat(o):
    o._cancel_edit()
    o._activate(row(o, "V1"))  # its header, and the bottom bar's "<channel> is full"


def forum(o):
    o._activate(row(o, "F1"))


def post(o):
    o._activate(row(o, "P1"))


def back(o):
    o._close_conversation()
    o._leave_forum()
    o._leave_server()


def check(o):
    start_size = widths.pop("start")
    changed = {name: size for name, size in widths.items() if size != start_size}
    assert not changed, f"the panel changed size from {start_size}: {changed}"
    print(f"the panel stayed {start_size[0]}x{start_size[1]} through {len(widths)} long-text views", flush=True)


fb.run_steps(main, [wait, start, wait, measure("server list"), channel, wait, wait, measure("long messages"),
                    long_bits, wait, measure("typing, status, reply, note"), edit, wait, measure("editing"),
                    voice_chat, wait, measure("voice chat"), forum, wait, measure("forum"), post, wait,
                    measure("post"), back, wait, measure("back out"), check], interval_ms=700)
