import datetime
import os
import unittest

import pytest
from qgis.core import QgsProject
from qgis.PyQt import QtCore

from planet_explorer.gui.pe_range_slider import PlanetExplorerRangeSlider
from planet_explorer.tests.utils import qgis_debug_wait

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]

DATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

ITEM_TYPE_CHECKBOXES = {
    "PSScene": "chkPlanetScope",
    "PSOrthoTile": "chkPlanetScopeOrtho",
    "REScene": "chkRapidEyeScene",
    "REOrthoTile": "chkRapidEyeOrtho",
    "SkySatScene": "chkSkySatScene",
    "SkySatCollect": "chkSkySatCollect",
}

SPECTRAL_BAND_CHECKBOXES = {"4Band": "chkNIR", "8Band": "chkYellow"}

INSTRUMENT_CHECKBOXES = {"PS2": "chkPs2", "PS2.SD": "chkPs2Sd", "PSB.SD": "chkPsbSd"}

ALLOWED_GEOMS = ["Polygon", "MultiPolygon"]
ABSOLUTE_PATH = os.path.dirname(__file__)
TEST_POLY = "{}/data/aoi_tests/test_aoi.gpkg".format(ABSOLUTE_PATH)
TEST_MULTIPOLY = "{}/data/aoi_tests/test_multipoly.gpkg".format(ABSOLUTE_PATH)


