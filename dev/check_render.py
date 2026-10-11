"""Check: when a chat changes, only the changed message is redrawn (images and GIFs elsewhere keep playing)."""

import tempfile

from PIL import Image

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

media_dir = tempfile.mkdtemp(prefix="vdo-check-")
Image.new("RGB", (160, 90), (200, 120, 60)).save(f"{media_dir}/still.png")
frames = [Image.new("RGB", (60, 40), color) for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
frames[0].save(f"{media_dir}/anim.gif", save_all=True, append_images=frames[1:], duration=100, loop=0)


def media(name, kind, w, h):
    url = f"file://{media_dir}/{name}"
    return {"kind": kind, "src": url, "full": url, "w": w, "h": h, "spoiler": False}


AUTHORS = ["Friend 1", "Friend 1", "You", "Friend 1", "You", "You", "Friend 1"]
fb.MESSAGES[:] = [fb.msg(i, f"message number {i}", author=AUTHORS[i % len(AUTHORS)]) for i in range(60)]
fb.MESSAGES[40] = fb.msg(40, "a picture", media=[media("still.png", "image", 160, 90)])
fb.MESSAGES[41] = fb.msg(41, "", media=[media("anim.gif", "anim", 60, 40)])
CALL = {"icon": "📞", "text": "Friend 1 started a call that lasted 4 minutes."}
fb.MESSAGES[43] = fb.msg(43, "", system=CALL)
FORWARDED = {"content": "see you at 9", "ast": [fb.text("see you at 9")], "media": [], "extras": []}
fb.MESSAGES[44] = fb.msg(44, "", author="You", forwarded=FORWARDED)
fb.MESSAGES[46] = fb.msg(46, "", author="You", poll={"question": "Which map?", "total": 3, "closed": False, "expiry": None,
                                       "answers": [{"text": "Dust", "emoji": "", "count": 2, "me": True},
                                                   {"text": "Inferno", "emoji": "", "count": 1, "me": False}]})
fb.MESSAGES[47] = fb.msg(47, "Rolled a 17", author="DiceBot", command={"user": "Friend 1", "name": "roll"})
OLDER = [fb.msg(i - 100, f"older message {i}") for i in range(10)]
fb.install(main, lambda method, args: {"messages": [dict(m) for m in OLDER], "more": False}
           if method == "olderMessages" else None)

seen = {}


def widgets(o):
    return {k: id(w) for k, w in o.blocks.items()}


def rebuilt(o):
    """Message ids whose rows were (re)built since the last call, and how many blocks were kept."""
    now = widgets(o)
    built = sorted(k[1][-2:] for k, i in now.items() if k[0] == "msg" and seen.get(k) != i)
    kept = sum(1 for k, i in now.items() if seen.get(k) == i)
    seen.clear()
    seen.update(now)
    assert o.msg_box.get_children() == list(o.blocks.values()), "pane out of order"
    return built, kept


def change(fn):
    def step(o):
        fn()
        o._load_messages()
    return step


def expect(label, ids):
    def step(o):
        built, kept = rebuilt(o)
        print(f"{label}: rebuilt {built}, kept {kept}", flush=True)
        assert built == ids, f"expected {ids} rebuilt"
    return step


seen_views = []  # the media widgets as first drawn


def first(o):
    call = next(w for k, w in o.blocks.items() if k[0] == "msg" and k[1] == str(10**18 + 43))
    menu = [item[0] if item else "---" for item in o._message_items(fb.MESSAGES[43])]
    print(f"call message: drawn as a system line ({type(call.get_children()[0]).__name__} icon), menu {menu}",
          flush=True)
    assert call.get_children()[0].get_text() == "📞" and menu == ["Copy message link", "---", "Open in Vesktop"]

    def texts(widget):
        own = [widget.get_text()] if isinstance(widget, main.Gtk.Label) else []
        kids = widget.get_children() if isinstance(widget, main.Gtk.Container) else []
        return own + [t for kid in kids for t in texts(kid)]
    def row(i):
        return next(w for k, w in o.blocks.items() if k[0] == "msg" and k[1] == str(10**18 + i))
    shown = {i: " | ".join(texts(row(i))) for i in (44, 46, 47)}
    print(f"forwarded: {shown[44]!r}\npoll: {shown[46]!r}\nbot command: {shown[47]!r}", flush=True)
    assert "↱ Forwarded" in shown[44] and "see you at 9" in shown[44]
    assert "Which map?" in shown[46] and "2 · 67%" in shown[46] and "3 votes" in shown[46]
    assert "Friend 1 used /roll" in shown[47]
    assert not any("couldn't be shown" in s for s in shown.values())
    for i in (44, 46):  # your own forward / poll: Discord can't edit those, so no Edit
        menu = [item[0] for item in o._message_items(fb.MESSAGES[i]) if item]
        assert "Edit message" not in menu and "Delete message" in menu, menu
    print("your own forward and poll: no Edit message, Delete still there", flush=True)
    rebuilt(o)
    seen_views[:] = [id(v) for v in o.media_views]
    assert len(seen_views) == 2, "both media items shown"


def same_media(o):
    assert [id(v) for v in o.media_views] == seen_views, "image / GIF widgets were rebuilt"
    print("image and GIF widgets kept", flush=True)


def edit(i, new):
    fb.MESSAGES[i] = dict(fb.MESSAGES[i], content=new, ast=[fb.text(new)], edited=True)


def react(i):
    fb.MESSAGES[i] = dict(fb.MESSAGES[i], reactions=[{"emoji": {"char": "👍", "name": "thumbsup"}, "count": 1,
                                                       "me": True}])


def older_loaded(o):
    built, _ = rebuilt(o)
    print(f"older loaded: rebuilt {built}", flush=True)
    assert len(built) == 10, "only the ten older messages are new"
    assert o.history_label.get_text() == "This is the start of the conversation."


fb.run_steps(main, [
    first,
    change(lambda: fb.MESSAGES.append(fb.msg(60, "new, same author", author=fb.MESSAGES[-1]["author"]))),
    expect("new message, same author", ["60"]),
    same_media,
    change(lambda: fb.MESSAGES.append(fb.msg(61, "new, other author", author="Someone"))),
    expect("new message, other author", ["61"]),
    change(lambda: edit(45, "EDITED")),
    expect("edit", ["45"]),
    change(lambda: react(50)),
    expect("reaction", ["50"]),
    change(lambda: None),
    expect("nothing changed", []),
    same_media,
    lambda o: (o.hide(), o.show()),
    expect("panel closed and reopened", []),
    same_media,
    lambda o: o._close_conversation(),
    lambda o: o._open_conversation("F1"),
    expect("chat closed with ← and reopened", []),
    same_media,
    lambda o: o._load_older(),
    older_loaded,
])
