"""The overlay panel: window, layout, show / hide, keyboard and voice; see the mixins for the rest."""

import asyncio
import json
import os
import signal
import sys
import time

from . import __version__, instance, state
from .bridge import VesktopBridge
from .compose import ComposeMixin
from .config import (CHAT_POLL_MS, CLICK_AWAY_CHECK_MS, CLICK_AWAY_GRACE_SECONDS, DEBUG_PORT, ERROR_MAX_CHARS,
                     ERROR_SHOW_MS, FOCUS_DELAY_MS, FOLLOW_CHECK_SECONDS, FOLLOW_STARTUP_GRACE, HEADER_AVATAR,
                     HELP_HOVER_CHECK_MS, HELP_HOVER_SIZE, HOTKEY_KEYSYM, HOTKEY_LABEL, HOTKEY_MODIFIERS,
                     LIST_POLL_MS, LIVE_LIST_REFRESH_MS, NOTE_SHOW_MS, OPACITY_MIN, OPACITY_STEP, PANEL_MAX_H,
                     PANEL_MAX_W, PANEL_SCREEN_H, PANEL_SCREEN_W, SIDEBAR_W, USER_AVATAR, VESKTOP_FOCUS_DELAY_MS,
                     VOICE_SETTLE_SECONDS)
from .gtk import Gdk, GLib, Gtk, HAVE_WEBKIT, WebKit2
from .history import HistoryMixin
from .hotkey import HotkeyListener
from .media import Avatar, MediaCache, Picture
from .messages import MessagesMixin, message_box
from .pickers import Picker, Suggestions
from .shortcuts import help_popover
from .sidebar import SidebarMixin
from .preflight import tell
from .system import activate_vesktop_window, other_vesktop_running, run_quiet, vesktop_running
from .theme import CSS, STATUS_COLORS
from .viewer import Viewer
from .widgets import add_class, fill_menu, label, pointer_inside, set_class


