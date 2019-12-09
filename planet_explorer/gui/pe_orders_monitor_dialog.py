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
import shutil
import json
import logging
import requests
import zipfile
import traceback
from functools import partial

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
    QgsProject
)

# noinspection PyPackageRequirements
from qgis.utils import (
    iface
)

# noinspection PyPackageRequirements
from qgis.gui import (
    QgsMessageBar
)

# noinspection PyPackageRequirements
from qgis.PyQt import uic

# noinspection PyPackageRequirements
from qgis.PyQt.QtCore import (
    Qt,
    QCoreApplication,
    QUrl
)

# noinspection PyPackageRequirements
from qgis.PyQt.QtGui import (
    QCursor,
    QDesktopServices
)

# noinspection PyPackageRequirements
from qgis.PyQt.QtWidgets import (
    QLabel,
    QPushButton,
    QHBoxLayout,
    QWidget,
    QListWidgetItem,
    QApplication,
    QMessageBox,
    QSizePolicy
)

from planet_explorer.planet_api.p_network import (
    PlanetCallbackWatcher,
    dispatch_callback,
    RESPONSE_TIMEOUT
)

from ..pe_utils import (
    QGIS_LOG_SECTION_NAME,
    resource_file,
    orders_download_folder,
    is_segments_write_key_valid
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

plugin_path = os.path.split(os.path.dirname(__file__))[0]

ORDERS_MONITOR_WIDGET, ORDERS_MONITOR_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_orders_monitor_dialog.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)

class PlanetOrdersMonitorDialog(ORDERS_MONITOR_BASE, ORDERS_MONITOR_WIDGET):
    
    def __init__(self,
                 p_client,
                 parent=None,
                 ):
        super().__init__(parent=parent)
        self._p_client = p_client

        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar)

        self.btnRefresh.clicked.connect(self.populate_orders_list)
        self.chkOnlyDownloadable.stateChanged.connect(self.check_state_changed)

        self.populate_orders_list()

    def check_state_changed(self, checkstate):
        for i in range(self.listOrders.count()):
            item = self.listOrders.item(i)
            item.setHidden(item.order.state() != "success" and checkstate == Qt.Checked)

    def populate_orders_list(self):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            orders: Orders = self._p_client.client.get_orders()
            ordersArray = []
            for page in orders.iter():
                ordersArray.extend(page.get().get(Orders.ITEM_KEY))
            self.listOrders.clear()
            for order in ordersArray:
                wrapper = OrderWrapper(order, self._p_client)
                item = OrderItem(wrapper)                
                widget = OrderItemWidget(wrapper, self)
                item.setSizeHint(widget.sizeHint())
                self.listOrders.addItem(item)
                self.listOrders.setItemWidget(item, widget)
                item.setHidden((not item.order.is_zipped() or item.order.state() != "success")
                            and self.chkOnlyDownloadable.isChecked())
        finally:
            QApplication.restoreOverrideCursor()

ID = "id"
NAME = "name"
CREATED_ON = "created_on"
PRODUCTS = "products"
ITEM_IDS = "item_ids"
STATE = "state"
DELIVERY = "delivery"
ARCHIVE_TYPE = "archive_type"

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
        return os.path.join(orders_download_folder(), self.id())

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
        button = QPushButton('Download')
        button.clicked.connect(self.download)
        button.setEnabled(order.state() == 'success' and order.is_zipped())

        layout = QHBoxLayout()
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(button)

        self.setLayout(layout)

    def download(self):
        for task in QgsApplication.taskManager().activeTasks():
            if isinstance(task, OrderProcessorTask) and task.order.id() == self.order.id():
                self.dialog.bar.pushMessage("", "This order is already being downloaded and processed", 
                                    level=Qgis.Warning, duration=5)
                return
        if self.order.downloaded():
            ret = QMessageBox.question(self, "Download order", "This order is already downloaded.\nDownload again?")
            if ret == QMessageBox.No:
                return          

        self.task = OrderProcessorTask(self.order)
        QgsApplication.taskManager().addTask(self.task)
        QCoreApplication.processEvents()
        self.dialog.bar.pushMessage("", "Order download task added to QGIS task manager",                
                            level=Qgis.Info, duration=5)


