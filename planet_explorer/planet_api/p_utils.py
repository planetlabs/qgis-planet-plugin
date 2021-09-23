# -*- coding: utf-8 -*-
"""
***************************************************************************
    p_utils.py
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
__author__ = "Planet Federal"
__date__ = "September 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import json
import logging
import os
from typing import Optional, Union

from planet.api.utils import geometry_from_json

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)


def json_str_or_obj_to_obj(json_type: Union[str, dict]) -> Optional[dict]:
    """
    :param json_type: JSON as string or `json` object
    :type json_type: str | dict
    :rtype: dict | None
    """
    json_obj = None
    if isinstance(json_type, (str, bytes, bytearray)):
        try:
            json_obj = json.loads(json_type)
        except TypeError:
            json_obj = None
            log.debug("JSON input type invalid")
        except ValueError:
            json_obj = None
            log.debug("JSON string invalid")
    elif isinstance(json_type, dict):
        json_obj = json_type

    if not json_obj:
        log.debug("JSON Python object invalid")
        return None

    return json_obj


def geometry_from_json_str_or_obj(json_type: Union[str, dict]) -> Optional[dict]:
    """
    :param json_type: GeoJSON feature, feature collection or geometry as
    string or `json` object
    :type json_type: str | dict
    :rtype: dict | None
    """
    json_obj = json_str_or_obj_to_obj(json_type)

    if json_obj is None:
        return None

    # Strip outer Feature or FeatureCollection
    json_geom = geometry_from_json(json_obj)

    if not json_geom:
        log.debug("GeoJSON geometry invalid")

    return json_geom


def geometry_from_request(request: Union[str, dict]) -> Optional[dict]:
    """
    :param request: JSON request as string or `json` object
    :type request: str | dict
    :rtype: dict | None
    """
    req_obj = json_str_or_obj_to_obj(request)
    if req_obj is None:
        return None

    config = []
    geom = None
    fltr = req_obj.get("filter", None)
    if fltr:
        config = fltr.get("config", None)

    for conf in config:
        if isinstance(conf, dict) and conf.get("field_name", None) == "geometry":
            geom = conf.get("config", None)
            break

    return geom
