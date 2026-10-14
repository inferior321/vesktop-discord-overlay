# Changelog

## 1.7.0

- Mute from the list: right-click a server, channel or DM → Mute ▸ for 15 minutes, 1 / 3 / 8 / 24 hours or until
  you turn it back on, like Discord's menu (synced with Discord). Muted ones are dimmed, now including DMs; the
  menu then offers Unmute, with when the mute ends. When a timed mute ends, the row un-dims right then.
- Muted DMs no longer count towards the Friends tab's ping count and unread dot (like muted servers on the
  Servers tab).
- The server member list updates smoothly while open: only the people who changed are redrawn (in a big server
  it changes about once a second, and redrawing hundreds of rows each time stuttered).
- "… is typing" now shows like Discord's: with pulsing dots just above the reply box (in space kept free below
  the last message, so it never covers one). The line under a friend's name at the top keeps their status.

## 1.6.0

- Server member lists: in a server chat, click the server's name (▾) in the header for the
  channel's member list, like Discord's: role groups, then online (and offline in small servers), each person
  with their status, role colour and what they're up to; more load as you scroll. Click someone to message them
  (your DM opens in the overlay) or mention them (@them goes into the reply box).

## 1.5.1

- The F1 shortcut list now closes when you click, anywhere (before, only Esc, F1 or hovering the ? did).

## 1.5.0

- Resize the panel: drag the ◢ in its bottom-right corner. It grows on both sides around where it is, from its
  default size up to 95% of the screen, and the size is remembered. Double-click the ◢ to go back to the
  default. (PANEL_GROW_MAX in the settings sets the largest share of the screen.)
- Move the panel: drag the ✥ in its top-right corner; the place is remembered (relative to the screen's centre,
  so it works on any monitor). Double-click the ✥ to centre it again. Moving and resizing keep the panel whole
  on its screen and clear of the taskbar and other panels.

## 1.4.1

- ← no longer closes the open chat: it only goes back out (reply box → list → out of a forum → out of a
  server), so you can browse while your conversation stays open.
- Fixed the panel growing wider (and staying wide): a message with many reactions (they now wrap onto more
  lines, like Discord's), an emoji-only message with many emoji (also wrap), a long channel / post / server name
  in the chat header, a long typing / status line, or a long author name (cut short with "…"). A new check
  keeps it so.
- Fixed forums looking empty (and showing no "N new") until you'd opened that server in Vesktop's own window:
  Discord loads a server's active posts only when you look at it, and now opening the server or forum in the
  overlay asks for them the same way.

## 1.4.0

- A server's channels now match Discord's sidebar: only the channels you picked in Browse Channels, in
  Discord's order, under their categories (click a heading to collapse or expand it, in Discord too), with
  joined threads under their channel.
- Forums: listed with Discord's "N new", and → opens a forum's posts (title, who started it, replies, new
  replies; most recent activity first). Scrolling to the end loads older posts; → on a post opens it as a chat.
- Mark as read on a server (or a forum) now also clears forums' new posts and joined threads, like Discord's.
  Before, a server whose only unread things were forum posts stayed unread.
- `@` and `#` suggestions in the reply box, like the `:` emoji ones: people in the chat and the server's
  channels; picking one makes a real mention / channel link.
- A list that fills in after it's shown (a forum's posts, found with Ctrl+Shift+→) highlights the open chat.

## 1.3.0

