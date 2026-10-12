"""Downloading/caching images and GIF videos, and the widgets that draw them."""

import hashlib
import math
import threading
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from .gtk import GLib, Gdk, GdkPixbuf, Gst, Gtk, HAVE_VIDEO, HAVE_WEBKIT, Pango, PangoCairo, WebKit2
from .config import (CACHE_DIR, CACHE_MAX_AGE_DAYS, MAX_DOWNLOAD, MEDIA_MAX_H, MEDIA_MAX_W, MEDIA_MEMORY_LARGE,
                     MEDIA_SMALL_PX, STICKER_SIZE, YOUTUBE_MAX_H, YOUTUBE_MAX_W)
from .theme import ACCENT, SIDEBAR, STATUS_COLORS, font

class MediaCache:
    """Downloads avatars, images and GIF videos once (memory + disk cache); results arrive on the GTK thread.

    Small images (avatars, icons, emoji) stay in memory; of the large ones only the MEDIA_MEMORY_LARGE most
    recently used do, and older ones are re-read from the disk cache when needed again.
    """

    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._prune()
        self.pool = ThreadPoolExecutor(4)
        self.done = {}  # (kind, url) -> GdkPixbufAnimation / file path, or None if it failed
        self.large = OrderedDict()  # keys of large images in self.done, least recently used first
        self.waiting = {}  # (kind, url) -> callbacks

    @staticmethod
    def _prune():
        cutoff = time.time() - CACHE_MAX_AGE_DAYS * 86400
        for path in CACHE_DIR.iterdir():
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass

    def image(self, url, callback):
        """GdkPixbufAnimation for url if already loaded; otherwise None, and callback(animation or None) later."""
        return self._get("image", url, callback)

    def still(self, url, callback):
        """First frame of an image (even an animated one) as a GdkPixbuf; same contract as image()."""
        return self._get("still", url, callback)

    def file(self, url, callback):
        """Local path of url if already downloaded; otherwise None, and callback(path or None) later."""
        return self._get("file", url, callback)

    def _get(self, kind, url, callback):
        key = (kind, url)
        if key in self.done:
            if key in self.large:
                self.large.move_to_end(key)  # recently used
            return self.done[key]
        if key in self.waiting:
            self.waiting[key].append(callback)
        else:
            self.waiting[key] = [callback]
            self.pool.submit(self._work, kind, url)
        return None

    def _work(self, kind, url):
        path = self._download(url)
        result = path
        if kind == "image" and path:
            try:
                result = GdkPixbuf.PixbufAnimation.new_from_file(str(path))
            except GLib.Error:
                result = None
        elif kind == "still" and path:
            try:
                result = GdkPixbuf.Pixbuf.new_from_file(str(path))
            except GLib.Error:
                result = None
        GLib.idle_add(self._finish, (kind, url), result)

    @staticmethod
    def _download(url):
        # Keyed by URL: Discord media URLs change whenever the content does.
        path = CACHE_DIR / hashlib.sha1(url.encode()).hexdigest()
        if path.exists():
            path.touch()  # recently used files survive pruning
            return path
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 vesktop-discord-overlay"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read(MAX_DOWNLOAD + 1)
            if len(data) > MAX_DOWNLOAD:
                return None
            partial = path.with_suffix(".part")
            partial.write_bytes(data)
            partial.replace(path)
            return path
        except (OSError, ValueError):
            return None

    def _finish(self, key, result):
        self.done[key] = result
        if key[0] != "file" and result is not None and \
                max(result.get_width(), result.get_height()) > MEDIA_SMALL_PX:
            self.large[key] = True
            while len(self.large) > MEDIA_MEMORY_LARGE:
                del self.done[self.large.popitem(last=False)[0]]  # widgets showing it keep their own copy
        for callback in self.waiting.pop(key, []):
            callback(result)
        return False


def hex_rgb(color):
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))


