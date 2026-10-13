"""Discord-like colors and the GTK stylesheet."""

import re

from .config import TEXT_SCALE
from .gtk import Gtk, Pango

# Near-black, like Discord's "Midnight" theme; text colors are Discord's own.
BORDER = "#050506"  # deepest: window edge, spoiler blocks
SIDEBAR = "#0b0b0d"  # sidebar, bottom bar, popups
BG = "#111114"  # message area
INPUT = "#1b1b1f"  # text boxes, buttons, inline code
HOVER = "#18181c"
SELECTED = "#26262b"
SELECTED_FOCUS = "#2c2c32"  # highlighted row while the list has keyboard focus
QUOTE_BAR = "#3a3a40"
ACCENT = "#5865f2"
STATUS_COLORS = {"online": "#23a55a", "idle": "#f0b232", "dnd": "#f23f43", "offline": "#80848e"}


def _desktop_font_pt():
    """Your desktop's font size in points (e.g. "Noto Sans 10" -> 10), the base everything is scaled from."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*$", Gtk.Settings.get_default().props.gtk_font_name or "")
    return float(match.group(1)) if match else 10.0


BASE_PT = _desktop_font_pt()


def pt(size):
    """A font size for the stylesheet, scaled by TEXT_SCALE."""
    return f"{size * TEXT_SCALE:.1f}pt"


def font(family_and_style, size):
    """A Pango font for text drawn by hand (picker headings, image captions), scaled by TEXT_SCALE."""
    return Pango.FontDescription(f"{family_and_style} {size * TEXT_SCALE:.1f}")


CSS = f"""
window.vesktop-overlay {{ background: {BORDER}; font-size: {pt(BASE_PT)}; }}  /* everything inherits this */
.sidebar {{ background: {SIDEBAR}; border: none; border-right: 1px solid {BORDER}; }}  /* GTK themes add a light edge */
.main {{ background: {BG}; }}

