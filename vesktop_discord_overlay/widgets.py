"""Small GTK helpers, time formatting and the sidebar's friend/server/channel cards."""

import time
from datetime import datetime

from .gtk import Gdk, Gtk, Pango
from .config import CARD_AVATAR
from .media import Avatar

def add_class(widget, *names):
    ctx = widget.get_style_context()
    for name in names:
        ctx.add_class(name)
    return widget


def set_class(widget, name, on):
    ctx = widget.get_style_context()
    (ctx.add_class if on else ctx.remove_class)(name)


def label(text="", *classes, xalign=0.0, ellipsize=False):
    lbl = Gtk.Label(label=text, xalign=xalign)
    if ellipsize:
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
    return add_class(lbl, *classes)


def relative_time(ms):
    if not ms:
        return ""
    secs = time.time() - ms / 1000
    if secs < 60:
        return "now"
    if secs < 3600:
        return f"{int(secs // 60)}m"
    if secs < 86400:
        return f"{int(secs // 3600)}h"
    if secs < 7 * 86400:
        return f"{int(secs // 86400)}d"
    return datetime.fromtimestamp(ms / 1000).strftime("%b %-d")


def copy_to_clipboard(text):
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text(text, -1)
    clipboard.store()  # keep it available after the panel hides


def fill_menu(menu, items, markup=False):
    """Add menu items: (text, action), (text, action, "danger") for a red one, or None for a dividing line."""
    for entry in items:
        if entry is None:
            menu.append(Gtk.SeparatorMenuItem())
            continue
        text, action, *style = entry
        item = add_class(Gtk.MenuItem(), *style)
        text_label = Gtk.Label(xalign=0)
        text_label.set_markup(text) if markup else text_label.set_text(text)
        item.add(text_label)
        item.connect("activate", lambda _i, action=action: action())
        menu.append(item)
    menu.show_all()


def pointer_inside(widget):
    """Is the mouse over this widget right now?"""
    if not widget.get_mapped():
        return False
    x, y = widget.get_pointer()
    alloc = widget.get_allocation()
    return 0 <= x < alloc.width and 0 <= y < alloc.height


def hook_label_menus(widget, fill):
    """Selectable text has its own right-click menu; fill(label, menu) gets to fill it instead."""
    if isinstance(widget, Gtk.Label) and widget.get_selectable():
        widget.connect("populate-popup", fill)
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            hook_label_menus(child, fill)


def day_label(day):
    today = datetime.now().date()
    if day == today:
        return "Today"
    if (today - day).days == 1:
        return "Yesterday"
    return day.strftime("%B %-d, %Y")


def divider(text, css_class, label_at_end=False):
    """A full-width line with a label in the middle (date separators) or at the end (the red NEW line)."""
    box = add_class(Gtk.Box(spacing=8, margin_top=14), css_class)
    parts = [Gtk.Separator(), label(text, "sep-text")]
    if not label_at_end:
        parts.append(Gtk.Separator())
    for part in parts:
        expand = isinstance(part, Gtk.Separator)
        part.set_valign(Gtk.Align.CENTER)
        box.pack_start(part, expand, expand, 0)
    return box


def message_time(ms):
    t = datetime.fromtimestamp(ms / 1000)
    if t.date() == datetime.now().date():
        return t.strftime("%H:%M")
    return t.strftime("%b %-d, %H:%M")


class CardRow(Gtk.ListBoxRow):
    """One friend / server / channel entry in the sidebar."""

    def __init__(self, images, kind):
        super().__init__()
        self.kind = kind  # "friend" | "server" | "channel"
        self.data = None
        self.set_can_focus(False)  # keep keyboard focus in the search box
        add_class(self, "card")

        box = Gtk.Box(spacing=10)
        if kind == "channel":
            self.avatar = None
            icon = label("#", "card-hash", xalign=0.5)
            icon.set_size_request(28, -1)
            box.pack_start(icon, False, False, 0)
        else:
            self.avatar = Avatar(images, CARD_AVATAR, rounded_square=kind == "server")
            box.pack_start(self.avatar, False, False, 0)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, valign=Gtk.Align.CENTER)
        self.name = label("", "card-name", ellipsize=True)
        self.draft = label("✎", "draft-mark")  # you left an unsent message here
        self.draft.set_tooltip_text("Unsent draft")
        self.draft.set_no_show_all(True)
        name_row = Gtk.Box(spacing=6)
        name_row.pack_start(self.name, False, True, 0)
        name_row.pack_start(self.draft, False, False, 0)
        self.preview = label("", "card-preview", ellipsize=True)
        self.preview.set_no_show_all(True)
        text.pack_start(name_row, False, False, 0)
        text.pack_start(self.preview, False, False, 0)
        box.pack_start(text, True, True, 0)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
        self.time = label("", "card-time", xalign=1.0)
        self.badge = label("", "badge", xalign=0.5)
        self.badge.set_halign(Gtk.Align.END)
        self.badge.set_no_show_all(True)
        self.dot = label("●", "dot", xalign=1.0)
        self.dot.set_no_show_all(True)
        side.pack_start(self.time, False, False, 0)
        side.pack_start(self.badge, False, False, 0)
        side.pack_start(self.dot, False, False, 0)
        box.pack_start(side, False, False, 0)
        self.add(box)

    def update(self, data):
        self.data = data
        self.name.set_text(data["name"])
        set_class(self.name, "unread", data["unread"] or data["mentions"] > 0)
        set_class(self, "muted", data.get("muted", False))

        p = data.get("preview")
        if p:
            who = "You" if p["self"] else p["author"]
            where = f"#{p['channel']} · " if p.get("channel") else ""
            self.preview.set_text(f"{where}{p['text']}" if p.get("system") else f"{where}{who}: {p['text']}")
        self.preview.set_visible(bool(p))

        self.time.set_text(relative_time(data["last"]))
        mentions = data["mentions"]
        self.badge.set_text(str(mentions))
        self.badge.set_visible(mentions > 0)
        self.dot.set_visible(mentions == 0 and data["unread"] and not data.get("muted", False))

        if self.avatar:
            fallback = data.get("acronym") or data["name"][:1].upper()
            self.avatar.set(data.get("icon"), fallback, data.get("status"))
            self.avatar.set_typing(bool(data.get("typing")))

    def set_draft(self, has_draft):
        self.draft.set_visible(has_draft)

    def set_typing(self, typing):
        """Live typing updates between list refreshes (from the overlay's typing events)."""
        if self.data is not None:
            self.data["typing"] = typing
        if self.avatar:
            self.avatar.set_typing(typing)

    def matches(self, terms):
        hay = self.data["name"].lower()
        return all(t in hay for t in terms)
