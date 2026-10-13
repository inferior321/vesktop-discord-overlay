"""Check: resizing and moving the panel with its grips (real mouse drags, through xdotool), with a fake taskbar
reserving the bottom of the screen like a real one:
  ◢ (bottom right) grows / shrinks it on both sides around where it is, between the default size and
    PANEL_GROW_MAX of the screen's work area;
  ✥ (top right) moves it, but never off the screen nor under the taskbar;
both are remembered across hiding and reopening; double-clicking ◢ resets the size, ✥ the place."""

import os
import subprocess

import fakebridge as fb
import vesktop_discord_overlay.overlay as main
from vesktop_discord_overlay import state
from vesktop_discord_overlay.config import PANEL_GROW_MAX
from vesktop_discord_overlay.gtk import Gdk, Gtk

TASKBAR = 40
fb.install(main)
seen = {}


def add_taskbar():
    """A dock along the bottom that reserves its height (like Cinnamon's panel), so the work area excludes it."""
    geo = Gdk.Display.get_default().get_monitor(0).get_geometry()
    screen_w, screen_h = geo.width, geo.height
    bar = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    bar.set_type_hint(Gdk.WindowTypeHint.DOCK)
    bar.set_decorated(False)
    bar.move(0, screen_h - TASKBAR)
    bar.set_size_request(screen_w, TASKBAR)
    bar.realize()
    from Xlib import Xatom, display
    x = display.Display(os.environ["DISPLAY"])
    strut = [0, 0, 0, TASKBAR, 0, 0, 0, 0, 0, 0, 0, screen_w - 1]  # left, right, top, bottom, then their spans
    x.create_resource_object("window", bar.get_window().get_xid()).change_property(
        x.intern_atom("_NET_WM_STRUT_PARTIAL"), Xatom.CARDINAL, 32, strut)
    x.flush()
    bar.show()
    seen["screen"] = (screen_w, screen_h)
    return bar


def mouse(*args):
    subprocess.run(["xdotool", *args], env=dict(os.environ))


