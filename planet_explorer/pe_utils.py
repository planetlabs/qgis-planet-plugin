# -*- coding: utf-8 -*-
"""
***************************************************************************
    p_utils.py
    ---------------------
    Date                 : March 2017, August 2019
    Author               : Alex Bruy, Planet Federal
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

***************************************************************************
Parts of preview_local_item_raster() culled from changeDataSource plugin
                             -------------------
        begin                : 2014-09-04
        copyright            : (C) 2014 by Enrico Ferreguti
        email                : enricofer@gmail.com
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
import logging
import json
import iso8601

from typing import (
    Optional,
    # Union,
    List,
    Tuple,
)

from qgis.PyQt.QtCore import (
    QVariant,    
    QUrl,
    QSettings 
)

from qgis.PyQt.QtGui import (
    QColor,
    QDesktopServices,
    QColor
)

from qgis.PyQt.QtWidgets import (
    QLabel,
    QWidgetAction,
)

from qgis.PyQt.QtXml import (
    QDomDocument,
)

from qgis.core import (
    # QgsPoint,
    QgsPointXY,
    # QgsAbstractGeometry,
    QgsGeometry,
    # QgsGeometryCollection,
    # QgsMultiPolygon,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsUnitTypes,
    QgsDistanceArea,
    QgsCoordinateTransform,
    QgsRectangle,
    QgsProject,
    QgsMapLayer,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsCoordinateReferenceSystem,
    QgsEditorWidgetSetup,
    QgsSimpleLineSymbolLayer,
    QgsLayerTree,
    QgsLayerTreeGroup,
    QgsReadWriteContext,
    QgsApplication
)

from qgis.gui import QgisInterface

from qgis.utils import iface

try:
    from .planet_api.p_client import (
        tile_service_url,
    )

    from .planet_api.p_node import PlanetNode

    from .planet_api.p_utils import geometry_from_json_str_or_obj

    from .planet_api.p_specs import (
        ITEM_TYPE_SPECS,
    )

    from .gui.basemap_layer_widget import (
        PLANET_MOSAICS,
        PLANET_CURRENT_MOSAIC,
        PLANET_MOSAIC_PROC,
        PLANET_MOSAIC_RAMP,
        PLANET_MOSAIC_DATATYPE,
        PLANET_BASEMAP_LABEL,
        WIDGET_PROVIDER_NAME
    )
except ImportError:
    # noinspection PyUnresolvedReferences
    from planet_api.p_client import (
        tile_service_url,
    )

    # noinspection PyUnresolvedReferences
    from planet_api.p_node import PlanetNode

    # noinspection PyUnresolvedReferences
    from planet_api.p_utils import geometry_from_json_str_or_obj

    # noinspection PyUnresolvedReferences
    from planet_api.p_specs import (
        ITEM_TYPE_SPECS,
    )

from qgiscommons2 import(
    settings
)

iface: QgisInterface

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

PROPERTIES = [
    'acquired', 'published', 'strip_id', 'satellite_id',
    'ground_control', 'item_type', 'quality_category',
]

PE_PREVIEW = 'PE thumbnail preview'
PE_PREVIEW_GROUP = 'Planet Explorer temp previews'

plugin_path = os.path.dirname(__file__)

SETTINGS_NAMESPACE = 'planet_explorer'

EMPTY_THUMBNAIL = os.path.join(
    plugin_path, 'planet_api', 'resources', 'empty_thumb.png')

QGIS_LOG_SECTION_NAME = "Planet"

ORDERS_DOWNLOAD_FOLDER = "ordersPath"
DEFAULT_ORDERS_FOLDERNAME = "planet_orders"

BASE_URL = 'https://www.planet.com'

PLANET_COLOR = QColor(0, 157, 165)
ITEM_BACKGROUND_COLOR = QColor(225, 246, 252)
MAIN_AOI_COLOR = PLANET_COLOR
SEARCH_AOI_COLOR = QColor(157, 0, 165)
QUADS_AOI_COLOR = QColor(157, 165, 0)
QUADS_AOI_BODY_COLOR = QColor(157, 165, 0, 70)

NAME = "name"
LINKS = "_links"
TILES = "tiles"
ONEMONTH = "1 mon"
THREEMONTHS = "3 mons"
WEEK = "7 days"
INTERVAL = "interval"
FIRST_ACQUIRED = "first_acquired"
LAST_ACQUIRED = "last_acquired"
DATATYPE = "datatype"

def sentry_dsn():
    return os.environ.get("SEGMENTS_WRITE_KEY")

def segments_write_key():
    return os.environ.get("SENTRY_DSN")

def is_segments_write_key_valid():
    return segments_write_key() is not None

def is_sentry_dsn_valid():
    return sentry_dsn() is not None

def qgsrectangle_for_canvas_from_4326_bbox_coords(coords):
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().crs(),
            QgsProject.instance())        
        extent = QgsRectangle(*coords)
        transform_extent = transform.transformBoundingBox(extent)
        return transform_extent

def qgsgeometry_from_geojson(json_type):
    """
    :param json_type: GeoJSON (as string or `json` object)
    :type json_type: str | dict
    :rtype: QgsGeometry
    """
    geom = QgsGeometry()

    json_geom = geometry_from_json_str_or_obj(json_type)
    if not json_geom:
        return geom

    geom_type = json_geom.get('type', '')
    if geom_type.lower() != 'polygon':
        log.debug('JSON geometry type is not polygon')
        return geom

    coords = json_geom.get('coordinates', None)
    if not coords:
        log.debug('JSON geometry contains no coordinates')
        return geom

    polygon = [[QgsPointXY(item[0], item[1]) for item in polyline] for
               polyline in coords]
    # noinspection PyArgumentList,PyCallByClass
    geom = QgsGeometry.fromPolygonXY(polygon)

    return geom


# QgsGeometryCollection calls segault on macOS (untested on other OS) - 8/2019
# For now, just keep QgsGeometry objs in list, and recreate ops for
#   QgsGeometryCollection, e.g. calculateBoundingBox(), when possible.
#
# def qgsgeometrycollection_from_geojsons(json_types):
#     """
#     :param json_types: List of GeoJSON features, feature collections or
#     geometries as string or `json` object
#     :type json_types: [str | dict]
#     :rtype: QgsGeometryCollection
#     """
#     geom_coll = QgsGeometryCollection()
#     qgs_geoms = [qgsgeometry_from_geojson(j) for j in json_types]
#
#     for qgs_geom in qgs_geoms:
#         qgs_geom: QgsGeometry
#         if qgs_geom.isEmpty():
#             continue
#         # QgsGeometry.get() returns underlying QgsAbstractGeometry
#         geom_coll.addGeometry(qgs_geom.get())
#
#     return geom_coll


