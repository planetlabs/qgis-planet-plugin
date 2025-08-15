import unittest

from qgis.core import QgsGeometry, QgsPoint, QgsPointXY, QgsWkbTypes
from qgis.gui import QgsMapCanvas, QgsRubberBand
from qgis.utils import iface

from planet_explorer.gui.pe_filters import PlanetAOIFilter


class TestAOIFilter(unittest.TestCase):

    def test_aoi_area_size_calculation(self):
        """Tests the filter for calculating the aoi size in square kilometers"""
        test_cases = [
            (
                "small_polygon",
                [
                    QgsPointXY(QgsPoint(10, 10)),
                    QgsPointXY(QgsPoint(10, 20)),
                    QgsPointXY(QgsPoint(20, 20)),
                    QgsPointXY(QgsPoint(20, 10)),
                    QgsPointXY(QgsPoint(10, 10)),
                ],
                1239202.90,
            ),
            (
                "mid_polygon",
                [
                    QgsPointXY(QgsPoint(10, 10)),
                    QgsPointXY(QgsPoint(10, 40)),
                    QgsPointXY(QgsPoint(40, 40)),
                    QgsPointXY(QgsPoint(40, 10)),
                    QgsPointXY(QgsPoint(10, 10)),
                ],
                11152826.13,
            ),
            (
                "large_polygon",
                [
                    QgsPointXY(QgsPoint(10, 10)),
                    QgsPointXY(QgsPoint(10, 60)),
                    QgsPointXY(QgsPoint(60, 60)),
                    QgsPointXY(QgsPoint(60, 10)),
                    QgsPointXY(QgsPoint(10, 10)),
                ],
                30980072.58,
            ),
            (
                "small_polygon_zero",
                [
                    QgsPointXY(QgsPoint(0, 0)),
                    QgsPointXY(QgsPoint(0, 0)),
                    QgsPointXY(QgsPoint(0, 0)),
                    QgsPointXY(QgsPoint(0, 0)),
                    QgsPointXY(QgsPoint(0, 0)),
                ],
                0.0,
            ),
        ]
        for name, polygon, expected_size in test_cases:
            aoi_filter = PlanetAOIFilter()
            canvas = iface.mapCanvas() if iface else QgsMapCanvas()
            aoi_box = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)

            geometry = QgsGeometry.fromPolygonXY([polygon])
            aoi_box.setToGeometry(geometry)

            aoi_filter._aoi_box = aoi_box
            size = aoi_filter.calculate_aoi_area()

            self.assertIsInstance(size, float)
            self.assertAlmostEqual(
                size, expected_size, places=2, msg=f"Failed for {name}"
            )
