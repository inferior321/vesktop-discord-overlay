"""Check: your custom status. Set from the menu on your name in a small pop-up (text, an emoji from the picker,
"Clear after"), shown under your name instead of Online, cleared, changed elsewhere, and its keys (real key
presses, through xdotool)."""

import os
import subprocess
import time

import fakebridge as fb
import vesktop_discord_overlay.overlay as main
from vesktop_discord_overlay import status

GAME = {"name": "video_game", "char": "🎮", "names": ["video_game"]}
PIZZA = {"name": "pizza", "char": "🍕", "names": ["pizza"]}
POG = {"id": "123", "name": "pog", "animated": False, "url": "https://cdn.discordapp.com/emojis/123.png?size=48"}


def respond(method, args):
    if method == "emojiCatalog":
        return {"categories": [{"id": "activity", "emojis": [GAME]}, {"id": "food", "emojis": [PIZZA]}]}
    if method == "emojiForStatus":  # a server emoji you may use in a status (as with Nitro)
        return {"frecent": [PIZZA], "custom": [{"guild": "Fake Server", "guildId": "S1", "emojis": [POG]}]}


fb.install(main, respond)


def key(*keys):
    subprocess.run(["xdotool", "key", "--delay", "40", *keys], env=dict(os.environ))


def type_text(text):
    subprocess.run(["xdotool", "type", "--delay", "20", text], env=dict(os.environ))


def menu(o):
    """The status menu's lines (as plain text)."""
    shown = []
    o._popup_menu = lambda items, *_a, **_k: shown.extend(i[0] if i else "---" for i in items) or True
    o._status_menu()
    del o._popup_menu
    return shown


def sent():
    """What the last setCustomStatus call sent."""
    return [args for method, args in fb.CALLS if method == "setCustomStatus"][-1][0]


def wait(o):
    pass


def start(o):
    assert o.user_status.get_text() == "Online", o.user_status.get_text()
    lines = menu(o)
    assert lines[:2] == ["✎  Set custom status…", "---"] and "Online" in lines[2], lines
    print(f"no custom status: 'Online' under your name; menu {lines[:3]}…", flush=True)
    o._open_custom_status()


def opened(o):
    assert o.custom_pop.get_visible() and o.win.get_focus() is o.custom_text, "the pop-up opens ready to type"
    assert o.custom_after.get_active_text() == "Today", "Clear after starts on Today, like Discord"
    type_text("ranked grind tonight")
    key("ctrl+e")


def emoji_chooser(o):
    assert o.status_emoji_box.get_visible() and o.win.get_focus() is o.status_emoji_search, "Ctrl+E: the emoji grid"
    names = [e.get("char") or e["name"] for e in o.status_emoji_grid.entries]
    assert names == ["🍕", "pog", "🎮", "🍕"], f"frequently used, server emoji, then the categories: {names}"
    type_text("vid")
    key("Return")


def emoji_picked(o):
    assert not o.status_emoji_box.get_visible() and o.win.get_focus() is o.custom_text, "back to the text"
    assert o.custom_emoji_char.get_text() == "🎮" and o.custom_emoji_clear.get_visible()
    assert o.custom_text.get_text() == "ranked grind tonight", o.custom_text.get_text()
    o.custom_after.set_active(2)  # 1 hour
    key("Return")


def saved(o):
    s = sent()
    assert (s["text"], s["emoji"]) == ("ranked grind tonight", {"char": "🎮"}), s
    assert abs(s["expires"] - (time.time() + 3600) * 1000) < 10_000, "Clear after 1 hour"
    assert not o.custom_pop.get_visible()
    assert fb.VOICE["custom"] == o.custom, "what Vesktop reports back matches what's shown (no flicker)"
    assert o.user_status.get_text() == "🎮 ranked grind tonight", o.user_status.get_text()
    assert menu(o)[0] == "✎  🎮 ranked grind tonight", menu(o)[0]
    print("typed, Ctrl+E → search 'vid' → Enter picks 🎮, Enter saves: '🎮 ranked grind tonight' (1 hour)",
          flush=True)
    # Changed in Discord itself (a while after saving here): the panel follows.
    o.custom_set_at = -100
    fb.VOICE["custom"] = {"text": "brb dinner", "emoji": None, "expires": None}
    fb.push_voice()


