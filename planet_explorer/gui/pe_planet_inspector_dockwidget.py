# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_orders_monitor_dialog.py
    ---------------------
    Date                 : September 2019
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

import logging
import os
import re

import iso8601
import mercantile
from planet.api.filters import build_search_request, string_filter
from planet.api.models import Mosaics
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
    QgsRectangle,
    QgsWkbTypes,
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand

from qgis.PyQt import uic

from qgis.PyQt.QtCore import QSize, Qt, QUrl, pyqtSignal

from qgis.PyQt.QtGui import QIcon, QImage, QPixmap

from qgis.PyQt.QtWidgets import (
    QAction,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from qgis.utils import iface

from ..pe_analytics import analytics_track, basemap_name_for_analytics
from ..pe_utils import PLANET_COLOR, add_menu_section_action, qgsgeometry_from_geojson
from ..planet_api import PlanetClient
from ..planet_api.p_specs import DAILY_ITEM_TYPES_DICT
from .pe_gui_utils import waitcursor


class PointCaptureMapTool(QgsMapToolEmitPoint):

    complete = pyqtSignal()

    def __init__(self, canvas):
        QgsMapToolEmitPoint.__init__(self, canvas)

        self.canvas = canvas
        self.cursor = Qt.CrossCursor

    def activate(self):
        self.canvas.setCursor(self.cursor)

    def canvasReleaseEvent(self, event):
        self.complete.emit()


ID = "id"
NAME = "name"
ITEM_IDS = "item_ids"
PROPERTIES = "properties"
GEOMETRY = "geometry"
COORDINATES = "coordinates"
ITEM_TYPE = "item_type"

plugin_path = os.path.split(os.path.dirname(__file__))[0]

COG_ICON = QIcon(":/plugins/planet_explorer/cog.svg")
INSPECTOR_ICON = QIcon(os.path.join(plugin_path, "resources", "inspector.png"))
PLACEHOLDER_THUMB = ":/plugins/planet_explorer/thumb-placeholder-128.svg"

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get("PYTHON_LOG_VERBOSE", None)

ORDERS_MONITOR_WIDGET, ORDERS_MONITOR_BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_planet_inspector_dockwidget.ui"),
    from_imports=True,
    import_from=os.path.basename(plugin_path),
    resource_suffix="",
)