def rounded_rect(cr, w, h, r):
    cr.new_sub_path()
    cr.arc(w - r, r, r, -math.pi / 2, 0)
    cr.arc(w - r, h - r, r, 0, math.pi / 2)
    cr.arc(r, h - r, r, math.pi / 2, math.pi)
    cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class Avatar(Gtk.DrawingArea):
    """Round (people) or rounded-square (servers) image with a text fallback and optional status dot."""

    def __init__(self, media, size, rounded_square=False):
        super().__init__()
        self.media = media
        self.size = size
        self.rounded_square = rounded_square
        self.url = None
        self.pixbuf = None
        self.fallback = ""
        self.status = None
        self.typing = False  # draws an animated "• • •" pill instead of the status dot
        self.typing_frame = 0
        self.typing_timer = None
        self.set_size_request(size, size)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)
        self.connect("destroy", lambda *_: self.set_typing(False))

    def set_typing(self, typing):
        """Discord-style: while they're typing, the status dot becomes a pulsing dots pill in their color."""
        if typing == self.typing:
            return
        self.typing = typing
        if typing and self.typing_timer is None:
            self.typing_timer = GLib.timeout_add(280, self._typing_tick)
        elif not typing and self.typing_timer is not None:
            GLib.source_remove(self.typing_timer)
            self.typing_timer = None
        self.queue_draw()

    def _typing_tick(self):
        self.typing_frame = (self.typing_frame + 1) % 3
        if self.get_mapped():
            self.queue_draw()
        return True

    def set(self, url, fallback, status=None):
        self.fallback = fallback
        self.status = status
        if url != self.url:
            self.url = url
            self.pixbuf = None
            if url:
                cached = self.media.image(url, lambda anim, u=url: self._loaded(u, anim))
                if cached:
                    self.pixbuf = self._scale(cached)
        self.queue_draw()

    def _scale(self, anim):
        return anim.get_static_image().scale_simple(self.size, self.size, GdkPixbuf.InterpType.BILINEAR)

    def _loaded(self, url, anim):
        if url == self.url and anim:
            self.pixbuf = self._scale(anim)
            self.queue_draw()

    def _draw(self, _widget, cr):
        s = self.size
        cr.save()
        if self.rounded_square:
            rounded_rect(cr, s, s, s * 0.3)
        else:
            cr.arc(s / 2, s / 2, s / 2, 0, 2 * math.pi)
        cr.clip()
        if self.pixbuf:
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
            cr.paint()
        else:
            cr.set_source_rgb(*hex_rgb(ACCENT))
            cr.paint()
            layout = self.create_pango_layout(self.fallback)
            layout.set_font_description(Pango.FontDescription(f"Noto Sans Bold {max(7, int(s * 0.28))}px"))
            tw, th = layout.get_pixel_size()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to((s - tw) / 2, (s - th) / 2)
            PangoCairo.show_layout(cr, layout)
        cr.restore()
        color = hex_rgb(STATUS_COLORS.get(self.status, STATUS_COLORS["offline"]))
        if self.status and self.typing:
            # A pill in their status color with three dots that pulse one after another.
            h = s * 0.34
            w = h * 1.9
            x, y = s - w - 1.5, s - h - 1.5
            rounded_rect_at(cr, x - 2.5, y - 2.5, w + 5, h + 5, (h + 5) / 2)
            cr.set_source_rgb(*hex_rgb(SIDEBAR))
            cr.fill()
            rounded_rect_at(cr, x, y, w, h, h / 2)
            cr.set_source_rgb(*color)
            cr.fill()
            dot = h * 0.16
            for i in range(3):
                cr.arc(x + w * (0.27 + 0.23 * i), y + h / 2, dot, 0, 2 * math.pi)
                cr.set_source_rgba(*hex_rgb(SIDEBAR), 1.0 if i == self.typing_frame else 0.45)
                cr.fill()
        elif self.status:
            r = s * 0.15
            cx = cy = s - r - 1
            cr.arc(cx, cy, r + 2.5, 0, 2 * math.pi)
            cr.set_source_rgb(*hex_rgb(SIDEBAR))
            cr.fill()
            cr.arc(cx, cy, r, 0, 2 * math.pi)
            cr.set_source_rgb(*color)
            cr.fill()
        return False


def fit(w, h, max_w, max_h):
    """Scale (w, h) down to fit inside max_w x max_h, keeping the aspect ratio; never scales up."""
    scale = min(1.0, max_w / w, max_h / h)
    return max(1, round(w * scale)), max(1, round(h * scale))


def sized_url(url, w, h):
    """Ask Discord's media proxy for a pre-shrunk copy instead of the full-size original."""
    host = urllib.parse.urlparse(url).hostname or ""
    if host == "media.discordapp.net" or host.startswith("images-ext-"):
        return f"{url}{'&' if '?' in url else '?'}width={w}&height={h}"
    return url


