# Changelog

## 1.0.0

First release.

- Ctrl+Shift+` panel over any window: Friends and Servers tabs with avatars, online status, unread dots,
  ping counts and last-message previews; servers open into their channel lists.
- Chats with Discord's formatting, server emoji, images, GIFs and inline YouTube. Scrolling up loads older
  messages, and new messages, edits, deletions and reactions appear the moment they happen.
- Replying with emoji and GIF pickers (Ctrl+E / Ctrl+G), `:` emoji suggestions and pasted images; your
  friends see you typing, and you see them typing.
- Right-click a message to reply, react, edit or delete your own, copy it or its link, or open it in Vesktop.
  Click a reaction to add or remove yours, and click a reply's quote to jump to the original.
- Chat history: Ctrl+← / Ctrl+→ step through the last 25 chats you opened, remembered across restarts;
  Ctrl+Shift+← removes one, Ctrl+Shift+↓ clears it.
- Full-panel image / GIF viewer with Copy and Save.
- Mute, deafen and leave voice; set your status (Online, Idle, Do Not Disturb, Invisible).
- Marks chats read once you've seen their newest messages, like Discord.
- Adjustable opacity (Ctrl+↑ / Ctrl+↓); every other setting in `vesktop_discord_overlay/config.py`.
- App-menu launcher that starts Vesktop with the port the overlay needs, and quits the overlay with Vesktop.
- `install.sh` checks what's needed and, on Debian / Ubuntu / Mint, installs it after asking; it also offers
  to install Vesktop from Flathub.
- Plain-language messages (desktop notification and terminal) when it can't work: a Wayland session, missing
  packages, Vesktop not running or not the Flatpak, or the hotkey taken by another program.
