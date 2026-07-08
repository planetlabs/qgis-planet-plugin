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
from pathlib import Path
from typing import Any
from urllib.parse import quote

import iso8601
from planet.exceptions import APIError
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
from qgis.PyQt.QtCore import QSettings, QUrl, QVariant
from qgis.PyQt.QtGui import QColor, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QLabel,
    QWidgetAction,
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

LANDSAT_ID = "Landsat8L1G"
SENTINEL_ID = "Sentinel2L1C"
RAPIDEYE_ID = "REScene"
RAPIDEYE_ORTHO_ID = "REOrthoTile"

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
ENABLE_COMPOSITE = "enableComposite"
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


def qgsrectangle_for_canvas_from_4326_bbox_coords(coords: tuple) -> QgsRectangle:
    """Create a QgsRectangle for the current canvas from EPSG:4326 bounding box coordinates.

    Args:
        coords (tuple): Bounding box coordinates in EPSG:4326 (minx, miny, maxx, maxy).

    Returns:
        QgsRectangle: Transformed rectangle in the current project's CRS.
    """
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsProject.instance().crs(),
        QgsProject.instance(),
    )
    extent = QgsRectangle(*coords)
    transform_extent = transform.transformBoundingBox(extent)
    return transform_extent


def qgsgeometry_from_geojson(json_type: str | dict) -> QgsGeometry:
    """Create a QGIS geometry from GeoJSON.

    Args:
        json_type (str | dict): GeoJSON as a string or JSON object.

    Returns:
        QgsGeometry: Geometry created from the GeoJSON. Returns an empty
            geometry if the input is invalid or cannot be converted.
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
        feats = QgsJsonUtils.stringToFeatureList(json.dumps(json_geom), QgsFields())
        geom = feats[0].geometry()
    except Exception:
        log.debug("JSON to geometry conversion failed")
        pass  # will return an empty geom

    return geom


def area_coverage_for_image(image: dict[str, Any], request: str | dict) -> float | None:
    """Get the area coverage percentage of an image's geometry
    within a given AOI defined by a request.

    Args:
        image (dict[str, Any]): Image metadata containing geometry information.
        request (str | dict): AOI request containing geometry information.

    Returns:
        float | None: Area coverage percentage of the image within
        the AOI. Returns None if AOI geometry is invalid.
    """
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
    """Add a styled section action to a menu.

    Because `QMenu.addSection()` fails to render with some UI styles, and
    `QWidgetAction` defaults to no padding.

    Args:
        text (str): Text for the action title.
        menu (QMenu): Menu to add the section action to.
        tag (str): Simple HTML tag, without angle brackets, used to style the
            text, for example `b`, `i`, or `u`.
        pad (float): Padding value for the `QLabel` QSS `em` and `ex` units.

    Returns:
        QWidgetAction: The created section action.
    """
    lbl = QLabel(f"<{tag}>{text}</{tag}>", menu)
    lbl.setStyleSheet(
        f"QLabel {{ padding-left: {pad}em; padding-right: {pad}em; "  # noqa: E702 E201
        f"padding-top: {pad}ex; padding-bottom: {pad}ex; }}"  # noqa: E702 E202
    )
    wa = QWidgetAction(menu)
    wa.setDefaultWidget(lbl)
    menu.addAction(wa)
    return wa


def tile_service_data_src_uri(
    item_type_ids: list[str], tile_hash: str | None = None, service: str = "xyz"
) -> str | None:
    """
    Args:
        item_type_ids (list[str]): List of item type IDs.
        tile_hash (str): Tile service hash.
        service (str): Either "xyz" or "wmts".

    Returns:
        str: Tile service data source URI.
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
    """Create an in-memory vector layer for displaying image footprints.

    Builds a MultiPolygon layer in EPSG:4326 with a semi-transparent purple
    outline style. Fields are derived from the image's properties, with types
    inferred from known Planet metadata field names.

    Args:
        image (dict): Planet image dictionary containing a ``properties`` key
            with metadata fields used to define the layer's attribute schema.

    Returns:
        QgsVectorLayer: In-memory footprint layer with fields and style applied,
            not yet added to the QGIS project.
    """
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


