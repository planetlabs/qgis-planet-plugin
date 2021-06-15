# -*- coding: utf-8 -*-
"""
***************************************************************************
    aoi_maptools.py
    ---------------------
    Date                 : March 2017, August 2019
    Author               : Alex Bruy, Planet Federal
    Copyright            : (C) 2017 Boundless, http://boundlessgeo.com
                         : (C) 2019 Planet Inc, https://planet.com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
__author__ = 'Planet Federal'
__date__ = 'August 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import logging
from math import sqrt

from qgis.PyQt.QtCore import (
    pyqtSignal,
    Qt,
    QRect,
    # QPoint,
    QPointF
)

from qgis.PyQt.QtGui import (
    QColor,
)

from qgis.core import (
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsRectangle,
    QgsCircle,
    QgsWkbTypes,
)

from qgis.gui import (
    QgsMapTool,
    QgsRubberBand,
)

from ..pe_utils import (
    PLANET_COLOR
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

RB_STROKE = PLANET_COLOR
RB_FILL = QColor(204, 235, 239, 100)


# noinspection DuplicatedCode
class PlanetExtentMapTool(QgsMapTool):

    extentSelected = pyqtSignal(object)

    def __init__(self, canvas):
        QgsMapTool.__init__(self, canvas)

        self.canvas = canvas
        self.extent = None
        self.dragging = False
        self.rubber_band = None
        self.select_rect = QRect()

    def canvasPressEvent(self, event):
        self.select_rect.setRect(0, 0, 0, 0)
        self.rubber_band = QgsRubberBand(self.canvas,
                                         QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setFillColor(RB_FILL)
        self.rubber_band.setStrokeColor(RB_STROKE)
        self.rubber_band.setWidth(1)

    def canvasMoveEvent(self, event):
        if event.buttons() != Qt.LeftButton:
            return

        if not self.dragging:
            self.dragging = True
            self.select_rect.setTopLeft(event.pos())

        self.select_rect.setBottomRight(event.pos())
        self._set_rubber_band()

    def canvasReleaseEvent(self, event):
        # If the user simply clicked without dragging ignore this
        if not self.dragging:
            return

        # Set valid values for rectangle's width and height
        if self.select_rect.width() == 1:
            self.select_rect.setLeft(self.select_rect.left() + 1)
        if self.select_rect.height() == 1:
            self.select_rect.setBottom(self.select_rect.bottom() + 1)

        if self.rubber_band:
            self._set_rubber_band()

            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            del self.rubber_band
            self.rubber_band = None

        self.dragging = False

        # noinspection PyUnresolvedReferences
        self.extentSelected.emit(self.extent)

    def _set_rubber_band(self):
        transform = self.canvas.getCoordinateTransform()

        ll = transform.toMapCoordinates(
            self.select_rect.left(), self.select_rect.bottom())
        ur = transform.toMapCoordinates(
            self.select_rect.right(), self.select_rect.top())

        if self.rubber_band:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            self.rubber_band.addPoint(ll, False)
            self.rubber_band.addPoint(QgsPointXY(ur.x(), ll.y()), False)
            self.rubber_band.addPoint(ur, False)
            self.rubber_band.addPoint(QgsPointXY(ll.x(), ur.y()), True)
            self.extent = QgsRectangle(ur, ll)


# noinspection DuplicatedCode
class PlanetCircleMapTool(QgsMapTool):

    circleSelected = pyqtSignal(object)

    def __init__(self, canvas):
        QgsMapTool.__init__(self, canvas)

        self.canvas = canvas
        self.circle = QgsGeometry
        self.dragging = False
        self.rubber_band = None
        self.center = QPointF()
        self.tangent_point = QPointF()
        self.radius = 0.0

    def canvasPressEvent(self, event):
        self.center = event.pos()
        self.rubber_band = QgsRubberBand(self.canvas,
                                         QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setFillColor(RB_FILL)
        self.rubber_band.setStrokeColor(RB_STROKE)
        self.rubber_band.setWidth(1)

    def canvasMoveEvent(self, event):
        if event.buttons() != Qt.LeftButton:
            return

        if not self.dragging:
            self.dragging = True
            self.center = event.pos()

        self.tangent_point = event.pos()
        self.radius = sqrt(QPointF.dotProduct(self.center, self.tangent_point))
        self._set_rubber_band()

    def canvasReleaseEvent(self, event):
        # If the user simply clicked without dragging ignore this
        if not self.dragging:
            return

        if self.rubber_band:
            self._set_rubber_band()

            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            del self.rubber_band
            self.rubber_band = None

        self.dragging = False

        # noinspection PyUnresolvedReferences
        self.circleSelected.emit(self.circle)

    def _set_rubber_band(self):
        transform = self.canvas.getCoordinateTransform()

        rb_center = transform.toMapCoordinates(
            self.center)
        rb_tangent = transform.toMapCoordinates(
            self.tangent_point)
        rb_circle = QgsCircle(QgsPoint(rb_center.x(), rb_center.y()),
                              rb_center.distance(rb_tangent.x(),
                                                 rb_tangent.y()))
        circle_geom = QgsGeometry(rb_circle.toPolygon())

        if self.rubber_band:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            self.rubber_band.addGeometry(circle_geom)
            self.circle = circle_geom


# noinspection DuplicatedCode
class PlanetPolyMapTool(QgsMapTool):
    polygonSelected = pyqtSignal(object)

    def __init__(self, canvas):
        QgsMapTool.__init__(self, canvas)

        self.canvas = canvas
        self.extent = None
        self.rubber_band = QgsRubberBand(self.canvas,
                                         QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setFillColor(RB_FILL)
        self.rubber_band.setStrokeColor(RB_STROKE)
        self.rubber_band.setWidth(1)
        self.vertex_count = 1  # two points are dropped initially

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            if self.rubber_band is None or self.extent is None:
                return
            # TODO: validate geom before firing signal
            self.extent.removeDuplicateNodes()
            self.polygonSelected.emit(self.extent)
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            del self.rubber_band
            self.rubber_band = None
            self.vertex_count = 1  # two points are dropped initially
            return
        elif event.button() == Qt.LeftButton:
            if self.rubber_band is None:
                self.rubber_band = QgsRubberBand(
                    self.canvas, QgsWkbTypes.PolygonGeometry)
                self.rubber_band.setFillColor(RB_FILL)
                self.rubber_band.setStrokeColor(RB_STROKE)
                self.rubber_band.setWidth(1)
            self.rubber_band.addPoint(event.mapPoint())
            self.extent = self.rubber_band.asGeometry()
            self.vertex_count += 1

    def canvasMoveEvent(self, event):
        if self.rubber_band is None:
            pass
        elif not self.rubber_band.numberOfVertices():
            pass
        elif self.rubber_band.numberOfVertices() == self.vertex_count:
            if self.vertex_count == 2:
                mouse_vertex = self.rubber_band.numberOfVertices() - 1
                self.rubber_band.movePoint(mouse_vertex, event.mapPoint())
            else:
                self.rubber_band.addPoint(event.mapPoint())
        else:
            mouse_vertex = self.rubber_band.numberOfVertices() - 1
            self.rubber_band.movePoint(mouse_vertex, event.mapPoint())

    def deactivate(self):
        QgsMapTool.deactivate(self)
        # noinspection PyUnresolvedReferences
        self.deactivated.emit()
