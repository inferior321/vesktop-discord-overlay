#!/usr/bin/env bash
# Sets up vesktop-discord-overlay: checks (and on Debian / Ubuntu / Mint, offers to install) what it needs,
# offers to install Vesktop from Flathub if it's missing, puts the program in ~/vesktop-discord-overlay and
# adds "Vesktop Discord Overlay" to the app menu.
#
#   ./install.sh               install, or update from a newer download (safe to run again)
#   ./install.sh --yes         same, answering yes to every question
#   ./install.sh --uninstall   remove the menu entry and icon (and, after asking, the program)
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
target="$HOME/vesktop-discord-overlay"  # where the program lives, for everyone
program_files=(launch.py main.py install.sh vesktop_discord_overlay assets README.md LICENSE CHANGELOG.md)
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
desktop="$apps/vesktop-discord-overlay.desktop"
icon="$icons/vesktop-discord-overlay.svg"
vesktop_app="dev.vencord.Vesktop"
assume_yes=false

# What the overlay needs, as Debian / Ubuntu / Mint packages.
required=(
    python3 python3-gi python3-gi-cairo python3-xlib python3-websockets  # Python and its add-ons
    gir1.2-gtk-3.0 gir1.2-gstreamer-1.0                                  # the window; GIF videos
    gstreamer1.0-gtk3 gstreamer1.0-libav                                 # GIF videos drawn in the panel
    xdotool zenity libnotify-bin flatpak                                 # windows, questions, notices, Vesktop
)
optional=(gir1.2-webkit2-4.1)  # YouTube videos playing inside the panel (otherwise they open in the browser)

bold=$'\e[1m' red=$'\e[31m' yellow=$'\e[33m' green=$'\e[32m' plain=$'\e[0m'
[[ -t 1 ]] || bold="" red="" yellow="" green="" plain=""
say()  { echo "${bold}==>${plain} $*"; }
ok()   { echo "    ${green}✓${plain} $*"; }
warn() { echo "    ${yellow}!${plain} $*"; }
fail() { echo "${red}${bold}Error:${plain} $*" >&2; exit 1; }

ask() {  # ask "Question?" -> true for yes (Enter means yes)
    if $assume_yes; then echo "$1 [Y/n] yes"; return 0; fi
    local answer
    read -r -p "$1 [Y/n] " answer || answer=n
    [[ -z "$answer" || "$answer" =~ ^[Yy] ]]
}

uninstall=false
for arg in "$@"; do
    case "$arg" in
        --yes|-y) assume_yes=true ;;
        --uninstall) uninstall=true ;;
        *) fail "unknown option: $arg (use --yes or --uninstall)" ;;
    esac
done

if $uninstall; then
    rm -f "$desktop" "$icon"
    update-desktop-database "$apps" 2>/dev/null || true
    echo "Removed the menu entry and icon."
    if [[ -d "$target/.git" ]]; then
        echo "Left $target in place: it's a git working copy."
    elif [[ -f "$target/vesktop_discord_overlay/__init__.py" ]] && ask "Delete the program too ($target)?"; then
        rm -rf "$target"
        echo "Deleted $target"
    fi
    echo "Settings and cache (delete them too if you like): ~/.config/vesktop-discord-overlay" \
         "~/.cache/vesktop-discord-overlay"
    exit 0
fi

# ---- 1. The desktop session ----------------------------------------------------------------------------
say "Checking your desktop session"
case "${XDG_SESSION_TYPE:-}" in
    x11) ok "X11 session" ;;
    wayland) warn "You're in a Wayland session. The overlay needs X11: it installs fine, but it will only"
             warn "work after you log in to an X11 / Xorg session (pick one on the login screen)." ;;
    *) warn "Couldn't tell whether this is an X11 session (the overlay needs X11, not Wayland)." ;;
esac

# ---- 2. Packages ------------------------------------------------------------------------------------------
say "Checking the packages the overlay needs"
is_installed() { [[ "$(dpkg-query -W -f='${Status}' "$1" 2>/dev/null)" == "install ok installed" ]]; }

