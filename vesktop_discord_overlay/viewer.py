"""The full-panel image / GIF viewer: click media in a chat to see it large without leaving the overlay."""

import shutil
import urllib.parse
from pathlib import Path

from .gtk import HAVE_VIDEO, Gdk, Gtk
from .media import LoopingVideo, Picture, fit, sized_url
from .widgets import add_class, copy_to_clipboard, label

VIEWABLE = ("image", "anim", "video")  # stills, animated GIFs, GIF-videos (Klipy/Tenor)


def viewable(item):
    return item["kind"] in VIEWABLE and not item.get("youtube")


class Viewer(Gtk.EventBox):
    """Dark layer over the whole panel showing one item large; ←/→ flip through the chat's media."""

    TOP_BAR = 44
    PAD = 24

    def __init__(self, media, notify):
        super().__init__()
        self.media = media
        self.notify = notify  # notify(text) shows a short note in the panel's bottom bar
        self.items = []
        self.index = 0
        self.video = None
        self.still = None  # pixbuf of what's shown, for Copy
        add_class(self, "viewer")
        self.set_no_show_all(True)
        self.connect("button-press-event", self._background_click)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bar = Gtk.Box(spacing=6, margin_start=12, margin_end=8, margin_top=8)
        self.counter = label("", "viewer-counter")
        bar.pack_start(self.counter, False, False, 0)
        for text, action in (("✕", self.close), ("Save", self._save), ("Copy", self._copy)):
            btn = add_class(Gtk.Button(label=text), "viewer-button")
            btn.set_can_focus(False)
            btn.connect("clicked", lambda *_, action=action: action())
            bar.pack_end(btn, False, False, 0)
        column.pack_start(bar, False, False, 0)
        self.stage = Gtk.Box()  # holds the picture or video, centered
        self.stage.set_halign(Gtk.Align.CENTER)
        self.stage.set_valign(Gtk.Align.CENTER)
        column.pack_start(self.stage, True, True, 0)
        self.hint = label("←/→ previous / next · Esc closes", "viewer-hint", xalign=0.5)
        column.pack_start(self.hint, False, False, 8)
        self.add(column)
        column.show_all()

    # ----- opening / closing / moving -----

    def open(self, items, index):
        self.items, self.index = items, index
        self.show()
        self._show_current()

    def close(self):
        self._clear_stage()
        self.hide()

    def step(self, delta):
        if self.items:
            self.index = (self.index + delta) % len(self.items)
            self._show_current()

    def _background_click(self, _widget, event):
        if event.button == 1:
            self.close()
        return True

    # ----- showing an item -----

    def _clear_stage(self):
        if self.video:
            self.video.stop()
            self.video = None
        self.still = None
        for child in self.stage.get_children():
            child.destroy()

    def _show_current(self):
        self._clear_stage()
        item = self.items[self.index]
        self.counter.set_text(f"{self.index + 1} / {len(self.items)}" if len(self.items) > 1 else "")
        # Measure the panel itself: on the first opening this layer hasn't been sized yet.
        panel = self.get_parent().get_allocation()
        room_w = max(200, panel.width - 2 * self.PAD)
        room_h = max(150, panel.height - self.TOP_BAR - 2 * self.PAD - 20)
        w, h = fit(item["w"], item["h"], room_w, room_h)

        if item["kind"] == "video" and HAVE_VIDEO:
            path = self.media.file(item["src"], lambda p, i=self.index: self._video_ready(i, p, w, h))
            if path:
                self._video_ready(self.index, path, w, h)
            still = item.get("poster")
        else:
            still = item["src"]
        if still and self.video is None:
            picture = Picture(w, h)
            self.stage.pack_start(picture, False, False, 0)  # on stage first, so a cached image can fill it now
            picture.show()
            # Ask Discord's media proxy for a copy at the viewing size (animated GIFs stay original).
            url = sized_url(still, w, h) if item["kind"] == "image" and not item.get("sticker") else still
            anim = self.media.image(url, lambda a, p=picture, i=self.index: self._image_ready(i, p, a))
            if anim:
                self._image_ready(self.index, picture, anim)

    def _image_ready(self, index, picture, anim):
        if anim and index == self.index and picture.get_parent() is self.stage:
            picture.set_animation(anim)
            self.still = anim.get_static_image()

    def _video_ready(self, index, path, w, h):
        if not path or index != self.index or not self.get_visible() or self.video:
            return
        video = LoopingVideo(path, w, h)
        if video.widget is None:
            return
        for child in self.stage.get_children():
            child.destroy()
        self.video = video
        self.stage.pack_start(video.widget, False, False, 0)
        video.widget.show()
        # Play only once it's on screen inside the panel (see MediaView._sync_playback).
        if video.widget.get_mapped():
            video.play()
        else:
            video.widget.connect("map", lambda *_: self.video is video and video.play())

    # ----- Copy / Save -----

    def _copy(self):
        if self.still is not None:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_image(self.still)
            self.notify("Image copied")
        else:  # a GIF-video has no still to copy; its link is the useful thing
            copy_to_clipboard(self.items[self.index]["full"])
            self.notify("Link copied")

    def _save(self):
        item = self.items[self.index]
        source = item["full"] if item["kind"] != "video" else item["src"]
        self.notify("Saving…")
        path = self.media.file(source, lambda path, item=item: self._saved(item, path))
        if path:  # already downloaded
            self._saved(item, path)

    def _saved(self, item, path):
        if not path:
            self.notify("Couldn't download it")
            return
        name = Path(urllib.parse.urlparse(item["full"]).path).name or "image"
        if "." not in name:
            name += ".mp4" if item["kind"] == "video" else ".png"
        downloads = Path.home() / "Downloads"
        downloads.mkdir(exist_ok=True)
        target, n = downloads / name, 1
        while target.exists():
            target = downloads / f"{Path(name).stem} ({n}){Path(name).suffix}"
            n += 1
        shutil.copyfile(path, target)
        self.notify(f"Saved to Downloads/{target.name}")
