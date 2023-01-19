import os
import pytest
import datetime
import json

from qgis.PyQt import QtCore
from qgis.core import QgsProject, QgsVectorLayer
from qgis.utils import iface

from planet_explorer.tests.utils import qgis_debug_wait
from planet_explorer.gui.pe_range_slider import PlanetExplorerRangeSlider
from planet_explorer.gui.pe_filters import PlanetAOIFilter

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]

DATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

ITEM_TYPE_CHECKBOXES = {
    "PSScene": "chkPlanetScope",
    "PSOrthoTile": "chkPlanetScopeOrtho",
    "REScene": "chkRapidEyeScene",
    "REOrthoTile": "chkRapidEyeOrtho",
    "SkySatScene": "chkSkySatScene",
    "SkySatCollect": "chkSkySatCollect",
    "Landsat8L1G": "chkLandsat",
    "Sentinel2L1C": "chkSentinel",
}

SPECTRAL_BAND_CHECKBOXES = {"4Band": "chkNIR", "8Band": "chkYellow"}

INSTRUMENT_CHECKBOXES = {"PS2": "chkPs2", "PS2.SD": "chkPs2Sd", "PSB.SD": "chkPsbSd"}

ALLOWED_GEOMS = ["Polygon", "MultiPolygon"]
ABSOLUTE_PATH = os.path.dirname(__file__)
TEST_POLY = '{}/data/aoi_tests/test_aoi.gpkg'.format(ABSOLUTE_PATH)
TEST_MULTIPOLY = '{}/data/aoi_tests/test_multipoly.gpkg'.format(ABSOLUTE_PATH)