.tab {{ background: transparent; background-image: none; border: none; box-shadow: none; text-shadow: none;
        color: #949ba4; padding: 6px 14px; border-radius: 6px; font-weight: 600; }}
.tab:hover {{ background: {HOVER}; color: #dbdee1; }}
.tab.active {{ background: {SELECTED}; color: #f2f3f5; }}

entry.search, entry.reply {{ background: {INPUT}; background-image: none; color: #dbdee1; border: none;
        border-radius: 6px; box-shadow: none; padding: 6px 10px; caret-color: #dbdee1; }}
entry.reply {{ background: {INPUT}; padding: 10px 14px; border-radius: 8px; }}

.back {{ background: transparent; background-image: none; border: none; box-shadow: none; text-shadow: none;
         color: #dbdee1; font-weight: 700; padding: 6px 10px; border-radius: 6px; }}
.back:hover {{ background: {HOVER}; }}

list.cards {{ background: transparent; }}
row.card {{ padding: 6px 8px; margin: 1px 8px; border-radius: 8px; background: transparent; }}
row.card:hover {{ background: {HOVER}; }}
row.card:selected {{ background: {SELECTED}; }}
row.card.muted {{ opacity: 0.45; }}
list.cards:focus {{ outline-style: none; }}
list.cards:focus row.card:selected {{ background: {SELECTED_FOCUS}; box-shadow: inset 3px 0 0 {ACCENT}; }}
.card-name {{ color: #b5bac1; font-weight: 600; }}
.card-name.unread {{ color: #f2f3f5; }}
.card-preview {{ color: #949ba4; font-size: {pt(9)}; }}
.card-time {{ color: #6d6f78; font-size: {pt(8)}; }}
.card-hash {{ color: #80848e; font-size: {pt(16)}; }}
.list-heading {{ color: #949ba4; font-size: {pt(8)}; font-weight: 700; }}
row.category {{ padding: 12px 8px 3px 18px; background: transparent; }}
row.category:hover .list-heading {{ color: #dbdee1; }}
.new-count {{ color: #7984f5; font-size: {pt(8)}; font-weight: 700; }}
.badge {{ background: #f23f43; color: white; border-radius: 9px; padding: 0 6px; font-size: {pt(8)}; font-weight: 700; }}
.dot {{ color: #f2f3f5; font-size: {pt(7)}; }}

.header {{ padding: 10px 16px; border-bottom: 1px solid {BORDER}; }}
.header-name {{ color: #f2f3f5; font-weight: 700; font-size: {pt(12)}; }}
.header-place {{ color: #949ba4; font-size: {pt(9)}; }}
.typing {{ color: #949ba4; font-size: {pt(9)}; font-style: italic; }}
.typing.activity {{ font-style: normal; }}
.card-preview.activity {{ color: #6d6f78; }}

.msg-author {{ color: #f2f3f5; font-weight: 600; }}
.msg-author.self {{ color: #00a8fc; }}
.msg-time {{ color: #6d6f78; font-size: {pt(8)}; }}
.msg-body {{ color: #dbdee1; }}
.msg-extra {{ color: #949ba4; font-style: italic; font-size: {pt(9)}; }}
label link, label link:visited {{ color: #00a8fc; }}
.msg-mentioned {{ background: rgba(240, 178, 50, 0.08); border-left: 2px solid #f0b232; padding: 2px 0 2px 6px; }}
.md-code {{ background: {SIDEBAR}; border: 1px solid {BORDER}; border-radius: 4px; padding: 6px 8px; }}
.md-code-text {{ font-family: monospace; font-size: {pt(9)}; color: #dbdee1; }}
.md-quote-bar {{ background: {QUOTE_BAR}; border-radius: 2px; min-width: 4px; }}
.md-jumbo {{ font-size: {pt(30)}; }}
.msg-reply {{ color: #949ba4; font-size: {pt(8)}; font-style: italic; }}
.system-icon {{ color: #949ba4; font-size: {pt(11)}; }}
.system-text {{ color: #949ba4; }}
.system-text b {{ color: #f2f3f5; }}
.forward-box {{ border-left: 3px solid {QUOTE_BAR}; padding: 2px 0 2px 10px; margin-left: 2px; }}
.poll {{ background: {SIDEBAR}; border: 1px solid {SELECTED}; border-radius: 8px; padding: 10px 12px;
         min-width: 280px; }}
.poll-question {{ color: #f2f3f5; font-weight: 700; }}
.poll-answer {{ background: {INPUT}; border-radius: 6px; padding: 5px 10px; }}
.poll-answer.mine {{ box-shadow: inset 0 0 0 1px {ACCENT}; }}
.poll-text {{ color: #dbdee1; }}
.poll-count {{ color: #949ba4; font-size: {pt(8.5)}; }}
.poll-footer {{ color: #949ba4; font-size: {pt(8)}; }}
.msg-reply:hover {{ color: #dbdee1; }}
.msg-flash {{ background: rgba(88, 101, 242, 0.22); }}
.msg-editing {{ background: rgba(88, 101, 242, 0.12); border-left: 2px solid {ACCENT}; padding: 2px 0 2px 6px; }}
.compose-note.danger {{ border: 1px solid rgba(242, 63, 67, 0.6); }}
button.danger {{ background: #da373c; background-image: none; color: white; border: none; border-radius: 6px;
                 padding: 2px 12px; min-height: 0; box-shadow: none; text-shadow: none; font-weight: 600; }}
button.danger:hover {{ background: #a12828; }}
button.plain {{ background: {INPUT}; background-image: none; color: #dbdee1; border: none; border-radius: 6px;
                padding: 2px 12px; min-height: 0; box-shadow: none; text-shadow: none; }}
button.plain:hover {{ background: {SELECTED}; }}
.draft-mark {{ color: #949ba4; font-size: {pt(9)}; }}
.picker-mode {{ color: #dbdee1; font-size: {pt(9)}; font-weight: 600; padding: 0 2px; }}
.date-sep separator {{ background: #2e2e33; min-height: 1px; }}
.date-sep .sep-text {{ color: #949ba4; font-size: {pt(8)}; font-weight: 600; }}
.new-sep separator {{ background: #f23f43; min-height: 1px; }}
.new-sep .sep-text {{ color: white; background: #f23f43; border-radius: 4px; padding: 0 5px;
                      font-size: {pt(7.5)}; font-weight: 700; }}
.jump-pill {{ background: {ACCENT}; background-image: none; color: white; border: none; border-radius: 14px;
              padding: 4px 14px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5); text-shadow: none; font-weight: 600; }}
.jump-pill:hover {{ background: #4752c4; }}
button.reaction {{ background: {INPUT}; background-image: none; border: 1px solid transparent; border-radius: 8px;
                   padding: 1px 7px; min-height: 0; box-shadow: none; text-shadow: none; }}
button.reaction:hover {{ border-color: #4e5058; }}
button.reaction.mine {{ background: rgba(88, 101, 242, 0.18); border-color: {ACCENT}; }}
.reaction-emoji {{ font-size: {pt(10)}; }}
.reaction-count {{ color: #dbdee1; font-size: {pt(8.5)}; font-weight: 600; }}
.compose-note {{ background: {SIDEBAR}; border-radius: 6px; padding: 3px 4px 3px 10px; }}
.compose-text {{ color: #b5bac1; font-size: {pt(9)}; }}
.compose-close {{ background: transparent; background-image: none; border: none; box-shadow: none; color: #949ba4;
                  padding: 0 6px; min-height: 0; text-shadow: none; }}
.compose-close:hover {{ color: #f2f3f5; }}
menu, .menu, .context-menu {{ background: {SIDEBAR}; color: #dbdee1; border: 1px solid {SELECTED};
                              padding: 4px 0; }}
menu menuitem {{ padding: 5px 14px; color: #dbdee1; }}
menu menuitem:hover {{ background: {SELECTED}; color: #f2f3f5; }}
menu separator {{ background: {SELECTED}; min-height: 1px; margin: 3px 0; }}
menu menuitem.danger label {{ color: #f23f43; }}
menu menuitem.danger:hover {{ background: #da373c; }}
menu menuitem.danger:hover label {{ color: white; }}
.viewer {{ background: rgba(0, 0, 0, 0.9); }}
.viewer-counter {{ color: #949ba4; font-size: {pt(9)}; }}
.viewer-hint {{ color: #6d6f78; font-size: {pt(8)}; }}
.viewer-button {{ background: {INPUT}; background-image: none; border: none; border-radius: 6px; color: #dbdee1;
                  padding: 3px 12px; box-shadow: none; text-shadow: none; }}
.viewer-button:hover {{ background: {SELECTED}; }}
.info {{ color: #949ba4; }}
.empty-hint {{ color: #6d6f78; font-size: {pt(11)}; }}
.empty-tip {{ color: #4e5058; font-size: {pt(8.5)}; }}

.bar {{ background: {SIDEBAR}; padding: 6px 10px; }}
button.voice, button.tool {{ background: {INPUT}; background-image: none; color: #dbdee1; border: none; border-radius: 6px;
               padding: 4px 8px 4px 12px; box-shadow: none; text-shadow: none; }}
button.voice:hover, button.tool:hover {{ background: {SELECTED}; }}
button.tool.active {{ background: {ACCENT}; color: white; }}
.picker {{ background: {SIDEBAR}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px;
           box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5); }}
flowbox.gifs flowboxchild {{ padding: 3px; border-radius: 9px; }}
flowbox.gifs flowboxchild:selected {{ background: {ACCENT}; }}
.suggest {{ background: {SIDEBAR}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5); }}
.suggest list {{ background: transparent; }}
row.suggest-row {{ padding: 3px 10px; border-radius: 6px; }}
row.suggest-row:selected {{ background: {SELECTED}; }}
.suggest-char {{ font-size: {pt(15)}; }}
.suggest-name {{ color: #dbdee1; }}
.suggest-sub {{ color: #949ba4; font-size: {pt(9)}; }}
button.voice.on {{ background: #f23f43; color: white; }}
.user-bar {{ background: {SIDEBAR}; padding: 6px 8px; border-top: 1px solid {BORDER}; }}
button.user-panel {{ background: transparent; background-image: none; border: none; border-radius: 6px;
                     padding: 2px 6px; box-shadow: none; text-shadow: none; }}
button.user-panel:hover {{ background: {HOVER}; }}
.user-name {{ color: #f2f3f5; font-weight: 600; font-size: {pt(9)}; }}
.user-status {{ color: #949ba4; font-size: {pt(8)}; }}
.keycap {{ background: rgba(255, 255, 255, 0.07); color: #b5bac1; border-radius: 4px; padding: 0 5px;
           font-size: {pt(8)}; font-family: monospace; }}
.keycap {{ border: 1px solid rgba(255, 255, 255, 0.1); box-shadow: none; }}  /* GTK themes add a bright outline */
button.voice.on .keycap {{ color: white; }}
button.voice.join {{ background: #248046; color: white; }}
button.voice.join:hover {{ background: #1a6334; }}
button.voice.join .keycap {{ color: white; }}
button.voice:disabled {{ background: {INPUT}; color: #6d6f78; }}
button.voice:disabled .keycap {{ color: #6d6f78; }}
.voice-label {{ color: #949ba4; font-size: {pt(8)}; }}
.voice-label.connected {{ color: #23a55a; font-weight: 700; }}
.voice-channel {{ color: #b5bac1; font-size: {pt(8)}; }}
popover.voice-pop {{ background: {SIDEBAR}; border: 1px solid {SELECTED}; }}
popover.custom-pop {{ background: {SIDEBAR}; border: 1px solid {SELECTED}; }}
popover.members-pop {{ background: {SIDEBAR}; border: 1px solid {SELECTED}; }}
.members-title {{ color: #f2f3f5; font-weight: 700; }}
.members-counts {{ color: #949ba4; font-size: {pt(8.5)}; }}
.member-row {{ border-radius: 6px; }}
.member-row:hover {{ background: {HOVER}; }}
.member-name {{ color: #dbdee1; font-weight: 600; }}
.member-activity {{ color: #949ba4; font-size: {pt(8)}; }}
.custom-pop-title {{ color: #f2f3f5; font-weight: 700; }}
.custom-pop-label {{ color: #949ba4; font-size: {pt(9)}; }}
popover.custom-pop combobox button {{ background: {INPUT}; background-image: none; color: #dbdee1; border: none;
    border-radius: 6px; box-shadow: none; }}
popover.custom-pop combobox button:hover {{ background: {SELECTED}; }}
button.tool.primary {{ background: {ACCENT}; color: white; }}
button.tool.primary:hover {{ background: #4752c4; }}
.voice-pop-title {{ color: #23a55a; font-weight: 700; }}
.voice-face {{ border: 2px solid transparent; border-radius: 999px; padding: 1px; }}
.voice-face.speaking {{ border-color: #23a55a; }}
.voice-person {{ color: #dbdee1; }}
.voice-state {{ color: #949ba4; font-size: {pt(8)}; }}
.voice-state.speaking {{ color: #23a55a; }}
.voice-state.muted, .voice-state.deafened {{ color: #f23f43; }}
.error-text {{ color: #f23f43; font-size: {pt(8)}; }}
.error-text.note {{ color: #949ba4; }}
.grip-mark {{ color: #6d6f78; font-size: {pt(15)}; }}
.grip:hover .grip-mark {{ color: #f2f3f5; }}
.help-icon {{ color: #949ba4; background: {INPUT}; border-radius: 9px; font-weight: 700; font-size: {pt(9)};
              padding: 0 6px; }}
.help-icon:hover {{ color: #f2f3f5; background: {SELECTED}; }}
.help-pop {{ background: {SIDEBAR}; border: 1px solid {BORDER}; }}
.help-section {{ color: #949ba4; font-size: {pt(8)}; font-weight: 700; }}
.help-desc {{ color: #dbdee1; font-size: {pt(9)}; }}
.help-version {{ color: #6d6f78; font-size: {pt(8)}; }}
.help-pop .keycap {{ padding: 0 4px; }}
scrolledwindow undershoot.top, scrolledwindow undershoot.bottom {{ background: none; }}
"""
