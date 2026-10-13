"""Small GTK helpers, time formatting and the sidebar's friend/server/channel cards."""

import time
from datetime import datetime

from .gtk import Gdk, Gtk, Pango
from .config import CARD_AVATAR, VOICE_AVATAR
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


def voice_person(images, person):
    """One person in a voice channel: picture (a green ring while speaking), name, muted / deafened."""
    row = Gtk.Box(spacing=10)
    ring = add_class(Gtk.Box(), "voice-face")
    set_class(ring, "speaking", person["speaking"])
    face = Avatar(images, VOICE_AVATAR)
    face.set(person["avatar"], person["name"][:1].upper())
    ring.add(face)
    row.pack_start(ring, False, False, 0)
    name = person["name"] + (" (you)" if person["me"] else "")
    row.pack_start(label(name, "voice-person", ellipsize=True), True, True, 0)
    state = "speaking" if person["speaking"] else "deafened" if person["deaf"] else "muted" if person["mute"] else ""
    if state:
        row.pack_start(add_class(label(state, "voice-state"), state), False, False, 0)
    return row


def grey_icon(icon_name, fallback):
    """A grey symbolic icon like Discord's channel icons (the fallback text if the icon theme lacks it)."""
    if Gtk.IconTheme.get_default().has_icon(icon_name):
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        icon.set_pixel_size(18)
    else:
        icon = Gtk.Label(label=fallback)
    return add_class(icon, "card-hash")


class CategoryRow(Gtk.ListBoxRow):
    """A category heading in a server's channel list, like Discord's. Clicking it collapses / expands it; the
    arrow keys skip it (see SidebarMixin._visible_rows)."""

    kind = "category"

    def __init__(self):
        super().__init__()
        self.data = None
        self.set_can_focus(False)
        self.set_selectable(False)
        add_class(self, "category")
        box = Gtk.Box(spacing=4)
        self.name = label("", "list-heading", ellipsize=True)
        self.arrow = label("", "list-heading")
        box.pack_start(self.name, False, True, 0)
        box.pack_start(self.arrow, False, False, 0)
        self.add(box)

    def update(self, data):
        self.data = data
        self.name.set_text(data["name"].upper())
        self.arrow.set_text(("▸" if data["collapsed"] else "▾") if data.get("canCollapse") else "")
        self.set_activatable(bool(data.get("canCollapse")))

    def matches(self, terms):
        return not terms  # headings hide while searching (the results are a flat list)

    def set_draft(self, _has_draft):
        pass


