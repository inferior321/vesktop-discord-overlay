"""Every tunable setting, with its default. To change one, don't edit this file (updates replace it): put the
line in ~/.config/vesktop-discord-overlay/settings.py instead, e.g. `TEXT_SCALE = 1.3`. The installer creates
that file with examples. Changes take effect the next time the overlay starts.

Sizes are in pixels unless the name says otherwise; times say their unit (_MS, _SECONDS, _MINUTES).
"""

import os
from pathlib import Path

from Xlib import X

# ---- Vesktop connection --------------------------------------------------------------------------------
DEBUG_PORT = 9222  # Vesktop's DevTools port (Vesktop must be started with --remote-debugging-port=<this>)
VESKTOP_APP = "dev.vencord.Vesktop"  # the Flatpak the overlay works with
VESKTOP_LAUNCH = ["flatpak", "run", VESKTOP_APP]
FOLLOW_CHECK_SECONDS = 3  # --follow-vesktop: how often to check whether Vesktop is still running
FOLLOW_STARTUP_GRACE = 90  # --follow-vesktop: seconds to wait for Vesktop to appear before giving up

# ---- Hotkey ----------------------------------------------------------------------------------------------
HOTKEY_KEYSYM = "grave"
HOTKEY_MODIFIERS = X.ControlMask | X.ShiftMask  # Ctrl+Shift+`
HOTKEY_LABEL = "Ctrl+Shift+`"  # how the hotkey is shown to you

# ---- Text ------------------------------------------------------------------------------------------------
TEXT_SCALE = 1.1  # all text in the panel, relative to your desktop's font size (1 = same size)

# ---- Opacity (Ctrl+Up / Ctrl+Down) ---------------------------------------------------------------------
OPACITY_STEP = 0.05
OPACITY_MIN = 0.30  # never fainter than this, so the panel can't effectively disappear
NOTE_SHOW_MS = 2500  # how long short notes ("Opacity 75%", "Saved to Downloads/…") stay in the bottom bar

# ---- Panel layout ----------------------------------------------------------------------------------------
PANEL_MAX_W, PANEL_MAX_H = 1080, 720  # the panel's size on large screens...
PANEL_SCREEN_W, PANEL_SCREEN_H = 0.72, 0.8  # ...and at most this share of a smaller screen
SIDEBAR_W = 330
CARD_AVATAR = 40  # friend / server pictures in the list
MESSAGE_AVATAR = 36
HEADER_AVATAR = 32
USER_AVATAR = 32  # you, in the user panel at the bottom of the sidebar
VOICE_AVATAR = 24  # people in voice channels (the server list; click "Voice connected")
HELP_HOVER_SIZE = 30  # hover target around the "?" (bigger than the icon, so it's easy to stay on)
ERROR_MAX_CHARS = 60  # an error message gets this much room in the bottom bar before the voice label
PICKER_MIN_H, PICKER_MAX_H = 220, 380  # emoji / GIF picker height

# ---- Messages --------------------------------------------------------------------------------------------
MESSAGE_COUNT = 30  # newest messages shown when a chat opens
OLDER_BATCH = 50  # older messages loaded each time you reach the top
GROUP_GAP_MINUTES = 5  # a longer pause between messages from the same person starts a new group
SCROLL_STEP = 60  # Up / Down in the reply box
SCROLL_EDGE = 40  # this close to the bottom counts as "at the newest"; this close to the top loads older
HISTORY_LENGTH = 25  # chats remembered for Ctrl+Left / Ctrl+Right
SCROLL_ANCHOR_SECONDS = 1.5  # after loading older messages, keep the one you were reading in place this long
REPLY_SEARCH_BATCHES = 10  # clicking a reply's quote: older batches to load at most, looking for the original
FLASH_MS = 2000  # how long a message you jumped to stays highlighted
DISCARD_BATCH = 40  # message rows destroyed per step when a chat is cleared (so the panel never freezes)

