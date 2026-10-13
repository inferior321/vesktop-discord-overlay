"""Check: a server's channel list as Discord's sidebar has it (category headings, collapsing them, a joined
thread under its channel) and forums: → on a forum lists its posts, scrolling to the end loads older ones,
→ on a post opens it as a chat, ← comes back out level by level, Ctrl+Shift+Right finds a post again."""

from types import SimpleNamespace

import fakebridge as fb
import vesktop_discord_overlay.overlay as main


def category(cid, name, collapsed=False):
    return {"kind": "category", "id": cid, "name": name, "collapsed": collapsed, "canCollapse": True}


fb.CHANNELS[:] = [
    category("K1", "Bulletin Board"),
    fb.card("C1", "general"),
    dict(fb.card("T1", "patch notes talk"), kind="thread", parentId="C1", preview=None),
    fb.card("C2", "memes"),
    category("K2", "Archive", collapsed=True),
    category("K3", "Support Forums"),
    dict(fb.card("F1", "help", unread=True), forum=True, newPosts=3, preview=None),
]
fb.POSTS["F1"] = {"posts": [fb.post(f"P{i}", f"question {i}", replies=i, unread=i < 3, new_count=2 if i == 1 else None)
                            for i in range(1, 31)],
                  "older": [fb.post(f"P{i}", f"old question {i}") for i in range(31, 37)]}


def respond(method, args):
    if method == "messages" and args[0].startswith("P"):
        return {"id": args[0], "name": "question", "place": "Fake Server › help", "icon": None, "guildId": "S1",
                "forum": {"id": "F1", "name": "help"}, "typing": [], "firstUnreadId": None,
                "messages": [dict(m) for m in fb.MESSAGES[-5:]]}


fb.install(main, respond)


def row(o, rid):
    return next(r for r in o.rows if r.data["id"] == rid)


def ids(o):
    return [r.data["id"] for r in o.rows]


def menu_items(o, r):
    shown = []
    o._popup_menu = lambda items, _event: shown.extend(name for name, _ in items) or True
    o._list_menu(o.listbox, SimpleNamespace(button=3, y=r.get_allocation().y + 5))
    del o._popup_menu
    return shown


def calls(method):
    return [args for m, args in fb.CALLS if m == method]


def wait(o):
    pass


def open_server(o):
    o._set_tab("servers")
    o._activate(row(o, "S1"))


def listed(o):
    assert ids(o) == ["K1", "C1", "T1", "C2", "K2", "K3", "F1"], ids(o)
    assert row(o, "K1").name.get_text() == "BULLETIN BOARD" and row(o, "K2").arrow.get_text() == "▸"
    assert row(o, "T1").icons["thread"].get_visible(), "a thread: ↳, under its channel"
    assert row(o, "F1").icons["forum"].get_visible() and row(o, "F1").new.get_text() == "3 new"
    o._focus_list()
    o._highlight(row(o, "C1"))
    o._move(1)
    o._move(1)
    assert o._highlighted() is row(o, "C2"), "the thread is a row the arrows go through"
    o._move(1)
    assert o._highlighted() is row(o, "F1"), "the arrows skip category headings"
    print(f"channels as Discord shows them: {ids(o)}; arrows skip headings", flush=True)
    o._activate(row(o, "K1"))  # click the heading


def collapsed(o):
    assert calls("collapseCategory")[-1] == ("K1", True), calls("collapseCategory")
    assert row(o, "K1").arrow.get_text() == "▸", "collapsed (in Discord too)"
    assert menu_items(o, row(o, "K1")) == [], "no menu on a heading"
    items = menu_items(o, row(o, "F1"))
    assert items == ["Mark as read", "Open in Vesktop"], items
    print("clicking a heading collapses it (sent to Discord); forums: Mark as read / Open in Vesktop", flush=True)
    o._highlight(row(o, "F1"))
    o._list_key("Right", None)


def in_forum(o):
    assert o.forum == {"id": "F1", "name": "help"} and o.back_label.get_text() == "←  help"
    assert ids(o)[:3] == ["P1", "P2", "P3"] and len(ids(o)) == 30, ids(o)
    first = row(o, "P1")
    assert first.preview.get_text() == "Friend 1 · 1 reply" and first.new.get_text() == "2 new"
    assert first.name.get_style_context().has_class("unread") and not first.dot.get_visible()
    assert row(o, "P3").preview.get_text() == "Friend 1 · 3 replies"
    print("→ on the forum: its posts, with starter, replies and new", flush=True)
    adj = o.list_scroll.get_vadjustment()
    adj.set_value(adj.get_upper())  # scroll to the end


