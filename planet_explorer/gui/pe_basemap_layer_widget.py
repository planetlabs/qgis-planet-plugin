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
import json
import os
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse, urlunparse

from qgis.core import (
    Qgis,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsMessageLog,
    QgsProject,
)
from qgis.gui import QgsLayerTreeEmbeddedWidgetProvider
from qgis.PyQt.QtCore import QByteArray, QRectF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor, QImage, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from ..pe_utils import (
    PLANET_CURRENT_MOSAIC,
    PLANET_MOSAIC_DATATYPE,
    PLANET_MOSAIC_PROC,
    PLANET_MOSAIC_RAMP,
    PLANET_MOSAICS,
    QGIS_LOG_SECTION_NAME,
    WIDGET_PROVIDER_NAME,
    datatype_from_mosaic_name,
    is_planet_url,
    mosaic_name_from_url,
    user_agent,
)
from ..planet_api import PlanetClient


class CustomSlider(QSlider):
    def paintEvent(self, event):
        # based on
        # http://qt.gitorious.org/qt/qt/blobs/master/src/gui/widgets/qslider.cpp

        with QPainter(self) as painter:
            style = self.style()
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)

            groove_rect = style.subControlRect(
                QStyle.ComplexControl.CC_Slider,
                opt,
                QStyle.SubControl.SC_SliderGroove,
                self,
            )
            handle_rect = style.subControlRect(
                QStyle.ComplexControl.CC_Slider,
                opt,
                QStyle.SubControl.SC_SliderHandle,
                self,
            )

            slider_space = style.pixelMetric(
                style.PixelMetric.PM_SliderSpaceAvailable, opt
            )
            range_x = style.sliderPositionFromValue(
                self.minimum(), self.maximum(), self.value(), slider_space
            )
            range_height = 4

            groove_rect = QRectF(
                groove_rect.x(),
                handle_rect.center().y() - (range_height / 2),
                groove_rect.width(),
                range_height,
            )

            range_rect = QRectF(
                groove_rect.x(),
                handle_rect.center().y() - (range_height / 2),
                range_x,
                range_height,
            )

            if style.metaObject().className() != "QMacStyle":
                # Paint groove for Fusion and Windows styles
                cur_brush = painter.brush()
                cur_pen = painter.pen()
                painter.setBrush(QBrush(QColor(169, 169, 169)))
                painter.setPen(Qt.PenStyle.NoPen)
                # painter.drawRect(groove_rect)
                painter.drawRoundedRect(
                    groove_rect, groove_rect.height() / 2, groove_rect.height() / 2
                )
                painter.setBrush(cur_brush)
                painter.setPen(cur_pen)

            cur_brush = painter.brush()
            cur_pen = painter.pen()
            painter.setBrush(QBrush(QColor(18, 141, 148)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(range_rect)
            painter.setBrush(cur_brush)
            painter.setPen(cur_pen)

            opt = QStyleOptionSlider()
            self.initStyleOption(opt)

            opt.subControls = QStyle.SubControl.SC_SliderHandle

            if self.tickPosition() != self.TickPosition.NoTicks:
                opt.subControls |= QStyle.SubControl.SC_SliderTickmarks

            if self.isSliderDown():
                opt.state |= QStyle.StateFlag.State_Sunken
            else:
                opt.state |= QStyle.StateFlag.State_Active

            opt.activeSubControls = QStyle.SubControl.SC_None

            opt.sliderPosition = self.value()
            opt.sliderValue = self.value()
            style.drawComplexControl(
                QStyle.ComplexControl.CC_Slider, opt, painter, self
            )


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
                    self.comboRamp.setItemData(
                        self.comboRamp.count() - 1, icon, Qt.ItemDataRole.DecorationRole
                    )
                self.comboRamp.setCurrentText(default)
                if len(ramps) != len(list(self.ramps["colors"].keys())):
                    item = QListWidgetItem()
                    self.listWidget.addItem(item)
                    label = QLabel(
                        "<a href='#' style='color: grey;'>Show all ramps</a>"
                    )
                    label.setAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
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
            self.comboRamp.setItemData(
                self.comboRamp.count() - 1, icon, Qt.ItemDataRole.DecorationRole
            )
        self.comboRamp.showPopup()

    def ramps_for_current_process(self):
        process = self.comboProc.currentText()
        if process in self.ramps["indices"]:
            pref_colors = self.ramps["indices"][process]["pref-colors"] or list(
                self.ramps["colors"].keys()
            )
            return self.ramps["indices"][process]["color"], pref_colors
        else:
            return None, []

    def load_ramps(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "resources", "mosaics_caps.json"
        )
        with open(path) as f:
            self.ramps = json.load(f)

        self.ramp_pixmaps = {}
        for k, v in self.ramps["colors"].items():
            base64 = v["icon"][len("data:image/png;base64,") :].encode()  # noqa
            byte_array = QByteArray.fromBase64(base64)
            image = QImage.fromData(byte_array, "PNG")
            scaled = image.scaled(100, 20)
            pixmap = QPixmap.fromImage(scaled)
            self.ramp_pixmaps[k] = pixmap

    def processes_for_datatype(self):
        if self.datatype == "uint16":
            return ["rgb", "cir", "ndvi", "mtvi2", "ndwi", "msavi2", "tgi", "vari"]
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

            # Prevent breaking projects created before the update
            # to PLANET_MOSAICS property in add_mosaics_to_qgis_project
            try:
                self.mosaicnames = [m["mosaic_name"] for m in self.mosaics]
                self.mosaicids = [m["mosaic_id"] for m in self.mosaics]
            except Exception:
                self.mosaicnames = [m[0] for m in self.mosaics]
                self.mosaicids = [m[1] for m in self.mosaics]

            self.layout = QVBoxLayout()
            self.renderingOptionsWidget = BasemapRenderingOptionsWidget(self.datatype)
            self.layout.addWidget(self.renderingOptionsWidget)
            if len(self.mosaics) > 1:
                current_mosaic_name = layer.customProperty(PLANET_CURRENT_MOSAIC)
                try:
                    idx = self.mosaicnames.index(current_mosaic_name)
                except ValueError:
                    idx = 0
                self.labelId = QLabel()
                self.labelId.setText(
                    f'<span style="color: grey;">{self.mosaicids[idx]}</span>'  # noqa
                )
                self.layout.addWidget(self.labelId)
                self.labelName = QLabel(current_mosaic_name)
                self.slider = CustomSlider(Qt.Orientation.Horizontal)
                self.slider.setRange(0, len(self.mosaics) - 1)
                self.slider.setTickInterval(1)
                self.slider.setTickPosition(QSlider.TickPosition.TicksAbove)
                self.slider.setPageStep(1)
                self.slider.setTracking(True)
                self.slider.setEnabled(True)
                self.slider.setValue(idx)
                self.slider.valueChanged.connect(self.on_value_changed)
                self.slider.sliderReleased.connect(self.change_source)
                self.layout.addWidget(self.labelName)
                self.layout.addWidget(self.slider)

            self.renderingOptionsWidget.set_process(proc)
            self.renderingOptionsWidget.set_ramp(ramp)
            self.renderingOptionsWidget.values_changed.connect(self.change_source)
            self.labelWarning = QLabel(
                '<span style="color:red;"><b>No API key or Auth token available</b></span>'
            )
            self.layout.addWidget(self.labelWarning)
            self.setLayout(self.layout)

            PlanetClient.getInstance().loginChanged.connect(self.login_changed)

            self.change_source()
        else:
            self.layout = QVBoxLayout()
            self.labelWarning = QLabel(
                '<span style="color:red;"><b>Not a valid Planet basemap'
                " layer</b></span>"
            )
            self.layout.addWidget(self.labelWarning)
            self.setLayout(self.layout)

    def is_planet_basemap(self):
        return is_planet_url(self.layer.source())

    def on_value_changed(self, value):
        self.labelId.setText(
            f'<span style="color: grey;">{self.mosaicids[value]}</span>'  # noqa
        )
        self.labelName.setText(f"{self.mosaicnames[value]}")
        if not self.slider.isSliderDown():
            self.change_source()

    def _resolve_tile_url(self, client, missing_auth) -> str:
        if len(self.mosaics) > 1:
            self.labelId.setVisible(not missing_auth)
            self.labelName.setVisible(not missing_auth)
            self.slider.setVisible(not missing_auth)
            value = self.slider.value() if len(self.mosaics) > 1 else 0
            mosaic = self.mosaics[value]

            # Prevent breaking projects created before the update
            # to PLANET_MOSAICS property in add_mosaics_to_qgis_project
            try:
                mosaicname = mosaic["mosaic_name"]
                tile_url = mosaic["tile_url"]
            except Exception:
                mosaicname, mosaicid = self.mosaics[value]
                TILE_URL_TEMPLATE = (
                    "https://tiles.planet.com/basemaps/v1/planet-tiles/"
                    "%s/gmap/{z}/{x}/{y}.png"
                )
                tile_url = TILE_URL_TEMPLATE % (mosaicid,)
            self.layer.setCustomProperty(PLANET_CURRENT_MOSAIC, mosaicname)
            return tile_url

        # Prevent breaking projects created before the update
        # to PLANET_MOSAICS property in add_mosaics_to_qgis_project
        try:
            return self.mosaics[0]["tile_url"]
        except Exception:
            _, tile_url = client._split_qgis_uri(unquote(self.layer.source()))
            return client.clean_planet_tile_url(tile_url)

    def _build_auth_header_for_uri(self, client, missing_auth) -> str | None:
        if missing_auth:
            return None

        if client.client_is_setup():
            return client.build_authorization_header(
                auth_header_key="http-header:authorization", encode=True
            )

        auth_param = client.extract_auth_param(unquote(self.layer.source()))
        # Deliberately failing api keys for authentication
        if auth_param is None or "api_key" in auth_param:
            return None
        else:
            key, value = next(iter(auth_param.items()))
            return f"{key}={quote(value, safe='')}"

    def change_source(self):
        try:
            client = PlanetClient.getInstance()

            # The label warning should only be shown if a logged-in user doesn't
            # does not have access to auth token or when layer source doesn't
            # contain authentication parameters if no user has logged-in.
            missing_auth = (
                not client.auth_params_check(unquote(self.layer.source()))
                and not client.client_is_setup()
            )

            self.labelWarning.setVisible(missing_auth)
            self.renderingOptionsWidget.setVisible(missing_auth)

            tile_url = self._resolve_tile_url(client, missing_auth)

            parts = urlparse(tile_url)
            query_params = parse_qs(parts.query, keep_blank_values=True)

            query_params["ua"] = [user_agent()]

            proc = self.renderingOptionsWidget.process()
            if proc and proc != "default":
                query_params["proc"] = [str(proc)]

            ramp = self.renderingOptionsWidget.ramp()
            if ramp:
                query_params["color"] = [str(ramp)]

            tokens = self.layer.source().split("&")
            for token in tokens:
                if token.startswith(("zmin=", "zmax=")):
                    k, _, v = token.partition("=")
                    if v:
                        query_params[k] = [v]

            tile_url = urlunparse(
                parts._replace(
                    query=urlencode(query_params, doseq=True, quote_via=quote)
                )
            )
            uri = f"type=xyz&url={tile_url}"

            auth_header = self._build_auth_header_for_uri(client, missing_auth)
            if auth_header is not None:
                uri = f"{uri}&{auth_header}"

            provider = self.layer.dataProvider()
            if provider is not None:
                provider.setDataSourceUri(uri)
                self.layer.triggerRepaint()
            self.layer.setCustomProperty(PLANET_MOSAIC_PROC, proc)
            self.layer.setCustomProperty(PLANET_MOSAIC_RAMP, ramp)
            self.ensure_correct_size()
        except RuntimeError as error:
            QgsMessageLog.logMessage(
                f"Problem changing source" f" {error}",
                QGIS_LOG_SECTION_NAME,
                Qgis.MessageLevel.Info,
            )

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
            if not PlanetClient.getInstance().client_is_setup():
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
