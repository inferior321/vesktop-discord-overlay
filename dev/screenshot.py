"""Save a picture of the test display: python3 dev/screenshot.py out.png [display, default :99]"""

import sys

from PIL import Image
from Xlib import X, display

screen = display.Display(sys.argv[2] if len(sys.argv) > 2 else ":99").screen().root
geometry = screen.get_geometry()
raw = screen.get_image(0, 0, geometry.width, geometry.height, X.ZPixmap, 0xffffffff).data
Image.frombytes("RGB", (geometry.width, geometry.height), raw, "raw", "BGRX").save(sys.argv[1])
