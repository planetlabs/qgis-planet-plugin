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
    QgsMapTool
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
    pyqtSignal,
    QObject
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

from planet.api.models import (
    Mosaics,
    MosaicQuads
)

from ..planet_api.p_quad_orders import (
    quad_orders
)

from ..planet_api.p_order_tasks import (
    QuadsOrderProcessorTask,
    OrderProcessorTask
)

from ..pe_utils import (
    qgsgeometry_from_geojson,
    PLANET_COLOR,
    add_menu_section_action
)

plugin_path = os.path.split(os.path.dirname(__file__))[0]

TASKING_ICON = QIcon(os.path.join(plugin_path, "resources", "tasking.png"))

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

WIDGET, BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_tasking_dockwidget.ui'),
    from_imports=True, import_from=os.path.basename(plugin_path),
    resource_suffix=''
)

class AOICaptureMapTool(QgsMapTool):
    
    aoi_captured = pyqtSignal()
    aoi_moved = pyqtSignal(QgsRectangle)

    def __init__(self, canvas):
        QgsMapTool.__init__(self, canvas)

        self.canvas = canvas
        self.cursor = Qt.CrossCursor

    def activate(self):
        self.canvas.setCursor(self.cursor)

    def canvasReleaseEvent(self, event):
        self.aoi_captured.emit()

    def canvasMoveEvent(self, event):
        pt = event.mapPoint()
        transform = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:3857"),
            QgsProject.instance()
        )
        pt3857 = transform.transform(pt)        
        SIZE = 5000
        rect3857 = QgsRectangle(pt3857.x() - SIZE / 2, pt3857.y() - SIZE / 2,
                            pt3857.x() + SIZE / 2, pt3857.y() + SIZE / 2)
        rect = transform.transform(rect3857, QgsCoordinateTransform.ReverseTransform)
        self.aoi_moved.emit(rect)


class TaskingDockWidget(BASE, WIDGET):
    
    def __init__(self,
                 parent=None,
                 ):
        super().__init__(parent=parent)

        self.setupUi(self)

        self.rect = None

        self.btnMapTool.setIcon(TASKING_ICON)

        self.footprint = QgsRubberBand(iface.mapCanvas(),
                              QgsWkbTypes.PolygonGeometry)        
        self.footprint.setStrokeColor(PLANET_COLOR)
        self.footprint.setWidth(2)

        self.map_tool = AOICaptureMapTool(iface.mapCanvas())
        self.map_tool.aoi_captured.connect(self.aoi_captured)
        self.map_tool.aoi_moved.connect(self.aoi_moved)
        self.btnMapTool.toggled.connect(self._set_map_tool)
        iface.mapCanvas().mapToolSet.connect(self._map_tool_set)

    def aoi_moved(self, rect):
        self.rect = rect
        geom = QgsGeometry.fromRect(rect)
        self.footprint.setToGeometry(geom)

    def aoi_captured(self):
        self._set_map_tool(False)
        transform = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance()
        )
        rect4326 = transform.transform(self.rect)
        self.textBrowser.setHtml(f"""<ul>
                                    <li>xmin: {rect4326.xMinimum()}</li>
                                    <li>xmax: {rect4326.xMaximum()}</li>
                                    <li>ymin: {rect4326.yMinimum()}</li>
                                    <li>ymax: {rect4326.yMaximum()}</li>
                                    </ul>""")

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
            self.footprint.reset(QgsWkbTypes.PolygonGeometry)          

dockwidget_instance = None

def _get_widget_instance():
    global dockwidget_instance
    if dockwidget_instance is None:
        if not PlanetClient.getInstance().has_api_key():
            return None
        dockwidget_instance = TaskingDockWidget(
            parent=iface.mainWindow())        
        dockwidget_instance.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        iface.addDockWidget(Qt.LeftDockWidgetArea, dockwidget_instance)

        dockwidget_instance.hide()
    return dockwidget_instance

def show_tasking_widget():
    wdgt = _get_widget_instance()
    if wdgt is not None:
        wdgt.show()

def hide_tasking_widget():
    wdgt = _get_widget_instance()    
    if wdgt is not None:
        wdgt.hide()

def toggle_tasking_widget():
    wdgt = _get_widget_instance()
    wdgt.setVisible(not wdgt.isVisible())

def remove_tasking_widget():
    if dockwidget_instance is not None:
        iface.removeDockWidget(dockwidget_instance)