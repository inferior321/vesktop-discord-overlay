"""Emoji / GIF pickers and the ':' emoji autocomplete."""

import math

from .gtk import GLib, Gdk, GdkPixbuf, Gtk, HAVE_VIDEO, Pango, PangoCairo
from .config import EMOJI_CELL, EMOJI_SEARCH_LIMIT, GIF_COLUMNS, GIF_SEARCH_DELAY_MS
from .media import LoopingVideo, Picture, hex_rgb, rounded_rect_at
from .theme import SELECTED, font
from .widgets import add_class, label, set_class

EMOJI_CATEGORY_TITLES = {
    "people": "People", "nature": "Nature", "food": "Food & Drink", "activity": "Activities",
    "travel": "Travel & Places", "objects": "Objects", "symbols": "Symbols", "flags": "Flags",
}


def emoji_names(entry):
    return entry.get("names") or [entry["name"]]


def match_emoji(entries, query, limit, frecent=()):
    """Emoji whose names start with the query (frequently used first), then ones that merely contain it."""
    q = query.lower()
    starts, contains, seen = [], [], set()
    for entry in entries:
        key = entry.get("id") or entry["name"]
        if key in seen:
            continue
        names = [n.lower() for n in emoji_names(entry)]
        if any(n.startswith(q) for n in names):
            starts.append(entry)
        elif any(q in n for n in names):
            contains.append(entry)
        else:
            continue
        seen.add(key)
    rank = {name: i for i, name in enumerate(frecent)}
    starts.sort(key=lambda e: (rank.get(e["name"], len(rank)), len(e["name"])))
    return (starts + contains)[:limit]


def emoji_text(entry):
    """What goes into the reply box: the character itself, or :name: for server emoji (converted on send)."""
    return entry["char"] if "char" in entry else f":{entry['name']}: "


