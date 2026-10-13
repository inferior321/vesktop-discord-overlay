"""Check: a server channel's member list (real clicks and keys, through xdotool): clicking the server's name in
the chat header opens it (not in a DM); role groups and people show with colours and activities; scrolling to the
end loads more; clicking someone offers Message / Mention, which open your DM / put @them in the reply box; Esc
and switching chats close it."""

import os
import subprocess
from types import SimpleNamespace

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

fb.install(main)


def mouse(*args):
    subprocess.run(["xdotool", *args], env=dict(os.environ))


def click_widget(o, widget, dx=10, dy=8):
    x, y = widget.translate_coordinates(o.win, dx, dy)
    ox, oy = o.win.get_window().get_origin()[1:]
    mouse("mousemove", str(ox + x), str(oy + y), "mousedown", "1", "sleep", "0.1", "mouseup", "1")


def row(o, rid):
    return next(r for r in o.rows if r.data["id"] == rid)


def calls(method):
    return [args for m, args in fb.CALLS if m == method]


def shown(o):
    """The list as text: headings, and names (with the activity line if any)."""
    out = []
    for child in o.members_list.get_children():
        if isinstance(child, main.Gtk.Label):
            out.append(child.get_text())
        else:
            texts = child.get_child().get_children()[1].get_children()
            out.append(" | ".join(t.get_text() for t in texts))
    return out


def wait(o):
    pass


def in_dm(o):
    assert not o.members_hint.get_visible(), "no member list in a DM"
    o._toggle_members()
    assert not o.members_pop.get_visible()
    o._set_tab("servers")
    o._activate(row(o, "S1"))


def open_channel(o):
    o._activate(row(o, "C1"))


def in_server(o):
    assert o.members_hint.get_visible() and o.members_target.get_tooltip_text() == "Members"
    click_widget(o, o.members_target)  # the server's name


def opened(o):
    assert o.members_pop.get_visible(), "clicking the server's name opens the member list"
    assert o.members_counts.get_text() == "1,234 online · 5,678 members", o.members_counts.get_text()
    lines = shown(o)
    assert lines[:4] == ["MODERATORS — 2", "Mod 1 👑 | Playing Minecraft", "Mod 2", "ONLINE — 250"], lines[:4]
    assert "Member 7 · bot" in lines and len(lines) == 100, (len(lines), lines[-1])
    name = o.members_list.get_children()[1].get_child().get_children()[1].get_children()[0]
    assert "#f0b232" in name.get_label(), "names in their role colour"
    print(f"server name clicked: member list with {len(lines)} rows, groups, colours, activities", flush=True)
    adj = o.members_scroll.get_vadjustment()
    adj.set_value(adj.get_upper())  # scroll to the end


def more(o):
    assert calls("members")[-1] == ("C1", 200), calls("members")[-1]
    assert len(shown(o)) == 200, len(shown(o))
    print("scrolling to the end loaded the next page", flush=True)
    menu = []
    o._popup_menu = lambda items, _event: menu.extend(items) or True
    o._member_menu(o.member_rows[3 + 2], SimpleNamespace(button=1))  # Member 2
    del o._popup_menu
    assert [name for name, _ in menu] == ["Message", "Mention"], menu
    o.reply.set_text("hi")
    o.reply.set_position(-1)
    dict(menu)["Mention"]()


def mentioned(o):
    assert o.reply.get_text() == "hi @member2 " and not o.members_pop.get_visible(), repr(o.reply.get_text())
    print("Mention puts '@member2 ' in the reply box", flush=True)
    o._toggle_members()


def reopened(o):
    assert o.members_pop.get_visible() and len(shown(o)) == 200, "reopened as it was (same channel)"
    mouse("key", "Escape")


def esc_closed(o):
    assert not o.members_pop.get_visible() and o.win.get_visible(), "Esc closes the list, not the panel"
    o._toggle_members()


def message(o):
    o._message_member(o.member_rows[1])


def messaged(o):
    assert calls("openDM")[-1] == ("m1",) and o.channel_id == "F2" and o.tab == "friends", (o.channel_id, o.tab)
    assert not o.members_pop.get_visible() and o.reply.has_focus()
    print("Esc closes it; Message opens your DM with them, ready to type", flush=True)
    o._set_tab("servers")
    o._activate(row(o, "C1"))
    o._toggle_members()


def switch_chat(o):
    assert o.members_pop.get_visible()
    o._activate(row(o, "C2"))


def switched(o):
    assert not o.members_pop.get_visible(), "another chat closes the list"
    o._toggle_members()


def fresh_list(o):
    assert o.members_for == "C2" and calls("members")[-1] == ("C2", 100), "a new channel starts its own list"
    print("switching chats closes the list; the next one starts fresh", flush=True)


fb.run_steps(main, [wait, in_dm, wait, open_channel, wait, in_server, wait, opened, wait, more, wait, mentioned,
                    wait, reopened, wait, esc_closed, wait, message, wait, messaged, wait, switch_chat, wait,
                    switched, wait, fresh_list], interval_ms=700)
