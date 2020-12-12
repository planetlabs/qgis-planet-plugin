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

import json

from qgis.core import(
    QgsProject,
    QgsDataProvider
)

from planet_explorer.planet_api import (
    PlanetClient
)

from planet_explorer.pe_utils import (
    PLANET_PREVIEW_ITEM_IDS,
    tile_service_data_src_uri,
)

def replace_apikeys():
    for layerid, layer in QgsProject.instance().mapLayers().items():
        replace_apikey_for_layer(layer)


def replace_apikey_for_layer(layer):
    client = PlanetClient.getInstance()
    if PLANET_PREVIEW_ITEM_IDS in layer.customPropertyKeys() :
        if client.has_api_key():        
            newsource = tile_service_data_src_uri(json.loads(
                                layer.customProperty(PLANET_PREVIEW_ITEM_IDS)))
        else:
            newsource = ""
        layer.setDataSource(newsource, layer.name(), layer.dataProvider().name(),
                            QgsDataProvider.ProviderOptions())
        layer.triggerRepaint()