class EmojiGrid(Gtk.DrawingArea):
    """Emoji in a grid with section headers, drawn by hand: one widget per emoji would be far too slow."""

    CELL = EMOJI_CELL
    HEADER = 26

    def __init__(self, media, on_pick, on_highlight):
        super().__init__()
        self.media = media
        self.on_pick = on_pick
        self.on_highlight = on_highlight
        self.adjustment = None  # the scrolled window's, set by Picker
        self.sections = []
        self.entries = []
        self.cells = []
        self.headers = []
        self.cursor = 0
        self.width = 0
        self.images = {}  # url -> scaled pixbuf (None while loading)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("draw", self._draw)
        self.connect("size-allocate", self._allocated)
        self.connect("button-press-event", self._clicked)
        self.connect("motion-notify-event", self._hovered)

    def set_sections(self, sections):
        self.sections = [(title, items) for title, items in sections if items]
        self.cursor = 0
        self._layout()
        if self.adjustment:
            self.adjustment.set_value(0)
        self._announce()

    def current(self):
        return self.entries[self.cursor] if self.entries else None

    def _allocated(self, _widget, alloc):
        if alloc.width != self.width:
            self.width = alloc.width
            GLib.idle_add(self._layout)  # re-flowing changes our height request; not allowed mid-allocation

    def _layout(self):
        cols = max(1, (self.width or 400) // self.CELL)
        y = 0
        entries, cells, headers = [], [], []
        for title, items in self.sections:
            headers.append((y, title))
            y += self.HEADER
            for i, item in enumerate(items):
                cells.append(((i % cols) * self.CELL, y + (i // cols) * self.CELL))
                entries.append(item)
            y += math.ceil(len(items) / cols) * self.CELL + 6
        self.entries, self.cells, self.headers = entries, cells, headers
        self.cursor = min(self.cursor, max(0, len(entries) - 1))
        self.set_size_request(-1, max(y, 1))
        self.queue_draw()
        return False

    def move(self, key):
        if not self.entries:
            return
        if key == "Left":
            self._set_cursor(self.cursor - 1)
        elif key == "Right":
            self._set_cursor(self.cursor + 1)
        else:
            self._vertical(1 if key == "Down" else -1)

    def _vertical(self, direction):
        """Nearest emoji in the next/previous row, crossing section boundaries."""
        cx, cy = self.cells[self.cursor]
        rows = [y for _, y in self.cells if (y > cy if direction > 0 else y < cy)]
        if not rows:
            return
        target = min(rows) if direction > 0 else max(rows)
        best = min((i for i, (_, y) in enumerate(self.cells) if y == target),
                   key=lambda i: abs(self.cells[i][0] - cx))
        self._set_cursor(best)

    def _set_cursor(self, index, scroll=True):
        if not self.entries:
            return
        self.cursor = max(0, min(index, len(self.entries) - 1))
        self.queue_draw()
        if scroll and self.adjustment:
            y = self.cells[self.cursor][1]
            self.adjustment.clamp_page(max(0, y - self.HEADER), y + self.CELL)
        self._announce()

    def _announce(self):
        self.on_highlight(self.current())

    def _index_at(self, x, y):
        for i, (cx, cy) in enumerate(self.cells):
            if cx <= x < cx + self.CELL and cy <= y < cy + self.CELL:
                return i
        return None

    def _hovered(self, _widget, event):
        i = self._index_at(event.x, event.y)
        if i is not None and i != self.cursor:
            self._set_cursor(i, scroll=False)
        return False

    def _clicked(self, _widget, event):
        i = self._index_at(event.x, event.y)
        if event.button == 1 and i is not None:
            self.cursor = i
            self.on_pick(self.entries[i])
        return True

    def _image(self, url):
        if url not in self.images:
            self.images[url] = None

            def loaded(anim, u=url):
                if anim:
                    self.images[u] = anim.get_static_image().scale_simple(28, 28, GdkPixbuf.InterpType.BILINEAR)
                    self.queue_draw()

            anim = self.media.image(url, loaded)
            if anim:
                loaded(anim)
        return self.images[url]

    def _draw(self, _widget, cr):
        _, top, _, bottom = cr.clip_extents()
        layout = self.create_pango_layout("")
        layout.set_font_description(font("Noto Sans Bold", 8))
        cr.set_source_rgb(*hex_rgb("#949ba4"))
        for y, title in self.headers:
            if top - self.HEADER <= y <= bottom:
                layout.set_text(title.upper(), -1)
                cr.move_to(6, y + 8)
                PangoCairo.show_layout(cr, layout)

        layout.set_font_description(Pango.FontDescription("Noto Sans 22px"))
        c = self.CELL
        for i, ((x, y), item) in enumerate(zip(self.cells, self.entries)):
            if y + c < top or y > bottom:
                continue
            if i == self.cursor:
                rounded_rect_at(cr, x + 2, y + 2, c - 4, c - 4, 6)
                cr.set_source_rgb(*hex_rgb(SELECTED))
                cr.fill()
            if "char" in item:
                layout.set_text(item["char"], -1)
                tw, th = layout.get_pixel_size()
                cr.set_source_rgb(1, 1, 1)
                cr.move_to(x + (c - tw) / 2, y + (c - th) / 2)
                PangoCairo.show_layout(cr, layout)
            else:
                pixbuf = self._image(item["url"])
                if pixbuf:
                    Gdk.cairo_set_source_pixbuf(cr, pixbuf, x + (c - 28) / 2, y + (c - 28) / 2)
                    cr.paint()
        return False


class GifTile(Gtk.EventBox):
    """One GIF (or category) in the GIF picker: a still frame, playing as video while highlighted."""

    def __init__(self, media, item, w, h, caption=None):
        super().__init__()
        self.media = media
        self.item = item
        self.w, self.h = w, h
        self.video = None
        self.want_play = False
        self.stack = Gtk.Overlay()
        self.picture = Picture(w, h, cover=True, caption=caption)
        self.stack.add(self.picture)
        self.add(self.stack)
        if item.get("still"):
            pixbuf = media.still(item["still"], self._still_ready)
            if pixbuf:
                self._still_ready(pixbuf)
        self.connect("destroy", lambda *_: self._stop_video())

    def _still_ready(self, pixbuf):
        if pixbuf:
            self.picture.set_pixbuf(pixbuf)

    def set_playing(self, playing):
        self.want_play = playing
        if not playing:
            self._stop_video()
        elif HAVE_VIDEO and self.item.get("mp4"):
            path = self.media.file(self.item["mp4"], self._video_ready)
            if path:
                self._video_ready(path)

    def _video_ready(self, path):
        if not path or not self.want_play or self.video:
            return
        iw, ih = self.item.get("w") or self.w, self.item.get("h") or self.h
        scale = min(self.w / iw, self.h / ih)
        video = LoopingVideo(path, max(1, round(iw * scale)), max(1, round(ih * scale)))
        if video.widget is None:
            return
        self.video = video
        video.widget.set_halign(Gtk.Align.CENTER)
        video.widget.set_valign(Gtk.Align.CENTER)
        self.stack.add_overlay(video.widget)
        video.widget.show()
        # Only play once inside the window (see MediaView._sync_playback).
        if video.widget.get_mapped():
            video.play()
        else:
            video.widget.connect("map", lambda *_: self.video is video and video.play())

    def _stop_video(self):
        if self.video:
            video, self.video = self.video, None
            video.stop()
            self.stack.remove(video.widget)


class Picker(Gtk.Box):
    """Emoji / GIF picker that pops up over the bottom of the message area (😀 / GIF buttons or Ctrl+E / G)."""

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.app = app  # the Overlay: bridge calls, emoji data, inserting/sending
        add_class(self, "picker")
        self.set_valign(Gtk.Align.END)
        self.page = "emoji"
        self.gif_tiles = []
        self.gif_cursor = 0
        self.gif_request = 0
        self.gif_showing_results = False
        self.search_timer = None
        self.reacting = False  # picking a reaction for a message, not an emoji for the reply box

        self.mode_label = label("", "picker-mode", ellipsize=True)  # "Reacting to …'s message"
        self.pack_start(self.mode_label, False, False, 0)

        top = Gtk.Box(spacing=6)
        self.page_buttons = {}
        for key, text, keys in (("emoji", "Emoji", "Ctrl+E"), ("gif", "GIFs", "Ctrl+G")):
            content = Gtk.Box(spacing=8)
            content.pack_start(Gtk.Label(label=text), False, False, 0)
            content.pack_start(label(keys, "keycap"), False, False, 0)
            btn = add_class(Gtk.Button(), "tab")
            btn.add(content)
            btn.set_can_focus(False)
            btn.connect("clicked", lambda _b, k=key: self.show_page(k))
            top.pack_start(btn, False, False, 0)
            self.page_buttons[key] = btn
        self.search = add_class(Gtk.Entry(), "search")
        self.search_handler = self.search.connect("changed", self._search_changed)
        top.pack_start(self.search, True, True, 0)
        self.pack_start(top, False, False, 0)

        self.stack = Gtk.Stack()
        self.emoji_grid = EmojiGrid(app.images, app._insert_emoji, self._describe)
        emoji_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        emoji_scroll.add(self.emoji_grid)
        self.emoji_grid.adjustment = emoji_scroll.get_vadjustment()
        self.stack.add_named(emoji_scroll, "emoji")

        gif_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.gif_status = label("", "info", xalign=0.5)
        self.gif_status.set_no_show_all(True)
        gif_page.pack_start(self.gif_status, False, False, 6)
        self.gif_flow = add_class(Gtk.FlowBox(), "gifs")
        self.gif_flow.set_homogeneous(True)
        self.gif_flow.set_min_children_per_line(GIF_COLUMNS)
        self.gif_flow.set_max_children_per_line(GIF_COLUMNS)
        self.gif_flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.gif_flow.set_valign(Gtk.Align.START)
        self.gif_flow.connect("child-activated", lambda _f, child: self._activate_gif(child.get_index()))
        self.gif_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.gif_scroll.add(self.gif_flow)
        gif_page.pack_start(self.gif_scroll, True, True, 0)
        self.stack.add_named(gif_page, "gif")
        self.pack_start(self.stack, True, True, 0)

        self.footer = label("", "hint", ellipsize=True)
        self.pack_start(self.footer, False, False, 0)

        for child in self.get_children():
            child.show_all()
        self.mode_label.set_no_show_all(True)
        self.mode_label.hide()
        self.set_no_show_all(True)  # hidden until opened

    # ----- opening / pages -----

    def open(self, page, height, reacting_to=None):
        """reacting_to: the author's name when picking a reaction for their message (emoji only)."""
        self.reacting = reacting_to is not None
        self.mode_label.set_text(f"Reacting to {reacting_to}'s message" if self.reacting else "")
        self.mode_label.set_visible(self.reacting)
        self.page_buttons["gif"].set_visible(not self.reacting)
        self.set_size_request(-1, height)
        self.show()
        self.show_page(page, force=True)
        if self.reacting:
            self.search.set_placeholder_text("Find an emoji to react with")

    def close(self):
        self._highlight_gif(None)
        self.reacting = False
        self.hide()

    def show_page(self, page, force=False):
        if page == self.page and not force:
            self.search.grab_focus_without_selecting()
            return
        self.page = page
        for key, btn in self.page_buttons.items():
            set_class(btn, "active", key == page)
        self.stack.set_visible_child_name(page)
        self._set_search("")
        if page == "emoji":
            self._highlight_gif(None)
            self.search.set_placeholder_text("Find the perfect emoji")
            self.app._with_emoji(lambda: self._render_emoji(""))
        else:
            self.search.set_placeholder_text("Search Klipy")
            self._load_gifs("")
        self.search.grab_focus_without_selecting()

    def _set_search(self, text):
        with self.search.handler_block(self.search_handler):
            self.search.set_text(text)

    def _search_changed(self, *_):
        text = self.search.get_text().strip()
        if self.page == "emoji":
            self._render_emoji(text)
            return
        if self.search_timer:
            GLib.source_remove(self.search_timer)
        self.search_timer = GLib.timeout_add(GIF_SEARCH_DELAY_MS, self._search_gifs)

    def _search_gifs(self):
        self.search_timer = None
        self._load_gifs(self.search.get_text().strip())
        return False

    def _describe(self, item):
        if self.page == "emoji":
            self.footer.set_text(" ".join(f":{n}:" for n in emoji_names(item)) if item else "")

    # ----- keys (search box has focus while open) -----

    def key(self, name):
        if name in ("Up", "Down", "Left", "Right"):
            if self.page == "emoji":
                self.emoji_grid.move(name)
            else:
                step = {"Left": -1, "Right": 1, "Up": -GIF_COLUMNS, "Down": GIF_COLUMNS}[name]
                self._highlight_gif(self.gif_cursor + step)
        elif name in ("Tab", "ISO_Left_Tab", "Page_Up", "Page_Down"):
            pass  # unused in the pickers (Ctrl+E / Ctrl+G or the tabs switch pages)
        elif name in ("Return", "KP_Enter"):
            if self.page == "emoji":
                if self.emoji_grid.current():
                    self.app._insert_emoji(self.emoji_grid.current())
            else:
                self._activate_gif(self.gif_cursor)
        elif name == "BackSpace" and self.page == "gif" and not self.search.get_text() and self.gif_showing_results:
            self._load_gifs("")  # back from a category to the category list
        else:
            return False
        return True

    # ----- emoji -----

    def _render_emoji(self, query):
        catalog, extra = self.app.emoji_catalog, self.app.channel_emoji()
        if catalog is None:
            return
        if query:
            matches = match_emoji(self.app.emoji_entries(), query.strip(":"), EMOJI_SEARCH_LIMIT,
                                  [e["name"] for e in extra["frecent"]])
            self.emoji_grid.set_sections([("Search results", matches)])
            if not matches:
                self.footer.set_text("No emoji match")
            return
        sections = [("Frequently used", extra["frecent"])]
        sections += [(g["guild"], g["emojis"]) for g in extra["custom"]]
        sections += [(EMOJI_CATEGORY_TITLES.get(c["id"], c["id"].title()), c["emojis"]) for c in catalog["categories"]]
        self.emoji_grid.set_sections(sections)

    # ----- GIFs -----

    def _load_gifs(self, query):
        self.gif_request += 1
        request = self.gif_request
        self._clear_gifs()
        self.gif_status.set_text("Loading…")
        self.gif_status.show()
        self.app._call("gifs", query, on_ok=lambda data: self._show_gifs(request, query, data),
                       on_err=lambda exc: self._gif_error(request, exc))

    def _gif_error(self, request, exc):
        if request == self.gif_request:
            self.gif_status.set_text(f"Couldn't load GIFs: {str(exc).splitlines()[0][:80]}")

    def _clear_gifs(self):
        self._highlight_gif(None)
        self.gif_tiles = []
        for child in self.gif_flow.get_children():
            child.destroy()

    def _show_gifs(self, request, query, data):
        if request != self.gif_request:
            return  # a newer search already started
        self.gif_showing_results = bool(query)
        items = data.get("gifs")
        captioned = items is None
        if captioned:
            items = data.get("categories", [])
        if not items:
            self.gif_status.set_text("No GIFs found")
            return
        self.gif_status.hide()
        width = self.gif_scroll.get_allocated_width() or 600
        tile_w = max(80, (width - 12) // GIF_COLUMNS - 8)
        tile_h = int(tile_w * 0.62)
        for item in items:
            tile = GifTile(self.app.images, item, tile_w, tile_h, caption=item["name"] if captioned else None)
            tile.connect("enter-notify-event", lambda t, _e: self._highlight_gif(self.gif_tiles.index(t), scroll=False))
            self.gif_flow.insert(tile, -1)
            tile.get_parent().set_can_focus(False)
            tile.show_all()
            self.gif_tiles.append(tile)
        self.gif_scroll.get_vadjustment().set_value(0)
        self._highlight_gif(0)

    def _highlight_gif(self, index, scroll=True):
        old = self.gif_tiles[self.gif_cursor] if 0 <= self.gif_cursor < len(self.gif_tiles) else None
        if index is None or not self.gif_tiles:
            if old:
                old.set_playing(False)
            self.gif_flow.unselect_all()
            return
        index = max(0, min(index, len(self.gif_tiles) - 1))
        tile = self.gif_tiles[index]
        if old and old is not tile:
            old.set_playing(False)
        self.gif_cursor = index
        self.gif_flow.select_child(tile.get_parent())
        tile.set_playing(True)
        self.footer.set_text(tile.item.get("title") or tile.item.get("name") or "")
        if scroll:
            alloc = tile.get_parent().get_allocation()
            if alloc.height > 1:
                self.gif_scroll.get_vadjustment().clamp_page(alloc.y, alloc.y + alloc.height)

    def _activate_gif(self, index):
        if not 0 <= index < len(self.gif_tiles):
            return
        item = self.gif_tiles[index].item
        if "query" in item:
            # A category: show its GIFs. Trending has no search words, so leave the box empty.
            self._set_search("" if item["query"] == "__trending__" else item["query"])
            self._load_gifs(item["query"])
        else:
            self.app._send_gif(item["url"])


class Suggestions(Gtk.Box):
    """The ':' emoji autocomplete list above the reply box."""

    def __init__(self, media, on_accept):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        add_class(self, "suggest")
        self.media = media
        self.set_valign(Gtk.Align.END)
        self.set_halign(Gtk.Align.START)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", lambda _lb, row: on_accept(row.item))
        self.pack_start(self.listbox, False, False, 0)
        self.listbox.show()
        self.set_no_show_all(True)

    def show_items(self, items):
        for row in self.listbox.get_children():
            row.destroy()
        for item in items:
            row = add_class(Gtk.ListBoxRow(), "suggest-row")
            row.item = item
            row.set_can_focus(False)
            box = Gtk.Box(spacing=10)
            if "char" in item:
                box.pack_start(label(item["char"], "suggest-char", xalign=0.5), False, False, 0)
            else:
                pic = Picture(22, 22)
                anim = self.media.image(item["url"], lambda a, p=pic: a and p.set_animation(a))
                if anim:
                    pic.set_animation(anim)
                box.pack_start(pic, False, False, 0)
            box.pack_start(label(f":{item['name']}:", "suggest-name"), False, False, 0)
            row.add(box)
            row.show_all()
            self.listbox.add(row)
        self.listbox.select_row(self.listbox.get_row_at_index(0))
        self.show()

    def move(self, delta):
        rows = self.listbox.get_children()
        current = self.listbox.get_selected_row()
        index = rows.index(current) if current in rows else 0
        self.listbox.select_row(rows[(index + delta) % len(rows)])

    def current(self):
        row = self.listbox.get_selected_row()
        return row.item if row else None