def _register_xyz_connection(catalog_layer_name: str, uri: str) -> None:
    """Register a tile URL in QGIS XYZ connections registry.

    Args:
        catalog_layer_name (str): Name to register the connection under.
        uri (str): Tile datasource URI.
    """
    url = uri.split("url=")[-1]
    s = QSettings()
    s.setValue(f"qgis/connections-xyz/{catalog_layer_name}/username", "")
    s.setValue(f"qgis/connections-xyz/{catalog_layer_name}/password", "")
    s.setValue(f"qgis/connections-xyz/{catalog_layer_name}/authcfg", "")
    s.setValue(
        f"qgis/connections-xyz/{catalog_layer_name}/url",
        url.replace(PlanetClient.getInstance().api_key, ""),
    )


def _build_raster_layer(
    item_ids: list,
    tile_service: str,
    catalog_layer_name: str | None,
) -> QgsRasterLayer | None:
    """Build a raster layer from the tile service URI.

    Args:
        item_ids (list): List of Planet item IDs.
        tile_service (str): Tile service type (xyz or wmts).
        catalog_layer_name (str | None): Name to register XYZ connection under.

    Returns:
        QgsRasterLayer | None: Raster layer or None if URI is not available.
    """
    uri = tile_service_data_src_uri(item_ids, service=tile_service)
    if not uri:
        log.debug("No tile URI for preview group")
        return None

    log.debug(f"Tile datasource URI: \n{uri}")
    rlayer = QgsRasterLayer(uri, "Image previews", "wms")
    rlayer.setCustomProperty(PLANET_PREVIEW_ITEM_IDS, json.dumps(item_ids))

    if tile_service == "xyz" and catalog_layer_name is not None:
        _register_xyz_connection(catalog_layer_name, uri)

    return rlayer


def _build_vector_layer(
    images: list[dict],
    footprints_filename: str | None,
    search_query: str | None,
    sort_order: tuple[str, str] | None,
) -> QgsVectorLayer | None:
    """Build a vector layer from image footprints.

    Args:
        images (list[dict]): List of Planet image dictionaries.
        footprints_filename (str | None): Path to save footprints as GeoPackage.
        search_query (str | None): Search query to store on each feature.
        sort_order (tuple[str, str] | None): Sort field and direction.

    Returns:
        QgsVectorLayer | None: Vector layer or None if no images.
    """
    if not images:
        return None

    vlayer = create_preview_vector_layer(images[0])
    vlayer.startEditing()
    dp = vlayer.dataProvider()
    fields: list[QgsField] = vlayer.fields()
    f_names = [f.name() for f in fields]

    for img in images:
        feat = QgsFeature()
        feat.setFields(fields)
        feat.setGeometry(qgsgeometry_from_geojson(img["geometry"]))

        if "item_id" in f_names:
            feat["item_id"] = img[ID]
        if search_query and "search_query" in f_names:
            feat["search_query"] = json.dumps(search_query)
        if sort_order and "sort_order" in f_names and len(sort_order) > 1:
            feat["sort_order"] = " ".join(sort_order)

        for k, v in img["properties"].items():
            if k in f_names:
                feat[k] = v

        dp.addFeature(feat)

    vlayer.commitChanges()

    if footprints_filename:
        QgsVectorFileWriter.writeAsVectorFormat(vlayer, footprints_filename, "UTF-8")
        gpkglayer = QgsVectorLayer(footprints_filename, "Footprints")
        gpkglayer.setRenderer(vlayer.renderer().clone())
        vlayer = gpkglayer

    QgsProject.instance().addMapLayer(vlayer, False)
    return vlayer


def create_preview_group(
    group_name: str,
    images: list[dict],
    footprints_filename: str | None = None,
    catalog_layer_name: str | None = None,
    tile_service: str = "xyz",
    search_query: str | None = None,
    sort_order: tuple[str, str] | None = None,
) -> None:
    """Create a QGIS layer group containing a tile preview layer and footprint vector layer.

    Adds an XYZ or WMTS raster layer from the Planet tile service alongside an
    optional footprint vector layer. If ``footprints_filename`` is provided, the
    footprints are saved to disk as a GeoPackage. Optionally registers the tile
    connection in QGIS's XYZ server registry.

    Args:
        group_name (str): Name prefix for the layer group.
        images (list[dict]): List of Planet image dictionaries with geometry and properties.
        footprints_filename (str | None): Path to save footprints as a GeoPackage.
            If None, the footprint layer is kept in memory only.
        catalog_layer_name (str | None): If provided, registers the tile URL under
            this name in ``qgis/connections-xyz``.
        tile_service (str): Tile service type, either ``"xyz"`` or ``"wmts"``.
        search_query (str | None): Original search query to store on each feature.
        sort_order (tuple[str, str] | None): Sort field and direction to store on each feature.
    """

    if tile_service.lower() not in ["wmts", "xyz"]:
        log.debug(
            "Incorrect tile service passed for preview group: "
            f"{tile_service} (must be wmts or xyz)"
        )
        return

    item_ids = [f"{img['properties'][ITEM_TYPE]}:{img[ID]}" for img in images]
    rlayer = _build_raster_layer(item_ids, tile_service, catalog_layer_name)
    if rlayer is None:
        return

    vlayer = _build_vector_layer(images, footprints_filename, search_query, sort_order)

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


