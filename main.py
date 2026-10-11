#!/usr/bin/env python3
"""vesktop-discord-overlay: a Ctrl+Shift+` overlay for Vesktop on X11.

Press Ctrl+Shift+` anywhere to pop up a panel with your Discord friends and servers,
read recent messages, reply, and toggle mute/deafen without leaving what
you're doing. Does nothing while Vesktop isn't running.

Vesktop must be started with the DevTools port open:
    flatpak run dev.vencord.Vesktop --remote-debugging-port=9222

Options:
    --follow-vesktop  quit when Vesktop exits (what the app-menu launcher uses)
    --version         print the version
    --help            print this

Panel keys:
    Up/Down          browse the list (Up from the top goes to the search box)
    Right            go in: a server opens its channels; a friend or channel opens its chat, ready to type
    Left             back out: reply box (cursor at start) -> list -> close the chat -> leave the server
    Up/Down (reply)  scroll the messages; the top loads older ones
    type a letter    search the current tab (Down goes back to the list)
    Ctrl+Tab         switch between Friends and Servers
    Tab              list <-> the open chat's reply box (keeps draft, highlight and tab)
    Enter (reply)    send the message
    Esc              close the picker / suggestions / reply / pasted image / search text; otherwise close the panel
    Ctrl+M / Ctrl+D  toggle mute / deafen
    Ctrl+Shift+D     leave the voice channel (also the Disconnect button, shown while in voice)
    Ctrl+Up / Down   panel opacity (5% steps, 30% minimum, remembered)
    Ctrl+Left/Right  previous / next chat you opened (last 25, wraps around)
    Ctrl+Shift+Left  remove the open chat from that history and close it
    Ctrl+Shift+Right show the open chat in the sidebar (Friends or its server), highlighted
    Ctrl+Shift+Down  clear that history (asks first); the history is remembered across restarts
    F1 / hover ?     list of all shortcuts
    Ctrl+Shift+`     toggle the panel (opens ready to type in the open chat)
    click an image   open it full size (or reveal a spoiler); clicking outside the panel closes it
    click a YouTube thumbnail  play it inline (Esc back to the panel; hiding the panel stops it)
    right-click      a chat in the list: Open in Vesktop, Mark as read;
                     a message: Reply, Add reaction, Edit / Delete (yours), Copy, Open in Vesktop
    click a reaction add yours, or remove it if it's already yours
    click a ↳ quote  go to the message it replies to
    your name        (bottom left) click it to pick Online / Idle / Do Not Disturb / Invisible
    Ctrl+E / Ctrl+G  (in the reply box, or the 😀 / GIF buttons) emoji / GIF picker
    ✎ in the list marks chats with an unsent draft.
"""

import sys

if __name__ == "__main__":
    if {"--version", "-V"} & set(sys.argv[1:]):
        from vesktop_discord_overlay import __version__
        print(f"vesktop-discord-overlay {__version__}")
    elif {"--help", "-h"} & set(sys.argv[1:]):
        print(__doc__)
    else:
        from vesktop_discord_overlay.preflight import check_or_exit
        check_or_exit()  # Wayland, missing packages: say so plainly instead of failing
        from vesktop_discord_overlay.overlay import main
        main()
