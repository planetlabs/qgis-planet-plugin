# -*- coding: utf-8 -*-
"""
***************************************************************************
    render-scene-to-aoi-thumb.py
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


# Set PL_API_KEY and possibly QGIS_PREFIX_PATH in your environment

import os
import sys
import logging

from typing import (
    Optional,
    Union,
    List,
)

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QImage, QPixmap
from qgis.PyQt.QtWidgets import QLabel

from qgis.core import (
    QgsApplication,
    QgsProject,
    # QgsDataSourceUri,
    QgsRectangle,
    # QgsGeometry,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsMapSettings,
    # QgsProviderRegistry,
    QgsRasterLayer,
    QgsMapRendererParallelJob,
    # QgsMapRendererSequentialJob
)
# from qgis.testing import start_app

# from planet_explorer.planet_api.p_client import (
#     PlanetClient,
#     tile_service_url,
# )

from planet_explorer.planet_api.p_node import (
    PlanetNode,
    PlanetNodeType as NodeT,
)

from planet_explorer.pe_utils import (
    tile_service_data_src_uri,
    qgsgeometry_from_geojson,
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

AOI_GEOJSON = """\
{
  "type": "Polygon",
  "coordinates": [
    [
      [
        -122.3956726239391,
        41.21394953252933
      ],
      [
        -121.8938167065475,
        41.21394953252933
      ],
      [
        -121.8938167065475,
        41.55217106103009
      ],
      [
        -122.3956726239391,
        41.55217106103009
      ],
      [
        -122.3956726239391,
        41.21394953252933
      ]
    ]
  ]
}"""

ITEM_KEYS = [
    'PSScene4Band:20190910_183734_100a',
    'PSScene4Band:20190910_183733_100a',
    'PSScene4Band:20190910_183732_100a',
    'PSScene4Band:20190910_183731_100a',
    'PSScene4Band:20190910_183730_100a',
    'PSScene4Band:20190910_183729_100a',
    'PSScene4Band:20190910_183728_100a',
]

# qgis_app = start_app()
""":type QgsApplication"""


def render_scene_to_image(
        item_keys: List[str],
        extent_json: Union[str, dict],
        api_key: str,
        node: Optional[PlanetNode] = None,
        width: int = 512,
        height: int = 512) -> QImage:

    img = QImage()

    if not item_keys:
        log.debug('No item type_id keys list object passed')
        return img

    if not extent_json:
        log.debug('Extent is invalid')
        return img

    if node and node.node_type() != NodeT.DAILY_SCENE:
        log.debug('Item type is not a Daily Scene')
        return img

    if not api_key:
        log.debug('No API in passed')
        return img

    # p = QgsProject.instance()

    ext: QgsRectangle = \
        qgsgeometry_from_geojson(extent_json).boundingBox()

    if ext.width() > ext.height():
        height = int(ext.height() / ext.width() * height)
    elif ext.height() > ext.width():
        width = int(ext.width() / ext.height() * width)

    # noinspection PyArgumentList
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsProject.instance())

    transform_extent = transform.transformBoundingBox(ext)

    data_src_uri = tile_service_data_src_uri(item_keys, api_key)
    log.debug(f'data_src_uri:\n'
              f'{data_src_uri}')

    rlayer = QgsRasterLayer(data_src_uri, "scene_layer", "wms")

    if not rlayer.isValid():
        log.debug('Layer is not valid')
        return img

    # p.addMapLayer(rlayer)

    settings = QgsMapSettings()
    settings.setExtent(transform_extent)
    settings.setOutputSize(QSize(width, height))
    settings.setLayers([rlayer])

    job = QgsMapRendererParallelJob(settings)
    job.start()

    # This blocks...
    # It should really be a QEventLoop or QTimer that checks for finished()
    # Any intermediate image can safely be pulled from renderedImage()
    job.waitForFinished()

    return job.renderedImage()


if __name__ == "__main__":
    from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout

    apikey = os.getenv('PL_API_KEY', None)
    if not apikey:
        log.debug('No API key in environ')
        sys.exit(1)

    # print(os.environ)

    # Supply path to qgis install location
    # QgsApplication.setPrefixPath(os.environ.get('QGIS_PREFIX_PATH'), True)

    # In python3 we need to convert to a bytes object (or should
    # QgsApplication accept a QString instead of const char* ?)
    try:
        argvb = list(map(os.fsencode, sys.argv))
    except AttributeError:
        argvb = sys.argv

    # Create a reference to the QgsApplication.  Setting the
    # second argument to False disables the GUI.
    qgs = QgsApplication(argvb, True)

    # Load providers
    qgs.initQgis()

    # print(qgs.showSettings())
    # print(qgs.libraryPaths())
    # print(QgsProviderRegistry.instance().pluginList())

    # wrap in dialog
    dlg = QDialog()
    layout = QVBoxLayout(dlg)
    image_lbl = QLabel(dlg)
    layout.addWidget(image_lbl)
    # layout.setMargin(0)

    # planet_client = PlanetClient(api_key=apikey)

    image = render_scene_to_image(
        item_keys=ITEM_KEYS,
        extent_json=AOI_GEOJSON,
        api_key=apikey,
    )

    if image.isNull():
        log.debug('Rendered image is null')
        qgs.exitQgis()
        sys.exit(1)
    image_lbl.setPixmap(QPixmap.fromImage(image))

    # b1 = QPushButton("ok", dlg)

    dlg.setWindowTitle('Scene Render Test')
    dlg.exec_()

    qgs.exitQgis()

    sys.exit(0)
