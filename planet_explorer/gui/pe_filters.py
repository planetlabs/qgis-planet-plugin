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
from math import floor

from qgis.PyQt import uic
from qgis.PyQt.QtCore import (
    QObject,
    pyqtSignal,
    pyqtSlot,
    QDateTime,
    Qt,
    QFile,
    QDir,
    QTextStream,
)
from qgis.PyQt.QtGui import (
    QColor,
)

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QLineEdit,
    QFrame,
    QGridLayout,
    QComboBox,
    QFileDialog,
    QMenu,
    QAction,
)

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsMapLayer,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsGeometry,
    # QgsJsonExporter,
    # QgsJsonUtils,
    QgsWkbTypes,
    QgsRectangle,
    QgsFeature,
    # QgsFeatureIterator,
    QgsVectorLayer,
)
from qgis.gui import (
    QgisInterface,
    QgsRubberBand,
    QgsDateTimeEdit,
    QgsMapTool,
    QgsMapCanvas,
)

# from planet.api.models import Searches, JSON
from planet.api.filters import (
    # and_filter,
    # build_search_request,
    date_range,
    geom_filter,
    not_filter,
    # or_filter,
    range_filter,
    string_filter,
    permission_filter,
)

from planet.api.utils import geometry_from_json


from ..planet_api.p_specs import (
    DAILY_ITEM_TYPES,
    MOSAIC_ITEM_TYPES,
)

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

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

plugin_path = os.path.split(os.path.dirname(__file__))[0]
MAIN_FILTERS_WIDGET, MAIN_FILTERS_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_main_filters_base.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)
MOSAIC_WIDGET, MOSAIC_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_mosaic_filter_base.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)
DAILY_WIDGET, DAILY_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_daily_filter_base.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)


class PlanetFilterMixin(QObject):
    """
    Base mixin for Planet API filter control widget groupings.

    Widget groupings should be a QFrame (no margins or border) with a
    QgsScrollArea inside it layout, then widgets inside scroll area's layouot.
    QgsScrollArea is important, as it keeps scrolling input devices from
    changing control widget's values (an annoying Qt 'feature').
    """

    # filtersChanged = pyqtSignal()
    messageSent = pyqtSignal('QString', str, 'PyQt_PyObject', 'PyQt_PyObject')

    def __init__(self, parent=None, plugin=None):
        super().__init__(parent=parent)

        self._plugin = plugin

    # noinspection PyMethodMayBeStatic
    def sources(self):
        """
        List of sources or types to search for.
        Not required to be implemented in subclasses.
        :rtype: list
        """
        return []

    # noinspection PyMethodMayBeStatic
    def sort_order(self):
        """
        Tuple of date-field (published|acquired) and sort order (asc|desc)
        Not required to be implemented in subclasses.
        :rtype: tuple | None
        """
        return None

    def filters(self):
        """
        Filter representation as a Python dictionary, generated from
        control widgets, suitable for use in Planet client filter chaining.
        :rtype: dict
        """
        raise NotImplementedError

    def filters_as_json(self):
        """
        Filter representation as a JSON, generated from
        control widgets, suitable for use in Planet client filter chaining.
        :rtype: dict
        """
        raise NotImplementedError

    def load_filters(self, filter_json):
        """
        From a saved search JSON representation, load defined filter values
        into control widgets
        :param filter_json: planet.api.models.JSON
        :rtype: None
        """
        raise NotImplementedError

    def _filters_from_request(self, request, field_name=None, filter_type=None):
        filters = []
        def _add_filter(filterdict):            
            if filterdict["type"] == "AndFilter":
                for subfilter in filterdict["config"]:
                    _add_filter(subfilter)
            if filterdict["type"] == "NotFilter":                
                _add_filter(filterdict["config"][0])
            else:
                if (field_name is not None 
                    and "field_name" in filterdict
                    and filterdict["field_name"] == field_name):
                        filters.append(filterdict)
                if filter_type is not None and filterdict["type"] == filter_type:
                    filters.append(filterdict)

        _add_filter(request["filter"])
        return filters

    def set_from_request(self, request):
        """
        From a dictionary representing a search query, load defined filter 
        values into control widgets
        :param request: dict
        :rtype: None
        """
        pass

    # noinspection PyUnresolvedReferences
    def filters_changed(self):
        raise NotImplementedError

    # noinspection PyMethodMayBeStatic
    def clean_up(self):
        """
        Clean up operations should go here
        Not required to be implemented in subclasses.
        """
        return

    def _show_message(self, message, level=Qgis.Info,
                      duration=None, show_more=None):
        if self._plugin is not None and hasattr(self._plugin, 'show_message'):
            self._plugin.show_message(message, level, duration, show_more)
        else:
            if level == Qgis.Warning:
                level_str = 'Warning'
            elif level == Qgis.Critical:
                level_str = 'Critical'
            elif level == Qgis.Success:
                level_str = 'Success'
            else:  # default
                level_str = 'Info'

            self.messageSent.emit(message, level_str, duration, show_more)


