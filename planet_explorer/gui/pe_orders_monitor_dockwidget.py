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

import json
import logging
import os
from pathlib import Path

import iso8601
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsContrastEnhancement,
    QgsProject,
    QgsRasterLayer,
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
    QWidget,
)

from ..pe_utils import (
    basename_only,
    iface,
    orders_download_folder,
    safe_join,
    user_agent,
)
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
METADATA = "metadata"

EXT_LINK = ":/plugins/planet_explorer/external-link.svg"
FOLDER_ICON = ":/plugins/planet_explorer/file-open.svg"

plugin_path = os.path.split(os.path.dirname(__file__))[0]

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get("PYTHON_LOG_VERBOSE", None)


ORDERS_MONITOR_WIDGET, ORDERS_MONITOR_BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_orders_monitor_dockwidget.ui")
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
        ordersArray = list(self.p_client.client.orders.list_orders(limit=0))
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

        self.listOrders.sortItems(Qt.SortOrder.DescendingOrder)


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

    def metadata(self):
        return self.order.get(METADATA)

    def download_folder(self):
        return os.path.join(orders_download_folder(), "daily", self.id())

    def downloaded(self):
        return os.path.exists(self.download_folder())

    async def _alocations(self):
        order_id = self.order["id"]
        order_detail = await self._p_client.orders_client.get_order(order_id)

        results = order_detail.get("_links", {}).get("results", [])
        locations = [(f"{r['location']}&ua={user_agent()}", r["name"]) for r in results]
        return locations

    def locations(self):
        return self._p_client.runner.run(self._alocations())


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
            f' href="https://www.planet.com/account/#/orders/{order.id()}">'  # noqa
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
                    level=Qgis.MessageLevel.Warning,
                    duration=5,
                )
                return
        if not is_unit_test and self.order.downloaded():
            ret = QMessageBox.question(
                self,
                "Download order",
                "This order is already downloaded.\nDownload again?",
            )
            if ret == QMessageBox.StandardButton.No:
                return

        self.task = OrderProcessorTask(self.order)
        self.task.taskCompleted.connect(self.dialog.refresh_list)
        QgsApplication.taskManager().addTask(self.task)
        QCoreApplication.processEvents()
        iface.messageBar().pushMessage(
            "",
            "Order download task added to QGIS task manager",
            level=Qgis.MessageLevel.Info,
            duration=5,
        )

    def _find_band(self, layer, name, default):
        """Finds the band number associated with the provided name (e.g. 'blue'),
        otherwise returns a default value.

        Args:
            layer (QgsRasterLayer): Raster layer. Both single band and multiband.
            name (str): Band name (e.g. 'blue').
            default (int): Default band number to use.

        Returns:
            int: Band number.
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

        Args:
            layer (QgsRasterLayer): Raster layer. Both single band and multiband.
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
                QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum,
                True,
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
                    QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum,
                    True,
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

    def _get_order_folder(self) -> str | None:
        """Get the order subfolder from the download root.

        Returns:
            str | None: Path to the order folder, or None if not found.
        """
        root = self.order.download_folder()
        for content in os.listdir(root):
            full_path = os.path.join(root, content)
            if os.path.isdir(full_path):
                return full_path
        return None

    def _is_valid_raster(self, json_file: dict) -> bool:
        """Check if a manifest file entry is a valid raster to load.

        Args:
            json_file (dict): File entry from manifest.

        Returns:
            bool: True if the file should be loaded as a raster layer.
        """
        media_type = json_file["media_type"]
        raster_types = ["image/tiff", "application/vnd.lotus-notes"]
        if media_type not in raster_types:
            return False

        annotations = json_file["annotations"]
        asset_type_key = "planet/asset_type"

        if asset_type_key in annotations:
            asset_type = annotations[asset_type_key]
            return not (asset_type.endswith("_udm") or asset_type.endswith("_udm2"))
        else:
            # workaround for composite
            image_path = json_file["path"]
            return image_path.endswith("composite.tif") or image_path.endswith(
                "composite_file_format.ntf"
            )

    def _load_rasters_from_manifest(self, final_path: str) -> bool:
        """Load raster layers from a manifest.json file.

        Args:
            final_path (str): Path to the order folder containing manifest.json.

        Returns:
            bool: True if at least one raster was loaded, False otherwise.
        """
        sanitized_final_path = os.path.abspath(os.path.realpath(final_path))

        try:
            manifest_file_path = safe_join(sanitized_final_path, "manifest.json")
        except ValueError:
            self.qgs_error_message(
                "Cannot add data to map", "Invalid order directory path"
            )
            return False

        if not Path(manifest_file_path).exists():
            self.qgs_error_message("Cannot add data to map", "Manifest file is missing")
            return False

        with open(manifest_file_path) as manifest_file:
            manifest_data = json.load(manifest_file)

        data_found = False
        for json_file in manifest_data["files"]:
            if not self._is_valid_raster(json_file):
                continue
            image_dir = safe_join(sanitized_final_path, json_file["path"])
            if Path(image_dir).exists():
                layer = QgsRasterLayer(image_dir, basename_only(image_dir))
                self.load_layer(layer)
                data_found = True

        if not data_found:
            self.qgs_error_message(
                "Cannot add data to map", "Image layer(s) is missing"
            )
        return data_found

    def add_to_map(self) -> bool:
        """Called when the add to map button is clicked.
        Adds the selected remotely sensed image in the order monitor list to QGIS.
        The data needs to be downloaded.

        Returns:
            bool: True if at least one layer was added, False otherwise.
        """
        final_path = self._get_order_folder()
        if final_path is None:
            self.qgs_error_message("Cannot add data to map", "Order folder not found")
            return False
        return self._load_rasters_from_manifest(final_path)

    def qgs_error_message(self, error_title="Error", error_desciption=""):
        """Displays an error message on the QGIS message bar.
        A buttons is included which will open a message box.

        Args:
            error_title (str): Error message title.
            error_desciption (str): Error message description.
        """
        message_bar = iface.messageBar()
        message_bar.pushInfo(error_title, message=error_desciption)


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
                    level=Qgis.MessageLevel.Warning,
                    duration=5,
                )
                return
        if not is_unit_test and self.order.downloaded():
            ret = QMessageBox.question(
                self,
                "Download order",
                "This order is already downloaded.\nDownload again?",
            )
            if ret == QMessageBox.StandardButton.No:
                return

        self.task = QuadsOrderProcessorTask(self.order)
        self.task.taskCompleted.connect(self.dialog.refresh_list)
        QgsApplication.taskManager().addTask(self.task)
        QCoreApplication.processEvents()
        iface.messageBar().pushMessage(
            "",
            "Order download task added to QGIS task manager",
            level=Qgis.MessageLevel.Info,
            duration=5,
        )


dockwidget_instance = None


def _get_widget_instance():
    global dockwidget_instance
    if dockwidget_instance is None:
        if not PlanetClient.getInstance().has_api_key():
            return None
        dockwidget_instance = PlanetOrdersMonitorDockWidget(parent=iface.mainWindow())
        dockwidget_instance.setObjectName("PlanetOrdersMonitorDockWidget")
        dockwidget_instance.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        iface.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dockwidget_instance)

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
