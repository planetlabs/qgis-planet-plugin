# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_filters.py
    ---------------------
    Date                 : August 2019
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
__date__ = "August 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import json
import logging
from math import floor
import os
import re

from planet.api.filters import (
    date_range,
    geom_filter,
    not_filter,
    permission_filter,
    range_filter,
    string_filter,
)
from planet.api.utils import geometry_from_json
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsDistanceArea,
    QgsFeature,
    QgsGeometry,
    QgsMapLayer,
    QgsProject,
    QgsRectangle,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import (
    QgsDateTimeEdit,
    QgsMapCanvas,
    QgsMapTool,
    QgsRubberBand,
)
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QDateTime, QObject, Qt, pyqtSignal, pyqtSlot
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAction,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QLineEdit,
    QMenu,
    QVBoxLayout,
)

from ..pe_utils import (
    MAIN_AOI_COLOR,
    qgsgeometry_from_geojson,
    zoom_canvas_to_aoi,
    iface,
)
from ..planet_api.p_client import PlanetClient
from .pe_aoi_maptools import PlanetCircleMapTool, PlanetExtentMapTool, PlanetPolyMapTool
from .pe_range_slider import PlanetExplorerRangeSlider
from .pe_legacy_warning_widget import LegacyWarningWidget

LOCAL_FILTERS = ["area_coverage"]

slider_filters = [
    dict(
        title="Cloud cover",
        filter_key="cloud_cover",
        prefix="",
        suffix="%",
        minimum=0,
        maximum=100,
        low=0,
        high=100,
        step=1,
        precision=1,
    ),
    dict(
        title="Sun Azimuth",
        filter_key="sun_azimuth",
        prefix="",
        suffix="°",
        minimum=0,
        maximum=360,
        low=0,
        high=360,
        step=1,
        precision=1,
    ),
    dict(
        title="Sun Elevation",
        filter_key="sun_elevation",
        prefix="",
        suffix="°",
        minimum=0,
        maximum=90,
        low=0,
        high=90,
        step=1,
        precision=1,
    ),
    dict(
        title="View Angle",
        filter_key="view_angle",
        prefix="",
        suffix="°",
        minimum=-25,
        maximum=25,
        low=0,
        high=25,
        step=1,
        precision=1,
    ),
    dict(
        title="Ground Sample Distance",
        filter_key="gsd",
        prefix="",
        suffix="m",
        minimum=0,
        maximum=50,
        low=0,
        high=50,
        step=1,
        precision=1,
    ),
    dict(
        title="Anomalous Pixels",
        filter_key="anomalous_pixels",
        prefix="",
        suffix="%",
        minimum=0,
        maximum=100,
        low=0,
        high=100,
        step=1,
        precision=1,
    ),
    dict(
        title="Usable Pixels",
        filter_key="usable_data",
        prefix="",
        suffix="%",
        minimum=0,
        maximum=100,
        low=0,
        high=100,
        step=1,
        precision=1,
    ),
    dict(
        title="Area Coverage",
        filter_key="area_coverage",
        prefix="",
        suffix="%",
        minimum=0,
        maximum=100,
        low=0,
        high=100,
        step=1,
        precision=1,
    ),
]

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

plugin_path = os.path.split(os.path.dirname(__file__))[0]
AOI_FILTER_WIDGET, AOI_FILTER_BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_aoi_filter_base.ui"),
    from_imports=True,
    import_from=f"{os.path.basename(plugin_path)}",
    resource_suffix="",
)
DAILY_WIDGET, DAILY_BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_daily_filter_base.ui"),
    from_imports=True,
    import_from=f"{os.path.basename(plugin_path)}",
    resource_suffix="",
)


def filters_from_request(request, field_name=None, filter_type=None):
    filters = []

    def _add_filter(filterdict):
        if filterdict["type"] in ["AndFilter", "OrFilter"]:
            for subfilter in filterdict["config"]:
                _add_filter(subfilter)
        elif filterdict["type"] == "NotFilter":
            _add_filter(filterdict["config"])
        else:
            if (
                field_name is not None
                and "field_name" in filterdict
                and filterdict["field_name"] == field_name
            ):
                filters.append(filterdict)
            if filter_type is not None and filterdict["type"] == filter_type:
                filters.append(filterdict)

    filter_entry = request["filter"] if "filter" in request else request
    _add_filter(filter_entry)
    return filters


def filters_as_text_from_request(request):
    s = ""
    for slider_filter in slider_filters:
        k = slider_filter["filter_key"]
        filters = filters_from_request(request, k)
        if filters:
            minvalue = filters[0]["config"].get("gte")
            if minvalue is None:
                minvalue = slider_filter["minimum"]
            elif k == "cloud_cover":
                minvalue *= 100.0
            maxvalue = filters[0]["config"].get("lte")
            if maxvalue is None:
                maxvalue = slider_filter["maximum"]
            elif k == "cloud_cover":
                maxvalue *= 100.0
        else:
            minvalue = slider_filter["minimum"]
            maxvalue = slider_filter["maximum"]
        s += (
            f'{slider_filter["title"]}: {minvalue}{slider_filter["suffix"]}'
            f' - {maxvalue}{slider_filter["suffix"]}\n'
        )

    filters = filters_from_request(request, filter_type="PermissionFilter")
    if filters:
        s += (
            "Only show images you can download:"
            f" {'assets:download' in filters[0]['config']}\n"
        )
    else:
        s += "Only show images you can download: False\n"
    filters = filters_from_request(request, "ground_control")
    if filters:
        s += (
            "Only show images with ground control:"
            f" {'assets:download' in filters[0]['config']}\n"
        )
    else:
        s += "Only show images with ground control: False\n"

    filters = filters_from_request(request, "id")
    if filters:
        s += f'IDs: {",".join(filters[0]["config"])}'

    return s


