import pytest

from qgis.core import QgsGeometry, QgsPoint, QgsPointXY, QgsWkbTypes
from qgis.gui import QgsRubberBand
from qgis.utils import iface
from qgis.PyQt import QtCore

from planet_explorer.gui.pe_filters import PlanetAOIFilter


@pytest.mark.parametrize(
    "name, polygon, expected_size",
    [
        pytest.param(
            "small_polygon",
            [
                QgsPointXY(QgsPoint(10, 10)),
                QgsPointXY(QgsPoint(10, 20)),
                QgsPointXY(QgsPoint(20, 20)),
                QgsPointXY(QgsPoint(20, 10)),
                QgsPointXY(QgsPoint(10, 10))
            ],
            1239202.90,
            id="area_of_interest_with_small_size",
        ),
        pytest.param(
            "mid_polygon",
            [
                QgsPointXY(QgsPoint(10, 10)),
                QgsPointXY(QgsPoint(10, 40)),
                QgsPointXY(QgsPoint(40, 40)),
                QgsPointXY(QgsPoint(40, 10)),
                QgsPointXY(QgsPoint(10, 10))
            ],
            11152826.13,
            id="area_of_interest_with_medium_size",
        ),
        pytest.param(
            "large_polygon",
            [
                QgsPointXY(QgsPoint(10, 10)),
                QgsPointXY(QgsPoint(10, 60)),
                QgsPointXY(QgsPoint(60, 60)),
                QgsPointXY(QgsPoint(60, 10)),
                QgsPointXY(QgsPoint(10, 10))
            ],
            30980072.58,
            id="area_of_interest_with_large_size",
        ),
        pytest.param(
            "small_polygon",
            [
                QgsPointXY(QgsPoint(0, 0)),
                QgsPointXY(QgsPoint(0, 0)),
                QgsPointXY(QgsPoint(0, 0)),
                QgsPointXY(QgsPoint(0, 0)),
                QgsPointXY(QgsPoint(0, 0))
            ],
            0.0,
            id="area_of_interest_with_zero_size",
        ),
    ],
)
def test_aoi_area_size_calculation(name, polygon, expected_size):
    """Tests the filter for calculating the aoi size in square kilometers
    """
    aoi_filter = PlanetAOIFilter()
    aoi_box = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)

    geometry = QgsGeometry.fromPolygonXY([polygon])
    aoi_box.setToGeometry(geometry)

    aoi_filter._aoi_box = aoi_box
    size = aoi_filter.calculate_aoi_area()

    assert size == expected_size
