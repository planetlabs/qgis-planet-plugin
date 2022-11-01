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
import json

import iso8601
from planet.api.models import Order, Orders

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsRasterLayer,
    QgsProject,
    QgsContrastEnhancement
)

from qgis.PyQt import uic

from qgis.PyQt.QtCore import QCoreApplication, Qt, QUrl

from qgis.PyQt.QtGui import QDesktopServices

from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget
)

from ..pe_utils import orders_download_folder, iface, user_agent
from ..planet_api import PlanetClient
from ..planet_api.p_order_tasks import OrderProcessorTask, QuadsOrderProcessorTask
from ..planet_api.p_quad_orders import quad_orders
from .pe_gui_utils import waitcursor

ID = "id"
NAME = "name"
CREATED_ON = "created_on"
PRODUCTS = "products"
ITEM_IDS = "item_ids"
ITEM_TYPE = "item_type"
PRODUCT_BUNDLE = "product_bundle"
STATE = "state"
DELIVERY = "delivery"
ARCHIVE_TYPE = "archive_type"

EXT_LINK = ":/plugins/planet_explorer/external-link.svg"
FOLDER_ICON = ":/plugins/planet_explorer/file-open.svg"

plugin_path = os.path.split(os.path.dirname(__file__))[0]

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get("PYTHON_LOG_VERBOSE", None)


ORDERS_MONITOR_WIDGET, ORDERS_MONITOR_BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_orders_monitor_dockwidget.ui"),
    from_imports=True,
    import_from=os.path.basename(plugin_path),
    resource_suffix="",
)


class PlanetOrdersMonitorDockWidget(ORDERS_MONITOR_BASE, ORDERS_MONITOR_WIDGET):
    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent=parent)
        self.p_client = PlanetClient.getInstance()

        self.setupUi(self)

        self.btnRefresh.clicked.connect(self.refresh_list)
        self.chkOnlyDownloadable.toggled.connect(self.check_state_changed)

        self.populate_orders_list()

    def check_state_changed(self, checkstate):
        for i in range(self.listOrders.count()):
            item = self.listOrders.item(i)
            if isinstance(item, OrderItem):
                item.setHidden(item.order.state() != "success" and checkstate)

    def refresh_list(self):
        self.populate_orders_list()

    @waitcursor
    def populate_orders_list(self):
        orders: Orders = self.p_client.get_orders()
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
            item.setHidden(
                (not item.order.is_zipped() or item.order.state() != "success")
                and self.chkOnlyDownloadable.isChecked()
            )
        quadorders = quad_orders()
        for order in quadorders:
            item = QuadsOrderItem(order)
            widget = QuadsOrderItemWidget(order, self)
            item.setSizeHint(widget.sizeHint())
            self.listOrders.addItem(item)
            self.listOrders.setItemWidget(item, widget)

        self.listOrders.sortItems(Qt.DescendingOrder)


class OrderWrapper:
    def __init__(self, order, p_client):
        self.order = order
        self.p_client = p_client

    def id(self):
        return self.order.get(ID)

    def name(self):
        return self.order.get(NAME)

    def date(self):
        datestring = self.order.get(CREATED_ON)
        return iso8601.parse_date(datestring).date().isoformat()

    def file_format(self):
        # TODO
        return ""

    def item_type(self):
        types = [p.get(ITEM_TYPE) for p in self.order.get(PRODUCTS)]
        return ", ".join(types)

    def assets_ordered(self):
        types = [p.get(PRODUCT_BUNDLE) for p in self.order.get(PRODUCTS)]
        return ", ".join(types)

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
        order_detail = self.p_client._get(
            self.order[Order.LINKS_KEY]["_self"]
        ).get_body()
        links = order_detail.get()[Order.LINKS_KEY]
        results = links[Order.RESULTS_KEY]
        locations = [
            (f"{r[Order.LOCATION_KEY]}&ua={user_agent()}", r[NAME]) for r in results
        ]
        return locations


class BaseWidgetItem(QListWidgetItem):
    def __lt__(self, other):
        try:
            return self.date() < other.date()
        except Exception:
            return QListWidgetItem.__lt__(self, other)


