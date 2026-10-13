"""Draw Discord-formatted message text (the simplified parse tree from bridge.js) as GTK widgets.

Node types (key "t"): text, strong, em, u, s, spoiler, subtext, heading, blockQuote, inlineCode, codeBlock,
link, list, mention, emoji, customEmoji, timestamp. Inline nodes become Pango markup in a label; code blocks,
quotes, lists, headings and subtext become their own widgets.
"""

import re

from .config import INLINE_EMOJI, JUMBO_EMOJI, JUMBO_LIMIT, TEXT_SCALE
from .gtk import GLib, Gtk, Pango
from .media import Picture
from .theme import BORDER, INPUT
from .widgets import add_class

INLINE_TAGS = {"strong": "b", "em": "i", "u": "u", "s": "s"}
BLOCK_TYPES = {"codeBlock", "blockQuote", "list", "heading", "subtext"}
HEADING_SIZES = {1: "x-large", 2: "large", 3: "medium"}
EMOJI_SIZE = round(INLINE_EMOJI * TEXT_SCALE)  # server emoji inside a line of text, sized like the text
EMOJI_SLOT = "\ufffc"  # object replacement character: a placeholder the emoji image covers


class Revealed:
    """The spoilers clicked open in one message. Stored in the overlay's shared dict only once one is, so
    messages without any don't each leave an entry behind."""

    def __init__(self, store, message_id):
        self.store, self.message_id = store, message_id

    def __contains__(self, number):
        return number in self.store.get(self.message_id, ())

    def add(self, number):
        self.store.setdefault(self.message_id, set()).add(number)


class RenderContext:
    """Per-message state: which spoilers are revealed (kept across refreshes) and how to open links."""

    def __init__(self, revealed, open_url, media):
        self.revealed = revealed  # Revealed: spoiler numbers clicked open, kept across refreshes
        self.open_url = open_url
        self.media = media
        self.next_spoiler = 0


def esc(text):
    return GLib.markup_escape_text(text, -1)


def plain_text(nodes):
    out = []
    for n in nodes:
        if "v" in n:
            out.append(n["v"])
        elif n["t"] == "customEmoji":
            out.append(f":{n['name']}:")
        elif n["t"] == "list":
            out.extend(plain_text(item) + "\n" for item in n["items"])
        elif "c" in n:
            out.append(plain_text(n["c"]))
    return "".join(out)


class _Spoilers:
    """Numbers spoilers in reading order so a re-render maps clicks to the same spoiler.

    Also collects the server emoji met along the way: (node, hidden) per placeholder in the text.
    """

    def __init__(self, revealed, start):
        self.revealed = revealed
        self.next = start
        self.emoji = []

    def take(self):
        self.next += 1
        return self.next - 1


def inline_markup(nodes, spoilers, hidden=False):
    """Pango markup for inline nodes. hidden: inside an unrevealed spoiler (no links, nothing readable)."""
    parts = []
    for n in nodes:
        t = n["t"]
        if t == "text":
            parts.append(esc(n["v"]))
        elif t in INLINE_TAGS:
            tag = INLINE_TAGS[t]
            parts.append(f"<{tag}>{inline_markup(n['c'], spoilers, hidden)}</{tag}>")
        elif t == "inlineCode":
            parts.append(f'<span font_family="monospace" background="{INPUT}">{esc(n["v"])}</span>')
        elif t == "link":
            inner = inline_markup(n["c"], spoilers, hidden)
            parts.append(inner if hidden else f'<a href="{esc(n["href"])}">{inner}</a>')
        elif t == "mention":
            color = ('background="#f0b232" bgalpha="25%" foreground="#fde3a7"' if n.get("me")
                     else 'background="#5865f2" bgalpha="30%" foreground="#dee0fc"')
            parts.append(f'<span {color}>{esc(n["v"])}</span>')
        elif t == "emoji":
            parts.append(esc(n["v"]))
        elif t == "customEmoji":
            spoilers.emoji.append((n, hidden))
            parts.append(EMOJI_SLOT)  # space is reserved here and the image drawn over it (see InlineLabel)
        elif t == "edited":
            parts.append(f' <span size="small" foreground="#6d6f78">(edited)</span>')
        elif t == "timestamp":
            parts.append(f'<span background="#ffffff" bgalpha="8%">{esc(n["v"])}</span>')
        elif t == "spoiler":
            number = spoilers.take()
            if hidden:
                parts.append(inline_markup(n["c"], spoilers, True))
            elif number in spoilers.revealed:
                parts.append(f'<span background="#ffffff" bgalpha="10%">{inline_markup(n["c"], spoilers)}</span>')
            else:
                # Same color as its background, and a link so a click can reveal it.
                text = inline_markup(n["c"], spoilers, True)
                parts.append(f'<a href="spoiler:{number}"><span foreground="{BORDER}" background="{BORDER}">'
                             f'{text}</span></a>')
        elif t == "heading":
            size = HEADING_SIZES.get(n.get("level", 1), "medium")
            parts.append(f'<span size="{size}" weight="bold">{inline_markup(n["c"], spoilers, hidden)}</span>')
        elif t == "subtext":
            parts.append(f'<span size="small" foreground="#949ba4">{inline_markup(n["c"], spoilers, hidden)}</span>')
        elif t == "list":
            parts.append(esc(plain_text([n])))
        elif "c" in n:
            parts.append(inline_markup(n["c"], spoilers, hidden))
        elif "v" in n:
            parts.append(esc(n["v"]))
    return "".join(parts)


