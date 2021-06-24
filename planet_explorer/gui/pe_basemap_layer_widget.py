# -*- coding: utf-8 -*-
"""
***************************************************************************
    basemap_layer_widgets.py
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
import os
import json
from urllib.parse import quote

from PyQt5.QtCore import (
    Qt,
    QRectF,
    pyqtSignal,
    QByteArray,
    QSize
)

from PyQt5.QtGui import (
    QPainter,
    QBrush,
    QColor,
    QImage,
    QPixmap
)

from PyQt5.QtWidgets import (
    QWidget,
    QSlider,
    QVBoxLayout,
    QGridLayout,
    QComboBox,
    QLabel,
    QStyle,
    QStyleOptionSlider,
    QFrame,
    QListWidget,
    QListWidgetItem
)

from qgis.core import (
    QgsLayerTreeLayer,
    QgsLayerTreeGroup,
    QgsProject,
)

from qgis.gui import (
    QgsLayerTreeEmbeddedWidgetProvider
)

from ..planet_api import PlanetClient

from ..pe_utils import (
    PLANET_MOSAICS,
    PLANET_CURRENT_MOSAIC,
    PLANET_MOSAIC_PROC,
    PLANET_MOSAIC_RAMP,
    PLANET_MOSAIC_DATATYPE,
    WIDGET_PROVIDER_NAME,
    mosaic_name_from_url,
    datatype_from_mosaic_name,
    is_planet_url
)

TILE_URL_TEMPLATE = "https://tiles.planet.com/basemaps/v1/planet-tiles/%s/gmap/{z}/{x}/{y}.png?api_key=%s"


class CustomSlider(QSlider):

    def paintEvent(self, event):
        # based on
        # http://qt.gitorious.org/qt/qt/blobs/master/src/gui/widgets/qslider.cpp

        painter = QPainter(self)
        style = self.style()
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)

        groove_rect = style.subControlRect(
            style.CC_Slider, opt, QStyle.SC_SliderGroove, self)
        handle_rect = style.subControlRect(
            style.CC_Slider, opt, QStyle.SC_SliderHandle, self)

        slider_space = style.pixelMetric(style.PM_SliderSpaceAvailable, opt)
        range_x = style.sliderPositionFromValue(
            self.minimum(), self.maximum(), self.value(), slider_space)
        range_height = 4

        groove_rect = QRectF(
            groove_rect.x(),
            handle_rect.center().y() - (range_height / 2),
            groove_rect.width(),
            range_height)

        range_rect = QRectF(
            groove_rect.x(),
            handle_rect.center().y() - (range_height / 2),
            range_x,
            range_height)

        if style.metaObject().className() != 'QMacStyle':
            # Paint groove for Fusion and Windows styles
            cur_brush = painter.brush()
            cur_pen = painter.pen()
            painter.setBrush(QBrush(QColor(169, 169, 169)))
            painter.setPen(Qt.NoPen)
            # painter.drawRect(groove_rect)
            painter.drawRoundedRect(groove_rect,
                                    groove_rect.height() / 2,
                                    groove_rect.height() / 2)
            painter.setBrush(cur_brush)
            painter.setPen(cur_pen)

        cur_brush = painter.brush()
        cur_pen = painter.pen()
        painter.setBrush(QBrush(QColor(18, 141, 148)))
        painter.setPen(Qt.NoPen)
        painter.drawRect(range_rect)
        painter.setBrush(cur_brush)
        painter.setPen(cur_pen)

        opt = QStyleOptionSlider()
        self.initStyleOption(opt)

        opt.subControls = QStyle.SC_SliderHandle

        if self.tickPosition() != self.NoTicks:
            opt.subControls |= QStyle.SC_SliderTickmarks

        if self.isSliderDown():
            opt.state |= QStyle.State_Sunken
        else:
            opt.state |= QStyle.State_Active

        opt.activeSubControls = QStyle.SC_None

        opt.sliderPosition = self.value()
        opt.sliderValue = self.value()
        style.drawComplexControl(
            QStyle.CC_Slider, opt, painter, self)


class BasemapRenderingOptionsWidget(QFrame):

    values_changed = pyqtSignal()

    def __init__(self, datatype=None):
        super().__init__()
        self.layout = QGridLayout()
        self.layout.setMargin(0)

        self.labelProc = QLabel("Processing:")
        self.comboProc = QComboBox()
        self.layout.addWidget(self.labelProc, 0, 0)
        self.layout.addWidget(self.comboProc, 0, 1)

        self.load_ramps()
        self.labelRamp = QLabel("Color ramp:")
        self.comboRamp = QComboBox()

        self.layout.addWidget(self.labelRamp, 1, 0)
        self.layout.addWidget(self.comboRamp, 1, 1)

        self.setLayout(self.layout)
        self.comboProc.currentIndexChanged.connect(self._proc_changed)
        self.listWidget = QListWidget()
        self.comboRamp.setView(self.listWidget)
        self.comboRamp.setModel(self.listWidget.model())
        self.comboRamp.currentIndexChanged.connect(self.values_changed.emit)

        self.set_datatype(datatype)

        self.setStyleSheet("QFrame {border: 0px;}")

    def set_datatype(self, datatype):
        self.datatype = datatype
        self.comboRamp.blockSignals(True)
        self.comboProc.clear()
        self.comboProc.addItem("default")
        procs = self.processes_for_datatype()
        if procs:
            self.comboProc.addItems(procs)
        self.labelProc.setVisible(self.can_use_indices())
        self.comboProc.setVisible(self.can_use_indices())
        self.comboRamp.blockSignals(False)
        self.comboRamp.setVisible(self.can_use_indices())
        self.labelRamp.setVisible(self.can_use_indices())
        self._proc_changed()

    def _proc_changed(self):
        if self.can_use_indices():
            self.comboRamp.clear()
            self.comboRamp.setIconSize(QSize(100, 20))
            default, ramps = self.ramps_for_current_process()
            if ramps:
                self.comboRamp.setVisible(True)
                self.labelRamp.setVisible(True)
                for name in ramps:
                    icon = self.ramp_pixmaps[name]
                    self.comboRamp.addItem(name)
                    self.comboRamp.setItemData(self.comboRamp.count() - 1, icon, Qt.DecorationRole)
                self.comboRamp.setCurrentText(default)
                if len(ramps) != len(list(self.ramps["colors"].keys())):
                    item = QListWidgetItem()
                    self.listWidget.addItem(item)
                    label = QLabel("<a href='#' style='color: grey;'>Show all ramps</a>")
                    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    label.linkActivated.connect(self._show_all_ramps)
                    self.listWidget.setItemWidget(item, label)
            else:
                self.comboRamp.setVisible(False)
                self.labelRamp.setVisible(False)
                self.values_changed.emit()
        else:
            self.values_changed.emit()

    def _show_all_ramps(self):
        self.comboRamp.clear()
        self.comboRamp.setIconSize(QSize(100, 20))
        ramps = list(self.ramps["colors"].keys())
        for name in ramps:
            icon = self.ramp_pixmaps[name]
            self.comboRamp.addItem(name)
            self.comboRamp.setItemData(self.comboRamp.count() - 1, icon, Qt.DecorationRole)
        self.comboRamp.showPopup()

    def ramps_for_current_process(self):
        process = self.comboProc.currentText()
        if process in self.ramps["indices"]:
            pref_colors = self.ramps["indices"][process]["pref-colors"] or list(self.ramps["colors"].keys())
            return self.ramps["indices"][process]["color"], pref_colors
        else:
            return None, []

    def load_ramps(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "resources", "mosaics_caps.json")
        with open(path) as f:
            self.ramps = json.load(f)

        self.ramp_pixmaps = {}
        for k, v in self.ramps["colors"].items():
            base64 = v["icon"][len("data:image/png;base64,"):].encode()
            byte_array = QByteArray.fromBase64(base64)
            image = QImage.fromData(byte_array, "PNG")
            scaled = image.scaled(100, 20)
            pixmap = QPixmap.fromImage(scaled)
            self.ramp_pixmaps[k] = pixmap

    def processes_for_datatype(self):
        if self.datatype == "uint16":
            return ["rgb", "cir", "ndvi", "mtvi2", "ndwi",
                    "msavi2", "tgi", "vari"]
        else:
            return []

    def can_use_indices(self):
        return self.datatype == "uint16"

    def process(self):
        return self.comboProc.currentText()

    def set_process(self, proc):
        self.comboProc.setCurrentText(proc)

    def set_ramp(self, ramp):
        self.comboRamp.setCurrentText(ramp)

    def ramp(self):
        ramp = self.comboRamp.currentText() if self.can_use_indices() else ""
        return ramp


class BasemapLayerWidget(QWidget):

    def __init__(self, layer):
        super().__init__()
        proc = layer.customProperty(PLANET_MOSAIC_PROC)
        ramp = layer.customProperty(PLANET_MOSAIC_RAMP)
        self.datatype = layer.customProperty(PLANET_MOSAIC_DATATYPE)
        self.layer = layer
        if self.is_planet_basemap():
            self.mosaics = json.loads(layer.customProperty(PLANET_MOSAICS))
            self.mosaicnames = [m[0] for m in self.mosaics]
            self.mosaicids = [m[1] for m in self.mosaics]
            self.layout = QVBoxLayout()
            self.renderingOptionsWidget = BasemapRenderingOptionsWidget(self.datatype)
            self.layout.addWidget(self.renderingOptionsWidget)
            if len(self.mosaics) > 1:
                # We don't use the layer source url when there are multiple mosaics.
                # It will be composed on-the-fly based on the mosaic parameters
                current_mosaic_name = layer.customProperty(PLANET_CURRENT_MOSAIC)
                idx = self.mosaicnames.index(current_mosaic_name)
                self.labelId = QLabel()
                self.labelId.setText(f'<span style="color: grey;">{self.mosaicids[idx]}</span>')
                self.layout.addWidget(self.labelId)
                self.labelName = QLabel(current_mosaic_name)
                self.slider = CustomSlider(Qt.Horizontal)
                self.slider.setRange(0, len(self.mosaics) - 1)
                self.slider.setTickInterval(1)
                self.slider.setTickPosition(QSlider.TicksAbove)
                self.slider.setPageStep(1)
                self.slider.setTracking(True)
                self.slider.setEnabled(True)
                self.slider.setValue(idx)
                self.slider.valueChanged.connect(self.on_value_changed)
                self.slider.sliderReleased.connect(self.change_source)
                self.layout.addWidget(self.labelName)
                self.layout.addWidget(self.slider)
            else:
                # if there are no multiple mosaics, we use the original url,
                # and just add 'proc' and 'color' modifiers to it
                layerurl = layer.source().split("&url=")[-1]
                tokens = layerurl.split("?")
                self.layerurl = f"{tokens[0]}?{quote(tokens[1])}"
            self.renderingOptionsWidget.set_process(proc)
            self.renderingOptionsWidget.set_ramp(ramp)
            self.renderingOptionsWidget.values_changed.connect(self.change_source)
            self.labelWarning = QLabel('<span style="color:red;"><b>No API key available</b></span>')
            self.layout.addWidget(self.labelWarning)
            self.setLayout(self.layout)

            PlanetClient.getInstance().loginChanged.connect(self.login_changed)

            self.change_source()
        else:
            self.layout = QVBoxLayout()
            self.labelWarning = QLabel('<span style="color:red;"><b>Not a valid Planet basemap layer</b></span>')
            self.layout.addWidget(self.labelWarning)
            self.setLayout(self.layout)

    def is_planet_basemap(self):
        return is_planet_url(self.layer.source())

    def on_value_changed(self, value):
        self.labelId.setText(f'<span style="color: grey;">{self.mosaicids[value]}</span>')
        self.labelName.setText(f"{self.mosaicnames[value]}")
        if not self.slider.isSliderDown():
            self.change_source()

    def change_source(self):
        has_api_key = PlanetClient.getInstance().has_api_key()
        self.labelWarning.setVisible(not has_api_key)
        self.renderingOptionsWidget.setVisible(has_api_key)
        if len(self.mosaics) > 1:
            self.labelId.setVisible(has_api_key)
            self.labelName.setVisible(has_api_key)
            self.slider.setVisible(has_api_key)
            value = self.slider.value() if len(self.mosaics) > 1 else 0
            name, mosaicid = self.mosaics[value]
            tile_url = TILE_URL_TEMPLATE % (mosaicid, str(PlanetClient.getInstance().api_key()))
            self.layer.setCustomProperty(PLANET_CURRENT_MOSAIC, name)
        else:
            tile_url = f"{self.layerurl}/{quote(f'&api_key={PlanetClient.getInstance().api_key()}')}"
        proc = self.renderingOptionsWidget.process()
        ramp = self.renderingOptionsWidget.ramp()
        procparam = quote(f'&proc={proc}') if proc != "default" else ""
        rampparam = quote(f'&color={ramp}') if ramp else ""
        tokens = self.layer.source().split("&")
        zoom = []
        for token in tokens:
            if token.startswith("zmin="):
                zoom.append(token)
            if token.startswith("zmax="):
                zoom.append(token)
        szoom = f"&{'&'.join(zoom)}" if zoom else ""
        uri = f"type=xyz&url={tile_url}{procparam}{rampparam}{szoom}"
        provider = self.layer.dataProvider()
        if provider is not None:
            provider.setDataSourceUri(uri)
            self.layer.triggerRepaint()
        self.layer.setCustomProperty(PLANET_MOSAIC_PROC, proc)
        self.layer.setCustomProperty(PLANET_MOSAIC_RAMP, ramp)
        self.ensure_correct_size()

    def login_changed(self):
        if not bool(self.datatype):
            mosaic = mosaic_name_from_url(self.layer.source())
            datatype = datatype_from_mosaic_name(mosaic)
            if datatype is not None:
                self.datatype = datatype
                self.layer.setCustomProperty(PLANET_MOSAIC_DATATYPE, datatype)
                self.renderingOptionsWidget.set_datatype(datatype)
        self.ensure_correct_size()
        self.change_source()

    def ensure_correct_size(self):
        if self.layer is None:
            return
        def findLayerItem(root=None):
            root = root or QgsProject.instance().layerTreeRoot()
            for child in root.children():
                if isinstance(child, QgsLayerTreeLayer):
                    if self.layer.id() == child.layer().id():
                        return child
                elif isinstance(child, QgsLayerTreeGroup):
                    return findLayerItem(child)
        item = findLayerItem()
        if item is not None:
            if not PlanetClient.getInstance().has_api_key():
                item.setExpanded(True)
            isExpanded = item.isExpanded()
            item.setExpanded(not isExpanded)
            item.setExpanded(isExpanded)

class BasemapLayerWidgetProvider(QgsLayerTreeEmbeddedWidgetProvider):

    def __init__(self):
        QgsLayerTreeEmbeddedWidgetProvider.__init__(self)
        self.widgets = {}

    def id(self):
        return WIDGET_PROVIDER_NAME

    def name(self):
        return "Planet Basemap Layer Widget"

    def createWidget(self, layer, widgetIndex):
        widget = BasemapLayerWidget(layer)
        self.widgets[layer.id()] = widget
        return self.widgets[layer.id()]

    def supportsLayer(self, layer):
        return PLANET_CURRENT_MOSAIC in layer.customPropertyKeys()

    def updateLayerWidgets(self):
        for widget in self.widgets.values():
            widget.login_changed()

    def layerWasRemoved(self, layerid):
        if layerid in self.widgets:
            del self.widgets[layerid]
