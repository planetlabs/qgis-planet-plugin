import os
import math
import json
import iso8601

from collections import defaultdict

from PyQt5.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QApplication,
    QCheckBox,
    QFrame,
    QToolButton,
    QAction,
    QMenu
)

from PyQt5.QtGui import (
    QPixmap,
    QIcon,
    QImage,
    QCursor,
    QPalette,
    QColor,
)

from PyQt5.QtNetwork import (
    QNetworkAccessManager,
    QNetworkRequest
)

from PyQt5 import QtCore

from PyQt5.QtCore import (
    QUrl,
    Qt,
    pyqtSignal,
    QCoreApplication,
    QThread,
    QObject,
    QSize,
    QEvent
)

from planet.api.models import (
    Mosaics,
    MosaicQuads
)

from planet_explorer.pe_utils import (
    ITEM_BACKGROUND_COLOR
)

from qgis.core import (
    QgsRasterLayer,
    QgsProject,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsWkbTypes,
    QgsGeometry,
    QgsDistanceArea,
    QgsRectangle,
    QgsUnitTypes
)

from qgis.gui import(
    QgsRubberBand
)

from qgis.utils import iface
from qgis.PyQt import uic

from ..planet_api import (
    PlanetClient
)

from ..planet_api.quad_orders import (
    create_quad_order_from_quads
)

from ..planet_api.p_node import (
    PLACEHOLDER_THUMB
)

from .pe_filters import (
    PlanetMainFilters
)

from ..pe_utils import (
    QUADS_AOI_COLOR,
    QUADS_AOI_BODY_COLOR,
    NAME,
    LINKS,
    TILES,
    FIRST_ACQUIRED,    
    ONEMONTH,
    THREEMONTHS,
    WEEK,
    INTERVAL,
    qgsrectangle_for_canvas_from_4326_bbox_coords,
    add_xyz,
    add_mosaics_to_qgis_project,
    mosaic_title,
    date_interval_from_mosaics,
    add_menu_section_action
)

from .pe_gui_utils import (
    waitcursor
)

from .pe_orders_monitor_dockwidget import (
    show_orders_monitor,
    refresh_orders
)

from .extended_combobox import ExtendedComboBox

ID = "id"
THUMBNAIL = "thumbnail"
PERCENT_COVERED = "percent_covered"
BBOX = "bbox"

QUADS_PER_PAGE = 50

MAX_QUADS_TO_DOWNLOAD = 100

