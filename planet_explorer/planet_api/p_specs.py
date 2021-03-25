# -*- coding: utf-8 -*-
"""
***************************************************************************
    p_specs.py
    ---------------------
    Date                 : September 2019
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
__date__ = 'September 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import logging
import re

# from typing import (
#     Optional,
#     Union,
#     List,
# )

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

ITEM_ASSET_DL_REGEX = re.compile(r'^assets\.(.*):download$')

ITEM_SHARED_PROPERTIES: dict = {
    'item_type': 'str',
    'acquired': 'str',
    'published': 'str',
    'updated': 'str',
    'satellite_id': 'str',
}

THUMB_GEOREF_FIELDS_IMAGE = [
    'pixel_resolution',
    'rows',
    'columns',
    'origin_x',
    'origin_y',
]

ITEM_TYPE_SPECS = {
    'PSScene': {
        'name': 'PlanetScope',
        'thumb_georef_fields': THUMB_GEOREF_FIELDS_IMAGE,
        'properties': {
            'acquired': 'datetime',
            'anomalous_pixels': 'float',
            'clear_confidence_percent': 'float',
            'clear_percent': 'float',
            'cloud_cover': 'float',
            'cloud_percent': 'float',
            'columns': 'int',
            'epsg_code': 'int',
            'ground_control': 'bool',
            'gsd': 'float',
            'heavy_haze_percent': 'float',
            'instrument': 'str',
            'light_haze_percent': 'float',
            'origin_x': 'float',
            'origin_y': 'float',
            'pixel_resolution': 'float',
            'provider': 'str',
            'published': 'datetime',
            'quality_category': 'str',
            'rows': 'int',
            'satellite_id': 'str',
            'shadow_percent': 'float',
            'snow_ice_percent': 'float',
            'strip_id': 'str',
            'sun_azimuth': 'float',
            'sun_elevation': 'float',
            'updated': 'datetime',
            'view_angle': 'float',
            'visible_confidence_percent': 'float',
            'visible_percent': 'float',
        },
        'bands': {
            '1': 'Red',
            '2': 'Green',
            '3': 'Blue',
            '4': 'Near-infrared',
        },
    },
    'REOrthoTile': {
        'name': 'RapidEye Ortho Tile',
        'thumb_georef_fields': THUMB_GEOREF_FIELDS_IMAGE,
        'properties': {
            'acquired': 'datetime',
            'anomalous_pixels': 'float',
            'black_fill': 'float',
            'catalog_id': 'str',
            'cloud_cover': 'float',
            'columns': 'int',
            'epsg_code': 'int',
            'grid_cell': 'str',
            'ground_control': 'bool',
            'gsd': 'float',
            'item_type': 'str',
            'origin_x': 'float',
            'origin_y': 'float',
            'pixel_resolution': 'float',
            'provider': 'str',
            'published': 'datetime',
            'rows': 'int',
            'satellite_id': 'str',
            'strip_id': 'str',
            'sun_azimuth': 'float',
            'sun_elevation': 'float',
            'updated': 'datetime',
            'usable_data': 'float',
            'view_angle': 'float',
        },
        'bands': {
            '1': 'Red',
            '2': 'Green',
            '3': 'Blue',
            '4': 'Red edge (analytic products only)',
            '5': 'Near-infrared (analytic products only)',
        },
    },
    'SkySatCollect': {
        'name': 'SkySat Collect',
        'thumb_georef_fields': None,
        'properties': {
            'acquired': 'datetime',
            'clear_confidence_percent': 'float',
            'clear_percent': 'float',
            'cloud_cover': 'float',
            'cloud_percent': 'float',
            'ground_control_ratio': 'float',
            'gsd': 'float',
            'heavy_haze_percent': 'float',
            'item_type': 'str',
            'light_haze_percent': 'float',
            'provider': 'str',
            'published': 'datetime',
            'quality_category': 'str',
            'satellite_azimuth': 'float',
            'satellite_id': 'str',
            'shadow_percent': 'float',
            'snow_ice_percent': 'float',
            'strip_id': 'str',
            'sun_azimuth': 'float',
            'sun_elevation': 'float',
            'updated': 'datetime',
            'view_angle': 'float',
            'visible_confidence_percent': 'float',
            'visible_percent': 'float'
        },
        'bands': {
            '1': 'Red',
            '2': 'Green',
            '3': 'Blue',
            '4': 'Near-infrared (analytic products only)',
            '5': 'Panchromatic',
        },
    },
    'Landsat8L1G': {
        'name': 'Landsat 8 Scene',
        'thumb_georef_fields': THUMB_GEOREF_FIELDS_IMAGE,
        'properties': {
            'acquired': 'datetime',
            'anomalous_pixels': 'float',
            'cloud_cover': 'float',
            'collection': 'str',
            'columns': 'int',
            'data_type': 'str',
            'epsg_code': 'int',
            'gsd': 'float',
            'instrument': 'str',
            'item_type': 'str',
            'origin_x': 'float',
            'origin_y': 'float',
            'pixel_resolution': 'float',
            'processed': 'datetime',
            'product_id': 'str',
            'provider': 'str',
            'published': 'datetime',
            'quality_category': 'str',
            'rows': 'int',
            'satellite_id': 'str',
            'sun_azimuth': 'float',
            'sun_elevation': 'float',
            'updated': 'datetime',
            'usable_data': 'float',
            'view_angle': 'float',
            'wrs_path': 'int',
            'wrs_row': 'int',
        },
        'bands': {
            '1': 'Coastal/aerosol',
            '2': 'Blue',
            '3': 'Green',
            '4': 'Red',
            '5': 'Near-infrared',
            '6': 'Short-wave infrared 1',
            '7': 'Short-wave infrared 2',
            '8': 'Panchromatic',
            '9': 'Cirrus',
            '10': 'Thermal infrared 1',
            '11': 'Thermal infrared 2',
        },
    },
    'SkySatScene': {
        'name': 'SkySat Scene',
        'thumb_georef_fields': None,
        'properties': {
            'acquired': 'datetime',
            'camera_id': 'str',
            'clear_confidence_percent': 'float',
            'clear_percent': 'float',
            'cloud_cover': 'float',
            'cloud_percent': 'float',
            'ground_control': 'bool',
            'gsd': 'float',
            'heavy_haze_percent': 'float',
            'item_type': 'str',
            'light_haze_percent': 'float',
            'provider': 'str',
            'published': 'datetime',
            'quality_category': 'str',
            'satellite_azimuth': 'float',
            'satellite_id': 'str',
            'shadow_percent': 'float',
            'snow_ice_percent': 'float',
            'strip_id': 'str',
            'sun_azimuth': 'float',
            'sun_elevation': 'float',
            'updated': 'datetime',
            'view_angle': 'float',
            'visible_confidence_percent': 'float',
            'visible_percent': 'float'
        },
        'bands': {
            '1': 'Red',
            '2': 'Green',
            '3': 'Blue',
            '4': 'Near-infrared (analytic products only)',
            '5': 'Panchromatic',
        },
    },
    'REScene': {
        'name': 'RapidEye Basic Scene',
        'thumb_georef_fields': None,
        'properties': {
            'acquired': 'datetime',
            'anomalous_pixels': 'float',
            'black_fill': 'float',
            'catalog_id': 'str',
            'cloud_cover': 'float',
            'columns': 15378,
            'gsd': 'float',
            'item_type': 'str',
            'provider': 'str',
            'published': 'datetime',
            'rows': 11819,
            'satellite_id': 'str',
            'strip_id': 'str',
            'sun_azimuth': 'float',
            'sun_elevation': 'float',
            'updated': 'datetime',
            'usable_data': 'float',
            'view_angle': 'float'
        },
        'bands': {
            '1': 'Red',
            '2': 'Green',
            '3': 'Blue',
            '4': 'Red edge (analytic products only)',
            '5': 'Near-infrared (analytic products only)',
        },
    },
    'Sentinel2L1C': {
        'name': 'Sentinel-2 Tile',
        'thumb_georef_fields': THUMB_GEOREF_FIELDS_IMAGE,
        'properties': {
            'abs_orbit_number': 'int',
            'acquired': 'datetime',
            'anomalous_pixels': 'float',
            'black_fill': 'float',
            'cloud_cover': 'float',
            'columns': 'int',
            'data_type': 'str',
            'datatake_id': 'str',
            'epsg_code': 'int',
            'granule_id': 'str',
            'gsd': 'float',
            'instrument': 'str',
            'item_type': 'str',
            'mgrs_grid_id': 'str',
            'origin_x': 'float',
            'origin_y': 'float',
            'pixel_resolution': 'float',
            'product_generation_time': 'int',
            'product_id': 'str',
            'provider': 'str',
            'published': 'str',
            'quality_category': 'str',
            'rel_orbit_number': 'int',
            'rows': 'int',
            's2_processor_version': 'str',
            'satellite_id': 'str',
            'sun_azimuth': 'float',
            'sun_elevation': 'float',
            'updated': 'datetime',
            'usable_data': 'float',
            'view_angle': 'float',
        },
        'bands': {
            '1': 'Coastal/aerosol',
            '2': 'Blue',
            '3': 'Green',
            '4': 'Red',
            '5': 'Red-edge 1',
            '6': 'Red-edge 2',
            '7': 'Red-edge 3',
            '8': 'Near-infrared',
            '8a': 'Narrow near-infrared',
            '9': 'Water vapor',
            '10': 'Cirrus',
            '11': 'Short-wave infrared 1',
            '12': 'Short-wave infrared 2',
        }
    },
    'PSOrthoTile': {
        'name': 'PlanetScope Ortho Tile',
        'thumb_georef_fields': THUMB_GEOREF_FIELDS_IMAGE,
        'properties': {
            'acquired': 'datetime',
            'anomalous_pixels': 'float',
            'black_fill': 'float',
            'clear_confidence_percent': 'float',
            'clear_percent': 'float',
            'cloud_cover': 'float',
            'cloud_percent': 'float',
            'columns': 'int',
            'epsg_code': 'int',
            'grid_cell': 'str',
            'ground_control': 'bool',
            'gsd': 'float',
            'heavy_haze_percent': 'float',
            'instrument': 'str',
            'item_type': 'str',
            'light_haze_percent': 'float',
            'origin_x': 'float',
            'origin_y': 'float',
            'pixel_resolution': 'float',
            'provider': 'str',
            'published': 'datetime',
            'quality_category': 'str',
            'rows': 'int',
            'satellite_id': 'str',
            'shadow_percent': 'float',
            'snow_ice_percent': 'float',
            'strip_id': 'str',
            'sun_azimuth': 'float',
            'sun_elevation': 'float',
            'updated': 'datetime',
            'usable_data': 'float',
            'view_angle': 'float',
            'visible_confidence_percent': 'float',
            'visible_percent': 'float'
        },
        'bands': {
            '1': 'Red',
            '2': 'Green',
            '3': 'Blue',
            '4': 'Near-infrared (analytic products only)',
        },
    },
}

RESOURCE_MOSAIC_SERIES = 'mosaic_series'
RESOURCE_SINGLE_MOSAICS = 'single_mosaics'
RESOURCE_DAILY = 'daily'

# Order dictates n-rows x 2-column layout
DAILY_ITEM_TYPES = [(k, v['name']) for k, v in ITEM_TYPE_SPECS.items()]

DAILY_ITEM_TYPES_DICT = dict(DAILY_ITEM_TYPES)

MOSAIC_ITEM_TYPES = [
    ('basemap', 'Basemap'),
    ('weekly', 'Weekly Mosaic'),
    ('monthly', '1-Month Mosaic'),
    ('quarterly', '3-Month Mosaic'),
    ('seasonal', 'Seasonal Mosaic'),
]
MOSAIC_ITEM_TYPES_DICT = dict(MOSAIC_ITEM_TYPES)

MOSAIC_PRODUCT_TYPES = {
    'basemap': 'Basemap',
    'timelapse': 'Time-lapse',
}

MOSAIC_SERIES_PRODUCT_TYPES = {
    'basemap': 'Basemap',
    'timelapse': 'Time-lapse',
    'l3m': 'RapidEye Level 3M',
}