class PlanetMainFilters(MAIN_FILTERS_BASE, MAIN_FILTERS_WIDGET,
                        PlanetFilterMixin):

    leAOI: QLineEdit

    filtersChanged = pyqtSignal()
    zoomToAOIRequested = pyqtSignal()

    def __init__(self, iface, parent=None, plugin=None):
        super().__init__(parent=parent)
        self._iface: QgisInterface = iface
        self._plugin = plugin

        self.setupUi(self)

        self._aoi_box = QgsRubberBand(self._iface.mapCanvas(),
                                      QgsWkbTypes.PolygonGeometry)
        self._aoi_box.setFillColor(QColor(0, 0, 0, 0))
        self._aoi_box.setStrokeColor(MAIN_AOI_COLOR)
        self._aoi_box.setWidth(3)
        self._aoi_box.setLineStyle(Qt.DashLine)

        self._canvas: QgsMapCanvas = self._iface.mapCanvas()
        # This may later be a nullptr, if no active tool when queried
        self._cur_maptool = None

        # self._json_exporter = QgsJsonExporter()
        # self._json_exporter.setIncludeAttributes(False)

        # noinspection PyUnresolvedReferences
        self.leAOI.textChanged['QString'].connect(self.filters_changed)
        # noinspection PyUnresolvedReferences
        self.leAOI.textEdited['QString'].connect(self.validate_edited_aoi)

        self._setup_tool_buttons()

        # Extent line edit tools
        self.btnZoomToAOI.clicked.connect(self.zoom_to_aoi)
        self.btnCopyAOI.clicked.connect(self.copy_aoi_to_clipboard)
        self.btnLoadAOI.clicked.connect(self.load_aoi_from_file)

    def reset_aoi_box(self):
        if self._aoi_box:
            self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)

    def filters(self):

        # return and_filter(geom_filter(self.leAOI.text),
        #         date_range('acquired', gte=dateEditStart.text,
        #         lte=dateEditEnd.text))
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
            except:
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

    def load_filters(self, filter_json):
        pass

    def set_from_request(self, request):
        filters = self._filters_from_request(request, "geometry")
        if filters:
            geom = filters[0]["config"]
            txt = json.dumps(geom)
            self.leAOI.setText(txt)

    @pyqtSlot('QString')
    def filters_changed(self, value):
        # noinspection PyUnresolvedReferences
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
        extent_json = geom_extent.asJson()

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
        extent_json = geom_extent.asJson()

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
        extent_json = geom_extent.asJson()

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
            aoi_json = aoi_geom.asJson()

        if isinstance(aoi, QgsGeometry):
            self._aoi_box.setToGeometry(aoi)
            # TODO: validate geom is less than 500 vertices
            aoi.transform(transform)
            aoi_json = aoi.asJson()

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
        geom_json = geom.asJson()
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
        bbox_json = geom_bbox.asJson()

        self.leAOI.setText(bbox_json)

        bbox_canvas = trans_canvas.transformBoundingBox(transform_bbox)
        # noinspection PyArgumentList
        self._aoi_box.setToGeometry(QgsGeometry.fromRect(bbox_canvas))

        self.zoom_to_aoi()

    def hide_aoi_if_matches_geom(self, geom):
            color = (QColor(0, 0, 0, 0) if self._aoi_box.asGeometry().equals(geom) 
                    else MAIN_AOI_COLOR)
            self._aoi_box.setStrokeColor(color)

    def show_aoi(self):
        if self._aoi_box is not None:
            self._aoi_box.setStrokeColor(MAIN_AOI_COLOR)

    def aoi_geom(self):
        if self._aoi_box is not None:
            return self._aoi_box.asGeometry()

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

        zoom_canvas_to_aoi(self.leAOI.text(), iface_obj=self._iface)

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
    def load_aoi_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open GeoJSON AOI file",
            QDir.homePath(),
            "JSON (*.json);;All Files (*)")
        file = QFile(path)
        if not file.open(QFile.ReadOnly | QFile.Text):
            return

        inf = QTextStream(file)
        json_txt = inf.readAll()

        try:
            json_obj = json.loads(json_txt)
        except ValueError:
            # noinspection PyUnresolvedReferences
            self._show_message('GeoJSON from file invalid',
                               level=Qgis.Warning,
                               duration=10)
            return

        json_geom = geometry_from_json(json_obj)

        if not json_geom:
            # noinspection PyUnresolvedReferences
            self._show_message('GeoJSON geometry from file invalid',
                               level=Qgis.Warning,
                               duration=10)
            return

        geom: QgsGeometry = qgsgeometry_from_geojson(json_geom)
        self._aoi_box.setToGeometry(
            geom,
            QgsCoordinateReferenceSystem("EPSG:4326")
        )

        self.leAOI.setText(json.dumps(json_geom))

        self.zoom_to_aoi()

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


