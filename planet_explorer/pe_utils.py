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
"""
__author__ = "Planet Federal"
__date__ = "August 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import configparser
import json
import logging
import os
import re
import urllib
from typing import List, Optional, Tuple  # Union,
from urllib.parse import quote

import iso8601

from planet.api.exceptions import APIException
from planet.api.models import Mosaics

from qgis.PyQt.QtCore import QVariant, QUrl, QSettings

from qgis.PyQt.QtGui import QColor, QDesktopServices

from qgis.PyQt.QtWidgets import (
    QLabel,
    QWidgetAction,
)

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsJsonUtils,
    QgsLayerTree,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsSimpleLineSymbolLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

from qgis.utils import iface as qgisiface

from .planet_api import PlanetClient
from .planet_api.p_client import tile_service_url
from .planet_api.p_utils import geometry_from_json_str_or_obj, geometry_from_request

# This can be further patched using the test.utils module
iface = qgisiface
if iface is None:
    from qgis.testing.mocked import get_iface

    iface = get_iface()

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

PROPERTIES = [
    "acquired",
    "published",
    "strip_id",
    "satellite_id",
    "ground_control",
    "item_type",
    "quality_category",
]

PE_PREVIEW = "PE thumbnail preview"
PE_PREVIEW_GROUP = "Planet Explorer temp previews"

plugin_path = os.path.dirname(__file__)

SETTINGS_NAMESPACE = "planet_explorer"

EMPTY_THUMBNAIL = os.path.join(
    plugin_path, "planet_api", "resources", "empty_thumb.png"
)

QGIS_LOG_SECTION_NAME = "Planet"

ORDERS_DOWNLOAD_FOLDER_SETTING = "ordersPath"
DEFAULT_ORDERS_FOLDERNAME = "planet_orders"
ENABLE_CLIP_SETTING = "enableClip"
ENABLE_STAC_METADATA = "enableStacMetadata"
ENABLE_HARMONIZATION_SETTING = "enableHarmonization"

BASE_URL = "https://www.planet.com"

PLANET_COLOR = QColor(0, 157, 165)
ITEM_BACKGROUND_COLOR = QColor(225, 246, 252)
MAIN_AOI_COLOR = PLANET_COLOR
SEARCH_AOI_COLOR = QColor(157, 0, 165)
QUADS_AOI_COLOR = QColor(157, 165, 0)
QUADS_AOI_BODY_COLOR = QColor(157, 165, 0, 70)

PLANET_PREVIEW_ITEM_IDS = "planet/previewItemIds"

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
ID = "id"
ITEM_TYPE = "item_type"
ITEM_TYPES = "item_types"

PLANET_CURRENT_MOSAIC = "planet/currentMosaic"
PLANET_MOSAICS = "planet/mosaics"
PLANET_MOSAIC_PROC = "planet/mosaicProc"
PLANET_MOSAIC_RAMP = "planet/mosaicRamp"
PLANET_MOSAIC_DATATYPE = "planet/mosaicDatatype"
PLANET_BASEMAP_LABEL = "planet/basemapLabel"
WIDGET_PROVIDER_NAME = "planetmosaiclayerwidget"


# This will be replaced by the paver package task
COMMIT_ID = ""


def qgsrectangle_for_canvas_from_4326_bbox_coords(coords):
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsProject.instance().crs(),
        QgsProject.instance(),
    )
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

    geom_type = json_geom.get("type", "")
    if geom_type.lower() not in ["polygon", "multipolygon"]:
        log.debug("JSON geometry type is not polygon")
        return geom

    coords = json_geom.get("coordinates", None)
    if not coords:
        log.debug("JSON geometry contains no coordinates")
        return geom

    try:
        feats = QgsJsonUtils.stringToFeatureList(
            json.dumps(json_geom), QgsFields(), None
        )
        geom = feats[0].geometry()
    except Exception:
        pass  # will return an empty geom

    return geom


def area_coverage_for_image(image, request):
    aoi_geom = geometry_from_request(request)
    if aoi_geom is None:
        return None
    aoi_qgsgeom = qgsgeometry_from_geojson(aoi_geom)
    aoi_area = aoi_qgsgeom.area()
    if aoi_area == 0:
        return 100
    image_qgsgeom = qgsgeometry_from_geojson(image["geometry"])
    intersection = aoi_qgsgeom.intersection(image_qgsgeom)
    area_coverage = intersection.area() / aoi_area * 100
    return area_coverage


def add_menu_section_action(text, menu, tag="b", pad=0.5):
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
    lbl = QLabel(f"<{tag}>{text}</{tag}>", menu)
    lbl.setStyleSheet(
        f"QLabel {{ padding-left: {pad}em; padding-right: {pad}em; "
        f"padding-top: {pad}ex; padding-bottom: {pad}ex;}}"
    )
    wa = QWidgetAction(menu)
    wa.setDefaultWidget(lbl)
    menu.addAction(wa)
    return wa


def tile_service_data_src_uri(
    item_type_ids: List[str], tile_hash: Optional[str] = None, service: str = "xyz"
) -> Optional[str]:
    """
    :param item_type_ids: List of item 'Type:IDs'
    :param api_key: Planet API key
    :param tile_hash: Tile service hash
    :param service: Either 'xyz' or 'wmts'
    :return: Tile service data source URI
    """

    tile_url = tile_service_url(item_type_ids, tile_hash=tile_hash, service=service)

    if tile_url:
        if service.lower() == "wmts":
            return "&".join(
                [
                    "tileMatrixSet=GoogleMapsCompatible23",
                    "crs=EPSG:3857",
                    "layers=Combined scene layer",
                    "styles=",
                    "format=image/png",
                    f"url={tile_url}",
                ]
            )
        elif service.lower() == "xyz":
            return "&".join(
                [
                    "type=xyz",
                    "crs=EPSG:3857",
                    # 'zmin=0',
                    # 'zmax=15',
                    # 'format=image/png',
                    "format=",
                    f"url={tile_url}",
                ]
            )
    else:
        log.debug("Tile service data source URI failed, no tile url resolved")

    return None


def create_preview_vector_layer(image):
    marker_line = QgsSimpleLineSymbolLayer(color=QColor(110, 88, 232, 100), width=1)
    # FIXME: Save this to a uuid.gpkg file in user-defined dir or project dir
    vlayer = QgsVectorLayer("MultiPolygon?crs=EPSG:4326", "Footprints", "memory")
    vlayer.renderer().symbol().changeSymbolLayer(0, marker_line)
    dp = vlayer.dataProvider()

    qgs_fields = [
        QgsField("item_id", QVariant.String),
        QgsField("item_type", QVariant.String),
        QgsField("search_query", QVariant.String),
        QgsField("sort_order", QVariant.String),
    ]

    prop_dates = ["acquired", "published", "updated"]
    prop_int = ["anomalous_pixels"]
    prop_double = [
        "clear_confidence_percent",
        "clear_percent",
        "cloud_cover",
        "cloud_percent",
        "ground_control_ratio",  # Only SkySat
        "gsd",
        "heavy_haze_percent",
        "light_haze_percent",
        "pixel_resolution",
        "satellite_azimuth",
        "shadow_percent",
        "snow_ice_percent",
        "sun_azimuth",
        "sun_elevation",
        "view_angle",
        "visible_confidence_percent",
        "visible_percent",
    ]
    prop_boolean = ["ground_control"]  # Only PlanetScope

    for prop in image["properties"]:
        # Determines the field types
        if prop in prop_dates:
            field_type = QVariant.DateTime
        elif prop in prop_int:
            field_type = QVariant.Int
        elif prop in prop_double:
            field_type = QVariant.Double
        elif prop in prop_boolean:
            field_type = QVariant.Bool
        else:
            # All other properties/fields will default to string
            field_type = QVariant.String

        qgs_fields.append(QgsField(str(prop), field_type))

    dp.addAttributes(qgs_fields)
    return vlayer


def create_preview_group(
    group_name: str,
    images: List[dict],
    footprints_filename=None,
    catalog_layer_name=None,
    tile_service: str = "xyz",
    search_query: str = None,
    sort_order: Tuple[str, str] = None,
) -> None:

    if tile_service.lower() not in ["wmts", "xyz"]:
        log.debug(
            "Incorrect tile service passed for preview group: "
            f"{tile_service} (must be wmts or xyz)"
        )
        return

    item_ids = [f"{img['properties'][ITEM_TYPE]}:{img[ID]}" for img in images]
    uri = tile_service_data_src_uri(item_ids, service=tile_service)

    if uri:
        log.debug(f"Tile datasource URI:\n{uri}")

        rlayer = QgsRasterLayer(uri, "Image previews", "wms")
        rlayer.setCustomProperty(PLANET_PREVIEW_ITEM_IDS, json.dumps(item_ids))

        if tile_service == "xyz" and catalog_layer_name is not None:
            url = uri.split("url=")[-1]
            s = QSettings()
            s.setValue(f"qgis/connections-xyz/{catalog_layer_name}/username", "")
            s.setValue(f"qgis/connections-xyz/{catalog_layer_name}/password", "")
            s.setValue(f"qgis/connections-xyz/{catalog_layer_name}/authcfg", "")
            s.setValue(
                f"qgis/connections-xyz/{catalog_layer_name}/url",
                url.replace(PlanetClient.getInstance().api_key(), ""),
            )
    else:
        log.debug("No tile URI for preview group")
        return

    vlayer = None
    if images:
        vlayer = create_preview_vector_layer(images[0])

        vlayer.startEditing()
        dp = vlayer.dataProvider()
        fields: List[QgsField] = vlayer.fields()

        for img in images:
            feat = QgsFeature()
            feat.setFields(fields)
            qgs_geom = qgsgeometry_from_geojson(img["geometry"])
            feat.setGeometry(qgs_geom)

            f_names = [f.name() for f in fields]

            if "item_id" in f_names:
                feat["item_id"] = img[ID]

            if search_query and "search_query" in f_names:
                feat["search_query"] = json.dumps(search_query)
            if sort_order and "sort_order" in f_names and len(sort_order) > 1:
                feat["sort_order"] = " ".join(sort_order)

            props: dict = img["properties"]
            for k, v in props.items():
                if k in f_names:
                    feat[k] = v

            dp.addFeature(feat)

        vlayer.commitChanges()

        if footprints_filename:
            QgsVectorFileWriter.writeAsVectorFormat(
                vlayer, footprints_filename, "UTF-8"
            )
            gpkglayer = QgsVectorLayer(footprints_filename, "Footprints")
            gpkglayer.setRenderer(vlayer.renderer().clone())
            vlayer = gpkglayer
        QgsProject.instance().addMapLayer(vlayer, False)

    # noinspection PyArgumentList
    QgsProject.instance().addMapLayer(rlayer, False)

    # noinspection PyArgumentList
    root: QgsLayerTree = QgsProject.instance().layerTreeRoot()
    group = root.insertGroup(0, f"{group_name} {tile_service.upper()} preview")
    if vlayer:
        group.addLayer(vlayer)
    group.addLayer(rlayer)
    if vlayer:
        iface.setActiveLayer(vlayer)


def zoom_canvas_to_geometry(geom):
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsProject.instance().crs(),
        QgsProject.instance(),
    )
    rect: QgsRectangle = transform.transformBoundingBox(geom.boundingBox())

    if not rect.isEmpty():
        rect.scale(1.05)
        iface.mapCanvas().setExtent(rect)
        iface.mapCanvas().refresh()


def zoom_canvas_to_aoi(json_type):
    if not json_type:
        log.debug("No AOI defined, skipping zoom to AOI")
        return

    geom: QgsGeometry = qgsgeometry_from_geojson(json_type)
    zoom_canvas_to_geometry(geom)


def resource_file(f):
    return os.path.join(os.path.dirname(__file__), "resources", f)


def orders_download_folder():
    download_folder = (
        QSettings().value(f"{SETTINGS_NAMESPACE}/{ORDERS_DOWNLOAD_FOLDER_SETTING}", "")
        or ""
    )
    if not os.path.exists(download_folder):
        try:
            os.makedirs(download_folder)
        except OSError:
            download_folder = os.path.join(
                QgsApplication.qgisSettingsDirPath(), DEFAULT_ORDERS_FOLDERNAME
            )
            if not os.path.exists(download_folder):
                os.makedirs(download_folder)

    return download_folder


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


def add_mosaics_to_qgis_project(
    mosaics, name, proc="default", ramp="", zmin=0, zmax=22, add_xyz_server=False
):
    mosaic_names = [(mosaic_title(mosaic), mosaic[NAME]) for mosaic in mosaics]
    tile_url = f"{mosaics[0][LINKS][TILES]}&ua={user_agent()}"
    uri = f"type=xyz&url={tile_url}&zmin={zmin}&zmax={zmax}"
    layer = QgsRasterLayer(uri, name, "wms")
    layer.setCustomProperty(PLANET_CURRENT_MOSAIC, mosaic_title(mosaics[0]))
    layer.setCustomProperty(PLANET_MOSAIC_PROC, proc)
    layer.setCustomProperty(PLANET_MOSAIC_RAMP, ramp)
    layer.setCustomProperty(PLANET_MOSAIC_DATATYPE, mosaics[0][DATATYPE])
    layer.setCustomProperty(PLANET_MOSAICS, json.dumps(mosaic_names))
    QgsProject.instance().addMapLayer(layer)
    layer.setCustomProperty("embeddedWidgets/count", 1)
    layer.setCustomProperty("embeddedWidgets/0/id", WIDGET_PROVIDER_NAME)
    view = iface.layerTreeView()
    view.layerTreeModel().refreshLayerLegend(view.currentNode())
    view.currentNode().setExpanded(True)
    if add_xyz_server:
        s = QSettings()
        s.setValue(f"qgis/connections-xyz/{name}/zmin", zmin)
        s.setValue(f"qgis/connections-xyz/{name}/zmax", zmax)
        s.setValue(f"qgis/connections-xyz/{name}/username", "")
        s.setValue(f"qgis/connections-xyz/{name}/password", "")
        s.setValue(f"qgis/connections-xyz/{name}/authcfg", "")
        procparam = quote(f"&proc={proc}") if proc != "rgb" else ""
        rampparam = quote(f"&color={ramp}") if ramp else ""
        full_uri = f"{tile_url}{procparam}{rampparam}"
        s.setValue(
            f"qgis/connections-xyz/{name}/url",
            full_uri.replace(PlanetClient.getInstance().api_key(), ""),
        )


def open_link_with_browser(url):
    QDesktopServices.openUrl(QUrl(url))


def datatype_from_mosaic_name(name):
    client = PlanetClient.getInstance()
    if client.has_api_key():
        try:
            resp = client.get_mosaic_by_name(name)

            resp_res = resp.get()
            resp_list = resp_res[Mosaics.ITEM_KEY] if resp_res is not None else []
            resp_item = resp_list[0][DATATYPE] if len(resp_list) > 0 else None

            return resp_item
        except APIException:
            raise
            return ""
    else:
        return ""


def mosaic_name_from_url(url):
    url = urllib.parse.unquote(url)
    pattern = re.compile(
        r".*&url=https://tiles[0-3]?\..*?/basemaps/v1/planet-tiles/(.*?)/.*"
    )
    result = pattern.search(url)
    if result is not None:
        mosaic = result.group(1)
        return mosaic
    else:
        return None


def add_widget_to_layer(layer):
    if (
        is_planet_url(layer.source())
        and PLANET_MOSAICS not in layer.customPropertyKeys()
    ):
        proc = "default"
        ramp = ""
        mosaic = mosaic_name_from_url(layer.source())
        if mosaic is not None:
            tokens = layer.source().split("&")
            for token in tokens:
                if token.startswith("url="):
                    subtokens = urllib.parse.unquote(token).split("&")
                    for subtoken in subtokens:
                        if subtoken.startswith("proc="):
                            proc = subtoken.split("=")[1]
                        if subtoken.startswith("ramp="):
                            ramp = subtoken.split("=")[1]
            datatype = datatype_from_mosaic_name(mosaic)
            mosaics = [(mosaic, mosaic)]
            layer.setCustomProperty(PLANET_MOSAIC_PROC, proc)
            layer.setCustomProperty(PLANET_MOSAIC_RAMP, ramp)
            layer.setCustomProperty(PLANET_MOSAIC_DATATYPE, datatype)
            layer.setCustomProperty(PLANET_MOSAICS, json.dumps(mosaics))
            layer.setCustomProperty("embeddedWidgets/count", 1)
            layer.setCustomProperty("embeddedWidgets/0/id", WIDGET_PROVIDER_NAME)
            view = iface.layerTreeView()
            current_node = view.currentNode()
            current_node.setExpanded(True) if current_node is not None else None


def is_planet_url(url):
    url = urllib.parse.unquote(url)
    loggedInPattern = re.compile(
        r".*&url=https://tiles[0-3]?\.planet\.com/.*?api_key=.*"
    )
    loggedOutPattern = re.compile(
        r".*&url=https://tiles[0-3]?\.\{planet_url\}/.*?api_key=.*"
    )
    isloggedInPattern = loggedInPattern.search(url) is not None
    isloggedOutPattern = loggedOutPattern.search(url) is not None

    singleUrl = url.count("&url=") == 1

    return singleUrl and (isloggedOutPattern or isloggedInPattern)


def plugin_version(add_commit=False):
    config = configparser.ConfigParser()
    path = os.path.join(os.path.dirname(__file__), "metadata.txt")
    config.read(path)
    version = config.get("general", "version")
    if add_commit:
        version = f"{version}-{COMMIT_ID}"
    return version


def user_agent():
    return f"qgis-{Qgis.QGIS_VERSION};planet-explorer{plugin_version()}"
