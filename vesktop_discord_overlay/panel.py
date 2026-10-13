"""The panel's size and place: the ◢ grip (bottom right) resizes it, the ✥ grip (top right) moves it. Both are
remembered; double-clicking a grip resets what it changes. The panel always stays whole within its screen's work
area: never off the screen, nor under the taskbar or other panels."""

from .config import (NOTE_SHOW_MS, PANEL_GROW_MAX, PANEL_MAX_H, PANEL_MAX_W, PANEL_SCREEN_H, PANEL_SCREEN_W,
                     RECENTRE_DELAY_MS, RESIZE_GRIP)
from .gtk import Gdk, GLib, Gtk
from . import state
from .widgets import add_class


class PanelMixin:
    """Part of Overlay (shares its state); see overlay.py."""

    def _build_grips(self, root):
        self.panel_size = None  # (width, height) as last placed
        self.panel_pos = None  # (x, y) of its top-left corner, as last placed
        self.size_limits = None  # (min width, min height, max width, max height) on its screen
        self.grip_drag = None  # while dragging a grip: what it started from
        self.grips = [
            self._grip(root, "◢", "resize-grip", "se-resize", Gtk.Align.END,
                       "Drag to resize (double-click: default size)", self._resize_drag, self._reset_size),
            self._grip(root, "✥", "move-grip", "move", Gtk.Align.START,
                       "Drag to move (double-click: back to the centre)", self._move_drag, self._reset_position),
        ]
        # (The image viewer covers the whole panel and has its own buttons in that corner.)
        self.viewer.connect("show", lambda *_: [g.hide() for g in self.grips])
        self.viewer.connect("hide", lambda *_: [g.show() for g in self.grips])

    def _grip(self, root, mark, css_class, cursor, valign, tip, on_drag, on_reset):
        """A small handle in the panel's right-hand corner (top or bottom): drag it, or double-click it."""
        grip = add_class(Gtk.EventBox(), "grip", css_class)
        grip.set_size_request(RESIZE_GRIP, RESIZE_GRIP)
        grip.set_halign(Gtk.Align.END)
        grip.set_valign(valign)
        grip.set_tooltip_text(tip)
        grip.add(add_class(Gtk.Label(label=mark), "grip-mark"))
        grip.add_events(Gdk.EventMask.BUTTON_MOTION_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK)
        grip.connect("button-press-event", self._grip_pressed, on_reset)
        grip.connect("motion-notify-event", lambda _g, event: self._grip_dragged(event, on_drag))
        grip.connect("button-release-event", self._grip_released)
        grip.connect("realize", lambda w: w.get_window().set_cursor(
            Gdk.Cursor.new_from_name(w.get_display(), cursor)))
        root.add_overlay(grip)
        grip.show_all()
        return grip

    # ---------- placing ----------

    def _monitor(self, x=None, y=None):
        """The usable part (work area) of the screen at (x, y), or else of the one with the mouse on it: the
        screen minus the taskbar and other panels, which the panel must not go under."""
        display = Gdk.Display.get_default()
        if x is None:
            _, x, y = display.get_default_seat().get_pointer().get_position()
        return display.get_monitor_at_point(x, y).get_workarea()

    def _place_window(self):
        """On the screen with the mouse: your size (◢) or the default, at your place on it (✥) or centred. The
        default size is also the smallest (unless the screen's work area is smaller); PANEL_GROW_MAX of the work
        area the largest."""
        geo = self._monitor()
        min_w = min(PANEL_MAX_W, int(geo.width * PANEL_SCREEN_W), geo.width)
        min_h = min(PANEL_MAX_H, int(geo.height * PANEL_SCREEN_H), geo.height)
        max_w, max_h = max(min_w, int(geo.width * PANEL_GROW_MAX)), max(min_h, int(geo.height * PANEL_GROW_MAX))
        hints = Gdk.Geometry()
        hints.min_width, hints.min_height, hints.max_width, hints.max_height = min_w, min_h, max_w, max_h
        self.win.set_geometry_hints(None, hints, Gdk.WindowHints.MIN_SIZE | Gdk.WindowHints.MAX_SIZE)
        self.size_limits = (min_w, min_h, max_w, max_h)
        saved = state.load()
        w, h = saved.get("panel_size") or (min_w, min_h)
        dx, dy = saved.get("panel_offset") or (0, 0)  # its centre, from the screen's centre
        self._set_panel(geo, int(w), int(h), geo.x + geo.width // 2 + int(dx), geo.y + geo.height // 2 + int(dy))

    def _set_panel(self, geo, w, h, cx, cy):
        """Size it within the limits, centred on (cx, cy) but kept whole within the work area."""
        min_w, min_h, max_w, max_h = self.size_limits
        w, h = max(min_w, min(max_w, w)), max(min_h, min(max_h, h))
        x = max(geo.x, min(geo.x + geo.width - w, cx - w // 2))
        y = max(geo.y, min(geo.y + geo.height - h, cy - h // 2))
        self.win.resize(w, h)
        self.win.move(x, y)
        self.panel_size, self.panel_pos = (w, h), (x, y)

    def _settle_soon(self):
        """Put the panel where it should be once the window manager has applied its new size (moving together
        with a resize, some window managers apply the size but drop the move)."""
        def settle():
            if self.panel_pos:
                self.win.move(*self.panel_pos)
            return False
        GLib.timeout_add(RECENTRE_DELAY_MS, settle)

    def _panel_centre(self):
        (x, y), (w, h) = self.panel_pos, self.panel_size
        return x + w // 2, y + h // 2

    # ---------- dragging a grip ----------

    def _grip_pressed(self, _grip, event, on_reset):
        if event.button != 1:
            return False
        if event.type == Gdk.EventType._2BUTTON_PRESS:  # double-click: reset what this grip changes
            self.grip_drag = None  # (its first click began a drag; this isn't one)
            on_reset()
            self._settle_soon()
            return True
        # The grips resize / move the panel themselves (the window manager only applies each change, within the
        # limits set in _place_window), so they work the same under any window manager.
        cx, cy = self._panel_centre()
        self.grip_drag = (event.x_root, event.y_root, *self.panel_size, cx, cy, self._monitor(cx, cy))
        return True

    def _grip_dragged(self, event, on_drag):
        if self.grip_drag:
            x0, y0, w, h, cx, cy, geo = self.grip_drag
            on_drag(geo, w, h, cx, cy, int(event.x_root - x0), int(event.y_root - y0))
        return True

    def _resize_drag(self, geo, w, h, cx, cy, dx, dy):
        """◢: grow (or shrink) on both sides around where the panel is, so one drag towards the screen's corner
        reaches the largest size."""
        self._set_panel(geo, w + 2 * dx, h + 2 * dy, cx, cy)

    def _move_drag(self, geo, w, h, cx, cy, dx, dy):
        """✥: follow the mouse, staying whole within the work area of the screen the panel started on."""
        self._set_panel(geo, w, h, cx + dx, cy + dy)

    def _grip_released(self, _grip, event):
        """Let go: remember the size and place (the place as an offset from the screen's centre, so it works on
        whichever screen the panel next opens on)."""
        if event.button == 1 and self.grip_drag:
            geo = self.grip_drag[-1]
            self.grip_drag = None
            cx, cy = self._panel_centre()
            state.save(panel_size=list(self.panel_size),
                       panel_offset=[cx - (geo.x + geo.width // 2), cy - (geo.y + geo.height // 2)])
            self._settle_soon()
        return True

    def _reset_size(self):
        state.save(panel_size=None)
        self._place_window()
        self._flash("Default size", NOTE_SHOW_MS)

    def _reset_position(self):
        state.save(panel_offset=None)
        self._place_window()
        self._flash("Centred", NOTE_SHOW_MS)
