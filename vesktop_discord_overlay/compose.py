"""The reply box: replies, edits, deleting, pasted images, sending, reactions, pickers and ':' suggestions."""

import base64
import re
import time

from .config import (MAX_UPLOAD_MB, NOTE_SHOW_MS, PICKER_MAX_H, PICKER_MIN_H, RELOAD_AFTER_SEND_MS,
                     SUGGESTION_COUNT, TYPING_REPORT_SECONDS, UPLOAD_TIMEOUT_SECONDS)
from .gtk import Gdk, GLib, Gtk
from .pickers import all_emoji, emoji_text, match_emoji
from .widgets import add_class, pointer_inside, set_class


class ComposeMixin:
    """Part of Overlay (shares its state); see overlay.py."""

    # ---------- replying and pasted images ----------

    def _small_close_button(self, on_click):
        btn = add_class(Gtk.Button(label="✕"), "compose-close")
        btn.set_can_focus(False)
        btn.connect("clicked", lambda *_: on_click())
        return btn

    def _start_reply(self, m):
        self.replying_to = m
        self.reply_note_label.set_markup(f"Replying to <b>{GLib.markup_escape_text(m['author'], -1)}</b>")
        self.reply_note.show()
        self._focus_reply()

    def _cancel_reply(self):
        self.replying_to = None
        self.reply_note.hide()

    def _on_paste(self, entry):
        """Ctrl+V with an image on the clipboard attaches it instead of pasting text."""
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        if not clipboard.wait_is_image_available():
            return  # ordinary text paste
        pixbuf = clipboard.wait_for_image()
        entry.stop_emission_by_name("paste-clipboard")
        if pixbuf is None:
            return
        if self.editing:
            self._flash("An edit can't add an image", NOTE_SHOW_MS)
            return
        ok, data = pixbuf.save_to_bufferv("png", [], [])
        if not ok:
            return
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            self._show_error(RuntimeError(f"Image is over Discord's {MAX_UPLOAD_MB} MB limit"))
            return
        self.pending_image = bytes(data)
        self.attach_thumb.set_pixbuf(pixbuf)
        self.attach_label.set_text(f"Pasted image · {max(1, round(len(data) / 1024))} KB · Enter sends it")
        self.attach_note.show()

    def _cancel_attachment(self):
        self.pending_image = None
        self.attach_note.hide()

    # ---------- editing and deleting your messages ----------

    def _start_edit(self, m):
        """Right-click → Edit message: its text goes into the reply box; Enter saves, Esc cancels."""
        if not m["self"] or not self.channel_id:
            return
        channel_id = self.channel_id
        self._call("editText", channel_id, m["id"],
                   on_ok=lambda text: channel_id == self.channel_id and self._begin_edit(m, text or ""))

    def _begin_edit(self, m, text):
        self._cancel_delete()
        if self.editing:
            self._cancel_edit()
        # Set your draft, reply and pasted image aside; they come back when the edit is saved or cancelled.
        self.edit_stash = (self.reply.get_text(), self.reply.get_position(), self.replying_to, self.pending_image)
        self.replying_to = None
        self.reply_note.hide()
        self.pending_image = None
        self.attach_note.hide()
        self.editing = m
        self.edit_original = text.strip()
        self.edit_note.show()
        self.reply.set_text(text)
        self._show_edit_highlight()
        self._focus_reply()
        self.reply.set_position(-1)

    def _show_edit_highlight(self):
        """Mark the message being edited (again after a redraw rebuilt its row)."""
        for message_id, body in self.message_widgets.items():
            set_class(body, "msg-editing", bool(self.editing) and message_id == self.editing["id"])

    def _cancel_edit(self):
        if not self.editing:
            return
        self.editing = None
        self.edit_note.hide()
        self._show_edit_highlight()
        text, position, replying_to, image = self.edit_stash
        self.edit_stash = None
        self.reply.set_text(text)
        self.reply.set_position(position)
        if replying_to:
            self._start_reply(replying_to)
        if image is not None:
            self.pending_image = image
            self.attach_note.show()  # its thumbnail and size are still set from the paste

    def _save_edit(self):
        m, content = self.editing, self.reply.get_text().strip()
        if not content:
            self._ask_delete(m)  # Discord won't keep an empty message: offer to delete it instead
            return
        channel_id = self.channel_id
        self._cancel_edit()
        if content != self.edit_original:  # unchanged: nothing to save (and no "(edited)")
            self._call("editMessage", channel_id, m["id"], content,
                       on_ok=lambda _: self._refresh_message(channel_id, m["id"]))

    def _ask_delete(self, m):
        """Right-click → Delete message: "Delete this message?" above the reply box (Shift skips it)."""
        if not m["self"]:
            return
        if shift_held():
            self._delete(m)
            return
        self.deleting = m
        self.delete_note.show()
        self._focus_reply()

    def _confirm_delete(self):
        if self.deleting:
            m, self.deleting = self.deleting, None
            self.delete_note.hide()
            self._delete(m)

    def _cancel_delete(self):
        self.deleting = None
        self.delete_note.hide()

    def _delete(self, m):
        if self.editing and self.editing["id"] == m["id"]:
            self._cancel_edit()
        channel_id = self.channel_id
        self._call("deleteMessage", channel_id, m["id"], on_ok=lambda _: self._forget_message(channel_id, m["id"]),
                   on_err=self._show_error)

    # ---------- reactions ----------

    def _toggle_reaction(self, m, reaction):
        """Clicking a reaction under a message adds yours, or removes it if it's already yours."""
        self._react(m, reaction["emoji"], add=not reaction["me"])

    def _react(self, m, emoji, add=True):
        channel_id = self.channel_id
        if not channel_id:
            return
        emoji = {"id": emoji["id"], "name": emoji["name"]} if emoji.get("id") else {"char": emoji["char"]}
        self._call("react", channel_id, m["id"], emoji, add,
                   on_ok=lambda _: self._refresh_message(channel_id, m["id"]), on_err=self._show_error)

    def _open_reaction_picker(self, m):
        """Right-click → Add reaction: the emoji picker, choosing a reaction for this message."""
        if not self.channel_id or not self.win.get_visible():
            return
        focus = self.win.get_focus()
        self._close_picker(focus_reply=False)
        self.suggestions.hide()
        self.reacting_to = m
        self.reaction_return_focus = focus
        height = max(PICKER_MIN_H, min(PICKER_MAX_H, self.msg_scroll.get_allocated_height() - 12))
        self.picker.open("emoji", height, reacting_to=m["author"])

    # ---------- drafts ----------

    def _update_draft_marks(self):
        """✎ beside chats in the list where you left an unsent message (not the one you're in)."""
        for (kind, row_id), row in self.row_cache.items():
            if kind != "server":
                row.set_draft(row_id != self.channel_id and bool(self.drafts.get(row_id, "").strip()))

    # ---------- sending ----------

    def _send(self):
        content = self.reply.get_text().strip()
        image = self.pending_image
        if (not content and image is None) or not self.channel_id or self.sending:
            return
        self.sending = True
        self.reply.set_sensitive(False)
        channel_id = self.channel_id
        reply_id = self.replying_to["id"] if self.replying_to else None

        def finished(_):
            self.sending = False
            self.typing_sent_to = None  # sending a message ends "typing" on Discord's side
            self.drafts.pop(channel_id, None)
            self._update_draft_marks()
            self.reply.set_sensitive(True)
            if channel_id == self.channel_id:
                self.reply.set_text("")
                self._cancel_reply()
                self._cancel_attachment()
            self._focus_reply()
            self.stick_bottom = True
            GLib.timeout_add(RELOAD_AFTER_SEND_MS, self._load_messages)

        def failed(exc):
            self.sending = False
            self.reply.set_sensitive(True)  # keep the text so it isn't lost
            self._focus_reply()
            self._show_error(exc)

        if image is not None:
            self._call("sendImage", channel_id, content, base64.b64encode(image).decode(), "image.png", reply_id,
                       on_ok=finished, on_err=failed, timeout=UPLOAD_TIMEOUT_SECONDS)
        else:
            self._call("send", channel_id, content, reply_id, on_ok=finished, on_err=failed)

    # ---------- emoji & GIF pickers ----------

    def _toggle_picker(self, page):
        if not self.channel_id or not self.win.get_visible():
            return
        if self.picker.get_visible():
            if self.picker.page == page:
                self._close_picker()
            else:
                self.picker.show_page(page)
        else:
            self.suggestions.hide()
            self.emoji_by_channel.pop(self.channel_id, None)  # refetch so "frequently used" is current
            height = max(PICKER_MIN_H, min(PICKER_MAX_H, self.msg_scroll.get_allocated_height() - 12))
            self.picker.open(page, height)
        for key, btn in self.tool_buttons.items():
            set_class(btn, "active", self.picker.get_visible() and self.picker.page == key)

    def _close_picker(self, focus_reply=True):
        if self.picker.get_visible():
            reacting, back_to = self.reacting_to is not None, self.reaction_return_focus
            self.reacting_to = self.reaction_return_focus = None
            self.picker.close()
            for btn in self.tool_buttons.values():
                set_class(btn, "active", False)
            if reacting and focus_reply:
                (back_to or self.listbox).grab_focus()  # back to where you were before reacting
            elif focus_reply:
                self._focus_reply()

    def _close_picker_if_clicked_away(self):
        """A click outside the open picker closes it, like Esc (its 😀 / GIF buttons keep toggling it)."""
        if not self.picker.get_visible():
            return
        if pointer_inside(self.picker) or any(pointer_inside(b) for b in self.tool_buttons.values()):
            return
        self._close_picker()

    def _with_emoji(self, then):
        """Run then() once the emoji catalog and this channel's emoji are loaded."""
        channel_id = self.channel_id
        if self.emoji_catalog is None:
            def got_catalog(catalog):
                self.emoji_catalog = catalog
                self._with_emoji(then)
            self._call("emojiCatalog", on_ok=got_catalog)
            return
        if channel_id in self.emoji_by_channel:
            then()
            return

        def got_channel(data):
            self.emoji_by_channel[channel_id] = data
            if channel_id == self.channel_id:
                then()
        self._call("emojiForChannel", channel_id, on_ok=got_channel)

    def channel_emoji(self):
        return self.emoji_by_channel.get(self.channel_id) or {"frecent": [], "custom": []}

    def emoji_entries(self):
        """Everything searchable: this channel's usable server emoji, then all built-in emoji."""
        return all_emoji(self.emoji_catalog, self.channel_emoji())

    def _insert_emoji(self, entry):
        if self.reacting_to:  # the picker was choosing a reaction
            m = self.reacting_to
            self._close_picker()
            self._react(m, entry)
            return
        self._close_picker(focus_reply=False)
        self._focus_reply()
        self.reply.set_position(self.reply.insert_text(emoji_text(entry), self.reply.get_position()))

    def _send_gif(self, url):
        channel_id = self.channel_id
        self._close_picker()
        if channel_id:
            self.stick_bottom = True
            reply_id = self.replying_to["id"] if self.replying_to else None
            self._cancel_reply()
            self._call("send", channel_id, url, reply_id,
                       on_ok=lambda _: GLib.timeout_add(RELOAD_AFTER_SEND_MS, self._load_messages))

    def _focus_reply(self):
        self.reply.grab_focus_without_selecting()

    def _report_typing(self):
        """Let the other side see "… is typing" while you type here, like Discord's own message box."""
        if not self.channel_id or not self.reply.has_focus():
            return  # e.g. a draft being restored, not you typing
        if not self.reply.get_text():
            if self.typing_sent_to:
                self._call("stopTyping", self.typing_sent_to, on_err=lambda _exc: None)
                self.typing_sent_to = None
            return
        now = time.monotonic()
        if self.typing_sent_to != self.channel_id or now - self.typing_sent_at > TYPING_REPORT_SECONDS:
            self.typing_sent_to, self.typing_sent_at = self.channel_id, now
            self._call("startTyping", self.channel_id, on_err=lambda _exc: None)

    def _update_suggestions(self):
        """Show emoji suggestions while typing :name (at least two letters after the colon)."""
        if not self.reply.has_focus() or self.picker.get_visible():
            self.suggestions.hide()
            return
        before = self.reply.get_text()[:self.reply.get_position()]
        match = re.search(r"(?:^|\s):([^\s:]{2,})$", before)
        if not match:
            self.suggestions.hide()
            return
        if self.emoji_catalog is None or self.channel_id not in self.emoji_by_channel:
            self._with_emoji(self._update_suggestions)
            return
        frecent = [e["name"] for e in self.channel_emoji()["frecent"]]
        items = match_emoji(self.emoji_entries(), match.group(1), SUGGESTION_COUNT, frecent)
        if items:
            self.suggestion_start = match.start(1) - 1  # index of the ':'
            self.suggestions.show_items(items)
        else:
            self.suggestions.hide()

    def _accept_suggestion(self, entry):
        if entry is None:
            return
        text, pos = self.reply.get_text(), self.reply.get_position()
        insert = emoji_text(entry)
        self.reply.set_text(text[:self.suggestion_start] + insert + text[pos:])
        self.suggestions.hide()
        self._focus_reply()
        self.reply.set_position(self.suggestion_start + len(insert))


def shift_held():
    """Is Shift down for the click / key being handled now?"""
    ok, state = Gtk.get_current_event_state()
    return ok and bool(state & Gdk.ModifierType.SHIFT_MASK)