def qgsfeature_from_geojson(json_type):
    """
    :param json_type: GeoJSON feature, feature collection or geometry as
    string or `json` object
    :type json_type: str | dict
    :rtype: QgsFeature
    """
    # TODO: Extend to include ALL GeoJSON properties
    # Possibly with underlying OGR interface call...
    # try:
    #     utf8 = QTextCodec.codecForName('UTF-8')
    #     # TODO: Add node id, properties as fields?
    #     fields = QgsFields()
    #     features = QgsJsonUtils().stringToFeatureList(
    #         string=feature_collect_json, fields=fields, encoding=utf8)
    # except Exception:
    #     log.debug('Footprint GeoJSON could not be parsed')
    #     return
    #
    # Or, just add feature fields manually, using...

    geom: QgsGeometry = qgsgeometry_from_geojson(json_type)

    feat = QgsFeature()
    feat.setFields(QgsFields())

    if not geom.isEmpty():
        feat.setGeometry(geom)

    return feat

# QgsGeometryCollection calls segault on macOS (untested on other OS) - 9/2019
# def qgsmultipolygon_from_geojsons(
#         json_types: Union[str, dict]) -> QgsMultiPolygon:
#     """
#     :param json_types: List of GeoJSON features, feature collections or
#     geometries as string or `json` object
#     :type json_types: [str | dict]
#     :rtype: QgsMultiPolygon
#     """
#     skip = 'skipping'
#     multi_p = QgsMultiPolygon()
#
#     qgs_geoms = [qgsgeometry_from_geojson(j) for j in json_types]
#
#     if len(qgs_geoms) < 1:
#         log.debug(f'GeoJSON geometry collection empty, {skip}')
#         return multi_p
#
#     for qgs_geom in qgs_geoms:
#         multi_p.addGeometry(qgs_geom.constGet())
#
#     return multi_p
#
#
# def multipolygon_geojson_from_geojsons(json_types):
#     """
#     :param json_types: List of GeoJSON features, feature collections or
#     geometries as string or `json` object
#     :type json_types: [str | dict]
#     :rtype: str
#     """
#     multi_p: QgsMultiPolygon = qgsmultipolygon_from_geojsons(json_types)
#     return multi_p.asJson()


