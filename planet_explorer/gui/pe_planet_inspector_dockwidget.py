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
__author__ = 'Planet Federal'
__date__ = 'September 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import re
import iso8601
import shutil
import json
import logging
import requests
import zipfile
import traceback
from functools import partial
from collections import defaultdict

from planet.api.models import (
    Orders,
    Order
)

# noinspection PyPackageRequirements
from qgis.core import (
    QgsApplication,
    QgsTask, 
    Qgis,
    QgsMessageLog,
    QgsRasterLayer,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsWkbTypes,
    QgsRectangle,
    QgsGeometry
)

from qgis.gui import (
    QgsRubberBand,
    QgsMapToolEmitPoint
)

# noinspection PyPackageRequirements
from qgis.utils import (
    iface
)

# noinspection PyPackageRequirements
from qgis.PyQt import uic

# noinspection PyPackageRequirements
from qgis.PyQt.QtCore import (
    Qt,
    QCoreApplication,
    QUrl,
    QSize,
    pyqtSignal
)

# noinspection PyPackageRequirements
from qgis.PyQt.QtGui import (
    QCursor,
    QDesktopServices,
    QIcon,
    QPixmap,
    QImage
)

# noinspection PyPackageRequirements
from qgis.PyQt.QtWidgets import (
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QListWidgetItem,
    QApplication,
    QMessageBox,
    QSizePolicy,
    QMenu,
    QAction,
    QFrame
)

from PyQt5.QtNetwork import (
    QNetworkAccessManager,
    QNetworkRequest
)

from ..pe_utils import (
    QGIS_LOG_SECTION_NAME,
    orders_download_folder,
    is_segments_write_key_valid
)

from .pe_gui_utils import (
    waitcursor
)

from ..planet_api import (
    PlanetClient
)

from planet.api.filters import (
    string_filter,    
    build_search_request
)

from ..planet_api.p_specs import (    
    DAILY_ITEM_TYPES_DICT
)

from ..planet_api.p_node import (
       PLACEHOLDER_THUMB
)

from planet.api.models import (
    Mosaics,
    MosaicQuads
)

from ..planet_api.quad_orders import (
    quad_orders
)

from ..planet_api.order_tasks import (
    QuadsOrderProcessorTask,
    OrderProcessorTask
)

from ..pe_utils import (
    qgsgeometry_from_geojson,
    PLANET_COLOR,
    add_menu_section_action
)

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

COG_ICON = QIcon(':/plugins/planet_explorer/cog.svg')
INSPECTOR_ICON = QIcon(os.path.join(plugin_path, "resources", "inspector.png"))

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)


ORDERS_MONITOR_WIDGET, ORDERS_MONITOR_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_planet_inspector_dockwidget.ui'),
    from_imports=True, import_from=os.path.basename(plugin_path),
    resource_suffix=''
)

