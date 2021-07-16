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
__author__ = 'Planet Federal'
__date__ = 'June 2021'
__copyright__ = '(C) 2021 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import analytics
from collections import Counter

from .planet_api import PlanetClient

ITEM_TYPE = "item_type"
ITEM_TYPES = "item_types"
NAME = "name"

# [set_segments_write_key]
# [set_sentry_dsn]

def sentry_dsn():
    return os.environ.get("SENTRY_DSN")

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
            user = PlanetClient.getInstance().user()['email']
            analytics.track(user, event, properties)
        except Exception:
            pass

item_type_names = {
        'PSScene4Band': "planetscope_scene",
        'PSScene3Band': "planetscope_scene",
        'PSOrthoTile': "planetscope_ortho",
        'REOrthoTile':  "rapideye_ortho",
        'SkySatCollect': "skysat_collect",
        'Landsat8L1G': "landsat",
        'SkySatScene': "skysat_scene",
        'REScene': "rapideye_scene",
        'Sentinel2L1C': "sentinel_scene",
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
            analytics_track("scene_search_executed",
                            {"item_type": name})

def send_analytics_for_preview(imgs):
    item_types = [img['properties'][ITEM_TYPE] for img in imgs]
    counter = Counter(item_types)
    for item_type in counter.keys():
        name = item_type_names.get(item_type)
        if name is not None:
            analytics_track("scene_preview_added_to_map",
                            {"item_type": name,
                             "scene_count": counter[item_type]})

def send_analytics_for_order(order):
    product = order["products"][0]
    name = item_type_names.get(product["item_type"])
    if name is not None:
        analytics_track(f"scene_order_placed",
                        {"count": len(product["item_ids"]),
                         "item_type": name})
        clipping = "clip" in [list(tool.keys())[0] for tool in order["tools"]]
        if clipping:
            analytics_track(f"scene_order_clipped",
                            {"scene_count": len(product["item_ids"]),
                             "item_type": name})