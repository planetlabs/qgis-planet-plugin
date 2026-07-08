# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_thumbnails.py
    ---------------------
    Date                 : September 2019
    Author               : Planet Federal
    Copyright            : (C) 2019 Planet Inc, https://planet.com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

__author__ = "Planet Federal"
__date__ = "September 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

from collections import defaultdict

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
from qgis.PyQt.QtCore import QObject, Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QImage, QPainter, QPixmap

from ..pe_utils import log, qgsgeometry_from_geojson
from ..planet_api import PlanetClient


class ThumbnailWorker(QObject):
    """Worker object that fetches image bytes from a URL on a background thread.

    Receives fetch requests via the ``fetch()`` slot, which is invoked on the
    background thread through Qt's signal/slot queued connection mechanism.

    Signals:
        finished_signal (str, bytes): Emitted with (url, image_bytes) on success.
        failed_signal (str): Emitted with (url) on failure.
    """

    finished_signal = pyqtSignal(str, bytes)
    failed_signal = pyqtSignal(str)

    def __init__(self, p_client):
        """
        Args:
            p_client (PlanetClient): Authenticated Planet API client used to fetch images.
        """
        super().__init__()
        self.p_client = p_client

    def fetch(self, url: str):
        """Fetch image bytes from a URL and emit the appropriate signal.

        This method is called on the background thread via a queued signal connection.
        Emits ``finished_signal`` on success or ``failed_signal`` if no bytes are returned.

        Args:
            url (str): The image URL to fetch.
        """
        image_bytes = self.p_client.get_image_bytes(url)
        if image_bytes is not None:
            self.finished_signal.emit(url, image_bytes)
        else:
            self.failed_signal.emit(url)


class ThumbnailManager(QObject):
    """Manages asynchronous thumbnail downloading and caching for widgets.

    Downloads thumbnails on a dedicated background thread to avoid blocking the UI.
    Caches results so each URL is only fetched once. Deduplicates in-flight requests
    so multiple widgets requesting the same URL only trigger a single fetch.

    Usage::

        _thumbnailManager.download_thumbnail(url, widget)

    The widget must implement a ``set_thumbnail(QImage)`` method.

    Signals:
        _fetch_requested (str): Internal signal that dispatches a URL to the worker thread.
    """

    _fetch_requested = pyqtSignal(str)

    def __init__(self):
        """Initializes the cache, worker, and background thread, then starts the thread."""
        super().__init__()
        self.p_client = PlanetClient.getInstance()
        self.thumbnails = {}
        self.widgets = defaultdict(list)

        self.thread = QThread()
        self.worker = ThumbnailWorker(self.p_client)
        self.worker.moveToThread(self.thread)

        self._fetch_requested.connect(self.worker.fetch)
        self.worker.finished_signal.connect(self.thumbnail_downloaded)
        self.worker.failed_signal.connect(self.thumbnail_failed)

        self.thread.start()

    def download_thumbnail(self, url, widget):
        """Request a thumbnail for a widget.

        Serves immediately from cache if available. Otherwise registers the widget
        and dispatches a background fetch if one is not already in progress for this URL.

        Args:
            url (str): The thumbnail image URL.
            widget: A widget implementing ``set_thumbnail(QImage)``.
        """

        if url in self.thumbnails:
            widget.set_thumbnail(self.thumbnails[url])
        else:
            self.widgets[url].append(widget)
            if len(self.widgets[url]) == 1:  # first request for this url
                self._fetch_requested.emit(url)

    def thumbnail_downloaded(self, url, image_bytes):
        """Handle a successful fetch.

        Converts raw bytes to a ``QImage``, stores it in the cache, and calls
        ``set_thumbnail`` on all widgets that were waiting for this URL.

        Args:
            url (str): The URL that was fetched.
            image_bytes (bytes): Raw image bytes returned by the worker.
        """
        img = QImage()
        img.loadFromData(image_bytes)
        self.thumbnails[url] = img
        for w in self.widgets[url]:
            try:
                w.set_thumbnail(img)
            except Exception as e:
                log.debug(f"Failed to set thumbnail for widget (likely closed): {e}")
                pass

    def thumbnail_failed(self, url):
        """Handle a failed fetch by logging a warning.

        Args:
            url (str): The URL that failed to fetch.
        """
        log.warning(f"Failed to download thumbnail for url: {url}")

    def shutdown(self):
        """
        Shuts down the background thread cleanly.
        Should be called when the plugin unloads to avoid dangling threads.
        """
        self.thread.quit()
        self.thread.wait()


_thumbnailManager = ThumbnailManager()


def download_thumbnail(url, widget):
    """Module-level convenience function to request a thumbnail download.

    Args:
        url (str): The thumbnail image URL.
        widget: A widget implementing ``set_thumbnail(QImage)``.
    """
    _thumbnailManager.download_thumbnail(url, widget)


def createCompoundThumbnail(_bboxes, thumbnails):
    """Composite multiple thumbnails into a single 256x256 pixmap arranged
    by their geographic positions.

    Bboxes are reprojected from EPSG:4326 to EPSG:3857 for proportional pixel
    math. Non-square bboxes are symmetrically padded to avoid stretching.
    Returns a transparent pixmap if painting fails.

    Args:
        _bboxes (list): GeoJSON geometry dicts in EPSG:4326, one per thumbnail.
        thumbnails (list[QPixmap]): Thumbnail pixmaps, same order as ``_bboxes``.

    Returns:
        QPixmap: 256x256 composite pixmap, or empty transparent pixmap on error.
    """
    bboxes = []
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsProject.instance(),
    )
    for box in _bboxes:
        rect4326 = qgsgeometry_from_geojson(box).boundingBox()
        rect = transform.transformBoundingBox(rect4326)
        bboxes.append(
            [rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()]
        )
    globalbox = (
        min([v[0] for v in bboxes]),
        min([v[1] for v in bboxes]),
        max([v[2] for v in bboxes]),
        max([v[3] for v in bboxes]),
    )
    SIZE = 256
    globalwidth = globalbox[2] - globalbox[0]
    globalheight = globalbox[3] - globalbox[1]
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        for i, thumbnail in enumerate(thumbnails):
            box = bboxes[i]
            width = box[2] - box[0]
            height = box[3] - box[1]
            if width > height:
                offsety = (width - height) / 2
                offsetx = 0
            else:
                offsetx = (height - width) / 2
                offsety = 0
            x = int((box[0] - offsetx - globalbox[0]) / globalwidth * SIZE)
            y = int((globalbox[3] - box[3] - offsety) / globalheight * SIZE)
            outputwidth = int((width + 2 * offsetx) / globalwidth * SIZE)
            outputheight = int((height + 2 * offsety) / globalheight * SIZE)
            painter.drawPixmap(x, y, outputwidth, outputheight, thumbnail)
    except Exception as e:
        # Unexpected values for bboxes might cause unexpected errors. We just ignore
        # them and return an empty image in that case
        log.debug(f"Failed to create compound thumbnail: {e}")
    finally:
        painter.end()
    return pixmap
