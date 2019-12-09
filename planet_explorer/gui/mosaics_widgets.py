# -*- coding: utf-8 -*-
"""
***************************************************************************
    mosaics_widgets.py
    ---------------------
    Date                 : October 2019
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
import json
from urllib.parse import quote
import datetime
import iso8601

from planet.api.models import (
    Mosaics
)

from planet_explorer.pe_utils import(
    ITEM_BACKGROUND_COLOR
)

from PyQt5.QtWidgets import (
    QTreeWidget,
    QTreeWidgetItem,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QWidget,
    QHBoxLayout,
    QApplication
)

from PyQt5.QtGui import (
    QPixmap,
    QImage,
    QCursor,
    QPalette
)

from PyQt5.QtNetwork import (
    QNetworkAccessManager,
    QNetworkRequest
)

from PyQt5 import QtCore

from PyQt5.QtCore import (
    QUrl,
    QSize,
    Qt
)

from qgis.core import (
    QgsRasterLayer,
    QgsProject
)

from qgis.utils import iface

from .mosaic_layer_widget import(
    PLANET_MOSAICS,
    PLANET_CURRENT_MOSAIC,
    PLANET_MOSAIC_PROC,
    PLANET_MOSAIC_RAMP,
    PLANET_MOSAIC_DATATYPE,
    WIDGET_PROVIDER_NAME
)

ID = "id"
NAME = "name"
LINKS = "_links"
TILES = "tiles"
SERIES = "series"
FIRST_ACQUIRED = "first_acquired"
LAST_ACQUIRED = "last_acquired"
INTERVAL = "interval"
THUMB = "thumb"
DATATYPE = "datatype"

ONEMONTH = "1 mon"
THREEMONTHS = "3 mons"
WEEK = "7 days"

def mosaicTitle(mosaic):
    date = iso8601.parse_date(mosaic[FIRST_ACQUIRED])
    if INTERVAL in mosaic:
        interval = mosaic[INTERVAL]
        if interval == ONEMONTH:
            return date.strftime("%B %Y")
        elif interval == THREEMONTHS:
            date2 = iso8601.parse_date(mosaic[LAST_ACQUIRED])
            month = date.strftime("%B")
            return date2.strftime(f"{month} to %B %Y")
        elif interval == WEEK:
            return date.strftime("%B %d %Y")
    else:
        return date.strftime("%B %d %Y")

def addToQgisProject(mosaic, name, mosaicNames):
    tile_url = mosaic[LINKS][TILES]
    uri = f'type=xyz&url={tile_url}'
    layer = QgsRasterLayer(uri, name, 'wms')
    layer.setCustomProperty(PLANET_CURRENT_MOSAIC, mosaicTitle(mosaic))
    layer.setCustomProperty(PLANET_MOSAIC_PROC, "default")
    layer.setCustomProperty(PLANET_MOSAIC_RAMP, "")
    layer.setCustomProperty(PLANET_MOSAIC_DATATYPE, mosaic[DATATYPE])
    layer.setCustomProperty(PLANET_MOSAICS, json.dumps(mosaicNames))
    QgsProject.instance().addMapLayer(layer)
    layer.setCustomProperty("embeddedWidgets/count", 1)
    layer.setCustomProperty("embeddedWidgets/0/id", WIDGET_PROVIDER_NAME) 
    view = iface.layerTreeView()
    view.model().refreshLayerLegend(view.currentNode())
    view.currentNode().setExpanded(True)    

class MosaicsListWidget(QListWidget):

    def __init__(self, parent):
        QTreeWidget.__init__(self, None)
        self.parent = parent
        self.itemDoubleClicked.connect(self.listItemDoubleClicked)
        self.setAutoScroll(True)
        self.setSortingEnabled(True)  
        p = self.palette()
        p.setColor(QPalette.Highlight, ITEM_BACKGROUND_COLOR)
        self.setPalette(p)

    def listItemDoubleClicked(self, item):
        if isinstance(item, MosaicListItem) and item.enabled:
            addToQgisProject(item.mosaic, mosaicTitle(item.mosaic), item.mosaicNames)

    def populate_with_first_page(self):
        if self.count() == 0:
            self.populate()

    def populate(self, search=None):
        self.clear()
        try:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            mosaics = self.client().get_mosaics(search)        
            mosaicsArray = mosaics.get().get(Mosaics.ITEM_KEY)                      
        finally:
            QApplication.restoreOverrideCursor()
        for mosaic in mosaicsArray[::-1]:                
            item = MosaicListItem(mosaic)
            self.addItem(item)
            widget = MosaicItemWidget(mosaic)
            self.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())

        _next = mosaics.next()
        if _next is not None:
            item = QListWidgetItem()
            self.addItem(item)
            widget = LoadMoreItemWidget(_next, self)
            self.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())

        self.sortItems()

    def client(self):
        return self.parent.p_client

class MosaicSeriesTreeWidget(QTreeWidget):

    def __init__(self, parent):
        QTreeWidget.__init__(self, None)
        self.parent = parent
        self.setColumnCount(1)
        self.header().hide()
        self.itemExpanded.connect(self.treeItemExpanded)
        self.itemDoubleClicked.connect(self.treeItemDoubleClicked)
        self.setAutoScroll(True)
        self.setIndentation(int(self.indentation() * 0.5))

    def treeItemExpanded(self, item):
        if item is not None and item.childCount() == 0:
            item.populate()

    def treeItemDoubleClicked(self, item, column):
        if isinstance(item, MosaicTreeItem) and item.enabled:
            name = item.parent().name
            addToQgisProject(item.mosaic, name, item.mosaicNames)

    def populate(self):
        if self.topLevelItemCount() == 0:
            try:
                QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
                series = self.client().list_mosaic_series().get()[SERIES]
                for serie in series:
                    item = SeriesTreeItem(serie)
                    self.addTopLevelItem(item)
                    date = iso8601.parse_date(serie[FIRST_ACQUIRED])
                    date2 = iso8601.parse_date(serie[LAST_ACQUIRED])
                    details = f'{date.strftime("%m/%d/%Y")} - {date2.strftime("%m/%d/%Y")} [{serie[INTERVAL]}]'
                    nameLabel = QLabel(f'<b>{serie[NAME]}</b><br><span style="color:grey;">{details}</span>')
                    nameLabel.setMargin(5)
                    self.setItemWidget(item, 0, nameLabel)
            finally:
                QApplication.restoreOverrideCursor()

    def client(self):
        return self.parent.p_client

class SeriesTreeItem(QTreeWidgetItem):

    def __init__(self, serie):
        QTreeWidgetItem.__init__(self)
        self.serie = serie
        self.name = serie[NAME]
        self.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

    def populate(self):
        if self.childCount() == 0:
            try:
                QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
                mosaics = self.treeWidget().client().get_mosaics_for_series(self.serie[ID])
                mosaicsArray = []
                for page in mosaics.iter():
                    mosaicsArray.extend(page.get().get(Mosaics.ITEM_KEY))
                mosaicNames = [(mosaicTitle(m), m[NAME]) for m in mosaicsArray]
                for mosaic in mosaicsArray[::-1]:
                    item = MosaicTreeItem(mosaic, mosaicNames)
                    self.addChild(item)
                    widget = MosaicItemWidget(mosaic)
                    self.treeWidget().setItemWidget(item, 0, widget)
                    item.setSizeHint(0, widget.sizeHint())
            finally:
                QApplication.restoreOverrideCursor()                    


class MosaicTreeItem(QTreeWidgetItem):

    def __init__(self, mosaic, mosaicNames):
        QTreeWidgetItem.__init__(self)        
        self.mosaic = mosaic
        self.enabled = TILES in mosaic[LINKS]
        self.mosaicNames = mosaicNames

class MosaicListItem(QListWidgetItem):

    def __init__(self, mosaic):
        QListWidgetItem.__init__(self)
        self.mosaic = mosaic
        self.enabled = TILES in mosaic[LINKS]
        self.mosaicNames = [(mosaicTitle(mosaic), mosaic[NAME])]

    def __lt__(self, other):
        if isinstance(other, MosaicListItem):
            return self.mosaic[FIRST_ACQUIRED] < other.mosaic[FIRST_ACQUIRED]
        else:
            return True

class LoadMoreItemWidget(QWidget):

    def __init__(self, mosaics, listWidget):
        QWidget.__init__(self)
        self.mosaics = mosaics
        self.listWidget = listWidget        
        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setText('<b><i><a href="link" style="color: rgb(0, 157, 165);">Load more</a></i></b>')
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(self.load_more)
        layout = QHBoxLayout()        
        layout.addWidget(label)
        layout.addStretch()
        self.setLayout(layout)

    def load_more(self):
        mosaics = self.mosaics.get().get(Mosaics.ITEM_KEY)
        for mosaic in mosaics[::-1]:                
            item = MosaicListItem(mosaic)
            self.listWidget.insertItem(self.listWidget.count() - 1, item)
            widget = MosaicItemWidget(mosaic)
            self.listWidget.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())
        self.listWidget.sortItems()
        _next = self.mosaics.next()
        if _next is None:
            self.listWidget.takeItem(self.listWidget.count() - 1)
        else:
            self.mosaics = _next


class MosaicItemWidget(QWidget):

    def __init__(self, mosaic):
        QWidget.__init__(self)
        self.mosaic = mosaic
        color = "black" if TILES in mosaic[LINKS] else "grey"
        title = mosaicTitle(mosaic)
        nameLabel = QLabel(f'<span style="color:{color};"><b>{title}</b></span><br><span style="color:grey;">{mosaic[NAME]}</span>')
        self.iconLabel = QLabel()
        layout = QHBoxLayout()
        layout.addWidget(self.iconLabel)
        layout.addWidget(nameLabel)
        layout.addStretch()
        self.setLayout(layout)
        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self.iconDownloaded)
        self.nam.get(QNetworkRequest(QUrl(mosaic[LINKS][THUMB])))
        
    def iconDownloaded(self, reply):
        img = QImage()
        img.loadFromData(reply.readAll())
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                            QtCore.Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)