# def test_search_default_filter(
#     qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, sample_aoi
# ):
#     """
#     Verifies:
#         - PLQGIS-TC04
#     """
#     dock_widget = logged_in_explorer_dock_widget().daily_images_widget
#
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.keyClicks(dock_widget._aoi_filter.leAOI, sample_aoi)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
#     # just verify that at least some images are showing
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     assert dock_widget.searchResultsWidget.tree.topLevelItemCount() > 1
#     images_found = int(
#         dock_widget.searchResultsWidget.lblImageCount.text().split(" ")[0]
#     )
#     assert images_found > 1
#
#
# def test_search_date_time_filter(
#     qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi
# ):
#     """
#     Verifies:
#         - PLQGIS-TC04
#     """
#     dock_widget = logged_in_explorer_dock_widget().daily_images_widget
#
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # note for ease of automation we just use internal widget controls to set the datetime
#     filter_widget = dock_widget._daily_filters_widget
#     start_date = (datetime.datetime.today() - datetime.timedelta(days=1)).date()
#     end_date = datetime.datetime.today().date()
#
#     filter_widget.startDateEdit.setMinimumDate(start_date)
#     filter_widget.endDateEdit.setMaximumDate(end_date)
#
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # click the back button and execute the search
#     qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # make sure all items from the search are correct
#     results_tree = dock_widget.searchResultsWidget.tree
#     for index in range(results_tree.topLevelItemCount()):
#         for image in results_tree.topLevelItem(index).images():
#             assert (
#                 datetime.datetime.strptime(
#                     image["properties"]["published"], DATE_TIME_FORMAT
#                 ).date()
#                 <= end_date
#             )
#             assert (
#                 datetime.datetime.strptime(
#                     image["properties"]["published"], DATE_TIME_FORMAT
#                 ).date()
#                 >= start_date
#             )
#
#
# @pytest.mark.parametrize(
#     "item_type",
#     [
#         "Landsat8L1G",
#         "Sentinel2L1C",
#         "SkySatScene",
#         "SkySatCollect",
#         "PSScene",
#         "PSOrthoTile",
#     ],
# )
# def test_search_item_type_filter(
#     qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi, item_type
# ):
#     """
#     Verifies:
#         - PLQGIS-TC04
#     """
#     dock_widget = logged_in_explorer_dock_widget().daily_images_widget
#
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # disable all the item checkboxes
#     for name, widget in ITEM_TYPE_CHECKBOXES.items():
#         getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)
#
#     checkbox = getattr(
#         dock_widget._daily_filters_widget, ITEM_TYPE_CHECKBOXES[item_type]
#     )
#     # default position for clicking checkboxes is incorrect, we must manually supply it
#     # https://stackoverflow.com/questions/19418125/pysides-qtest-not-checking-box
#     qtbot.mouseClick(
#         checkbox, QtCore.Qt.LeftButton, pos=QtCore.QPoint(2, int(checkbox.height() / 2))
#     )
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     assert checkbox.isChecked()
#
#     # click the back button and execute the search
#     qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # make sure all items from the search are correct
#     results_tree = dock_widget.searchResultsWidget.tree
#     assert results_tree.topLevelItemCount() >= 1
#
#     for index in range(results_tree.topLevelItemCount()):
#         assert results_tree.topLevelItem(index).itemtype == item_type
#
#
# @pytest.mark.parametrize("band", ["4Band", "8Band"])
# def test_search_spectral_band_filter(
#     qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi, band
# ):
#     """
#     Verifies:
#         - PLQGIS-TC17
#     """
#     dock_widget = logged_in_explorer_dock_widget().daily_images_widget
#
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # disable all the item and spectral band checkboxes
#     for name, widget in ITEM_TYPE_CHECKBOXES.items():
#         if name == "PSScene":
#             getattr(dock_widget._daily_filters_widget, widget).setCheckState(2)
#         else:
#             getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)
#     for name, widget in SPECTRAL_BAND_CHECKBOXES.items():
#         getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)
#
#     checkbox = getattr(
#         dock_widget._daily_filters_widget, SPECTRAL_BAND_CHECKBOXES[band]
#     )
#     # default position for clicking checkboxes is incorrect, we must manually supply it
#     # https://stackoverflow.com/questions/19418125/pysides-qtest-not-checking-box
#     qtbot.mouseClick(
#         checkbox, QtCore.Qt.LeftButton, pos=QtCore.QPoint(2, int(checkbox.height() / 2))
#     )
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     assert checkbox.isChecked()
#
#     # click the back button and execute the search
#     qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # make sure all items from the search are correct
#     results_tree = dock_widget.searchResultsWidget.tree
#     assert results_tree.topLevelItemCount() >= 1
#
#     for image in results_tree.topLevelItem(0).images():
#         if band == "4Band":
#             assert "basic_analytic_4b" in image["assets"]
#         if band == "8Band":
#             assert "basic_analytic_8b" in image["assets"]
#
#
# @pytest.mark.parametrize("instrument", ["PS2", "PS2.SD", "PSB.SD"])
# def test_search_instrument_filter(
#     qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi, instrument
# ):
#     """
#     Verifies:
#         - PLQGIS-TC17
#     """
#     dock_widget = logged_in_explorer_dock_widget().daily_images_widget
#
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # disable all the item and spectral band checkboxes
#     for name, widget in ITEM_TYPE_CHECKBOXES.items():
#         if name == "PSScene":
#             getattr(dock_widget._daily_filters_widget, widget).setCheckState(2)
#         else:
#             getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)
#     for name, widget in INSTRUMENT_CHECKBOXES.items():
#         getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)
#
#     checkbox = getattr(
#         dock_widget._daily_filters_widget, INSTRUMENT_CHECKBOXES[instrument]
#     )
#     # default position for clicking checkboxes is incorrect, we must manually supply it
#     # https://stackoverflow.com/questions/19418125/pysides-qtest-not-checking-box
#     qtbot.mouseClick(
#         checkbox, QtCore.Qt.LeftButton, pos=QtCore.QPoint(2, int(checkbox.height() / 2))
#     )
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     assert checkbox.isChecked()
#
#     # click the back button and execute the search
#     qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # if no images found, just skip the test
#     # TODO: extend the date range?
#     results_tree = dock_widget.searchResultsWidget.tree
#     if results_tree.topLevelItemCount() == 0:
#         pytest.skip(f"No images found with instrument: {instrument}")
#
#     for image in results_tree.topLevelItem(0).images():
#         assert instrument == image["properties"]["instrument"]
#
#
# def test_search_item_id_filter(
#     qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi
# ):
#     """
#     Verifies:
#         - PLQGIS-TC17
#     """
#     item_id = "20220710_170008_10_2403"
#     dock_widget = logged_in_explorer_dock_widget().daily_images_widget
#
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     filter_widget = dock_widget._daily_filters_widget
#
#     qtbot.keyClicks(filter_widget.leStringIDs, item_id)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     # click the back button and execute the search
#     qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # make sure all items from the search are correct
#     results_tree = dock_widget.searchResultsWidget.tree
#     assert results_tree.topLevelItemCount() == 1
#     # make sure the item id for the returned image is correct
#     assert results_tree.topLevelItem(0).images()[0]["id"] == item_id
#
#
# @pytest.mark.parametrize(
#     "slider_key, min_, max_, data_api_name",
#     [
#         ("cloud_cover", 0.0, 20.0, "cloud_percent"),
#         ("sun_azimuth", 45.0, 200.0, "sun_azimuth"),
#         ("sun_elevation", 45.0, 75.0, "sun_elevation"),
#     ],
#     ids=["Cloud Cover", "Sun Azimuth", "Sun Elevation"],
# )
# def test_search_env_conditions_filter(
#     qtbot,
#     logged_in_explorer_dock_widget,
#     qgis_debug_enabled,
#     sample_aoi,
#     slider_key,
#     min_,
#     max_,
#     data_api_name,
# ):
#     """
#     Verifies:
#         - PLQGIS-TC17
#     """
#     dock_widget = logged_in_explorer_dock_widget().daily_images_widget
#
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.keyClicks(dock_widget._aoi_filter.leAOI, sample_aoi)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     filter_widget = dock_widget._daily_filters_widget
#
#     # get the slider we want to change
#     sliders = filter_widget.frameRangeSliders.findChildren(PlanetExplorerRangeSlider)
#     for slider in sliders:
#         if slider.filter_key == slider_key:
#             break
#
#     # for ease of automation, we don't use mouse clicks here,
#     # we just manually set the sliders to a range
#     slider.setRangeLow(min_)
#     slider.setRangeHigh(max_)
#     slider.updateLabels()
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # click the back button and execute the search
#     qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # make sure all items from the search are correct
#     results_tree = dock_widget.searchResultsWidget.tree
#     for index in range(results_tree.topLevelItemCount()):
#         for image in results_tree.topLevelItem(index).images():
#             assert image["properties"][data_api_name] <= max_
#             assert image["properties"][data_api_name] >= min_
#
#
# def test_preview_daily_imagery(
#     qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, sample_aoi
# ):
#     """
#     Verifies:
#         - PLQGIS-TC05
#     """
#     dock_widget = logged_in_explorer_dock_widget().daily_images_widget
#
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.keyClicks(dock_widget._aoi_filter.leAOI, sample_aoi)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     # grab the first result and add it to the canvas
#     results_tree = dock_widget.searchResultsWidget.tree
#     item_widget = results_tree.itemWidget(results_tree.topLevelItem(0), 0)
#     qtbot.mouseClick(item_widget.labelZoomTo, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     qtbot.mouseClick(item_widget.labelAddPreview, QtCore.Qt.LeftButton)
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#
#     layers = QgsProject.instance().mapLayers().values()
#     # two because layers AND footprints are included in the previews
#     assert len(layers) == 2
#
#
# def test_search_wrong_aoi(qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled):
#     """
#     Verifies:
#         - PLQGIS-TC04
#     """
#     dock_widget = logged_in_explorer_dock_widget().daily_images_widget
#
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.keyClicks(dock_widget._aoi_filter.leAOI, "wrong AOI")
#     qgis_debug_wait(qtbot, qgis_debug_enabled)
#     qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)