class Overlay(SidebarMixin, MessagesMixin, ComposeMixin, HistoryMixin):
    """The panel: window, layout, show / hide, keyboard, voice. The rest lives in the mixins."""

    def __init__(self):
        self.bridge = VesktopBridge(DEBUG_PORT)
        self.images = MediaCache()
        self.media_views = []
        self.shown_at = 0.0

        self.tab = "friends"
        self.server = None  # {"id", "name"} while drilled into a server
        self.friends = []
        self.servers = []
        self.channels = []
        self.rows = []
        self.row_cache = {}
        self.list_key = None

        self.channel_id = None
        self.open_guild_id = None  # server of the open conversation, if any
        self.rendered_key = None
        self.stick_bottom = True
        self.drafts = {}
        self.prev_window = None
        self.poll_sources = []
        self.list_refresh_pending = False
        self.loading_chat = None  # channel whose messages are being read right now
        self.reload_wanted = False  # it changed while being read: read it again when that finishes
        self.sending = False
        self.first_open = True
        self.busy_calls = set()
        self.typing_sent_to = None
        self.typing_sent_at = 0.0
        self.revealed = {}  # message id -> spoiler numbers clicked open (only messages where you did)
        self.marked_read = {}  # channel id -> newest message id we've marked read
        self.typing_now = {}  # channel id -> names typing there, pushed live by Vesktop
        self.context_menu = None
        self.opacity = min(1.0, max(OPACITY_MIN, float(state.load().get("opacity", 1.0))))
        self.replying_to = None  # message the next send replies to
        self.editing = None  # your message being edited in the reply box
        self.edit_original = ""  # its text when editing began
        self.edit_stash = None  # (draft, cursor, reply, pasted image) set aside while editing
        self.deleting = None  # your message waiting for "Delete this message?"
        self.reacting_to = None  # message the emoji picker is choosing a reaction for
        self.reaction_return_focus = None
        self.jump_target = None  # (channel, message id, batches tried) while loading back to a reply's original
        self.status = None  # your status as last shown on the status button
        self.status_set_at = -VOICE_SETTLE_SECONDS
        self.history = []  # chats you opened, oldest first; each appears once (see _record_visit)
        self.history_pos = -1
        self.history_gap = None  # index a pruned chat left, while no chat is open after pruning
        self.scroll_memory = {}  # channel id -> (message id at the top of the view, its offset) when you left
        self.restore_to = None
        self.pending_image = None  # PNG bytes pasted into the reply box, sent with the next message
        self.new_marker = None  # first unread message id of the open chat, for the NEW line
        self.new_marker_for = None
        self.seen_newest = None  # newest message id you've seen at the bottom (for the jump pill)
        self.typing_live = False
        self.bridge.on_event = lambda payload: GLib.idle_add(self._on_bridge_event, payload)
        self.voice_state = {"mute": False, "deaf": False, "channel": None}  # as last shown on the buttons
        self.voice_pressed_at = -VOICE_SETTLE_SECONDS
        self.latest = []  # newest messages of the open chat, as last polled
        self.older = {}  # channel id -> older history loaded by scrolling up (oldest first)
        self.history_done = set()  # channels whose whole history is loaded
        self.loading_older = False
        self.anchor = None  # (message id, offset from top of view, expiry) while older messages settle in
        self.message_widgets = {}  # message id -> its body, oldest first
        self.blocks = {}  # what the message pane shows: block key -> widget, in order (see _render_messages)
        self.blocks_for = None  # the chat those blocks belong to (reopening it, or the panel, reuses them)
        self.discarding = []  # widgets waiting to be destroyed, a batch at a time (see _discard)
        self.discard_source = None
        self.history_label = None
        self.player_view = None  # the message media currently showing the YouTube player
        self.kept_player = None  # (media key, player, had focus) while a re-render is in progress
        self.emoji_catalog = None
        self.emoji_by_channel = {}
        self.suggestion_start = 0

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.Settings.get_default().props.gtk_application_prefer_dark_theme = True
        self._build_ui()

        self.hotkey = HotkeyListener(HOTKEY_KEYSYM, HOTKEY_MODIFIERS, lambda: GLib.idle_add(self.toggle))
        self.hotkey.start()
        self.hotkey.ready.wait(3)
        if self.hotkey.failure:
            tell(f"{self.hotkey.failure} ({HOTKEY_LABEL}; pick another in config.py)")
            raise SystemExit(1)

    # ---------- UI construction ----------

    def _build_ui(self):
        win = self.win = Gtk.Window(title="vesktop-discord-overlay")
        add_class(win, "vesktop-overlay")
        win.set_decorated(False)
        win.set_keep_above(True)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)
        win.set_opacity(self.opacity)  # Ctrl+Up / Ctrl+Down; needs a compositor (Cinnamon has one)
        win.connect("key-press-event", self._on_key)
        win.connect("delete-event", lambda *_: self.hide() or True)
        win.connect("focus-out-event", self._on_focus_out)
        # Sees every click in the panel before the widget clicked does (without stopping it): clicking outside
        # an open picker closes it, and the click still does its usual thing.
        self.click_watch = Gtk.GestureMultiPress.new(win)
        self.click_watch.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.click_watch.set_button(0)  # any button
        self.click_watch.connect("pressed", lambda *_: self._close_picker_if_clicked_away())

        # The viewer floats over the whole panel, so the window's content sits in an overlay.
        root = Gtk.Overlay()
        win.add(root)
        root.show()
        outer = Gtk.Box(spacing=0, margin=1)
        root.add(outer)
        self.viewer = Viewer(self.images, lambda text: self._flash(text, NOTE_SHOW_MS))
        root.add_overlay(self.viewer)

        # Sidebar: tabs, search, back button, cards.
        side = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "sidebar")
        side.set_size_request(SIDEBAR_W, -1)
        outer.pack_start(side, False, False, 0)

        tabs = Gtk.Box(spacing=4, margin_start=10, margin_end=10, margin_top=10, margin_bottom=6)
        self.tab_buttons = {}
        self.tab_badges = {}
        self.tab_dots = {}
        for key, title in (("friends", "Friends"), ("servers", "Servers")):
            content = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
            content.pack_start(Gtk.Label(label=title), False, False, 0)
            badge = label("", "badge", xalign=0.5)
            badge.set_no_show_all(True)
            content.pack_start(badge, False, False, 0)
            dot = label("●", "dot", xalign=0.5)  # unread, but no pings
            dot.set_no_show_all(True)
            content.pack_start(dot, False, False, 0)
            self.tab_dots[key] = dot
            btn = add_class(Gtk.Button(), "tab")
            btn.add(content)
            btn.set_can_focus(False)
            btn.connect("clicked", lambda _b, k=key: self._set_tab(k))
            tabs.pack_start(btn, True, True, 0)
            self.tab_buttons[key] = btn
            self.tab_badges[key] = badge
        side.pack_start(tabs, False, False, 0)
        self._update_tab_buttons()

        self.search = add_class(Gtk.Entry(), "search")
        self.search.set_placeholder_text("Search")
        self.search.set_margin_start(10)
        self.search.set_margin_end(10)
        self.search.set_margin_bottom(6)
        self.search.connect("changed", lambda *_: self._refilter())
        side.pack_start(self.search, False, False, 0)

        self.back = add_class(Gtk.Button(), "back")
        self.back.set_can_focus(False)
        self.back.set_margin_start(8)
        self.back.set_margin_end(8)
        self.back.set_no_show_all(True)
        self.back_label = label("", ellipsize=True)
        self.back.add(self.back_label)
        self.back_label.show()
        self.back.connect("clicked", lambda *_: self._leave_server())
        side.pack_start(self.back, False, False, 0)

        self.listbox = add_class(Gtk.ListBox(), "cards")
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_can_focus(True)  # arrow-key navigation zone; see _list_key
        self.listbox.set_filter_func(self._filter_row)
        self.listbox.connect("row-activated", lambda _lb, row: self._activate(row))
        self.listbox.connect("button-press-event", self._list_menu)
        self.list_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.list_scroll.add(self.listbox)
        side.pack_start(self.list_scroll, True, True, 4)

        # You, at the bottom of the sidebar like Discord's user panel: click to change your status.
        user_bar = add_class(Gtk.Box(), "user-bar")
        self.user_panel = add_class(Gtk.Button(), "user-panel")
        self.user_panel.set_can_focus(False)
        self.user_panel.set_tooltip_text("Click to change your status")
        panel_content = Gtk.Box(spacing=10)
        self.user_avatar = Avatar(self.images, USER_AVATAR)
        panel_content.pack_start(self.user_avatar, False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.user_name = label("", "user-name", ellipsize=True)
        self.user_status = label("", "user-status")
        names.pack_start(self.user_name, False, False, 0)
        names.pack_start(self.user_status, False, False, 0)
        panel_content.pack_start(names, True, True, 0)
        self.user_panel.add(panel_content)
        self.user_panel.connect("clicked", lambda *_: self._status_menu())
        user_bar.pack_start(self.user_panel, True, True, 0)
        side.pack_end(user_bar, False, False, 0)
        self.me = {"name": "", "avatar": None}

        # Main pane: header, messages, reply box, voice bar.
        main = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "main")
        outer.pack_start(main, True, True, 0)

        header = self.header = add_class(Gtk.Box(spacing=10), "header")
        self.header_avatar = Avatar(self.images, HEADER_AVATAR)
        header.pack_start(self.header_avatar, False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        name_row = Gtk.Box(spacing=10)
        self.header_name = label("", "header-name", ellipsize=True)
        self.header_place = label("", "header-place")
        name_row.pack_start(self.header_name, False, False, 0)
        name_row.pack_start(self.header_place, False, False, 0)
        titles.pack_start(name_row, False, False, 0)
        self.typing = label("", "typing")
        titles.pack_start(self.typing, False, False, 0)
        header.pack_start(titles, True, True, 0)
        main.pack_start(header, False, False, 0)

        self.msg_box = message_box()
        self.msg_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.msg_scroll.add(self.msg_box)
        adj = self.msg_scroll.get_vadjustment()
        adj.connect("changed", self._keep_bottom)
        adj.connect("value-changed", self._track_bottom)
        # Pickers and the ':' suggestions float over the bottom of the messages.
        layer = Gtk.Overlay()
        layer.add(self.msg_scroll)
        self.picker = Picker(self)
        self.picker.set_margin_start(12)
        self.picker.set_margin_end(12)
        self.picker.set_margin_bottom(6)
        layer.add_overlay(self.picker)
        self.jump_pill = add_class(Gtk.Button(label="New messages ↓"), "jump-pill")
        self.jump_pill.set_can_focus(False)
        self.jump_pill.set_halign(Gtk.Align.CENTER)
        self.jump_pill.set_valign(Gtk.Align.END)
        self.jump_pill.set_margin_bottom(10)
        self.jump_pill.set_no_show_all(True)
        self.jump_pill.connect("clicked", self._jump_to_newest)
        layer.add_overlay(self.jump_pill)
        self.suggestions = Suggestions(self.images, self._accept_suggestion)
        self.suggestions.set_margin_start(16)
        self.suggestions.set_margin_bottom(6)
        layer.add_overlay(self.suggestions)
        main.pack_start(layer, True, True, 0)
        self.chat_layer = layer
        # With no chat open the chat layer is hidden (a closed chat stays in it, ready to reopen) and this shows.
        self.empty_hint = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, valign=Gtk.Align.CENTER)
        self.empty_hint.pack_start(label("→  open a chat", "empty-hint", xalign=0.5), False, False, 0)
        self.empty_hint.pack_start(label("Ctrl+Tab switches Friends / Servers  ·  F1 shows every shortcut",
                                         "empty-tip", xalign=0.5), False, False, 0)
        self.empty_hint.show_all()
        self.empty_hint.set_no_show_all(True)
        self.empty_hint.hide()
        main.pack_start(self.empty_hint, True, True, 0)

        # Above the reply box: the message you're replying to or editing, a pasted image waiting to be sent,
        # and "Delete this message?".
        self.compose = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_start=16, margin_end=16,
                               margin_bottom=4)
        self.reply_note = add_class(Gtk.Box(spacing=8), "compose-note")
        self.reply_note_label = label("", "compose-text", ellipsize=True)
        self.reply_note.pack_start(self.reply_note_label, True, True, 0)
        self.reply_note.pack_start(self._small_close_button(self._cancel_reply), False, False, 0)
        self.attach_note = add_class(Gtk.Box(spacing=8), "compose-note")
        self.attach_thumb = Picture(36, 36, cover=True)
        self.attach_note.pack_start(self.attach_thumb, False, False, 0)
        self.attach_label = label("", "compose-text")
        self.attach_note.pack_start(self.attach_label, True, True, 0)
        self.attach_note.pack_start(self._small_close_button(self._cancel_attachment), False, False, 0)
        self.edit_note = add_class(Gtk.Box(spacing=8), "compose-note")
        edit_text = label("Editing message · Enter saves, Esc cancels", "compose-text")
        self.edit_note.pack_start(edit_text, True, True, 0)
        self.edit_note.pack_start(self._small_close_button(self._cancel_edit), False, False, 0)
        self.delete_note = add_class(Gtk.Box(spacing=8), "compose-note", "danger")
        self.delete_note.pack_start(label("Delete this message? Enter deletes, Esc cancels", "compose-text"),
                                    True, True, 0)
        delete_btn = add_class(Gtk.Button(label="Delete"), "danger")
        delete_btn.set_can_focus(False)
        delete_btn.connect("clicked", lambda *_: self._confirm_delete())
        cancel_btn = add_class(Gtk.Button(label="Cancel"), "plain")
        cancel_btn.set_can_focus(False)
        cancel_btn.connect("clicked", lambda *_: self._cancel_delete())
        self.delete_note.pack_start(cancel_btn, False, False, 0)
        self.delete_note.pack_start(delete_btn, False, False, 0)
        for note in (self.reply_note, self.edit_note, self.attach_note, self.delete_note):
            note.show_all()
            note.set_no_show_all(True)
            note.hide()
            self.compose.pack_start(note, False, False, 0)
        main.pack_start(self.compose, False, False, 0)

        self.reply_row = Gtk.Box(spacing=6, margin_start=16, margin_end=16, margin_bottom=10)
        self.reply = add_class(Gtk.Entry(), "reply")
        self.reply.connect("paste-clipboard", self._on_paste)
        self.reply.connect("changed", lambda *_: (self._update_suggestions(), self._report_typing()))
        self.reply.connect("notify::cursor-position", lambda *_: self._update_suggestions())
        self.reply.connect("focus-out-event", lambda *_: self.suggestions.hide() or False)
        self.reply_row.pack_start(self.reply, True, True, 0)
        self.tool_buttons = {}
        for key, text, keys in (("emoji", "😀", "Ctrl+E"), ("gif", "GIF", "Ctrl+G")):
            btn, _ = self._keyed_button(text, keys, "tool", lambda k=key: self._toggle_picker(k))
            self.reply_row.pack_start(btn, False, False, 0)
            self.tool_buttons[key] = btn
        main.pack_start(self.reply_row, False, False, 0)

        bar = add_class(Gtk.Box(spacing=6), "bar")
        self.mute_btn, self.mute_text = self._keyed_button("Mute", "Ctrl+M", "voice",
                                                           lambda: self._voice("toggleMute"))
        self.deaf_btn, self.deaf_text = self._keyed_button("Deafen", "Ctrl+D", "voice",
                                                           lambda: self._voice("toggleDeaf"))
        bar.pack_start(self.mute_btn, False, False, 0)
        bar.pack_start(self.deaf_btn, False, False, 0)
        # The "?" (hover it, or F1) lists every shortcut; errors briefly show beside it.
        self.help_icon = add_class(Gtk.Label(label="?"), "help-icon")
        help_box = Gtk.EventBox()
        help_box.set_size_request(HELP_HOVER_SIZE, HELP_HOVER_SIZE)  # a forgiving hover target around the "?"
        help_box.set_valign(Gtk.Align.CENTER)
        self.help_icon.set_halign(Gtk.Align.CENTER)
        self.help_icon.set_valign(Gtk.Align.CENTER)
        help_box.add(self.help_icon)
        help_box.connect("enter-notify-event", lambda *_: self._help_hover())
        help_box.connect("leave-notify-event", lambda *_: self._help_maybe_close())
        bar.pack_end(help_box, False, False, 4)
        self.help_box = help_box
        self.help = help_popover(help_box)
        self.help.connect("leave-notify-event", lambda *_: self._help_maybe_close())
        self.help_by_hover = False
        self.help_timer = None
        self.error_label = label("", "error-text", xalign=1.0, ellipsize=True)
        self.error_label.set_no_show_all(True)
        # While showing, an error gets room before the voice label.
        self.error_label.set_max_width_chars(ERROR_MAX_CHARS)
        bar.pack_end(self.error_label, False, False, 6)
        # The voice channel you're in, with Disconnect beside it; together they get the rest of the bar.
        voice_box = Gtk.Box(spacing=8)
        voice_box.set_margin_start(6)
        # Like Discord: a green "Voice connected" with the channel under it, or a grey "Not in voice".
        voice_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.voice_label = label("", "voice-label", ellipsize=True)
        self.voice_channel = label("", "voice-channel", ellipsize=True)
        self.voice_channel.set_no_show_all(True)
        voice_text.pack_start(self.voice_label, False, False, 0)
        voice_text.pack_start(self.voice_channel, False, False, 0)
        voice_box.pack_start(voice_text, False, True, 0)
        self.disconnect_btn, _ = self._keyed_button("Disconnect", "Ctrl+Shift+D", "voice",
                                                    self._disconnect_voice)
        self.disconnect_btn.show_all()
        self.disconnect_btn.set_no_show_all(True)  # only while you're in a voice channel
        self.disconnect_btn.hide()
        voice_box.pack_start(self.disconnect_btn, False, False, 0)
        bar.pack_start(voice_box, True, True, 0)
        main.pack_start(bar, False, False, 0)
        self.bottom_rows = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.VERTICAL)  # user panel and bottom bar line up
        self.bottom_rows.add_widget(user_bar)
        self.bottom_rows.add_widget(bar)
        self.error_timer = None

        outer.show_all()

    def _keyed_button(self, text, keys, css_class, on_click):
        """A button with its keyboard shortcut shown on it (Mute, Deafen, Disconnect, 😀, GIF)."""
        btn = add_class(Gtk.Button(), css_class)
        btn.set_can_focus(False)
        content = Gtk.Box(spacing=8)
        text_label = Gtk.Label(label=text)
        content.pack_start(text_label, False, False, 0)
        content.pack_start(label(keys, "keycap"), False, False, 0)
        btn.add(content)
        btn.connect("clicked", lambda *_: on_click())
        return btn, text_label

    # ---------- plumbing ----------

    def _call(self, method, *args, on_ok=None, on_err=None, skip_if_busy=False, timeout=10):
        """Run a bridge call in the background; callbacks run on the GTK thread.

        skip_if_busy: for polling, don't start an identical call while the previous one is still waiting
        (otherwise a slow Vesktop gets a growing pile of requests and a matching pile of errors).
        """
        key = (method, json.dumps(args))
        if skip_if_busy:
            if key in self.busy_calls:
                return
            self.busy_calls.add(key)
        future = self.bridge.call(method, *args, timeout=timeout)

        def done(f):
            self.busy_calls.discard(key)
            try:
                result = f.result()
            except Exception as exc:  # noqa: BLE001 - surfaced in the UI
                GLib.idle_add(on_err or self._show_error, exc)
                return
            if on_ok:
                GLib.idle_add(on_ok, result)

        future.add_done_callback(done)

    def _popup_menu(self, items, event, widget=None, markup=False):
        """A menu (see fill_menu): at the pointer (right-click), or above a widget (a button)."""
        menu = Gtk.Menu()
        fill_menu(menu, items, markup)
        menu.attach_to_widget(self.win)
        menu.show_all()
        if widget is not None:
            menu.popup_at_widget(widget, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, None)
        else:
            menu.popup_at_pointer(event)
        self.context_menu = menu  # keep it alive while it's open
        return True

    # ---------- shortcut list ("?") ----------

    def _help_hover(self):
        self.help_by_hover = True
        self.help.popup()

    def _help_maybe_close(self):
        # A "leave" isn't trusted on its own: the list's shadow can overlap the "?" as it appears, which
        # reports a leave while the mouse hasn't moved. Check where the pointer really is a moment later.
        if self.help_by_hover and self.help_timer is None:
            self.help_timer = GLib.timeout_add(HELP_HOVER_CHECK_MS, self._help_close_if_away)
        return False

    def _help_close_if_away(self):
        self.help_timer = None
        if not (self.help_by_hover and self.help.get_visible()):
            return False
        if pointer_inside(self.help_box) or pointer_inside(self.help):
            # Still hovering; look again.
            self.help_timer = GLib.timeout_add(HELP_HOVER_CHECK_MS, self._help_close_if_away)
        else:
            self.help.popdown()
        return False

    def _show_error(self, exc):
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            text = "Vesktop didn't respond in time"
        else:
            lines = str(exc).splitlines()
            text = lines[0][:90] if lines else type(exc).__name__
        self.error_label.set_tooltip_text(text)
        self._flash(f"Error: {text}", ERROR_SHOW_MS, error=True)

    def _flash(self, text, ms, error=False):
        """A short message in the bottom bar: errors (red) or notes like the opacity level (grey)."""
        self.error_label.set_text(text)
        set_class(self.error_label, "note", not error)
        self.error_label.show()
        if self.error_timer:
            GLib.source_remove(self.error_timer)
        self.error_timer = GLib.timeout_add(ms, self._clear_error)

    def _change_opacity(self, delta):
        self.opacity = round(min(1.0, max(OPACITY_MIN, self.opacity + delta)), 2)
        self.win.set_opacity(self.opacity)
        state.save(opacity=self.opacity)
        self._flash(f"Opacity {round(self.opacity * 100)}%", NOTE_SHOW_MS)

    def _clear_error(self):
        self.error_timer = None
        self.error_label.hide()
        return False

    # ---------- show / hide ----------

    def toggle(self):
        if self.win.get_visible():
            self.hide()
        else:
            self.show()
        return False

    def show(self):
        if not vesktop_running():
            # Say why nothing opens, instead of silently doing nothing.
            if other_vesktop_running():
                tell("Vesktop is running, but not the Flatpak version, which is the one the overlay works with.")
            else:
                tell("Vesktop isn't running. Start it from the Vesktop Discord Overlay menu entry.")
            return
        self.prev_window = run_quiet(["xdotool", "getactivewindow"]) or None
        self._place_window()
        self.shown_at = time.monotonic()
        self.win.show()
        for view in self.media_views:
            view.set_active(True)
        GLib.timeout_add(FOCUS_DELAY_MS, self._grab_focus)

        if not self.bridge.port_open():
            self.header.show()
            self._set_header("Vesktop isn't reachable", "", None)
            self._render_info(
                "Vesktop is running without the debug port, so the overlay can't talk to it.\n\n"
                "Quit Vesktop from its tray icon (Quit, not just closing the window), then start it with:\n\n"
                f"    flatpak run dev.vencord.Vesktop --remote-debugging-port={DEBUG_PORT}\n\n"
                "Press Esc to close.")
            self._set_rows([], "none")
            return

        self.search.set_text("")
        if self.first_open:
            # First open: start wherever Vesktop currently is.
            self.first_open = False
            self._call("current", on_ok=self._on_current)
        else:
            self._refresh_lists()
            if self.channel_id:
                self._load_messages()
            else:
                self._show_empty()
        self._refresh_voice()
        self.poll_sources = [GLib.timeout_add(LIST_POLL_MS, self._poll_lists),
                             GLib.timeout_add(CHAT_POLL_MS, self._poll_chat)]

    def _on_current(self, cur):
        if cur and cur["guildId"]:
            self.tab = "servers"
            self.server = {"id": cur["guildId"], "name": ""}
        if cur:
            self._open_conversation(cur["id"])
        else:
            self._show_empty()
        self._update_tab_buttons()
        self._refresh_lists()

    def _grab_focus(self):
        gdk_win = self.win.get_window()
        if gdk_win:
            # The window manager ignores plain focus requests from background apps; ask it to activate us.
            run_quiet(["xdotool", "windowactivate", str(gdk_win.get_xid())])
        self.win.present()
        self._focus_list()  # arrows work right away; typing a letter jumps to search
        return False

    def hide(self):
        for source in self.poll_sources:
            GLib.source_remove(source)
        self.poll_sources = []
        self._cancel_delete()
        self._cancel_edit()  # before saving the draft, so the draft is your own text, not the edit
        self._save_draft()
        self._update_draft_marks()
        self._close_picker(focus_reply=False)
        self._stop_youtube()
        self.help.popdown()
        self.viewer.close()
        self.new_marker_for = None  # next time, show the NEW line for whatever is unread then
        for view in self.media_views:
            view.set_active(False)
        self.win.hide()
        if self.prev_window:
            run_quiet(["xdotool", "windowactivate", self.prev_window])
            self.prev_window = None

    def _place_window(self):
        display = Gdk.Display.get_default()
        _, x, y = display.get_default_seat().get_pointer().get_position()
        geo = display.get_monitor_at_point(x, y).get_geometry()
        w = min(PANEL_MAX_W, int(geo.width * PANEL_SCREEN_W))
        h = min(PANEL_MAX_H, int(geo.height * PANEL_SCREEN_H))
        self.win.resize(w, h)
        self.win.move(geo.x + (geo.width - w) // 2, geo.y + (geo.height - h) // 2)

    def _poll_lists(self):
        self._refresh_lists()
        self._refresh_voice()
        return True

    def _poll_chat(self):
        # Only a safety net: Vesktop reports changes to chats as they happen (see _on_bridge_event).
        if self.channel_id:
            self._load_messages()
        return True

    def _on_bridge_event(self, payload):
        """Things Vesktop pushes as they happen (see bridge.js): chats that changed, and who's typing where."""
        try:
            event = json.loads(payload)
        except ValueError:
            return False
        if event.get("type") == "typing":
            self.typing_live = True
            self.typing_now = event["channels"]
            if self.channel_id:
                self._set_typing(self.typing_now.get(self.channel_id, []))
            for (kind, channel_id), row in self.row_cache.items():
                if kind == "friend":
                    row.set_typing(channel_id in self.typing_now)
        elif event.get("type") == "chats" and self.win.get_visible():
            if self.channel_id in event["channels"]:
                self._load_messages()
            if not self.list_refresh_pending:  # unread dots and badges, without a refresh per message
                self.list_refresh_pending = True
                GLib.timeout_add(LIVE_LIST_REFRESH_MS, self._live_list_refresh)
        return False

    def _live_list_refresh(self):
        self.list_refresh_pending = False
        if self.win.get_visible():
            self._refresh_lists()
        return False

    # ---------- keyboard ----------

    def _on_key(self, _win, event):
        name = Gdk.keyval_name(event.keyval) or ""
        if self.viewer.get_visible():
            if name == "Escape":
                self.viewer.close()
            elif name in ("Left", "Right"):
                self.viewer.step(-1 if name == "Left" else 1)
            return True  # nothing typed while viewing should land in the reply box behind it
        if self.help.get_visible():
            self.help.popdown()
            if name in ("F1", "Escape"):
                return True
        elif name == "F1":
            self.help_by_hover = False  # stays until a key closes it, wherever the mouse is
            self.help.popup()
            return True
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            lower = name.lower()
            if name in ("Tab", "ISO_Left_Tab"):
                self._set_tab("servers" if self.tab == "friends" else "friends")
            elif lower == "m":
                self._voice("toggleMute")
            elif lower == "d" and event.state & Gdk.ModifierType.SHIFT_MASK:
                self._disconnect_voice()
            elif lower == "d":
                self._voice("toggleDeaf")
            elif name in ("Up", "Down"):
                self._change_opacity(OPACITY_STEP if name == "Up" else -OPACITY_STEP)
            elif name in ("Left", "Right") and event.state & Gdk.ModifierType.SHIFT_MASK:
                if name == "Left":
                    self._prune_history()
                else:
                    self._show_chat_in_sidebar()
            elif name in ("Left", "Right"):
                self._step_history(-1 if name == "Left" else 1)
            elif lower in ("e", "g") and self.win.get_focus() in (self.reply, self.picker.search):
                # Only from the reply box (or inside an open picker): that's where the emoji / GIF goes.
                # A reaction can't be a GIF, so Ctrl+G does nothing while choosing one.
                if not (self.picker.reacting and lower == "g"):
                    self._toggle_picker("emoji" if lower == "e" else "gif")
            else:
                return False
            return True

        focus = self.win.get_focus()
        if name == "Escape" and HAVE_WEBKIT and isinstance(focus, WebKit2.WebView):
            self._focus_reply()  # out of the video, back to the panel; the video keeps playing
            return True
        if self.picker.get_visible():
            if name == "Escape":
                self._close_picker()
                return True
            if focus is self.picker.search:
                return self.picker.key(name)
        if self.suggestions.get_visible() and focus is self.reply:
            if name == "Escape":
                self.suggestions.hide()
            elif name in ("Up", "Down"):
                self.suggestions.move(1 if name == "Down" else -1)
            elif name in ("Tab", "Return", "KP_Enter"):
                self._accept_suggestion(self.suggestions.current())
            else:
                return False
            return True

        if name == "Escape":
            self._escape()
            return True

        if name in ("Tab", "ISO_Left_Tab"):
            # Tab toggles between the list and the open chat's reply box, keeping your draft, cursor,
            # highlight and Friends/Servers tab (e.g. browse Servers mid-conversation, then Tab back).
            # Anywhere else it does nothing, rather than GTK's default of wandering focus around.
            if focus is self.reply:
                self._focus_list()
            elif self.channel_id and focus in (self.listbox, self.search):
                self._focus_reply()
            return True
        if focus is self.listbox:
            return self._list_key(name, event)
        if focus is self.search:
            if name == "Down":
                self._focus_list()
            elif name in ("Return", "KP_Enter"):
                self._activate(self._highlighted())
            else:
                return False
            return True
        if focus is self.reply:
            if name in ("Return", "KP_Enter"):
                if self.deleting:
                    self._confirm_delete()
                elif self.editing:
                    self._save_edit()
                else:
                    self._send()
            elif name == "Left" and self.reply.get_position() == 0 and not self.reply.get_selection_bounds():
                self._focus_list()  # at the start of the text: back out to the list
            elif name in ("Up", "Down"):
                self._scroll_messages(name)
            else:
                return False
            return True
        return False

    # ---------- voice / Vesktop ----------

    def _refresh_voice(self, skip_if_busy=True):
        asked_at = time.monotonic()

        def got(v):
            # An answer to a question asked before your last press is stale; don't let it undo the button.
            if asked_at < self.voice_pressed_at:
                return
            # Just after a press, Discord may not have applied it yet: only accept answers that agree with
            # the button until the settle time; after that the real state wins (e.g. if the toggle failed).
            settling = time.monotonic() < self.voice_pressed_at + VOICE_SETTLE_SECONDS
            if settling and (v["mute"], v["deaf"]) != (self.voice_state["mute"], self.voice_state["deaf"]):
                return
            self._on_voice(v)

        self._call("voice", on_ok=got, on_err=lambda _exc: None, skip_if_busy=skip_if_busy)
        return False

    def _on_voice(self, v):
        self.voice_state = v
        self.mute_text.set_text("Unmute" if v["mute"] else "Mute")
        set_class(self.mute_btn, "on", v["mute"])
        self.deaf_text.set_text("Undeafen" if v["deaf"] else "Deafen")
        set_class(self.deaf_btn, "on", v["deaf"])
        self.voice_label.set_text("Voice connected" if v["channel"] else "Not in voice")
        set_class(self.voice_label, "connected", bool(v["channel"]))
        self.voice_channel.set_text(f"🔊 {v['channel']}" if v["channel"] else "")
        self.voice_channel.set_visible(bool(v["channel"]))
        if v.get("me") and v["me"] != self.me:
            self.me = v["me"]
            self._show_me()
        self.disconnect_btn.set_visible(bool(v["channel"]))
        # Just after you pick a status, Discord's answer may still be the old one; trust the button a moment.
        settled = time.monotonic() > self.status_set_at + VOICE_SETTLE_SECONDS
        if v.get("status") and (settled or v["status"] == self.status):
            self._show_status(v["status"])

    # ---------- status / leaving voice ----------

    def _show_status(self, status):
        self.status = status
        self.user_status.set_text(STATUS_NAMES.get(status, status))
        self._show_me()

    def _show_me(self):
        """Your avatar (with your status as its dot) and name in the user panel."""
        name = self.me.get("name") or ""
        self.user_name.set_text(name)
        dot = "offline" if self.status == "invisible" else self.status  # invisible shows as grey, like Discord
        self.user_avatar.set(self.me.get("avatar"), name[:1].upper(), dot)

    def _status_menu(self):
        items = []
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

    def _disconnect_voice(self):
        if not self.win.get_visible() or not self.voice_state.get("channel"):
            return
        self._on_voice(dict(self.voice_state, channel=None))
        self.voice_pressed_at = time.monotonic()
        self._call("disconnectVoice", on_err=self._show_error)
        GLib.timeout_add(int(VOICE_SETTLE_SECONDS * 1000) + 100, self._refresh_voice, False)

    def _voice(self, method):
        """Toggle mute/deafen. The button flips at once (Discord can take a moment to apply the change),
        then the real state is read back shortly after to confirm or correct it."""
        if not self.win.get_visible():
            return
        expected = dict(self.voice_state)
        if method == "toggleMute":
            if expected["deaf"]:
                expected["deaf"] = expected["mute"] = False  # like Discord: unmuting while deafened undeafens
            else:
                expected["mute"] = not expected["mute"]
        else:
            expected["deaf"] = not expected["deaf"]
            if expected["deaf"]:
                expected["mute"] = True  # deafened always shows as muted
        self.voice_pressed_at = time.monotonic()
        self._on_voice(expected)
        self._call(method, on_err=self._show_error)
        GLib.timeout_add(int(VOICE_SETTLE_SECONDS * 1000) + 100, self._refresh_voice, False)  # final word

    def _open_in_vesktop(self, channel_id=None, server_id=None):
        """Right-click → Open in Vesktop: show that chat (or server) in Vesktop, with its message box focused."""
        self.prev_window = None  # going to Vesktop, not back to the previous window
        self.hide()
        if server_id:
            self._call("openServer", server_id, on_ok=lambda _: self._after_open())
        else:
            self._call("open", channel_id, on_ok=lambda _: self._after_open())

    # ---------- click-away ----------

    def _on_focus_out(self, *_):
        # Ignore the focus shuffle right after opening; otherwise check shortly after, since menus and
        # keyboard grabs (like the hotkey itself) briefly take focus without the user leaving.
        if self.win.get_visible() and time.monotonic() - self.shown_at > CLICK_AWAY_GRACE_SECONDS:
            GLib.timeout_add(CLICK_AWAY_CHECK_MS, self._close_if_unfocused)
        return False

    def _close_if_unfocused(self):
        if not self.win.get_visible() or self.win.is_active() or Gtk.grab_get_current() is not None:
            return False
        if self._still_active_window():
            # Another program's global hotkey (e.g. a volume key script) grabbed the keyboard for a moment.
            # That takes focus from us without the user going anywhere, so stay open.
            return False
        self.prev_window = None  # they clicked somewhere else; leave focus there
        self.hide()
        return False

    def _still_active_window(self):
        """Is the panel still the window manager's active window (_NET_ACTIVE_WINDOW)?"""
        active = Gdk.Screen.get_default().get_active_window()
        own = self.win.get_window()
        return active is not None and own is not None and active.get_xid() == own.get_xid()

    def _after_open(self):
        activate_vesktop_window()
        GLib.timeout_add(VESKTOP_FOCUS_DELAY_MS, self._focus_composer)

    def _focus_composer(self):
        self._call("focusComposer")
        return False


STATUS_NAMES = {"online": "Online", "idle": "Idle", "dnd": "Do Not Disturb", "invisible": "Invisible"}


def follow_vesktop():
    """Quit once Vesktop has fully exited (closing it to the tray doesn't count; quitting or a crash does).

    Only after Vesktop has been seen running, so starting the overlay while Vesktop is still loading is fine.
    """
    started, seen = time.monotonic(), False

    def check():
        nonlocal seen
        if vesktop_running():
            seen = True
        elif seen or time.monotonic() - started > FOLLOW_STARTUP_GRACE:
            print("Vesktop has exited; quitting.", flush=True)
            Gtk.main_quit()
            return False
        return True

    GLib.timeout_add_seconds(FOLLOW_CHECK_SECONDS, check)


def main():
    lock = instance.acquire()
    if lock is None:
        print("vesktop-discord-overlay is already running.", flush=True)
        return
    Overlay()
    if "--follow-vesktop" in sys.argv[1:]:
        follow_vesktop()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, Gtk.main_quit)
    print(f"vesktop-discord-overlay {__version__} running. Press {HOTKEY_LABEL} to open the overlay, "
          "Ctrl+C here to quit.", flush=True)
    Gtk.main()
    # Exit right away: a stuck download or Vesktop call in a worker thread would otherwise delay quitting.
    os._exit(0)
