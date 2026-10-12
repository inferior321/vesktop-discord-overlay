"""You, at the bottom left: your status (Online / Idle / ...) and custom status, set from the menu on your name."""

import time
from datetime import datetime, timedelta

from .config import CUSTOM_STATUS_EMOJI_H, CUSTOM_STATUS_W, VOICE_SETTLE_SECONDS
from .gtk import Gdk, GLib, Gtk
from .media import Picture
from .pickers import EmojiGrid, emoji_names, show_emoji
from .theme import STATUS_COLORS
from .widgets import add_class, label

STATUS_NAMES = {"online": "Online", "idle": "Idle", "dnd": "Do Not Disturb", "invisible": "Invisible"}

CUSTOM_STATUS_MAX = 128  # Discord's limit
# "Clear after", as Discord offers it: seconds from now, "today" (local midnight) or None (never).
CLEAR_AFTER = [("Today", "today"), ("4 hours", 4 * 3600), ("1 hour", 3600), ("30 minutes", 1800),
               ("Don't clear", None)]


def expiry(after):
    """When a status set now with this "Clear after" choice ends, in ms (None: it doesn't)."""
    if after is None:
        return None
    if after == "today":
        midnight = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(midnight.timestamp() * 1000)
    return int((time.time() + after) * 1000)


def status_emoji(entry):
    """A picker entry as a status emoji, in the form Vesktop reports it (so the two compare equal)."""
    if entry is None:
        return None
    if entry.get("id"):
        return {"id": entry["id"], "name": entry["name"],
                "url": f"https://cdn.discordapp.com/emojis/{entry['id']}.png?size=48"}
    return {"char": entry["char"], "name": entry["char"]}


def status_summary(custom):
    """One line for menus: "🎮 ranked grind tonight" (a server emoji, which can't be drawn there: ":name:")."""
    emoji = custom.get("emoji")
    mark = "" if not emoji else emoji.get("char") or f":{emoji['name']}:"
    return f"{mark} {custom['text']}".strip()


