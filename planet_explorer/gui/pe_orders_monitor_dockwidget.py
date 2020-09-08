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
import iso8601
import shutil
import json
import logging
import requests
import zipfile
import traceback
from functools import partial
from collections import defaultdict

from osgeo import gdal

import analytics

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
    QgsRectangle
)

from qgis.gui import QgsRubberBand

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
    QSize
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
    QAction
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


from .pointcapturemaptool import PointCaptureMapTool

ID = "id"
NAME = "name"
CREATED_ON = "created_on"
PRODUCTS = "products"
ITEM_IDS = "item_ids"
STATE = "state"
DELIVERY = "delivery"
ARCHIVE_TYPE = "archive_type"
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
    os.path.join(plugin_path, 'ui', 'pe_orders_monitor_dockwidget.ui'),
    from_imports=True, import_from=os.path.basename(plugin_path),
    resource_suffix=''
)

class PlanetOrdersMonitorDockWidget(ORDERS_MONITOR_BASE, ORDERS_MONITOR_WIDGET):
    
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

        self.btnRefresh.clicked.connect(self.refresh_list)
        self.chkOnlyDownloadable.toggled.connect(self.check_state_changed)

        self.populate_orders_list()

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
                for quad in json_quads:
                    scenes = self.p_client.get_items_for_quad(mosaicid, quad[ID])
                    for scene in scenes:
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
        return "48fff803-4104-49bc-b913-7467b7a5ffb5"

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

    def show_inspector_panel(self):
        self.tabWidget.setCurrentIndex(1)

    def show_orders_panel(self):
        self.tabWidget.setCurrentIndex(0)

    def check_state_changed(self, checkstate):
        for i in range(self.listOrders.count()):
            item = self.listOrders.item(i)
            if isinstance(item, OrderItem):
                item.setHidden(item.order.state() != "success" and checkstate == Qt.Checked)

    def refresh_list(self):
        self.populate_orders_list()

    @waitcursor
    def populate_orders_list(self):
        orders: Orders = self.p_client.client.get_orders()
        ordersArray = []
        for page in orders.iter():
            ordersArray.extend(page.get().get(Orders.ITEM_KEY))
        self.listOrders.clear()
        for order in ordersArray:
            wrapper = OrderWrapper(order, self.p_client)
            item = OrderItem(wrapper)                
            widget = OrderItemWidget(wrapper, self)
            item.setSizeHint(widget.sizeHint())
            self.listOrders.addItem(item)
            self.listOrders.setItemWidget(item, widget)
            item.setHidden((not item.order.is_zipped() or item.order.state() != "success")
                        and self.chkOnlyDownloadable.isChecked())
        quadorders = quad_orders()
        for order in quadorders:
            item = QuadsOrderItem(order)
            widget = QuadsOrderItemWidget(order, self)
            item.setSizeHint(widget.sizeHint())
            self.listOrders.addItem(item)
            self.listOrders.setItemWidget(item, widget)            

class SceneItem(QListWidgetItem):

    def __init__(self, scene):
        QListWidgetItem.__init__(self)
        self.scene = scene        

class SceneItemWidget(QWidget):

    def __init__(self, scene):
        QWidget.__init__(self)
        self.scene = scene
        self.properties = scene[PROPERTIES]
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

class OrderWrapper():

    def __init__(self, order, p_client):
        self.order = order
        self.p_client = p_client

    def id(self):
        return self.order.get(ID)

    def name(self):
        return self.order.get(NAME)

    def date(self):
        return self.order.get(CREATED_ON)

    def is_zipped(self):
        delivery = self.order.get(DELIVERY)
        if delivery is not None:
            return delivery.get(ARCHIVE_TYPE) == "zip"
        else:
            return False

    def assets_count(self):
        return sum([len(p.get(ITEM_IDS)) for p in self.order.get(PRODUCTS)])

    def state(self):
        return self.order.get(STATE)

    def download_folder(self):
        return os.path.join(orders_download_folder(), "daily", self.id())

    def downloaded(self):        
        return os.path.exists(self.download_folder())

    def locations(self):
        order_detail = self.p_client.client._get(self.order[Order.LINKS_KEY]["_self"]).get_body()        
        links = order_detail.get()[Order.LINKS_KEY]
        results = links[Order.RESULTS_KEY]
        locations = [(r[Order.LOCATION_KEY], r[NAME]) for r in results]
        return locations

class OrderItem(QListWidgetItem):

    def __init__(self, order):
        super().__init__()
        self.order = order       