def area_from_geojsons(
        json_types,
        source_crs='EPSG:4326',
        units_out=QgsUnitTypes.AreaSquareKilometers):
    """
    :param json_types: List of GeoJSON features, feature collections or
    geometries as string or `json` object
    :type json_types: [str | dict]
    :param source_crs: String containing a crs definition, e.g. 'EPSG:4326'
    :type source_crs: str
    :param units_out: Units to convert TO, as QgsUnitTypes enum
    :type units_out: QgsUnitTypes
    :rtype: float
    """
    skip = 'skipping area calculation'
    total_area = 0.0

    qgs_geoms = [qgsgeometry_from_geojson(j) for j in json_types]

    if len(qgs_geoms) < 1:
        log.debug(f'Geometry collection empty, {skip}')
        return total_area

    area = QgsDistanceArea()

    if source_crs != 'EPSG:4326':
        # By default QgsDistanceArea calculates in WGS84
        src_crs = QgsCoordinateReferenceSystem(source_crs)
        if src_crs.isValid():
            # noinspection PyArgumentList
            prj_inst = QgsProject.instance()
            area.setSourceCrs(src_crs, prj_inst.transformContext())
            area.setEllipsoid(src_crs.ellipsoidAcronym())
        else:
            log.warning(f'Passed source_crs Auth ID is invalid: {source_crs}')
            log.warning(skip.capitalize())
            return total_area

    for geom in qgs_geoms:
        total_area += area.measureArea(geom)

    return area.convertAreaMeasurement(total_area, units_out)


def add_menu_section_action(text, menu, tag='b', pad=0.5):
    """Because QMenu.addSection() fails to render with some UI styles, and
    QWidgetAction defaults to no padding.
    :param text: Text for action's title
    :type text: str
    :param menu: QMenu to add section action
    :type menu: QMenu
    :param tag: Simple HTML tag (sans < or >) to style the text, e.g. b, i, u
    :type tag: str
    :param pad: Value for QLabel qss em and ex padding
    :type pad: float
    """
    lbl = QLabel(f'<{tag}>{text}</{tag}>', menu)
    lbl.setStyleSheet(
        f'QLabel {{ padding-left: {pad}em; padding-right: {pad}em; '
        f'padding-top: {pad}ex; padding-bottom: {pad}ex;}}')
    wa = QWidgetAction(menu)
    wa.setDefaultWidget(lbl)
    menu.addAction(wa)
    return wa


def tile_service_data_src_uri(
        item_type_ids: List[str],
        api_key: str,
        tile_hash: Optional[str] = None,
        service: str = 'xyz') -> Optional[str]:
    """
    :param item_type_ids: List of item 'Type:IDs'
    :param api_key: Planet API key
    :param tile_hash: Tile service hash
    :param service: Either 'xyz' or 'wmts'
    :return: Tile service data source URI
    """

    tile_url = tile_service_url(
        item_type_ids, api_key, tile_hash=tile_hash, service=service)

    if tile_url:
        if service.lower() == 'wmts':
            return '&'.join([
                'tileMatrixSet=GoogleMapsCompatible23',
                'crs=EPSG:3857',
                'layers=Combined scene layer',
                'styles=',
                'format=image/png',
                f'url={tile_url}'
            ])
        elif service.lower() == 'xyz':
            return '&'.join([
                'type=xyz',
                'crs=EPSG:3857',
                # 'zmin=0',
                # 'zmax=15',
                # 'format=image/png',
                'format=',
                f'url={tile_url}'
            ])
    else:
        log.debug(f'Tile service data source URI failed, '
                  f'no tile url resolved')

    return None