def emoji_url(node, size=96):
    ext = "gif" if node.get("animated") else "png"
    return f"https://cdn.discordapp.com/emojis/{node['id']}.{ext}?size={size}"


def _slot_attr(index):
    """A blank, emoji-sized box in the text at byte `index` (the EMOJI_SLOT character)."""
    size = EMOJI_SIZE * Pango.SCALE
    rect = Pango.Rectangle()
    rect.x, rect.y, rect.width, rect.height = 0, -int(size * 0.8), size + 2 * Pango.SCALE, size
    attr = Pango.attr_shape_new(rect, rect)
    attr.start_index, attr.end_index = index, index + len(EMOJI_SLOT.encode())
    return attr


class InlineLabel(Gtk.Overlay):
    """Wrapped, selectable formatted text; links open in the browser, spoilers reveal on click.

    GTK labels can't hold images, so server emoji get a blank emoji-sized slot in the text and the image
    is floated over that slot (repositioned whenever the text re-wraps).
    """

    def __init__(self, nodes, ctx, *classes):
        super().__init__()
        self.label = add_class(Gtk.Label(xalign=0), "msg-body", *classes)
        self.label.set_line_wrap(True)
        self.label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.label.set_selectable(True)
        self.label.set_can_focus(False)
        self.add(self.label)
        self.nodes = nodes
        self.ctx = ctx
        self.spoiler_start = ctx.next_spoiler
        self.emoji = []  # (picture, byte index of its slot)
        self.connect("get-child-position", self._place_emoji)
        self.label.connect("activate-link", self._link)
        self._render()

    def _render(self):
        spoilers = _Spoilers(self.ctx.revealed, self.spoiler_start)
        markup = inline_markup(self.nodes, spoilers).strip("\n")
        self.ctx.next_spoiler = max(self.ctx.next_spoiler, spoilers.next)
        try:
            # Pango's checker doesn't know GtkLabel's <a> links, so leave them out of the check.
            _, _, text, _ = Pango.parse_markup(re.sub(r'<a href="[^"]*">|</a>', "", markup), -1, "\0")
            self.label.set_markup(markup)
        except GLib.Error:
            text = None
            self.label.set_text(plain_text(self.nodes).strip("\n"))  # never lose a message to a markup error
        self._place_slots(text, spoilers.emoji)

    def _place_slots(self, text, emoji):
        for picture, _ in self.emoji:
            picture.destroy()
        self.emoji = []
        attrs = Pango.AttrList()
        if text is not None:
            data, index = text.encode(), 0
            for node, hidden in emoji:
                index = data.find(EMOJI_SLOT.encode(), index)
                if index < 0:
                    break
                attrs.insert(_slot_attr(index))
                if not hidden:  # inside an unrevealed spoiler the slot just stays blank
                    picture = Picture(EMOJI_SIZE, EMOJI_SIZE)
                    picture.set_tooltip_text(f":{node['name']}:")
                    anim = self.ctx.media.image(emoji_url(node, 48), lambda a, p=picture: a and p.set_animation(a))
                    if anim:
                        picture.set_animation(anim)
                    self.add_overlay(picture)
                    picture.show()
                    self.emoji.append((picture, index))
                index += len(EMOJI_SLOT.encode())
        self.label.set_attributes(attrs)

    def _place_emoji(self, _overlay, widget, alloc):
        index = next((i for picture, i in self.emoji if picture is widget), None)
        if index is None:
            return False
        pos = self.label.get_layout().index_to_pos(index)
        x, y = self.label.get_layout_offsets()  # where the label draws its text, in window coordinates
        own = self.get_allocation()
        alloc.x = x - own.x + pos.x // Pango.SCALE + 1
        alloc.y = y - own.y + pos.y // Pango.SCALE + max(0, (pos.height // Pango.SCALE - EMOJI_SIZE) // 2)
        alloc.width = alloc.height = EMOJI_SIZE
        return True

    def _link(self, _label, uri):
        if uri.startswith("spoiler:"):
            self.ctx.revealed.add(int(uri.split(":", 1)[1]))
            self._render()
        else:
            self.ctx.open_url(uri)
        return True  # handled; don't let GTK open it too


def is_jumbo(nodes):
    """Only emoji (and spaces), and not too many: Discord draws these large."""
    count = 0
    for n in nodes:
        if n["t"] in ("emoji", "customEmoji"):
            count += 1
        elif not (n["t"] == "text" and not n["v"].strip()):
            return False
    return 0 < count <= JUMBO_LIMIT


