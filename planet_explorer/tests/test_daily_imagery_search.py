import pytest

from qgis.PyQt import QtCore

from planet_explorer.tests.utils import qgis_debug_wait

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]


def test_explorer_search_daily_images(
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


def test_search_daily_images_wrong_aoi(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled
):
    """
    Verifies:
        - PLQGIS-TC04
    """
    dock_widget = logged_in_explorer_dock_widget().daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, "wrong AOI")
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
