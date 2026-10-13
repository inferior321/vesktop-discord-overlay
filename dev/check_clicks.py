"""Check: clicks with a real mouse (xdotool). Picking a reaction in the emoji picker right above a GIF (a looping
video, as Discord sends most GIFs) doesn't also open the GIF; media open only on a whole
click (pressed and released on them); sliding off an emoji or a GIF before letting go cancels; F1's shortcut
list closes on any click."""

import os
import subprocess
import tempfile

import fakebridge as fb
import vesktop_discord_overlay.overlay as main
from vesktop_discord_overlay.gtk import Gst

# A 2-second test-pattern GIF video, made with GStreamer.
media_dir = tempfile.mkdtemp(prefix="vdo-check-")
GIF = f"{media_dir}/gif.mp4"
maker = Gst.parse_launch("videotestsrc num-buffers=20 ! video/x-raw,width=360,height=280,framerate=10/1 "
                         f"! avenc_mpeg4 ! mp4mux ! filesink location={GIF}")
maker.set_state(Gst.State.PLAYING)
maker.get_bus().timed_pop_filtered(10 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
maker.set_state(Gst.State.NULL)
URL = f"file://{GIF}"
# A big GIF at the bottom of the chat: where the emoji picker opens over the messages.
fb.MESSAGES[:] = [fb.msg(i, f"message number {i}") for i in range(30)]
fb.MESSAGES.append(fb.msg(30, "", media=[{"kind": "video", "src": URL, "poster": None, "full": URL, "w": 360,
                                          "h": 280, "spoiler": False}]))
EMOJI = [{"name": f"e{i}", "char": chr(0x1F600 + i), "names": [f"e{i}"]} for i in range(64)]
fb.install(main, lambda method, args: {"categories": [{"id": "people", "emojis": EMOJI}]}
           if method == "emojiCatalog" else None)


def mouse(*args):
    subprocess.run(["xdotool", *args], env=dict(os.environ))


def click(x, y):
    """A click like a person's: the button stays down a moment (xdotool's own "click" is instant, too fast to
    show what happens when the press makes something vanish before the release)."""
    mouse("mousemove", str(x), str(y), "mousedown", "1", "sleep", "0.15", "mouseup", "1")


def screen_point(o, widget, x, y):
    """Where (x, y) inside a widget is on the screen."""
    wx, wy = widget.translate_coordinates(o.win, x, y)
    ox, oy = o.win.get_window().get_origin()[1:]
    return int(ox + wx), int(oy + wy)


def inside(o, widget, point):
    x, y = screen_point(o, widget, 0, 0)
    alloc = widget.get_allocation()
    return x <= point[0] < x + alloc.width and y <= point[1] < y + alloc.height


def gif(o):
    """The GIF's widget (looked up each time: a reaction redraws its message)."""
    return next(v for v in o.media_views if v.item["src"] == URL)


def reactions():
    return [m for m in fb.CALLS if m[0] == "react"]


def wait(o):
    pass


def open_picker(o):
    o._open_reaction_picker(dict(fb.MESSAGES[-1]))


def click_emoji(o):
    grid = o.picker.emoji_grid
    shown_gif = gif(o)
    centers = [screen_point(o, grid, x + grid.CELL // 2, y + grid.CELL // 2) for x, y in grid.cells]
    scroll = grid.get_parent().get_parent()
    shown = [p for p in centers if inside(o, scroll, p)]  # (in the grid's visible part)
    point = next((p for p in shown if inside(o, shown_gif, p)), None)
    assert point, "the test needs the GIF right under an emoji"
    click(*point)


def picked_only(o):
    assert len(reactions()) == 1, f"the emoji was picked: {reactions()}"
    assert not o.picker.get_visible(), "the picker closed"
    assert not o.viewer.get_visible(), "the GIF under the emoji didn't open"
    print("clicked an emoji right above a GIF: reaction added, GIF not opened", flush=True)
    o._open_reaction_picker(dict(fb.MESSAGES[-1]))


def slide_off_emoji(o):
    grid = o.picker.emoji_grid
    cx, cy = grid.cells[0]
    x, y = screen_point(o, grid, cx + grid.CELL // 2, cy + grid.CELL // 2)
    sx, sy = screen_point(o, o.picker.search, 10, 10)
    mouse("mousemove", str(x), str(y), "mousedown", "1", "mousemove", str(sx), str(sy), "mouseup", "1")


def slid_off(o):
    assert len(reactions()) == 1 and o.picker.get_visible(), "sliding off the emoji before letting go: no pick"
    print("pressed an emoji, slid off, let go: nothing picked, picker still open", flush=True)
    o._close_picker()


def slide_off_gif(o):
    x, y = screen_point(o, gif(o), 30, 30)
    mouse("mousemove", str(x), str(y), "mousedown", "1", "mousemove", str(x), str(y - 400), "mouseup", "1")


def gif_not_opened(o):
    assert not o.viewer.get_visible(), "pressed on the GIF, let go elsewhere: not opened"
    click(*screen_point(o, gif(o), 30, 30))


def gif_opened(o):
    assert o.viewer.get_visible(), "a whole click on the GIF opens it"
    print("a GIF opens on a whole click only (pressed and released on it)", flush=True)
    o.viewer.close()


def gif_playing(o):
    assert gif(o).video is not None, "the GIF plays as a video (the case to test)"


def help_open(o):
    o._focus_reply()
    mouse("key", "F1")


def help_shown(o):
    assert o.help.get_visible(), "F1 shows the shortcut list"
    click(*screen_point(o, o.listbox, 60, 20))  # somewhere else in the panel


def help_closed(o):
    assert not o.help.get_visible() and o.win.get_visible(), "a click closes the list (not the panel)"
    mouse("key", "F1")


def help_again(o):
    assert o.help.get_visible()
    help_widget = o.help.get_child()
    click(*screen_point(o, help_widget, 20, 20))  # on the list itself


def help_closed_again(o):
    assert not o.help.get_visible(), "a click on the list closes it too"
    print("F1's shortcut list closes on a click, anywhere", flush=True)


fb.run_steps(main, [wait, wait, gif_playing, open_picker, wait,
                    click_emoji, wait, picked_only, wait, slide_off_emoji, wait,
                    slid_off, wait, slide_off_gif, wait, gif_not_opened, wait, gif_opened, wait, help_open, wait,
                    help_shown, wait, help_closed, wait, help_again, wait, help_closed_again], interval_ms=700)