class StatusMixin:
    """Part of Overlay (shares its state); see overlay.py."""

    # ---------- your status ----------

    def _show_status(self, status):
        self.status = status
        self._show_status_line()
        self._show_me()

    def _show_me(self):
        """Your avatar (with your status as its dot) and name in the user panel."""
        name = self.me.get("name") or ""
        self.user_name.set_text(name)
        dot = "offline" if self.status == "invisible" else self.status  # invisible shows as grey, like Discord
        self.user_avatar.set(self.me.get("avatar"), name[:1].upper(), dot)

    def _status_menu(self):
        """Click your name: your custom status first (set or change it), then Online / Idle / DND / Invisible."""
        custom = GLib.markup_escape_text(status_summary(self.custom)) if self.custom else "Set custom status…"
        items = [(f"✎  {custom}", self._open_custom_status), None]
        for status, name in STATUS_NAMES.items():
            color = STATUS_COLORS.get(status, STATUS_COLORS["offline"])
            mark = "○" if status == "invisible" else "●"
            tick = "   ✓" if status == self.status else ""
            text = f'<span foreground="{color}">{mark}</span>  {name}{tick}'
            items.append((text, lambda status=status: self._set_status(status)))
        self._popup_menu(items, None, widget=self.user_panel, markup=True)

    def _set_status(self, status):
        self._show_status(status)  # at once; the next voice refresh confirms it
        self.status_set_at = time.monotonic()
        self._call("setStatus", status, on_err=self._show_error)

    # ---------- your custom status ----------

    def _build_custom_status(self):
        self.custom = None  # your custom status, as last shown (see status_emoji for the emoji's form)
        self.custom_set_at = -VOICE_SETTLE_SECONDS
        self.custom_emoji = None  # the emoji chosen in the pop-up, not yet saved

        pop = self.custom_pop = add_class(Gtk.Popover(relative_to=self.user_panel, position=Gtk.PositionType.TOP,
                                                      modal=True), "custom-pop")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=10)
        box.set_size_request(CUSTOM_STATUS_W, -1)
        box.pack_start(label("Custom status", "custom-pop-title"), False, False, 0)

        row = Gtk.Box(spacing=6)
        self.custom_emoji_btn = add_class(Gtk.Button(), "tool")
        self.custom_emoji_btn.set_can_focus(False)
        self.custom_emoji_btn.set_tooltip_text("Pick an emoji (Ctrl+E)")
        emoji_face = Gtk.Box()
        self.custom_emoji_char = label("😀")
        self.custom_emoji_pic = Picture(20, 20)
        self.custom_emoji_pic.set_no_show_all(True)
        emoji_face.pack_start(self.custom_emoji_char, False, False, 0)
        emoji_face.pack_start(self.custom_emoji_pic, False, False, 0)
        self.custom_emoji_btn.add(emoji_face)
        self.custom_emoji_btn.connect("clicked", lambda *_: self._toggle_status_emoji())
        self.custom_emoji_clear = add_class(Gtk.Button(label="✕"), "tool")
        self.custom_emoji_clear.set_can_focus(False)
        self.custom_emoji_clear.set_tooltip_text("Remove the emoji")
        self.custom_emoji_clear.connect("clicked", lambda *_: self._set_custom_emoji(None))
        self.custom_text = add_class(Gtk.Entry(), "search")
        self.custom_text.set_max_length(CUSTOM_STATUS_MAX)
        self.custom_text.set_placeholder_text("What's up?")
        self.custom_text.connect("activate", lambda *_: self._save_custom_status())
        row.pack_start(self.custom_emoji_btn, False, False, 0)
        row.pack_start(self.custom_emoji_clear, False, False, 0)
        row.pack_start(self.custom_text, True, True, 0)
        box.pack_start(row, False, False, 0)

        # The emoji chooser (😀 or Ctrl+E): the same grid and search as the reply box's picker.
        self.status_emoji_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.status_emoji_search = add_class(Gtk.Entry(), "search")
        self.status_emoji_search.set_placeholder_text("Find an emoji")
        self.status_emoji_search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "edit-find-symbolic")
        self.status_emoji_search.connect("changed", lambda *_: self._render_status_emoji())
        self.status_emoji_search.connect("activate", lambda *_: self._pick_status_emoji(
            self.status_emoji_grid.current()))
        self.status_emoji_footer = label("", "hint", ellipsize=True)
        self.status_emoji_grid = EmojiGrid(self.images, self._pick_status_emoji, lambda item: (
            self.status_emoji_footer.set_text(" ".join(f":{n}:" for n in emoji_names(item)) if item else "")))
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_size_request(-1, CUSTOM_STATUS_EMOJI_H)
        scroll.add(self.status_emoji_grid)
        self.status_emoji_grid.adjustment = scroll.get_vadjustment()
        self.status_emoji_box.pack_start(self.status_emoji_search, False, False, 0)
        self.status_emoji_box.pack_start(scroll, True, True, 0)
        self.status_emoji_box.pack_start(self.status_emoji_footer, False, False, 0)
        box.pack_start(self.status_emoji_box, False, False, 0)
        self.status_emoji = {"frecent": [], "custom": []}  # what Discord lets you use in a status

        after = Gtk.Box(spacing=8)
        after.pack_start(label("Clear after", "custom-pop-label"), False, False, 0)
        self.custom_after = Gtk.ComboBoxText()
        for text, _ in CLEAR_AFTER:
            self.custom_after.append_text(text)
        self.custom_after.set_can_focus(False)
        after.pack_start(self.custom_after, False, False, 0)
        box.pack_start(after, False, False, 0)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        clear = add_class(Gtk.Button(label="Clear"), "tool")
        save = add_class(Gtk.Button(label="Save"), "tool", "primary")
        for btn in (clear, save):
            btn.set_can_focus(False)
            buttons.pack_start(btn, False, False, 0)
        clear.connect("clicked", lambda *_: self._clear_custom_status())
        save.connect("clicked", lambda *_: self._save_custom_status())
        box.pack_start(buttons, False, False, 0)

        pop.add(box)
        pop.connect("key-press-event", self._custom_status_key)  # (an open pop-up gets keys before the window)
        box.show_all()
        self.status_emoji_box.hide()

        # Under your name: a server emoji's picture before the text (a built-in emoji is part of the text).
        self.user_status_emoji = Picture(16, 16)
        self.user_status_emoji.set_no_show_all(True)
        self.user_status_row.pack_start(self.user_status_emoji, False, False, 0)
        self.user_status_row.reorder_child(self.user_status_emoji, 0)

    # ---------- the line under your name ----------

    def _show_custom(self, custom):
        self.custom = custom
        self._show_status_line()

    def _show_status_line(self):
        """Under your name: your custom status if you have one (like Discord), otherwise Online / Idle / ..."""
        custom = self.custom
        emoji = custom and custom.get("emoji")
        picture = bool(emoji and emoji.get("id"))
        if custom:
            char = emoji.get("char") if emoji else None
            self.user_status.set_text(f"{char} {custom['text']}".strip() if char else custom["text"])
        else:
            self.user_status.set_text(STATUS_NAMES.get(self.status, self.status or ""))
        self.user_status_emoji.set_visible(picture)
        if picture:
            url = emoji["url"]

            def loaded(anim):
                still_shown = self.custom and (self.custom.get("emoji") or {}).get("url") == url
                if anim and still_shown:
                    self.user_status_emoji.set_animation(anim)
            self.images.image(url, loaded)
        self.user_panel.set_tooltip_text(
            (status_summary(custom) + "\n" if custom else "") + "Click to change your status")

    def _on_custom_status(self, custom):
        """From Vesktop (set anywhere, cleared, expired). Just after you save, trust the pop-up a moment."""
        if custom != self.custom and time.monotonic() > self.custom_set_at + VOICE_SETTLE_SECONDS:
            self._show_custom(custom)

    # ---------- the pop-up ----------

    def _open_custom_status(self):
        custom = self.custom or {}
        self.custom_text.set_text(custom.get("text", ""))
        self._set_custom_emoji(custom.get("emoji"))
        self.custom_after.set_active(0)  # Today, like Discord
        self.status_emoji_box.hide()
        self.custom_pop.popup()
        self.custom_text.grab_focus_without_selecting()
        self.custom_text.set_position(-1)

    def _set_custom_emoji(self, emoji):
        self.custom_emoji = emoji
        picture = bool(emoji and emoji.get("id"))
        self.custom_emoji_char.set_text(emoji["char"] if emoji and not picture else "😀")
        self.custom_emoji_char.set_opacity(1.0 if emoji else 0.6)
        self.custom_emoji_char.set_visible(not picture)
        self.custom_emoji_pic.set_visible(picture)
        if picture:
            self.images.image(emoji["url"], lambda anim: anim and self.custom_emoji_pic.set_animation(anim))
        self.custom_emoji_clear.set_visible(emoji is not None)

    def _toggle_status_emoji(self):
        if self.status_emoji_box.get_visible():
            self.status_emoji_box.hide()
            self.custom_text.grab_focus_without_selecting()
            return
        self.status_emoji_search.set_text("")
        self.status_emoji_box.show()
        self.status_emoji_search.grab_focus()

        def got(extra):
            self.status_emoji = extra
            self._render_status_emoji()
        if self.emoji_catalog is None:
            def got_catalog(catalog):
                self.emoji_catalog = catalog
                self._call("emojiForStatus", on_ok=got)
            self._call("emojiCatalog", on_ok=got_catalog)
        else:
            self._render_status_emoji()
            self._call("emojiForStatus", on_ok=got)  # (cheap; picks up a Nitro change or new frequent emoji)

    def _render_status_emoji(self):
        if self.emoji_catalog is not None:
            show_emoji(self.status_emoji_grid, self.status_emoji_footer, self.emoji_catalog, self.status_emoji,
                       self.status_emoji_search.get_text().strip())

    def _pick_status_emoji(self, entry):
        if entry is None:
            return
        self._set_custom_emoji(status_emoji(entry))
        self.status_emoji_box.hide()
        self.custom_text.grab_focus_without_selecting()
        self.custom_text.set_position(-1)

    def _custom_status_key(self, _pop, event):
        """Keys while the pop-up is open. Returns False for anything the text boxes should get."""
        name = Gdk.keyval_name(event.keyval) or ""
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        choosing = self.status_emoji_box.get_visible()
        if name == "Escape":
            if choosing:
                self._toggle_status_emoji()  # back to the text
            else:
                self.custom_pop.popdown()
            return True
        if ctrl and name.lower() == "e":
            self._toggle_status_emoji()
            return True
        if choosing and name in ("Up", "Down", "Left", "Right") and self.win.get_focus() is self.status_emoji_search:
            self.status_emoji_grid.move(name)
            return True
        return False  # typing, Enter (saves, or picks the highlighted emoji), Tab, ...

    def _save_custom_status(self):
        text = self.custom_text.get_text().strip()
        if not text and self.custom_emoji is None:
            self._clear_custom_status()
            return
        after = CLEAR_AFTER[max(0, self.custom_after.get_active())][1]
        custom = {"text": text, "emoji": self.custom_emoji, "expires": expiry(after)}
        self._apply_custom_status(custom)

    def _clear_custom_status(self):
        self._apply_custom_status(None)

    def _apply_custom_status(self, custom):
        self.custom_pop.popdown()
        self._show_custom(custom)  # at once; Vesktop's answer confirms it
        self.custom_set_at = time.monotonic()
        if custom and custom["emoji"]:  # Vesktop takes {char} or {id, name}
            emoji = custom["emoji"]
            custom = dict(custom, emoji={"id": emoji["id"], "name": emoji["name"]} if emoji.get("id")
                          else {"char": emoji["char"]})
        self._call("setCustomStatus", custom, on_err=self._show_error)