class PlanetFilterMixin(QObject):
    """
    Base mixin for Planet API filter control widget groupings.

    Widget groupings should be a QFrame (no margins or border) with a
    QgsScrollArea inside it layout, then widgets inside scroll area's layouot.
    QgsScrollArea is important, as it keeps scrolling input devices from
    changing control widget's values (an annoying Qt 'feature').
    """

    def __init__(self, parent=None, plugin=None):
        super().__init__(parent=parent)

        self._plugin = plugin

    def _show_message(self, message, level=Qgis.Info, duration=None, show_more=None):
        self._plugin.show_message(message, level, duration, show_more)


class PlanetAOIFilter(AOI_FILTER_BASE, AOI_FILTER_WIDGET, PlanetFilterMixin):

    filtersChanged = pyqtSignal()
    savedSearchSelected = pyqtSignal(object)
    zoomToAOIRequested = pyqtSignal()

    def __init__(
        self,
        parent=None,
        plugin=None,
        color=MAIN_AOI_COLOR,
    ):
        super().__init__(parent=parent)
        self._plugin = plugin

        self.setupUi(self)

        self.emitFiltersChanged = False

        self.color = color

        self._aoi_box = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
        self._aoi_box.setFillColor(QColor(0, 0, 0, 0))
        self._aoi_box.setStrokeColor(color)
        self._aoi_box.setWidth(3)
        self._aoi_box.setLineStyle(Qt.DashLine)

        self._canvas: QgsMapCanvas = iface.mapCanvas()
        # This may later be a nullptr, if no active tool when queried
        self._cur_maptool = None

        self.leAOI.textChanged["QString"].connect(self.filters_changed)
        self.leAOI.textEdited["QString"].connect(self.validate_edited_aoi)

        self._setup_tool_buttons()

        # Extent line edit tools
        self.btnZoomToAOI.clicked.connect(self.zoom_to_aoi)
        self.btnCopyAOI.clicked.connect(self.copy_aoi_to_clipboard)

        self.p_client = PlanetClient.getInstance()

    def reset_aoi_box(self):
        self.leAOI.setText("")
        if self._aoi_box:
            self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)

    def filters(self):
        filters = []
        if self.leAOI.text():
            try:
                qgsgeom = qgsgeometry_from_geojson(self.leAOI.text())
                if not qgsgeom.isEmpty():
                    geom_json = json.loads(qgsgeom.asJson())
                    filters.append(geom_filter(geom_json))
                else:
                    self._show_message(
                        "AOI not valid GeoJSON polygon", level=Qgis.Warning, duration=10
                    )
            except Exception:
                self._show_message(
                    "AOI not valid JSON", level=Qgis.Warning, duration=10
                )
            finally:
                return filters

    def filters_as_json(self):
        filters = []
        if self.leAOI.text():
            filters.append(self.leAOI.text())

        return filters

    def set_from_request(self, request):
        self.emitFiltersChanged = False
        filters = filters_from_request(request, "geometry")
        if filters:
            geom = filters[0]["config"]
            txt = json.dumps(geom)
            self.leAOI.setText(txt)
        else:
            self.leAOI.setText("")
        self.emitFiltersChanged = True

    @pyqtSlot("QString")
    def filters_changed(self, value):
        if self.emitFiltersChanged:
            self.filtersChanged.emit()

    @pyqtSlot()
    def clean_up(self):
        self.reset_aoi_box()

    def _setup_tool_buttons(self):
        extent_menu = QMenu(self)

        canvas_act = QAction("Current visible extent", extent_menu)
        canvas_act.triggered[bool].connect(self.aoi_from_current_extent)
        extent_menu.addAction(canvas_act)

        active_act = QAction("Active map layer extent", extent_menu)
        active_act.triggered[bool].connect(self.aoi_from_active_layer_extent)
        extent_menu.addAction(active_act)

        full_act = QAction("All map layers extent", extent_menu)
        full_act.triggered[bool].connect(self.aoi_from_full_extent)
        extent_menu.addAction(full_act)

        self.btnExtent.setMenu(extent_menu)

        # Also show menu on click, to keep disclosure triangle visible
        self.btnExtent.clicked.connect(self.btnExtent.showMenu)

        draw_menu = QMenu(self)

        box_act = QAction("Rectangle", draw_menu)
        box_act.triggered[bool].connect(self.aoi_from_box)
        draw_menu.addAction(box_act)

        circle_act = QAction("Circle", draw_menu)
        circle_act.triggered[bool].connect(self.aoi_from_circle)
        draw_menu.addAction(circle_act)

        polygon_act = QAction("Polygon", draw_menu)
        polygon_act.triggered[bool].connect(self.aoi_from_polygon)
        draw_menu.addAction(polygon_act)

        self.btnDraw.setMenu(draw_menu)
        # Also show menu on click, to keep disclosure triangle visible
        self.btnDraw.clicked.connect(self.btnDraw.showMenu)

        selection_menu = QMenu(self)

        #self.single_select_act = QAction("Single feature", selection_menu)
        #self.single_select_act.triggered[bool].connect(self.aoi_from_feature)
        #selection_menu.addAction(self.single_select_act)

        self.multi_polygon_select_act = QAction("Selected features", selection_menu)
        self.multi_polygon_select_act.triggered[bool].connect(
            self.aoi_from_multiple_polygons
        )
        selection_menu.addAction(self.multi_polygon_select_act)

        self.bound_select_act = QAction(
            "Selected features (bounding box)", selection_menu
        )
        self.bound_select_act.triggered[bool].connect(self.aoi_from_bound)
        selection_menu.addAction(self.bound_select_act)

        self.btnSelection.setMenu(selection_menu)
        # Also show menu on click, to keep disclosure triangle visible
        self.btnSelection.clicked.connect(self._toggle_selection_tools)
        self.btnSelection.clicked.connect(self.btnSelection.showMenu)

        upload_menu = QMenu(self)

        upload_act = QAction("Upload vector layer file", upload_menu)
        upload_act.triggered[bool].connect(self.upload_file)
        upload_menu.addAction(upload_act)

        upload_bb_act = QAction("Upload vector layer file (bounding box)", upload_menu)
        upload_bb_act.triggered[bool].connect(self.upload_file_bb)
        upload_menu.addAction(upload_bb_act)

        self.btnUpload.setMenu(upload_menu)
        self.btnUpload.clicked.connect(self.btnUpload.showMenu)

    def upload_file_bb(self):
        """Loads a vector file provided by a user. Considers embedded gpkg files.
        Checks if the layer(s) are valid. Then calls the function to calculate the
        bounding box AOI.
        """
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select AOI file", "", "All files(*.*)"
        )
        if filename:
            layer = QgsVectorLayer(filename, "")
            embedded_layers = []
            if len(layer.dataProvider().subLayers()) > 1:
                # If the file contains embedded layers
                # Therefore need to process each layer
                for subLayer in layer.dataProvider().subLayers():
                    sublayer_name = subLayer.split("!!::!!")[1]
                    embedded_file = "{}|layername={}".format(filename, sublayer_name)
                    embedded_layer = QgsVectorLayer(embedded_file, "")
                    if not embedded_layer.isValid():
                        # Skip invalid layers
                        continue
                    elif not isinstance(layer, QgsVectorLayer):
                        # Skip non-vector layers
                        continue
                    elif embedded_layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                        # Only add the embedded layer if it's a valid polygon layer
                        embedded_layers.append(embedded_layer)

                if len(embedded_layers) == 0:
                    # If none of the embedded layers are polygons
                    self._show_message(
                        "None of the embedded layers are valid polygons",
                        level=Qgis.Warning,
                        duration=10,
                    )
                    return
                self.aoi_bb_from_layer(embedded_layers)
            else:
                # No embedded layers in the file
                if not layer.isValid():
                    self._show_message("Invalid layer", level=Qgis.Warning, duration=10)
                    return
                elif not isinstance(layer, QgsVectorLayer):
                    self._show_message(
                        "Active layer must be a vector layer.",
                        level=Qgis.Warning,
                        duration=10,
                    )
                    return
                elif layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                    # If the geometry is not polygon
                    self._show_message(
                        "AOI geometry type invalid", level=Qgis.Warning, duration=10
                    )
                    return
                else:
                    self.aoi_bb_from_layer([layer])

    def upload_file(self):
        """Loads a vector file provided by a user. Considers embedded gpkg files.
        Checks if the layer(s) are valid. Then calls the function to calculate the
        AOI.
        """
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select AOI file", "", "All files(*.*)"
        )
        if filename:
            layer = QgsVectorLayer(filename, "")
            embedded_layers = []
            if len(layer.dataProvider().subLayers()) > 1:
                # If the file contains embedded layers
                # Therefore need to process each layer
                for subLayer in layer.dataProvider().subLayers():
                    sublayer_name = subLayer.split("!!::!!")[1]
                    embedded_file = "{}|layername={}".format(filename, sublayer_name)
                    embedded_layer = QgsVectorLayer(embedded_file, "")
                    if not embedded_layer.isValid():
                        # Skip invalid layers
                        continue
                    elif not isinstance(layer, QgsVectorLayer):
                        # Skip non-vector layers
                        continue
                    elif embedded_layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                        # Only add the embedded layer if it's a valid polygon layer
                        embedded_layers.append(embedded_layer)

                if len(embedded_layers) == 0:
                    # If none of the embedded layers are polygons
                    self._show_message(
                        "None of the embedded layers are valid polygons",
                        level=Qgis.Warning,
                        duration=10,
                    )
                    return
                self.aoi_from_layer(embedded_layers)
            else:
                # No embedded layers in the file
                if not layer.isValid():
                    self._show_message("Invalid layer", level=Qgis.Warning, duration=10)
                    return
                elif not isinstance(layer, QgsVectorLayer):
                    self._show_message(
                        "Active layer must be a vector layer.",
                        level=Qgis.Warning,
                        duration=10,
                    )
                    return
                elif layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                    # If the geometry is not polygon
                    self._show_message(
                        "AOI geometry type invalid", level=Qgis.Warning, duration=10
                    )
                    return
                else:
                    self.aoi_from_layer([layer])

    def show_aoi_area_size(self):
        """Displays the aoi area size in square kilometers."""

        area_size_sqkm = self.calculate_aoi_area()

        formatted_area_sq = "{:,}".format(round(area_size_sqkm, 2))

        self.laAOISize.setText(f"Total AOI area (sqkm): {formatted_area_sq}")

    def calculate_aoi_area(self):
        """Calculate the current aoi area in square kilometers"""

        geometry = self.aoi_as_4326_geom()
        area = QgsDistanceArea()
        area.setSourceCrs(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().transformContext(),
        )
        area.setEllipsoid(QgsProject.instance().ellipsoid())
        geometry_area = area.measureArea(geometry)
        geometry_area_sq = area.convertAreaMeasurement(
            geometry_area, QgsUnitTypes.AreaSquareKilometers
        )

        return round(geometry_area_sq, 2)

    def aoi_from_layer(self, layers):
        """Determine AOI from polygons. Considers all polygons.
        :param layers: List of QgsVectorLayers
        :type layers: list
        """
        multipart_polygon = None
        for layer in layers:
            features = layer.getFeatures()
            # Creates the multipart polygon which will be used for the searches
            for feature in features:
                geom = feature.geometry()
                # Skips features with invalid geometries
                if geom.isNull():
                    continue
                elif geom.isEmpty():
                    continue
                elif not geom.isGeosValid():
                    continue

                transform = QgsCoordinateTransform(
                    layer.crs(),
                    QgsCoordinateReferenceSystem("EPSG:4326"),
                    QgsProject.instance(),
                )

                try:
                    geom.transform(transform)
                except QgsCsException:
                    self._show_message(
                        "Could not convert AOI to EPSG:4326",
                        level=Qgis.Warning,
                        duration=10,
                    )
                    return

                if multipart_polygon is None:
                    multipart_polygon = QgsGeometry(geom)
                else:
                    multipart_polygon.addPartGeometry(geom)

        if multipart_polygon is not None:
            # Sets the features to the canvas
            geom_json = multipart_polygon.asJson(precision=6)
            self._aoi_box.setToGeometry(multipart_polygon)
            self.leAOI.setText(geom_json)

            log.debug("AOI set to layer")

            self.zoom_to_aoi()
            self.show_aoi_area_size()
        else:
            # There were no features to process
            self._show_message(
                "Layer(s) contains no valid features", level=Qgis.Warning, duration=10
            )
            return

    def aoi_bb_from_layer(self, layers):
        """Determine AOI as a bounding box from polygons. Considers all polygons.
        :param layers: List of QgsVectorLayers
        :type layers: list
        """
        multipart_polygon = None
        for layer in layers:
            features = layer.getFeatures()
            # Creates the multipart polygon which will be used for the searches
            for feature in features:
                geom = feature.geometry()
                # Skips features with invalid geometries
                if geom.isNull():
                    continue
                elif geom.isEmpty():
                    continue
                elif not geom.isGeosValid():
                    continue

                transform = QgsCoordinateTransform(
                    layer.crs(),
                    QgsCoordinateReferenceSystem("EPSG:4326"),
                    QgsProject.instance(),
                )

                try:
                    geom.transform(transform)
                except QgsCsException:
                    self._show_message(
                        "Could not convert AOI to EPSG:4326",
                        level=Qgis.Warning,
                        duration=10,
                    )
                    return

                if multipart_polygon is None:
                    multipart_polygon = QgsGeometry(geom)
                else:
                    multipart_polygon.addPartGeometry(geom)

        if multipart_polygon is not None:
            bounding_box = multipart_polygon.boundingBox()
            bb_polygon = bounding_box.asWktPolygon()
            geom_bb = QgsGeometry().fromWkt(bb_polygon)

            geom_json = geom_bb.asJson(precision=6)

            self._aoi_box.setToGeometry(geom_bb)

            self.leAOI.setText(geom_json)

            log.debug("AOI set to layer")

            self.zoom_to_aoi()
            self.show_aoi_area_size()
        else:
            # There were no features to process
            self._show_message(
                "Layer(s) contains no valid features", level=Qgis.Warning, duration=10
            )
            return

    def _toggle_selection_tools(self):
        active_layer = iface.activeLayer()
        is_vector = isinstance(active_layer, QgsVectorLayer)
        if is_vector and active_layer.selectedFeatureCount():
            if active_layer.selectedFeatureCount() > 1:
                self.single_select_act.setEnabled(False)
                self.bound_select_act.setEnabled(True)
            elif active_layer.selectedFeatureCount():
                self.single_select_act.setEnabled(True)
                self.bound_select_act.setEnabled(False)
            else:
                self.single_select_act.setEnabled(False)
                self.bound_select_act.setEnabled(False)
        else:
            self.single_select_act.setEnabled(False)
            self.bound_select_act.setEnabled(False)

    @pyqtSlot()
    def aoi_from_current_extent(self):
        """Return current map extent as geojson transformed to EPSG:4326"""
        canvas = iface.mapCanvas()
        transform = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance(),
        )

        canvas_extent: QgsRectangle = canvas.extent()
        try:
            transform_extent = transform.transformBoundingBox(canvas_extent)
        except QgsCsException:
            self._show_message(
                "Could not convert AOI to EPSG:4326", level=Qgis.Warning, duration=10
            )
            return
        geom_extent = QgsGeometry.fromRect(transform_extent)
        extent_json = geom_extent.asJson(precision=6)

        self._aoi_box.setToGeometry(QgsGeometry.fromRect(canvas.extent()))

        self.leAOI.setText(extent_json)

        log.debug("AOI set to canvas extent")

        self.zoom_to_aoi()
        self.show_aoi_area_size()

    @pyqtSlot()
    def aoi_from_active_layer_extent(self):
        """Return active map layer extent as geojson transformed to EPSG:4326"""
        map_layer: QgsMapLayer = iface.activeLayer()
        if map_layer is None:
            log.debug("No active layer selected, skipping AOI extent")
            return

        if not map_layer.isValid():
            log.debug("Active map layer invalid, skipping AOI extent")
            return

        transform = QgsCoordinateTransform(
            map_layer.crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance(),
        )

        ml_extent: QgsRectangle = map_layer.extent()
        try:
            transform_extent = transform.transformBoundingBox(ml_extent)
        except QgsCsException:
            self._show_message(
                "Could not convert AOI to EPSG:4326", level=Qgis.Warning, duration=10
            )
            return
        geom_extent = QgsGeometry.fromRect(transform_extent)
        extent_json = geom_extent.asJson(precision=6)

        self.leAOI.setText(extent_json)

        log.debug("AOI set to active layer extent")

        self.zoom_to_aoi()
        self.show_aoi_area_size()

    @pyqtSlot()
    def aoi_from_full_extent(self):
        """Return full data map extent as geojson transformed to EPSG:4326"""
        canvas = iface.mapCanvas()

        transform = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance(),
        )

        canvas_extent: QgsRectangle = canvas.fullExtent()
        if canvas_extent.isNull():  # Canvas not yet initialized
            return
        try:
            transform_extent = transform.transformBoundingBox(canvas_extent)
        except QgsCsException:
            self._show_message(
                "Could not convert AOI to EPSG:4326", level=Qgis.Warning, duration=10
            )
            return
        geom_extent = QgsGeometry.fromRect(transform_extent)
        extent_json = geom_extent.asJson(precision=6)
        self._aoi_box.setToGeometry(QgsGeometry.fromRect(canvas_extent))

        self.leAOI.setText(extent_json)

        log.debug("AOI set to full data extent")

        self.zoom_to_aoi()
        self.show_aoi_area_size()

    @pyqtSlot()
    def aoi_from_box(self):
        self._cur_maptool: QgsMapTool = self._canvas.mapTool()
        self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)
        aoi_draw = PlanetExtentMapTool(iface.mapCanvas())
        iface.mapCanvas().setMapTool(aoi_draw)
        aoi_draw.extentSelected.connect(self.set_draw_aoi)

    @pyqtSlot()
    def aoi_from_circle(self):
        self._cur_maptool: QgsMapTool = self._canvas.mapTool()
        self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)
        aoi_draw = PlanetCircleMapTool(iface.mapCanvas())
        iface.mapCanvas().setMapTool(aoi_draw)
        aoi_draw.circleSelected.connect(self.set_draw_aoi)

    @pyqtSlot()
    def aoi_from_polygon(self):
        self._cur_maptool: QgsMapTool = self._canvas.mapTool()
        self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)
        aoi_draw = PlanetPolyMapTool(iface.mapCanvas())
        iface.mapCanvas().setMapTool(aoi_draw)
        aoi_draw.polygonSelected.connect(self.set_draw_aoi)

    @pyqtSlot(object)
    def set_draw_aoi(self, aoi):
        transform = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance(),
        )

        aoi_json = None

        if isinstance(aoi, QgsRectangle):
            aoi_geom = QgsGeometry().fromRect(aoi)
            self._aoi_box.setToGeometry(aoi_geom)
            aoi_geom.transform(transform)
            aoi_json = aoi_geom.asJson(precision=6)

        if isinstance(aoi, QgsGeometry):
            self._aoi_box.setToGeometry(aoi)
            # TODO: validate geom is less than 500 vertices
            aoi.transform(transform)
            aoi_json = aoi.asJson(precision=6)

        if aoi_json:
            self.leAOI.setText(aoi_json)

            self._show_message("AOI set to drawn figure")
            self.zoom_to_aoi()
            self.show_aoi_area_size()
            if self._cur_maptool is not None:
                # Restore previously used maptool
                self._canvas.setMapTool(self._cur_maptool)
                self._cur_maptool = None
            else:
                # Fallback to activating pan tool
                iface.actionPan().trigger()
        else:
            self._show_message("AOI unable to be set", level=Qgis.Warning, duration=10)

    # @pyqtSlot()
    # def aoi_from_feature(self):
    #     layer = iface.activeLayer()
    #     if not isinstance(layer, QgsVectorLayer):
    #         self._show_message(
    #             "Active layer must be a vector layer.", level=Qgis.Warning, duration=10
    #         )
    #         return
    #
    #     if layer.selectedFeatureCount() > 1:
    #         self._show_message(
    #             "More than 1 feature. Searching by bbox.",
    #             level=Qgis.Warning,
    #             duration=10,
    #         )
    #         self.aoi_from_bound()
    #         return
    #     elif layer.selectedFeatureCount() < 1:
    #         self._show_message("No features selected.", level=Qgis.Warning, duration=10)
    #         return
    #
    #     selected: QgsFeature = layer.selectedFeatures()[0]
    #     geom: QgsGeometry = selected.geometry()
    #
    #     if geom.constGet().vertexCount() > 500:
    #         self._show_message(
    #             "More than 500 vertices. Searching by bbox.",
    #             level=Qgis.Warning,
    #             duration=10,
    #         )
    #         self.aoi_from_bound()
    #         return
    #
    #     trans_layer = QgsCoordinateTransform(
    #         layer.sourceCrs(),
    #         QgsCoordinateReferenceSystem("EPSG:4326"),
    #         QgsProject.instance(),
    #     )
    #
    #     trans_canvas = QgsCoordinateTransform(
    #         QgsCoordinateReferenceSystem("EPSG:4326"),
    #         QgsProject.instance().crs(),
    #         QgsProject.instance(),
    #     )
    #
    #     # geom.transform(transform)
    #     geom.transform(trans_layer)
    #     geom_json = geom.asJson(precision=6)
    #     self.leAOI.setText(geom_json)
    #
    #     geom.transform(trans_canvas)
    #     self._aoi_box.setToGeometry(geom, QgsCoordinateReferenceSystem("EPSG:4326"))
    #     self.zoom_to_aoi()
    #
    #     self.show_aoi_area_size()

    def aoi_from_multiple_polygons(self):
        layer = iface.activeLayer()
        if not layer.isValid():
            self._show_message("Invalid layer", level=Qgis.Warning, duration=10)
            return
        if not isinstance(layer, QgsVectorLayer):
            self._show_message(
                "Active layer must be a vector layer.", level=Qgis.Warning, duration=10
            )
            return

        feature_count = layer.featureCount()
        if feature_count == 0:
            self._show_message(
                "Layer contains no features", level=Qgis.Warning, duration=10
            )
            return
        else:
            selected_feature_count = layer.selectedFeatureCount()
            if selected_feature_count == 0:
                # If no features is selected, all layer will be taken into account
                features = layer.getFeatures()
            else:
                # Only selected features will be considered
                features = layer.selectedFeatures()

            # Creates the multipart polygon which will be used for the searches
            multipart_polygon = None
            for feature in features:
                geom = feature.geometry()

                transform = QgsCoordinateTransform(
                    layer.crs(),
                    QgsCoordinateReferenceSystem("EPSG:4326"),
                    QgsProject.instance(),
                )

                try:
                    geom.transform(transform)
                except QgsCsException:
                    self._show_message(
                        "Could not convert AOI to EPSG:4326",
                        level=Qgis.Warning,
                        duration=10,
                    )
                    return

                if multipart_polygon is None:
                    multipart_polygon = QgsGeometry(geom)
                else:
                    multipart_polygon.addPartGeometry(geom)

            # Sets the features to the canvas
            geom_json = multipart_polygon.asJson(precision=6)
            self._aoi_box.setToGeometry(multipart_polygon)
            self.leAOI.setText(geom_json)

            log.debug("AOI set to layer")

            self.zoom_to_aoi()
            self.show_aoi_area_size()

    @pyqtSlot()
    def aoi_from_bound(self):
        layer = iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer):
            self._show_message(
                "Active layer must be a vector layer.", level=Qgis.Warning, duration=10
            )
            return

        all_features = False
        if layer.selectedFeatureCount() == 0:
            # If no features were selected, all features are considered
            # Required to do the selection for determining the bounding box
            layer.selectAll()
            all_features = True

        bbox = layer.boundingBoxOfSelected()
        if all_features:
            # Deselect all features for the case when the user had no features selected
            layer.removeSelection()

        trans_layer = QgsCoordinateTransform(
            layer.sourceCrs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance(),
        )

        trans_canvas = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().crs(),
            QgsProject.instance(),
        )

        transform_bbox = trans_layer.transformBoundingBox(bbox)
        geom_bbox = QgsGeometry.fromRect(transform_bbox)
        bbox_json = geom_bbox.asJson(precision=6)

        self.leAOI.setText(bbox_json)

        bbox_canvas = trans_canvas.transformBoundingBox(transform_bbox)
        self._aoi_box.setToGeometry(QgsGeometry.fromRect(bbox_canvas))

        self.zoom_to_aoi()
        self.show_aoi_area_size()

    def hide_aoi_if_matches_geom(self, geom):
        color = (
            QColor(0, 0, 0, 0)
            if self._aoi_box.asGeometry().equals(geom)
            else self.color
        )
        self._aoi_box.setStrokeColor(color)

    def show_aoi(self):
        if self._aoi_box is not None:
            self._aoi_box.setStrokeColor(self.color)

    def aoi_geom(self):
        if self._aoi_box is not None:
            return self._aoi_box.asGeometry()

    def aoi_as_4326_geom(self):
        transform = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance(),
        )
        geom = self.aoi_geom()
        if geom is not None:
            geom.transform(transform)
        return geom

    @pyqtSlot()
    def zoom_to_aoi(self):
        if not self.leAOI.text():
            log.debug("No AOI defined, skipping zoom to AOI")
            return

        geom: QgsGeometry = qgsgeometry_from_geojson(self.leAOI.text())
        if geom.isEmpty():
            self._show_message(
                "AOI GeoJSON geometry invalid", level=Qgis.Warning, duration=10
            )
            return

        self._aoi_box.setToGeometry(geom, QgsCoordinateReferenceSystem("EPSG:4326"))

        self.show_aoi()

        zoom_canvas_to_aoi(self.leAOI.text())

        self.zoomToAOIRequested.emit()

    @pyqtSlot()
    def copy_aoi_to_clipboard(self):
        if not self.leAOI.text():
            log.debug("No AOI defined, skipping zoom to AOI")
            return

        try:
            json_obj = json.loads(self.leAOI.text())
        except ValueError:
            return

        json_geom_txt = json.dumps(json_obj, indent=2)

        cb = QgsApplication.clipboard()
        cb.setText(json_geom_txt)

        self._show_message("AOI copied to clipboard")

    @pyqtSlot()
    def validate_edited_aoi(self):
        json_txt = self.leAOI.text()
        if not json_txt:
            self.reset_aoi_box()
            self.show_aoi_area_size()
            log.debug("No AOI defined, skipping validation")
            return

        try:
            json_obj = json.loads(json_txt)
        except ValueError:
            self._show_message(
                "AOI GeoJSON is invalid", level=Qgis.Warning, duration=10
            )
            return

        try:
            json_geom = geometry_from_json(json_obj)
        except Exception:
            json_geom = None

        if not json_geom:
            self._show_message(
                "AOI GeoJSON geometry invalid", level=Qgis.Warning, duration=10
            )
            return

        geom: QgsGeometry = qgsgeometry_from_geojson(json_geom)
        self._aoi_box.setToGeometry(geom, QgsCoordinateReferenceSystem("EPSG:4326"))

        self.leAOI.blockSignals(True)
        self.leAOI.setText(json.dumps(json_geom))
        self.leAOI.blockSignals(False)

        self.zoom_to_aoi()
        self.show_aoi_area_size()


