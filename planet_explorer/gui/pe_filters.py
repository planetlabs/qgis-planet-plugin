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
__author__ = 'Planet Federal'
__date__ = 'August 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import json
import logging
import re

from qgis.PyQt import uic
from qgis.PyQt.QtCore import (
    QObject,
    pyqtSignal,
    pyqtSlot,
    QDateTime,
    Qt
)
from qgis.PyQt.QtGui import (
    QColor,
)

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QLineEdit,
    QFrame,
    QComboBox,
    QMenu,
    QAction,
    QMessageBox
)

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsMapLayer,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsGeometry,
    QgsWkbTypes,
    QgsRectangle,
    QgsFeature,
    QgsVectorLayer,
)
from qgis.gui import (
    QgisInterface,
    QgsRubberBand,
    QgsDateTimeEdit,
    QgsMapTool,
    QgsMapCanvas,
)


from planet.api.filters import (
    date_range,
    geom_filter,
    not_filter,
    range_filter,
    string_filter,
    permission_filter,
)

from planet.api.utils import geometry_from_json

from ..pe_utils import (
    qgsgeometry_from_geojson,
    zoom_canvas_to_aoi,
    MAIN_AOI_COLOR
)
from .pe_range_slider import PlanetExplorerRangeSlider

from .pe_aoi_maptools import (
    PlanetExtentMapTool,
    PlanetCircleMapTool,
    PlanetPolyMapTool,
)

from ..planet_api.p_client import (
    PlanetClient
)

LOCAL_FILTERS = ["area_coverage"]

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

plugin_path = os.path.split(os.path.dirname(__file__))[0]
MAIN_FILTERS_WIDGET, MAIN_FILTERS_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_main_filters_base.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)
DAILY_WIDGET, DAILY_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_daily_filter_base.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)


def filters_from_request(request, field_name=None, filter_type=None):
    filters = []
    def _add_filter(filterdict):
        if filterdict["type"] in ["AndFilter", "OrFilter"]:
            for subfilter in filterdict["config"]:
                _add_filter(subfilter)
        elif filterdict["type"] == "NotFilter":
            _add_filter(filterdict["config"][0])
        else:
            if (field_name is not None
                and "field_name" in filterdict
                and filterdict["field_name"] == field_name):
                    filters.append(filterdict)
            if filter_type is not None and filterdict["type"] == filter_type:
                filters.append(filterdict)

    filter_entry = request["filter"] if "filter" in request else request
    _add_filter(filter_entry)
    return filters

def filters_as_text_from_request(request):
    slider_filters = {
            'cloud_cover': 'Cloud cover',
            'sun_azimuth': 'Sun Azimuth',
            'sun_elevation': 'Sun Elevation',
            'view_angle': 'View Angle',
            'gsd': 'Ground Sample Distance',
            'anomalous_pixels': 'Anomalous Pixels',
            'usable_data': 'Usable Pixels',
    }
    s = ""
    for k, v in slider_filters.items():
        filters = filters_from_request(request, k)
        if filters:
            minvalue = filters[0]['config'].get('gte')
            if minvalue is None:
                minvalue = "---"
            elif k == 'cloud_cover':
                minvalue *= 100.0
            maxvalue = filters[0]['config'].get('lte')
            if maxvalue is None:
                maxvalue = "---"
            elif k == 'cloud_cover':
                maxvalue *= 100.0
        else:
            minvalue = maxvalue = "---"
        s += f"{k}: {minvalue}, {maxvalue}\n"

    filters = filters_from_request(request, filter_type='PermissionFilter')
    if filters:
        s += f"Only show images you can download: {'assets:download' in filters[0]['config']}\n"
    else:
        s += "Only show images you can download: False\n"
    filters = filters_from_request(request, 'ground_control')
    if filters:
        s += f"Only show images with ground control: {'assets:download' in filters[0]['config']}\n"
    else:
        s += "Only show images with ground control: False\n"

    filters = filters_from_request(request, 'id')
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

    def _show_message(self, message, level=Qgis.Info,
                      duration=None, show_more=None):
        self._plugin.show_message(message, level, duration, show_more)