class PlanetMosaicFilter(MOSAIC_BASE, MOSAIC_WIDGET, PlanetFilterMixin):

    cmbBoxMosaicTypes: QComboBox
    leName: QLineEdit

    filtersChanged = pyqtSignal()

    def __init__(self, parent=None, plugin=None):
        super().__init__(parent=parent)
        self.setupUi(self)
        self._plugin = plugin

        self.cmbBoxMosaicTypes.clear()
        for i, (a, b) in enumerate(MOSAIC_ITEM_TYPES):
            self.cmbBoxMosaicTypes.insertItem(i, b, userData=a)
        # Set a default
        self.cmbBoxMosaicTypes.setCurrentIndex(0)
        # noinspection PyUnresolvedReferences
        self.cmbBoxMosaicTypes.currentIndexChanged[int].connect(
            self.filters_changed)

        # noinspection PyUnresolvedReferences
        self.leName.textChanged['QString'].connect(self.filters_changed)

    def sources(self):
        return [self.cmbBoxMosaicTypes.currentData()]

    def filters(self):
        pass

    def filters_as_json(self):
        pass

    def load_filters(self, filter_json):
        pass

    def set_from_request(self, request):
        pass

    @pyqtSlot()
    def filters_changed(self):
        # noinspection PyUnresolvedReferences
        self.filtersChanged.emit()


