# -*- coding: utf-8 -*-
"""
***************************************************************************
    mosaic_layer_widgets.py
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

from PyQt5.QtCore import Qt, QRectF

from PyQt5.QtGui import (
    QPainter,
    QBrush,
    QColor
)

from PyQt5.QtWidgets import (
    QWidget,
    QSlider,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QStyle, 
    QStyleOptionSlider,
    QStyleFactory
)

from qgis.core import (
    QgsMapLayer,
    QgsDataProvider,
    QgsLayerTreeLayer,
    QgsLayerTreeGroup,
    QgsProject
)

from qgis.gui import (
    QgsLayerTreeEmbeddedWidgetProvider,
    QgsLayerTreeEmbeddedWidgetRegistry
)

from ..pe_utils import PLANET_COLOR

from ..planet_api import PlanetClient

PLANET_CURRENT_MOSAIC = "planet/currentMosaic"
PLANET_MOSAICS = "planet/mosaics"
PLANET_MOSAIC_PROC = "planet/mosaicProc"
PLANET_MOSAIC_RAMP = "planet/mosaicRamp"
PLANET_MOSAIC_DATATYPE = "planet/mosaicDatatype"

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

class MosaicLayerWidget(QWidget):

    def __init__(self, layer):
        super().__init__()
        self.current_mosaic_name = layer.customProperty(PLANET_CURRENT_MOSAIC)
        proc = layer.customProperty(PLANET_MOSAIC_PROC)
        ramp = layer.customProperty(PLANET_MOSAIC_RAMP)
        self.datatype = layer.customProperty(PLANET_MOSAIC_DATATYPE)
        self.layer = layer
        self.mosaics = json.loads(layer.customProperty(PLANET_MOSAICS))
        self.mosaicnames = [m[0] for m in self.mosaics]
        self.mosaicids = [m[1] for m in self.mosaics]
        self.layout = QVBoxLayout()
        self.labelId = QLabel()
        self.layout.addWidget(self.labelId)
        if len(self.mosaics) > 1:
            idx = self.mosaicnames.index(self.current_mosaic_name)            
            self.labelName = QLabel(f"{self.current_mosaic_name}")
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
            idx = 0
        self.labelId.setText(f'<span style="color: grey;">{self.mosaicids[idx]}</span>')
        self.hlayoutProc = QHBoxLayout()
        self.labelProc = QLabel("Processing:")
        self.comboProc = QComboBox()
        self.comboProc.addItems(self.processes_for_datatype())
        self.comboProc.setCurrentText(proc)
        self.hlayoutProc.addWidget(self.labelProc)
        self.hlayoutProc.addWidget(self.comboProc)

        self.load_ramps()
        self.hlayoutRamp = QHBoxLayout()
        self.labelRamp = QLabel("Color ramp:")        
        self.comboRamp = QComboBox()                
        for r in self.ramps:
            self.comboRamp.addItem(r)
        self.comboRamp.setCurrentText(ramp)        
        self.comboRamp.setVisible(self.can_use_indices())
        self.labelRamp.setVisible(self.can_use_indices())
        self.hlayoutRamp.addWidget(self.labelRamp)
        self.hlayoutRamp.addWidget(self.comboRamp)
        self.layout.addLayout(self.hlayoutProc)
        self.layout.addLayout(self.hlayoutRamp)
        self.labelWarning = QLabel('<span style="color:red;"><b>No API key available</b></span>')
        self.layout.addWidget(self.labelWarning)
        self.setLayout(self.layout)

        self.comboProc.currentIndexChanged.connect(self.change_source)
        self.comboRamp.currentIndexChanged.connect(self.change_source)

        PlanetClient.getInstance().loginChanged.connect(self.login_changed)
        
        self.change_source()

    def load_ramps(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "resources", "mosaics_caps.json")
        with open(path) as f:
            caps = json.load(f)

        self.ramps = list(caps["colors"].keys())

    def on_value_changed(self, value):
        self.labelId.setText(f'<span style="color: grey;">{self.mosaicids[value]}</span>')
        self.labelName.setText(f"{self.mosaicnames[value]}")
        if not self.slider.isSliderDown():
            self.change_source()

    def can_use_indices(self):
        return self.datatype == "uint16"

    def change_source(self):
        has_api_key = PlanetClient.getInstance().has_api_key()
        self.labelWarning.setVisible(not has_api_key)
        self.labelId.setVisible(has_api_key)
        self.labelProc.setVisible(has_api_key)
        self.labelRamp.setVisible(has_api_key and self.can_use_indices())
        if len(self.mosaics) > 1:
            self.labelName.setVisible(has_api_key)
            self.slider.setVisible(has_api_key)
        self.comboProc.setVisible(has_api_key)
        self.comboRamp.setVisible(has_api_key and self.can_use_indices())
        value = self.slider.value() if len(self.mosaics) > 1 else 0
        proc = self.comboProc.currentText()
        ramp = self.comboRamp.currentText()
        name, mosaicid = self.mosaics[value]
        tile_url = TILE_URL_TEMPLATE % (mosaicid, str(PlanetClient.getInstance().api_key()))
        procparam = quote(f'&proc={proc}') if proc != "default" else ""
        rampparam = quote(f'&color={ramp}') if self.can_use_indices() else ""
        uri = f"type=xyz&url={tile_url}{procparam}{rampparam}"        
        self.layer.dataProvider().setDataSourceUri(uri)
        self.layer.setCustomProperty(PLANET_CURRENT_MOSAIC, name)
        self.layer.setCustomProperty(PLANET_MOSAIC_PROC, proc)
        self.layer.setCustomProperty(PLANET_MOSAIC_RAMP, ramp)
        self.layer.triggerRepaint()

    def login_changed(self):
        self.change_source()
        self.ensure_correct_size()

    def ensure_correct_size(self):
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

    def processes_for_datatype(self):
        if self.datatype == "uint16":
            return  ["default", "rgb", "cir", "ndvi", "mtvi2", "ndwi",
                        "msavi2", "tgi", "vari"]
        elif self.datatype == "byte":
            return ["default", "tgi", "vari"]
        else:
            return ["default"]

WIDGET_PROVIDER_NAME = "planetmosaiclayerwidget"

class MosaicLayerWidgetProvider(QgsLayerTreeEmbeddedWidgetProvider):

    def __init__(self):
        QgsLayerTreeEmbeddedWidgetProvider.__init__(self)
        self.widgets = {}

    def id(self):
        return WIDGET_PROVIDER_NAME

    def name(self):
        return "Planet Mosaic Layer Widget"

    def createWidget(self, layer, widgetIndex):
        widget = MosaicLayerWidget(layer)
        self.widgets[layer.id()] = widget
        return widget

    def supportsLayer(self, layer):    
        return PLANET_CURRENT_MOSAIC in layer.customPropertyKeys()

    def logoutLayerWidgets(self):
        PlanetClient.getInstance().log_out()
        for widget in self.widgets.values():
            widget.login_changed()