def temp_preview_group():
    # noinspection PyArgumentList
    root: QgsLayerTree = QgsProject.instance().layerTreeRoot()
    group: QgsLayerTreeGroup = root.findGroup(PE_PREVIEW_GROUP)
    if not group:
        group = root.insertGroup(0, PE_PREVIEW_GROUP)
    return group


def remove_maplayers_by_name(layer_name, only_first=False):
    # noinspection PyArgumentList
    layers = QgsProject.instance().mapLayersByName(layer_name)
    for layer in layers:
        # noinspection PyArgumentList
        QgsProject.instance().removeMapLayer(layer)
        if only_first:
            break


# noinspection PyUnusedLocal
def preview_local_item_raster(local_url, name=PE_PREVIEW,
                              remove_existing=False, epsg_code=None) -> bool:
    if not os.path.exists(local_url):
        log.warning(f'{name} layer local url does not exist:\n'
                    f'{local_url}')
        return False

    if remove_existing:
        remove_maplayers_by_name(name, only_first=True)

    # noinspection PyArgumentList
    layers: List[QgsMapLayer] = QgsProject.instance().mapLayersByName(name)
    if len(layers) < 1 or layers[0].type() != QgsMapLayer.RasterLayer:
        prev_layer = QgsRasterLayer(local_url, name, 'gdal')
        if not prev_layer.isValid():
            log.warning(f'{name} layer failed to load!')
            return False
        log.debug(f'Creating new thumbnail preview with {local_url}')
        # noinspection PyArgumentList
        QgsProject.instance().addMapLayer(prev_layer, False)
        group = temp_preview_group()
        group.addLayer(prev_layer)
        return True
    else:
        prev_layer = layers[0]
        if not prev_layer.isValid():
            log.warning(f'{name} layer is invalid! Removing it.')
            remove_maplayers_by_name(name)
            return False

        log.debug(f'Updating thumbnail preview with {local_url}')

        # Parts culled from changeDataSource plugin by Enrico Ferreguti
        temp_layer = QgsRasterLayer(local_url, 'temp_thumb', 'gdal')
        extent = temp_layer.extent()

        xml_doc = QDomDocument('style')
        xml_mls = xml_doc.createElement('maplayers')
        xml_ml = xml_doc.createElement('maplayer')
        context = QgsReadWriteContext()
        prev_layer.writeLayerXml(xml_ml, xml_doc, context)
        # apply layer definition
        xml_ml.firstChildElement('datasource')\
            .firstChild().setNodeValue(local_url)
        # xml_ml.firstChildElement('provider')
        #     .firstChild().setNodeValue(newProvider)
        # TODO: Have to update CRS, too, or new thumbs will have previous one's
        # If a new extent (for raster) is provided it is applied to the layer
        if extent:
            ml_extent = xml_ml.firstChildElement('extent')
            ml_extent.firstChildElement('xmin')\
                .firstChild().setNodeValue(str(extent.xMinimum()))
            ml_extent.firstChildElement('xmax')\
                .firstChild().setNodeValue(str(extent.xMaximum()))
            ml_extent.firstChildElement('ymin')\
                .firstChild().setNodeValue(str(extent.yMinimum()))
            ml_extent.firstChildElement('ymax')\
                .firstChild().setNodeValue(str(extent.yMaximum()))

        xml_mls.appendChild(xml_ml)
        xml_doc.appendChild(xml_mls)
        prev_layer.readLayerXml(xml_ml, context)
        prev_layer.reload()
        prev_layer.triggerRepaint()
        # iface.actionDraw().trigger()
        # iface.mapCanvas().refresh()
        iface.layerTreeView().refreshLayerSymbology(prev_layer.id())
        return True


def clear_local_item_raster_preview():
    preview_local_item_raster(EMPTY_THUMBNAIL)


def py_to_qvariant_type(py_type: str) -> QVariant.Type:
    type_map = {
        'str': QVariant.String,
        'datetime': QVariant.DateTime,
        'int': QVariant.Int,
        'float': QVariant.Double,
        'bool': QVariant.Bool,
    }
    return type_map.get(py_type, QVariant.Invalid)


