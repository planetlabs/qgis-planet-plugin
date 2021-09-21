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

import iso8601
from planet.api.models import Order, Orders

from qgis.core import Qgis, QgsApplication

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

from ..pe_utils import orders_download_folder, iface
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
        self, parent=None,
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
        locations = [(r[Order.LOCATION_KEY], r[NAME]) for r in results]
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
        button = QPushButton("Re-Download" if order.downloaded() else "Download")
        button.clicked.connect(self.download)
        button.setEnabled(order.state() == "success" and order.is_zipped())

        vlayout = QVBoxLayout()
        vlayout.addWidget(button)
        if order.downloaded():
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

    def download(self):
        for task in QgsApplication.taskManager().activeTasks():
            if (
                isinstance(task, OrderProcessorTask)
                and task.order.id() == self.order.id()
            ):
                iface.messageBar().pushMessage(
                    "",
                    "This order is already being downloaded and processed",
                    level=Qgis.Warning,
                    duration=5,
                )
                return
        if self.order.downloaded():
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

    def download(self):
        for task in QgsApplication.taskManager().activeTasks():
            if (
                isinstance(task, QuadsOrderProcessorTask)
                and task.order.id() == self.order.id()
            ):
                iface.messageBar().pushMessage(
                    "",
                    "This order is already being downloaded and processed",
                    level=Qgis.Warning,
                    duration=5,
                )
                return
        if self.order.downloaded():
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