class OrderItem(BaseWidgetItem):
    def __init__(self, order):
        super().__init__()
        self.order = order

    def date(self):
        return self.order.date()


class OrderItemWidget(QWidget):
    def __init__(self, order, dialog):
        super().__init__()
        self.dialog = dialog
        self.order = order
        txt = (
            "<style>h3{margin-bottom: 0px;}</style>"
            f"<b><h3>Order {order.name()}</h3></b>"
            f"<b>Placed on</b>: {order.date()}<br>"
            "<b>Id</b>: <a"
            f' href="https://www.planet.com/account/#/orders/{order.id()}">'
            f"{order.id()}</a><br>"
            f"<b>Imagery source</b>: {order.item_type()}<br>"
            # f'<b>Assets ordered</b>: {order.assets_ordered()}<br>'
            # f'<b>File format</b>: {order.file_format()}<br>'
            f"<b>Asset count</b>: {order.assets_count()}<br>"
        )

        label = QLabel(txt)
        label.setOpenExternalLinks(True)
        if not order.is_zipped():
            label.setStyleSheet("color: gray")
        # Addition space characters added to Download so that it
        # vertically lines-up neatly with the Re-download button
        button = QPushButton("Re-Download" if order.downloaded() else "   Download   ")
        button.clicked.connect(self.download)
        button.setEnabled(order.state() == "success" and order.is_zipped())

        hlayout = QHBoxLayout()
        hlayout.addWidget(button)

        add_to_map_btn = QPushButton("Add to map")
        add_to_map_btn.clicked.connect(self.add_to_map)
        hlayout.addWidget(add_to_map_btn)

        if order.downloaded():
            # Enable the add to map button if the data has been downloaded
            add_to_map_btn.setEnabled(True)

            # Add the open folder location button if the data has been downloaded
            label_open_folder = QLabel("<a href='#'>Open order folder</a>")
            hlayout.addWidget(label_open_folder)
            label_open_folder.setOpenExternalLinks(False)
            label_open_folder.linkActivated.connect(
                lambda: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(self.order.download_folder())
                )
            )
        else:
            # Add to map button will be disabled if the data has not been downloaded
            add_to_map_btn.setEnabled(False)
        hlayout.addStretch(1)  # Spacer

        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addStretch()
        layout.addLayout(hlayout)

        self.setLayout(layout)

    def download(self, is_unit_test=False):
        for task in QgsApplication.taskManager().activeTasks():
            if (
                not is_unit_test
                and isinstance(task, OrderProcessorTask)
                and task.order.id() == self.order.id()
            ):
                iface.messageBar().pushMessage(
                    "",
                    "This order is already being downloaded and processed",
                    level=Qgis.Warning,
                    duration=5,
                )
                return
        if not is_unit_test and self.order.downloaded():
            ret = QMessageBox.question(
                self,
                "Download order",
                "This order is already downloaded.\nDownload again?",
            )
            if ret == QMessageBox.No:
                return

        self.task = OrderProcessorTask(self.order)
        self.task.taskCompleted.connect(self.dialog.refresh_list)
        QgsApplication.taskManager().addTask(self.task)
        QCoreApplication.processEvents()
        iface.messageBar().pushMessage(
            "",
            "Order download task added to QGIS task manager",
            level=Qgis.Info,
            duration=5,
        )

    def _find_band(self, layer, name, default):
        """Finds the band number associated with the provided name (e.g. 'blue'),
        otherwise returns a default value.

        :param layer: Raster layer. Both single band and multiband.
        :type layer: QgsRasterLayer

        :param name: Band name (e.g. 'blue')
        :type name: str

        :param default: Default band number to use
        :type default: int

        :returns: Band number
        "rtype: int
        """
        name = name.lower()
        for i in range(layer.bandCount()):
            if name == layer.bandName(i).lower().split(": ")[-1]:
                return i
        return default

    def load_layer(self, layer):
        """Adds the provided QgsRasterLayer to the QGIS map.
        Rasters with less than 3 bands will be added as
        a grey scale layer, whereas multiband will be added as True colour RGB.

        :param layer: Raster layer. Both single band and multiband.
        :type layer: QgsRasterLayer
        """

        band_cnt = layer.bandCount()
        if band_cnt < 3:

            # These cases will be skipped for now, but removing this 'return'
            # will add singleband layers again
            return

            # Rasters with less than 3 bands will be added as single band
            r = layer.renderer().clone()
            r.setGrayBand(1)

            used_bands = r.usesBands()
            typ = layer.renderer().dataType(1)
            enhancement = QgsContrastEnhancement(typ)
            enhancement.setContrastEnhancementAlgorithm(
                QgsContrastEnhancement.StretchToMinimumMaximum, True
            )
            band_min, band_max = layer.dataProvider().cumulativeCut(
                used_bands[0], 0.02, 0.98, sampleSize=10000
            )
            enhancement.setMinimumValue(band_min)
            enhancement.setMaximumValue(band_max)
            r.setContrastEnhancement(enhancement)

            layer.setRenderer(r)
            QgsProject.instance().addMapLayer(layer)
        else:
            # BGR image for 3 or more bands
            r = layer.renderer().clone()
            r.setBlueBand(self._find_band(layer, "blue", 1))
            r.setGreenBand(self._find_band(layer, "green", 2))
            r.setRedBand(self._find_band(layer, "red", 3))

            used_bands = r.usesBands()
            for b in range(3):
                typ = layer.renderer().dataType(b)
                enhancement = QgsContrastEnhancement(typ)
                enhancement.setContrastEnhancementAlgorithm(
                    QgsContrastEnhancement.StretchToMinimumMaximum, True
                )
                band_min, band_max = layer.dataProvider().cumulativeCut(
                    used_bands[b], 0.02, 0.98, sampleSize=10000
                )
                enhancement.setMinimumValue(band_min)
                enhancement.setMaximumValue(band_max)
                if b == 0:
                    r.setRedContrastEnhancement(enhancement)
                elif b == 1:
                    r.setGreenContrastEnhancement(enhancement)
                elif b == 2:
                    r.setBlueContrastEnhancement(enhancement)

            layer.setRenderer(r)
            QgsProject.instance().addMapLayer(layer)

    def add_to_map(self):
        """Called when the add to map button is clicked.
        Adds the selected remotely sensed image in the order monitor list to QGIS.
        The data needs to be downloaded.
        """

        # Order name is usually "OrderName_" followed by the sensor (e.g. SkySat)
        # For the QGIS plugin the output folder should be "OrderName_QGIS"
        order_name_split = self.order.name().split('_')
        folder_prefix = order_name_split[0]
        #  List which excludes the first and last elements
        order_names = order_name_split[1 :len(order_name_split) - 1]
        for prefix in order_names:
            # Adds each prefix
            folder_prefix = '{}_{}'.format(
                folder_prefix,
                prefix
            )

        manifest_dir = '{}/{}_QGIS/{}'.format(
            self.order.download_folder(),
            folder_prefix,
            'manifest.json'
        )

        if os.path.exists(manifest_dir):
            manifest_file = open(manifest_dir)
            manifest_data = json.load(manifest_file)

            list_files = manifest_data['files']
            for json_file in list_files:
                media_type = json_file['media_type']

                raster_types = [
                    'image/tiff',
                    'application/vnd.lotus-notes'
                ]

                if media_type in raster_types:
                    annotations = json_file['annotations']
                    asset_type = annotations['planet/asset_type']
                    if asset_type.endswith('_udm') or asset_type.endswith('_udm2'):
                        # Skips all 'udm' asset rasters
                        continue

                    image_path = json_file['path']
                    image_dir = '{}/{}_QGIS/{}'.format(
                        self.order.download_folder(),
                        folder_prefix,
                        image_path
                    )

                    if os.path.exists(image_dir):
                        layer = QgsRasterLayer(image_dir, os.path.basename(image_dir))
                        self.load_layer(layer)
                    else:
                        # The raster specified in the manifest.json file is missing
                        self.qgs_error_message(
                            "Cannot add data to map",
                            "Image layer is missing"
                        )
        else:
            # The manifest.json file is missing
            # This file contains information on the downloaded data
            self.qgs_error_message(
                "Cannot add data to map",
                "Manifest file is missing"
            )

    def qgs_error_message(self, error_title='Error', error_desciption=''):
        """Displays an error message on the QGIS message bar.
        A buttons is included which will open a message box.

        :param error_title: Error message title
        :type error_title: str

        :param error_desciption: Error message description
        :type error_desciption: str
        """

        message_bar = iface.messageBar()
        message_bar.pushInfo(
            error_title,
            message=error_desciption
        )


