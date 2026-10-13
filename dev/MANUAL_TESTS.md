# Manual tests

`dev/check.sh` covers the overlay's own behaviour with a fake Vesktop. These are the things it can't cover,
because they need a real Discord account, a real desktop or a fresh system. Run through them before a release,
especially after Discord or Vesktop updates.

First run `python3 dev/smoke_real.py` (read-only: checks every list, server and forum against your account).

Use a chat with a friend who knows you're testing, or a server channel you own.

## On a real account

- [ ] **Live messages:** with a chat open in the panel, have someone message you. It appears within a second.
- [ ] **Reactions:** right-click a message → Add reaction, pick one; click the reaction again to remove it.
- [ ] **Edit:** right-click one of your messages → Edit message, change it, press Enter. It shows "(edited)".
- [ ] **Delete:** right-click one of your messages → Delete message. It asks first; Enter deletes. Try again
      holding Shift while clicking Delete: no question.
- [ ] **Status:** click your name at the bottom left, pick Idle, then Online again. Vesktop shows the same.
- [ ] **Custom status:** click your name → Set custom status…, type something, pick an emoji, Clear after 30
      minutes, Save. Vesktop (and a friend) show it; it shows under your name. Change it in Vesktop: the panel
      follows. Clear it from the panel: gone in Vesktop too.
- [ ] **Voice:** join a voice channel. Ctrl+M / Ctrl+D mute and deafen; muting with Discord's own button
      changes the panel's button at the same moment; Disconnect (or Ctrl+Shift+D) leaves the channel.
- [ ] **Voice channels:** open a server with voice channels. They're listed last under VOICE, with who's in
      them. → opens one's text chat; the bottom-right button then says Join <channel>, and it (or
      Ctrl+Shift+D) joins: you appear under the channel and the button becomes Disconnect. Right-click a voice
      channel → Open in Vesktop: Vesktop shows it with its chat open, and doesn't join. A full channel with a
      user limit (if you find one) shows e.g. 5/5 and a grey "… is full" button.
- [ ] **Open in Vesktop:** right-click a friend, a channel and a server in the list → Open in Vesktop. Vesktop
      comes up on it with its message box focused.
- [ ] **Server channels:** open a server that uses Browse Channels: the overlay lists the same channels and
      categories as Discord's sidebar. Click a category heading: it collapses in Discord too. Right-click the
      server → Mark as read: its unread dot (and forums' "new") clears.
- [ ] **Forums:** → on a forum lists its posts; scroll to the end: older posts load. → on a post opens it;
      reply there. ← goes back to the posts, then the channels.
- [ ] **Mentions:** type `@` and part of a friend's name, pick them, send: it's a real mention (they're
      pinged). In a server, `#` and part of a channel name: a clickable channel link.
- [ ] **Panel size:** open a busy server's announcement with lots of reactions, and a forum post or channel
      with a long name: the panel keeps its width (reactions wrap; long names end in "…").
- [ ] **Resize:** drag the ◢ in the panel's bottom-right corner: it grows on both sides, staying centred,
      no smaller than the default and no larger than nearly the whole screen. Close and reopen it: same size.
      Double-click the ◢: back to the default. Drag the ✥ (top right): the panel moves, but never off the screen
      or under the taskbar (try dragging it down past the taskbar, and onto another monitor if you have one).
      Close and reopen it: same place. Double-click the ✥: back to the centre.
- [ ] **Read elsewhere:** read a chat on your phone or in Vesktop's window. Its unread dot in the panel clears
      within a second.
- [ ] **Health:** after starting from the app menu, no "Discord changed something" notification appears.

## On a fresh system

- [ ] **Install:** on a clean Linux Mint / Ubuntu (a virtual machine, or a new user account), clone the repo
      and run `./install.sh`. It offers to install the missing packages and Vesktop, and adds the menu entry.
- [ ] **First run:** start "Vesktop Discord Overlay" from the menu, log in to Vesktop, press Ctrl+Shift+`.
- [ ] **Other desktops** (if you can): GNOME or KDE on X11, a second monitor, display scaling above 100%.

## Message kinds

These are rare in test chats, so check them when they turn up: a forwarded message, a poll (and its votes
changing live), a voice message, a bot's reply to a slash command, and a call line ("started a call that
lasted …").