class PlanetDailyFilter(DAILY_BASE, DAILY_WIDGET, PlanetFilterMixin):
    """ """

    filtersChanged = pyqtSignal()
    updateLegacySearch = pyqtSignal()

    ID_PATTERN = [
        r"\d{8,8}_\d{6,6}",
        r"\d{4,4}-\d{2,2}-\d{2,2}",
        r"LC",
        r"S2",
    ]

    id_regex = [re.compile(pattern) for pattern in ID_PATTERN]

    def __init__(self, parent=None, plugin=None):
        super().__init__(parent=parent)
        self.setupUi(self)
        self._plugin = plugin

        self.emitFiltersChanged = True

        # Set up checkboxes for old sources (for legacy saved searches)
        item_types = {
            k: v
            for k, v in PlanetClient.getInstance().item_types_names().items()
            if k != "PSScene"
        }
        row_total = floor(len(item_types) / 2)
        row = col = 0
        gl = QGridLayout(self.oldSourcesWidget)
        gl.setContentsMargins(0, 0, 0, 0)
        for a, b in item_types.items():
            # Strip ' Scene' to reduce horizontal width of 2-column layout, except for SkySat
            name = b.replace(" Scene", "") if b != "SkySat Scene" else b
            cb = QCheckBox(name, parent=self.oldSourcesWidget)
            cb.setProperty("api-name", a)
            gl.addWidget(cb, row, col)
            row += 1
            if row > row_total:
                row = 0
                col += 1
        self.oldSourcesWidget.setLayout(gl)

        self.itemTypeCheckBoxes = [
            self.chkPlanetScope,
            self.chkPlanetScopeOrtho,
            self.chkRapidEyeScene,
            self.chkRapidEyeOrtho,
            self.chkSkySatScene,
            self.chkSkySatCollect,
            self.chkLandsat,
            self.chkSentinel,
        ]

        for source in self.itemTypeCheckBoxes:
            apiname = source.property("api-name")
            if apiname is not None:
                source.stateChanged.connect(self.filtersChanged)

        self.chkYellow.stateChanged.connect(self._yellowFilterToggled)
        self.chkNIR.stateChanged.connect(self._nirFilterToggled)
        self.chkPlanetScope.stateChanged.connect(self._pssceneToggled)
        layout = QVBoxLayout()
        layout.setMargin(0)
        self.legacyWarningWidget = LegacyWarningWidget()
        self.legacyWarningWidget.updateLegacySearch.connect(
            self.updateLegacySearch.emit
        )
        layout.addWidget(self.legacyWarningWidget)
        self.frameWarningLegacySearch.setLayout(layout)
        self.frameWarningLegacySearch.setVisible(False)

        self.startDateEdit.valueChanged["QDateTime"].connect(self.filtersChanged)
        self.startDateEdit.valueChanged["QDateTime"].connect(self.change_date_vis)
        self.endDateEdit.valueChanged["QDateTime"].connect(self.filtersChanged)
        self.endDateEdit.valueChanged["QDateTime"].connect(self.change_date_vis)

        current_day = QDateTime().currentDateTimeUtc()
        self.startDateEdit.setDateTime(current_day.addMonths(-3))
        self.endDateEdit.setDateTime(current_day)

        self.leStringIDs.textChanged.connect(self.filters_changed)

        for slider in slider_filters:
            sliderWidget = PlanetExplorerRangeSlider(**slider)
            self.frameRangeSliders.layout().addWidget(sliderWidget)
            sliderWidget.rangeChanged.connect(self.filters_changed)

        self.chkGroundControl.stateChanged[int].connect(self.filters_changed)
        self.chkFullCatalog.stateChanged[int].connect(self.filters_changed)

    def _yellowFilterToggled(self):
        if self.chkYellow.isChecked():
            self.chkNIR.setChecked(True)

    def _nirFilterToggled(self):
        if not self.chkNIR.isChecked():
            self.chkYellow.setChecked(False)

    def _pssceneToggled(self):
        self.planetScopeWidget.setEnabled(self.chkPlanetScope.isChecked())

    def sources(self):
        nir = self.chkNIR.isChecked()
        yellow = self.chkYellow.isChecked()
        surface = self.chkSurfaceReflectance.isChecked()
        checked_sources = {}
        for sourceWidget in self.itemTypeCheckBoxes:
            if sourceWidget.isChecked():
                apiname = sourceWidget.property("api-name")
                if apiname == "PSScene":
                    checked_sources[apiname] = self._asset_filter(nir, yellow, surface)
                elif apiname is not None:
                    checked_sources[apiname] = None
        return checked_sources

    def _asset_filter(self, nir, yellow, surface):
        if nir:
            if yellow:
                assets = PlanetClient.getInstance().psscene_asset_types_for_nbands(8)
            else:
                assets = PlanetClient.getInstance().psscene_asset_types_for_nbands(4)
        else:
            assets = PlanetClient.getInstance().psscene_asset_types_for_nbands(3)
        if surface:
            assets = [a for a in assets if "_sr" in a]
        return assets

    def set_min_enddate(self):
        self.endDateEdit.setMinimumDate(self.startDateEdit.date())

    def set_max_startdate(self):
        self.startDateEdit.setMaximumDate(self.endDateEdit.date())

    def change_date_vis(self):
        dates = self.frameDates.findChildren(QgsDateTimeEdit)
        for date in dates:
            if date.dateTime().isNull():
                date.lineEdit().setEchoMode(QLineEdit.NoEcho)
            else:
                date.lineEdit().setEchoMode(QLineEdit.Normal)

    def filters(self):
        populated_filters = []

        start_qdate = None
        end_qdate = None
        start_date = None
        end_date = None
        if not self.startDateEdit.dateTime().isNull():
            start_qdate = self.startDateEdit.date()
            start_date = start_qdate.toString(Qt.ISODate)
        if not self.endDateEdit.dateTime().isNull():
            end_qdate = self.endDateEdit.date().addDays(1)
            end_date = end_qdate.toString(Qt.ISODate)

        if start_qdate and end_qdate:
            if start_qdate < end_qdate:
                date_filter = date_range("acquired", gte=start_date, lte=end_date)
                populated_filters.append(date_filter)
            else:
                self._show_message(
                    "Start date later than end date.", level=Qgis.Warning, duration=10
                )
        elif start_date:
            start_date_filter = date_range("acquired", gte=start_date)
            populated_filters.append(start_date_filter)
        elif end_date:
            end_date_filter = date_range("acquired", lte=end_date)
            populated_filters.append(end_date_filter)

        # TODO: double check actual domain/range of sliders
        sliders = self.frameRangeSliders.findChildren(PlanetExplorerRangeSlider)
        for slider in sliders:
            slide_filter = None
            range_low, range_high = slider.range()
            if slider.filter_key == "cloud_cover":
                range_low /= 100.0
                range_high /= 100.0
                slider_max = 1.0
            else:
                slider_max = slider.max
            if range_low != slider.min and range_high != slider_max:
                slide_filter = range_filter(
                    slider.filter_key, gte=range_low, lte=range_high
                )
            elif range_low != slider.min:
                slide_filter = range_filter(slider.filter_key, gte=range_low)
            elif range_high != slider_max:
                slide_filter = range_filter(slider.filter_key, lte=range_high)
            if slide_filter:
                populated_filters.append(slide_filter)

        s_ids = self.leStringIDs.text()
        if s_ids:
            ids_actual = []
            s_ids.replace(" ", "")
            for s_id in s_ids.split(","):
                for text_chunk in s_id.split(":"):
                    for pattern in self.id_regex:
                        if pattern.match(text_chunk):
                            ids_actual.append(text_chunk)

            if ids_actual:
                s_ids_list = ["id"]
                s_ids_list.extend(ids_actual)
                string_ids_filter = string_filter(*s_ids_list)
                populated_filters.append(string_ids_filter)
            else:
                self._show_message(
                    "No valid ID present", level=Qgis.Warning, duration=10
                )

        instruments = []
        for chk in [self.chkPs2, self.chkPs2Sd, self.chkPsbSd]:
            if chk.isChecked():
                instruments.append(chk.property("api-name"))
        if instruments:
            instrument_filter = string_filter("instrument", *instruments)
            populated_filters.append(instrument_filter)

        server_filters = []
        if not self.chkFullCatalog.isChecked():
            dl_permission_filter = permission_filter("assets:download")
            server_filters.append(dl_permission_filter)

        if self.chkStandardQuality.isChecked():
            quality_filter = string_filter("quality_category", "standard")
            server_filters.append(quality_filter)

        # Ground_control can be 'true', 'false, or a numeric value
        # Safest to check for not 'false'
        if self.chkGroundControl.isChecked():
            gc_filter = not_filter(string_filter("ground_control", "false"))
            server_filters.append(gc_filter)

        server_filters.extend(
            [f for f in populated_filters if f["field_name"] not in LOCAL_FILTERS]
        )
        local_filters = [
            f for f in populated_filters if f["field_name"] in LOCAL_FILTERS
        ]
        return server_filters, local_filters

    def set_from_request(self, request):
        """
        We assume here that the request has the structure of requests created
        with the plugin. We are not fully parsing the request to analize it,
        but instead making that assumption to simplify things.
        """
        self.emitFiltersChanged = False
        sources = request["item_types"]
        for checkbox in self.itemTypeCheckBoxes:
            checkbox.setChecked(checkbox.property("api-name") in sources)

        asset_filters = filters_from_request(request, filter_type="AssetFilter")
        self.chkNIR.setChecked(False)
        self.chkYellow.setChecked(False)
        self.chkSurfaceReflectance.setChecked(False)
        if asset_filters:
            all_assets = []
            used_assets = []
            for item_type in sources:
                all_assets.extend(
                    PlanetClient.getInstance().asset_types_for_item_type(item_type)
                )
            for filt in asset_filters:
                used_assets.extend(filt.get("config", []))
            used_bands = []
            display_names = []
            for a in all_assets:
                if a["id"] in used_assets and "bands" in a:
                    used_bands.append(a["bands"])
                    display_names.append(a.get("display_name", ""))
            nir = all([{"name": "nir"} in bands for bands in used_bands])
            yellow = all([{"name": "yellow"} in bands for bands in used_bands])
            surface = all(["surface reflectance" in name for name in display_names])
            self.chkNIR.setChecked(nir)
            self.chkYellow.setChecked(yellow)
            self.chkSurfaceReflectance.setChecked(surface)

        filters = filters_from_request(request, "acquired")
        if filters:
            gte = filters[0]["config"].get("gte")
            if gte is not None:
                self.startDateEdit.setDateTime(QDateTime.fromString(gte, Qt.ISODate))
            lte = filters[0]["config"].get("lte")
            if lte is not None:
                self.endDateEdit.setDateTime(QDateTime.fromString(lte, Qt.ISODate))
        sliders = self.frameRangeSliders.findChildren(PlanetExplorerRangeSlider)
        for slider in sliders:
            filters = filters_from_request(request, slider.filter_key)
            if filters:
                gte = filters[0]["config"].get("gte")
                if gte is None:
                    slider.setRangeLow(slider.min)
                else:
                    if slider.filter_key == "cloud_cover":
                        gte *= 100.0
                    slider.setRangeLow(gte)
                lte = filters[0]["config"].get("lte")
                if lte is None:
                    slider.setRangeHigh(slider.max)
                else:
                    if slider.filter_key == "cloud_cover":
                        lte *= 100.0
                    slider.setRangeHigh(lte)
            else:
                slider.setRangeLow(slider.min)
                slider.setRangeHigh(slider.max)
        filters = filters_from_request(request, filter_type="PermissionFilter")
        if filters:
            self.chkFullCatalog.setChecked(
                "assets:download" not in filters[0]["config"]
            )
        else:
            self.chkFullCatalog.setChecked(False)
        filters = filters_from_request(request, "ground_control")
        self.chkGroundControl.setChecked(bool(filters))

        filters = filters_from_request(request, "instrument")
        if filters:
            types = filters[0]["config"]
            for chk in [self.chkPs2, self.chkPs2Sd, self.chkPsbSd]:
                chk.setChecked(chk.property("api-name") in types)
        else:
            for chk in [self.chkPs2, self.chkPs2Sd, self.chkPsbSd]:
                chk.setChecked(False)

        filters = filters_from_request(request, "quality_category")
        self.chkStandardQuality.setChecked(bool(filters))

        filters = filters_from_request(request, "id")
        if filters:
            self.leStringIDs.setText(",".join(filters[0]["config"]))
        else:
            self.leStringIDs.setText("")

        self.check_for_legacy_request(request)
        self.emitFiltersChanged = True

    def check_for_legacy_request(self, request):
        sources = request["item_types"]
        if "PSScene3Band" in sources or "PSScene4Band" in sources:
            self.frameWarningLegacySearch.setVisible(True)
            self.stackedWidgetSources.setCurrentWidget(self.oldSourcesWidget)
            source_boxes = self.oldSourcesWidget.findChildren(QCheckBox)
            for checkbox in source_boxes:
                checkbox.setChecked(checkbox.property("api-name") in sources)
            self.otherAttributesWidget.setEnabled(False)
            self.frameFilters.setEnabled(False)
            self.startDateEdit.setEnabled(False)
            self.endDateEdit.setEnabled(False)
            self.legacyWarningWidget.set_has_image_id(bool(self.leStringIDs.text()))

            self.chkPlanetScope.setChecked(True)
            self.chkNIR.setChecked("PSScene4Band" in sources)
            self.chkYellow.setChecked(False)
            self.chkSurfaceReflectance.setChecked(False)
        else:
            self.hide_legacy_search_elements()

    def hide_legacy_search_elements(self):
        self.otherAttributesWidget.setEnabled(True)
        self.frameFilters.setEnabled(True)
        self.startDateEdit.setEnabled(True)
        self.endDateEdit.setEnabled(True)
        self.frameWarningLegacySearch.setVisible(False)
        self.stackedWidgetSources.setCurrentWidget(self.newSourcesWidget)

    def clear_id_filter(self):
        self.leStringIDs.setText("")

    @pyqtSlot()
    def filters_changed(self):
        if self.emitFiltersChanged:
            self.filtersChanged.emit()