def create_preview_vector_layer(node: PlanetNode = None):
    # noinspection PyArgumentList
    marker_line = QgsSimpleLineSymbolLayer(
        color=QColor(110, 88, 232, 100), width=1)
    # FIXME: Save this to a uuid.gpkg file in user-defined dir or project dir
    vlayer = QgsVectorLayer(
        'MultiPolygon?crs=EPSG:4326', 'Footprints', 'memory'
    )
    vlayer.renderer().symbol().changeSymbolLayer(0, marker_line)
    dp = vlayer.dataProvider()

    qgs_fields = [
        QgsField('item_id', QVariant.String),
        QgsField('item_type', QVariant.String),
        QgsField('search_query', QVariant.String),
        QgsField('sort_order', QVariant.String),
    ]

    if node:
        i_specs: dict = ITEM_TYPE_SPECS.get(node.item_type(), None)
        if i_specs:
            i_props: dict = i_specs.get('properties', None)
            if i_props:
                for k, v in i_props.items():
                    qgs_fields.append(QgsField(str(k), py_to_qvariant_type(v)))

    dp.addAttributes(qgs_fields)
    return vlayer


def create_preview_group(
        group_name: str,
        nodes: List[PlanetNode],
        api_key: str,
        tile_service: str = 'xyz',
        search_query: str = None,
        sort_order: Tuple[str, str] = None) -> None:

    if tile_service.lower() not in ['wmts', 'xyz']:
        log.debug(f'Incorrect tile service passed for preview group: '
                  f'{tile_service} (must be wmts or xyz)')
        return

    item_type_ids = [n.item_type_id() for n in nodes]
    uri = tile_service_data_src_uri(
        item_type_ids, api_key, service=tile_service)

    if uri:
        log.debug(f'Tile datasource URI:\n{uri}')

        rlayer = QgsRasterLayer(uri, 'Image previews', 'wms')
    else:
        log.debug('No tile URI for preview group')
        return

    vlayer = None
    if nodes:
        first_node = nodes[0]
        vlayer = create_preview_vector_layer(first_node)
        i_specs: dict = ITEM_TYPE_SPECS.get(first_node.item_type(), None)

        vlayer.startEditing()
        dp = vlayer.dataProvider()
        fields: List[QgsField] = vlayer.fields()

        for node in nodes:
            node: PlanetNode
            feat = QgsFeature()
            feat.setFields(fields)
            qgs_geom = qgsgeometry_from_geojson(node.geometry())
            feat.setGeometry(qgs_geom)

            f_names = [f.name() for f in fields]

            if 'item_id' in f_names:
                feat['item_id'] = node.item_id()
            if 'item_type' in f_names:
                feat['item_type'] = node.item_type()
            if search_query and 'search_query' in f_names:
                feat['search_query'] = json.dumps(search_query)
            if (sort_order and 'sort_order' in f_names
                    and len(sort_order) > 1):
                feat['sort_order'] = ' '.join(sort_order)

            if i_specs:
                node_props: dict = node.item_properties()
                if node_props:
                    for k, v in node_props.items():
                        # vlayer should have same attribute fields, but...
                        if str(k) in f_names:
                            feat[str(k)] = v

            dp.addFeature(feat)

        vlayer.commitChanges()

        # noinspection PyArgumentList
        QgsProject.instance().addMapLayer(vlayer, False)

    # noinspection PyArgumentList
    QgsProject.instance().addMapLayer(rlayer, False)

    # noinspection PyArgumentList
    root: QgsLayerTree = QgsProject.instance().layerTreeRoot()
    group = root.insertGroup(0, f'{group_name} {tile_service.upper()} preview')
    if vlayer:
        group.addLayer(vlayer)
    group.addLayer(rlayer)
    if vlayer:
        iface.setActiveLayer(vlayer)


def zoom_canvas_to_aoi(json_type, iface_obj: QgisInterface = None):
    iface_obj = iface_obj or iface
    if not iface_obj:
        log.debug('No iface object, skipping AOI extent')
        return

    if not json_type:
        log.debug('No AOI defined, skipping zoom to AOI')
        return

    qgs_geom: QgsGeometry = qgsgeometry_from_geojson(json_type)

    # noinspection PyArgumentList
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsProject.instance().crs(),
        QgsProject.instance()
    )
    rect: QgsRectangle = transform.transformBoundingBox(
        qgs_geom.boundingBox())

    if not rect.isEmpty():
        rect.scale(1.05)
        iface_obj.mapCanvas().setExtent(rect)
        iface_obj.mapCanvas().refresh()