class PlanetInspectorDockWidget(ORDERS_MONITOR_BASE, ORDERS_MONITOR_WIDGET):
    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent=parent)
        self.p_client = PlanetClient.getInstance()

        self.setupUi(self)

        self.btnMapTool.setIcon(INSPECTOR_ICON)

        self.textBrowser.setHtml(
            """<center>
                Click on a visible pixel within a streamed or previewed Planet Basemap
                </center>"""
        )
        self.textBrowser.setVisible(True)
        self.listScenes.setVisible(False)

        self.listScenes.setAlternatingRowColors(True)
        self.listScenes.setSelectionMode(self.listScenes.NoSelection)

        self.map_tool = PointCaptureMapTool(iface.mapCanvas())
        self.map_tool.canvasClicked.connect(self.point_captured)
        self.btnMapTool.toggled.connect(self._set_map_tool)
        iface.mapCanvas().mapToolSet.connect(self._map_tool_set)

    def point_captured(self, point, button):
        self._populate_scenes_from_point(point)

    @waitcursor
    def _populate_scenes_from_point(self, point):
        self.listScenes.clear()
        canvasCrs = iface.mapCanvas().mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(
            canvasCrs, QgsCoordinateReferenceSystem(4326), QgsProject.instance()
        )
        wgspoint = transform.transform(point)
        mosaicname = self._mosaic_name_from_current_layer()
        if mosaicname:
            client = PlanetClient.getInstance()
            mosaic = (
                client.get_mosaic_by_name(mosaicname).get().get(Mosaics.ITEM_KEY)[0]
            )
            analytics_track(
                "basemap_inspected", {"mosaic_type": basemap_name_for_analytics(mosaic)}
            )
            tile = mercantile.tile(wgspoint.x(), wgspoint.y(), mosaic["level"])
            url = "https://tiles.planet.com/basemaps/v1/pixprov/{}/{}/{}/{}.json"
            url = url.format(mosaicname, tile.z, tile.x, tile.y)
            data = client._get(url).get_body().get()
            grid = self.parse_utfgrid(data["grid"])
            links = data["keys"]
            idx = self.read_val_at_pixel(
                grid, wgspoint.y(), wgspoint.x(), mosaic["level"]
            )
            url = links[idx]
            try:
                info = client._get(url).get_body().get()
                item = SceneItem(info)
                self.listScenes.addItem(item)
                widget = SceneItemWidget(info)
                item.setSizeHint(widget.sizeHint())
                self.listScenes.setItemWidget(item, widget)
                self.textBrowser.setVisible(False)
                self.listScenes.setVisible(True)
            except Exception:
                self.textBrowser.setHtml(
                    """
                        <center><span style="color: rgb(200,0,0);">
                        ⚠️ The selected pixel is not part of a streamed Planet Basemap.
                        </span></center>
                    """
                )
                self.textBrowser.setVisible(True)
                self.listScenes.setVisible(False)
        else:
            self.textBrowser.setHtml(
                """
                    <center><span style="color: rgb(200,0,0);">
                    ⚠️ Current layer is not a Planet Basemap.
                    </span></center>
                """
            )
            self.textBrowser.setVisible(True)
            self.listScenes.setVisible(False)

    def parse_utfgrid(self, utf):
        """Convert a utfgrid formatted array into an integer array."""

        def _convert_char(character):
            val = ord(character)
            for breakpoint in [93, 35]:
                if val >= breakpoint:
                    val -= 1
            return val - 32

        grid = []
        for line in utf:
            grid.append([_convert_char(x) for x in line])
        return grid

    def read_val_at_pixel(self, grid, lat, lon, zoom):
        """Interpolate the row/column of a webtile from a lat/lon/zoom and extract
        the corresponding value from `grid`."""
        tile = mercantile.tile(lon, lat, zoom)
        size = len(grid)
        box = mercantile.xy_bounds(tile)
        x, y = mercantile.xy(lon, lat)
        width = box.right - box.left
        height = box.top - box.bottom
        i = int(round(size * (box.top - y) / height))
        j = int(round(size * (x - box.left) / width))
        return grid[i][j]

    def _mosaic_name_from_current_layer(self):
        name = None
        layer = iface.activeLayer()
        if layer is not None:
            source = layer.source()
            for prop in source.split("&"):
                tokens = prop.split("=")
                if tokens[0] == "url":
                    url = tokens[1]
                    groups = re.search(
                        "https://tiles.planet.com/basemaps/v1/planet-tiles/(.*)/gmap",
                        url,
                        re.IGNORECASE,
                    )
                    if groups:
                        name = groups.group(1)
                        break
        return name

    def _set_map_tool(self, checked):
        if checked:
            self.prev_map_tool = iface.mapCanvas().mapTool()
            iface.mapCanvas().setMapTool(self.map_tool)
        else:
            iface.mapCanvas().setMapTool(self.prev_map_tool)

    def _map_tool_set(self, new, old):
        if new != self.map_tool:
            self.btnMapTool.blockSignals(True)
            self.btnMapTool.setChecked(False)
            self.btnMapTool.blockSignals(False)


class SceneItem(QListWidgetItem):
    def __init__(self, scene):
        QListWidgetItem.__init__(self)
        self.scene = scene


