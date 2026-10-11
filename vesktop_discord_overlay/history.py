"""Chat history: Ctrl+Left / Ctrl+Right, Ctrl+Shift+Left (prune), Ctrl+Shift+Right (show in sidebar) and
Ctrl+Shift+Down (clear). Remembered across restarts in state.json."""

from . import state
from .config import HISTORY_LENGTH, NOTE_SHOW_MS


class HistoryMixin:
    """Part of Overlay (shares its state); see overlay.py."""

    # ---------- chat history (Ctrl+Left / Ctrl+Right) ----------

    def _record_visit(self, channel_id, guild_id):
        """Opening a chat yourself makes it the newest entry (a chat appears only once)."""
        self.history = [e for e in self.history if e["id"] != channel_id]
        self.history.append({"id": channel_id, "guildId": guild_id, "name": ""})
        self.history = self.history[-HISTORY_LENGTH:]
        self.history_pos = len(self.history) - 1
        self.history_gap = None
        self._forget_left_chats()
        self._save_history()

    def _step_history(self, delta):
        """Walk the history without reordering it, wrapping at the ends; the sidebar stays as it is."""
        if not self.history or not self.win.get_visible():
            return
        if self.history_gap is not None:  # just pruned: continue from the gap it left
            self.history_pos = (self.history_gap - 1 if delta < 0 else self.history_gap) % len(self.history)
            self.history_gap = None
        elif len(self.history) < 2:
            return
        else:
            self.history_pos = (self.history_pos + delta) % len(self.history)
        entry = self.history[self.history_pos]
        self.history_step = delta  # if this chat can't open any more, the next step skips it
        focus = self.win.get_focus()
        self._close_picker(focus_reply=False)
        # Only the open chat changes; the sidebar stays as it is (Ctrl+Shift+Right brings it to the chat).
        self._open_conversation(entry["id"], from_history=True)
        self.open_guild_id = entry["guildId"]
        if focus is self.reply:  # focus stays where it was
            self._focus_reply()
        elif focus is self.listbox:
            self.listbox.grab_focus()
        label_text = f"{self.history_pos + 1} / {len(self.history)}"
        self._flash(f"{label_text} · {entry['name']}" if entry["name"] else label_text, NOTE_SHOW_MS)

    def _show_chat_in_sidebar(self):
        """Ctrl+Shift+Right: show the open chat in the sidebar, in Friends or in its server's channels,
        highlighted. Clears any search that would hide it; focus stays where it was."""
        if not self.channel_id:
            return
        focus = self.win.get_focus()
        self.search.set_text("")
        guild_id = self.open_guild_id
        if guild_id:
            self.tab = "servers"
            if not self.server or self.server["id"] != guild_id:
                name = next((s["name"] for s in self.servers if s["id"] == guild_id), "")
                self.server = {"id": guild_id, "name": name}
                self.channels = []
                self._call("channels", guild_id, on_ok=lambda chans: self._on_channels(guild_id, chans))
        else:
            self.tab = "friends"
        self._update_tab_buttons()
        self._render_sidebar()
        self._highlight_id(self.channel_id)
        if focus is self.reply:
            self._focus_reply()
        elif focus is self.listbox:
            self.listbox.grab_focus()

    def _prune_history(self):
        """Ctrl+Shift+Left: drop the open chat from the history and close it ("tidy up")."""
        index = next((i for i, e in enumerate(self.history) if e["id"] == self.channel_id), None)
        if index is None:
            return
        name = self.history[index]["name"]
        del self.history[index]
        self.history_gap = index  # Ctrl+Left / Right continue from here
        self._close_conversation()
        self._forget_left_chats()
        self._save_history()
        self.listbox.grab_focus()
        self._flash(f"Removed {name} from history" if name else "Removed from history", NOTE_SHOW_MS)

    def _forget_left_chats(self):
        """Older messages you scrolled back to, and where you were reading, are kept only for chats still in
        the history (and the open one); a chat that has left it opens fresh at its newest messages."""
        keep = {entry["id"] for entry in self.history} | {self.channel_id}
        for store in (self.older, self.scroll_memory):
            for channel_id in [c for c in store if c not in keep]:
                del store[channel_id]
        self.history_done &= keep

    def _save_history(self):
        state.save(history=self.history)

    def _drop_unreachable_history(self, channel_id):
        """A chat in the history that can't open any more (you left the server, the DM is gone): drop it quietly
        and step on to the next one. True if it did."""
        index = next((i for i, e in enumerate(self.history) if e["id"] == channel_id), None)
        if not self.history_step or index is None:
            return False
        del self.history[index]
        self._save_history()
        step, self.history_step = self.history_step, 0
        if not self.history:
            self._close_conversation()
            return True
        self.history_gap = index
        self.channel_id = None  # so the next chat opens even if it's this one's neighbour
        self._step_history(step)
        return True

    # ---------- clearing the whole history (Ctrl+Shift+Down) ----------

    def _ask_clear_history(self):
        if not self.history:
            self._flash("The chat history is already empty", NOTE_SHOW_MS)
            return
        count = len(self.history)
        self.clearing_history = True
        self.clear_note_label.set_text(f"Clear chat history ({count} chat{'s' if count != 1 else ''})? "
                                       "Enter clears, Esc cancels")
        self.clear_note.show()

    def _confirm_clear_history(self):
        if not self.clearing_history:
            return
        self._cancel_clear_history()
        self.history, self.history_pos, self.history_gap = [], -1, None
        self._forget_left_chats()
        self._save_history()
        self._flash("Chat history cleared", NOTE_SHOW_MS)

    def _cancel_clear_history(self):
        self.clearing_history = False
        self.clear_note.hide()
