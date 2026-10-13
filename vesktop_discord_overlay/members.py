"""The member list of the open server channel, like Discord's: click the server's name (▾) in the chat
header. Role groups, then Online (and Offline in small servers); each person with their picture and status dot,
name in their role colour, and what they're up to. More load as you scroll. Click someone: Message / Mention."""

from .config import MEMBER_AVATAR, MEMBERS_H, MEMBERS_LOAD_MARGIN, MEMBERS_W
from .gtk import Gdk, GLib, Gtk
from .media import Avatar
from .widgets import add_class, label

MEMBER_PAGE = 100  # rows asked for at a time (Discord's page size)


def count_text(n):
    return f"{n:,}" if n is not None else "?"


class MembersMixin:
    """Part of Overlay (shares its state); see overlay.py."""

    def _build_members(self, anchor):
        self.member_rows = []  # every row seen so far for the open channel (Discord forgets pages scrolled past)
        self.members_for = None  # the channel those rows are for
        self.members_up_to = MEMBER_PAGE  # rows asked for so far
        self.members_total = 0
        pop = self.members_pop = add_class(Gtk.Popover(relative_to=anchor, position=Gtk.PositionType.BOTTOM,
                                                       modal=True), "members-pop")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
        self.members_title = label("", "members-title", ellipsize=True)
        self.members_counts = label("", "members-counts")
        self.members_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroll = self.members_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_size_request(MEMBERS_W, MEMBERS_H)
        scroll.add(self.members_list)
        scroll.get_vadjustment().connect("value-changed", lambda *_: self._maybe_load_more_members())
        box.pack_start(self.members_title, False, False, 0)
        box.pack_start(self.members_counts, False, False, 0)
        box.pack_start(scroll, True, True, 0)
        pop.add(box)
        box.show_all()

    # ---------- opening ----------

    def _can_show_members(self):
        return bool(self.channel_id and self.open_guild_id)

    def _toggle_members(self):
        if self.members_pop.get_visible():
            self.members_pop.popdown()
            return
        if not self._can_show_members():
            return
        if self.members_for != self.channel_id:
            self.member_rows, self.members_for, self.members_up_to = [], self.channel_id, MEMBER_PAGE
            self.members_scroll.get_vadjustment().set_value(0)
        self.members_title.set_text(self.header_place.get_text().split(" › ")[0])
        self._render_members()
        self.members_pop.popup()
        self._load_members()

    def _load_members(self):
        channel_id = self.channel_id
        self._call("members", channel_id, self.members_up_to,
                   on_ok=lambda data: self._on_members(channel_id, data), skip_if_busy=True)

    def _on_members(self, channel_id, data):
        if channel_id != self.members_for or data is None:
            return
        # Keep every row seen: Discord only keeps the first page and the one you're at.
        rows = data["rows"]
        if len(self.member_rows) < len(rows):
            self.member_rows += [None] * (len(rows) - len(self.member_rows))
        changed = False
        for i, row in enumerate(rows):
            if row is not None and row != self.member_rows[i]:
                self.member_rows[i], changed = row, True
        self.members_total = data["total"]
        counts = []
        if data.get("online") is not None:
            counts.append(f"{count_text(data['online'])} online")
        if data.get("members") is not None:
            counts.append(f"{count_text(data['members'])} members")
        self.members_counts.set_text(" · ".join(counts))
        if changed and self.members_pop.get_visible():
            self._render_members()

    def _on_members_changed(self):
        """Vesktop: a member list changed (a page arrived, someone came online)."""
        if self.members_pop.get_visible():
            self._load_members()

    def _maybe_load_more_members(self):
        """Near the end of what's shown: ask for the next page, as Discord's list does when you scroll."""
        if not self.members_pop.get_visible() or self.members_up_to >= self.members_total:
            return
        adj = self.members_scroll.get_vadjustment()
        if adj.get_value() + adj.get_page_size() >= adj.get_upper() - MEMBERS_LOAD_MARGIN:
            self.members_up_to += MEMBER_PAGE
            self._load_members()

    # ---------- the list ----------

    def _render_members(self):
        scroll = self.members_scroll.get_vadjustment().get_value()
        for child in self.members_list.get_children():
            child.destroy()
        for row in self.member_rows:
            if row is None:
                continue
            if row["kind"] == "group":
                count = f" — {count_text(row['count'])}" if row.get("count") is not None else ""
                self.members_list.pack_start(label(f"{row['title'].upper()}{count}", "list-heading"), False, False, 6)
            else:
                self.members_list.pack_start(self._member_row(row), False, False, 0)
        if not any(self.member_rows):
            self.members_list.pack_start(label("Loading…", "member-activity"), False, False, 0)
        self.members_list.show_all()
        GLib.idle_add(self.members_scroll.get_vadjustment().set_value, scroll)

    def _member_row(self, member):
        """Picture with the status dot, name in their role colour, what they're up to; click for a menu."""
        events = add_class(Gtk.EventBox(), "member-row")
        row = Gtk.Box(spacing=10, margin=3)
        face = Avatar(self.images, MEMBER_AVATAR)
        face.set(member["avatar"], member["name"][:1].upper(), member["status"])
        row.pack_start(face, False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        name = label(member["name"] + (" 👑" if member["owner"] else "") + (" · bot" if member["bot"] else ""),
                     "member-name", ellipsize=True)
        if member.get("color"):
            name.set_markup(f'<span foreground="{member["color"]}">{GLib.markup_escape_text(name.get_text())}</span>')
        texts.pack_start(name, False, False, 0)
        if member.get("activity"):
            texts.pack_start(label(member["activity"], "member-activity", ellipsize=True), False, False, 0)
        row.pack_start(texts, True, True, 0)
        events.add(row)
        events.connect("button-press-event", lambda _w, event: event.button in (1, 3) and (
            self._member_menu(member, event) or True))
        events.connect("realize", lambda w: w.get_window().set_cursor(
            Gdk.Cursor.new_from_name(w.get_display(), "pointer")))
        return events

    def _member_menu(self, member, event):
        items = [("Message", lambda: self._message_member(member))]
        if member.get("username"):
            items.append(("Mention", lambda: self._mention_member(member)))
        self._popup_menu(items, event)

    def _message_member(self, member):
        """Your DM with them (started if you have none), opened here, ready to type."""
        self.members_pop.popdown()

        def opened(channel_id):
            self._set_tab("friends")
            self._open_conversation(channel_id)
            self._focus_reply()
        self._call("openDM", member["id"], on_ok=opened, on_err=self._show_error)

    def _mention_member(self, member):
        """@username into the reply box, at the cursor (a real mention once sent)."""
        self.members_pop.popdown()
        self._focus_reply()
        position = self.reply.get_position()
        text = self.reply.get_text()
        before = "" if position == 0 or text[position - 1] == " " else " "
        insert = f"{before}@{member['username']} "
        self.reply.set_position(self.reply.insert_text(insert, position))
