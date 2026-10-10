"""The keyboard shortcut list behind the "?" in the panel's corner (hover it, or press F1)."""

from . import __version__
from .gtk import Gtk
from .widgets import add_class, label

# Only the shortcuts that aren't already printed on a button; two columns so it fits the shortest panel.
COLUMNS = [[
    ("Anywhere", [
        ("Ctrl+Tab", "Friends / Servers"),
        ("Esc", "Close popups, then the panel"),
        ("Ctrl+↑ ↓", "Opacity"),
    ]),
    ("List", [
        ("↑ ↓", "Move"),
        ("→", "Open; again: reply box"),
        ("←", "Close chat / leave server"),
        ("Enter", "Open and type"),
        ("Type", "Search"),
        ("Tab", "List ⇄ reply box"),
    ]),
    ("Mouse", [
        ("Click media", "Full size / play YouTube"),
        ("Right-click", "React, edit, delete, open in Vesktop…"),
        ("Click outside", "Close the panel"),
    ]),
], [
    ("Reply box", [
        ("Enter", "Send"),
        ("↑ ↓", "Scroll (top loads older)"),
        ("← at start", "Back to the list"),
        (":ab", "Emoji suggestions"),
    ]),
    ("Pickers", [
        ("Arrows, Enter", "Choose, insert / send"),
        ("Esc", "Close"),
    ]),
    ("History", [
        ("Ctrl+← →", "Previous / next chat"),
        ("Ctrl+Shift+←", "Remove chat from history"),
        ("Ctrl+Shift+→", "Show chat in the list"),
    ]),
]]


def _column(sections):
    grid = Gtk.Grid(column_spacing=10, row_spacing=2)
    row = 0
    for section, entries in sections:
        heading = label(section.upper(), "help-section")
        heading.set_margin_top(0 if row == 0 else 8)
        grid.attach(heading, 0, row, 2, 1)
        row += 1
        for keys, what in entries:
            key = label(keys, "keycap", xalign=0.0)
            key.set_halign(Gtk.Align.START)
            grid.attach(key, 0, row, 1, 1)
            grid.attach(label(what, "help-desc"), 1, row, 1, 1)
            row += 1
    return grid


def help_popover(relative_to):
    """A non-modal popover listing every shortcut, so it never takes focus from what you're doing."""
    popover = Gtk.Popover(relative_to=relative_to, modal=False, position=Gtk.PositionType.TOP)
    add_class(popover, "help-pop")
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
    columns = Gtk.Box(spacing=22)
    for sections in COLUMNS:
        columns.pack_start(_column(sections), False, False, 0)
    content.pack_start(columns, False, False, 0)
    content.pack_start(label(f"vesktop-discord-overlay {__version__}", "help-version", xalign=1.0), False, False, 0)
    popover.add(content)
    content.show_all()
    return popover