class OrderItemWidget(QWidget):

    def __init__(self, order, dialog):
        super().__init__()
        self.dialog = dialog
        self.order = order        
        txt = (f'<b>Order {order.name()}<br>({order.date()})</b><br>'
              f'{order.assets_count()} assets - state: {order.state()}')

        label = QLabel(txt)
        if not order.is_zipped():
            label.setStyleSheet("color: gray")
        button = QPushButton('Re-Download' if order.downloaded() else 'Download')   
        button.clicked.connect(self.download)
        button.setEnabled(order.state() == 'success' and order.is_zipped())

        vlayout = QVBoxLayout()
        vlayout.addWidget(button)
        if order.downloaded():
            labelOpenFolder = QLabel("<a href='#'>Open order folder</a>")
            vlayout.addWidget(labelOpenFolder)
            labelOpenFolder.setOpenExternalLinks(False)
            labelOpenFolder.linkActivated.connect(lambda: QDesktopServices.openUrl(
                                    QUrl.fromLocalFile(self.order.download_folder())))

        layout = QHBoxLayout()
        layout.addWidget(label)
        layout.addStretch()
        layout.addLayout(vlayout)

        self.setLayout(layout)

    def download(self):
        for task in QgsApplication.taskManager().activeTasks():
            if isinstance(task, OrderProcessorTask) and task.order.id() == self.order.id():
                iface.messageBar().pushMessage("", "This order is already being downloaded and processed", 
                                    level=Qgis.Warning, duration=5)
                return
        if self.order.downloaded():
            ret = QMessageBox.question(self, "Download order", "This order is already downloaded.\nDownload again?")
            if ret == QMessageBox.No:
                return          

        self.task = OrderProcessorTask(self.order)
        self.task.taskCompleted.connect(self.dialog.refresh_list)
        QgsApplication.taskManager().addTask(self.task)
        QCoreApplication.processEvents()
        iface.messageBar().pushMessage("", "Order download task added to QGIS task manager",                
                            level=Qgis.Info, duration=5)


class QuadsOrderItem(QListWidgetItem):

    def __init__(self, order):
        super().__init__()
        self.order = order       

class QuadsOrderItemWidget(QWidget):

    def __init__(self, order, dialog):
        super().__init__()
        self.dialog = dialog
        self.order = order        

        txt = (f'<b>Order {self.order.name}<br>({self.order.date})</b><br>'
              f'{self.order.description}')
        label = QLabel(txt)

        button = QPushButton('Re-Download' if self.order.downloaded() else 'Download')
        button.clicked.connect(self.download)

        vlayout = QVBoxLayout()
        vlayout.addWidget(button)
        if self.order.downloaded():
            labelOpenFolder = QLabel("<a href='#'>Open order folder</a>")
            vlayout.addWidget(labelOpenFolder)
            labelOpenFolder.setOpenExternalLinks(False)
            labelOpenFolder.linkActivated.connect(lambda: QDesktopServices.openUrl(
                                    QUrl.fromLocalFile(self.order.download_folder())))

        layout = QHBoxLayout()
        layout.addWidget(label)
        layout.addStretch()
        layout.addLayout(vlayout)

        self.setLayout(layout)

    def download(self):
        for task in QgsApplication.taskManager().activeTasks():
            if isinstance(task, QuadsOrderProcessorTask) and task.order.id() == self.order.id():
                iface.messageBar().pushMessage("", "This order is already being downloaded and processed", 
                                    level=Qgis.Warning, duration=5)
                return
        if self.order.downloaded():
            ret = QMessageBox.question(self, "Download order", "This order is already downloaded.\nDownload again?")
            if ret == QMessageBox.No:
                return          

        self.task = QuadsOrderProcessorTask(self.order)
        self.task.taskCompleted.connect(self.dialog.refresh_list)
        QgsApplication.taskManager().addTask(self.task)
        QCoreApplication.processEvents()
        iface.messageBar().pushMessage("", "Order download task added to QGIS task manager",                
                            level=Qgis.Info, duration=5)


dockwidget_instance = None

def _get_widget_instance():
    global dockwidget_instance
    if dockwidget_instance is None:
        dockwidget_instance = PlanetOrdersMonitorDockWidget(
            parent=iface.mainWindow())        
        dockwidget_instance.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        iface.addDockWidget(Qt.LeftDockWidgetArea, dockwidget_instance)

        dockwidget_instance.hide()
    return dockwidget_instance

def show_orders_monitor(refresh=True):
    wdgt = _get_widget_instance()
    if refresh:
        wdgt.refresh_list()
    wdgt.show_orders_panel()
    wdgt.show()

def refresh_orders():
    wdgt = _get_widget_instance()    
    wdgt.refresh_list()

def toggle_orders_monitor():
    wdgt = _get_widget_instance()
    wdgt.show_orders_panel()
    wdgt.setVisible(not wdgt.isVisible())


def show_inspector():
    wdgt = _get_widget_instance()
    wdgt.show_inspector_panel()
    wdgt.show()

def toggle_inspector():
    wdgt = _get_widget_instance()
    wdgt.show_inspector_panel()
    wdgt.setVisible(not wdgt.isVisible())

    
