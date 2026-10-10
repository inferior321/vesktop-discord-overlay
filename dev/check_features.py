"""Check: reactions, editing / deleting your messages, jumping to a reply's original, draft marks, status and
leaving voice."""

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

AUTHORS = ["Friend 1", "You"]
fb.OLDER[:] = [fb.msg(i - 200, f"older message {i}", author=AUTHORS[i % 2]) for i in range(120)]
fb.MESSAGES[:] = [fb.msg(i, f"message number {i}", author=AUTHORS[i % 2]) for i in range(40)]
fb.MESSAGES[30] = dict(fb.MESSAGES[30], reactions=[{"emoji": {"char": "👍", "name": "thumbsup"}, "count": 2,
                                                   "me": False}])
ORIGINAL = fb.OLDER[5]  # 115 messages further back: three batches of older history
fb.MESSAGES[38] = dict(fb.MESSAGES[38], reply={"id": ORIGINAL["id"], "author": "Friend 1", "text": "older…"})
fb.install(main)


def message(o, i):
    return next(m for m in o._merged_messages() if m["id"] == str(10**18 + i))


def calls(method):
    return [args for name, args in fb.CALLS if name == method]


def reaction(o, i, char):
    return next((r for r in message(o, i).get("reactions", []) if r["emoji"].get("char") == char), None)


def wait(o):
    pass


# ----- reactions -----

def toggle_on(o):
    o._toggle_reaction(message(o, 30), reaction(o, 30, "👍"))


def toggled_on(o):
    r = reaction(o, 30, "👍")
    print(f"click 👍: count {r['count']}, mine {r['me']}", flush=True)
    assert r["count"] == 3 and r["me"], "clicking adds yours"
    o._toggle_reaction(message(o, 30), r)


def toggled_off(o):
    r = reaction(o, 30, "👍")
    print(f"click again: count {r['count']}, mine {r['me']}", flush=True)
    assert r["count"] == 2 and not r["me"], "clicking again removes yours"


def open_reaction_picker(o):
    o.reply.grab_focus()
    o._open_reaction_picker(message(o, 30))
    assert o.picker.get_visible() and o.picker.reacting
    assert o.picker.mode_label.get_text() == "Reacting to Friend 1's message", o.picker.mode_label.get_text()
    assert not o.picker.page_buttons["gif"].get_visible(), "no GIFs tab while reacting"


def pick_reaction(o):
    o._insert_emoji({"name": "skull", "char": "💀", "names": ["skull"]})
    assert not o.picker.get_visible(), "picker closes after one pick"
    assert o.win.get_focus() is o.reply, "focus back where it was"


def picked(o):
    r = reaction(o, 30, "💀")
    print(f"picked 💀 as a reaction: {r and (r['count'], r['me'])}", flush=True)
    assert r and r["me"], "picked emoji added as a reaction"
    assert o.reply.get_text() == "", "nothing typed into the reply box"
    o._toggle_picker("emoji")  # the ordinary picker afterwards
    assert not o.picker.reacting and o.picker.page_buttons["gif"].get_visible(), "GIFs tab back"
    assert not o.picker.mode_label.get_visible()
    o._close_picker()


# ----- editing and deleting -----

def start_edit(o):
    o.reply.set_text("my draft")
    o._start_reply(message(o, 36))
    o._start_edit(message(o, 39))


def editing(o):
    assert o.reply.get_text() == "message number 39", o.reply.get_text()
    assert o.edit_note.get_visible() and not o.reply_note.get_visible()
    assert o.message_widgets[message(o, 39)["id"]].get_style_context().has_class("msg-editing")
    o._escape()
    assert o.reply.get_text() == "my draft" and o.replying_to is not None, "draft and reply restored"
    assert not o.message_widgets[message(o, 39)["id"]].get_style_context().has_class("msg-editing")
    print("Esc while editing: draft and reply came back", flush=True)
    o._cancel_reply()
    o.reply.set_text("")
    o._start_edit(message(o, 39))


def save_edit(o):
    o.reply.set_text("fixed the typo")
    o._save_edit()


def saved(o):
    m = message(o, 39)
    print(f"saved edit: {m['content']!r}, edited {m['edited']}", flush=True)
    assert m["content"] == "fixed the typo" and m["edited"]
    assert o.editing is None and not o.edit_note.get_visible()
    o._start_edit(message(o, 37))


def empty_edit(o):
    o.reply.set_text("")
    o._save_edit()
    assert o.deleting and o.delete_note.get_visible(), "empty edit offers to delete"
    o._confirm_delete()


def deleted(o):
    ids = [m["id"] for m in o._merged_messages()]
    print(f"deleted message 37: {str(10**18 + 37) not in ids}", flush=True)
    assert str(10**18 + 37) not in ids and not o.delete_note.get_visible()


# ----- reply jump -----

def jump(o):
    assert ORIGINAL["id"] not in o.message_widgets
    o._jump_to_message(ORIGINAL["id"])


def jumped(o):
    body = o.message_widgets.get(ORIGINAL["id"])
    print(f"jumped to the original: loaded {body is not None}, "
          f"flashing {body is not None and body.get_style_context().has_class('msg-flash')}", flush=True)
    assert body is not None and o.jump_target is None
    assert body.get_style_context().has_class("msg-flash")


# ----- right-clicking message text -----