def resource_file(f):
    return os.path.join(os.path.dirname(__file__), "resources", f)

def orders_download_folder():
    download_folder = settings.pluginSetting(ORDERS_DOWNLOAD_FOLDER)
    if not os.path.exists(download_folder):
        try:
            os.makedirs(download_folder)
        except OSError:
            download_folder = os.path.join(QgsApplication.qgisSettingsDirPath(), DEFAULT_ORDERS_FOLDERNAME)
            if not os.path.exists(download_folder):
                os.makedirs(download_folder)

    return download_folder

def open_orders_download_folder():
    QDesktopServices.openUrl(
        QUrl.fromLocalFile(orders_download_folder())
    )

def mosaic_title(mosaic):
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

def date_interval_from_mosaics(mosaic):
    date = iso8601.parse_date(mosaic[0][FIRST_ACQUIRED])
    date2 = iso8601.parse_date(mosaic[-1][LAST_ACQUIRED])
    dates = f'{date.strftime("%B %Y")} - {date2.strftime("%B %Y")}'
    return dates

def add_xyz(name, url, zmin, zmax):
    s = QSettings()    
    s.setValue(f'qgis/connections-xyz/{name}/zmin', zmin)
    s.setValue(f'qgis/connections-xyz/{name}/zmin', zmax)
    s.setValue(f'qgis/connections-xyz/{name}/username', "")
    s.setValue(f'qgis/connections-xyz/{name}/password', "")
    s.setValue(f'qgis/connections-xyz/{name}/authcfg', "")
    s.setValue(f'qgis/connections-xyz/{name}/url', url)
    uri = f'type=xyz&url={url}&zmin={zmin}&zmax={zmax}'
    layer = QgsRasterLayer(uri, name, 'wms')
    QgsProject.instance().addMapLayer(layer)

def add_mosaics_to_qgis_project(mosaics, name):
    mosaic_names = [(mosaic_title(mosaic), mosaic[NAME]) for mosaic in mosaics]
    if len(mosaics) > 1:
        label = date_interval_from_mosaics(mosaics)        
    else:
        label = mosaics[0][NAME]
    tile_url = mosaics[0][LINKS][TILES]
    uri = f'type=xyz&url={tile_url}'
    layer = QgsRasterLayer(uri, name, 'wms')
    layer.setCustomProperty(PLANET_CURRENT_MOSAIC, mosaic_title(mosaics[0]))
    layer.setCustomProperty(PLANET_BASEMAP_LABEL, label)
    layer.setCustomProperty(PLANET_MOSAIC_PROC, "default")
    layer.setCustomProperty(PLANET_MOSAIC_RAMP, "")
    layer.setCustomProperty(PLANET_MOSAIC_DATATYPE, mosaics[0][DATATYPE])
    layer.setCustomProperty(PLANET_MOSAICS, json.dumps(mosaic_names))
    QgsProject.instance().addMapLayer(layer)
    layer.setCustomProperty("embeddedWidgets/count", 1)
    layer.setCustomProperty("embeddedWidgets/0/id", WIDGET_PROVIDER_NAME) 
    view = iface.layerTreeView()
    view.model().refreshLayerLegend(view.currentNode())
    view.currentNode().setExpanded(True)    

# ******************* Functions from previous plugin below *******************


def catalog_layer():
    """Returns Planet Explorer catalog layer if it is already exists or
    creates it and then returns.
    """
    # noinspection PyArgumentList
    layers = QgsProject.instance().mapLayersByName('Planet Explorer catalog')
    if len(layers) == 0:
        layer = QgsVectorLayer(
            'Polygon?crs=epsg:4326&index=yes',
            'Planet Explorer catalog',
            'memory')
        provider = layer.dataProvider()
        provider.addAttributes(
            [
                QgsField('id', QVariant.String, '', 25, 0),
                QgsField('acquired', QVariant.String, '', 35, 0),
                QgsField('metadata', QVariant.String, '', 2000, 0),
                QgsField('thumbnail', QVariant.String, '', 2000, 0),
            ]
        )
        layer.updateFields()
        if os.name == 'nt':
            layer.loadNamedStyle(
                os.path.join(plugin_path, 'resources', 'footprints-win.qml'),
                categories=QgsMapLayer.AllStyleCategories)
        else:
            layer.loadNamedStyle(
                os.path.join(plugin_path, 'resources', 'footprints-nix.qml'),
                categories=QgsMapLayer.AllStyleCategories)
        setup_edit_widgets(layer)
        # noinspection PyArgumentList
        QgsProject.instance().addMapLayer(layer)
        return layer
    else:
        return layers[0]