@pytest.mark.parametrize(
    "name, layer_dir, expected_coordinates",
    [
        pytest.param(
            "polygons",
            TEST_POLY,
            [
                [
                    [
                        [18.688858, -33.840948],
                        [18.634939, -33.96754],
                        [19.047537, -34.089444],
                        [19.244459, -33.681535],
                        [18.672448, -33.636993],
                        [18.290326, -33.644026],
                        [18.24344, -33.777651],
                        [18.688858, -33.840948],
                    ]
                ],
                [
                    [
                        [17.812478, -33.460602],
                        [17.721783, -33.629738],
                        [17.898272, -33.740044],
                        [18.089469, -33.521883],
                        [17.969358, -33.404224],
                        [17.812478, -33.460602],
                    ]
                ],
                [
                    [
                        [19.508736, -34.058705],
                        [19.39843, -34.191072],
                        [19.572469, -34.257255],
                        [19.648457, -34.021936],
                        [19.552859, -33.769459],
                        [19.508736, -34.058705],
                    ]
                ],
            ],
        ),
        pytest.param(
            "multipolygons",
            TEST_MULTIPOLY,
            [
                [
                    [
                        [19.854093, -32.914008],
                        [19.115666, -33.119873],
                        [19.804865, -33.36154],
                        [20.400082, -33.00799],
                        [20.042057, -32.694718],
                        [19.854093, -32.914008],
                    ]
                ],
                [
                    [
                        [18.063967, -32.824502],
                        [17.996837, -33.173577],
                        [18.390665, -33.231756],
                        [18.592054, -32.846879],
                        [18.242979, -32.694718],
                        [18.063967, -32.824502],
                    ]
                ],
                [
                    [
                        [19.795914, -33.603207],
                        [19.80039, -33.777745],
                        [20.149464, -33.840399],
                        [20.221069, -33.459997],
                        [19.921223, -33.406293],
                        [19.795914, -33.603207],
                    ]
                ],
                [
                    [
                        [18.784493, -33.204904],
                        [18.650233, -33.406293],
                        [19.053012, -33.603207],
                        [19.563198, -33.580831],
                        [19.267827, -33.272034],
                        [18.829246, -33.066169],
                        [18.784493, -33.204904],
                    ]
                ],
                [
                    [
                        [18.866631, -32.117031],
                        [18.615466, -32.368195],
                        [19.083323, -32.535639],
                        [19.309864, -32.117031],
                        [19.093172, -31.924963],
                        [18.866631, -32.117031],
                    ]
                ],
                [
                    [
                        [19.565953, -32.107181],
                        [19.462532, -32.328797],
                        [20.102757, -32.491316],
                        [20.112606, -31.979136],
                        [19.738321, -31.905264],
                        [19.565953, -32.107181],
                    ]
                ],
            ],
        ),
    ],
)
def test_aoi_from_layer(name, layer_dir, expected_coordinates):
    """Tests the filter for the AOI read from an input vector layer.
    AOI calculated from each polygon.
    """
    aoi_filter = PlanetAOIFilter()
    layer = QgsVectorLayer(layer_dir, "")

    # Determines the extent
    aoi_filter.aoi_from_layer([layer])

    extent = aoi_filter.leAOI.text()
    extent_json = json.loads(extent)
    geom_type = extent_json.get("type")
    coords = extent_json.get("coordinates")

    assert geom_type in ALLOWED_GEOMS
    assert coords == expected_coordinates


