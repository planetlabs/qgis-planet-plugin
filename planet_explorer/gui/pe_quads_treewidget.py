# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_quads_treewidget.py
    ---------------------
    Date                 : September 2020
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
__date__ = "September 2020"
__copyright__ = "(C) 2020 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

from collections import defaultdict

from qgis.core import QgsGeometry, QgsWkbTypes
from qgis.gui import QgsRubberBand
from qgis.PyQt import QtCore
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..pe_utils import (
    LINKS,
    NAME,
    QUADS_AOI_BODY_COLOR,
    QUADS_AOI_COLOR,
    iface,
    mosaic_title,
    qgsrectangle_for_canvas_from_4326_bbox_coords,
)
from .pe_thumbnails import download_thumbnail

ID = "id"
THUMBNAIL = "thumbnail"
PERCENT_COVERED = "percent_covered"
BBOX = "bbox"

PLACEHOLDER_THUMB = ":/plugins/planet_explorer/thumb-placeholder-128.svg"


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
        self._updating = False

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
            w.blockSignals(True)
            w.setChecked(checked)
            w.blockSignals(True)
        self._quad_selection_changed()

    def populate_by_quad(self, mosaics, quads):
        self.clear()
        instances_by_quad = defaultdict(list)
        for mosaic, mosaicquads in zip(mosaics, quads):
            widgets = []
            for quad in mosaicquads:
                item = QuadInstanceTreeItem(quad)
                widget = QuadInstanceItemWidget(quad)
                widget.quadSelected.connect(self._quad_selection_changed)
                widgets.append(widget)
                instances_by_quad[quad[ID]].append((item, widget))
            self.widgets[mosaic.get(NAME)] = widgets

        for quadid, values in instances_by_quad.items():
            item = QTreeWidgetItem()
            self.addTopLevelItem(item)
            widget = ParentTreeItemWidget(quadid, item)
            self.setItemWidget(item, 0, widget)
            item.setSizeHint(0, widget.sizeHint())
            for quaditem, quadwidget in values:
                item.addChild(quaditem)
                self.setItemWidget(quaditem, 0, quadwidget)
                quaditem.setSizeHint(0, quadwidget.sizeHint())
            widget.update_name_and_checkbox()

    def populate_by_basemap(self, mosaics, quads):
        self.clear()
        for mosaic, mosaicquads in zip(mosaics, quads):
            item = QTreeWidgetItem()
            self.addTopLevelItem(item)
            widget = ParentTreeItemWidget(mosaic_title(mosaic), item)
            self.setItemWidget(item, 0, widget)
            item.setSizeHint(0, widget.sizeHint())
            widgets = []
            for quad in mosaicquads:
                subitem = QuadInstanceTreeItem(quad)
                item.addChild(subitem)
                subwidget = QuadInstanceItemWidget(quad)
                self.setItemWidget(subitem, 0, subwidget)
                subitem.setSizeHint(0, subwidget.sizeHint())
                subwidget.quadSelected.connect(self._quad_selection_changed)
                widgets.append(subwidget)
            self.widgets[mosaic.get(NAME)] = widgets
            widget.update_name_and_checkbox()

    def _quad_selection_changed(self):
        if self._updating:
            return
        self._updating = True
        self.quadsSelectionChanged.emit()
        for i in range(self.topLevelItemCount()):
            w = self.itemWidget(self.topLevelItem(i), 0)
            if w is not None:
                w.update_name_and_checkbox()
        self._updating = False