class QuadsOrderItem(BaseWidgetItem):
    def __init__(self, order):
        super().__init__()
        self.order = order

    def date(self):
        return self.order.date


class QuadsOrderItemWidget(QWidget):
    def __init__(self, order, dialog):
        super().__init__()
        self.dialog = dialog
        self.order = order

        datestring = iso8601.parse_date(order.date).date().isoformat()

        txt = (
            "<style>h3{margin-bottom: 0px;}</style>"
            f"<b><h3>Order {order.name}</h3></b>"
            f"<b>Placed on</b>: {datestring}<br>"
            f"<b>Id</b>: {order.id()}<br>"
            f"<b>Quad count</b>: {order.numquads()}<br>"
        )
        label = QLabel(txt)

        button = QPushButton("Re-Download" if self.order.downloaded() else "Download")
        button.clicked.connect(self.download)

        vlayout = QVBoxLayout()
        vlayout.addWidget(button)
        if self.order.downloaded():
            labelOpenFolder = QLabel("<a href='#'>Open order folder</a>")
            vlayout.addWidget(labelOpenFolder)
            labelOpenFolder.setOpenExternalLinks(False)
            labelOpenFolder.linkActivated.connect(
                lambda: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(self.order.download_folder())
                )
            )

        layout = QHBoxLayout()
        layout.addWidget(label)
        layout.addStretch()
        layout.addLayout(vlayout)

        self.setLayout(layout)

    def download(self, is_unit_test=False):
        for task in QgsApplication.taskManager().activeTasks():
            if (
                not is_unit_test
                and isinstance(task, QuadsOrderProcessorTask)
                and task.order.id() == self.order.id()
            ):
                iface.messageBar().pushMessage(
                    "",
                    "This order is already being downloaded and processed",
                    level=Qgis.Warning,
                    duration=5,
                )
                return
        if not is_unit_test and self.order.downloaded():
            ret = QMessageBox.question(
                self,
                "Download order",
                "This order is already downloaded.\nDownload again?",
            )
            if ret == QMessageBox.No:
                return

        self.task = QuadsOrderProcessorTask(self.order)
        self.task.taskCompleted.connect(self.dialog.refresh_list)
        QgsApplication.taskManager().addTask(self.task)
        QCoreApplication.processEvents()
        iface.messageBar().pushMessage(
            "",
            "Order download task added to QGIS task manager",
            level=Qgis.Info,
            duration=5,
        )


dockwidget_instance = None


def _get_widget_instance():
    global dockwidget_instance
    if dockwidget_instance is None:
        if not PlanetClient.getInstance().has_api_key():
            return None
        dockwidget_instance = PlanetOrdersMonitorDockWidget(parent=iface.mainWindow())
        dockwidget_instance.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )

        iface.addDockWidget(Qt.LeftDockWidgetArea, dockwidget_instance)

        dockwidget_instance.hide()
    return dockwidget_instance


def show_orders_monitor(refresh=True):
    wdgt = _get_widget_instance()
    if wdgt is not None:
        if refresh:
            wdgt.refresh_list()
        wdgt.show()


def hide_orders_monitor():
    wdgt = _get_widget_instance()
    if wdgt is not None:
        wdgt.hide()


def refresh_orders():
    wdgt = _get_widget_instance()
    wdgt.refresh_list()


def toggle_orders_monitor():
    wdgt = _get_widget_instance()
    wdgt.setVisible(not wdgt.isVisible())


def remove_orders_monitor():
    if dockwidget_instance is not None:
        iface.removeDockWidget(dockwidget_instance)
