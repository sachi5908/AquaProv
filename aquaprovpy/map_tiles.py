"""Asynchronous, viewport-only basemap tiles for a Matplotlib Qt canvas."""
from pathlib import Path
from textwrap import fill

import numpy as np
from PySide6.QtCore import QDateTime, QObject, QStandardPaths, QTimer, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkReply, QNetworkRequest

from .locations import tile_extent, visible_tiles


TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
ATTRIBUTION = '© OpenStreetMap contributors · openstreetmap.org/copyright'
USER_AGENT = b'AquaProv/1.0 (desktop sample-location map)'


class TileCache(QNetworkDiskCache):
    def prepare(self, metadata):
        # Qt honours HTTP caching/validation headers. Supply the policy's
        # seven-day fallback only when the server supplied no expiry.
        if not metadata.expirationDate().isValid():
            metadata.setExpirationDate(QDateTime.currentDateTimeUtc().addDays(7))
        return super().prepare(metadata)


def image_array(payload):
    image = QImage.fromData(payload)
    if image.isNull() or image.width() != 256 or image.height() != 256:
        raise ValueError('The map server did not return a 256 × 256 tile image.')
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(image.constBits(), dtype=np.uint8).reshape(256, 256, 4).copy()


class TileBasemap(QObject):
    """Fetch at most four tiles concurrently, with debounced pan/zoom refreshes.

    Only tile indexes are sent to the provider; labels and measurements remain
    local. No prefetching, offline-area downloads, or automatic retry loops.
    """
    status_changed = Signal(str, bool)

    def __init__(self, axis, canvas, parent=None, cache_directory=None, provider='osm'):
        super().__init__(parent)
        from .basemaps import basemap
        self.provider = basemap(provider)
        if provider == 'plain':
            raise ValueError('Plain coordinates do not use map tiles.')
        self.tile_url = TILE_URL if provider == 'osm' else self.provider['url']
        self.axis, self.canvas = axis, canvas
        self.manager = QNetworkAccessManager(self)
        cache = TileCache(self.manager)
        root = cache_directory or str(Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.GenericCacheLocation)) / 'AquaProv' / 'map-tiles')
        cache.setCacheDirectory(str(root))
        cache.setMaximumCacheSize(128 * 1024 * 1024)
        self.manager.setCache(cache)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.refresh)
        self.pending = {}
        self.queue = []
        self.images = {}
        self.failures = 0
        self.last_error = ''
        self.busy = False
        self.closed = False
        self.signature = None
        self.notice = axis.text(0.01, 0.99, 'Loading map background…', transform=axis.transAxes,
                                va='top', fontsize=8, color='#843c0c', zorder=10,
                                bbox={'facecolor': 'white', 'alpha': 0.9, 'edgecolor': 'none'})
        self.notice.set_in_layout(False)
        self.callbacks = [axis.callbacks.connect(event, self.schedule)
                          for event in ('xlim_changed', 'ylim_changed')]
        self.resize_callback = canvas.mpl_connect('resize_event', self.schedule)

    def schedule(self, *_):
        if not self.closed:
            self.busy = True
            self.status_changed.emit('Map view changed · loading background…', True)
            self.timer.start()

    def _cancel_requests(self):
        self.queue = []
        for reply in list(self.pending):
            reply.finished.disconnect()
            reply.abort()
            reply.deleteLater()
        self.pending.clear()

    def refresh(self, force=False):
        if self.closed:
            return
        if getattr(self.canvas, '_background_drawing', False):
            QTimer.singleShot(40, self, lambda: self.refresh(force))
            return
        self.timer.stop()
        # A deferred first draw has not yet constrained an equal-aspect map's
        # axes rectangle. Apply that geometry before selecting the tile zoom;
        # otherwise the next draw/export needlessly replaces the initial tiles.
        self.axis.apply_aspect()
        tiles = visible_tiles(self.axis.get_xlim(), self.axis.get_ylim(), self.axis.bbox.width,
                              max_zoom=self.provider['max_zoom'])
        signature = tuple(tiles)
        if signature == self.signature and not force:
            self._report()
            return
        self._cancel_requests()
        self.signature = signature
        self.failures, self.last_error = 0, ''
        wanted = set(tiles)
        for tile in list(self.images):
            if tile not in wanted:
                self.images.pop(tile).remove()
        self.queue = [tile for tile in tiles if tile not in self.images]
        self._pump()

    def _pump(self):
        while self.queue and len(self.pending) < 4:
            tile = self.queue.pop(0)
            z, x, y = tile
            request = QNetworkRequest(QUrl(self.tile_url.format(z=z, x=x, y=y)))
            request.setRawHeader(b'User-Agent', USER_AGENT)
            request.setRawHeader(b'Accept', b'image/png,image/jpeg')
            request.setTransferTimeout(10000)
            request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                                 QNetworkRequest.CacheLoadControl.PreferCache)
            reply = self.manager.get(request)
            self.pending[reply] = tile
            reply.finished.connect(lambda reply=reply: self._finished(reply))
        self._report()

    def _finished(self, reply):
        if self.closed or reply not in self.pending:
            return
        if getattr(self.canvas, '_background_drawing', False):
            # A reply may arrive while an Agg worker owns this scene. Keep the
            # reply alive and add its image only after the worker has joined.
            QTimer.singleShot(40, self, lambda: self._finished(reply))
            return
        tile = self.pending.pop(reply, None)
        if self.closed or tile is None:
            reply.deleteLater()
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError(reply.errorString())
            pixels = image_array(bytes(reply.readAll()))
            # Explicit limits and aspect=None preserve georeferencing and camera.
            self.images[tile] = self.axis.imshow(pixels, extent=tile_extent(tile),
                                                origin='upper', interpolation='bilinear',
                                                aspect=None, zorder=0)
        except ValueError as exc:
            self.failures += 1
            self.last_error = str(exc)
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if status in (403, 429):
                # Do not keep requesting from a provider that has blocked/rate-limited us.
                self.failures += len(self.queue)
                self.queue.clear()
        finally:
            reply.deleteLater()
        self._pump()

    def _report(self):
        if self.closed:
            return
        if getattr(self.canvas, '_background_drawing', False):
            QTimer.singleShot(40, self, self._report)
            return
        self.busy = bool(self.pending or self.queue or self.timer.isActive())
        if self.busy:
            message = f'Loading {self.provider["name"]} · {len(self.images)} tiles ready…'
        elif self.failures:
            message = (f'Background incomplete: {self.failures} tile(s) unavailable. '
                       'Samples are still positioned correctly. Check internet and Retry background.')
        elif not self.signature:
            message = 'Outside the map world bounds · use Reset view to return to the samples.'
        else:
            message = self.provider['name'] + ' ready · pan/zoom to explore; Export saves this view.'
        self.notice.set_text(fill(message, 65) if self.busy or self.failures or not self.signature else '')
        self.notice.set_visible(self.busy or bool(self.failures) or not self.signature)
        self.status_changed.emit(message + (f' ({self.last_error})' if self.last_error else ''), self.busy)
        self.canvas.draw_idle()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        for callback in self.callbacks:
            self.axis.callbacks.disconnect(callback)
        self.canvas.mpl_disconnect(self.resize_callback)
        self._cancel_requests()
        self.busy = False
