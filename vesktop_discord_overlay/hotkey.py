"""Global X11 hotkey listener."""

import threading

from Xlib import X, XK, display as xdisplay, error as xerror

AUTOREPEAT_GAP_MS = 5  # a key repeat's release and press arrive together; a real release-then-press can't
REPEAT_WITHIN_MS = 1000  # covers the delay before repeats start; a later press counts even after a missed release


class HotkeyListener(threading.Thread):
    """Grabs a global key combo on the X root window and calls on_press when it's hit."""

    def __init__(self, keysym, modifiers, on_press):
        super().__init__(daemon=True)
        self.keysym = keysym
        self.modifiers = modifiers
        self.on_press = on_press
        self.ready = threading.Event()
        self.failure = None

    def run(self):
        disp = xdisplay.Display()
        root = disp.screen().root
        keycode = disp.keysym_to_keycode(XK.string_to_keysym(self.keysym))
        catch = xerror.CatchError(xerror.BadAccess)
        # Grab with every combination of CapsLock / NumLock so the hotkey works regardless of them.
        for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
            root.grab_key(keycode, self.modifiers | extra, True, X.GrabModeAsync, X.GrabModeAsync, onerror=catch)
        disp.sync()
        if catch.get_error():
            self.failure = "That hotkey is already taken by another program."
            self.ready.set()
            return
        self.ready.set()
        # Holding the keys down makes X repeat them. A repeat is a press with no release since the last
        # press, or a release immediately followed by a press (same moment); only real presses count.
        held, pressed_at, released_at = False, None, None
        while True:
            event = disp.next_event()
            if event.type == X.KeyRelease:
                held, released_at = False, event.time
            elif event.type == X.KeyPress:
                repeat = ((held and event.time - pressed_at < REPEAT_WITHIN_MS)
                          or (released_at is not None and event.time - released_at <= AUTOREPEAT_GAP_MS))
                held, pressed_at = True, event.time
                if not repeat:
                    self.on_press()
