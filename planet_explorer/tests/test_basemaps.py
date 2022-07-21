import pytest
import random

from qgis.PyQt import QtCore

from planet_explorer.tests.utils import qgis_debug_wait
from planet_explorer.tests.utils import filter_basemaps_by_name
from planet_explorer.gui.pe_basemap_layer_widget import PLANET_CURRENT_MOSAIC
from planet_explorer.gui.pe_basemap_layer_widget import PLANET_MOSAIC_RAMP
from planet_explorer.gui.pe_basemap_layer_widget import PLANET_MOSAIC_PROC


pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]


@pytest.fixture
def basemaps_widget(qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled):
    dock_widget = logged_in_explorer_dock_widget()
    basemaps_widget = dock_widget.basemaps_widget
    qtbot.addWidget(basemaps_widget)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    dock_widget.show_mosaics_panel()

    def _basemap_opened():
        assert dock_widget.tabWidgetResourceType.currentIndex() == 1

    qtbot.waitUntil(_basemap_opened, timeout=20 * 1000)
    yield basemaps_widget


def test_basemaps_shown(qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled):
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


def test_basemaps_time_slider(
    qtbot, qgis_debug_enabled, qgis_new_project, qgis_canvas, plugin, basemaps_widget
):
    """
    Verifies:
        - PLQGIS-TC11
        - PLQGIS-TC13
    """
    num_months = 4
    # filter by 'Global Monthly' series
    filter_basemaps_by_name(
        "Global Monthly", qtbot, basemaps_widget, qgis_debug_enabled
    )
    # select a few items in the series
    mosaics_list = basemaps_widget.mosaicsList
    for index in range(num_months):
        qtbot.mouseClick(
            mosaics_list.itemWidget(mosaics_list.item(index)).checkBox,
            QtCore.Qt.LeftButton,
        )
        qgis_debug_wait(qtbot, qgis_debug_enabled)

    assert "4 items" in basemaps_widget.btnOrder.text()
    qtbot.mouseClick(basemaps_widget.btnExplore, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    assert qgis_canvas.layerCount() == 1

    # create the time slider widget (we do it this way so we don't have to create the whole layer
    # viewer widget provided by QGIS
    layer = qgis_canvas.layers()[0]
    widget = plugin.provider.createWidget(layer, 0)
    if qgis_debug_enabled:
        widget.show()

    # make sure slider includes each month
    assert len(widget.mosaicnames) == num_months
    # make sure moving the slider changes the currently shown basemap/mosaic
    for index, name in enumerate(widget.mosaicnames):
        widget.slider.setValue(index)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        assert layer.customProperty(PLANET_CURRENT_MOSAIC) == name


def test_basemaps_band_selector(
    qtbot, qgis_debug_enabled, qgis_new_project, qgis_canvas, plugin, basemaps_widget
):
    """
    Verifies:
        - PLQGIS-TC11
        - PLQGIS-TC12
    """
    filter_basemaps_by_name("Coral Sea", qtbot, basemaps_widget, qgis_debug_enabled)

    # select an item in the series
    mosaics_list = basemaps_widget.mosaicsList
    qtbot.mouseClick(
        mosaics_list.itemWidget(mosaics_list.item(0)).checkBox, QtCore.Qt.LeftButton
    )
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    qtbot.mouseClick(basemaps_widget.btnExplore, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    assert qgis_canvas.layerCount() == 1

    # create the band selector widget (we do it this way so we don't have to create the whole layer
    # viewer widget provided by QGIS
    layer = qgis_canvas.layers()[0]
    widget = plugin.provider.createWidget(layer, 0)
    if qgis_debug_enabled:
        widget.show()

    proc_options = [
        widget.renderingOptionsWidget.comboProc.itemText(index)
        for index in range(widget.renderingOptionsWidget.comboProc.count())
    ]

    for proc_option in proc_options:
        widget.renderingOptionsWidget.set_process(proc_option)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        assert layer.customProperty(PLANET_MOSAIC_PROC) == proc_option

        if widget.renderingOptionsWidget.ramp():
            ramp_options = [
                widget.renderingOptionsWidget.comboRamp.itemText(index)
                for index in range(widget.renderingOptionsWidget.comboRamp.count())
            ]
            # since there are so many color ramps,  just randomly select one to test
            ramp_option = random.choice(ramp_options)
            widget.renderingOptionsWidget.set_ramp(ramp_option)
            qgis_debug_wait(qtbot, qgis_debug_enabled)
            assert layer.customProperty(PLANET_MOSAIC_RAMP) == ramp_option
