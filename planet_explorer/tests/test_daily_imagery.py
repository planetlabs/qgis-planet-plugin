import pytest

from qgis.PyQt import QtCore
from qgis.core import QgsProject

from planet_explorer.tests.utils import qgis_debug_wait
from planet_explorer.gui.pe_range_slider import PlanetExplorerRangeSlider

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]

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


def test_search_default_filter(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, sample_aoi
):
    """
    Verifies:
        - PLQGIS-TC04
    """
    dock_widget = logged_in_explorer_dock_widget().daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, sample_aoi)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
    # just verify that at least some images are showing
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    assert dock_widget.searchResultsWidget.tree.topLevelItemCount() > 1
    images_found = int(
        dock_widget.searchResultsWidget.lblImageCount.text().split(" ")[0]
    )
    assert images_found > 1


def test_preview_daily_imagery(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, sample_aoi
):
    """
    Verifies:
        - PLQGIS-TC05
    """
    dock_widget = logged_in_explorer_dock_widget().daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, sample_aoi)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # grab the first result and add it to the canvas
    results_tree = dock_widget.searchResultsWidget.tree
    item_widget = results_tree.itemWidget(results_tree.topLevelItem(0), 0)
    qtbot.mouseClick(item_widget.labelZoomTo, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    qtbot.mouseClick(item_widget.labelAddPreview, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    layers = QgsProject.instance().mapLayers().values()
    # two because layers AND footprints are included in the previews
    assert len(layers) == 2


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
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi, item_type
):
    """
    Verifies:
        - PLQGIS-TC04
    """
    dock_widget = logged_in_explorer_dock_widget().daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # disable all the item checkboxes
    for name, widget in ITEM_TYPE_CHECKBOXES.items():
        getattr(dock_widget._daily_filters_widget, widget).setCheckState(0)

    checkbox = getattr(
        dock_widget._daily_filters_widget, ITEM_TYPE_CHECKBOXES[item_type]
    )
    # default position for clicking checkboxes is incorrect, we must manually supply it
    # https://stackoverflow.com/questions/19418125/pysides-qtest-not-checking-box
    qtbot.mouseClick(
        checkbox, QtCore.Qt.LeftButton, pos=QtCore.QPoint(2, int(checkbox.height() / 2))
    )
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    assert checkbox.isChecked()

    # click the back button and execute the search
    qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # make sure all items from the search are correct
    results_tree = dock_widget.searchResultsWidget.tree
    assert results_tree.topLevelItemCount() >= 1

    for index in range(results_tree.topLevelItemCount()):
        assert results_tree.topLevelItem(index).itemtype == item_type


@pytest.mark.parametrize("band", ["4Band", "8Band"])
def test_search_spectral_band_filter(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi, band
):
    """
    Verifies:
        - PLQGIS-TC17
    """
    dock_widget = logged_in_explorer_dock_widget().daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # disable all the item and spectral band checkboxes
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
    # default position for clicking checkboxes is incorrect, we must manually supply it
    # https://stackoverflow.com/questions/19418125/pysides-qtest-not-checking-box
    qtbot.mouseClick(
        checkbox, QtCore.Qt.LeftButton, pos=QtCore.QPoint(2, int(checkbox.height() / 2))
    )
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    assert checkbox.isChecked()

    # click the back button and execute the search
    qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # make sure all items from the search are correct
    results_tree = dock_widget.searchResultsWidget.tree
    assert results_tree.topLevelItemCount() >= 1

    for image in results_tree.topLevelItem(0).images():
        if band == "4Band":
            assert "basic_analytic_4b" in image["assets"]
        if band == "8Band":
            assert "basic_analytic_8b" in image["assets"]


@pytest.mark.parametrize("instrument", ["PS2", "PS2.SD", "PSB.SD"])
def test_search_instrument_filter(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi, instrument
):
    """
    Verifies:
        - PLQGIS-TC17
    """
    dock_widget = logged_in_explorer_dock_widget().daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # disable all the item and spectral band checkboxes
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
    # default position for clicking checkboxes is incorrect, we must manually supply it
    # https://stackoverflow.com/questions/19418125/pysides-qtest-not-checking-box
    qtbot.mouseClick(
        checkbox, QtCore.Qt.LeftButton, pos=QtCore.QPoint(2, int(checkbox.height() / 2))
    )
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    assert checkbox.isChecked()

    # click the back button and execute the search
    qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # if no images found, just skip the test
    # TODO: extend the date range?
    results_tree = dock_widget.searchResultsWidget.tree
    if results_tree.topLevelItemCount() == 0:
        pytest.skip(f"No images found with instrument: {instrument}")

    for image in results_tree.topLevelItem(0).images():
        assert instrument == image["properties"]["instrument"]


def test_search_item_id_filter(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi
):
    """
    Verifies:
        - PLQGIS-TC17
    """
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
    # click the back button and execute the search
    qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # make sure all items from the search are correct
    results_tree = dock_widget.searchResultsWidget.tree
    assert results_tree.topLevelItemCount() == 1
    # make sure the item id for the returned image is correct
    assert results_tree.topLevelItem(0).images()[0]["id"] == item_id


@pytest.mark.parametrize(
    "slider_key, min_, max_, data_api_name",
    [
        ("cloud_cover", 0.0, 20.0, "cloud_percent"),
        ("sun_elevation", 45.0, 75.0, "sun_elevation"),
    ],
    ids=["Cloud Cover", "Sun Elevation"],
)
def test_search_env_conditions_filter(
    qtbot,
    logged_in_explorer_dock_widget,
    qgis_debug_enabled,
    sample_aoi,
    slider_key,
    min_,
    max_,
    data_api_name,
):
    """
    Verifies:
        - PLQGIS-TC17
    """
    dock_widget = logged_in_explorer_dock_widget().daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, sample_aoi)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnFilterResults, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    filter_widget = dock_widget._daily_filters_widget

    # get the slider we want to change
    sliders = filter_widget.frameRangeSliders.findChildren(PlanetExplorerRangeSlider)
    for slider in sliders:
        if slider.filter_key == slider_key:
            break

    # for ease of automation, we don't use mouse clicks here,
    # we just manually set the sliders to a range
    slider.setRangeLow(min_)
    slider.setRangeHigh(max_)
    slider.updateLabels()
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # click the back button and execute the search
    qtbot.mouseClick(dock_widget.btnBackFromFilters, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # make sure all items from the search are correct
    results_tree = dock_widget.searchResultsWidget.tree
    for index in range(results_tree.topLevelItemCount()):
        for image in results_tree.topLevelItem(index).images():
            assert image["properties"][data_api_name] <= max_
            assert image["properties"][data_api_name] >= min_


def test_search_wrong_aoi(qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled):
    """
    Verifies:
        - PLQGIS-TC04
    """
    dock_widget = logged_in_explorer_dock_widget().daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, "wrong AOI")
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