class PlanetMainFilters(MAIN_FILTERS_BASE, MAIN_FILTERS_WIDGET,
                        PlanetFilterMixin):

    leAOI: QLineEdit

    filtersChanged = pyqtSignal()
    savedSearchSelected = pyqtSignal(object)
    zoomToAOIRequested = pyqtSignal()

    def __init__(self, iface, parent=None, plugin=None,
                no_saved_search=False, color=MAIN_AOI_COLOR):
        super().__init__(parent=parent)
        self._iface: QgisInterface = iface
        self._plugin = plugin

        self.setupUi(self)

        self.emitFiltersChanged = False

        self.color = color

        self._aoi_box = QgsRubberBand(self._iface.mapCanvas(),
                                      QgsWkbTypes.PolygonGeometry)
        self._aoi_box.setFillColor(QColor(0, 0, 0, 0))
        self._aoi_box.setStrokeColor(color)
        self._aoi_box.setWidth(3)
        self._aoi_box.setLineStyle(Qt.DashLine)

        self._canvas: QgsMapCanvas = self._iface.mapCanvas()
        # This may later be a nullptr, if no active tool when queried
        self._cur_maptool = None

        # noinspection PyUnresolvedReferences
        self.leAOI.textChanged['QString'].connect(self.filters_changed)
        # noinspection PyUnresolvedReferences
        self.leAOI.textEdited['QString'].connect(self.validate_edited_aoi)

        self._setup_tool_buttons()

        # Extent line edit tools
        self.btnZoomToAOI.clicked.connect(self.zoom_to_aoi)
        self.btnCopyAOI.clicked.connect(self.copy_aoi_to_clipboard)

        self.p_client = PlanetClient.getInstance()
        self.p_client.loginChanged.connect(self.populate_saved_searches)

        self.comboSavedSearch.currentIndexChanged.connect(self.saved_search_selected)

        if no_saved_search:
            self.comboSavedSearch.setVisible(False)

    def populate_saved_searches(self, is_logged):
        if is_logged:
            self.comboSavedSearch.clear()
            self.comboSavedSearch.blockSignals(True)
            self.comboSavedSearch.addItem("[Select a Saved Search]")
            res = self.p_client.get_searches().get()
            for search in res["searches"]:
                self.comboSavedSearch.addItem(search["name"], search)
            self.comboSavedSearch.blockSignals(False)

    def add_saved_search(self, request):
        self.comboSavedSearch.blockSignals(True)
        self.comboSavedSearch.addItem(request["name"], request)
        self.comboSavedSearch.setCurrentIndex(self.comboSavedSearch.count() - 1)
        self.comboSavedSearch.blockSignals(False)

    def saved_search_selected(self, idx):
        if idx == 0:
            return
        request = self.comboSavedSearch.currentData()
        sources = request['item_types']
        if 'PSScene3Band' in sources or 'PSScene4Band' in sources:
            item_types = ["PSScene" if typ in ["PSScene3Band", "PSScene4Band"]
                          else typ for typ in request['item_types']]
            request['item_types'] = item_types
            self.comboSavedSearch.setItemData(idx, request)
            ret = QMessageBox.question(self, "Saved Search Conversion",
                                       'This search was saved using an older format and it will be converted.\n'
                                       'Do you also want to update the search request in the server?',
                                      )
            if ret == QMessageBox.Yes:
                PlanetClient.getInstance().update_search(request)

        self.savedSearchSelected.emit(request)

    def null_out_saved_search(self):
        self.comboSavedSearch.blockSignals(True)
        self.comboSavedSearch.setCurrentIndex(0)
        self.comboSavedSearch.blockSignals(False)

    def reset_aoi_box(self):
        self.leAOI.setText("")
        if self._aoi_box:
            self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)

    def filters(self):
        filters = []
        if self.leAOI.text():
            # TODO: Validate GeoJSON; try planet.api.utils.probably_geojson()
            # noinspection PyBroadException
            try:
                if qgsgeometry_from_geojson(self.leAOI.text()):
                    aoi = json.loads(self.leAOI.text())
                    filters.append(geom_filter(aoi))
                else:
                    self._show_message("AOI not valid GeoJSON polygon",
                                       level=Qgis.Warning,
                                       duration=10)
            except Exception:
                self._show_message("AOI not valid JSON",
                                   level=Qgis.Warning,
                                   duration=10)
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

    @pyqtSlot('QString')
    def filters_changed(self, value):
        if self.emitFiltersChanged:# noinspection PyUnresolvedReferences
            self.filtersChanged.emit()

    @pyqtSlot()
    def clean_up(self):
        self.reset_aoi_box()

    def _setup_tool_buttons(self):
        extent_menu = QMenu(self)

        canvas_act = QAction('Current visible extent', extent_menu)
        # noinspection PyUnresolvedReferences
        canvas_act.triggered[bool].connect(self.aoi_from_current_extent)
        extent_menu.addAction(canvas_act)

        active_act = QAction('Active map layer extent', extent_menu)
        # noinspection PyUnresolvedReferences
        active_act.triggered[bool].connect(self.aoi_from_active_layer_extent)
        extent_menu.addAction(active_act)

        full_act = QAction('All map layers extent', extent_menu)
        # noinspection PyUnresolvedReferences
        full_act.triggered[bool].connect(self.aoi_from_full_extent)
        extent_menu.addAction(full_act)

        self.btnExtent.setMenu(extent_menu)

        # Also show menu on click, to keep disclosure triangle visible
        self.btnExtent.clicked.connect(self.btnExtent.showMenu)

        draw_menu = QMenu(self)

        box_act = QAction('Rectangle', draw_menu)
        # noinspection PyUnresolvedReferences
        box_act.triggered[bool].connect(self.aoi_from_box)
        draw_menu.addAction(box_act)

        circle_act = QAction('Circle', draw_menu)
        # noinspection PyUnresolvedReferences
        circle_act.triggered[bool].connect(self.aoi_from_circle)
        draw_menu.addAction(circle_act)

        polygon_act = QAction('Polygon', draw_menu)
        # noinspection PyUnresolvedReferences
        polygon_act.triggered[bool].connect(self.aoi_from_polygon)
        draw_menu.addAction(polygon_act)

        self.btnDraw.setMenu(draw_menu)
        # Also show menu on click, to keep disclosure triangle visible
        self.btnDraw.clicked.connect(self.btnDraw.showMenu)

        selection_menu = QMenu(self)

        self.single_select_act = QAction('Single feature', selection_menu)
        # noinspection PyUnresolvedReferences
        self.single_select_act.triggered[bool].connect(self.aoi_from_feature)
        selection_menu.addAction(self.single_select_act)

        self.bound_select_act = QAction('Multiple features (bounding box)',
                                        selection_menu)
        # noinspection PyUnresolvedReferences
        self.bound_select_act.triggered[bool].connect(self.aoi_from_bound)
        selection_menu.addAction(self.bound_select_act)

        self.btnSelection.setMenu(selection_menu)
        # Also show menu on click, to keep disclosure triangle visible
        self.btnSelection.clicked.connect(self._toggle_selection_tools)
        self.btnSelection.clicked.connect(self.btnSelection.showMenu)

    def _toggle_selection_tools(self):
        active_layer = self._iface.activeLayer()
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
    # noinspection PyArgumentList
    def aoi_from_current_extent(self):
        """Return current map extent as geojson transformed to EPSG:4326
        """
        if not self._iface:
            log.debug('No iface object, skipping AOI extent')
            return

        canvas = self._iface.mapCanvas()
        # noinspection PyArgumentList
        transform = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance()
        )

        canvas_extent: QgsRectangle = canvas.extent()
        transform_extent = transform.transformBoundingBox(canvas_extent)
        # noinspection PyArgumentList
        geom_extent = QgsGeometry.fromRect(transform_extent)
        extent_json = geom_extent.asJson(precision=6)

        # noinspection PyArgumentList
        self._aoi_box.setToGeometry(QgsGeometry.fromRect(canvas.extent()))

        self.leAOI.setText(extent_json)

        log.debug('AOI set to canvas extent')

        self.zoom_to_aoi()

    @pyqtSlot()
    # noinspection PyArgumentList
    def aoi_from_active_layer_extent(self):
        """Return active map layer extent as geojson transformed to EPSG:4326
        """
        if not self._iface:
            log.debug('No iface object, skipping AOI extent')
            return

        map_layer: QgsMapLayer = self._iface.activeLayer()
        if map_layer is None:
            log.debug('No active layer selected, skipping AOI extent')
            return

        if not map_layer.isValid():
            log.debug('Active map layer invalid, skipping AOI extent')
            return

        # noinspection PyArgumentList
        transform = QgsCoordinateTransform(
            map_layer.crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance())

        ml_extent: QgsRectangle = map_layer.extent()
        transform_extent = transform.transformBoundingBox(ml_extent)
        # noinspection PyArgumentList
        geom_extent = QgsGeometry.fromRect(transform_extent)
        extent_json = geom_extent.asJson(precision=6)

        # noinspection PyArgumentList,PyCallByClass
        self._aoi_box.setToGeometry(QgsGeometry.fromRect(ml_extent))

        self.leAOI.setText(extent_json)

        log.debug('AOI set to active layer extent')

        self.zoom_to_aoi()

    @pyqtSlot()
    # noinspection PyArgumentList
    def aoi_from_full_extent(self):
        """Return full data map extent as geojson transformed to EPSG:4326
        """
        if not self._iface:
            log.debug('No iface object, skipping AOI extent')
            return

        canvas = self._iface.mapCanvas()

        # noinspection PyArgumentList
        transform = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance())

        canvas_extent: QgsRectangle = canvas.fullExtent()
        transform_extent = transform.transformBoundingBox(canvas_extent)
        # noinspection PyArgumentList
        geom_extent = QgsGeometry.fromRect(transform_extent)
        extent_json = geom_extent.asJson(precision=6)

        # noinspection PyArgumentList,PyCallByClass
        self._aoi_box.setToGeometry(QgsGeometry.fromRect(canvas_extent))

        self.leAOI.setText(extent_json)

        log.debug('AOI set to full data extent')

        self.zoom_to_aoi()

    @pyqtSlot()
    def aoi_from_box(self):
        self._cur_maptool: QgsMapTool = self._canvas.mapTool()
        self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)
        aoi_draw = PlanetExtentMapTool(self._iface.mapCanvas())
        self._iface.mapCanvas().setMapTool(aoi_draw)
        aoi_draw.extentSelected.connect(self.set_draw_aoi)

    @pyqtSlot()
    def aoi_from_circle(self):
        self._cur_maptool: QgsMapTool = self._canvas.mapTool()
        self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)
        aoi_draw = PlanetCircleMapTool(self._iface.mapCanvas())
        self._iface.mapCanvas().setMapTool(aoi_draw)
        aoi_draw.circleSelected.connect(self.set_draw_aoi)

    @pyqtSlot()
    def aoi_from_polygon(self):
        self._cur_maptool: QgsMapTool = self._canvas.mapTool()
        self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)
        aoi_draw = PlanetPolyMapTool(self._iface.mapCanvas())
        self._iface.mapCanvas().setMapTool(aoi_draw)
        aoi_draw.polygonSelected.connect(self.set_draw_aoi)

    @pyqtSlot(object)
    def set_draw_aoi(self, aoi):
        # noinspection PyArgumentList
        transform = QgsCoordinateTransform(
            QgsProject.instance().crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance())

        aoi_json = None

        if isinstance(aoi, QgsRectangle):
            aoi_geom = QgsGeometry().fromRect(aoi)
            self._aoi_box.setToGeometry(aoi_geom)
            aoi_geom.transform(transform)
            aoi_json = aoi_geom.asJson(precision=6)

        if isinstance(aoi, QgsGeometry):
            if aoi.isMultipart():
                aoi = QgsGeometry.fromPolygonXY(aoi.asMultiPolygon()[0])
            self._aoi_box.setToGeometry(aoi)
            # TODO: validate geom is less than 500 vertices
            aoi.transform(transform)
            aoi_json = aoi.asJson(precision=6)

        if aoi_json:
            self.leAOI.setText(aoi_json)

            # noinspection PyUnresolvedReferences
            self._show_message('AOI set to drawn figure')
            self.zoom_to_aoi()
            if self._cur_maptool is not None:
                # Restore previously used maptool
                self._canvas.setMapTool(self._cur_maptool)
                self._cur_maptool = None
            else:
                # Fallback to activating pan tool
                self._iface.actionPan().trigger()
        else:
            # noinspection PyUnresolvedReferences
            self._show_message('AOI unable to be set',
                               level=Qgis.Warning,
                               duration=10)

    @pyqtSlot()
    def aoi_from_feature(self):
        layer: QgsVectorLayer = self._iface.activeLayer()

        if layer.selectedFeatureCount() > 1:
            self._show_message('More than 1 feature. Searching by bbox.',
                               level=Qgis.Warning,
                               duration=10)
            self.aoi_from_bound()
            return
        elif layer.selectedFeatureCount() < 1:
            self._show_message('No features selected.',
                               level=Qgis.Warning,
                               duration=10)
            return

        selected: QgsFeature = layer.selectedFeatures()[0]
        if selected.geometry().isMultipart():
            multi_geom = selected.geometry().asGeometryCollection()
            if len(multi_geom) > 1:
                self._show_message(
                                   'More than 1 geometry. Searching by bbox.',
                                   level=Qgis.Warning,
                                   duration=10
                    )
                self.aoi_from_bound()
                return
            elif len(multi_geom) < 1:
                self._show_message('No geometry selected.',
                                   level=Qgis.Warning,
                                   duration=10)
                return
            else:
                geom: QgsGeometry = multi_geom[0]
        else:
            geom: QgsGeometry = selected.geometry()

        if geom.constGet().vertexCount() > 500:
            self._show_message(
                               'More than 500 vertices. Searching by bbox.',
                               level=Qgis.Warning,
                               duration=10
            )
            self.aoi_from_bound()
            return

        # noinspection PyArgumentList
        trans_layer = QgsCoordinateTransform(
            layer.sourceCrs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance()
        )

        # noinspection PyArgumentList
        trans_canvas = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().crs(),
            QgsProject.instance()
        )

        # geom.transform(transform)
        geom.transform(trans_layer)
        geom_json = geom.asJson(precision=6)
        self.leAOI.setText(geom_json)

        geom.transform(trans_canvas)
        self._aoi_box.setToGeometry(
            geom,
            QgsCoordinateReferenceSystem("EPSG:4326")
        )
        self.zoom_to_aoi()

    @pyqtSlot()
    def aoi_from_bound(self):
        layer: QgsVectorLayer = self._iface.activeLayer()

        if layer.selectedFeatureCount() < 1:
            self._show_message('No features selected.',
                               level=Qgis.Warning,
                               duration=10)
            return

        bbox = layer.boundingBoxOfSelected()

        # noinspection PyArgumentList
        trans_layer = QgsCoordinateTransform(
            layer.sourceCrs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance()
        )

        # noinspection PyArgumentList
        trans_canvas = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().crs(),
            QgsProject.instance()
        )

        transform_bbox = trans_layer.transformBoundingBox(bbox)
        # noinspection PyArgumentList
        geom_bbox = QgsGeometry.fromRect(transform_bbox)
        bbox_json = geom_bbox.asJson(precision=6)

        self.leAOI.setText(bbox_json)

        bbox_canvas = trans_canvas.transformBoundingBox(transform_bbox)
        # noinspection PyArgumentList
        self._aoi_box.setToGeometry(QgsGeometry.fromRect(bbox_canvas))

        self.zoom_to_aoi()

    def hide_aoi_if_matches_geom(self, geom):
            color = (QColor(0, 0, 0, 0) if self._aoi_box.asGeometry().equals(geom)
                    else self.color)
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
            QgsProject.instance()
        )
        geom = self.aoi_geom()
        if geom is not None:
            geom.transform(transform)
        return geom


    @pyqtSlot()
    def zoom_to_aoi(self):
        if not self._iface:
            log.debug('No iface object, skipping AOI extent')
            return

        if not self.leAOI.text():
            log.debug('No AOI defined, skipping zoom to AOI')
            return

        geom: QgsGeometry = qgsgeometry_from_geojson(self.leAOI.text())
        self._aoi_box.setToGeometry(
            geom,
            QgsCoordinateReferenceSystem("EPSG:4326")
        )

        self.show_aoi()

        zoom_canvas_to_aoi(self.leAOI.text())

        self.zoomToAOIRequested.emit()

    @pyqtSlot()
    def copy_aoi_to_clipboard(self):
        if not self.leAOI.text():
            log.debug('No AOI defined, skipping zoom to AOI')
            return

        json_geom_txt = json.dumps(json.loads(self.leAOI.text()), indent=2)

        cb = QgsApplication.clipboard()
        cb.setText(json_geom_txt)

        # noinspection PyUnresolvedReferences
        self._show_message('AOI copied to clipboard')

    @pyqtSlot()
    def validate_aoi(self):
        # TODO:gather existing validation logic here
        # TODO: Check for valid json.loads

        # TODO: Check API verticie limit of 500
        pass

    @pyqtSlot()
    def validate_edited_aoi(self):
        json_txt = self.leAOI.text()
        if not json_txt:
            self.reset_aoi_box()
            log.debug('No AOI defined, skipping validation')
            return

        try:
            json_obj = json.loads(json_txt)
        except ValueError:
            # noinspection PyUnresolvedReferences
            self._show_message('AOI GeoJSON is invalid',
                               level=Qgis.Warning,
                               duration=10)
            return

        json_geom = geometry_from_json(json_obj)

        if not json_geom:
            # noinspection PyUnresolvedReferences
            self._show_message('AOI GeoJSON geometry invalid',
                               level=Qgis.Warning,
                               duration=10)
            return

        geom: QgsGeometry = qgsgeometry_from_geojson(json_geom)
        self._aoi_box.setToGeometry(
            geom,
            QgsCoordinateReferenceSystem("EPSG:4326")
        )

        self.leAOI.blockSignals(True)
        self.leAOI.setText(json.dumps(json_geom))
        self.leAOI.blockSignals(False)

        self.zoom_to_aoi()


