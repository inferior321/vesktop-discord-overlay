"""Make the README screenshot (assets/screenshot.png) with the fake Vesktop: invented people, conversation, avatars
and images, nothing real. Run it through dev/screenshot.sh, which provides a private display."""

import os
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

OUT = Path(__file__).resolve().parent.parent / "assets" / "screenshot.png"
media_dir = Path(tempfile.mkdtemp(prefix="vdo-shot-"))


def avatar(name, top, bottom, shape):
    """A simple made-up profile picture: a gradient disc with a light shape on it."""
    size = 128
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        mix = y / size
        draw.line([(0, y), (size, y)], fill=tuple(int(a + (b - a) * mix) for a, b in zip(top, bottom)))
    light = (255, 255, 255)
    if shape == "circle":
        draw.ellipse([38, 30, 90, 82], fill=light)
        draw.ellipse([22, 84, 106, 150], fill=light)
    elif shape == "star":
        draw.polygon([(64, 22), (76, 52), (108, 54), (82, 74), (92, 106), (64, 88), (36, 106), (46, 74), (20, 54),
                      (52, 52)], fill=light)
    elif shape == "wave":
        for i in range(4):
            draw.arc([10, 30 + i * 18, 118, 70 + i * 18], 200, 340, fill=light, width=6)
    else:
        draw.rectangle([36, 36, 92, 92], fill=light)
    path = media_dir / f"{name}.png"
    img.save(path)
    return f"file://{path}"


def scenery():
    """A made-up game-map picture: sky, sun, hills, a lake."""
    w, h = 720, 400
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        mix = y / h
        draw.line([(0, y), (w, y)], fill=(int(255 - 120 * mix), int(140 - 60 * mix), int(90 + 80 * mix)))
    draw.ellipse([470, 90, 590, 210], fill=(255, 214, 140))
    far_hills = [(0, 300), (140, 170), (300, 290), (460, 160), (720, 310), (720, 400), (0, 400)]
    near_hills = [(0, 340), (200, 250), (380, 330), (560, 240), (720, 330), (720, 400), (0, 400)]
    draw.polygon(far_hills, fill=(56, 48, 92))
    draw.polygon(near_hills, fill=(34, 30, 64))
    draw.rectangle([0, 350, w, h], fill=(70, 90, 150))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    path = media_dir / "map.png"
    img.save(path)
    return {"kind": "image", "src": f"file://{path}", "full": f"file://{path}", "w": w, "h": h, "spoiler": False}


PEOPLE = {
    "Maya": avatar("maya", (255, 120, 150), (170, 70, 210), "circle"),
    "Jordan": avatar("jordan", (80, 200, 170), (40, 120, 200), "wave"),
    "Priya": avatar("priya", (255, 190, 90), (240, 110, 70), "star"),
    "Sam": avatar("sam", (120, 140, 255), (70, 70, 190), "square"),
    "Chris": avatar("chris", (150, 220, 110), (60, 150, 90), "circle"),
    "Nina": avatar("nina", (250, 150, 210), (200, 90, 140), "star"),
    "Theo": avatar("theo", (190, 190, 200), (100, 100, 120), "wave"),
    "Kai": avatar("kai", (110, 190, 255), (90, 100, 230), "star"),
}
SQUAD = avatar("squad", (255, 160, 80), (210, 70, 90), "square")
RAID = avatar("raid", (90, 90, 110), (40, 40, 60), "star")


def friend(cid, name, preview, minutes_ago, status="online", unread=False, mentions=0, typing=False, by=None):
    card = fb.card(cid, name, unread=unread, mentions=mentions, status=status)
    card.update(icon=PEOPLE.get(name, SQUAD), typing=typing, last=time.time() * 1000 - minutes_ago * 60_000,
                preview={"author": by or name, "self": by == "You", "text": preview})
    return card


fb.FRIENDS[:] = [
    friend("F1", "Maya", "gg everyone 😄", 1),
    friend("F2", "Jordan", "omw, 5 min", 6, status="idle", unread=True, mentions=2, typing=True),
    friend("F3", "Weekend Squad", "who's bringing snacks?", 18, status=None, unread=True, by="Priya"),
    friend("F4", "Priya", "that boss fight was unreal", 45, status="dnd", by="You"),
    friend("F5", "Sam", "sent the clip 🎬", 120, status="offline"),
    friend("F6", "Chris", "ok see you saturday", 300),
    friend("F7", "Nina", "lol same", 1440, status="idle"),
    friend("F8", "Theo", "thanks!", 2880, status="offline"),
]
fb.SERVERS[:] = [dict(fb.card("S1", "Weekend Raid", unread=True), icon=RAID)]
fb.VOICE.update(channel="Squad Lounge", status="online", me={"name": "Kai", "avatar": PEOPLE["Kai"]})

T = fb.text
MAP = scenery()


def said(i, author, parts, minutes_ago, **extra):
    m = fb.msg(i, "".join(p["v"] if p["t"] == "text" else p["c"][0]["v"] for p in parts), author=author,
               avatar=PEOPLE.get(author if author != "You" else "Kai"), **extra)
    m.update(ast=parts, time=time.time() * 1000 - minutes_ago * 60_000)
    if author == "You":
        m["author"] = "Kai"
    return m


fb.MESSAGES[:] = [
    said(1, "Maya", [T("anyone up for ranked tonight? 🎮")], 52),
    said(2, "You", [T("yes!! after dinner")], 50),
    said(3, "Maya", [{"t": "strong", "c": [T("8pm")]}, T(" then. bring your A game")], 49),
    said(4, "Maya", [T("also the new map just dropped")], 48, media=[MAP]),
    said(5, "You", [T("that looks unreal, the lake level? 👀")], 46,
         reply={"id": str(10**18 + 4), "author": "Maya", "text": "also the new map just dropped"},
         reactions=[{"emoji": {"char": "🔥", "name": "fire"}, "count": 3, "me": True},
                    {"emoji": {"char": "👀", "name": "eyes"}, "count": 1, "me": False}]),
    fb.msg(6, "", author="Maya", avatar=PEOPLE["Maya"],
           system={"icon": "📞", "text": "Maya started a call that lasted 42 minutes."}),
    said(7, "Maya", [T("gg everyone 😄 same time tomorrow?")], 1,
         reactions=[{"emoji": {"char": "😂", "name": "joy"}, "count": 2, "me": False},
                    {"emoji": {"char": "👍", "name": "thumbsup"}, "count": 3, "me": True}]),
]
fb.MESSAGES[5]["time"] = time.time() * 1000 - 44 * 60_000
def chat(method, args):
    """Every chat opens as the conversation with Maya."""
    if method == "messages":
        return {"id": args[0], "name": "Maya", "place": "Direct Message", "icon": PEOPLE["Maya"], "guildId": None,
                "typing": [], "firstUnreadId": None, "messages": [dict(m) for m in fb.MESSAGES]}


fb.install(main, chat)


def shoot(o):
    from Xlib import X, display
    win = o.win.get_window()
    x, y = win.get_origin()[1:]
    w, h = win.get_width(), win.get_height()
    root = display.Display(os.environ["DISPLAY"]).screen().root
    raw = root.get_image(x, y, w, h, X.ZPixmap, 0xffffffff).data
    Image.frombytes("RGB", (w, h), raw, "raw", "BGRX").save(OUT)
    print(f"saved {OUT} ({w}x{h})", flush=True)


def wait(o):
    pass


fb.run_steps(main, [wait, wait, wait, lambda o: o._focus_list(), wait, shoot], interval_ms=800)
sys.exit(0)