# ---- Timing ----------------------------------------------------------------------------------------------
LIST_POLL_MS = 15000  # re-read the sidebar and Mute / Deafen this often as a safety net (changes show instantly)
CHAT_POLL_MS = 10000  # re-read the open chat this often as a safety net; changes normally show instantly
LIVE_LIST_REFRESH_MS = 1000  # when anything in the lists changes (messages, reads, online status), refresh the
                             # sidebar at most this often
FOCUS_DELAY_MS = 50  # after the panel appears, before taking keyboard focus
CLICK_AWAY_GRACE_SECONDS = 0.6  # ignore focus changes this soon after opening (the panel taking focus)
CLICK_AWAY_CHECK_MS = 150  # after losing focus, look again before deciding you clicked away
HELP_HOVER_CHECK_MS = 200  # the "?" list: how soon to re-check whether the mouse really left
ERROR_SHOW_MS = 5000
RELOAD_AFTER_SEND_MS = 300  # re-read the chat this long after sending, to show your message
VESKTOP_FOCUS_DELAY_MS = 250  # Open in Vesktop: after raising Vesktop, before focusing its message box
GIF_SEARCH_DELAY_MS = 350  # wait for a pause in typing before searching GIFs
TYPING_REPORT_SECONDS = 3  # tell Discord you're typing at most this often (Discord throttles further)
VOICE_SETTLE_SECONDS = 1.5  # after Mute/Deafen, how long to trust the button over Discord's answer

# ---- Media and emoji -------------------------------------------------------------------------------------
MEDIA_MAX_W, MEDIA_MAX_H = 360, 280  # images and GIFs in messages
STICKER_SIZE = 160
YOUTUBE_MAX_W, YOUTUBE_MAX_H = 480, 270  # inline YouTube player (and its thumbnail)
INLINE_EMOJI = 20  # server emoji inside a line of text (grows with TEXT_SCALE)
JUMBO_EMOJI = 44  # emoji-only messages
JUMBO_LIMIT = 27  # Discord shows up to this many emoji-only characters large
EMOJI_CELL = 40  # emoji picker grid
GIF_COLUMNS = 3
SUGGESTION_COUNT = 8  # ':' emoji suggestions
EMOJI_SEARCH_LIMIT = 400

# ---- Downloads and cache ---------------------------------------------------------------------------------
MAX_DOWNLOAD = 25 * 1024 * 1024
MAX_UPLOAD_MB = 10  # Discord's upload limit without Nitro
UPLOAD_TIMEOUT_SECONDS = 120
CACHE_MAX_AGE_DAYS = 14  # downloaded images / GIFs unused this long are deleted
MEDIA_MEMORY_LARGE = 150  # large decoded images / GIFs kept in memory (older ones are re-read from disk)
MEDIA_SMALL_PX = 128  # images this size or smaller (avatars, icons, emoji) always stay in memory
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "vesktop-discord-overlay"
LOG_MAX_KB = 512  # overlay.log (when started from the app menu): over this, it's trimmed to its newest half
STATE_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "vesktop-discord-overlay" / "state.json"

# ---- Your settings ---------------------------------------------------------------------------------------
# ~/.config/vesktop-discord-overlay/settings.py overrides any of the settings above. It's ordinary Python
# (`X` is there for the hotkey's modifiers), and updates never touch it.
SETTINGS_FILE = STATE_FILE.parent / "settings.py"


def _apply_your_settings():
    if not SETTINGS_FILE.exists():
        return
    import sys
    settings = {"X": X, "Path": Path}
    try:
        exec(compile(SETTINGS_FILE.read_text(), str(SETTINGS_FILE), "exec"), settings)
    except Exception as exc:  # noqa: BLE001 - a broken settings file mustn't stop the overlay
        print(f"vesktop-discord-overlay: ignoring {SETTINGS_FILE}: {exc}", file=sys.stderr, flush=True)
        return
    known = {name for name in globals() if name.isupper()}
    for name, value in settings.items():
        if name.isupper() and name in known:
            globals()[name] = value
        elif name.isupper():
            print(f"vesktop-discord-overlay: {SETTINGS_FILE}: there's no setting called {name}", file=sys.stderr,
                  flush=True)


_apply_your_settings()
