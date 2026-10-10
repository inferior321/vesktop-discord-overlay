"""GTK / GStreamer setup. Import gi things from here so the versions are pinned before first use."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GdkX11", "3.0")  # gives Gdk windows get_xid(), used to activate the panel
gi.require_version("PangoCairo", "1.0")
gi.require_foreign("cairo")
from gi.repository import Gdk, GdkPixbuf, GdkX11, GLib, Gtk, Pango, PangoCairo  # noqa: E402,F401

try:
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    Gst.init(None)
    HAVE_VIDEO = Gst.ElementFactory.find("gtksink") is not None
    # Decode GIF videos in software, in this process only. They're tiny, so the graphics card gains nothing,
    # and GPU decoders (NVIDIA's especially) make each player take ~100 ms of the panel's time to start and
    # stop: closing a chat with a dozen GIFs froze it for a second. Software decoding takes a few ms.
    for factory in Gst.Registry.get().get_feature_list(Gst.ElementFactory):
        kind = factory.get_metadata(Gst.ELEMENT_METADATA_KLASS) or ""  # e.g. "Codec/Decoder/Video/Hardware"
        if "Decoder" in kind and "Hardware" in kind:
            factory.set_rank(Gst.Rank.NONE)
except (ValueError, ImportError):
    Gst = None
    HAVE_VIDEO = False  # GIF videos fall back to their still thumbnail

try:
    gi.require_version("WebKit2", "4.1")
    from gi.repository import WebKit2

    HAVE_WEBKIT = True
except (ValueError, ImportError):
    WebKit2 = None
    HAVE_WEBKIT = False  # YouTube thumbnails then just open in the browser