def changed_elsewhere(o):
    assert o.user_status.get_text() == "brb dinner", o.user_status.get_text()
    print("changed in Discord: 'brb dinner' shows at once", flush=True)
    o._open_custom_status()
    key("ctrl+e")


def esc_layers(o):
    assert o.custom_text.get_text() == "brb dinner", "opens on the current one"
    assert o.custom_emoji_char.get_text() == "😀", "(which has no emoji)"
    assert o.status_emoji_box.get_visible()
    key("Escape")


def esc_once(o):
    assert o.custom_pop.get_visible() and not o.status_emoji_box.get_visible(), (
        f"Esc: the emoji grid closes first (pop-up {o.custom_pop.get_visible()}, "
        f"grid {o.status_emoji_box.get_visible()})")
    key("Escape")


def esc_twice(o):
    assert not o.custom_pop.get_visible() and o.win.get_visible(), "Esc again: the pop-up, not the panel"
    assert fb.VOICE["custom"]["text"] == "brb dinner" and sent()["text"] != "brb dinner", "Esc saves nothing"
    print("Esc closes the emoji grid, then the pop-up (nothing saved), not the panel", flush=True)
    o._open_custom_status()
    o._toggle_status_emoji()


def server_emoji(o):
    o.status_emoji_search.set_text("pog")
    o.status_emoji_search.emit("activate")
    assert o.custom_emoji_pic.get_visible() and not o.custom_emoji_char.get_visible(), "a server emoji's picture"
    o.custom_text.set_text("")
    o.custom_after.set_active(4)  # Don't clear
    o._save_custom_status()
    s = sent()
    assert s == {"text": "", "emoji": {"id": "123", "name": "pog"}, "expires": None}, s
    assert o.user_status_emoji.get_visible() and o.user_status.get_text() == "", "just the emoji's picture"
    assert menu(o)[0] == "✎  :pog:", menu(o)[0]
    print("a server emoji alone, Don't clear: sent as {id, name}; its picture shows under your name", flush=True)
    o._open_custom_status()
    o.custom_emoji_clear.clicked()
    o._save_custom_status()  # no text, no emoji: clears


def cleared(o):
    assert sent() is None and o.user_status.get_text() == "Online" and not o.user_status_emoji.get_visible()
    o._open_custom_status()
    o.custom_text.set_text("x")
    before = len(fb.CALLS)
    o._clear_custom_status()
    assert [args for method, args in fb.CALLS[before:] if method == "setCustomStatus"] == [(None,)], "Clear clears"


def clear_closed(o):
    assert not o.custom_pop.get_visible(), "Clear closes the pop-up"
    o._open_custom_status()


def hidden_with_panel(o):
    o.hide()
    assert not o.win.get_visible() and not o.custom_pop.get_visible(), "hiding the panel closes the pop-up"
    today = status.expiry("today")
    assert time.time() * 1000 < today <= (time.time() + 86400) * 1000 and time.localtime(today / 1000)[3:6] == (0, 0, 0)
    assert status.expiry(None) is None
    print("emptied or Clear: cleared, back to 'Online'; hiding the panel closes the pop-up; Today ends at midnight",
          flush=True)


fb.run_steps(main, [wait, start, wait, opened, wait, emoji_chooser, wait, emoji_picked, wait, saved, wait,
                    changed_elsewhere, wait, esc_layers, wait, esc_once, wait, esc_twice, wait, server_emoji,
                    wait, cleared, wait, clear_closed, wait, hidden_with_panel], interval_ms=600)
