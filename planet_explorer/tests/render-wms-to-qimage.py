# -*- coding: utf-8 -*-
"""
***************************************************************************
    render-wms-to-qimage.py
    ---------------------
    Date                 : August 2019
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
__date__ = 'August 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'


# Set PL_API_KEY and possibly QGIS_PREFIX_PATH in your environment

import os
import sys

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QImage, QPixmap
from qgis.PyQt.QtWidgets import QLabel

from qgis.core import (
    QgsApplication,
    # QgsProject,
    QgsDataSourceUri,
    QgsRectangle,
    QgsMapSettings,
    # QgsProviderRegistry,
    QgsRasterLayer,
    QgsMapRendererParallelJob,
    # QgsMapRendererSequentialJob
)
# from qgis.testing import start_app


XYZ_URL = 'https://tiles0.planet.com/data/v1/layers/' \
          '2_hdz40JpoETvRNZX2ZL6ngZ9cltlXmYA-gjpA/{z}/{x}/{y}'

# example  = 'https://tiles{0-3}.planet.com/basemaps/v1/planet-tiles/{mosaic_name}/gmap/{z}/{x}/{y}.png?api_key={api-key}'

# XYZ_URL = f'https://tiles.planet.com/basemaps/v1/planet-tiles/' \
#           f'/global_monthly_2016_01_mosaic/gmap/' \
#           f'{{z}}/{{x}}/{{y}}.png?' \
#           f'api_key={os.environ.get("PL_API_KEY")}'

XYZ_URL = f'https://tiles.planet.com/basemaps/v1/planet-tiles/' \
        f'global_quarterly_2018q3_mosaic/gmap/{{z}}/{{x}}/{{y}}.png?' \
        f'api_key={os.environ.get("PL_API_KEY")}'

WMS_URL = f'https://tiles0.planet.com/data/v1/layers/wmts/' \
    f'JI7gTtruuxI9gsnBRbIjJZJ0BS4hXpRgGgBEig?' \
    f'api_key={os.environ.get("PL_API_KEY")}'
EXTENT = (-13769297.91963258385658264,
          4600825.79851222783327103,
          -13648442.77041305601596832,
          4676839.34374015405774117)

# qgis_app = start_app()
""":type QgsApplication"""


# def thumbnail_image(item_type, item_id):
#     dispatcher = RequestsDispatcher(4)
#     client_auth = os.environ.get("PL_API_KEY")
#
#     url = f'https://tiles.planet.com/data/v1/item-types/{item_type}/' \
#           f'items/{item_id}/thumb?api_key={client_auth}' \
#
#     result = dispatcher.dispatch_request(method="GET", url=url)
#     image_data = result.content
#
#     qp = QPixmap()
#     qp.loadFromData(image_data)
#
#     return QImage(qp)

def build_basemap_uri():
    for year in range(2016, 2020):
        for x in range(1, 12):
            if year == 2019 and x <= 8:
                month = format(x, '02')
                monthlyMosaic = f'global_monthly_{year}_{month}_mosaic'
                url = f'https://tiles.planet.com/basemaps/v1/planet-tiles/' \
                      f'{monthlyMosaic}/gmap/' \
                      f'{{z}}/{{x}}/{{y}}.png?' \
                      # f'api_key={os.environ.get("PL_API_KEY")}'
                print(url);

def render_wms_to_image(xyz=True, extent=EXTENT, width=64, height=60):
    """
    :type xyz: bool
    :type extent: tuple
    :type width: int
    :type height: int
    :rtype: QImage
    """
    # p = QgsProject.instance()
    # p = QgsProject()
    uri = QgsDataSourceUri()
    if xyz:
        uri.setParam('type', 'xyz')
        uri.setParam('crs', 'EPSG:3857')
        uri.setParam('format', '')
        # uri.setParam('zmin', '0')
        # uri.setParam('zmax', '18')
        uri.setParam('url', XYZ_URL)
    else:
        uri.setParam('tileMatrixSet', 'GoogleMapsCompatible23')
        uri.setParam('crs', 'EPSG:3857')
        uri.setParam('format', 'image/png')
        uri.setParam('styles', '')
        uri.setParam('layers', 'Combined scene layer')
        uri.setParam('url', WMS_URL)

    # Important to do this conversion, else WMS provider will double encode;
    #   instead of just `str(uri.encodedUri())`, which outputs "b'uri'"
    # This coerces QByteArray -> str ... assuming UTF-8 is valid.
    final_uri = bytes(uri.encodedUri()).decode("utf-8")
    layer = QgsRasterLayer(final_uri, "scene_layer", "wms")

    if not layer.isValid():
        print('Layer is not valid')
        return QImage()
    # p.addMapLayer(layer)

    settings = QgsMapSettings()
    settings.setExtent(QgsRectangle(*extent))
    settings.setOutputSize(QSize(width, height))
    settings.setLayers([layer])

    job = QgsMapRendererParallelJob(settings)
    job.start()

    # This blocks...
    # It should really be a QEventLoop or QTimer that checks for finished()
    # Any intermediate image can safely be pulled from renderedImage()
    job.waitForFinished()

    return job.renderedImage()


if __name__ == "__main__":
    from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QStyleFactory

    # print(os.environ)

    # Supply path to qgis install location
    # QgsApplication.setPrefixPath(os.environ.get('QGIS_PREFIX_PATH'), True)

    # In python3 we need to convert to a bytes object (or should
    # QgsApplication accept a QString instead of const char* ?)

    build_basemap_uri()

    try:
        argvb = list(map(os.fsencode, sys.argv))
    except AttributeError:
        argvb = sys.argv

    # Create a reference to the QgsApplication.  Setting the
    # second argument to False disables the GUI.
    qgs = QgsApplication(argvb, True)

    qgs.setStyle(QStyleFactory.create("Fusion"))

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

    # First WMS, with tileset
    image = render_wms_to_image(xyz=False)
    if image.isNull():
        qgs.exitQgis()
        sys.exit(1)
    image_lbl.setPixmap(QPixmap.fromImage(image))

    dlg.setWindowTitle('WMS Scene Render Test')
    dlg.exec_()

    # Then XYZ
    image = render_wms_to_image(xyz=True)

    # image = thumbnail_image(item_type="PSScene4Band", item_id="20160831_143848_0c79")
    if image.isNull():
        qgs.exitQgis()
        sys.exit(1)
    image_lbl.setPixmap(QPixmap.fromImage(image))

    # b1 = QPushButton("ok", dlg)

    dlg.setWindowTitle('XYZ Scene Render Test')
    dlg.exec_()

    qgs.exitQgis()
