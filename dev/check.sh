#!/bin/bash
# Run every dev/check_*.py against the fake Vesktop on a private test display: an invisible one (Xvfb) if it's
# installed, as on GitHub's servers, otherwise a window (Xephyr). metacity is optional. Your real desktop,
# Vesktop and Discord account are never touched.
cd "$(dirname "$0")" || exit 1
TEST_DISPLAY=${TEST_DISPLAY:-:99}
export NO_AT_BRIDGE=1  # no accessibility service on the test display; don't warn about it
if command -v Xvfb >/dev/null; then
    Xvfb "$TEST_DISPLAY" -screen 0 1360x768x24 >/dev/null 2>&1 & SERVER=$!
elif command -v Xephyr >/dev/null; then
    Xephyr "$TEST_DISPLAY" -screen 1360x768 -title "vdo checks" -no-host-grab >/dev/null 2>&1 & SERVER=$!
else
    echo "Needs Xvfb (sudo apt install xvfb) or Xephyr (sudo apt install xserver-xephyr)."
    exit 1
fi
trap 'kill $WM $SERVER 2>/dev/null' EXIT
sleep 2
command -v metacity >/dev/null && { DISPLAY=$TEST_DISPLAY metacity --replace >/dev/null 2>&1 & WM=$!; sleep 1; }
failed=0
for check in check_*.py; do
    echo "== $check"
    DISPLAY=$TEST_DISPLAY timeout 120 python3 "$check" 2>&1 | grep -v -e "DRI2" -e "overlay running"
    status=${PIPESTATUS[0]}
    [ "$status" -eq 0 ] || failed=1
done
[ $failed -eq 0 ] && echo "All checks passed." || echo "Some checks FAILED."
exit $failed