class PlanetInspectorDockWidget(ORDERS_MONITOR_BASE, ORDERS_MONITOR_WIDGET):
    
    def __init__(self,
                 parent=None,
                 ):
        super().__init__(parent=parent)
        self.p_client = PlanetClient.getInstance()

        self.setupUi(self)

        self.btnMapTool.setIcon(INSPECTOR_ICON)

        self.textBrowser.setHtml("""<center> 
                Click on a visible pixel within a streamed or previewed Planet Basemap
                </center>""")
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
        BUFFER = 0.00001

        self.listScenes.clear()
        canvasCrs = iface.mapCanvas().mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(canvasCrs, QgsCoordinateReferenceSystem(4326),
                                           QgsProject.instance())
        wgspoint = transform.transform(point)

        mosaicid = self._mosaic_id_from_current_layer()
        if mosaicid:
            bbox = [wgspoint.x() - BUFFER, wgspoint.y() - BUFFER,
                    wgspoint.x() + BUFFER, wgspoint.y() + BUFFER,]
            quads = self.p_client.get_quads_for_mosaic(mosaicid, bbox)
            json_quads = []
            for page in quads.iter():
                json_quads.extend(page.get().get(MosaicQuads.ITEM_KEY))
            if json_quads:
                pointgeom = QgsGeometry.fromPointXY(wgspoint)
                for quad in json_quads:
                    scenes = self.p_client.get_items_for_quad(mosaicid, quad[ID])
                    for scene in scenes:
                        geom = qgsgeometry_from_geojson(scene[GEOMETRY])
                        if pointgeom.within(geom):
                            item = SceneItem(scene)
                            self.listScenes.addItem(item)
                            widget = SceneItemWidget(scene)
                            item.setSizeHint(widget.sizeHint())
                            self.listScenes.setItemWidget(item, widget)
                self.textBrowser.setVisible(False)
                self.listScenes.setVisible(True)
            else:
                self.textBrowser.setHtml("""<center><span style="color: rgb(200,0,0);">
                                     ⚠️ The selected pixel is not part of a streamed Planet Basemap.
                                     </span></center>""")
                self.textBrowser.setVisible(True)
                self.listScenes.setVisible(False)
        else:   
            self.textBrowser.setHtml("""<center><span style="color: rgb(200,0,0);">
                                     ⚠️ Current layer is not a Planet Basemap.
                                     </span></center>""")
            self.textBrowser.setVisible(True)
            self.listScenes.setVisible(False)

    def _mosaic_id_from_current_layer(self):
        layer = iface.activeLayer()
        source = layer.source()        
        name = None
        for prop in source.split("&"):
            tokens = prop.split("=")
            if len(tokens) == 2 and tokens[0] == "url":
                url = tokens[1]
                groups = re.search('https://tiles.planet.com/basemaps/v1/planet-tiles/(.*)/gmap',
                                        url, re.IGNORECASE)

                if groups:
                    name = groups.group(1)
                    break
        if name is None:
            return
        client = PlanetClient.getInstance().api_client()
        mosaicid = client.get_mosaic_by_name(name).get().get(Mosaics.ITEM_KEY)[0][ID]
        return mosaicid
        
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

        datetime = iso8601.parse_date(self.properties["published"])
        date = datetime.strftime('%H:%M:%S')
        time = datetime.strftime('%b %d, %Y')
            
        text = f"""{date}<span style="color: rgb(100,100,100);">{time} UTC</span><br>
                        <b>{DAILY_ITEM_TYPES_DICT[self.properties['item_type']]}</b>
                    """

        self.nameLabel = QLabel(text)        
        self.iconLabel = QLabel()
        self.toolsButton = QLabel()
        self.toolsButton.setPixmap(COG_ICON.pixmap(QSize(18, 18)))
        self.toolsButton.mousePressEvent = self.showContextMenu

        pixmap = QPixmap(PLACEHOLDER_THUMB, 'SVG')
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio, 
                            Qt.SmoothTransformation)
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

        self.footprint = QgsRubberBand(iface.mapCanvas(),
                              QgsWkbTypes.PolygonGeometry)        
        self.footprint.setStrokeColor(PLANET_COLOR)
        self.footprint.setWidth(2)

        self.geom = qgsgeometry_from_geojson(scene[GEOMETRY])

        self.setStyleSheet("SceneItemWidget{border: 2px solid transparent;}")
        
    def showContextMenu(self, evt):
        menu = QMenu()
        add_menu_section_action('Current item', menu)
        zoom_act = QAction('Zoom to extent', menu)
        zoom_act.triggered.connect(self.zoom_to_extent)
        menu.addAction(zoom_act)
        open_act = QAction('Open in Explorer', menu)
        open_act.triggered.connect(self.open_in_explorer)
        menu.addAction(open_act)
        menu.exec_(self.toolsButton.mapToGlobal(evt.pos()))

    def open_in_explorer(self):
        from .pe_explorer_dockwidget import show_explorer_and_search_daily_images
        request = build_search_request(string_filter('id', self.scene[ID]), 
                                        [self.properties[ITEM_TYPE]])
        show_explorer_and_search_daily_images(request)

    def zoom_to_extent(self):
        rect = QgsRectangle(self.geom.boundingBox())
        rect.scale(1.05)
        iface.mapCanvas().setExtent(rect)
        iface.mapCanvas().refresh()

    def iconDownloaded(self, reply):
        img = QImage()
        img.loadFromData(reply.readAll())
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio, 
                            Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)

    def show_footprint(self):                
        self.footprint.setToGeometry(self.geom)

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
        dockwidget_instance = PlanetInspectorDockWidget(
            parent=iface.mainWindow())        
        dockwidget_instance.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        iface.addDockWidget(Qt.LeftDockWidgetArea, dockwidget_instance)

        dockwidget_instance.hide()
    return dockwidget_instance

def show_inspector():
    wdgt = _get_widget_instance()
    wdgt.show()

def hide_inspector():
    wdgt = _get_widget_instance()    
    wdgt.hide()

def toggle_inspector():
    wdgt = _get_widget_instance()
    wdgt.setVisible(not wdgt.isVisible())

    
