"""The sidebar: Friends / Servers tabs, search, the card list and its keys."""

from .gtk import Gdk, GLib
from .widgets import CardRow, label, set_class


class SidebarMixin:
    """Part of Overlay (shares its state); see overlay.py."""

    # ---------- sidebar ----------

    def _set_tab(self, tab):
        if tab == self.tab:
            return
        self.tab = tab
        self.search.set_text("")
        self._update_tab_buttons()
        self._render_sidebar()
        self._focus_list()

    def _update_tab_buttons(self):
        for key, btn in self.tab_buttons.items():
            set_class(btn, "active", key == self.tab)

    def _refresh_lists(self):
        server_id = self.server["id"] if self.server else None
        self._call("overview", server_id, on_ok=lambda data: self._on_overview(server_id, data), skip_if_busy=True)

    def _on_overview(self, server_id, data):
        self.friends = data["friends"]
        self.servers = data["servers"]
        if server_id == (self.server["id"] if self.server else None):
            self.channels = data["channels"] or []
        if self.server and not self.server["name"]:
            self.server["name"] = next((s["name"] for s in self.servers if s["id"] == self.server["id"]), "")
        # Tab badges, like Discord's sidebar: a red number for pings (every unread DM message counts as one),
        # otherwise a white dot if anything unmuted is unread.
        counts = {"friends": sum(f["mentions"] for f in self.friends),
                  "servers": sum(s["mentions"] for s in self.servers if not s["muted"])}
        unread = {"friends": any(f["unread"] for f in self.friends),
                  "servers": any(s["unread"] for s in self.servers if not s["muted"])}
        for key, badge in self.tab_badges.items():
            badge.set_text(str(counts[key]))
            badge.set_visible(counts[key] > 0)
            self.tab_dots[key].set_visible(counts[key] == 0 and unread[key])
        self._render_sidebar()
        self._update_header_status()  # the open DM's status dot in the header

    def _render_sidebar(self):
        if self.tab == "friends":
            self.back.hide()
            self._set_rows(self.friends, "friend")
        elif self.server is None:
            self.back.hide()
            self._set_rows(self.servers, "server")
        else:
            self.back_label.set_text(f"←  {self.server['name']}")
            self.back.show()
            self._set_rows(self.channels, "channel")

    def _set_rows(self, items, kind):
        key = (kind, self.server["id"] if kind == "channel" else None, tuple(i["id"] for i in items))
        if key == self.list_key:
            for row, item in zip(self.rows, items):
                row.update(item)
            self.listbox.invalidate_filter()
            return
        # Order or membership changed: re-add rows (reusing widgets), keeping highlight and scroll.
        same_view = self.list_key is not None and self.list_key[:2] == key[:2]
        highlighted = self._highlighted()
        highlighted_id = highlighted.data["id"] if highlighted else None
        scroll = self.list_scroll.get_vadjustment().get_value()
        # Unselect first: GTK leaves a removed row flagged as selected, and then it can't be selected again.
        self.listbox.unselect_all()
        for row in self.rows:
            self.listbox.remove(row)
        self.rows = []
        for item in items:
            row = self.row_cache.get((kind, item["id"]))
            if row is None:
                row = self.row_cache[(kind, item["id"])] = CardRow(self.images, kind)
                row.show_all()
            row.update(item)
            self.listbox.add(row)
            self.rows.append(row)
        self.list_key = key
        self.listbox.invalidate_filter()
        if same_view:
            GLib.idle_add(self.list_scroll.get_vadjustment().set_value, scroll)
            self._highlight_id(highlighted_id)
        else:
            self.list_scroll.get_vadjustment().set_value(0)
            self._highlight_default()
        self._update_draft_marks()  # rows new to the list need their ✎

    def _filter_row(self, row):
        return row.matches(self.search.get_text().lower().split())

    def _row_heading(self, row, before):
        """A "VOICE" heading above the first voice channel (a heading, not a row, so the arrows skip it)."""
        first_voice = row.data.get("voice") and not (before and before.data.get("voice"))
        if first_voice and row.get_header() is None:
            heading = label("VOICE", "list-heading")
            heading.show()
            row.set_header(heading)
        elif not first_voice and row.get_header() is not None:
            row.set_header(None)

    def _visible_rows(self):
        terms = self.search.get_text().lower().split()
        return [r for r in self.rows if r.matches(terms)]

    def _highlighted(self):
        return self.listbox.get_selected_row()

    def _highlight(self, row):
        if row is None:
            self.listbox.unselect_all()
            return
        self.listbox.select_row(row)
        GLib.idle_add(self._scroll_to_row, row)

    def _scroll_to_row(self, row):
        alloc = row.get_allocation()
        if alloc.height > 1:
            self.list_scroll.get_vadjustment().clamp_page(alloc.y, alloc.y + alloc.height)
        return False

    def _highlight_id(self, row_id):
        visible = self._visible_rows()
        self._highlight(next((r for r in visible if r.data["id"] == row_id), visible[0] if visible else None))

    def _highlight_default(self):
        """Highlight the open conversation (or its server); with a search typed, the best match."""
        visible = self._visible_rows()
        if self.search.get_text().strip() or not visible:
            self._highlight(visible[0] if visible else None)
            return
        on_server_list = self.tab == "servers" and self.server is None
        self._highlight_id(self.open_guild_id if on_server_list else self.channel_id)

    def _refilter(self):
        self.listbox.invalidate_filter()
        self._highlight_default()

    def _move(self, delta):
        visible = self._visible_rows()
        if not visible:
            return
        current = self._highlighted()
        index = visible.index(current) if current in visible else -1
        self._highlight(visible[max(0, min(index + delta, len(visible) - 1))])

    def _activate(self, row):
        if row is None or row.data is None:
            return
        if row.kind == "server":
            server_id = row.data["id"]
            self.server = {"id": server_id, "name": row.data["name"]}
            self.channels = []
            self.search.set_text("")
            self._render_sidebar()
            # Just this server's channels: much quicker than a full sidebar refresh.
            self._call("channels", server_id, on_ok=lambda chans: self._on_channels(server_id, chans))
            self.search.grab_focus()
            return
        self._open_conversation(row.data["id"])
        self._highlight(row)
        self._focus_reply()

    def _on_channels(self, server_id, channels):
        if self.server and self.server["id"] == server_id:
            self.channels = channels
            self._render_sidebar()

    def _leave_server(self):
        if not self.server:
            return
        server_id = self.server["id"]
        self.server = None
        self.search.set_text("")
        self._render_sidebar()
        self._highlight_id(server_id)
        self._focus_list()

    # ---------- right-click menu ----------

    def _mark_server_read(self, guild_id):
        self._call("markServerRead", guild_id, on_ok=lambda count: count and self._refresh_lists())

    def _mark_chat_read(self, channel_id):
        self._call("markRead", channel_id, on_ok=lambda changed: changed and self._refresh_lists())

    def _list_menu(self, _listbox, event):
        if event.button != 3:
            return False
        row = self.listbox.get_row_at_y(int(event.y))
        if row is None or row.data is None:
            return False
        row_id = row.data["id"]
        if row.kind == "server":
            items = [("Mark as read", lambda: self._mark_server_read(row_id)),
                     ("Open in Vesktop", lambda: self._open_in_vesktop(server_id=row_id))]
        else:  # a DM or a server's channel
            items = [("Mark as read", lambda: self._mark_chat_read(row_id)),
                     ("Open in Vesktop", lambda: self._open_in_vesktop(channel_id=row_id))]
        return self._popup_menu(items, event)

    # ---------- list keys ----------

    def _list_key(self, name, event):
        """Keys while the conversation list has focus: arrows browse, Right goes in (a chat: straight to its
        reply box), Left backs out."""
        if name == "Down":
            self._move(1)
        elif name == "Up":
            if self._at_top():
                self._focus_search()
            else:
                self._move(-1)
        elif name == "Right":
            self._enter(self._highlighted())
        elif name in ("Return", "KP_Enter"):
            pass  # → opens chats; Enter only sends (and the list widget would otherwise open the row itself)
        elif name == "Left":
            self._back()
        elif name in ("Page_Up", "Page_Down", "Home", "End", "BackSpace"):
            pass  # deliberately unused here (the list widget would otherwise page / jump on its own)
        else:
            # Typing a letter in the list goes straight into the search box.
            char = chr(Gdk.keyval_to_unicode(event.keyval) or 0)
            if not char.isprintable() or char == "\0":
                return False
            self.search.grab_focus()
            self.search.set_text(self.search.get_text() + char)
            self.search.set_position(-1)
        return True

    def _at_top(self):
        visible = self._visible_rows()
        return not visible or self._highlighted() in (None, visible[0])

    def _focus_list(self):
        if not self._highlighted():
            self._highlight_default()
        self.listbox.grab_focus()

    def _enter(self, row):
        """Go one level deeper: a server opens its channels; a friend or channel opens its chat, ready to type."""
        if row is None or row.data is None:
            return
        if row.kind == "server":
            self._activate(row)
            self._focus_list()
            return
        self._open_conversation(row.data["id"])  # (nothing to do if it's already open)
        self._highlight(row)
        self._focus_reply()
        self.reply.set_position(-1)  # continue any draft at its end

    def _back(self):
        """Go one level up: close the open chat first, then leave the server's channel list."""
        in_this_view = self.channel_id and any(r.data["id"] == self.channel_id for r in self.rows)
        if in_this_view:
            highlighted = self._highlighted()
            self._close_conversation()
            if highlighted:
                self._highlight(highlighted)
        elif self.tab == "servers" and self.server:
            self._leave_server()

    def _escape(self):
        """Esc dismisses the topmost temporary thing; with none left, it closes the panel from anywhere.
        (Pickers, suggestions, the "?" list and video focus are handled before this; ← goes back a level.)"""
        if self.deleting:
            self._cancel_delete()
        elif self.clearing_history:
            self._cancel_clear_history()
        elif self.editing:
            self._cancel_edit()
        elif self.replying_to:
            self._cancel_reply()
        elif self.pending_image is not None:
            self._cancel_attachment()
        elif self.search.get_text():
            self.search.set_text("")
        else:
            self.hide()

    def _focus_search(self):
        self.search.grab_focus()
        self.search.select_region(0, -1)
