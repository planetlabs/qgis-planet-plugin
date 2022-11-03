import pytest

from qgis.core import QgsGeometry, QgsPoint, QgsRubberBand, QgsWkbTypes
from qgis.utils import iface
from qgis.PyQt import QtCore

from planet_explorer.gui.pe_filters import PlanetAOIFilter


def test_aoi_area_size_calculation(
    qtbot,
):
    """
    """
    aoi_filter = PlanetAOIFilter()
    aoi_box = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
    points = [QgsPoint(60, 60), QgsPoint(60, 80), QgsPoint(80, 80), QgsPoint(80, 60), QgsPoint(60, 60)]
    geometry = QgsGeometry.fromPolygon([points])
    aoi_box.setGeometry(geometry)

    aoi_filter._aoi_box = aoi_box
    size = aoi_filter.calculate_aoi_area()

    assert size == 1000
