#!/bin/bash
# Open a private test display (a window on your desktop) with the overlay running on fake data.
# Press Ctrl+Shift+` inside it to open the panel; dev/screenshot.py saves a picture of it. Close it with Ctrl+C.
cd "$(dirname "$0")" || exit 1
TEST_DISPLAY=${TEST_DISPLAY:-:99}
Xephyr "$TEST_DISPLAY" -screen 1360x768 -title "vdo test display" -no-host-grab >/dev/null 2>&1 & XEPHYR=$!
trap 'kill $WM $XEPHYR 2>/dev/null' EXIT
sleep 2
command -v metacity >/dev/null && { DISPLAY=$TEST_DISPLAY metacity --replace >/dev/null 2>&1 & WM=$!; sleep 1; }
echo "Test display $TEST_DISPLAY is up. e.g.: DISPLAY=$TEST_DISPLAY xdotool key ctrl+shift+grave"
DISPLAY=$TEST_DISPLAY python3 run_fake.py
