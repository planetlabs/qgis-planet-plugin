# -*- coding: utf-8 -*-
"""
***************************************************************************
    p_utils.py
    ---------------------
    Date                 : June 2021
    Author               : Victor Olaya
    Copyright            : (C) 2021 Planet Inc, https://planet.com
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
__date__ = "June 2021"
__copyright__ = "(C) 2021 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import os
from collections import Counter

import analytics

from .planet_api import PlanetClient

ITEM_TYPE = "item_type"
ITEM_TYPES = "item_types"
NAME = "name"

# [set_segments_write_key]
# [set_sentry_dsn]

SCENE_ORDER_CLIPPED = "scene_order_clipped"
SCENE_SEARCH_EXECUTED = "scene_search_executed"
SCENE_PREVIEW_ADDED_TO_MAP = "scene_preview_added_to_map"
SCENE_ORDER_PLACED = "scene_order_placed"
BASEMAP_SERVICE_ADDED_TO_MAP = "basemap_service_added_to_map"
BASEMAP_SERVICE_CONNECTION_ESTABLISHED = "basemap_service_connection_established"
BASEMAP_COMPLETE_ORDER = "basemap_complete_order"
BASEMAP_PARTIAL_ORDER = "basemap_partial_order"
SAVED_SEARCH_CREATED = "saved_search_created"
ITEM_IDS_COPIED = "item_ids_copied"
API_KEY_COPIED = "api_key_copied"
USER_LOGIN = "user_login"
SAVE_CREDENTIALS = "save_credentials"
SAVED_SEARCH_ACCESSED = "saved_search_accessed"
BASEMAP_INSPECTED = "basemap_inspected"
CURL_REQUEST_COPIED = "curl_request_copied"
SKYSAT_TASK_CREATED = "skysat_task_created"


def sentry_dsn():
    return os.environ.get("SENTRY_DSN")


def sentry_integrations():
    from sentry_sdk.integrations import (
        argv,
        atexit,
        dedupe,
        logging,
        modules,
        stdlib,
        threading,
    )

    return [
        argv.ArgvIntegration,
        atexit.AtexitIntegration,
        dedupe.DedupeIntegration,
        logging.LoggingIntegration,
        modules.ModulesIntegration,
        stdlib.StdlibIntegration,
        threading.ThreadingIntegration,
    ]


def segments_write_key():
    return os.environ.get("SEGMENTS_WRITE_KEY")


def is_segments_write_key_valid():
    return segments_write_key() is not None


def is_sentry_dsn_valid():
    return sentry_dsn() is not None


def analytics_track(event, properties=None):
    properties = properties or {}
    if is_segments_write_key_valid():
        try:
            user = PlanetClient.getInstance().user()["email"]
            analytics.track(user, event, properties)
        except Exception:
            pass


item_type_names = {
    "PSScene": "planetscope_scene",
    "PSScene4Band": "planetscope_scene",
    "PSScene3Band": "planetscope_scene",
    "PSOrthoTile": "planetscope_ortho",
    "REOrthoTile": "rapideye_ortho",
    "SkySatCollect": "skysat_collect",
    "Landsat8L1G": "landsat",
    "SkySatScene": "skysat_scene",
    "REScene": "rapideye_scene",
    "Sentinel2L1C": "sentinel_scene",
}


def basemap_name_for_analytics(basemap):
    item_type = basemap[ITEM_TYPES][0]
    if item_type.startswith("PSScene"):
        if "analytic" in basemap[NAME]:
            name = "planetscope_sr"
        else:
            name = "planetscope_visual"
    else:
        name = "skysat"
    return name


def send_analytics_for_search(sources):
    for source in sources:
        name = item_type_names.get(source)
        if name is not None:
            analytics_track(SCENE_SEARCH_EXECUTED, {"item_type": name})


def send_analytics_for_preview(imgs):
    item_types = [img["properties"][ITEM_TYPE] for img in imgs]
    counter = Counter(item_types)
    for item_type in counter.keys():
        name = item_type_names.get(item_type)
        if name is not None:
            analytics_track(
                SCENE_PREVIEW_ADDED_TO_MAP,
                {"item_type": name, "scene_count": counter[item_type]},
            )


def send_analytics_for_order(order):

    print('send analytics')

    product = order["products"][0]
    name = item_type_names.get(product["item_type"])

    #print('item type: ' + product["item_type"])

    #print('name: ' + name)

    if name is not None:

        print('name is not none')

        analytics_track(
            SCENE_ORDER_PLACED,
            {"count": len(product["item_ids"]), "item_type": name},
        )
        clipping = "clip" in [list(tool.keys())[0] for tool in order["tools"]]
        if clipping:

            print('clipping')

            analytics_track(
                SCENE_ORDER_CLIPPED,
                {"scene_count": len(product["item_ids"]), "item_type": name},
            )
