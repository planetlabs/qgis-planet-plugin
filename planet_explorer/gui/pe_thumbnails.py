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

from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QImage, QPainter, QPixmap

from ..pe_utils import qgsgeometry_from_geojson, log


class ThumbnailManager:
    def __init__(self):
        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self.thumbnail_downloaded)
        self.thumbnails = {}
        self.widgets = defaultdict(list)

    def download_thumbnail(self, url, widget):
        if url in self.thumbnails:
            widget.set_thumbnail(self.thumbnails[url])
        else:
            self.widgets[url].append(widget)
            self.nam.get(QNetworkRequest(QUrl(url)))

    def thumbnail_downloaded(self, reply):
        if reply.error() == QNetworkReply.NoError:
            url = reply.url().toString()
            img = QImage()
            img.loadFromData(reply.readAll())
            self.thumbnails[url] = img
            for w in self.widgets[url]:
                try:
                    w.set_thumbnail(img)
                except Exception:
                    log("Error setting thumbnail for widget")
                    # the widget might have been deleted
                    pass


_thumbnailManager = ThumbnailManager()


def download_thumbnail(url, widget):
    _thumbnailManager.download_thumbnail(url, widget)


def createCompoundThumbnail(_bboxes, thumbnails):
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
    pixmap.fill(Qt.transparent)
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
    except Exception:
        """
        Unexpected values for bboxes might cause uneexpected errors. We just ignore
        them and return an empty image in that case
        """
    finally:
        painter.end()
    return pixmap