class SceneItemWidget(QFrame):
    def __init__(self, scene):
        QWidget.__init__(self)
        self.scene = scene
        self.properties = scene[PROPERTIES]

        self.setMouseTracking(True)

        datetime = iso8601.parse_date(self.properties["acquired"])
        time = datetime.strftime("%H:%M:%S")
        date = datetime.strftime("%b %d, %Y")

        text = f"""{date}<span style="color: rgb(100,100,100);"> {time} UTC</span><br>
                        <b>{DAILY_ITEM_TYPES_DICT[self.properties['item_type']]}</b>
                    """

        self.nameLabel = QLabel(text)
        self.iconLabel = QLabel()
        self.toolsButton = QLabel()
        self.toolsButton.setPixmap(COG_ICON.pixmap(QSize(18, 18)))
        self.toolsButton.mousePressEvent = self.showContextMenu

        pixmap = QPixmap(PLACEHOLDER_THUMB, "SVG")
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        layout = QHBoxLayout()
        layout.setMargin(2)
        vlayout = QVBoxLayout()
        vlayout.setMargin(0)
        vlayout.addWidget(self.iconLabel)
        self.iconWidget = QWidget()
        self.iconWidget.setFixedSize(48, 48)
        self.iconWidget.setLayout(vlayout)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.nameLabel)
        layout.addStretch()
        layout.addWidget(self.toolsButton)
        layout.addSpacing(10)
        self.setLayout(layout)
        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self.iconDownloaded)
        url = f"{scene['_links']['thumbnail']}?api_key={PlanetClient.getInstance().api_key()}"
        self.nam.get(QNetworkRequest(QUrl(url)))

        self.footprint = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
        self.footprint.setStrokeColor(PLANET_COLOR)
        self.footprint.setWidth(2)

        self.geom = qgsgeometry_from_geojson(scene[GEOMETRY])

        self.setStyleSheet("SceneItemWidget{border: 2px solid transparent;}")

    def showContextMenu(self, evt):
        menu = QMenu()
        add_menu_section_action("Current item", menu)
        zoom_act = QAction("Zoom to extent", menu)
        zoom_act.triggered.connect(self.zoom_to_extent)
        menu.addAction(zoom_act)
        open_act = QAction("Open in Search Panel", menu)
        open_act.triggered.connect(self.open_in_explorer)
        menu.addAction(open_act)
        menu.exec_(self.toolsButton.mapToGlobal(evt.pos()))

    def open_in_explorer(self):
        from .pe_explorer_dockwidget import show_explorer_and_search_daily_images

        request = build_search_request(
            string_filter("id", self.scene[ID]), [self.properties[ITEM_TYPE]]
        )
        show_explorer_and_search_daily_images(request)

    def zoom_to_extent(self):
        rect = QgsRectangle(self.geom.boundingBox())
        canvasCrs = iface.mapCanvas().mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem(4326), canvasCrs, QgsProject.instance()
        )
        newrect = transform.transform(rect)
        newrect.scale(1.05)
        iface.mapCanvas().setExtent(newrect)
        iface.mapCanvas().refresh()

    def iconDownloaded(self, reply):
        img = QImage()
        img.loadFromData(reply.readAll())
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)

    def show_footprint(self):
        rect = QgsRectangle(self.geom.boundingBox())
        canvasCrs = iface.mapCanvas().mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem(4326), canvasCrs, QgsProject.instance()
        )
        newrect = transform.transform(rect)
        self.footprint.setToGeometry(QgsGeometry.fromRect(newrect))

    def hide_footprint(self):
        self.footprint.reset(QgsWkbTypes.PolygonGeometry)

    def enterEvent(self, event):
        self.setStyleSheet("SceneItemWidget{border: 2px solid rgb(0, 157, 165);}")
        self.show_footprint()

    def leaveEvent(self, event):
        self.setStyleSheet("SceneItemWidget{border: 2px solid transparent;}")
        self.hide_footprint()


dockwidget_instance = None


def _get_widget_instance():
    global dockwidget_instance
    if dockwidget_instance is None:
        if not PlanetClient.getInstance().has_api_key():
            return None
        dockwidget_instance = PlanetInspectorDockWidget(parent=iface.mainWindow())
        dockwidget_instance.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )

        iface.addDockWidget(Qt.LeftDockWidgetArea, dockwidget_instance)

        dockwidget_instance.hide()
    return dockwidget_instance


def show_inspector():
    wdgt = _get_widget_instance()
    if wdgt is not None:
        wdgt.show()


def hide_inspector():
    wdgt = _get_widget_instance()
    if wdgt is not None:
        wdgt.hide()


def toggle_inspector():
    wdgt = _get_widget_instance()
    wdgt.setVisible(not wdgt.isVisible())


def remove_inspector():
    if dockwidget_instance is not None:
        iface.removeDockWidget(dockwidget_instance)
