# -*- coding: utf-8 -*-
"""
***************************************************************************
    order_tasks.py
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
import os
import shutil
import traceback
import zipfile
from collections import defaultdict

import requests
from osgeo import gdal

from qgis.core import (
    Qgis,
    QgsMessageLog,
    QgsProject,
    QgsRasterLayer,
    QgsTask,
    QgsContrastEnhancement,
)

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QPushButton

from ..pe_utils import QGIS_LOG_SECTION_NAME, iface


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
            zip_locations = [
                (url, path) for url, path in locations if path.lower().endswith("zip")
            ]
            for url, path in zip_locations:
                local_filename = os.path.basename(path)
                local_fullpath = os.path.join(download_folder, local_filename)
                self.filenames.append(local_fullpath)
                r = requests.get(url, stream=True)
                file_size = r.headers.get("content-length") or 0
                file_size = int(file_size)
                percentage_per_chunk = (100.0 / len(zip_locations)) / (
                    file_size / chunk_size
                )
                progress = 0
                with open(local_fullpath, "wb") as f:
                    for chunk in r.iter_content(chunk_size):
                        f.write(chunk)
                        progress += percentage_per_chunk
                        self.setProgress(progress)
                        if self.isCanceled():
                            return False

            self.process_download()

            return True
        except Exception:
            self.exception = traceback.format_exc()
            return False

    def process_download(self):
        self.msg = []
        for filename in self.filenames:
            output_folder = os.path.splitext(filename)[0]
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)
            with zipfile.ZipFile(filename, "r") as z:
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
                images.append(
                    (
                        os.path.join(base_folder, img["path"]),
                        img["annotations"]["planet/item_type"],
                    )
                )
        return images

    def finished(self, result):
        if result:
            layers = []
            for filename, image_type in self.images:
                if filename.endswith("_udm.tif") or filename.endswith("_udm2.tif"):
                    # Skips all udm rasters
                    continue
                layers.append(QgsRasterLayer(filename, os.path.basename(filename)))
            validity = [lay.isValid() for lay in layers]
            if False in validity:
                widget = iface.messageBar().createMessage(
                    "Planet Explorer",
                    f"Order '{self.order.name()}' correctly downloaded ",
                )
                button = QPushButton(widget)
                button.setText("Open order folder")
                button.clicked.connect(
                    lambda: QDesktopServices.openUrl(
                        QUrl.fromLocalFile(self.order.download_folder())
                    )
                )
                widget.layout().addWidget(button)
                iface.messageBar().pushWidget(widget, level=Qgis.Success)
            else:
                iface.messageBar().pushMessage(
                    "Planet Explorer",
                    f"Order '{self.order.name()}' correctly downloaded and processed",
                    level=Qgis.Success,
                    duration=5,
                )
        elif self.exception is not None:
            QgsMessageLog.logMessage(
                f"Order '{self.order.name()}' could not be"
                f" downloaded.\n{self.exception}",
                QGIS_LOG_SECTION_NAME,
                Qgis.Warning,
            )
            iface.messageBar().pushMessage(
                "Planet Explorer",
                f"Order '{self.order.name()}' could not be downloaded. See log for"
                " details",
                level=Qgis.Warning,
                duration=5,
            )


class QuadsOrderProcessorTask(QgsTask):
    def __init__(self, order):
        super().__init__(f"Processing order {order.name}", QgsTask.CanCancel)
        self.exception = None
        self.order = order
        self.filenames = defaultdict(list)

    def run(self):
        try:
            chunk_size = 1024
            locations = self.order.locations()
            download_folder = self.order.download_folder()
            if os.path.exists(download_folder):
                shutil.rmtree(download_folder)
            os.makedirs(download_folder)
            i = 0
            total = sum([len(x) for x in locations.values()])
            for mosaic, files in locations.items():
                if files:
                    folder = os.path.join(download_folder, mosaic)
                    os.makedirs(folder, exist_ok=True)
                    for url, path in files:
                        local_filename = os.path.basename(path) + ".tif"
                        local_fullpath = os.path.join(
                            download_folder, mosaic, local_filename
                        )
                        self.filenames[mosaic].append(local_fullpath)
                        r = requests.get(url, stream=True)
                        with open(local_fullpath, "wb") as f:
                            for chunk in r.iter_content(chunk_size):
                                f.write(chunk)
                        i += 1
                        self.setProgress(i * 100 / total)
                        if self.isCanceled():
                            return False

            return True
        except Exception:
            self.exception = traceback.format_exc()
            return False

    def finished(self, result):
        if result:
            layers = {}
            valid = True
            for mosaic, files in self.filenames.items():
                mosaiclayers = []
                for filename in files:
                    mosaiclayers.append(
                        QgsRasterLayer(filename, os.path.basename(filename), "gdal")
                    )
                layers[mosaic] = mosaiclayers
                valid = valid and (False not in [lay.isValid() for lay in mosaiclayers])
            if not valid:
                widget = iface.messageBar().createMessage(
                    "Planet Explorer",
                    f"Order '{self.order.name}' correctly downloaded ",
                )
                button = QPushButton(widget)
                button.setText("Open order folder")
                button.clicked.connect(
                    lambda: QDesktopServices.openUrl(
                        QUrl.fromLocalFile(self.order.download_folder())
                    )
                )
                widget.layout().addWidget(button)
                iface.messageBar().pushWidget(widget, level=Qgis.Success)
            else:
                if self.order.load_as_virtual:
                    for mosaic, files in self.filenames.items():
                        vrtpath = os.path.join(
                            self.order.download_folder(), mosaic, f"{mosaic}.vrt"
                        )
                        gdal.BuildVRT(vrtpath, files)
                        layer = QgsRasterLayer(vrtpath, mosaic, "gdal")
                        QgsProject.instance().addMapLayer(layer)
                else:
                    for mosaic, mosaiclayers in layers.items():
                        for layer in mosaiclayers:
                            QgsProject.instance().addMapLayer(layer)
                        # TODO create groups
                iface.messageBar().pushMessage(
                    "Planet Explorer",
                    f"Order '{self.order.name}' correctly downloaded and processed",
                    level=Qgis.Success,
                    duration=5,
                )
        elif self.exception is not None:
            QgsMessageLog.logMessage(
                f"Order '{self.order.name}' could not be downloaded.\n{self.exception}",
                QGIS_LOG_SECTION_NAME,
                Qgis.Warning,
            )
            iface.messageBar().pushMessage(
                "Planet Explorer",
                f"Order '{self.order.name}' could not be downloaded. See log for"
                " details",
                level=Qgis.Warning,
                duration=5,
            )