def grip_point(o, css_class):
    grip = next(g for g in o.grips if g.get_style_context().has_class(css_class))
    alloc = grip.get_allocation()
    x, y = grip.translate_coordinates(o.win, alloc.width // 2, alloc.height // 2)
    ox, oy = o.win.get_window().get_origin()[1:]
    return ox + x, oy + y


def drag(o, css_class, dx, dy):
    x, y = grip_point(o, css_class)
    steps = []
    for i in range(1, 6):
        # (The pointer stops at the screen's edges anyway; and xdotool would read "-5" as an option.)
        steps += ["mousemove", str(max(0, x + dx * i // 5)), str(max(0, y + dy * i // 5)), "sleep", "0.05"]
    mouse("mousemove", str(x), str(y), "mousedown", "1", "sleep", "0.3", *steps, "sleep", "0.2", "mouseup", "1")


def double_click(o, css_class):
    x, y = grip_point(o, css_class)
    mouse("mousemove", str(x), str(y), "click", "--repeat", "2", "--delay", "80", "1")


def size(o):
    return tuple(o.win.get_size())


def where(o):
    return tuple(o.win.get_position())


def inside_work_area(o):
    """Whole, and above the taskbar."""
    (x, y), (w, h), (sw, sh) = where(o), size(o), seen["screen"]
    return x >= 0 and y >= 0 and x + w <= sw and y + h <= sh - TASKBAR


def centred(o):
    (x, y), (w, h), (sw, sh) = where(o), size(o), seen["screen"]
    return abs(x - (sw - w) // 2) <= 2 and abs(y - (sh - TASKBAR - h) // 2) <= 2


def wait(o):
    pass


def start(o):
    o.hide()
    seen["taskbar"] = add_taskbar()


def reopen(o):
    o.show()


def work_area(o):
    geo = o._monitor()
    assert geo.height == seen["screen"][1] - TASKBAR, f"the work area leaves out the taskbar: {geo.height}"
    seen["default"] = size(o)
    seen["max"] = (int(geo.width * PANEL_GROW_MAX), int(geo.height * PANEL_GROW_MAX))
    assert centred(o) and inside_work_area(o), (where(o), size(o))
    print(f"work area {geo.width}x{geo.height} (a {TASKBAR}px taskbar below); opens centred in it", flush=True)
    drag(o, "resize-grip", 200, 100)


def grew(o):
    w, h = size(o)
    assert w > seen["default"][0] + 150 and h > seen["default"][1] + 60, size(o)
    assert centred(o) and inside_work_area(o)
    assert tuple(state.load()["panel_size"]) == (w, h)
    drag(o, "resize-grip", -900, -900)


def not_below_default(o):
    assert size(o) == seen["default"], f"no smaller than the default: {size(o)}"
    drag(o, "resize-grip", 2000, 2000)


def not_above_max(o):
    assert size(o) == seen["max"], f"no larger than {PANEL_GROW_MAX:.0%} of the work area {seen['max']}: {size(o)}"
    assert inside_work_area(o), "the largest size still clears the taskbar"
    print(f"◢ resizes from {seen['default']} up to {seen['max']}, centred, never under the taskbar", flush=True)
    double_click(o, "resize-grip")


def size_reset(o):
    assert size(o) == seen["default"] and not state.load().get("panel_size")
    drag(o, "move-grip", -150, -60)


def moved(o):
    assert not centred(o) and inside_work_area(o), (where(o), size(o))
    seen["moved"] = where(o)
    assert state.load().get("panel_offset"), "the place is remembered"
    print(f"✥ moved it to {where(o)}", flush=True)
    drag(o, "move-grip", 3000, 3000)  # far past the bottom-right: under the taskbar, off the screen


def held_in(o):
    (x, y), (w, h), (sw, sh) = where(o), size(o), seen["screen"]
    assert inside_work_area(o), f"never off the screen or under the taskbar: at {(x, y)} size {(w, h)}"
    assert x + w == sw and y + h == sh - TASKBAR, f"pushed into the bottom-right corner of the work area: {(x, y)}"
    drag(o, "move-grip", -3000, -3000)


def held_top_left(o):
    assert where(o) == (0, 0), f"and the top-left corner: {where(o)}"
    print("dragged far past every edge: it stops at the screen's edges and above the taskbar", flush=True)
    drag(o, "move-grip", 120, 80)


def moved_again(o):
    seen["moved"] = where(o)
    drag(o, "resize-grip", 2000, 2000)  # grow around where it is now


def centre(o):
    (x, y), (w, h) = where(o), size(o)
    return x + w // 2, y + h // 2


def grown_in_place(o):
    # (Grown to the largest size near the top-left, it had to be pushed inwards: its centre moved with it.)
    assert size(o) == seen["max"] and inside_work_area(o), (where(o), size(o))
    seen["centre"] = centre(o)
    drag(o, "resize-grip", -2000, -2000)


def shrunk_in_place(o):
    (cx, cy), (gx, gy) = centre(o), seen["centre"]
    assert size(o) == seen["default"] and abs(cx - gx) <= 2 and abs(cy - gy) <= 2, (centre(o), seen["centre"])
    seen["moved"] = where(o)
    print("◢ after a move grows and shrinks around the moved spot, still kept clear of the edges", flush=True)
    o.hide()


def reopened(o):
    (x, y), (mx, my) = where(o), seen["moved"]
    assert abs(x - mx) <= 2 and abs(y - my) <= 2, f"reopened where it was moved to: {where(o)} vs {seen['moved']}"
    double_click(o, "move-grip")


def place_reset(o):
    assert centred(o) and not state.load().get("panel_offset"), where(o)
    assert size(o) == seen["default"], "(the place reset keeps the size)"
    print("hide / reopen keeps the place; double-clicking ✥ re-centres it", flush=True)


fb.run_steps(main, [wait, wait, start, wait, reopen, wait, work_area, wait, wait, grew, wait, wait,
                    not_below_default, wait, wait, not_above_max, wait, wait, size_reset, wait, wait, moved, wait,
                    wait, held_in, wait, wait, held_top_left, wait, wait, moved_again, wait, wait, grown_in_place,
                    wait, wait, shrunk_in_place, wait, reopen, wait, reopened, wait, wait, place_reset],
             interval_ms=700)