@pytest.mark.parametrize(
    "layer_dir, expected_coordinates",
    [
        pytest.param(
            TEST_POLY,
            [
                [
                    [17.721783, -34.257255],
                    [19.648457, -34.257255],
                    [19.648457, -33.404224],
                    [17.721783, -33.404224],
                    [17.721783, -34.257255],
                ]
            ],
        ),
        pytest.param(
            TEST_MULTIPOLY,
            [
                [
                    [17.996837, -33.840399],
                    [20.400082, -33.840399],
                    [20.400082, -31.905264],
                    [17.996837, -31.905264],
                    [17.996837, -33.840399],
                ]
            ],
        ),
    ],
)
def test_aoi_bb_from_layer(layer_dir, expected_coordinates):
    """Tests the filter for the AOI read from an input vector layer.
    AOI calculated from a bounding box covering all features.
    """
    aoi_filter = PlanetAOIFilter()
    layer = QgsVectorLayer(layer_dir, "")

    # Determines the extent
    aoi_filter.aoi_bb_from_layer([layer])

    extent = aoi_filter.leAOI.text()
    extent_json = json.loads(extent)
    geom_type = extent_json.get("type")
    coords = extent_json.get("coordinates")

    assert geom_type in ALLOWED_GEOMS
    assert coords == expected_coordinates


