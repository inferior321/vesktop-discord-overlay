"""The open chat: loading, drawing and scrolling its messages, older history and media."""

import time
import traceback
from datetime import datetime

from .config import (DISCARD_BATCH, FLASH_MS, GROUP_GAP_MINUTES, MESSAGE_AVATAR, MESSAGE_COUNT, NOTE_SHOW_MS,
                     OLDER_BATCH, REPLY_SEARCH_BATCHES, SCROLL_ANCHOR_SECONDS, SCROLL_EDGE, SCROLL_STEP)
from .gtk import Gdk, GLib, Gtk
from .markdown import reaction_row, render_message, RenderContext, Revealed
from .media import Avatar, MediaView
from .system import activate_vesktop_window
from .viewer import viewable
from .widgets import (add_class, copy_to_clipboard, day_label, divider, fill_menu, hook_label_menus, label,
                      message_time, set_class)


class MessagesMixin:
    """Part of Overlay (shares its state); see overlay.py."""

    # ---------- messages ----------

    def _save_draft(self):
        if self.channel_id:
            self.drafts[self.channel_id] = self.reply.get_text()

    def _open_conversation(self, channel_id, from_history=False):
        if channel_id == self.channel_id:
            return
        self._cancel_delete()
        self._cancel_edit()  # before saving the draft, so the draft is your own text, not the edit
        self._save_draft()
        self._remember_scroll()
        self.members_pop.popdown()  # (another chat: another member list)
        self.channel_id = channel_id
        self.open_voice = None  # (known once it loads, unless it's in the server list open now)
        self.open_forum = None
        self.jump_target = None
        self.open_guild_id = self.server["id"] if self.tab == "servers" and self.server else None
        if not from_history:
            self._record_visit(channel_id, self.open_guild_id)
        self.header.show()
        self.reply_row.show()
        self._close_picker(focus_reply=False)
        self.reply.set_text(self.drafts.get(channel_id, ""))
        reopening = channel_id == self.blocks_for  # the chat you just closed: its rows are still there
        self.rendered_key = None
        self.stick_bottom = True
        self.latest = []
        self.new_marker_for = self.new_marker = self.seen_newest = None
        self._cancel_reply()
        self._cancel_attachment()
        self.restore_to = self.scroll_memory.pop(channel_id, None)
        if self.restore_to is None:  # you'd left it at the newest messages: start fresh from there
            self.older.pop(channel_id, None)
            self.history_done.discard(channel_id)
        self.loading_older = False
        self.anchor = None
        if reopening:
            self._show_chat_pane()
        else:
            self._render_info("Loading…")
        self.typing_text = ""
        self.typing_bar.hide()
        self._update_draft_marks()
        self._update_call_button()  # a voice channel's chat: Join it from the bottom bar
        self._load_messages()

    def _close_conversation(self):
        """Back to the empty pane: no chat open, no header, no reply box."""
        self._cancel_delete()
        self._cancel_edit()
        self._save_draft()
        self._remember_scroll()
        self.channel_id = None
        self.open_voice = None
        self.open_forum = None
        self.members_pop.popdown()
        self.open_guild_id = None
        self.rendered_key = None
        self.jump_target = None
        self.reply.set_text("")
        self._update_draft_marks()
        self._update_call_button()
        self._show_empty()

    def _show_empty(self):
        """The empty pane. The closed chat's messages are only hidden (which also pauses its GIFs), so closing
        is instant however much is loaded, and reopening it is too."""
        self.header.hide()
        self.reply_row.hide()
        self._close_picker(focus_reply=False)
        self.jump_pill.hide()
        self.chat_layer.hide()
        self.empty_hint.show()

    def _show_chat_pane(self):
        self.empty_hint.hide()
        self.chat_layer.show()

    def _load_messages(self):
        channel_id = self.channel_id
        if not channel_id:
            return False
        if self.loading_chat == channel_id:  # already reading it: read it once more afterwards, for what's new
            self.reload_wanted = True
            return False
        self.loading_chat, self.reload_wanted = channel_id, False

        def finished():
            if self.loading_chat == channel_id:
                self.loading_chat = None
                if self.reload_wanted:
                    self._load_messages()

        def got(data):
            try:
                self._on_messages(channel_id, data)
            finally:  # even if drawing failed, so this chat keeps updating
                finished()

        def failed(exc):
            self._show_error(exc)
            finished()

        self._call("messages", channel_id, MESSAGE_COUNT, on_ok=got, on_err=failed)
        return False

    def _on_messages(self, channel_id, data):
        if channel_id != self.channel_id:
            return  # user already switched to another conversation
        if "error" in data:
            if self._drop_unreachable_history(channel_id):
                return
            self._render_info(data["error"])
            return
        if data["guildId"]:
            self.open_guild_id = data["guildId"]
        self.open_voice = data.get("voice")  # a voice channel's chat: the bottom bar offers to join it
        self.open_forum = data.get("forum")  # a forum post: the forum it's in (for Ctrl+Shift+Right)
        self._update_call_button()
        self.history_step = 0
        for entry in self.history:
            if entry["id"] == channel_id and (entry["name"], entry["guildId"]) != (data["name"], data["guildId"]):
                entry.update(name=data["name"], guildId=data["guildId"])
                self._save_history()  # (names are remembered too, for the "3 / 7 · name" note)
        self._set_header(data["name"], data["place"], data["icon"], rounded=bool(data["guildId"]))
        self.reply.set_placeholder_text(f"Message {data['name'] if data['guildId'] else '@' + data['name']}")
        if not self.typing_live:  # once Vesktop pushes typing changes live, those are always fresher
            self._set_typing(data["typing"])

        if self.new_marker_for != channel_id:  # first load of this chat since opening it: where unread begins
            self.new_marker_for = channel_id
            self.new_marker = data.get("firstUnreadId")
            self.rendered_key = None
        self.latest = data["messages"]
        self._render_messages()
        self._mark_read_if_seen()

    def _merged_messages(self):
        """Loaded older history plus the live newest messages, oldest first, without duplicates."""
        by_id = {m["id"]: m for m in self.older.get(self.channel_id, [])}
        by_id.update((m["id"], m) for m in self.latest)
        return sorted(by_id.values(), key=lambda m: int(m["id"]))

    def _render_messages(self):
        msgs = self._merged_messages()
        key = tuple(self._message_key(m) for m in msgs)
        if key == self.rendered_key:
            return
        if self.rendered_key is None:  # a chat (re)opened: show its newest messages
            self.stick_bottom = True
            if self.blocks_for != self.channel_id:  # another chat's rows: start from an empty pane
                self._clear_messages(keep_player=True)
        self.rendered_key = key
        self.blocks_for = self.channel_id

        # The pane as a list of blocks (date lines, the NEW line, one row per message), each with a key that
        # changes whenever its drawing would. Blocks whose key is unchanged keep their widgets, so a new
        # message only adds a row: nothing else is rebuilt, and GIFs and videos keep playing.
        plan = [(("history",), self._history_block)]
        if not msgs:
            plan.append((("empty",), lambda: label("No messages yet.", "info")))
        prev, day, new_line_done = None, None, False
        for m in msgs:
            m_day = datetime.fromtimestamp(m["time"] / 1000).date()
            starts_new_day = m_day != day
            is_first_unread = (not new_line_done and self.new_marker is not None
                               and int(m["id"]) >= int(self.new_marker))
            starts_group = (prev is None or starts_new_day or is_first_unread or prev["authorId"] != m["authorId"]
                            or m["time"] - prev["time"] > GROUP_GAP_MINUTES * 60_000 or bool(m["reply"])
                            or bool(m.get("system")) or bool(prev.get("system")) or bool(m.get("command")))
            if starts_new_day:
                text = day_label(m_day)
                plan.append((("day", m_day, text), lambda text=text: divider(text, "date-sep")))
                day = m_day
            if is_first_unread:
                plan.append((("new",), lambda: divider("NEW", "new-sep", label_at_end=True)))
                new_line_done = True
            plan.append((("msg", m["id"], starts_group, self._message_key(m)),
                         lambda m=m, starts_group=starts_group: self._message_row(m, starts_group)))
            prev = m
        self._apply_plan(plan)
        self._update_history_label()  # its line is kept across redraws, so refresh its text
        if self.editing:
            self._show_edit_highlight()

        if self.restore_to and self.restore_to[0] in self.message_widgets:
            # Back to where you were reading in this chat (applied once the layout settles).
            message_id, offset = self.restore_to
            self.anchor = (message_id, offset, time.monotonic() + SCROLL_ANCHOR_SECONDS)
            self.stick_bottom = False
            self.restore_to = None
        self._update_jump_pill()

    @staticmethod
    def _message_key(m):
        """Everything that changes how a message is drawn."""
        return (m["id"], m["author"], m["avatar"], m["content"], m["mentionsMe"], m.get("edited"),
                str(m.get("system")), str(m.get("forwarded")), str(m.get("poll")), str(m.get("command")),
                tuple(m["extras"]), tuple(item.get("src") for item in m["media"]),
                tuple((str(r["emoji"]), r["count"], r["me"]) for r in m.get("reactions", ())))

    def _apply_plan(self, plan):
        """Make the pane show exactly these blocks, in order, reusing the widgets of unchanged ones."""
        old = self.blocks
        wanted = {block_key for block_key, _ in plan}
        # A playing YouTube video in a message that's about to be redrawn is lifted out and handed to the
        # new row (see _message_row), so it keeps playing.
        if self.player_view and self.player_view.player:
            kept_views = (v for k, w in old.items() if k in wanted for v in getattr(w, "views", ()))
            if not any(v is self.player_view for v in kept_views):
                had_focus = self.win.get_focus() is self.player_view.player
                self.kept_player = (self.player_view.key, self.player_view.detach_player(), had_focus)
                self.player_view = None
        self._discard([widget for block_key, widget in old.items() if block_key not in wanted])
        self.blocks = {}
        for block_key, build in plan:
            widget = old.get(block_key)
            if widget is None:
                try:
                    widget = build()
                except Exception:  # noqa: BLE001 - one odd message mustn't break the whole pane
                    traceback.print_exc()
                    widget = label("(This message couldn't be shown here.)", "info")
                    widget.views, widget.body = [], widget
                self.msg_box.pack_start(widget, False, False, 0)
                widget.show_all()
            self.blocks[block_key] = widget
        order = list(self.blocks.values())
        if self.msg_box.get_children() != order:  # e.g. older messages arrived above
            for index, widget in enumerate(order):
                self.msg_box.reorder_child(widget, index)
        self._drop_kept_player()
        rows = [w for k, w in self.blocks.items() if k[0] == "msg"]
        self.media_views = [view for row in rows for view in row.views]
        self.message_widgets = {k[1]: w.body for k, w in self.blocks.items() if k[0] == "msg"}  # oldest first

    def _history_block(self):
        """The "Loading older messages…" / "This is the start…" line at the top."""
        self.history_label = label("", "info", xalign=0.5)
        self.history_label.set_margin_top(6)
        self.history_label.set_no_show_all(True)  # shown only while loading / at the very start
        self._update_history_label()
        return self.history_label

    def _message_row(self, m, starts_group):
        """One message. The first of a group from the same author gets the avatar and name; the rest are
        indented to line up under it."""
        if m.get("system"):
            return self._system_row(m)
        row = Gtk.Box(spacing=12, margin_top=12 if starts_group else 2)
        if starts_group:
            avatar = Avatar(self.images, MESSAGE_AVATAR)
            avatar.set_valign(Gtk.Align.START)
            avatar.set(m["avatar"], m["author"][:1].upper())
            row.pack_start(avatar, False, False, 0)
        else:
            indent = Gtk.Box()
            indent.set_size_request(MESSAGE_AVATAR, -1)
            row.pack_start(indent, False, False, 0)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        if starts_group:
            if m.get("command"):  # a bot answering a slash command: who used which one
                used = f"↳ {m['command']['user']} used /{m['command']['name']}"
                col.pack_start(label(used, "msg-reply", ellipsize=True), False, False, 0)
            if m["reply"]:
                reply = label(f"↳ {m['reply']['author']}: {m['reply']['text']}", "msg-reply", ellipsize=True)
                if m["reply"].get("id"):  # click it to go to the message it replies to
                    reply_events = Gtk.EventBox()
                    reply_events.add(reply)
                    reply_events.set_tooltip_text("Go to the original message")
                    reply_events.connect("button-press-event", lambda _w, e: e.button == 1 and (
                        self._jump_to_message(m["reply"]["id"]) or True))
                    reply_events.connect("realize", lambda w: w.get_window().set_cursor(
                        Gdk.Cursor.new_from_name(w.get_display(), "pointer")))
                    reply = reply_events
                col.pack_start(reply, False, False, 0)
            head = Gtk.Box(spacing=8)
            author = label(m["author"], "msg-author", ellipsize=True)  # (a long name mustn't widen the panel)
            set_class(author, "self", m["self"])
            author.set_valign(Gtk.Align.BASELINE)
            stamp = label(message_time(m["time"]), "msg-time")
            stamp.set_valign(Gtk.Align.BASELINE)
            head.pack_start(author, False, True, 0)
            head.pack_start(stamp, False, False, 0)
            col.pack_start(head, False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        if m["mentionsMe"]:
            add_class(body, "msg-mentioned")
        ctx = RenderContext(Revealed(self.revealed, m["id"]), self._open_url, self.images)
        for widget in render_message(m["ast"], ctx, edited=m.get("edited")):
            body.pack_start(widget, False, False, 0)
        views = []
        for index, item in enumerate(m["media"]):
            views.append(self._media_view(body, item, (m["id"], index)))
        for extra in m["extras"]:
            body.pack_start(label(extra, "msg-extra", ellipsize=True), False, False, 0)
        if m.get("forwarded"):  # like Discord: "↱ Forwarded" over the original, set off by a bar
            forwarded = m["forwarded"]
            body.pack_start(label("↱ Forwarded", "msg-reply"), False, False, 0)
            box = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), "forward-box")
            for widget in render_message(forwarded["ast"], RenderContext(Revealed(self.revealed, m["id"] + ":f"),
                                                                         self._open_url, self.images)):
                box.pack_start(widget, False, False, 0)
            for index, item in enumerate(forwarded["media"]):
                views.append(self._media_view(box, item, (m["id"], "forwarded", index)))
            for extra in forwarded["extras"]:
                box.pack_start(label(extra, "msg-extra", ellipsize=True), False, False, 0)
            body.pack_start(box, False, False, 2)
        if m.get("poll"):
            body.pack_start(self._poll_box(m["poll"]), False, False, 4)
        if m.get("reactions"):
            body.pack_start(reaction_row(m["reactions"], self.images, lambda r: self._toggle_reaction(m, r)),
                            False, False, 2)
        # Right-click anywhere on the message for its menu (on its text too, where GTK has a menu of its own).
        holder = Gtk.EventBox()
        holder.add(body)
        holder.connect("button-press-event", lambda _w, event: self._message_menu(m, event))
        hook_label_menus(body, lambda text, menu: self._fill_text_menu(text, menu, m))
        col.pack_start(holder, False, False, 0)
        row.pack_start(col, True, True, 0)
        row.views, row.body = views, body
        return row

    def _media_view(self, box, item, key):
        """An image / GIF / video / YouTube thumbnail in a message, added to box."""
        view = MediaView(self.images, item, self._open_url, on_play=self._play_youtube, on_view=self._view_media)
        view.key = key
        if self.kept_player and self.kept_player[0] == key:
            _, player, had_focus = self.kept_player
            view.adopt_player(player)  # the video that was playing before the redraw
            if had_focus:
                GLib.idle_add(player.grab_focus)  # keep its keys (and Esc back to the panel) working
            self.player_view, self.kept_player = view, None
        view.set_margin_top(4)
        view.set_margin_bottom(2)
        if not self.win.get_visible():
            view.set_active(False)
        box.pack_start(view, False, False, 0)
        return view

    @staticmethod
    def _poll_box(poll):
        """A poll, view only (voting is done in Vesktop): the question, each answer with its votes, yours
        ticked."""
        box = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4), "poll")
        box.set_halign(Gtk.Align.START)
        box.pack_start(label(f"📊  {poll['question']}", "poll-question", ellipsize=True), False, False, 0)
        total = poll["total"] or 1
        for answer in poll["answers"]:
            row = add_class(Gtk.Box(spacing=10), "poll-answer")
            set_class(row, "mine", answer["me"])
            text = f"{answer['emoji']} {answer['text']}".strip() + ("  ✓" if answer["me"] else "")
            row.pack_start(label(text, "poll-text", ellipsize=True), True, True, 0)
            share = round(answer["count"] * 100 / total)
            row.pack_start(label(f"{answer['count']} · {share}%", "poll-count"), False, False, 0)
            box.pack_start(row, False, False, 0)
        votes = f"{poll['total']} vote{'s' if poll['total'] != 1 else ''}"
        state = "Poll closed" if poll["closed"] else "Vote in Vesktop"
        box.pack_start(label(f"{votes} · {state}", "poll-footer"), False, False, 0)
        return box

    def _system_row(self, m):
        """A Discord system message (a call, a pin, someone joining, ...): one grey line with an icon, as in
        Discord."""
        row = Gtk.Box(spacing=12, margin_top=8)
        icon = label(m["system"]["icon"], "system-icon", xalign=0.5)
        icon.set_size_request(MESSAGE_AVATAR, -1)
        row.pack_start(icon, False, False, 0)
        text, author = m["system"]["text"], m["author"]
        if text.startswith(author):  # the person in white, the rest grey, as Discord does
            esc = GLib.markup_escape_text
            markup = f"<b>{esc(author, -1)}</b>{esc(text[len(author):], -1)}"
        else:
            markup = GLib.markup_escape_text(text, -1)
        body = Gtk.Box(spacing=8)
        line = label("", "system-text", ellipsize=True)
        line.set_markup(markup)
        stamp = label(message_time(m["time"]), "msg-time")
        body.pack_start(line, False, True, 0)
        body.pack_start(stamp, False, False, 0)
        holder = Gtk.EventBox()  # right-click: copy its link, open it in Vesktop
        holder.add(body)
        holder.connect("button-press-event", lambda _w, event: self._message_menu(m, event))
        row.pack_start(holder, True, True, 0)
        row.views, row.body = [], body
        return row

    # ---------- message right-click menu ----------

    def _message_items(self, m, text=None):
        """The message menu, in groups: respond, copy, open, and (your messages) delete, alone and in red.
        text: the label right-clicked, if any; with part of it highlighted the copy group starts with that."""
        link = f"https://discord.com/channels/{self.open_guild_id or '@me'}/{self.channel_id}/{m['id']}"
        if m.get("system"):  # nothing to reply to, react to or copy as text
            return [("Copy message link", lambda: copy_to_clipboard(link)), None,
                    ("Open in Vesktop", lambda: self._open_message_in_vesktop(m["id"]))]
        respond = [("Reply", lambda: self._start_reply(m)),
                   ("Add reaction", lambda: self._open_reaction_picker(m))]
        if m["self"] and not m.get("forwarded") and not m.get("poll"):  # (Discord can't edit those either)
            respond.append(("Edit message", lambda: self._start_edit(m)))
        whole = (m["content"] or (m.get("forwarded") or {}).get("content") or (m.get("poll") or {}).get("question")
                 or (m["media"][0]["full"] if m["media"] else ""))
        copy = [("Copy text", lambda: copy_to_clipboard(whole)),
                ("Copy message link", lambda: copy_to_clipboard(link))]
        if text is not None:
            highlighted, start, end = text.get_selection_bounds()
            if highlighted and start != end:
                copy.insert(0, ("Copy selection", lambda: text.emit("copy-clipboard")))
        items = [*respond, None, *copy, None, ("Open in Vesktop", lambda: self._open_message_in_vesktop(m["id"]))]
        if m["self"]:
            items += [None, ("Delete message", lambda: self._ask_delete(m), "danger")]
        return items

    def _message_menu(self, m, event):
        if event.button != 3:
            return False
        return self._popup_menu(self._message_items(m), event)

    def _fill_text_menu(self, text, menu, m):
        """Right-clicking a message's text: the message menu instead of GTK's Cut / Copy / Paste / Delete /
        Select All."""
        for item in menu.get_children():
            menu.remove(item)
        fill_menu(menu, self._message_items(m, text))

    def _open_message_in_vesktop(self, message_id):
        channel_id = self.channel_id
        self.prev_window = None  # going to Vesktop, not back to the previous window
        self.hide()
        self._call("openMessage", channel_id, message_id, on_ok=lambda _: activate_vesktop_window())

    def _clear_messages(self, keep_player=False):
        # keep_player: a re-render of the same chat; lift a playing YouTube video out so it keeps playing.
        if keep_player and self.player_view and self.player_view.player:
            had_focus = self.win.get_focus() is self.player_view.player
            self.kept_player = (self.player_view.key, self.player_view.detach_player(), had_focus)
        self.player_view = None
        self.media_views = []
        self.message_widgets = {}
        self.blocks = {}
        self.blocks_for = None
        self.history_label = None
        # A fresh, empty box takes the old one's place at once; the old one is destroyed in the background.
        old_box, self.msg_box = self.msg_box, message_box()
        viewport = old_box.get_parent()
        viewport.remove(old_box)
        viewport.add(self.msg_box)
        self.msg_box.show()
        self._discard(old_box.get_children() + [old_box])

    def _discard(self, widgets):
        """Take widgets off screen now and destroy them a batch at a time in the background: destroying hundreds
        of messages in one go would freeze the panel."""
        for widget in widgets:
            for view in getattr(widget, "views", ()):
                if view.video:
                    view.video.stop()  # (in the background too)
            if widget.get_parent() is self.msg_box:
                self.msg_box.remove(widget)
        self.discarding.extend(widgets)
        if self.discard_source is None:
            self.discard_source = GLib.idle_add(self._discard_batch, priority=GLib.PRIORITY_LOW)

    def _discard_batch(self):
        batch, self.discarding = self.discarding[:DISCARD_BATCH], self.discarding[DISCARD_BATCH:]
        for widget in batch:
            widget.destroy()
        if self.discarding:
            return True
        self.discard_source = None
        return False

    def _drop_kept_player(self):
        # Its message is gone (e.g. deleted); don't leave the video playing invisibly.
        if self.kept_player:
            self.kept_player[1].destroy()
            self.kept_player = None

    def _render_info(self, message):
        self.rendered_key = None
        self._clear_messages()
        self._show_chat_pane()
        info = label(message, "info")
        info.set_line_wrap(True)
        info.set_margin_top(12)
        self.msg_box.pack_start(info, False, False, 0)
        self.msg_box.show_all()

    def _set_header(self, name, place, icon, rounded=False):
        self.header_name.set_text(name)
        self.header_place.set_text(place)
        # In a server chat its name opens the member list: say so (a ▾, a hand, a tooltip).
        server = self._can_show_members()
        self.members_hint.set_visible(server)
        target = self.members_target
        target.set_tooltip_text("Members" if server else None)
        if target.get_window():
            hand = Gdk.Cursor.new_from_name(target.get_display(), "pointer") if server else None
            target.get_window().set_cursor(hand)
        self.header_avatar.rounded_square = rounded
        self.header_avatar.set(icon, name.lstrip("#@🔊 ")[:1].upper(), self._friend_status())
        self._update_header_line()

    def _friend_card(self):
        """The open DM's card in the Friends list (None for server channels)."""
        return next((f for f in self.friends if f["id"] == self.channel_id), None) if self.channel_id else None

    def _friend_status(self):
        """The online status of the friend in the open DM (None for group DMs and server channels), as the
        Friends list knows it, so the header's picture shows the same dot as the list, like Discord."""
        card = self._friend_card()
        return card.get("status") if card else None

    def _update_header_status(self):
        """After the lists refresh (statuses change live): keep the open DM's dot in the header current."""
        if self.channel_id:
            avatar = self.header_avatar
            avatar.set(avatar.url, avatar.fallback, self._friend_status())
            self._update_header_line()  # (their custom status / activity may have changed too)

    def _set_typing(self, names):
        if not names:
            text = ""
        elif len(names) == 1:
            text = f"{names[0]} is typing…"
        elif len(names) <= 3:
            text = f"{', '.join(names[:-1])} and {names[-1]} are typing…"
        else:
            text = "Several people are typing…"
        self.typing_text = text
        self.typing_label.set_text(text)
        self.typing_bar.set_visible(bool(text))  # (just above the reply box, with pulsing dots)

    def _update_header_line(self):
        """The line under the chat's name: (in a DM) the friend's custom status or activity, like Discord."""
        card = self._friend_card()
        self.header_line.set_text((card or {}).get("activity") or "")

    def _keep_bottom(self, adj):
        if self.anchor and time.monotonic() < self.anchor[2]:
            # Older messages were added above: keep the message you were looking at where it was.
            widget = self.message_widgets.get(self.anchor[0])
            pos = widget.translate_coordinates(self.msg_box, 0, 0) if widget else None
            if pos:
                adj.set_value(pos[1] - self.anchor[1])
            return
        if self.stick_bottom:
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def _track_bottom(self, adj):
        self.stick_bottom = adj.get_value() >= adj.get_upper() - adj.get_page_size() - SCROLL_EDGE
        if self.stick_bottom:
            self._mark_read_if_seen()
        self._update_jump_pill()
        if adj.get_value() <= SCROLL_EDGE and adj.get_upper() > adj.get_page_size() and not self.anchor_active():
            self._load_older()

    def anchor_active(self):
        return self.anchor is not None and time.monotonic() < self.anchor[2]

    def _remember_scroll(self):
        """Leaving a chat while scrolled up: note the message at the top of the view and where it sat."""
        if not self.channel_id or self.stick_bottom:
            self.scroll_memory.pop(self.channel_id, None)
            return
        top = self.msg_scroll.get_vadjustment().get_value()
        for message_id, widget in self.message_widgets.items():  # oldest first
            pos = widget.translate_coordinates(self.msg_box, 0, 0)
            if pos and pos[1] + widget.get_allocated_height() > top:
                self.scroll_memory[self.channel_id] = (message_id, pos[1] - top)
                return

    def _update_jump_pill(self):
        """Show "New messages" while you're scrolled up and something newer than what you last saw arrived."""
        newest = self.latest[-1]["id"] if self.latest else None
        if self.stick_bottom or self.seen_newest is None:
            self.seen_newest = newest
        show = (not self.stick_bottom and newest is not None and self.seen_newest is not None
                and int(newest) > int(self.seen_newest) and not self.picker.get_visible())
        self.jump_pill.set_visible(show)

    def _jump_to_newest(self, *_):
        adj = self.msg_scroll.get_vadjustment()
        self.stick_bottom = True
        adj.set_value(adj.get_upper() - adj.get_page_size())
        self.jump_pill.hide()

    def _mark_read_if_seen(self):
        """Mark the open chat read once its newest messages are on screen (not while reading history)."""
        channel_id = self.channel_id
        if not (channel_id and self.latest and self.stick_bottom and self.win.get_visible()):
            return
        newest = self.latest[-1]["id"]
        if self.marked_read.get(channel_id) == newest:
            return  # already told Discord about this one
        self.marked_read[channel_id] = newest
        self._call("markRead", channel_id, on_err=lambda _exc: None,
                   on_ok=lambda changed: changed and self._refresh_lists())  # clear its dot/badge right away

    # ---------- older history ----------

    def _load_older(self):
        channel_id = self.channel_id
        if (not channel_id or self.loading_older or channel_id in self.history_done
                or self.rendered_key is None or not self.latest):
            return
        oldest = self._merged_messages()[0]
        self.loading_older = True
        self._update_history_label()
        self._call("olderMessages", channel_id, oldest["id"], OLDER_BATCH,
                   on_ok=lambda data: self._on_older(channel_id, oldest["id"], data),
                   on_err=lambda exc: self._on_older_failed(channel_id, exc))

    def _on_older(self, channel_id, anchor_id, data):
        self.loading_older = False
        if channel_id != self.channel_id:
            return
        if "error" in data or not data.get("more"):
            self.history_done.add(channel_id)
        new = data.get("messages", [])
        if new:
            self.older[channel_id] = new + self.older.get(channel_id, [])
            # Remember where the previously-oldest message sits so the view doesn't jump.
            widget = self.message_widgets.get(anchor_id)
            pos = widget.translate_coordinates(self.msg_box, 0, 0) if widget else None
            offset = (pos[1] if pos else 0) - self.msg_scroll.get_vadjustment().get_value()
            self.anchor = (anchor_id, offset, time.monotonic() + SCROLL_ANCHOR_SECONDS)
            self.stick_bottom = False
            self._render_messages()
        else:
            self._update_history_label()
        if self.jump_target and self.jump_target[0] == channel_id:
            GLib.idle_add(self._continue_jump)

    def _on_older_failed(self, channel_id, exc):
        self.loading_older = False
        self.jump_target = None
        if channel_id == self.channel_id:
            self._update_history_label()
            self._show_error(exc)

    def _update_history_label(self):
        if self.history_label is None:
            return
        if self.loading_older:
            text = "Loading older messages…"
        elif self.channel_id in self.history_done:
            text = "This is the start of the conversation."
        else:
            text = ""
        self.history_label.set_text(text)
        self.history_label.set_visible(bool(text))

    # ---------- scrolling ----------

    def _scroll_messages(self, key):
        """Up/Down scroll the chat while typing."""
        adj = self.msg_scroll.get_vadjustment()
        step = SCROLL_STEP if key == "Down" else -SCROLL_STEP
        adj.set_value(max(adj.get_lower(), min(adj.get_value() + step, adj.get_upper() - adj.get_page_size())))

    # ---------- media viewer ----------

    def _view_media(self, view):
        """Open the viewer on this item, with every viewable item in the chat to flip through."""
        views = [v for v in self.media_views if viewable(v.item)]
        self.viewer.open([v.item for v in views], views.index(view) if view in views else 0)

    # ---------- YouTube ----------

    def _play_youtube(self, view):
        """Start YouTube's player in place of this thumbnail; only one plays at a time."""
        if self.player_view and self.player_view is not view:
            self.player_view.stop_player()
        self.player_view = view
        view.start_player()

    def _stop_youtube(self):
        if self.player_view:
            self.player_view.stop_player()
            self.player_view = None

    def _open_url(self, url):
        """Open an image/GIF/video full size in the default browser or viewer, and get out of the way."""
        try:
            Gtk.show_uri_on_window(self.win, url, Gtk.get_current_event_time())
        except GLib.Error as exc:
            self._show_error(exc)
            return
        self.prev_window = None
        self.hide()

    # ---------- going to a message (clicking a reply's quote) ----------

    def _jump_to_message(self, message_id):
        """Scroll to this message and flash it; if it isn't loaded, load older history until it is."""
        if message_id in self.message_widgets:
            self.jump_target = None
            self._show_message(message_id)
            return
        self.jump_target = (self.channel_id, message_id, 0)
        self._flash("Finding the message…", NOTE_SHOW_MS)
        self._continue_jump()

    def _continue_jump(self):
        if not self.jump_target or self.jump_target[0] != self.channel_id:
            return False
        channel_id, message_id, tries = self.jump_target
        if message_id in self.message_widgets:
            self.jump_target = None
            self._show_message(message_id)
        elif channel_id in self.history_done or tries >= REPLY_SEARCH_BATCHES:
            self.jump_target = None
            self._flash("Couldn't find the original message (it may be deleted)", NOTE_SHOW_MS * 2)
        elif not self.loading_older:  # (if older messages are loading already, their arrival continues this)
            self.jump_target = (channel_id, message_id, tries + 1)
            self._load_older()
        return False

    def _show_message(self, message_id):
        """Center a loaded message in view and highlight it for a moment."""
        body = self.message_widgets[message_id]
        adj = self.msg_scroll.get_vadjustment()
        offset = max(0, (adj.get_page_size() - body.get_allocated_height()) / 2)
        # Held in place while the layout settles (images loading above it), like after loading older messages.
        self.anchor = (message_id, offset, time.monotonic() + SCROLL_ANCHOR_SECONDS)
        self.stick_bottom = False
        self._keep_bottom(adj)
        add_class(body, "msg-flash")
        GLib.timeout_add(FLASH_MS, lambda: body.get_style_context().remove_class("msg-flash") or False)

    # ---------- after you react, edit or delete ----------

    def _refresh_message(self, channel_id, message_id):
        """Re-read one message you changed. New ones refresh by themselves; older history loaded by scrolling up
        doesn't, so it's updated here."""
        older = self.older.get(channel_id, [])
        if not any(m["id"] == message_id for m in older):
            return

        def got(fresh):
            if fresh:
                older = self.older.get(channel_id, [])
                self.older[channel_id] = [fresh if m["id"] == message_id else m for m in older]
                if channel_id == self.channel_id:
                    self._render_messages()
        self._call("message", channel_id, message_id, on_ok=got, on_err=lambda _exc: None)

    def _forget_message(self, channel_id, message_id):
        """A message you deleted leaves older history at once (newer messages refresh by themselves)."""
        if channel_id in self.older:
            self.older[channel_id] = [m for m in self.older[channel_id] if m["id"] != message_id]
            if channel_id == self.channel_id:
                self._render_messages()


def message_box():
    """The box holding the open chat's messages."""
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=16, margin_end=16, margin_top=6,
                   margin_bottom=24)  # (room at the bottom for the "… is typing" line)
