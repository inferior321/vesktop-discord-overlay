# vesktop-discord-overlay

A Discord overlay for Linux. Press **Ctrl+Shift+`** over any window, a game included, to see your friends and
servers, read and reply, react, send emoji and GIFs, and mute or deafen, without switching to Discord.

It works with [Vesktop](https://github.com/Vencord/Vesktop), the Discord client built on Vencord. The overlay
talks to the Vesktop you already have running, so it uses your normal Discord session and Discord's own
client code; it never sees or stores your login token.

## Features

- **Friends and Servers** with avatars, online status, unread dots, ping counts and last-message previews;
  servers open into their channel lists. Type to search.
- **Chats** with Discord's formatting (bold, links, mentions, spoilers, code, quotes, lists), server emoji,
  images, GIFs and inline YouTube. New messages, edits, deletions and reactions appear the moment they
  happen; scrolling up loads older messages.
- **Replying** with emoji and GIF pickers, `:` emoji suggestions and pasted images. Your friends see you
  typing, and you see them typing.
- **Right-click a message** to reply, react, edit or delete your own, copy it or its link, or open it in
  Vesktop. Click a reaction to add or remove yours; click a reply's quote to jump to the original.
- **Voice and status**: mute, deafen, leave the voice channel, and set Online / Idle / Do Not Disturb /
  Invisible from the bottom bar.
- **Keyboard-first**: arrow keys, Enter and Esc get you everywhere; Ctrl+← / Ctrl+→ step through the last
  25 chats you opened. Press F1 for the full list.
- **Marks chats as read** once you've seen their newest messages, like Discord, so they clear on your other
  devices too.
- Image viewer, adjustable opacity, unsent-draft markers, and every setting in one commented file.

## Before you use it

- **Discord's terms.** Vencord and Vesktop are client modifications, which Discord's Terms of Service don't
  allow, and this overlay works through them. People use Vencord widely without trouble, but there is no
  guarantee. Use it at your own risk.
- **The debug port.** The overlay reaches Vesktop through Chromium's remote-debugging port (9222). While
  Vesktop runs with that port open, any program running as you on this computer could control your Discord
  session. The port only listens on your own machine (127.0.0.1); other computers can't reach it.
- **Discord updates can break it.** The overlay uses Discord's own internal code (through Vencord), which
  Discord changes without notice. After a Discord or Vesktop update, parts of the overlay, or all of it, may
  stop working until it's updated to match. Version 1.0.0 was tested with Vesktop 1.6.7 (Flatpak) on Linux
  Mint 22.3 Cinnamon.
- **What it connects to.** Everything Discord-related goes through Vesktop. The overlay itself downloads only
  the images, GIFs and thumbnails it shows (from Discord's and YouTube's servers) and caches them in
  `~/.cache/vesktop-discord-overlay`.

## Requirements

- **Linux with an X11 session.** Wayland is not supported (global hotkeys and window handling need X11).
  It was built on Linux Mint Cinnamon.
- **Vesktop installed from Flathub** (`dev.vencord.Vesktop`). Other ways of installing Vesktop aren't
  supported yet.
- Python 3 with GTK 3, GStreamer and a few small packages. On Debian, Ubuntu and Mint the installer checks
  for these and offers to install whatever is missing. On other distributions, install your equivalents of
  the Debian packages below first:

  ```
  python3-gi python3-gi-cairo python3-xlib python3-websockets gir1.2-gtk-3.0 gir1.2-gstreamer-1.0
  gstreamer1.0-gtk3 gstreamer1.0-libav xdotool zenity libnotify-bin flatpak
  gir1.2-webkit2-4.1   (optional: plays YouTube videos inside the panel instead of in your browser)
  ```

## Install

```
cd ~
git clone https://github.com/inferior321/vesktop-discord-overlay.git
cd vesktop-discord-overlay
./install.sh
```

The program lives in **`~/vesktop-discord-overlay`**. (If you downloaded it somewhere else instead, run
`./install.sh` from there: it copies the program into `~/vesktop-discord-overlay`, after which you can delete
the download.)

The installer checks your session (X11), installs any missing packages after asking (with `sudo`), offers to
install Vesktop from Flathub if you don't have it, and adds **Vesktop Discord Overlay** to your app menu.
It's safe to run again; `./install.sh --yes` answers yes to every question.

To pin the menu entry to your panel: open the menu, search for it, right-click it and choose **Add to panel**.
From then on, use it instead of Vesktop's own launcher. Clicking it:

- starts Vesktop with the debug port open (or brings its window up if it's already running that way);
- offers to restart Vesktop if it was started without the port;
- starts the overlay, which quits by itself when Vesktop fully quits (closing Vesktop to the tray doesn't
  count).

Then press **Ctrl+Shift+`** anywhere.