class CardRow(Gtk.ListBoxRow):
    """One entry in the sidebar: a friend, a server, a channel (text / voice / forum), a thread under its
    channel, or a forum post."""

    def __init__(self, images, kind):
        super().__init__()
        self.kind = kind  # "friend" | "server" | "channel" | "thread" | "post"
        self.data = None
        self.set_can_focus(False)  # keep keyboard focus in the search box
        add_class(self, "card")

        self.images = images
        self.members = None  # a voice channel's people, as last shown
        box = Gtk.Box(spacing=10)
        if kind in ("channel", "thread", "post"):
            self.avatar = None
            # Like Discord: # for a text channel, a speaker, speech bubbles for a forum, ↳ for a thread.
            self.icons = {
                "channel": {"text": label("#", "card-hash", xalign=0.5),
                            "voice": grey_icon("audio-volume-high-symbolic", "🔊"),
                            "forum": grey_icon("media-view-subtitles-symbolic", "💬")},
                "thread": {"thread": label("↳", "card-hash", xalign=0.5)},
                "post": {"post": grey_icon("text-x-generic-symbolic", "📝")},
            }[kind]
            for icon in self.icons.values():
                icon.set_size_request(28, -1)
                icon.set_no_show_all(True)
                box.pack_start(icon, False, False, 0)
            if kind == "thread":
                box.set_margin_start(16)  # under its channel
        else:
            self.avatar = Avatar(images, CARD_AVATAR, rounded_square=kind == "server")
            box.pack_start(self.avatar, False, False, 0)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, valign=Gtk.Align.CENTER)
        self.name = label("", "card-name", ellipsize=True)
        self.draft = label("✎", "draft-mark")  # you left an unsent message here
        self.draft.set_tooltip_text("Unsent draft")
        self.draft.set_no_show_all(True)
        self.count = label("", "card-time")  # a voice channel's "3/5" when it has a user limit
        self.count.set_no_show_all(True)
        name_row = Gtk.Box(spacing=6)
        name_row.pack_start(self.name, False, True, 0)
        name_row.pack_start(self.draft, False, False, 0)
        name_row.pack_start(self.count, False, False, 0)
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
        self.new = label("", "new-count", xalign=1.0)  # a forum's "3 new" posts, a post's new replies
        self.new.set_no_show_all(True)
        side.pack_start(self.time, False, False, 0)
        side.pack_start(self.new, False, False, 0)
        side.pack_start(self.badge, False, False, 0)
        side.pack_start(self.dot, False, False, 0)
        box.pack_start(side, False, False, 0)
        # A voice channel's people, under it (not rows of their own: the arrows skip them).
        self.people = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_start=38)
        self.people.set_no_show_all(True)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.pack_start(box, False, False, 0)
        outer.pack_start(self.people, False, False, 0)
        self.add(outer)

    def update(self, data):
        self.data = data
        self.name.set_text(data["name"])
        set_class(self.name, "unread", data["unread"] or data["mentions"] > 0)
        set_class(self, "muted", data.get("muted", False))

        p = data.get("preview")
        if self.kind == "post":  # who started it, how many replies
            replies = data.get("replies", 0)
            parts = [data.get("starter"), f"{replies} repl{'y' if replies == 1 else 'ies'}"]
            self.preview.set_text(" · ".join(part for part in parts if part))
            self.preview.set_visible(True)
        elif self.kind == "thread":
            self.preview.set_visible(False)  # just its name, like Discord
        elif p:
            who = "You" if p["self"] else p["author"]
            where = f"#{p['channel']} · " if p.get("channel") else ""
            self.preview.set_text(f"{where}{p['text']}" if p.get("system") else f"{where}{who}: {p['text']}")
        elif data.get("activity"):  # no message loaded: what they're up to, like Discord's DM list
            self.preview.set_text(data["activity"])
        if self.kind not in ("post", "thread"):
            set_class(self.preview, "activity", not p and bool(data.get("activity")))
            self.preview.set_visible(bool(p) or bool(data.get("activity")))
        new = data.get("newPosts") or data.get("newCount") or (1 if data.get("isNew") else 0)
        self.new.set_text("new" if data.get("isNew") and not data.get("newCount") else f"{new} new")
        self.new.set_visible(bool(new))

        self.time.set_text(relative_time(data["last"]))
        mentions = data["mentions"]
        self.badge.set_text(str(mentions))
        self.badge.set_visible(mentions > 0)
        # (A post's unread shows as a bright title only, like Discord's forum list: most posts are unread.)
        self.dot.set_visible(mentions == 0 and data["unread"] and not data.get("muted", False) and not new
                             and self.kind != "post")

        if self.kind in ("channel", "thread", "post"):
            shown = ("voice" if data.get("voice") else "forum" if data.get("forum") else "text"
                     if self.kind == "channel" else self.kind)
            for which, icon in self.icons.items():
                icon.set_visible(which == shown)
        if self.kind == "channel":
            limit = data.get("limit") or 0
            self.count.set_text(f"{len(data.get('members') or [])}/{limit}")
            self.count.set_visible(limit > 0)
            self._show_members(data.get("members") or [])
        if self.avatar:
            fallback = data.get("acronym") or data["name"][:1].upper()
            self.avatar.set(data.get("icon"), fallback, data.get("status"))
            self.avatar.set_typing(bool(data.get("typing")))

    def _show_members(self, members):
        if members == self.members:
            return
        self.members = members
        for child in self.people.get_children():
            child.destroy()
        for person in members:
            row = voice_person(self.images, person)
            row.show_all()
            self.people.pack_start(row, False, False, 0)
        self.people.set_visible(bool(members))

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
