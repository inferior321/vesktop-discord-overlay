"""Run the overlay against the fake Vesktop, to try changes by hand without your real account.

    dev/display.sh              # a private test display with the overlay on it (recommended), or:
    python3 dev/run_fake.py     # on your own desktop (press Ctrl+Shift+` as usual)
"""

import fakebridge as fb
import vesktop_discord_overlay.overlay as main

fb.install(main)
main.main()