class ParentTreeItemWidget(QFrame):
    def __init__(self, text, item):
        QWidget.__init__(self)
        self.setMouseTracking(True)
        self.text = text
        self.item = item
        self.label = QLabel()
        self.checkBox = QCheckBox("")
        self.checkBox.setTristate(True)
        self.checkBox.stateChanged.connect(self.check_box_state_changed)
        layout = QHBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.checkBox)
        layout.addWidget(self.label)
        layout.addStretch()
        self.setLayout(layout)

    def check_box_state_changed(self):
        total = self.item.childCount()
        if self.checkBox.isTristate():
            self.checkBox.setTristate(False)
            self.checkBox.setChecked(False)
        else:
            for i in range(total):
                w = self.item.treeWidget().itemWidget(self.item.child(i), 0)
                w.setChecked(self.checkBox.isChecked(), False)
            self.item.treeWidget().quadsSelectionChanged.emit()

    def update_name_and_checkbox(self):
        selected = 0
        total = self.item.childCount()
        for i in range(total):
            w = self.item.treeWidget().itemWidget(self.item.child(i), 0)
            if w.isSelected():
                selected += 1
        self.label.setText(f"<b>{self.text} - {selected} of {total} selected</b>")
        self.checkBox.blockSignals(True)
        if selected == total:
            self.checkBox.setTristate(False)
            self.checkBox.setCheckState(Qt.Checked)
        elif selected == 0:
            self.checkBox.setTristate(False)
            self.checkBox.setCheckState(Qt.Unchecked)
        else:
            self.checkBox.setTristate(True)
            self.checkBox.setCheckState(Qt.PartiallyChecked)
        self.checkBox.blockSignals(False)


class QuadInstanceTreeItem(QTreeWidgetItem):
    def __init__(self, quad):
        QTreeWidgetItem.__init__(self)
        self.quad = quad


class QuadInstanceItemWidget(QFrame):

    quadSelected = pyqtSignal()

    def __init__(self, quad):
        QWidget.__init__(self)
        self.setMouseTracking(True)
        self.quad = quad
        self.nameLabel = QLabel(
            f'<b>{quad[ID]}</b><br><span style="color:grey;">'  # noqa
            f"{quad[PERCENT_COVERED]} % covered</span>"
        )
        self.iconLabel = QLabel()
        pixmap = QPixmap(PLACEHOLDER_THUMB, "SVG")
        thumb = pixmap.scaled(
            48, 48, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
        )
        self.iconLabel.setPixmap(thumb)
        self.checkBox = QCheckBox("")
        self.checkBox.stateChanged.connect(self.check_box_state_changed)
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

        download_thumbnail(quad[LINKS][THUMBNAIL], self)

        self.footprint = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
        self.footprint.setFillColor(QUADS_AOI_COLOR)
        self.footprint.setStrokeColor(QUADS_AOI_COLOR)
        self.footprint.setWidth(2)

        self.footprintfill = QgsRubberBand(
            iface.mapCanvas(), QgsWkbTypes.PolygonGeometry
        )
        self.footprintfill.setFillColor(QUADS_AOI_BODY_COLOR)
        self.footprintfill.setWidth(0)

        self.update_footprint_brush()
        self.hide_solid_interior()
        self.show_footprint()

        self.setStyleSheet("QuadInstanceItemWidget{border: 2px solid transparent;}")

    def set_thumbnail(self, img):
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.iconLabel.setStyleSheet("")

    def check_box_state_changed(self):
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
        self.footprint.setBrushStyle(
            Qt.BDiagPattern if self.checkBox.isChecked() else Qt.NoBrush
        )
        self.footprint.updateCanvas()

    def remove_footprint(self):
        iface.mapCanvas().scene().removeItem(self.footprint)
        iface.mapCanvas().scene().removeItem(self.footprintfill)

    def isSelected(self):
        return self.checkBox.isChecked()

    def setChecked(self, checked, emit=True):
        if not emit:
            self.checkBox.blockSignals(True)
        self.checkBox.setChecked(checked)
        if not emit:
            self.update_footprint_brush()
            self.checkBox.blockSignals(False)

    def enterEvent(self, event):
        self.setStyleSheet(
            "QuadInstanceItemWidget{border: 2px solid rgb(157, 165, 0);}"
        )
        self.show_solid_interior()

    def leaveEvent(self, event):
        self.setStyleSheet("QuadInstanceItemWidget{border: 2px solid transparent;}")
        self.hide_solid_interior()