- Custom status: click your name → **Set custom status…** for a small pop-up with your text, an emoji (😀 or
  Ctrl+E: the same emoji picker, with server emoji if Discord lets you use them in a status), and "Clear after"
  (Today, 4 hours, 1 hour, 30 minutes, Don't clear). It shows under your name instead of "Online", like Discord,
  and stays in sync with Discord itself.
- Hiding the panel now also closes the Voice connected pop-up.
- Picking an emoji in the reaction picker over a GIF no longer also opens the GIF. Emoji now pick when you let go
  of the button, like normal buttons, and images / GIFs open only on a whole click on them; sliding off before
  letting go cancels.

## 1.2.1

- The Join button follows where you are: the highlighted voice channel while you're in the list, the open chat
  while you're typing. Before, after Ctrl+← / Ctrl+→ to a DM it still offered to join the voice channel left
  highlighted in the list. And a voice channel's chat reached from another server (Ctrl+← / Ctrl+→) offers
  Join too.
- Right-click a server → Mark as read also clears its voice channels' chats.
- Right-click a voice channel → Open in Vesktop shows it with its text chat open (without joining).
- Voice channels with a user limit show "2/5"; when one is full, the button greys out as "<channel> is full".
- Voice channels have a grey speaker icon like Discord's, instead of the colour 🔊 emoji.
- A second README picture shows a server's voice channels and the Voice connected pop-up.

## 1.2.0

- Voice channels in each server's channel list: after the text channels, under a VOICE heading, in the
  server's own order, with who's in them (picture, a green ring while speaking, muted / deafened), live.
  → or a click opens a voice channel's text chat.
- Joining voice: with a voice channel highlighted (or its chat open), the bottom-right button becomes a green
  **Join <channel>**; it or Ctrl+Shift+D joins. In a call it's **Disconnect**, as before.
- Click **Voice connected ▾** to see who's in your call and who's speaking, live.
- Your friends' status: their online dot on their picture in the chat header, and their custom status or
  activity ("Playing Valorant") under their name there, and in the list for chats with no message loaded.

## 1.1.0

- Ctrl+Shift+← (remove the open chat from the Ctrl+← / Ctrl+→ history) now moves on to the next chat, like
  closing a browser tab: the more recent one, or the one before if it was the most recent; the empty screen
  only when it was the last one. A note says which chat you're in now.
- Ctrl+Shift+↓ (clear the whole history) now also closes the open chat, leaving the empty screen with the
  cursor in the list.

## 1.0.0

First release.

- Ctrl+Shift+` panel over any window: Friends and Servers tabs with avatars, online status, unread dots,
  ping counts and last-message previews; servers open into their channel lists.
- Chats with Discord's formatting, server emoji, images, GIFs and inline YouTube, plus Discord's own lines for
  calls ("started a call that lasted 4 minutes", missed calls), pins, people joining, boosts, stages, AutoMod
  and poll results; forwarded messages, polls (view only), voice messages and "used /command" for bot replies. Scrolling up loads older
  messages, and new messages, edits, deletions and reactions appear the moment they happen; so do unread
  marks, online status, new DMs and servers in the lists.
- Replying with emoji and GIF pickers (Ctrl+E / Ctrl+G), `:` emoji suggestions and pasted images; your
  friends see you typing, and you see them typing.
- Right-click a message to reply, react, edit or delete your own, copy it or its link, or open it in Vesktop.
  Click a reaction to add or remove yours, and click a reply's quote to jump to the original.
- Keyboard-first: the panel opens ready to type in the open chat; → opens a chat and puts you in its reply
  box; Tab and ← (at the start of the text) go back to the list.
- Chat history: Ctrl+← / Ctrl+→ step through the last 25 chats you opened, remembered across restarts;
  Ctrl+Shift+← removes one, Ctrl+Shift+↓ clears it.
- Full-panel image / GIF viewer with Copy and Save.
- Mute, deafen and leave voice; set your status (Online, Idle, Do Not Disturb, Invisible) from your name at
  the bottom left. Changes made in Discord itself show instantly.
- Marks chats read once you've seen their newest messages, like Discord.
- Makes no Discord requests on its own: list previews come only from messages Vesktop already has.
- Adjustable opacity (Ctrl+↑ / Ctrl+↓); every other setting can be changed in
  `~/.config/vesktop-discord-overlay/settings.py`, which updates never touch.
- App-menu launcher that starts Vesktop with the port the overlay needs, and quits the overlay with Vesktop.
- `install.sh` checks what's needed and, on Debian / Ubuntu / Mint, installs it after asking; it also offers
  to install Vesktop from Flathub.
- After a Discord update renames something it relies on, the overlay says which features are affected
  (the rest keep working) instead of showing cryptic errors.
- Plain-language messages (desktop notification and terminal) when it can't work: a Wayland session, missing
  packages, Vesktop not running or not the Flatpak, the hotkey taken by another program, or a keyboard layout
  without a ` key (on layouts where ` is an accent key, that key works).