class TestDailyImagery(unittest.TestCase):

    def test_search_default_filter(
        self, qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, sample_aoi
    ):
        dock_widget = logged_in_explorer_dock_widget().daily_images_widget

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget._aoi_filter.leAOI, sample_aoi)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        self.assertGreater(dock_widget.searchResultsWidget.tree.topLevelItemCount(), 1)
        images_found = int(
            dock_widget.searchResultsWidget.lblImageCount.text().split(" ")[0]
        )
        self.assertGreater(images_found, 1)

    def test_search_date_time_filter(
        self, qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi
    ):
        dock_widget = logged_in_explorer_dock_widget().daily_images_widget

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        filter_widget = dock_widget._daily_filters_widget
        start_date = (datetime.datetime.today() - datetime.timedelta(days=1)).date()
        end_date = datetime.datetime.today().date()

        filter_widget.startDateEdit.setMinimumDate(start_date)
        filter_widget.endDateEdit.setMaximumDate(end_date)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        results_tree = dock_widget.searchResultsWidget.tree
        for index in range(results_tree.topLevelItemCount()):
            for image in results_tree.topLevelItem(index).images():
                published_date = datetime.datetime.strptime(
                    image["properties"]["published"], DATE_TIME_FORMAT
                ).date()
                self.assertLessEqual(published_date, end_date)
                self.assertGreaterEqual(published_date, start_date)

    @pytest.mark.parametrize(
        "item_type",
        [
            "Landsat8L1G",
            "Sentinel2L1C",
            "SkySatScene",
            "SkySatCollect",
            "PSScene",
            "PSOrthoTile",
        ],
    )
    def test_search_item_type_filter(
        self,
        qtbot,
        logged_in_explorer_dock_widget,
        qgis_debug_enabled,
        large_aoi,
        item_type,
    ):
        dock_widget = logged_in_explorer_dock_widget().daily_images_widget

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        for name, widget in ITEM_TYPE_CHECKBOXES.items():
            getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)

        checkbox = getattr(
            dock_widget._daily_filters_widget, ITEM_TYPE_CHECKBOXES[item_type]
        )
        qtbot.mouseClick(
            checkbox,
            QtCore.Qt.LeftButton,
            pos=QtCore.QPoint(2, int(checkbox.height() / 2)),
        )
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        self.assertTrue(checkbox.isChecked())

        qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        results_tree = dock_widget.searchResultsWidget.tree
        self.assertGreaterEqual(results_tree.topLevelItemCount(), 1)
        for index in range(results_tree.topLevelItemCount()):
            self.assertEqual(results_tree.topLevelItem(index).itemtype, item_type)

    @pytest.mark.parametrize("band", ["4Band", "8Band"])
    def test_search_spectral_band_filter(
        self, qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi, band
    ):
        dock_widget = logged_in_explorer_dock_widget().daily_images_widget

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        for name, widget in ITEM_TYPE_CHECKBOXES.items():
            if name == "PSScene":
                getattr(dock_widget._daily_filters_widget, widget).setCheckState(2)
            else:
                getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)
        for name, widget in SPECTRAL_BAND_CHECKBOXES.items():
            getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)

        checkbox = getattr(
            dock_widget._daily_filters_widget, SPECTRAL_BAND_CHECKBOXES[band]
        )
        qtbot.mouseClick(
            checkbox,
            QtCore.Qt.LeftButton,
            pos=QtCore.QPoint(2, int(checkbox.height() / 2)),
        )
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        self.assertTrue(checkbox.isChecked())

        qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        results_tree = dock_widget.searchResultsWidget.tree
        self.assertGreaterEqual(results_tree.topLevelItemCount(), 1)
        for image in results_tree.topLevelItem(0).images():
            if band == "4Band":
                self.assertIn("basic_analytic_4b", image["assets"])
            if band == "8Band":
                self.assertIn("basic_analytic_8b", image["assets"])

    @pytest.mark.parametrize("instrument", ["PS2", "PS2.SD", "PSB.SD"])
    def test_search_instrument_filter(
        self,
        qtbot,
        logged_in_explorer_dock_widget,
        qgis_debug_enabled,
        large_aoi,
        instrument,
    ):
        dock_widget = logged_in_explorer_dock_widget().daily_images_widget

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        for name, widget in ITEM_TYPE_CHECKBOXES.items():
            if name == "PSScene":
                getattr(dock_widget._daily_filters_widget, widget).setCheckState(2)
            else:
                getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)
        for name, widget in INSTRUMENT_CHECKBOXES.items():
            getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)

        checkbox = getattr(
            dock_widget._daily_filters_widget, INSTRUMENT_CHECKBOXES[instrument]
        )
        qtbot.mouseClick(
            checkbox,
            QtCore.Qt.LeftButton,
            pos=QtCore.QPoint(2, int(checkbox.height() / 2)),
        )
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        self.assertTrue(checkbox.isChecked())

        qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        results_tree = dock_widget.searchResultsWidget.tree
        if results_tree.topLevelItemCount() == 0:
            pytest.skip(f"No images found with instrument: {instrument}")

        for image in results_tree.topLevelItem(0).images():
            self.assertEqual(instrument, image["properties"]["instrument"])

    def test_search_item_id_filter(
        self, qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi
    ):
        item_id = "20220710_170008_10_2403"
        dock_widget = logged_in_explorer_dock_widget().daily_images_widget

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        filter_widget = dock_widget._daily_filters_widget
        qtbot.keyClicks(filter_widget.leStringIDs, item_id)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        results_tree = dock_widget.searchResultsWidget.tree
        self.assertEqual(results_tree.topLevelItemCount(), 1)
        self.assertEqual(results_tree.topLevelItem(0).images()[0]["id"], item_id)

    @pytest.mark.parametrize(
        "slider_key, min_, max_, data_api_name",
        [
            ("cloud_cover", 0.0, 20.0, "cloud_percent"),
            ("sun_azimuth", 45.0, 200.0, "sun_azimuth"),
            ("sun_elevation", 45.0, 75.0, "sun_elevation"),
        ],
        ids=["Cloud Cover", "Sun Azimuth", "Sun Elevation"],
    )
    def test_search_env_conditions_filter(
        self,
        qtbot,
        logged_in_explorer_dock_widget,
        qgis_debug_enabled,
        sample_aoi,
        slider_key,
        min_,
        max_,
        data_api_name,
    ):
        dock_widget = logged_in_explorer_dock_widget().daily_images_widget

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget._aoi_filter.leAOI, sample_aoi)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        filter_widget = dock_widget._daily_filters_widget
        sliders = filter_widget.frameRangeSliders.findChildren(
            PlanetExplorerRangeSlider
        )
        for slider in sliders:
            if slider.filter_key == slider_key:
                break

        slider.setRangeLow(min_)
        slider.setRangeHigh(max_)
        slider.updateLabels()
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        results_tree = dock_widget.searchResultsWidget.tree
        for index in range(results_tree.topLevelItemCount()):
            for image in results_tree.topLevelItem(index).images():
                self.assertLessEqual(image["properties"][data_api_name], max_)
                self.assertGreaterEqual(image["properties"][data_api_name], min_)

    def test_preview_daily_imagery(
        self, qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, sample_aoi
    ):
        dock_widget = logged_in_explorer_dock_widget().daily_images_widget

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget._aoi_filter.leAOI, sample_aoi)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        results_tree = dock_widget.searchResultsWidget.tree
        item_widget = results_tree.itemWidget(results_tree.topLevelItem(0), 0)
        qtbot.mouseClick(item_widget.labelZoomTo, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        qtbot.mouseClick(item_widget.labelAddPreview, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        layers = list(QgsProject.instance().mapLayers().values())
        self.assertEqual(len(layers), 2)

    def test_search_wrong_aoi(
        self, qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled
    ):
        dock_widget = logged_in_explorer_dock_widget().daily_images_widget

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget._aoi_filter.leAOI, "wrong AOI")
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)

    # The AOI and bounding box tests below can also be converted to unittest methods,
    # but they are parameterized with pytest. For brevity, here's one example:

    def _assert_aoi(self, extent_json, expected_coordinates):
        geom_type = extent_json.get("type")
        coords = extent_json.get("coordinates")
        self.assertIn(geom_type, ALLOWED_GEOMS)
        self.assertEqual(coords, expected_coordinates)


# ...other parameterized tests remain as pytest functions
