import os
import sys
import logging

# noinspection PyPackageRequirements
from PIL import Image

# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    Qt,
    QSize,
    QRect,
)

# noinspection PyPackageRequirements
from PyQt5.QtGui import (
    QImage,
    qAlpha,
    QPixmap,
)

# noinspection PyPackageRequirements
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsPixmapItem,
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)


# def non_transparent_image_rect( image: QImage, min_size: QSize , center: bool ) -> QRect:
#     """
#     Culled from QgsImageOperation::nonTransparentImageRect in QGIS 3.4
#     :param image:
#     :param min_size:
#     :param center:
#     :return:
#     """
#
#     width: int = image.width()
#     height: int = image.height()
#     xmin: int = width
#     xmax: int = 0
#     ymin: int = height
#     ymax: int = 0
#
#     # Scan down till we hit something
#     for y in range(height):  # ( int y = 0; y < height; ++y )
#         found = False
#         # const QRgb *imgScanline = reinterpret_cast< const QRgb * >( image.constScanLine( y ) )
#         for x in range(width):  # ( int x = 0; x < width; ++x )
#             if qAlpha( QRgb(image.scanLine(x)) ):
#                 ymin = y
#                 ymax = y
#                 xmin = x
#                 xmax = x
#                 found = True
#                 break
#         if found:
#             break
#
#     # Scan up till we hit something
#     for ( int y = height - 1; y >= ymin; --y )
#     {
#         bool found = false
#         const QRgb *imgScanline = reinterpret_cast< const QRgb * >( image.constScanLine( y ) )
#         for ( int x = 0; x < width; ++x )
#             {
#             if ( qAlpha( imgScanline[x] ) )
#         {
#             ymax = y
#         xmin = std::min( xmin, x )
#         xmax = std::max( xmax, x )
#         found = true
#         break
#         }
#         }
#         if ( found )
#             break
#     }
#
#     # Scan left to right till we hit something, using a refined y region
#     for ( int y = ymin; y <= ymax; ++y )
#     {
#         const QRgb *imgScanline = reinterpret_cast< const QRgb * >( image.constScanLine( y ) )
#         for ( int x = 0; x < xmin; ++x )
#             {
#             if ( qAlpha( imgScanline[x] ) )
#         {
#             xmin = x
#         }
#         }
#     }
#
#     # Scan right to left till we hit something, using the refined y region
#     for ( int y = ymin; y <= ymax; ++y )
#     {
#         const QRgb *imgScanline = reinterpret_cast< const QRgb * >( image.constScanLine( y ) )
#         for ( int x = width - 1; x > xmax; --x )
#             {
#             if ( qAlpha( imgScanline[x] ) )
#         {
#             xmax = x
#         }
#         }
#     }
#
#     if ( min_size.isValid() )
#     {
#     if ( xmax - xmin < min_size.width() )  # centers image on x
#     {
#         xmin = std::max( ( xmax + xmin ) / 2 - min_size.width() / 2, 0 )
#     xmax = xmin + min_size.width()
#     }
#     if ( ymax - ymin < min_size.height() )  # centers image on y
#     {
#         ymin = std::max( ( ymax + ymin ) / 2 - min_size.height() / 2, 0 )
#     ymax = ymin + min_size.height()
#     }
#     }
#     if ( center )
#     {
#     # Recompute min and max to center image
#     const int dx = std::max( std::abs( xmax - width / 2 ), std::abs( xmin - width / 2 ) )
#     const int dy = std::max( std::abs( ymax - height / 2 ), std::abs( ymin - height / 2 ) )
#     xmin = std::max( 0, width / 2 - dx )
#     xmax = std::min( width, width / 2 + dx )
#     ymin = std::max( 0, height / 2 - dy )
#     ymax = std::min( height, height / 2 + dy )
#     }
#
#     return QRect( xmin, ymin, xmax - xmin, ymax - ymin )


def opaque_image_rect(pxm: QPixmap) -> QRect:
    """
    Culled from https://stackoverflow.com/a/3722051
    """
    gpi: QGraphicsPixmapItem = QGraphicsPixmapItem(pxm)
    return gpi.opaqueArea().boundingRect().toAlignedRect()


def trim_transparent_pixels(orig_path, trimmed_path):

    pxm: QPixmap = QPixmap(orig_path)
    opq_rect = opaque_image_rect(pxm)

    pxm_geo = pxm.copy(opq_rect)
    pxm_geo.save(trimmed_path, format='PNG', quality=0)


if __name__ == "__main__":
    size = '512'
    orig_file = f'thumb_{size}_orig.png'
    trimmed_file = f'thumb_{size}.png'

    app = QApplication(sys.argv)

    trim_transparent_pixels(orig_file, trimmed_file)

    sys.exit(app.exec_())