### Update

```
cd ~/vesktop-discord-overlay
git pull
./install.sh
```

Or download the new version anywhere and run its `./install.sh`. If you had changed `config.py`, your old
settings are kept as `~/vesktop-discord-overlay/config.py.backup-<date>` so you can copy them back.

### Uninstall

```
~/vesktop-discord-overlay/install.sh --uninstall
rm -rf ~/.cache/vesktop-discord-overlay ~/.config/vesktop-discord-overlay
```

The first command removes the menu entry and, after asking, the program. Vesktop and the packages the
installer added stay installed (other programs may use them); remove them with `apt` / `flatpak uninstall`
if you want.

### Running from a terminal instead

1. Quit Vesktop from its tray icon (closing the window isn't enough), then start it with the port open:

   ```
   flatpak run dev.vencord.Vesktop --remote-debugging-port=9222
   ```

2. Start the overlay and leave it running (Ctrl+C quits it):

   ```
   python3 main.py
   ```

## Keys

| Key | What it does |
|---|---|
| Ctrl+Shift+` | Open / close the panel (clicking outside it also closes it) |
| Esc | Close whatever is open on top (picker, suggestions, reply, pasted image, search text); otherwise close the panel |
| Ctrl+Tab | Switch between the Friends and Servers tabs |
| Ctrl+← / Ctrl+→ | Step back / forward through the last 25 chats you opened (wraps around; the sidebar stays put) |
| Ctrl+Shift+→ | Show the open chat in the sidebar (Friends, or its server's channels), highlighted |
| Ctrl+Shift+← | Remove the open chat from that history and close it (it comes back if you open it again) |
| Ctrl+↑ / Ctrl+↓ | Panel opacity, in 5% steps (30% minimum); remembered between runs |
| ↑ / ↓ | Move through the list |
| → | Go in: server → its channels, friend/channel → open the chat, open chat → reply box |
| ← | Back out: reply box (cursor at the start) → list → close the chat → leave the server |
| Tab | Switch between the list and the open chat's reply box (keeps your draft, highlight and tab) |
| Enter | In the list: open the chat and jump to the reply box. In the reply box: send |
| Type a letter | Search the current tab |
| ↑ / ↓ (in the reply box) | Scroll the messages; reaching the top loads older ones |
| Ctrl+E / Ctrl+G (in the reply box), or the 😀 / **GIF** buttons | Emoji / GIF picker; the other one switches, the same one or Esc closes |
| `:` + two letters | Emoji suggestions. Tab or Enter inserts one |
| Right-click a message → Reply | Reply to it; Esc cancels |
| Right-click a message → Add reaction | Pick an emoji to react with |
| Click a reaction under a message | Add yours, or remove it if it's already yours |
| Right-click your own message → Edit message | Its text goes into the reply box: Enter saves, Esc cancels (your draft comes back) |
| Right-click your own message → Delete message | Asks first (Enter deletes, Esc cancels); hold Shift to skip the question |
| Click the **↳** quote above a reply | Go to the original message (loads older history if needed) |
| Ctrl+V with an image copied | Attach it; Enter sends it (with any text as a caption), Esc removes it |
| Right-click a message | Reply, Add reaction, Edit / Delete (yours), Copy text, Copy message link, Open in Vesktop (at that message); with part of its text highlighted, also Copy selection |
| Right-click a friend, server or channel in the list | Mark as read (a server: all its channels), Open in Vesktop |
| Ctrl+M / Ctrl+D | Mute / deafen |
| Ctrl+Shift+D, or **Disconnect** (shown while in voice) | Leave the voice channel |
| Your name and picture at the bottom left | Your status: click to pick Online, Idle, Do Not Disturb or Invisible |
| ✎ beside a chat in the list | You left an unsent draft there |
| F1, or hover the **?** in the bottom-right corner | List of all these shortcuts |
| Click an image or GIF | View it large inside the panel: ←/→ flip through the chat's media, **Copy** / **Save** (to Downloads), Esc or a click closes |
| Click a YouTube thumbnail | Play it right in the chat with YouTube's own player. Esc returns to the panel; hiding the panel stops it |

## Settings

Everything adjustable (the hotkey, text size, panel size, timings, media sizes, the debug port) is in
`vesktop_discord_overlay/config.py`, grouped and commented. Changes apply the next time the overlay starts.
The panel's opacity is remembered in `~/.config/vesktop-discord-overlay/state.json`.

## Troubleshooting

- **Messages about what's wrong.** If the overlay can't work (a Wayland session, a missing package, Vesktop
  not running or not the Flatpak, the hotkey taken), it says so in a desktop notification (and in the terminal, if you started
  it from one) with what to do. Its log is `~/.cache/vesktop-discord-overlay/overlay.log`.
- **"The hotkey is already taken by another program".** Something else already uses Ctrl+Shift+`. Pick
  another key in `config.py` (`HOTKEY_KEYSYM`, `HOTKEY_MODIFIERS`, `HOTKEY_LABEL`).
- **The panel says "Vesktop isn't reachable".** Vesktop is running without the debug port. Quit it from its
  tray icon and start it from the **Vesktop Discord Overlay** menu entry (or with the command above).
- **It doesn't work at all on my desktop.** Check that you're on X11: `echo $XDG_SESSION_TYPE` should print
  `x11`. On Wayland, log out and pick an X11 / Xorg session at the login screen, if your desktop offers one.
- **GIFs show as still pictures.** Install `gstreamer1.0-gtk3` and `gstreamer1.0-libav`.
- **YouTube links open in the browser.** Install `gir1.2-webkit2-4.1` to play them inside the panel.

## Development

### Layout

| File | What's in it |
|---|---|
| `main.py` | Entry point (`--follow-vesktop`: quit when Vesktop exits; `--version`; `--help`) |
| `launch.py` | What the menu/panel icon runs: starts Vesktop with the port, then the overlay |
| `install.sh` | Checks / installs what's needed (Debian / Ubuntu / Mint), offers Vesktop, puts the program in `~/vesktop-discord-overlay`, adds the app-menu entry and icon |
| `vesktop_discord_overlay/overlay.py` | The panel: window, layout, show / hide, keyboard, voice and status |
| `vesktop_discord_overlay/sidebar.py` | Friends / Servers tabs, search, the list and its keys |
| `vesktop_discord_overlay/messages.py` | The open chat: drawing messages (only what changed), scrolling, older history, media |
| `vesktop_discord_overlay/compose.py` | The reply box: replies, edits, deleting, pasted images, sending, reactions, pickers |
| `vesktop_discord_overlay/history.py` | Chat history (Ctrl+← / → and Ctrl+Shift+← / →) |
| `vesktop_discord_overlay/pickers.py` | Emoji / GIF pickers and `:` autocomplete |
| `vesktop_discord_overlay/media.py` | Image / GIF / video download cache and the widgets that draw them |
| `vesktop_discord_overlay/viewer.py` | The full-panel image / GIF viewer |
| `vesktop_discord_overlay/markdown.py` | Draws message text: Discord's formatting, links, spoilers, emoji, reactions |
| `vesktop_discord_overlay/shortcuts.py` | The shortcut list behind the **?** / F1 |
| `vesktop_discord_overlay/widgets.py` | Small GTK helpers, menus and the sidebar cards |
| `vesktop_discord_overlay/bridge.py` | DevTools connection to Vesktop |
| `vesktop_discord_overlay/bridge.js` | Runs inside Vesktop: reads Discord's stores, sends, edits and reacts, fetches emoji/GIFs, reports new messages and typing as they happen |
| `vesktop_discord_overlay/hotkey.py` | Global hotkey (X11 key grab) |
| `vesktop_discord_overlay/system.py` | Process / window helpers: Vesktop start/quit, debug port check, xdotool |
| `vesktop_discord_overlay/preflight.py` | Startup checks (Wayland, missing packages) with plain-language messages |
| `vesktop_discord_overlay/instance.py` | Single-overlay lock |
| `vesktop_discord_overlay/state.py` | Remembered preferences (`~/.config/vesktop-discord-overlay/state.json`) |
| `vesktop_discord_overlay/config.py` | **All settings**, grouped and commented |
| `vesktop_discord_overlay/theme.py` | Colors and the GTK stylesheet |
| `vesktop_discord_overlay/gtk.py` | GTK / GStreamer setup |
| `dev/` | Testing tools: a fake Vesktop with made-up chats, automatic checks, a private test display |

### Testing changes

Everything in `dev/` runs against a fake Vesktop with made-up friends, servers and messages, so no real
account is read or touched. It needs `Xephyr` (`sudo apt install xserver-xephyr`) for the private test
display.

- `dev/check.sh` runs the automatic checks (features, message redrawing, live updates, chat history) and says
  whether they passed.
- `dev/display.sh` opens a test display window with the overlay running on fake data, to try things by hand
  (press Ctrl+Shift+` inside it). `python3 dev/screenshot.py out.png` saves a picture of it.

## License

[MIT](LICENSE)
