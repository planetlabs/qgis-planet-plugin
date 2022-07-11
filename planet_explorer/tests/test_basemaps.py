import pytest

from qgis.core import QgsProject
from qgis.PyQt import QtCore

from planet_explorer.tests.utils import qgis_debug_wait

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]


def test_explorer_basemaps_shown(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled
):
    """
    Verifies:
        - PLQGIS-TC10
    """
    dock_widget = logged_in_explorer_dock_widget()
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    basemaps_tab_index = None
    # get the index of the basemaps widget
    for index in range(dock_widget.tabWidgetResourceType.count()):
        if dock_widget.tabWidgetResourceType.tabText(index) == "Basemaps":
            basemaps_tab_index = index
            break

    if basemaps_tab_index:
        assert dock_widget.tabWidgetResourceType.isTabEnabled(basemaps_tab_index)
    else:
        pytest.fail("Basemaps tab is not enabled or not found!")

    # determine where to click to hit the "Basemaps" tab
    # position calculated as relative to the center of the whole tab bar
    tab_bar = dock_widget.tabWidgetResourceType.tabBar()
    posx, posy = int(tab_bar.rect().width() * 0.9), tab_bar.rect().center().y()
    # keep increasing posx until we hit the next tab
    while tab_bar.tabAt(QtCore.QPoint(posx, posy)) == 0:
        posx = int(posx * 1.1)

    qtbot.mouseClick(tab_bar, QtCore.Qt.LeftButton, pos=QtCore.QPoint(posx, posy))
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    def _basemap_opened():
        assert dock_widget.tabWidgetResourceType.currentIndex() == 1

    qtbot.waitUntil(_basemap_opened, timeout=20 * 1000)

    assert dock_widget.basemaps_widget.mosaicsList.count() == 0
    assert dock_widget.basemaps_widget.comboSeriesName.count() > 1

    # select a series
    series_name_widget = dock_widget.basemaps_widget.comboSeriesName
    qtbot.keyClicks(series_name_widget, "Global Monthly")
    qtbot.keyPress(series_name_widget, QtCore.Qt.Key_Enter)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    assert dock_widget.basemaps_widget.mosaicsList.count() > 1


def test_explorer_basemaps_explorable(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled
):
    """
    Verifies:
        - PLQGIS-TC10
    """
    dock_widget = logged_in_explorer_dock_widget()
    basemaps_widget = dock_widget.basemaps_widget
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    dock_widget.show_mosaics_panel()

    def _basemap_opened():
        assert dock_widget.tabWidgetResourceType.currentIndex() == 1

    qtbot.waitUntil(_basemap_opened, timeout=20 * 1000)

    # select a series
    series_name_widget = dock_widget.basemaps_widget.comboSeriesName
    qtbot.keyClicks(series_name_widget, "Global Monthly")
    qtbot.keyPress(series_name_widget, QtCore.Qt.Key_Enter)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # add an item from the basemaps series to the map layer
    mosaics_list = basemaps_widget.mosaicsList
    assert mosaics_list.count() > 0
    item = mosaics_list.item(0)
    qtbot.mouseClick(mosaics_list.itemWidget(item).checkBox, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    assert "1 items" in basemaps_widget.btnOrder.text()
    qtbot.mouseClick(basemaps_widget.btnExplore, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    layers = QgsProject.instance().mapLayers().values()
    assert len(layers) == 1
