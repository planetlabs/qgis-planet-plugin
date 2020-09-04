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
    QgsUnitTypes,
    QgsApplication
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
BBOX = "bbox"
THUMB = "thumb"

COG_ICON = QIcon(':/plugins/planet_explorer/cog.svg')

class BasemapsListWidget(QListWidget):

    basemapsSelectionChanged = pyqtSignal()

    def __init__(self):
        QListWidget.__init__(self, None)
        self.setAutoScroll(True)
        self.setSortingEnabled(True) 
        self.setAlternatingRowColors(True)
        p = self.palette()
        p.setColor(QPalette.Highlight, ITEM_BACKGROUND_COLOR)
        self.setPalette(p)
        self.widgets = []

    def clear(self):
        self.widgets = []
        super().clear()

    def populate(self, mosaics):              
        self.widgets = []
        for mosaic in mosaics[::-1]:                
            item = BasemapListItem(mosaic)
            self.addItem(item)
            widget = BasemapItemWidget(mosaic)
            self.setItemWidget(item, widget)
            width = self.width()
            if self.verticalScrollBar().isVisible():
                width -= self.verticalScrollBar().width()
            widget.setMaximumWidth(width)
            widget.setFixedWidth(width)
            item.setSizeHint(widget.sizeHint())
            widget.basemapSelected.connect(self.basemapsSelectionChanged.emit)
            self.widgets.append(widget)
        
        self.sortItems()

    def resizeEvent(self, evt):
        super().resizeEvent(evt)
        for widget in self.widgets:
            width = self.width()
            if self.verticalScrollBar().isVisible():
                width -= self.verticalScrollBar().width()
            widget.setMaximumWidth(width)
            widget.setFixedWidth(width)

    def selected_mosaics(self):
        return sorted([w.mosaic for w in self.widgets if w.isSelected()], 
                        key=lambda x: x[FIRST_ACQUIRED])

    def setAllChecked(self, checked):
        for w in self.widgets:
            w.setChecked(checked)
        
class BasemapListItem(QListWidgetItem):

    def __init__(self, mosaic):
        QListWidgetItem.__init__(self)
        self.mosaic = mosaic
        self.enabled = TILES in mosaic[LINKS]

    def __lt__(self, other):
        if isinstance(other, BasemapListItem):
            return self.mosaic[FIRST_ACQUIRED] < other.mosaic[FIRST_ACQUIRED]
        else:
            return True        

class BasemapItemWidget(QWidget):

    basemapSelected = pyqtSignal()

    def __init__(self, mosaic):
        QWidget.__init__(self)
        self.mosaic = mosaic
        available = TILES in mosaic[LINKS]
        color = "black" if available else "grey"        
        title = mosaic_title(mosaic)
        self.nameLabel = QLabel(f'<span style="color:{color};"><b>{title}</b></span>'
                            f'<br><span style="color:grey;">{mosaic[NAME]}</span>')        
        self.iconLabel = QLabel()
        self.toolsButton = QLabel()
        self.toolsButton.setPixmap(COG_ICON.pixmap(QSize(18, 18)))
        self.toolsButton.mousePressEvent = self.showContextMenu

        pixmap = QPixmap(PLACEHOLDER_THUMB, 'SVG')
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                            QtCore.Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.checkBox = QCheckBox("")
        self.checkBox.setEnabled(available)
        self.checkBox.stateChanged.connect(self.basemapSelected.emit)
        layout = QHBoxLayout()
        layout.setMargin(2)
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
        layout.addWidget(self.toolsButton)
        layout.addSpacing(10)
        self.setLayout(layout)
        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self.iconDownloaded)
        self.nam.get(QNetworkRequest(QUrl(mosaic[LINKS][THUMB])))
        
    def showContextMenu(self, evt):
        menu = QMenu()
        add_menu_section_action('Current item', menu)
        zoom_act = QAction('Zoom to extent', menu)        
        zoom_act.triggered.connect(self.zoom_to_extent)
        menu.addAction(zoom_act)
        copy_id_act = QAction('Copy ID to clipboard', menu)        
        copy_id_act.triggered.connect(self.copy_id)
        menu.addAction(copy_id_act)
        menu.exec_(self.toolsButton.mapToGlobal(evt.pos()))

    def copy_id(self):
        cb = QgsApplication.clipboard()
        cb.setText(self.mosaic[ID])        

    def zoom_to_extent(self):
        rect = qgsrectangle_for_canvas_from_4326_bbox_coords(self.mosaic[BBOX])
        rect.scale(1.05)
        iface.mapCanvas().setExtent(rect)
        iface.mapCanvas().refresh()

    def iconDownloaded(self, reply):
        img = QImage()
        img.loadFromData(reply.readAll())
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                            QtCore.Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)

    def isSelected(self):
        return self.checkBox.isChecked()

    def setChecked(self, checked):
        self.checkBox.setChecked(checked)