if command -v apt-get >/dev/null && command -v dpkg-query >/dev/null; then
    missing=()
    for pkg in "${required[@]}"; do is_installed "$pkg" || missing+=("$pkg"); done
    missing_optional=()
    for pkg in "${optional[@]}"; do
        # Only offer it if this system's repositories have it.
        is_installed "$pkg" || { apt-cache show "$pkg" >/dev/null 2>&1 && missing_optional+=("$pkg"); }
    done
    if ((${#missing[@]} == 0)); then
        ok "Everything needed is installed"
    else
        echo "    Missing: ${missing[*]}"
        if ask "Install them now? (runs: sudo apt-get install ...)"; then
            sudo apt-get install -y "${missing[@]}" || {
                echo "    That failed; refreshing the package lists and trying once more..."
                sudo apt-get update && sudo apt-get install -y "${missing[@]}"
            } || fail "couldn't install: ${missing[*]}"
        else
            fail "these are required. Install them with:  sudo apt install ${missing[*]}"
        fi
    fi
    if ((${#missing_optional[@]} > 0)); then
        echo "    Optional: ${missing_optional[*]} plays YouTube videos inside the panel (without it they open in"
        echo "    your browser)."
        if ask "Install it too?"; then
            sudo apt-get install -y "${missing_optional[@]}" || warn "Couldn't install it; YouTube will open in the browser."
        fi
    fi
else
    warn "This isn't a Debian / Ubuntu / Mint system, so the installer can't install packages for you."
    warn "Install your distribution's packages for: Python 3, PyGObject (GTK 3 and GStreamer bindings),"
    warn "python-xlib, websockets, the GStreamer GTK sink and libav plugins, xdotool, zenity, notify-send,"
    warn "Flatpak, and optionally WebKitGTK 4.1. Then run this again; the next step checks what Python can load."
fi

# Whatever the system: can Python actually load everything?
problems="$(python3 - <<'EOF' 2>&1 || true
import importlib
checks = [("PyGObject", "gi"), ("python-xlib", "Xlib"), ("websockets", "websockets")]
for name, module in checks:
    try:
        importlib.import_module(module)
    except ImportError:
        print(f"Python can't load {name}")
try:
    import gi
    for lib, version in (("Gtk", "3.0"), ("Gdk", "3.0"), ("GdkX11", "3.0"), ("PangoCairo", "1.0"), ("Gst", "1.0")):
        try:
            gi.require_version(lib, version)
            importlib.import_module(f"gi.repository.{lib}")
        except (ValueError, ImportError):
            print(f"Python can't load {lib} {version}")
    gi.require_foreign("cairo")
except ImportError:
    pass
EOF
)"
[[ -z "$problems" ]] || fail "$problems"
ok "Python can load GTK, GStreamer, python-xlib and websockets"

# ---- 3. Vesktop ------------------------------------------------------------------------------------------
say "Checking for Vesktop"
command -v flatpak >/dev/null || fail "Flatpak isn't installed (the overlay works with Vesktop's Flatpak)."
if flatpak info "$vesktop_app" >/dev/null 2>&1; then
    ok "Vesktop (Flatpak) is installed"
else
    if command -v vesktop >/dev/null || compgen -G "$HOME/Applications/*esktop*.AppImage" >/dev/null; then
        warn "Vesktop seems to be installed some other way (not the Flatpak). The overlay only works with the"
        warn "Flatpak for now; you can have both installed."
    fi
    if ask "Vesktop's Flatpak isn't installed. Install it from Flathub now?"; then
        if flatpak remotes --columns=name | grep -qx flathub; then
            flatpak install -y flathub "$vesktop_app"
        else
            echo "    Adding Flathub (just for your user)..."
            flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
            flatpak install -y --user flathub "$vesktop_app"
        fi
        ok "Vesktop installed"
    else
        warn "Skipped. Install it later with:  flatpak install flathub $vesktop_app"
    fi
fi

# ---- 4. The program ---------------------------------------------------------------------------------------
if [[ "$here" == "$target" ]]; then
    say "The program is already in $target"
else
    say "Copying the program to $target"
    if [[ -e "$target" && ! -f "$target/vesktop_discord_overlay/__init__.py" ]]; then
        fail "$target already exists and isn't this program. Move or rename it, then run this again."
    fi
    if [[ -d "$target/.git" ]] && ! ask "$target is a git working copy; overwrite its files with this version?"; then
        fail "stopped; nothing was copied."
    fi
    # Your settings: if config.py was changed there, keep a copy before the new version replaces it.
    old_config="$target/vesktop_discord_overlay/config.py"
    if [[ -f "$old_config" ]] && ! cmp -s "$old_config" "$here/vesktop_discord_overlay/config.py"; then
        backup="$target/config.py.backup-$(date +%Y%m%d-%H%M%S)"  # outside the folder that gets replaced
        cp "$old_config" "$backup"
        warn "The old config.py was saved as $backup. If you had changed settings in it, put those lines in"
        warn "~/.config/vesktop-discord-overlay/settings.py instead (updates never touch that file)."
    fi
    mkdir -p "$target"
    rm -rf "$target/vesktop_discord_overlay"  # so files removed in the new version don't linger
    for item in "${program_files[@]}"; do
        if [[ -e "$here/$item" ]]; then cp -r "$here/$item" "$target/"; fi
    done
    find "$target" -name __pycache__ -type d -prune -exec rm -rf {} +
    ok "Copied (you can delete $here now if you like)"
fi

# ---- 5. Your settings file ----------------------------------------------------------------------------------
settings="${XDG_CONFIG_HOME:-$HOME/.config}/vesktop-discord-overlay/settings.py"
if [[ ! -e "$settings" ]]; then
    mkdir -p "$(dirname "$settings")"
    cat > "$settings" <<'SETTINGS'
# Your settings for vesktop-discord-overlay. Anything here overrides the default in
# ~/vesktop-discord-overlay/vesktop_discord_overlay/config.py, which lists every setting and what it does.
# Updates never touch this file. Remove the # at the start of a line to use it; changes apply the next time
# the overlay starts.

# TEXT_SCALE = 1.3                          # bigger text everywhere (1 = your desktop's size)
# HOTKEY_KEYSYM = "grave"                   # the hotkey's key ("grave" is `), e.g. "F12" or "o"
# HOTKEY_MODIFIERS = X.ControlMask | X.ShiftMask
# HOTKEY_LABEL = "Ctrl+Shift+`"             # how the hotkey is written in messages
# PANEL_MAX_W, PANEL_MAX_H = 1080, 720      # the panel's size on large screens
# HISTORY_LENGTH = 25                       # chats remembered for Ctrl+Left / Ctrl+Right
SETTINGS
    ok "Created $settings for your own settings"
fi

# ---- 6. The menu entry ----------------------------------------------------------------------------------
say "Adding Vesktop Discord Overlay to the app menu"
mkdir -p "$apps" "$icons"
cp "$target/assets/vesktop-discord-overlay.svg" "$icon"
cat > "$desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Vesktop Discord Overlay
GenericName=Discord overlay
Comment=Vesktop with the Ctrl+Shift+\` overlay
Exec=python3 "$target/launch.py"
Icon=vesktop-discord-overlay
Terminal=false
Categories=Network;Chat;InstantMessaging;
Keywords=discord;vesktop;overlay;chat;
StartupNotify=false
EOF
chmod +x "$target/launch.py"
update-desktop-database "$apps" 2>/dev/null || true
gtk-update-icon-cache -q -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true
ok "Added"

echo
echo "${bold}Done.${plain} Open your app menu and start ${bold}Vesktop Discord Overlay${plain} (use it instead of Vesktop's"
echo "own launcher; to pin it, right-click it and choose \"Add to panel\"). Then press Ctrl+Shift+\` anywhere."