def wrapping_row(spacing):
    """A row that wraps onto more lines when it doesn't fit (like text), so it can never widen the panel."""
    row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=spacing, row_spacing=spacing,
                      max_children_per_line=100, homogeneous=False)
    row.set_can_focus(False)  # (it spans the message's width; each line fills from the left)
    return row


def add_to_row(row, widget):
    row.add(widget)
    child = widget.get_parent()  # the FlowBoxChild around it
    child.set_can_focus(False)
    child.set_halign(Gtk.Align.START)


def jumbo_row(nodes, ctx):
    """An emoji-only message: its emoji large, wrapping if there are many."""
    row = wrapping_row(4)
    for n in nodes:
        if n["t"] == "emoji":
            add_to_row(row, add_class(Gtk.Label(label=n["v"]), "md-jumbo"))
        elif n["t"] == "customEmoji":
            pic = Picture(JUMBO_EMOJI, JUMBO_EMOJI)
            pic.set_tooltip_text(f":{n['name']}:")
            anim = ctx.media.image(emoji_url(n), lambda a, p=pic: a and p.set_animation(a))
            if anim:
                pic.set_animation(anim)
            add_to_row(row, pic)
    return row


def code_block(node):
    box = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "md-code")
    text = add_class(Gtk.Label(label=node["v"].rstrip("\n"), xalign=0), "md-code-text")
    text.set_line_wrap(True)
    text.set_line_wrap_mode(Pango.WrapMode.CHAR)
    text.set_selectable(True)
    text.set_can_focus(False)
    box.pack_start(text, False, False, 0)
    return box


def quote_block(node, ctx):
    row = Gtk.Box(spacing=8)
    row.pack_start(add_class(Gtk.Box(), "md-quote-bar"), False, False, 0)
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    for widget in render_blocks(node["c"], ctx):
        inner.pack_start(widget, False, False, 0)
    row.pack_start(inner, True, True, 0)
    return row


def list_block(node, ctx):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    for i, item in enumerate(node["items"]):
        row = Gtk.Box(spacing=6, margin_start=4)
        marker = f"{node.get('start', 1) + i}." if node.get("ordered") else "•"
        row.pack_start(add_class(Gtk.Label(label=marker, yalign=0), "msg-body"), False, False, 0)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for widget in render_blocks(item, ctx):
            inner.pack_start(widget, False, False, 0)
        row.pack_start(inner, True, True, 0)
        box.pack_start(row, False, False, 0)
    return box


def render_blocks(nodes, ctx):
    """Widgets for a run of nodes: consecutive inline nodes share one label; blocks get their own widget."""
    widgets, run = [], []

    def flush():
        if plain_text(run).strip():
            widgets.append(InlineLabel(list(run), ctx))
        run.clear()

    for n in nodes:
        t = n["t"]
        if t not in BLOCK_TYPES:
            run.append(n)
            continue
        flush()
        if t == "codeBlock":
            widgets.append(code_block(n))
        elif t == "blockQuote":
            widgets.append(quote_block(n, ctx))
        elif t == "list":
            widgets.append(list_block(n, ctx))
        else:  # heading / subtext: one formatted line each
            widgets.append(InlineLabel([n], ctx))
    flush()
    return widgets


def render_message(nodes, ctx, edited=False):
    if is_jumbo(nodes):
        return [jumbo_row(nodes, ctx)]
    return render_blocks(nodes + [{"t": "edited"}] if edited and nodes else nodes, ctx)


def reaction_row(reactions, media, on_click):
    """Emoji reactions under a message, with counts; yours are highlighted. Clicking one calls on_click(reaction)
    (the overlay adds or removes yours). They wrap onto more lines like Discord's: a message with dozens of
    reactions mustn't widen the panel."""
    row = wrapping_row(4)
    for r in reactions:
        pill = add_class(Gtk.Button(), "reaction")
        pill.set_can_focus(False)
        if r["me"]:
            add_class(pill, "mine")
        content = Gtk.Box(spacing=5)
        emoji = r["emoji"]
        if emoji.get("name"):
            pill.set_tooltip_text(f":{emoji['name']}:")
        if "char" in emoji:
            content.pack_start(add_class(Gtk.Label(label=emoji["char"]), "reaction-emoji"), False, False, 0)
        else:
            pic = Picture(18, 18)
            anim = media.image(emoji_url(emoji, 48), lambda a, p=pic: a and p.set_animation(a))
            if anim:
                pic.set_animation(anim)
            content.pack_start(pic, False, False, 0)
        content.pack_start(add_class(Gtk.Label(label=str(r["count"])), "reaction-count"), False, False, 0)
        pill.add(content)
        pill.connect("clicked", lambda _b, r=r: on_click(r))
        add_to_row(row, pill)
    return row