@pytest.mark.parametrize(
    "layer_dir, expected_coordinates, perform_selection",
    [
        pytest.param(
            TEST_POLY,
            [
                [
                    [18.688858, -33.840948],
                    [18.634939, -33.96754],
                    [19.047537, -34.089444],
                    [19.244459, -33.681535],
                    [18.672448, -33.636993],
                    [18.290326, -33.644026],
                    [18.24344, -33.777651],
                    [18.688858, -33.840948],
                ]
            ],
            True,
        ),
        pytest.param(
            TEST_POLY,
            [
                [
                    [
                        [18.688858, -33.840948],
                        [18.634939, -33.96754],
                        [19.047537, -34.089444],
                        [19.244459, -33.681535],
                        [18.672448, -33.636993],
                        [18.290326, -33.644026],
                        [18.24344, -33.777651],
                        [18.688858, -33.840948],
                    ]
                ],
                [
                    [
                        [17.812478, -33.460602],
                        [17.721783, -33.629738],
                        [17.898272, -33.740044],
                        [18.089469, -33.521883],
                        [17.969358, -33.404224],
                        [17.812478, -33.460602],
                    ]
                ],
                [
                    [
                        [19.508736, -34.058705],
                        [19.39843, -34.191072],
                        [19.572469, -34.257255],
                        [19.648457, -34.021936],
                        [19.552859, -33.769459],
                        [19.508736, -34.058705],
                    ]
                ],
            ],
            False,
        ),
        pytest.param(
            TEST_MULTIPOLY,
            [
                [
                    [
                        [19.854093, -32.914008],
                        [19.115666, -33.119873],
                        [19.804865, -33.36154],
                        [20.400082, -33.00799],
                        [20.042057, -32.694718],
                        [19.854093, -32.914008],
                    ]
                ],
                [
                    [
                        [18.063967, -32.824502],
                        [17.996837, -33.173577],
                        [18.390665, -33.231756],
                        [18.592054, -32.846879],
                        [18.242979, -32.694718],
                        [18.063967, -32.824502],
                    ]
                ],
            ],
            True,
        ),
        pytest.param(
            TEST_MULTIPOLY,
            [
                [
                    [
                        [19.854093, -32.914008],
                        [19.115666, -33.119873],
                        [19.804865, -33.36154],
                        [20.400082, -33.00799],
                        [20.042057, -32.694718],
                        [19.854093, -32.914008],
                    ]
                ],
                [
                    [
                        [18.063967, -32.824502],
                        [17.996837, -33.173577],
                        [18.390665, -33.231756],
                        [18.592054, -32.846879],
                        [18.242979, -32.694718],
                        [18.063967, -32.824502],
                    ]
                ],
                [
                    [
                        [19.795914, -33.603207],
                        [19.80039, -33.777745],
                        [20.149464, -33.840399],
                        [20.221069, -33.459997],
                        [19.921223, -33.406293],
                        [19.795914, -33.603207],
                    ]
                ],
                [
                    [
                        [18.784493, -33.204904],
                        [18.650233, -33.406293],
                        [19.053012, -33.603207],
                        [19.563198, -33.580831],
                        [19.267827, -33.272034],
                        [18.829246, -33.066169],
                        [18.784493, -33.204904],
                    ]
                ],
                [
                    [
                        [18.866631, -32.117031],
                        [18.615466, -32.368195],
                        [19.083323, -32.535639],
                        [19.309864, -32.117031],
                        [19.093172, -31.924963],
                        [18.866631, -32.117031],
                    ]
                ],
                [
                    [
                        [19.565953, -32.107181],
                        [19.462532, -32.328797],
                        [20.102757, -32.491316],
                        [20.112606, -31.979136],
                        [19.738321, -31.905264],
                        [19.565953, -32.107181],
                    ]
                ],
            ],
            False,
        ),
    ],
)
def test_aoi_from_multiple_polygons(layer_dir, expected_coordinates, perform_selection):
    """Tests the filter for the AOI read from no selection and a selection on a layer loaded in QGIS.
    AOI calculated from each polygon.
    """
    aoi_filter = PlanetAOIFilter()
    layer = QgsVectorLayer(layer_dir, "")
    QgsProject.instance().addMapLayer(layer)

    iface.setActiveLayer(layer)
    features = layer.getFeatures()
    feat_count = layer.featureCount()

    if perform_selection:
        # Only the selected features will be considered, otherwise all features
        selection_count = int(feat_count / 2)
        test = list(features)[:selection_count]
        for feat in test:
            feat_id = feat.id()
            layer.select(feat_id)

    # Determines the extent
    aoi_filter.aoi_from_multiple_polygons()

    extent = aoi_filter.leAOI.text()
    extent_json = json.loads(extent)
    geom_type = extent_json.get("type")
    coords = extent_json.get("coordinates")

    # Done using the layer, remove it from the project
    QgsProject.instance().removeMapLayer(layer.id())

    assert geom_type in ALLOWED_GEOMS
    assert coords == expected_coordinates