def text_menu(o):
    from vesktop_discord_overlay.gtk import Gtk

    def selectable(widget):
        if isinstance(widget, Gtk.Label) and widget.get_selectable():
            return widget
        for child in widget.get_children() if isinstance(widget, Gtk.Container) else []:
            found = selectable(child)
            if found:
                return found

    text = selectable(o.message_widgets[message(o, 35)["id"]])  # one of yours
    layouts = []
    for highlighted in (False, True):
        text.select_region(0, 7 if highlighted else 0)
        menu = Gtk.Menu()
        for gtk_item in ("Cut", "Copy", "Paste", "Delete", "Select All"):  # what GTK puts there itself
            menu.append(Gtk.MenuItem(label=gtk_item))
        o._fill_text_menu(text, menu, message(o, 35))
        layouts.append(["---" if isinstance(i, Gtk.SeparatorMenuItem) else
                        i.get_label() + (" (red)" if i.get_style_context().has_class("danger") else "")
                        for i in menu.get_children()])
    for layout in layouts:
        print("text menu: " + " | ".join(layout), flush=True)
    assert layouts[0] == ["Reply", "Add reaction", "Edit message", "---", "Copy text", "Copy message link", "---",
                          "Open in Vesktop", "---", "Delete message (red)"], layouts[0]
    assert layouts[1] == layouts[0][:4] + ["Copy selection"] + layouts[0][4:], layouts[1]
    others = [i[0] if i else "---" for i in o._message_items(message(o, 34))]  # someone else's
    print("their message: " + " | ".join(others), flush=True)
    assert others == ["Reply", "Add reaction", "---", "Copy text", "Copy message link", "---", "Open in Vesktop"]


# ----- clicking outside an open picker -----

def click_on(widget, dx=20, dy=10):
    """A real mouse click on a widget (through the test display)."""
    import os
    import subprocess
    x, y = widget.translate_coordinates(widget.get_toplevel(), 0, 0)
    ox, oy = widget.get_toplevel().get_window().get_origin()[1:]
    env = dict(os.environ)
    subprocess.run(["xdotool", "mousemove", str(ox + x + dx), str(oy + y + dy), "click", "1"], env=env)


def picker_open(o):
    o._focus_reply()
    o._toggle_picker("emoji")
    assert o.picker.get_visible()
    click_on(o.picker.search)


def picker_click_inside(o):
    assert o.picker.get_visible(), "a click inside the picker keeps it open"
    click_on(o.tool_buttons["gif"])


def picker_switched(o):
    assert o.picker.get_visible() and o.picker.page == "gif", "the GIF button still switches pages"
    click_on(next(r for r in o.rows if r.data["id"] == "F3"))


def picker_clicked_away(o):
    print(f"clicked a chat while the picker was open: picker {'open' if o.picker.get_visible() else 'closed'}, "
          f"open chat {o.channel_id}", flush=True)
    assert not o.picker.get_visible(), "clicking outside closes it"
    assert o.channel_id == "F3", "and the click still opened the chat"
    o._open_reaction_picker(message(o, 30))


def reaction_picker_open(o):
    assert o.picker.get_visible() and o.picker.reacting
    click_on(o.msg_scroll, dx=40, dy=40)


def reaction_picker_closed(o):
    assert not o.picker.get_visible() and not o.picker.reacting, "clicking the messages closes the reaction picker"
    print("reaction picker closed by clicking the messages", flush=True)


# ----- Ctrl+E / Ctrl+G -----

def key(o, combo):
    import os
    import subprocess
    subprocess.run(["xdotool", "key", combo], env=dict(os.environ))


def ctrl_e(o):
    o._focus_reply()
    key(o, "ctrl+e")


def ctrl_e_opened(o):
    assert o.picker.get_visible() and o.picker.page == "emoji", "Ctrl+E opens the emoji picker"
    key(o, "ctrl+g")


def ctrl_g_switched(o):
    assert o.picker.get_visible() and o.picker.page == "gif", "Ctrl+G switches to GIFs"
    key(o, "ctrl+g")


def ctrl_g_closed(o):
    assert not o.picker.get_visible(), "the same key again closes it"
    o._open_reaction_picker(message(o, 30))
    key(o, "ctrl+g")


def reaction_ignores_ctrl_g(o):
    assert o.picker.get_visible() and o.picker.reacting and o.picker.page == "emoji", "no GIFs while reacting"
    o._close_picker()
    print("Ctrl+E / Ctrl+G open, switch and close the pickers; Ctrl+G ignored while reacting", flush=True)


# ----- drafts, status, voice -----

def drafts(o):
    o.drafts["F5"] = "see you"
    o.drafts[o.channel_id] = "half a thought"  # the open chat: no mark while you're in it
    o._update_draft_marks()
    marks = {k[1]: r.draft.get_visible() for k, r in o.row_cache.items()
             if k[0] == "friend" and k[1] in ("F2", "F5", o.channel_id)}
    print(f"draft marks: {marks} (open chat {o.channel_id})", flush=True)
    assert marks == {"F2": False, "F5": True, o.channel_id: False}


def status(o):
    o._set_status("dnd")
    assert calls("setStatus")[-1] == ("dnd",) and o.status == "dnd"
    fb.VOICE["channel"] = "General"
    o._refresh_voice(skip_if_busy=False)


def in_voice(o):
    assert o.disconnect_btn.get_visible(), "Disconnect shown in voice"
    o._disconnect_voice()
    assert not o.disconnect_btn.get_visible() and calls("disconnectVoice")
    print("status set to dnd; Disconnect shown in voice and leaves it", flush=True)


fb.run_steps(main, [toggle_on, wait, toggled_on, wait, toggled_off, open_reaction_picker, pick_reaction, wait,
                    picked, start_edit, wait, editing, wait, save_edit, wait, saved, wait, empty_edit, wait,
                    deleted, jump, wait, jumped, text_menu, picker_open, picker_click_inside, picker_switched,
                    picker_clicked_away, reaction_picker_open, reaction_picker_closed, ctrl_e, ctrl_e_opened, ctrl_g_switched,
                    ctrl_g_closed, reaction_ignores_ctrl_g, drafts, status, wait,
                    in_voice], interval_ms=500)