class Picture(Gtk.DrawingArea):
    """A still or animated image drawn at a fixed size with rounded corners, plus spoiler / play overlays."""

    def __init__(self, w, h, play_badge=False, spoiler=False, cover=False, caption=None):
        super().__init__()
        self.w, self.h = w, h
        self.play_badge = play_badge
        self.spoiler = spoiler
        self.cover = cover  # crop to fill instead of stretching
        self.caption = caption
        self.pixbuf = None
        self.frames = None  # GdkPixbufAnimationIter while animating
        self.timer = None
        self.set_size_request(w, h)
        self.connect("draw", self._draw)
        self.connect("destroy", lambda *_: self.stop())

    def set_animation(self, anim):
        self.stop()
        if anim.is_static_image():
            self._show(anim.get_static_image())
            return
        self.frames = anim.get_iter(None)
        self._show(self.frames.get_pixbuf())
        self._schedule()

    def set_pixbuf(self, pixbuf):
        self.stop()
        self._show(pixbuf)

    def _show(self, pixbuf):
        if self.cover:
            pw, ph = pixbuf.get_width(), pixbuf.get_height()
            scale = max(self.w / pw, self.h / ph)
            sw, sh = max(self.w, round(pw * scale)), max(self.h, round(ph * scale))
            scaled = pixbuf.scale_simple(sw, sh, GdkPixbuf.InterpType.BILINEAR)
            self.pixbuf = scaled.new_subpixbuf((sw - self.w) // 2, (sh - self.h) // 2, self.w, self.h)
        else:
            self.pixbuf = pixbuf.scale_simple(self.w, self.h, GdkPixbuf.InterpType.BILINEAR)
        self.queue_draw()

    def _schedule(self):
        delay = self.frames.get_delay_time()
        if delay >= 0:
            self.timer = GLib.timeout_add(max(20, delay), self._next_frame)

    def _next_frame(self):
        self.timer = None
        if self.frames is None:
            return False
        if self.get_mapped():
            if self.frames.advance(None):
                self._show(self.frames.get_pixbuf())
            self._schedule()
        else:
            self.timer = GLib.timeout_add(500, self._next_frame)  # off screen: idle cheaply
        return False

    def stop(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        self.frames = None

    def _draw(self, _widget, cr):
        w, h = self.w, self.h
        rounded_rect(cr, w, h, min(8, w / 4, h / 4))
        cr.clip()
        if self.pixbuf is None:
            cr.set_source_rgb(*hex_rgb(SIDEBAR))
            cr.paint()
        elif self.spoiler:
            # Pixelate, then darken: hides the content but hints there's an image.
            tiny = self.pixbuf.scale_simple(max(1, w // 24), max(1, h // 24), GdkPixbuf.InterpType.BILINEAR)
            Gdk.cairo_set_source_pixbuf(cr, tiny.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR), 0, 0)
            cr.paint()
        else:
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
            cr.paint()

        if self.caption:
            cr.set_source_rgba(0, 0, 0, 0.45)
            cr.paint()
            layout = self.create_pango_layout(self.caption)
            layout.set_font_description(font("Noto Sans Bold", 11))
            layout.set_width((w - 12) * Pango.SCALE)
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            layout.set_alignment(Pango.Alignment.CENTER)
            _, th = layout.get_pixel_size()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(6, (h - th) / 2)
            PangoCairo.show_layout(cr, layout)
        elif self.spoiler:
            cr.set_source_rgba(0, 0, 0, 0.55)
            cr.paint()
            layout = self.create_pango_layout("SPOILER")
            layout.set_font_description(font("Noto Sans Bold", 10))
            tw, th = layout.get_pixel_size()
            cr.set_source_rgba(0, 0, 0, 0.7)
            rounded_rect_at(cr, (w - tw) / 2 - 10, (h - th) / 2 - 5, tw + 20, th + 10, 10)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to((w - tw) / 2, (h - th) / 2)
            PangoCairo.show_layout(cr, layout)
        elif self.play_badge:
            r = min(24, w / 4, h / 4)
            cr.arc(w / 2, h / 2, r, 0, 2 * math.pi)
            cr.set_source_rgba(0, 0, 0, 0.6)
            cr.fill()
            cr.move_to(w / 2 - r * 0.35, h / 2 - r * 0.5)
            cr.line_to(w / 2 + r * 0.55, h / 2)
            cr.line_to(w / 2 - r * 0.35, h / 2 + r * 0.5)
            cr.close_path()
            cr.set_source_rgb(1, 1, 1)
            cr.fill()
        return False


def rounded_rect_at(cr, x, y, w, h, r):
    cr.save()
    cr.translate(x, y)
    rounded_rect(cr, w, h, r)
    cr.restore()


class LoopingVideo:
    """Silent, looping mp4 playback (how Discord shows Tenor/Klipy GIFs) through GStreamer's GTK sink."""

    def __init__(self, path, w, h):
        self.widget = None
        self.started = False
        self.pipeline = Gst.ElementFactory.make("playbin")
        try:
            # Scale inside GStreamer: the sink widget otherwise asks for the clip's native size.
            video_bin = Gst.parse_bin_from_description(
                f"videoconvert ! videoscale ! video/x-raw,width={w},height={h},pixel-aspect-ratio=1/1 "
                f"! gtksink name=sink", True)
        except GLib.Error:
            video_bin = None
        if not self.pipeline or not video_bin:
            self.pipeline = None
            return
        sink = video_bin.get_by_name("sink")
        self.pipeline.connect("element-setup", _one_decoder_thread)
        self.pipeline.set_property("uri", Gst.filename_to_uri(str(path)))
        self.pipeline.set_property("video-sink", video_bin)
        self.pipeline.set_property("audio-sink", Gst.ElementFactory.make("fakesink"))
        self.widget = sink.get_property("widget")
        self.widget.set_size_request(w, h)
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message::eos", self._restart)
        self.bus.connect("message::error", lambda *_: self.stop())

    def _restart(self, *_):
        if self.pipeline:
            self.pipeline.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0)

    def play(self):
        if self.pipeline:
            self.started = True
            self.pipeline.set_state(Gst.State.PLAYING)

    def pause(self):
        # Never pause a pipeline that hasn't started: that also brings up the sink (see MediaView).
        if self.pipeline and self.started:
            self.pipeline.set_state(Gst.State.PAUSED)

    def stop(self):
        """Shut the player down in the background: GStreamer takes ~70 ms per player to do it, which with a
        dozen GIFs in a chat would freeze the panel for most of a second."""
        if self.pipeline:
            pipeline, widget = self.pipeline, self.widget
            self.pipeline = None
            self.bus.remove_signal_watch()
            _stopping.add((pipeline, widget))  # kept alive until it's down (the sink draws into the widget)

            def shut_down():
                pipeline.set_state(Gst.State.NULL)
                GLib.idle_add(lambda: _stopping.discard((pipeline, widget)) or False)
            threading.Thread(target=shut_down, daemon=True).start()


_stopping = set()  # video players being shut down in the background


def _one_decoder_thread(_playbin, element):
    """GIF clips are tiny: one decoding thread each is plenty. By default the decoder starts one per CPU core
    for every GIF, so a chat with eight GIFs ran ~130 threads with a frame buffer set each."""
    if element.find_property("max-threads") is not None:
        element.set_property("max-threads", 1)


YOUTUBE_PAGE = """<!doctype html>
<html><body style="margin:0;background:#000;overflow:hidden">
<iframe src="https://www.youtube.com/embed/{id}?autoplay=1&playsinline=1&rel=0" style="border:0;width:100vw;height:100vh"
  allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen
  referrerpolicy="strict-origin-when-cross-origin"></iframe>
</body></html>"""
# YouTube's embed refuses to play without a referring page ("Error 153"), so the player is wrapped in a tiny
# page of our own served from this made-up origin rather than loading the embed URL directly.
YOUTUBE_ORIGIN = "https://vesktop-discord-overlay.localhost/"


def youtube_player(video_id, w, h, open_url):
    """YouTube's official embedded player in a small web view."""
    view = WebKit2.WebView(website_policies=WebKit2.WebsitePolicies(autoplay=WebKit2.AutoplayPolicy.ALLOW))
    view.set_size_request(w, h)
    settings = view.get_settings()
    settings.set_enable_fullscreen(True)
    settings.set_media_playback_requires_user_gesture(False)
    # Links inside the player (title, YouTube logo, "watch on YouTube") open in the normal browser.
    view.connect("create", lambda _v, action: open_url(action.get_request().get_uri()))
    view.load_html(YOUTUBE_PAGE.format(id=video_id), YOUTUBE_ORIGIN)
    return view


class MediaView(Gtk.EventBox):
    """One inline image / GIF / video thumbnail in a message. Click reveals a spoiler, or opens it full size.

    YouTube thumbnails instead ask on_play to start the embedded player in their place.
    """

    def __init__(self, media, item, open_url, on_play=None, on_view=None):
        super().__init__()
        self.item = item
        self.open_url = open_url
        self.on_play = on_play
        self.on_view = on_view  # opens the overlay's own viewer for images / GIFs
        self.video = None
        self.player = None  # YouTube web view while playing
        self.active = True
        self.alive = True
        self.youtube = item.get("youtube") if HAVE_WEBKIT and on_play else None
        if item.get("sticker"):
            limit = (STICKER_SIZE, STICKER_SIZE)
        elif self.youtube:
            limit = (YOUTUBE_MAX_W, YOUTUBE_MAX_H)
        else:
            limit = (MEDIA_MAX_W, MEDIA_MAX_H)
        self.w, self.h = fit(item["w"], item["h"], *limit)
        self.set_halign(Gtk.Align.START)
        self.picture = Picture(self.w, self.h, play_badge=item["kind"] == "poster", spoiler=item.get("spoiler", False))
        self.add(self.picture)
        # Opens on a whole click: pressed and released on it. (A release alone, e.g. after an emoji picked
        # above it made the picker vanish, doesn't count.)
        self.pressed = False
        self.connect("button-press-event", self._pressed)
        self.connect("button-release-event", self._clicked)
        self.connect("realize", self._set_cursor)
        self.connect("destroy", self._destroyed)
        self.connect("map", lambda *_: self._sync_playback())
        self.connect("unmap", lambda *_: self._sync_playback())

        kind = item["kind"]
        still = item.get("poster") if kind == "video" else item["src"]
        if still:
            resizable = kind in ("image", "poster") and not item.get("sticker")
            anim = media.image(sized_url(still, self.w, self.h) if resizable else still, self._image_ready)
            if anim:
                self.picture.set_animation(anim)
        if kind == "video" and HAVE_VIDEO:
            path = media.file(item["src"], self._video_ready)
            if path:
                self._video_ready(path)

    def _set_cursor(self, widget):
        widget.get_window().set_cursor(Gdk.Cursor.new_from_name(widget.get_display(), "pointer"))

    def _image_ready(self, anim):
        if anim and self.alive and self.video is None:
            self.picture.set_animation(anim)

    def _video_ready(self, path):
        if not path or not self.alive or self.video:
            return
        video = LoopingVideo(path, self.w, self.h)
        if video.widget is None:
            return
        self.video = video
        self.remove(self.picture)
        self.picture.destroy()
        self.add(video.widget)
        video.widget.show()
        self._sync_playback()

    def set_active(self, active):
        """Pause videos while the panel is hidden."""
        self.active = active
        self._sync_playback()

    def _sync_playback(self):
        # Only start once we're on screen inside the panel: gtksink puts a widget that isn't in a window
        # yet into a window of its own, which would steal it from the message.
        if self.video:
            (self.video.play if self.active and self.get_mapped() else self.video.pause)()

    def _pressed(self, _widget, event):
        self.pressed = event.button == 1
        return False  # (the message under it still gets right-clicks)

    def _clicked(self, _widget, event):
        if event.button != 1 or not self.pressed:
            return False
        self.pressed = False
        alloc = self.get_allocation()
        if not (0 <= event.x < alloc.width and 0 <= event.y < alloc.height):
            return False  # slid off before letting go: no click
        if self.video is None and self.picture.spoiler:
            self.picture.spoiler = False
            self.picture.queue_draw()
        elif self.youtube and self.player is None:
            self.on_play(self)
        elif self.on_view and self.item["kind"] in ("image", "anim", "video") and not self.item.get("youtube"):
            self.on_view(self)
        else:
            self.open_url(self.item["full"])
        return True

    # ----- YouTube player (started/stopped by the overlay so only one plays at a time) -----

    def start_player(self):
        self.adopt_player(youtube_player(self.youtube, self.w, self.h, self.open_url))
        self.player.grab_focus()

    def adopt_player(self, player):
        """Show a player in place of the thumbnail (also used to carry a playing video across a re-render)."""
        if self.picture.get_parent() is self:
            self.remove(self.picture)
        self.player = player
        self.add(player)
        player.show()

    def detach_player(self):
        player, self.player = self.player, None
        if player is not None:
            self.remove(player)
        return player

    def stop_player(self):
        player = self.detach_player()
        if player is not None:
            player.destroy()
            if self.alive:
                self.add(self.picture)
                self.picture.show()

    def _destroyed(self, *_):
        self.alive = False
        if self.video:
            self.video.stop()