class OrderProcessorTask(QgsTask):
    def __init__(self, order):
        super().__init__(f"Processing order {order.name()}", QgsTask.CanCancel)
        self.exception = None
        self.order = order
        self.filenames = []        

    def run(self):
        try:
            chunk_size = 1024
            locations = self.order.locations()
            download_folder = self.order.download_folder()
            if os.path.exists(download_folder):
                shutil.rmtree(download_folder)
            os.makedirs(download_folder)
            zip_locations = [(url,path) for url,path in locations if path.lower().endswith("zip")]
            for url, path in zip_locations:
                local_filename = os.path.basename(path)                
                local_fullpath = os.path.join(download_folder, local_filename)
                self.filenames.append(local_fullpath)
                r = requests.get(url, stream=True)
                file_size = r.headers.get('content-length') or 0
                file_size = int(file_size)
                percentage_per_chunk = (100.0 / len(zip_locations)) / (file_size / chunk_size)
                progress = 0
                with open(local_fullpath, 'wb') as f:                
                    for chunk in r.iter_content(chunk_size):
                        f.write(chunk)
                        progress += percentage_per_chunk
                        self.setProgress(progress)
                        if self.isCanceled():
                            return False
            
            self.process_download()

            return True
        except Exception as e:
            self.exception = traceback.format_exc()
            return False

    def process_download(self):
        self.msg = []
        for filename in self.filenames:
            output_folder = os.path.splitext(filename)[0]
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)
            with zipfile.ZipFile(filename, 'r') as z:
                z.extractall(output_folder)
            os.remove(filename)
            manifest_file = os.path.join(output_folder, "manifest.json")
            self.images = self.images_from_manifest(manifest_file)


    def images_from_manifest(self, manifest_file):
        base_folder = os.path.dirname(manifest_file)
        with open(manifest_file) as f:
            manifest = json.load(f)
        images = []
        for img in manifest["files"]:
            if img["media_type"] == "image/tiff":
                images.append((os.path.join(base_folder, img["path"]),
                            img["annotations"]["planet/item_type"]))
        return images


    def finished(self, result):      
        if result:
            layers = []
            for filename, image_type in self.images:
                layers.append((QgsRasterLayer(filename, os.path.basename(filename)), image_type))
            validity = [lay.isValid() for lay, _ in layers]
            if False in validity:
                widget = iface.messageBar().createMessage("Planet Explorer", 
                        f"Order '{self.order.name()}' correctly downloaded ")
                button = QPushButton(widget)
                button.setText("Open order folder")
                button.clicked.connect(lambda: QDesktopServices.openUrl(
                                    QUrl.fromLocalFile(self.order.download_folder()))
                )
                widget.layout().addWidget(button)
                iface.messageBar().pushWidget(widget, level=Qgis.Success)                
            else:
                for layer, image_type in layers:
                    QgsProject.instance().addMapLayer(layer)                   
                iface.messageBar().pushMessage("Planet Explorer", 
                    f"Order '{self.order.name()}' correctly downloaded and processed",
                    level=Qgis.Success, duration=5)
            if is_segments_write_key_valid():
                analytics.track(self.order.p_client.user()["email"], "Order downloaded", self.order.order)
        elif self.exception is not None:
            QgsMessageLog.logMessage(f"Order '{self.order.name()}' could not be downloaded.\n{self.exception}", 
                QGIS_LOG_SECTION_NAME, Qgis.Warning)
            iface.messageBar().pushMessage("Planet Explorer", 
                f"Order '{self.order.name()}' could not be downloaded. See log for details",
                level=Qgis.Warning, duration=5)