class PlanetDailyFilter(DAILY_BASE, DAILY_WIDGET, PlanetFilterMixin):
    """
    """
    frameSources: QFrame
    frameDates: QFrame
    leStringIDs: QLineEdit
    endDateEdit: QgsDateTimeEdit
    startDateEdit: QgsDateTimeEdit
    cmbBoxDateType: QComboBox
    cmbBoxDateSort: QComboBox
    frameRangeSliders: QFrame
    rangeCloudCover: PlanetExplorerRangeSlider

    chkBxGroundControl: QCheckBox
    chkBxCanDownload: QCheckBox

    filtersChanged = pyqtSignal()

    SORT_ORDER_DATE_TYPES = [
        ('acquired', 'Acquired'),
        ('published', 'Published'),
        # ('updated', 'Updated'),
    ]

    SORT_ORDER_TYPES = [
        ('desc', 'descending'),
        ('asc', 'ascending'),
    ]

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

        # Set up sources (in 2 columns; layout is grid)
        checked = ['PSScene4Band']
        row_total = floor(len(DAILY_ITEM_TYPES) / 2)
        row = col = 0
        gl = QGridLayout(self.frameSources)
        gl.setContentsMargins(0, 0, 0, 0)
        for a, b in DAILY_ITEM_TYPES:
            # Strip ' Scene' to reduce horizontal width of 2-column layout
            cb = QCheckBox(b.replace(' Scene', ''), parent=self.frameSources)
            cb.setChecked(a in checked)
            cb.setProperty('api-name', a)
            cb.setToolTip(b)
            # noinspection PyUnresolvedReferences
            cb.stateChanged[int].connect(self.filtersChanged)
            gl.addWidget(cb, row, col)
            row += 1
            if row > row_total:
                row = 0
                col += 1

        self.frameSources.setLayout(gl)

        # TODO: (Eventually) Add multi-date range widget with and/or selector

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

        self.cmbBoxDateType.clear()
        for i, (a, b) in enumerate(self.SORT_ORDER_DATE_TYPES):
            self.cmbBoxDateType.insertItem(i, b, userData=a)
        # Set a default (acquired)
        self.cmbBoxDateType.setCurrentIndex(0)
        # noinspection PyUnresolvedReferences
        self.cmbBoxDateType.currentIndexChanged[int].connect(
            self.filters_changed)

        self.cmbBoxDateSort.clear()
        for i, (a, b) in enumerate(self.SORT_ORDER_TYPES):
            self.cmbBoxDateSort.insertItem(i, b, userData=a)
        # Set a default
        self.cmbBoxDateSort.setCurrentIndex(0)
        # noinspection PyUnresolvedReferences
        self.cmbBoxDateSort.currentIndexChanged[int].connect(
            self.filters_changed)

        # TODO: (Eventually) Add multi-field searching, with +/- operation
        #       of adding new field/QLineEdit, without duplicates
        # noinspection PyUnresolvedReferences
        self.leStringIDs.textChanged['QString'].connect(self.filters_changed)

        # TODO: Figure out how area coverage filter works in Explorer

        # TODO: Consolidate range filters for basemap/mosaic reusability
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

        # TODO: Add rest of range sliders

        # Ground control filter checkbox
        # noinspection PyUnresolvedReferences
        self.chkBxGroundControl.stateChanged[int].connect(self.filters_changed)

        # Access Filter checkbox
        # noinspection PyUnresolvedReferences
        self.chkBxCanDownload.stateChanged[int].connect(self.filters_changed)

    def sources(self):
        checked_sources = []
        sources = self.frameSources.findChildren(QCheckBox)
        for source in sources:
            if source.isChecked():
                checked_sources.append(source.property('api-name'))
        return checked_sources

    def sort_order(self):
        return (
            str(self.cmbBoxDateType.currentData()),
            str(self.cmbBoxDateSort.currentData())
        )

    def set_sort_order(self, sort_order):
        self.cmbBoxDateType.setCurrentIndex(
            [v[0] for v in self.SORT_ORDER_DATE_TYPES].index(sort_order[0])
        )
        self.cmbBoxDateSort.setCurrentIndex(
            [v[0] for v in self.SORT_ORDER_TYPES].index(sort_order[1])
        )

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
            if range_low != slider.min and range_high != slider.max:
                slide_filter = range_filter(slider.filter_key,
                                            gte=range_low,
                                            lte=range_high)
            elif range_low != slider.min:
                slide_filter = range_filter(slider.filter_key,
                                            gte=range_low)
            elif range_high != slider.max:
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

        if self.chkBxCanDownload.isChecked():
            dl_permission_filter = permission_filter('assets:download')
            populated_filters.append(dl_permission_filter)

        # Ground_control can be 'true', 'false, or a numeric value
        # Safest to check for not 'false'
        if self.chkBxGroundControl.isChecked():
            gc_filter = not_filter(string_filter('ground_control', 'false'))
            populated_filters.append(gc_filter)

        return populated_filters

    def filters_as_json(self):
        pass

    def load_filters(self, filter_json):
        pass

    def set_from_request(self, request):
        '''
        We assume here that the request has the structure of requests created
        with the plugin. We are not fully parsing the request to analize it, 
        but instead making that assumption to simplify things.
        '''
        checked_sources = request['item_types']
        sources = self.frameSources.findChildren(QCheckBox)
        for source in sources:
            source.setChecked(source.property('api-name') in checked_sources)
        filters = self._filters_from_request(request, 'acquired')
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
            filters = self._filters_from_request(request, slider.filter_key)
            if filters:
                gte = filters[0]['config'].get('gte')
                if gte is not None:
                    if slider.filter_key == 'cloud_cover':
                        gte *= 100.0
                    slider.setRangeLow(gte)
                lte = filters[0]['config'].get('lte')
                if lte is not None:
                    if slider.filter_key == 'cloud_cover':
                        lte *= 100.0
                    slider.setRangeHigh(lte)
            else:
                slider.setRangeLow(slider.min)
                slider.setRangeHigh(slider.max)
        filters = self._filters_from_request(request, filter_type='PermissionFilter')
        if filters:
            self.chkBxCanDownload.setChecked('assets:download' in filters[0]['config'])
        else:
            self.chkBxCanDownload.setChecked(False)
        filters = self._filters_from_request(request, 'ground_control')
        self.chkBxGroundControl.setChecked(bool(filters))

        filters = self._filters_from_request(request, 'id')
        if filters:
            self.leStringIDs.setText(",".join(filters[0]['config']))



    @pyqtSlot()
    def filters_changed(self):
        # noinspection PyUnresolvedReferences
        self.filtersChanged.emit()
