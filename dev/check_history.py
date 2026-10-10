"""Check: Ctrl+Left / Right change only the chat (the sidebar stays put); Ctrl+Shift+Right brings the sidebar
to the chat; chats that leave the history are forgotten."""

import fakebridge as fb
import vesktop_discord_overlay.overlay as main
from vesktop_discord_overlay.config import HISTORY_LENGTH

fb.install(main)


def sidebar(o):
    row = o._highlighted()
    return o.tab, o.server and o.server["id"], row.data["id"] if row else None


def into_server_channel(o):
    o._set_tab("servers")
    o._activate(next(r for r in o.rows if r.data["id"] == "S1"))


def open_channel(o):
    o._activate(next(r for r in o.rows if r.data["id"] == "C1"))
    assert o.channel_id == "C1" and [e["id"] for e in o.history] == ["F1", "C1"], o.history


def back_in_history(o):
    o._step_history(-1)
    print(f"Ctrl+Left: chat {o.channel_id}, sidebar {sidebar(o)}", flush=True)
    assert o.channel_id == "F1" and sidebar(o) == ("servers", "S1", "C1"), "sidebar stays put"


def show_in_sidebar(o):
    o.search.set_text("gen")
    o._show_chat_in_sidebar()
    print(f"Ctrl+Shift+Right: sidebar {sidebar(o)}, search '{o.search.get_text()}'", flush=True)
    assert sidebar(o) == ("friends", "S1", "F1") and o.search.get_text() == ""


def forward_then_show(o):
    o._step_history(1)
    assert o.channel_id == "C1" and sidebar(o)[0] == "friends"
    o._show_chat_in_sidebar()
    assert sidebar(o) == ("servers", "S1", "C1"), sidebar(o)
    print(f"Ctrl+Right then Ctrl+Shift+Right: sidebar {sidebar(o)}", flush=True)


def forgets_left_chats(o):
    o.older["F1"] = [fb.msg(1, "old")]
    o.scroll_memory["F1"] = ("1", 0)
    for i in range(HISTORY_LENGTH):  # pushes F1 out of the history
        o._open_conversation(f"X{i}")
    assert "F1" not in o.older and "F1" not in o.scroll_memory, "left chat forgotten"
    assert len(o.history) == HISTORY_LENGTH
    print("chat pushed out of the history: its loaded messages are dropped", flush=True)


fb.run_steps(main, [into_server_channel, open_channel, back_in_history, show_in_sidebar, forward_then_show,
                    forgets_left_chats])
