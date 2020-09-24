# -*- coding: utf-8 -*-
"""
***************************************************************************
    apikey_replacer.py
    ---------------------
    Date                 : December 2019
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
__date__ = 'December 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import re
import json
import urllib.parse

from qgis.core import(
    QgsProject,
    QgsDataProvider
)

from planet_explorer.planet_api import (
    PlanetClient
)

from planet_explorer.gui.pe_basemap_layer_widget import (
    PLANET_CURRENT_MOSAIC
)

from planet_explorer.pe_utils import (
    PLANET_PREVIEW_ITEM_IDS,
    tile_service_data_src_uri
)

APIKEY_PLACEHOLDER = "{api_key}"
PLANET_ROOT_URL = "planet.com"
PLANET_ROOT_URL_PLACEHOLDER = "{planet_url}"

def is_planet_layer(url):
    loggedInPattern = re.compile(r".*&url=https://tiles[0-3]?\.planet\.com/.*?api_key=.*")
    loggedOutPattern = re.compile(r".*&url=https://tiles[0-3]?\.\{planet_url\}/.*?api_key=.*")
    isloggedInPattern = loggedInPattern.search(url) is not None
    isloggedOutPattern = loggedOutPattern.search(url) is not None

    singleUrl = url.count("&url=") == 1

    return singleUrl and (isloggedOutPattern or isloggedInPattern)

def replace_apikeys():
    for layerid, layer in QgsProject.instance().mapLayers().items():
        replace_apikey_for_layer(layer)

def replace_apikey_for_layer(layer):
    source = urllib.parse.unquote(layer.source())
    if is_planet_layer(source):
        client = PlanetClient.getInstance()
        if PLANET_PREVIEW_ITEM_IDS in layer.customPropertyKeys() and client.has_api_key():
            #In case of a preview layer, we get a new url to avoid link expiration
                newsource = tile_service_data_src_uri(json.loads(
                                    layer.customProperty(PLANET_PREVIEW_ITEM_IDS)))
        else:
            tokens = source.split("api_key=")
            if len(tokens) == 1:
                tokens.append("")
            else:
                try:
                    idx = tokens[1].index("&")
                    tokens[1] = tokens[1][idx:]
                except ValueError:
                    tokens[1] = ""            
            if client.has_api_key():
                newsource = f"{tokens[0]}api_key={client.api_key()}{tokens[1]}"
                newsource = newsource.replace(PLANET_ROOT_URL_PLACEHOLDER, PLANET_ROOT_URL)
            else:
                newsource = f"{tokens[0]}api_key={tokens[1]}"
                newsource = newsource.replace(PLANET_ROOT_URL, PLANET_ROOT_URL_PLACEHOLDER)
        if newsource is not None:
            layer.setDataSource(newsource, layer.name(), layer.dataProvider().name(), 
                                QgsDataProvider.ProviderOptions())
            layer.triggerRepaint()