def zoom_canvas_to_geometry(geom: QgsGeometry):
    """Zoom the QGIS map canvas to fit a geometry's bounding box.

    Reprojects the geometry from EPSG:4326 to the project CRS, scales the
    extent by 5% for padding, then sets and refreshes the map canvas.
    Does nothing if the resulting extent is empty.

    Args:
        geom (QgsGeometry): Geometry in EPSG:4326 to zoom to.
    """
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


def zoom_canvas_to_aoi(json_type: str | dict):
    """Zoom the QGIS map canvas to a GeoJSON area of interest.

    Does nothing if ``json_type`` is empty or None.

    Args:
        json_type (str | dict): GeoJSON geometry or feature as a string or dictionary.
    """
    if not json_type:
        log.debug("No AOI defined, skipping zoom to AOI")
        return

    geom: QgsGeometry = qgsgeometry_from_geojson(json_type)
    zoom_canvas_to_geometry(geom)


def resource_file(f: str) -> str:
    """Return the absolute path to a file in the plugin's resources directory.

    Args:
        f (str): Filename relative to the resources directory.

    Returns:
        str: Absolute path to the resource file.
    """
    return safe_join(os.path.dirname(__file__), "resources", f)


def orders_download_folder():
    """Return the configured orders download folder, creating it if needed.

    Reads the folder path from QGIS settings. Falls back to a default folder
    inside the QGIS profile directory if the configured path does not exist
    and cannot be created.

    Returns:
        str: Absolute path to the orders download folder.
    """
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


def mosaic_title(mosaic: dict) -> str:
    """Generate a human-readable title for a mosaic based on
    its acquisition interval.

    Args:
        mosaic (dict): Mosaic dictionary containing acquisition
            date and interval metadata.

    Returns:
        str: Formatted date string. Examples by interval:
            - Monthly: "January 2024"
            - Quarterly: "January to March 2024"
            - Weekly or no interval: "January 01 2024"
    """
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


def date_interval_from_mosaics(mosaics: list) -> str:
    """Return a formatted date range string spanning a
    list of mosaics.

    Args:
        mosaics (list): List of mosaic dictionaries ordered
            by acquisition date.
            Must contain at least one entry with ``FIRST_ACQUIRED`` and ``LAST_ACQUIRED`` keys.

    Returns:
        str: Date range formatted as "Month Year - Month Year" e.g. "January 2024 - March 2024".
    """
    date = iso8601.parse_date(mosaics[0][FIRST_ACQUIRED])
    date2 = iso8601.parse_date(mosaics[-1][LAST_ACQUIRED])
    dates = f'{date.strftime("%B %Y")} - {date2.strftime("%B %Y")}'
    return dates


def add_mosaics_to_qgis_project(
    mosaics: list,
    name: str,
    proc: str = "default",
    ramp: str = "",
    zmin: int = 0,
    zmax: int = 22,
    add_xyz_server: bool = False,
):
    """Add a mosaic XYZ tile layer to the current QGIS project.

    Creates a WMS raster layer from the mosaic tile URL, attaches Planet-specific
    custom properties, and registers an embedded widget in the layer tree.
    Optionally saves the connection as a named XYZ tile server in QGIS settings.

    Args:
        mosaics (list): Ordered list of mosaic dictionaries. The first entry
            is used for the tile URL, datatype, and current mosaic label.
        name (str): Display name for the layer and XYZ connection.
        proc (str): Processing profile to apply (e.g. ``"rgb"``, ``"default"``).
        ramp (str): Color ramp name. Empty string applies no ramp.
        zmin (int): Minimum zoom level for the tile layer.
        zmax (int): Maximum zoom level for the tile layer.
        add_xyz_server (bool): If True, also saves the connection to QGIS's
            XYZ tile server registry under ``qgis/connections-xyz``.
    """

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
            full_uri.replace(PlanetClient.getInstance().api_key, ""),
        )


