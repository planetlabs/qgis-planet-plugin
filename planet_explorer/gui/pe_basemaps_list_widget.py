# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_basemaps_list_Widget.py
    ---------------------
    Date                 : August 2020
    Author               : Planet Federal
    Copyright            : (C) 2017 Boundless, http://boundlessgeo.com
                         : (C) 2019 Planet Inc, https://planet.com
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
__date__ = 'August 2020'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'


from PyQt5.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QCheckBox,
    QAction,
    QMenu
)

from PyQt5.QtGui import (
    QPixmap,
    QIcon,
    QImage,
    QPalette
)

from PyQt5 import QtCore

from PyQt5.QtCore import (
    pyqtSignal,
    QSize,
    Qt
)

from planet_explorer.pe_utils import (
    ITEM_BACKGROUND_COLOR
)

from qgis.core import (
    QgsApplication
)

from qgis.utils import iface

from ..planet_api import (
    PlanetClient
)

from ..pe_utils import (
    NAME,
    LINKS,
    TILES,
    FIRST_ACQUIRED,
    qgsrectangle_for_canvas_from_4326_bbox_coords,
    mosaic_title,
    add_menu_section_action
)

from .pe_thumbnails import (
    download_thumbnail
)

ID = "id"
BBOX = "bbox"
THUMB = "thumb"

COG_ICON = QIcon(':/plugins/planet_explorer/cog.svg')
PLACEHOLDER_THUMB = ':/plugins/planet_explorer/thumb-placeholder-128.svg'


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
        for mosaic in mosaics:
            available = TILES in mosaic[LINKS]
            if available:
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
        title = mosaic_title(mosaic)
        self.nameLabel = QLabel(f'<span style="color:black;"><b>{title}</b></span>'
                            f'<br><span style="color:grey;">{mosaic[NAME]}</span>')
        self.iconLabel = QLabel()
        self.toolsButton = QLabel()
        self.toolsButton.setPixmap(COG_ICON.pixmap(QSize(18, 18)))
        self.toolsButton.mousePressEvent = self.showContextMenu

        pixmap = QPixmap(PLACEHOLDER_THUMB, 'SVG')
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.checkBox = QCheckBox("")
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

        if THUMB in mosaic[LINKS]:
            download_thumbnail(mosaic[LINKS][THUMB], self)
        else:
            THUMBNAIL_DEFAULT_URL = "https://tiles.planet.com/basemaps/v1/planet-tiles/{name}/thumb?api_key={apikey}"
            download_thumbnail(THUMBNAIL_DEFAULT_URL.format(name=mosaic[NAME],
                                        apikey=PlanetClient.getInstance().api_key()), self)

    def set_thumbnail(self, img):
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)

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