class QuadsTreeWidget(QTreeWidget):

    quadsSelectionChanged = pyqtSignal()

    def __init__(self):
        QTreeWidget.__init__(self, None)
        self.setColumnCount(1)
        self.header().hide()        
        self.setAutoScroll(True)
        self.setMouseTracking(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(self.NoSelection)
        self.widgets = {}

    
    def quad_widgets(self):
        all_widgets = []
        for widgets in self.widgets.values():
            all_widgets.extend(widgets)
        return all_widgets

    def clear(self):
        for w in self.quad_widgets():
            w.remove_footprint()
        self.widgets = {}
        super().clear()

    def show_footprints(self):        
        for w in self.quad_widgets():
            w.show_footprint()

    def hide_footprints(self):        
        for w in self.quad_widgets():
            w.hide_footprint()    

    def quads_count(self):
        return len(self.quad_widgets())

    def selected_quads(self):
        selected = []
        for widgets in self.widgets.values():
            selected.extend([w.quad for w in widgets if w.isSelected()])
        return selected

    def selected_quads_classified(self):
        selected = {}
        for mosaic, widgets in self.widgets.items():
            selected[mosaic] = [w.quad for w in widgets if w.isSelected()]
        return selected

    def setAllChecked(self, checked):
        for w in self.quad_widgets():
            w.setChecked(checked)

    def populate(self, mosaics, quads):
        self.clear()
        for mosaic, mosaicquads in zip(mosaics, quads):
            item = BasemapTreeItem(mosaic)            
            self.addTopLevelItem(item)
            widgets = []
            for quad in mosaicquads:
                subitem = QuadTreeItem(quad)
                item.addChild(subitem)
                widget = QuadItemWidget(quad)
                self.setItemWidget(subitem, 0, widget)
                subitem.setSizeHint(0, widget.sizeHint())
                widget.quadSelected.connect(self._quad_selection_changed)
                widgets.append(widget)
            self.widgets[mosaic.get(NAME)] = widgets
            item.update_name()

    def _quad_selection_changed(self):
        self.quadsSelectionChanged.emit()
        for i in range(self.topLevelItemCount()):
            self.topLevelItem(i).update_name()

class BasemapTreeItem(QTreeWidgetItem):

    def __init__(self, mosaic):
        QTreeWidgetItem.__init__(self)
        self.mosaic = mosaic
        font = self.font(0)
        font.setBold(True)
        self.setFont(0, font)
        self.update_name()

    def update_name(self):
        selected = 0
        total = self.childCount()
        for i in range(total):
            if self.treeWidget().itemWidget(self.child(i), 0).isSelected():
                selected += 1
        self.setText(0, f"{mosaic_title(self.mosaic)} - {selected} of {total} selected")

class QuadTreeItem(QTreeWidgetItem):

    def __init__(self, quad):
        QTreeWidgetItem.__init__(self)
        self.quad = quad

class QuadItemWidget(QFrame):

    quadSelected = pyqtSignal()

    def __init__(self, quad):
        QWidget.__init__(self)
        self.setMouseTracking(True)
        self.quad = quad
        self.nameLabel = QLabel(f'<b>{quad[ID]}</b><br><span style="color:grey;">'
                            f'{quad[PERCENT_COVERED]} % covered</span>')
        self.iconLabel = QLabel()
        pixmap = QPixmap(PLACEHOLDER_THUMB, 'SVG')
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                            QtCore.Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.checkBox = QCheckBox("")
        self.checkBox.stateChanged.connect(self.checkBoxstateChanged)
        layout = QHBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.checkBox)
        vlayout = QVBoxLayout()
        vlayout.setMargin(0)
        vlayout.addWidget(self.iconLabel)
        self.iconWidget = QWidget()
        self.iconWidget.setFixedSize(48, 48)
        self.iconWidget.setLayout(vlayout)
        layout.addWidget(self.iconWidget)        
        layout.addWidget(self.nameLabel)
        layout.addStretch()
        self.setLayout(layout)
        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self.iconDownloaded)
        self.nam.get(QNetworkRequest(QUrl(quad[LINKS][THUMBNAIL])))
        self.footprint = QgsRubberBand(iface.mapCanvas(),
                              QgsWkbTypes.PolygonGeometry)        
        self.footprint.setFillColor(QUADS_AOI_COLOR)
        self.footprint.setStrokeColor(QUADS_AOI_COLOR)
        self.footprint.setWidth(2)

        self.footprintfill = QgsRubberBand(iface.mapCanvas(),
                              QgsWkbTypes.PolygonGeometry)        
        self.footprintfill.setFillColor(QUADS_AOI_BODY_COLOR)        
        self.footprintfill.setWidth(0)

        self.update_footprint_brush()
        self.hide_solid_interior()
        self.show_footprint()

        self.setStyleSheet("QuadItemWidget{border: 2px solid transparent;}")

    def checkBoxstateChanged(self):
        self.update_footprint_brush()
        self.quadSelected.emit()        

    def show_footprint(self):
        coords = self.quad[BBOX]
        extent = qgsrectangle_for_canvas_from_4326_bbox_coords(coords)      
        self.geom = QgsGeometry.fromRect(extent)        
        self.footprint.setToGeometry(self.geom)
        self.footprintfill.setToGeometry(self.geom)

    def hide_footprint(self):
        self.footprint.reset(QgsWkbTypes.PolygonGeometry)
        self.footprintfill.reset(QgsWkbTypes.PolygonGeometry)

    def show_solid_interior(self):                        
        self.footprintfill.setBrushStyle(Qt.SolidPattern)        
        self.footprintfill.updateCanvas()

    def hide_solid_interior(self):
        self.footprintfill.setBrushStyle(Qt.NoBrush)
        self.footprintfill.updateCanvas()
    
    def update_footprint_brush(self):
        self.footprint.setBrushStyle(Qt.CrossPattern if self.checkBox.isChecked() else Qt.NoBrush)
        self.footprint.updateCanvas()

    def remove_footprint(self):
        iface.mapCanvas().scene().removeItem(self.footprint)
        iface.mapCanvas().scene().removeItem(self.footprintfill)
        
    def iconDownloaded(self, reply):
        img = QImage()
        img.loadFromData(reply.readAll())
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                            QtCore.Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.iconLabel.setStyleSheet("")

    def isSelected(self):
        return self.checkBox.isChecked()

    def setChecked(self, checked):
        self.checkBox.setChecked(checked)

    def enterEvent(self, event):
        self.setStyleSheet("QuadItemWidget{border: 2px solid rgb(157, 165, 0);}")
        self.show_solid_interior()

    def leaveEvent(self, event):
        self.setStyleSheet("QuadItemWidget{border: 2px solid transparent;}")
        self.hide_solid_interior()