def open_link_with_browser(url: str) -> None:
    """Open a URL in the default web browser.

    Args:
        url (str): The URL to open.
    """
    QDesktopServices.openUrl(QUrl(url))


def datatype_from_mosaic_name(name: str) -> str:
    """Get the data type for a mosaic identified by name.

    Args:
        name (str): The name of the mosaic.

    Returns:
        str: The data type of the mosaic.

    Raises:
        APIError: If the Planet API request fails.
    """
    client = PlanetClient.getInstance()
    if client.client_is_setup():
        try:
            mosaic = client.get_mosaic(name)
            mosaic_datatype = mosaic[DATATYPE] if mosaic is not None else None
            return mosaic_datatype
        except APIError:
            raise
    else:
        return ""


def mosaic_name_from_url(url: str) -> str | None:
    """
    Parse the name of a mosaic from its Planet API url.

    Args:
        url (str): Planet API url for the mosaic

    Returns:
        str | None: Name of the mosaic if the search was successful,
            else returns None.
    """
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
    """Attach Planet mosaic metadata and an embedded widget to an
    existing layer.

    Parses the layer's source URL to extract the mosaic name,
    processing profile, and color ramp, then sets them as custom properties
    and registers the Planet embedded widget in the layer tree.
    Only acts on Planet tile layers that do not already have mosaic metadata
    attached.

    Args:
        layer (QgsRasterLayer): The raster layer to update.
    """
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


def is_planet_url(url: str) -> bool:
    """Check whether a URL string refers to a Planet tile layer.

    Matches both authenticated (with API key) and unauthenticated
    (with placeholder domain) Planet tile URLs.

    Args:
        url (str): URL-encoded layer URI string to check.

    Returns:
        bool: True if the URL contains exactly one Planet tile endpoint.
    """
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


def plugin_version(add_commit: bool = False) -> str:
    """Return the plugin version string from metadata.txt.

    Args:
        add_commit (bool): If True, appends the commit ID as ``"version-commit"``.

    Returns:
        str: Version string, e.g. ``"1.2.3"`` or ``"1.2.3-abc1234"``.
    """
    config = configparser.ConfigParser()
    path = os.path.join(os.path.dirname(__file__), "metadata.txt")
    config.read(path)
    version = config.get("general", "version")
    if add_commit:
        version = f"{version}-{COMMIT_ID}"
    return version


def user_agent() -> str:
    """Return the User-Agent string for Planet API requests.

    Returns:
        str: User-Agent formatted as ``"qgis-{version};planet-explorer{plugin_version}"``.
    """
    return (
        f"qgis-{Qgis.QGIS_VERSION};planet-explorer{plugin_version()}"  # noqa: E702 E231
    )


SAFE_LOCALE = re.compile(r"^[a-z]{2}(?:_[A-Z]{2})?$")


def safe_join(base_dir: str, *parts: str) -> str:
    """Join path parts under a base directory, raising on path
    traversal attempts.

    Args:
        base_dir (str): The root directory all paths must remain within.
        *parts (str): Path components to join under ``base_dir``.

    Returns:
        str: Resolved absolute path.

    Raises:
        ValueError: If the resolved path escapes ``base_dir``.
    """
    base = Path(base_dir).resolve()
    candidate = base.joinpath(*parts).resolve()

    try:
        candidate.relative_to(base)
    except ValueError:
        raise ValueError("Path traversal detected") from None

    return str(candidate)


def basename_only(name: str) -> str:
    """Extract the filename from a path, stripping any directory components.

    Args:
        name (str): File path or name.

    Returns:
        str: The bare filename with no directory components.
    """
    return Path(name).name  # strips ../../ etc.


def safe_locale(loc: str) -> str:
    """Validate and return a locale string against an allowlist pattern.

    Args:
        loc (str): Locale string to validate (e.g. ``"en_US"``).

    Returns:
        str: The validated locale string.

    Raises:
        ValueError: If the locale does not match the expected format.
    """
    if not SAFE_LOCALE.fullmatch(loc):
        raise ValueError("Invalid locale")
    return loc