class PlanetDailyFilter(DAILY_BASE, DAILY_WIDGET, PlanetFilterMixin):
    """
    """
    frameSources: QFrame
    frameDates: QFrame
    leStringIDs: QLineEdit
    endDateEdit: QgsDateTimeEdit
    startDateEdit: QgsDateTimeEdit
    cmbBoxDateSort: QComboBox
    frameRangeSliders: QFrame
    rangeCloudCover: PlanetExplorerRangeSlider

    chkBxGroundControl: QCheckBox
    chkBxCanDownload: QCheckBox

    filtersChanged = pyqtSignal()

    ID_PATTERN = [
        r'\d{8,8}_\d{6,6}',
        r'\d{4,4}-\d{2,2}-\d{2,2}',
        r'LC',
        r'S2',
    ]

    id_regex = [re.compile(pattern) for pattern in ID_PATTERN]

    def __init__(self, parent=None, plugin=None):
        super().__init__(parent=parent)
        self.setupUi(self)
        self._plugin = plugin

        self.emitFiltersChanged = True

        self.chkPlanetScope.stateChanged.connect(self._planet_scope_check_changed)
        self.chkOrthotiles.stateChanged.connect(self._orthotiles_check_changed)
        self.chkPlanetScopeOrtho.stateChanged.connect(self._update_orthotiles_check)
        self.chkRapidEyeOrtho.stateChanged.connect(self._update_orthotiles_check)

        sources = self.frameSources.findChildren(QCheckBox)
        for source in sources:
            apiname = source.property('api-name')
            if apiname is not None:
                source.stateChanged.connect(self.filtersChanged)

        # noinspection PyUnresolvedReferences
        self.startDateEdit.valueChanged['QDateTime'].connect(
            self.filtersChanged)
        # noinspection PyUnresolvedReferences
        self.startDateEdit.valueChanged['QDateTime'].connect(
            self.set_min_enddate)
        # noinspection PyUnresolvedReferences
        self.startDateEdit.valueChanged['QDateTime'].connect(
            self.change_date_vis)
        # noinspection PyUnresolvedReferences
        self.endDateEdit.valueChanged['QDateTime'].connect(
            self.filtersChanged)
        # noinspection PyUnresolvedReferences
        self.endDateEdit.valueChanged['QDateTime'].connect(
            self.set_max_startdate)
        # noinspection PyUnresolvedReferences
        self.endDateEdit.valueChanged['QDateTime'].connect(
            self.change_date_vis)

        # Setup datetime boxes
        current_day = QDateTime().currentDateTimeUtc()
        self.startDateEdit.setDateTime(current_day.addMonths(-3))
        self.endDateEdit.setDateTime(current_day)

        # TODO: (Eventually) Add multi-field searching, with +/- operation
        #       of adding new field/QLineEdit, without duplicates
        # noinspection PyUnresolvedReferences
        self.leStringIDs.textChanged['QString'].connect(self.filters_changed)

        self.rangeCloudCover = PlanetExplorerRangeSlider(
            title='Cloud cover',
            filter_key='cloud_cover',
            prefix='',
            suffix='%',
            minimum=0,
            maximum=100,
            low=0,
            high=100,
            step=1,
            precision=1
        )
        # Layout's parent widget takes ownership
        self.frameRangeSliders.layout().addWidget(self.rangeCloudCover)
        self.rangeCloudCover.rangeChanged[float, float].connect(
            self.filters_changed)

        self.rangeAzimuth = PlanetExplorerRangeSlider(
            title='Sun Azimuth',
            filter_key='sun_azimuth',
            prefix='',
            suffix='°',
            minimum=0,
            maximum=360,
            low=0,
            high=360,
            step=1,
            precision=1
        )
        # Layout's parent widget takes ownership
        self.frameRangeSliders.layout().addWidget(self.rangeAzimuth)
        self.rangeAzimuth.rangeChanged[float, float].connect(
            self.filters_changed)

        self.rangeElevation = PlanetExplorerRangeSlider(
            title='Sun Elevation',
            filter_key='sun_elevation',
            prefix='',
            suffix='°',
            minimum=0,
            maximum=90,
            low=0,
            high=90,
            step=1,
            precision=1
        )
        # Layout's parent widget takes ownership
        self.frameRangeSliders.layout().addWidget(self.rangeElevation)
        self.rangeElevation.rangeChanged[float, float].connect(
            self.filters_changed)

        self.rangeViewAngle = PlanetExplorerRangeSlider(
            title='View Angle',
            filter_key='view_angle',
            prefix='',
            suffix='°',
            minimum=-25,
            maximum=25,
            low=0,
            high=25,
            step=1,
            precision=1
        )
        # Layout's parent widget takes ownership
        self.frameRangeSliders.layout().addWidget(self.rangeViewAngle)
        self.rangeViewAngle.rangeChanged[float, float].connect(
            self.filters_changed)

        self.rangeGsd = PlanetExplorerRangeSlider(
            title='Ground Sample Distance',
            filter_key='gsd',
            prefix='',
            suffix='m',
            minimum=0,
            maximum=50,
            low=0,
            high=50,
            step=1,
            precision=1
        )
        # Layout's parent widget takes ownership
        self.frameRangeSliders.layout().addWidget(self.rangeGsd)
        self.rangeGsd.rangeChanged[float, float].connect(
            self.filters_changed)

        self.rangeAnomalousPx = PlanetExplorerRangeSlider(
            title='Anomalous Pixels',
            filter_key='anomalous_pixels',
            prefix='',
            suffix='%',
            minimum=0,
            maximum=100,
            low=0,
            high=100,
            step=1,
            precision=1
        )

        # Layout's parent widget takes ownership
        self.frameRangeSliders.layout().addWidget(self.rangeAnomalousPx)
        self.rangeAnomalousPx.rangeChanged[float, float].connect(
            self.filters_changed)

        self.rangeUsable = PlanetExplorerRangeSlider(
            title='Usable Pixels',
            filter_key='usable_data',
            prefix='',
            suffix='%',
            minimum=0,
            maximum=100,
            low=0,
            high=100,
            step=1,
            precision=1
        )
        # Layout's parent widget takes ownership
        self.frameRangeSliders.layout().addWidget(self.rangeUsable)
        self.rangeUsable.rangeChanged[float, float].connect(
            self.filters_changed)

        self.rangeAreaCoverage = PlanetExplorerRangeSlider(
            title='Area Coverage',
            filter_key='area_coverage',
            prefix='',
            suffix='%',
            minimum=0,
            maximum=100,
            low=0,
            high=100,
            step=1,
            precision=1
        )
        self.frameRangeSliders.layout().addWidget(self.rangeAreaCoverage)
        self.rangeAreaCoverage.rangeChanged[float, float].connect(
            self.filters_changed)

        # TODO: Add rest of range sliders

        # Ground control filter checkbox
        # noinspection PyUnresolvedReferences
        self.chkBxGroundControl.stateChanged[int].connect(self.filters_changed)

        # Access Filter checkbox
        # noinspection PyUnresolvedReferences
        self.chkBxCanDownload.stateChanged[int].connect(self.filters_changed)

    def _update_orthotiles_check(self):
        sources = [self.chkPlanetScopeOrtho,
                   self.chkRapidEyeOrtho]
        nchecked = sum([1 if s.isChecked() else 0 for s in sources])
        self.chkOrthotiles.blockSignals(True)
        if nchecked == 0:
            self.chkOrthotiles.setCheckState(Qt.Unchecked)
        elif nchecked == len(sources):
            self.chkOrthotiles.setCheckState(Qt.Checked)
        else:
            self.chkOrthotiles.setCheckState(Qt.PartiallyChecked)
        self.chkOrthotiles.blockSignals(False)

    def _orthotiles_check_changed(self):
        sources = [self.chkPlanetScopeOrtho,
                   self.chkRapidEyeOrtho]
        if self.chkOrthotiles.checkState() == Qt.Unchecked:
            for s in sources:
                s.blockSignals(True)
                s.setChecked(False)
                s.blockSignals(False)
        elif self.chkOrthotiles.checkState() == Qt.Checked:
            for s in sources:
                s.blockSignals(True)
                s.setChecked(True)
                s.blockSignals(False)
        else:
            self.chkOrthotiles.setCheckState(Qt.Checked)

    def _planet_scope_check_changed(self):
        radio_boxes = [self.radio3Bands, self.radio4Bands, self.radio8Bands]
        for radio in radio_boxes:
            radio.setEnabled(self.chkPlanetScope.isChecked())

    def sources(self):
        checked_sources = []
        sources = self.frameSources.findChildren(QCheckBox)
        for source in sources:
            if source.isChecked():
                apiname = source.property('api-name')
                if apiname is not None:
                    checked_sources.append(apiname)
        return checked_sources

    def set_min_enddate(self):
        self.endDateEdit.setMinimumDate(self.startDateEdit.date())

    def set_max_startdate(self):
        self.startDateEdit.setMaximumDate(self.endDateEdit.date())

    def change_date_vis(self):
        dates = self.frameDates.findChildren(
            QgsDateTimeEdit)

        for date in dates:
            if date.dateTime().isNull():
                date.lineEdit().setEchoMode(QLineEdit.NoEcho)
            else:
                date.lineEdit().setEchoMode(QLineEdit.Normal)

    def filters(self):
        populated_filters = []

        start_date = None
        end_date = None
        start_datetime = None
        end_datetime = None
        if not self.startDateEdit.dateTime().isNull():
            start_datetime = self.startDateEdit.dateTime()
            start_date = start_datetime.toString(Qt.ISODate)
        if not self.endDateEdit.dateTime().isNull():
            end_datetime = self.endDateEdit.dateTime()
            end_date = end_datetime.toString(Qt.ISODate)

        if start_datetime and end_datetime:
            if start_datetime < end_datetime:
                date_filter = date_range(
                    'acquired',
                    gte=start_date,
                    lte=end_date
                )
                populated_filters.append(date_filter)
            else:
                self._show_message('Start date later than end date.',
                                   level=Qgis.Warning,
                                   duration=10)
        elif start_date:
            start_date_filter = date_range('acquired', gte=start_date)
            populated_filters.append(start_date_filter)
        elif end_date:
            end_date_filter = date_range('acquired', lte=end_date)
            populated_filters.append(end_date_filter)

        # TODO: double check actual domain/range of sliders
        sliders = self.frameRangeSliders.findChildren(
            PlanetExplorerRangeSlider)
        for slider in sliders:
            slide_filter = None
            range_low, range_high = slider.range()
            if slider.filter_key == 'cloud_cover':
                range_low /= 100.0
                range_high /= 100.0
                slider_max = 1.0
            else:
                slider_max = slider.max
            if range_low != slider.min and range_high != slider_max:
                slide_filter = range_filter(slider.filter_key,
                                            gte=range_low,
                                            lte=range_high)
            elif range_low != slider.min:
                slide_filter = range_filter(slider.filter_key,
                                            gte=range_low)
            elif range_high != slider_max:
                slide_filter = range_filter(slider.filter_key,
                                            lte=range_high)
            if slide_filter:
                populated_filters.append(slide_filter)

        s_ids = self.leStringIDs.text()
        if s_ids:
            ids_actual = []
            s_ids.replace(" ", "")
            for s_id in s_ids.split(','):
                for text_chunk in s_id.split(':'):
                    for pattern in self.id_regex:
                        if pattern.match(text_chunk):
                            ids_actual.append(text_chunk)

            if ids_actual:
                s_ids_list = ['id']
                s_ids_list.extend(ids_actual)
                string_ids_filter = string_filter(*s_ids_list)
                populated_filters.append(string_ids_filter)
            else:
                self._show_message('No valid ID present',
                                   level=Qgis.Warning,
                                   duration=10)

        instruments = []
        for chk in [self.chkPs2, self.chkPs2Sd, self.chkPsbSd]:
            if chk.isChecked():
                instruments.append(chk.text())
        if instruments:
            instrument_filter = string_filter('instrument', *instruments)
            populated_filters.append(instrument_filter)

        if self.chkBxCanDownload.isChecked():
            dl_permission_filter = permission_filter('assets:download')
            populated_filters.append(dl_permission_filter)

        # Ground_control can be 'true', 'false, or a numeric value
        # Safest to check for not 'false'
        if self.chkBxGroundControl.isChecked():
            gc_filter = not_filter(string_filter('ground_control', 'false'))
            populated_filters.append(gc_filter)

        server_filters = [f for f in populated_filters if f["field_name"] not in LOCAL_FILTERS]
        local_filters = [f for f in populated_filters if f["field_name"] in LOCAL_FILTERS]
        return server_filters, local_filters

    def set_from_request(self, request):
        '''
        We assume here that the request has the structure of requests created
        with the plugin. We are not fully parsing the request to analize it,
        but instead making that assumption to simplify things.
        '''
        self.emitFiltersChanged = False
        checked_sources = request['item_types']
        sources = self.frameSources.findChildren(QCheckBox)
        for source in sources:
            source.setChecked(source.property('api-name') in checked_sources)
        filters = filters_from_request(request, 'acquired')
        if filters:
            gte = filters[0]['config'].get('gte')
            if gte is not None:
                self.startDateEdit.setDateTime(QDateTime.fromString(gte, Qt.ISODate))
            lte = filters[0]['config'].get('lte')
            if lte is not None:
                self.endDateEdit.setDateTime(QDateTime.fromString(lte, Qt.ISODate))
        sliders = self.frameRangeSliders.findChildren(
            PlanetExplorerRangeSlider)
        for slider in sliders:
            filters = filters_from_request(request, slider.filter_key)
            if filters:
                gte = filters[0]['config'].get('gte')
                if gte is None:
                    slider.setRangeLow(slider.min)
                else:
                    if slider.filter_key == 'cloud_cover':
                        gte *= 100.0
                    slider.setRangeLow(gte)
                lte = filters[0]['config'].get('lte')
                if lte is None:
                    slider.setRangeHigh(slider.max)
                else:
                    if slider.filter_key == 'cloud_cover':
                        lte *= 100.0
                    slider.setRangeHigh(lte)
            else:
                slider.setRangeLow(slider.min)
                slider.setRangeHigh(slider.max)
        filters = filters_from_request(request, filter_type='PermissionFilter')
        if filters:
            self.chkBxCanDownload.setChecked('assets:download' in filters[0]['config'])
        else:
            self.chkBxCanDownload.setChecked(False)
        filters = filters_from_request(request, 'ground_control')
        self.chkBxGroundControl.setChecked(bool(filters))

        filters = filters_from_request(request, 'instrument')
        if filters:
            types = filters[0]['config']
            for chk in [self.chkPs2, self.chkPs2Sd, self.chkPsbSd]:
                chk.setChecked(chk.text() in types)
        else:
            for chk in [self.chkPs2, self.chkPs2Sd, self.chkPsbSd]:
                chk.setChecked(False)


        filters = filters_from_request(request, 'id')
        if filters:
            self.leStringIDs.setText(",".join(filters[0]['config']))
        else:
            self.leStringIDs.setText("")
        self.emitFiltersChanged = True

    @pyqtSlot()
    def filters_changed(self):
        # noinspection PyUnresolvedReferences
        if self.emitFiltersChanged:
            self.filtersChanged.emit()
