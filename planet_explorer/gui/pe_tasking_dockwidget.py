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

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsWkbTypes,
)
from qgis.gui import QgsMapTool, QgsRubberBand

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtWidgets import QDialog, QTextBrowser, QVBoxLayout

from ..pe_analytics import analytics_track
from ..pe_utils import PLANET_COLOR, open_link_with_browser, iface
from ..planet_api import PlanetClient

plugin_path = os.path.split(os.path.dirname(__file__))[0]

TASKING_ICON = QIcon(os.path.join(plugin_path, "resources", "tasking.png"))
SVG_ICON = os.path.join(plugin_path, "resources", "pin.svg")

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get("PYTHON_LOG_VERBOSE", None)

WIDGET, BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_tasking_dockwidget.ui"),
    from_imports=True,
    import_from=os.path.basename(plugin_path),
    resource_suffix="",
)


class AOICaptureMapTool(QgsMapTool):

    aoi_captured = pyqtSignal(QgsRectangle, QgsPointXY)

    def __init__(self, canvas):
        QgsMapTool.__init__(self, canvas)

        self.canvas = canvas
        self.cursor = Qt.CrossCursor

    def activate(self):
        self.canvas.setCursor(self.cursor)

    def canvasReleaseEvent(self, event):
        pt = event.mapPoint()
        transform3857 = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:3857"),
            QgsProject.instance(),
        )
        transform4326 = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance(),
        )
        pt4326 = transform4326.transform(pt)
        pt3857 = transform3857.transform(pt)
        SIZE = 5000
        rect3857 = QgsRectangle(
            pt3857.x() - SIZE / 2,
            pt3857.y() - SIZE / 2,
            pt3857.x() + SIZE / 2,
            pt3857.y() + SIZE / 2,
        )
        rect = transform3857.transform(
            rect3857, QgsCoordinateTransform.ReverseTransform
        )
        self.aoi_captured.emit(rect, pt4326)


class WarningDialog(QDialog):
    def __init__(self, pt):
        super().__init__(iface.mainWindow())
        self.pt = pt
        layout = QVBoxLayout()
        textbrowser = QTextBrowser()
        textbrowser.setOpenLinks(False)
        textbrowser.setOpenExternalLinks(False)
        textbrowser.anchorClicked.connect(self._link_clicked)
        url = (
            "https://learn.planet.com/sample-skysat.html?utm_source=defense-and-intelligence&amp;"
            "amp;utm_medium=website&amp;amp;utm_campaign=skysat-sample-imagery&amp;amp;"
            "utm_content=skysat-sample-imagery"
        )
        text = f"""<p><strong>Complete your high resolution imagery order</strong></p>
                <p><br/>Your custom high resolution imagery order can be completed using
                Planet&rsquo;s Tasking Dashboard. The dashboard allows you to place an order
                to task our SkySat satellite and get high-resolution imagery for your area
                and time of interest.</p>
                <p>If you have not yet purchased the ability to order high-resolution imagery,
                you may download samples<a href="{url}"> here</a>
                and contact our sales team <a href="https://www.planet.com/contact-sales/">
                here</a>.</p>
                <p>&nbsp;</p>
                <p"><a href="dashboard">Take me to the Tasking Dashboard</a>&nbsp;</p>"""
        textbrowser.setHtml(text)
        layout.addWidget(textbrowser)
        self.setLayout(layout)
        self.setFixedSize(600, 400)

    def _link_clicked(self, url):
        if url.toString() == "dashboard":
            analytics_track("skysat_task_created")
            url = f"https://www.planet.com/tasking/orders/new/#/geometry/{self.pt.asWkt()}"
            open_link_with_browser(url)
            self.close()
        else:
            open_link_with_browser(url.toString())


class TaskingDockWidget(BASE, WIDGET):
    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent=parent)

        self.setupUi(self)

        self.rect = None
        self.prev_map_tool = None

        self.btnMapTool.setIcon(TASKING_ICON)
        self.btnMapTool.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self.footprint = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
        self.footprint.setStrokeColor(PLANET_COLOR)
        self.footprint.setFillColor(QColor(204, 235, 239, 100))
        self.footprint.setWidth(2)
        self.marker = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PointGeometry)
        self.marker.setIcon(QgsRubberBand.ICON_SVG)
        self.marker.setSvgIcon(SVG_ICON, QPoint(-15, -30))

        self.map_tool = AOICaptureMapTool(iface.mapCanvas())
        self.map_tool.aoi_captured.connect(self.aoi_captured)
        self.btnMapTool.toggled.connect(self._set_map_tool)
        iface.mapCanvas().mapToolSet.connect(self._map_tool_set)

        self.textBrowserPoint.setHtml("No point selected")
        self.btnOpenDashboard.setEnabled(False)

        self.btnOpenDashboard.clicked.connect(self._open_tasking_dashboard)
        self.btnCancel.clicked.connect(self.cancel_clicked)

        self.visibilityChanged.connect(self.visibility_changed)

        self.textBrowserPoint.viewport().setAutoFillBackground(False)

    def aoi_captured(self, rect, pt):
        self.pt = pt
        self.rect = rect
        self.footprint.setToGeometry(QgsGeometry.fromRect(rect))
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().crs(),
            QgsProject.instance(),
        )
        transformed = transform.transform(pt)
        self.marker.setToGeometry(QgsGeometry.fromPointXY(transformed))
        self._set_map_tool(False)
        text = f"""
                <p><b>Selected Point Coordinates</b></p>
                <p align="center">Latitude : {pt.x():.4f}</p>
                <p align="center">Longitude : {pt.y():.4f}</p>
                """
        self.textBrowserPoint.setHtml(text)
        self.btnCancel.setEnabled(True)
        self.btnOpenDashboard.setEnabled(True)

    def cancel_clicked(self):
        self.footprint.reset(QgsWkbTypes.PolygonGeometry)
        self.marker.reset(QgsWkbTypes.PointGeometry)
        self.btnOpenDashboard.setEnabled(False)
        self.textBrowserPoint.setHtml("")
        self.btnCancel.setEnabled(False)
        self._set_map_tool(False)

    def _set_map_tool(self, checked):
        if checked:
            self.prev_map_tool = iface.mapCanvas().mapTool()
            iface.mapCanvas().setMapTool(self.map_tool)
        else:
            if self.prev_map_tool is not None:
                iface.mapCanvas().setMapTool(self.prev_map_tool)

    def _map_tool_set(self, new, old):
        if new != self.map_tool:
            self.btnMapTool.blockSignals(True)
            self.btnMapTool.setChecked(False)
            self.btnMapTool.blockSignals(False)

    def visibility_changed(self, visible):
        if not visible:
            self.cancel_clicked()

    def _open_tasking_dashboard(self):
        dialog = WarningDialog(self.pt)
        dialog.exec()


dockwidget_instance = None


def _get_widget_instance():
    global dockwidget_instance
    if dockwidget_instance is None:
        if not PlanetClient.getInstance().has_api_key():
            return None
        dockwidget_instance = TaskingDockWidget(parent=iface.mainWindow())
        dockwidget_instance.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )

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
    if wdgt is not None:
        wdgt.setVisible(not wdgt.isVisible())


def remove_tasking_widget():
    if dockwidget_instance is not None:
        iface.removeDockWidget(dockwidget_instance)
