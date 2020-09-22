# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_thumbnails.py
    ---------------------
    Date                 : September 2019
    Author               : Planet Federal
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


from qgis.PyQt.QtCore import (
    pyqtSignal,
    pyqtSlot,
    QObject,
    QSize,
    QThread,
    Qt
)

from qgis.PyQt.QtGui import (
    QImage,
    QPixmap,
    QPainter
)

from qgis.core import (
    QgsProject,
    QgsRectangle,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsMapSettings,
    QgsRasterLayer,
)

from ..planet_api.p_client import (
    PlanetClient
)


from ..pe_utils import (
    tile_service_data_src_uri,    
    qgsgeometry_from_geojson
)


def createCompoundThumbnail(_bboxes, thumbnails):
    bboxes = []
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem('EPSG:4326'),
        QgsCoordinateReferenceSystem('EPSG:3857'),
        QgsProject.instance())
    for box in _bboxes:
        rect4326 = qgsgeometry_from_geojson(box).boundingBox()
        rect = transform.transformBoundingBox(rect4326)
        bboxes.append([rect.xMinimum(), rect.yMinimum(),
                      rect.xMaximum(), rect.yMaximum()])
    globalbox = (min([v[0] for v in bboxes]),
                min([v[1] for v in bboxes]),
                max([v[2] for v in bboxes]),
                max([v[3] for v in bboxes])
                )
    SIZE = 256
    globalwidth = globalbox[2] - globalbox[0]
    globalheight = globalbox[3] - globalbox[1]
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    for i, thumbnail in enumerate(thumbnails):         
        box = bboxes[i]
        width = box[2] - box[0]
        height = box[3] - box[1]        
        if width > height:
            offsety = (width - height) / 2 
            offsetx = 0
        else:
            offsetx = (height - width) / 2 
            offsety = 0                       
        x = int( (box[0] - offsetx - globalbox[0]) / globalwidth * SIZE)
        y = int( (globalbox[3] - box[3] - offsety) / globalheight * SIZE)
        outputwidth = int( (width + 2 * offsetx)/ globalwidth * SIZE)
        outputheight = int( (height + 2 * offsety) / globalheight * SIZE)
        painter.drawPixmap(x, y, outputwidth, outputheight, thumbnail)
    painter.end()
    return pixmap
