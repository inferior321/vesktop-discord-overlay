# Changelog

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
- Adjustable opacity (Ctrl+↑ / Ctrl+↓); every other setting in `vesktop_discord_overlay/config.py`.
- App-menu launcher that starts Vesktop with the port the overlay needs, and quits the overlay with Vesktop.
- `install.sh` checks what's needed and, on Debian / Ubuntu / Mint, installs it after asking; it also offers
  to install Vesktop from Flathub.
- After a Discord update renames something it relies on, the overlay says which features are affected
  (the rest keep working) instead of showing cryptic errors.
- Plain-language messages (desktop notification and terminal) when it can't work: a Wayland session, missing
  packages, Vesktop not running or not the Flatpak, the hotkey taken by another program, or a keyboard layout
  without a ` key (on layouts where ` is an accent key, that key works).
