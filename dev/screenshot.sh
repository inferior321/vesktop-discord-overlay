#!/bin/bash
# Make the README screenshot (assets/screenshot.png) on a private display, with made-up chats (make_screenshot.py).
cd "$(dirname "$0")" || exit 1
DISPLAY_NO=${TEST_DISPLAY:-:98}
if command -v Xvfb >/dev/null; then
    Xvfb "$DISPLAY_NO" -screen 0 1600x1000x24 >/dev/null 2>&1 & SERVER=$!
else
    Xephyr "$DISPLAY_NO" -screen 1600x1000 -title "vdo screenshot" -no-host-grab >/dev/null 2>&1 & SERVER=$!
fi
trap 'kill $WM $SERVER 2>/dev/null' EXIT
sleep 2
command -v metacity >/dev/null && { DISPLAY=$DISPLAY_NO metacity --replace >/dev/null 2>&1 & WM=$!; sleep 1; }
DISPLAY=$DISPLAY_NO NO_AT_BRIDGE=1 timeout 60 python3 make_screenshot.py "$@" 2>&1 | grep -v -e DRI2 -e "overlay running"