@pytest.mark.parametrize(
    "layer_dir, expected_coordinates",
    [
        pytest.param(
            TEST_POLY,
            [
                [
                    [17.721783, -34.257255],
                    [19.648457, -34.257255],
                    [19.648457, -33.404224],
                    [17.721783, -33.404224],
                    [17.721783, -34.257255],
                ]
            ],
        ),
        pytest.param(
            TEST_MULTIPOLY,
            [
                [
                    [17.996837, -33.840399],
                    [20.400082, -33.840399],
                    [20.400082, -31.905264],
                    [17.996837, -31.905264],
                    [17.996837, -33.840399],
                ]
            ],
        ),
    ],
)
def test_bb_aoi_from_multiple_polygons(layer_dir, expected_coordinates):
    """Tests the filter for the AOI read from on the bounding box of a layer loaded in QGIS.
    AOI calculated using a bounding box covering all polygons.
    """
    aoi_filter = PlanetAOIFilter()
    layer = QgsVectorLayer(layer_dir, "")
    QgsProject.instance().addMapLayer(layer)

    iface.setActiveLayer(layer)
    layer.selectAll()

    # Determines the extent
    aoi_filter.aoi_from_bound()

    extent = aoi_filter.leAOI.text()
    extent_json = json.loads(extent)
    geom_type = extent_json.get("type")
    coords = extent_json.get("coordinates")

    # Done using the layer, remove it from the project
    QgsProject.instance().removeMapLayer(layer.id())

    assert geom_type in ALLOWED_GEOMS
    assert coords == expected_coordinates