def clear_layer(layer):
    """Clear given vector layer from features
    """
    if layer.featureCount() > 0:
        provider = layer.dataProvider()
        provider.deleteFeatures(layer.allFeatureIds())
        layer.updateExtents()


def load_raster_layer(file_path):
    """Load raster layer from given file path.
    """
    img_group = imagery_group()

    file_name = os.path.splitext(os.path.basename(file_path))[0]
    if os.path.isfile(file_path):
        layer = QgsRasterLayer(file_path, file_name, 'gdal')
        if layer.isValid():
            # noinspection PyArgumentList
            QgsProject.instance().addMapLayer(layer, False)
            img_group.addLayer(layer)


def imagery_group():
    """Returns PlanetLabs imagery group if it is already exists or
    creates it and then returns.
    """
    # noinspection PyArgumentList
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup('PlanetLabs imagery')
    if group is None:
        group = root.insertGroup(0, 'PlanetLabs imagery')

    return group


def json_to_key_value(data):
    """Convert JSON object into key-value pairs

    Adapted from Catalog Planet Labs plugin by Luiz Motta
    https://github.com/lmotta/catalogpl_plugin
    """
    def parse_item(item):

        def add_value(val):
            items.append('{}={}'.format(', '.join(keys), val))

        if not isinstance(item, (dict, list)):
            add_value(item)
            return

        if isinstance(item, dict):
            for k, v in sorted(item.items()):
                keys.append('{}'.format(k))
                parse_item(v)
                del keys[-1]

    keys = []
    items = []

    parse_item(data)

    return '\n'.join(items)


def json_to_footprints(data):
    layer = catalog_layer()
    fields = layer.fields()

    features = []
    for item in data['features']:
        ft = QgsFeature()
        ft.setFields(fields)

        coords = item['geometry']['coordinates']
        polygon = [[QgsPointXY(item[0], item[1]) for item in polyline]
                   for polyline in coords]
        # noinspection PyArgumentList,PyCallByClass
        ft.setGeometry(QgsGeometry.fromPolygonXY(polygon))

        metadata = item['properties']

        ft['id'] = item['id']
        ft['acquired'] = metadata['acquired']
        del metadata['acquired']
        ft['metadata'] = json_to_key_value(metadata)

        features.append(ft)

    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    layer.triggerRepaint()


def zoom_to_layer(layer):
    layer_extent = layer.extent()

    # transform extent
    layer_extent = iface.mapCanvas().mapSettings().layerExtentToOutputExtent(
        layer, layer_extent)

    if layer_extent.isNull():
        return

    # increase bounding box with 5%, so that layer is a bit inside the borders
    layer_extent.scale(1.05)

    # zoom to bounding box
    iface.mapCanvas().setExtent(layer_extent)
    iface.mapCanvas().refresh()


def setup_edit_widgets(layer):
    # noinspection PyUnusedLocal
    form_config = layer.editFormConfig()
    idx = layer.fields().indexFromName('thumbnail')
    if idx != -1:
        config = {
            'DocumentViewer': 1,
            'DocumentViewerHeight': 0,
            'DocumentViewerWidth': 0,
            'FileWidget': True,
            'FileWidgetButton': True,
            'FileWidgetFilter': '',
            'PropertyCollection': {
                'name': None,
                'properties': {},
                'type': 'collection'
            },
            'RelativeStorage': 0,
            'StorageMode': 0,
        }
        setup = QgsEditorWidgetSetup('ExternalResource', config)
        layer.setEditorWidgetSetup(idx, setup)

    idx = layer.fields().indexFromName('metadata')
    if idx != -1:
        setup = QgsEditorWidgetSetup(
            'TextEdit',
            {
                'IsMultiline': True,
            }
        )
        layer.setEditorWidgetSetup(idx, setup)

def open_link_with_browser(url):
    QDesktopServices.openUrl(QUrl(url))