def older_loaded(o):
    # (While you stay at the end, the next page follows: here pages are 3 posts, so both of them.)
    assert calls("olderPosts") and set(calls("olderPosts")) == {("F1",)}, calls("olderPosts")
    assert ids(o)[30:33] == ["P31", "P32", "P33"], ids(o)[29:]
    print(f"scrolling to the end loaded older posts ({len(calls('olderPosts'))} pages)", flush=True)
    o._highlight(row(o, "P2"))
    o._list_key("Right", None)


def post_open(o):
    assert o.channel_id == "P2" and o.reply.has_focus(), "→ on a post opens it, ready to type"
    o._focus_list()
    o._list_key("Left", None)


def back_out(o):
    assert o.channel_id is None and o.forum, "← first closes the post"
    o._list_key("Left", None)
    assert o.forum is None and o._highlighted() is row(o, "F1"), "← again: back to the channels, on the forum"
    o._list_key("Left", None)
    assert o.server is None, "← again: the server list"
    print("← closes the post, then leaves the forum, then the server", flush=True)
    o._set_tab("friends")
    o._open_conversation("P5")  # e.g. from the Ctrl+← history


def reveal(o):
    o._show_chat_in_sidebar()


def revealed(o):
    assert o.tab == "servers" and o.server["id"] == "S1" and o.forum["id"] == "F1", (o.tab, o.server, o.forum)
    assert o._highlighted() is row(o, "P5"), "Ctrl+Shift+Right: the post, highlighted in its forum"
    print("Ctrl+Shift+Right on a post: shown in its forum, highlighted", flush=True)
    o._back()  # (the open post is in this view: closes it)
    o._leave_forum()
    o._activate(row(o, "F1"))
    o._mark_chat_read("F1")


def marked(o):
    assert ("F1",) in calls("markRead"), calls("markRead")
    print("Mark as read on a forum asks Vesktop to mark it read", flush=True)
    o._focus_list()
    o.search.set_text("question 2")


def searched(o):
    shown = [r.data["id"] for r in o._visible_rows()]
    expected = [r.data["id"] for r in o.rows if "question" in r.data["name"] and "2" in r.data["name"]]
    assert shown == expected and "P2" in shown and "P3" not in shown, shown  # (each word must appear)
    o.search.set_text("")
    o._highlight(row(o, "P20"))


def update_arrives(o):
    state["scroll"] = o.list_scroll.get_vadjustment().get_value()  # (once the list has settled)
    assert state["scroll"] > 0, "scrolled down to P20"
    fb.POSTS["F1"]["posts"][19] = dict(fb.POSTS["F1"]["posts"][19], replies=99)  # a reply arrives meanwhile
    fb.push_lists()


def live_update(o):
    assert o._highlighted() is row(o, "P20") and row(o, "P20").preview.get_text() == "Friend 1 · 99 replies"
    assert abs(o.list_scroll.get_vadjustment().get_value() - state["scroll"]) < 2, "kept the scroll position"
    print("search inside a forum filters its posts; a live update keeps the highlight and scroll", flush=True)
    o._set_tab("friends")
    o._set_tab("servers")


def tabs_back(o):
    assert o.forum and o.forum["id"] == "F1" and ids(o)[0] == "P1", "Friends and back: still in the forum"
    o._leave_forum()


def rows_freed(o):
    assert not [k for k in o.row_cache if k[0] == "post"], "a left forum's post rows are freed"
    o._activate(row(o, "K3"))  # collapse a heading, then search: headings hide, matching channels show
    o.search.set_text("help")


def collapsed_search(o):
    assert [r.data["id"] for r in o._visible_rows()] == ["F1"] and not o._filter_row(row(o, "K3"))
    o.search.set_text("")
    print("Friends and back keeps the forum; leaving frees its rows; searching hides headings", flush=True)


state = {}
fb.run_steps(main, [wait, open_server, wait, listed, wait, collapsed, wait, in_forum, wait, wait, older_loaded,
                    wait, post_open, wait, back_out, wait, reveal, wait, wait, revealed, wait, marked, wait,
                    searched, wait, update_arrives, wait, wait, live_update, wait, tabs_back, wait, rows_freed,
                    wait, collapsed_search],
             interval_ms=600)
