import random
import unittest

import pytest
from qgis.PyQt import QtCore

from planet_explorer.gui.pe_basemap_layer_widget import (
    PLANET_CURRENT_MOSAIC,
    PLANET_MOSAIC_PROC,
    PLANET_MOSAIC_RAMP,
)
from planet_explorer.planet_api.p_quad_orders import QuadOrder
from planet_explorer.tests.utils import (
    filter_basemaps_by_name,
    get_random_string,
    qgis_debug_wait,
)

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]


@pytest.fixture
def basemaps_widget(qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled):
    dock_widget = logged_in_explorer_dock_widget()
    basemaps_widget = dock_widget.basemaps_widget
    qtbot.addWidget(basemaps_widget)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    dock_widget.show_mosaics_panel()

    def _basemap_opened():
        if dock_widget.tabWidgetResourceType.currentIndex() != 1:
            raise AssertionError("Expected currentIndex to be 1")

    qtbot.waitUntil(_basemap_opened, timeout=20 * 1000)
    yield dock_widget, basemaps_widget


class TestBasemaps(unittest.TestCase):

    def test_basemaps_shown(
        self, qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled
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

        self.assertIsNotNone(
            basemaps_tab_index, "Basemaps tab is not enabled or not found!"
        )
        self.assertTrue(
            dock_widget.tabWidgetResourceType.isTabEnabled(basemaps_tab_index)
        )

        # determine where to click to hit the "Basemaps" tab
        tab_bar = dock_widget.tabWidgetResourceType.tabBar()
        posx, posy = int(tab_bar.rect().width() * 0.9), tab_bar.rect().center().y()
        # keep increasing posx until we hit the next tab
        while tab_bar.tabAt(QtCore.QPoint(posx, posy)) == 0:
            posx = int(posx * 1.1)

        qtbot.mouseClick(tab_bar, QtCore.Qt.LeftButton, pos=QtCore.Qt.Point(posx, posy))
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        def _basemap_opened():
            self.assertEqual(dock_widget.tabWidgetResourceType.currentIndex(), 1)

        qtbot.waitUntil(_basemap_opened, timeout=20 * 1000)

        self.assertEqual(dock_widget.basemaps_widget.mosaicsList.count(), 0)
        self.assertGreater(dock_widget.basemaps_widget.comboSeriesName.count(), 1)

        # select a series
        series_name_widget = dock_widget.basemaps_widget.comboSeriesName
        qtbot.keyClicks(series_name_widget, "Global Monthly")
        qtbot.keyPress(series_name_widget, QtCore.Qt.Key_Enter)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        self.assertGreater(dock_widget.basemaps_widget.mosaicsList.count(), 1)

    def test_basemaps_time_slider(
        self,
        qtbot,
        qgis_debug_enabled,
        qgis_new_project,
        qgis_canvas,
        plugin,
        basemaps_widget,
    ):
        """
        Verifies:
            - PLQGIS-TC11
            - PLQGIS-TC13
        """
        _, basemaps_widget = basemaps_widget
        num_months = 4
        filter_basemaps_by_name(
            "Global Monthly", qtbot, basemaps_widget, qgis_debug_enabled
        )
        mosaics_list = basemaps_widget.mosaicsList
        for index in range(num_months):
            qtbot.mouseClick(
                mosaics_list.itemWidget(mosaics_list.item(index)).checkBox,
                QtCore.Qt.LeftButton,
            )
            qgis_debug_wait(qtbot, qgis_debug_enabled)

        self.assertIn("4 items", basemaps_widget.btnOrder.text())
        qtbot.mouseClick(basemaps_widget.btnExplore, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        self.assertEqual(qgis_canvas.layerCount(), 1)

        layer = qgis_canvas.layers()[0]
        widget = plugin.provider.createWidget(layer, 0)
        if qgis_debug_enabled:
            widget.show()

        self.assertEqual(len(widget.mosaicnames), num_months)
        for index, name in enumerate(widget.mosaicnames):
            widget.slider.setValue(index)
            qgis_debug_wait(qtbot, qgis_debug_enabled)
            self.assertEqual(layer.customProperty(PLANET_CURRENT_MOSAIC), name)

    def test_basemaps_band_selector(
        self,
        qtbot,
        qgis_debug_enabled,
        qgis_new_project,
        qgis_canvas,
        plugin,
        basemaps_widget,
    ):
        """
        Verifies:
            - PLQGIS-TC11
            - PLQGIS-TC12
        """
        _, basemaps_widget = basemaps_widget
        filter_basemaps_by_name("Coral Sea", qtbot, basemaps_widget, qgis_debug_enabled)

        mosaics_list = basemaps_widget.mosaicsList
        qtbot.mouseClick(
            mosaics_list.itemWidget(mosaics_list.item(0)).checkBox, QtCore.Qt.LeftButton
        )
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        qtbot.mouseClick(basemaps_widget.btnExplore, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        self.assertEqual(qgis_canvas.layerCount(), 1)

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
            self.assertEqual(layer.customProperty(PLANET_MOSAIC_PROC), proc_option)

            if widget.renderingOptionsWidget.ramp():
                ramp_options = [
                    widget.renderingOptionsWidget.comboRamp.itemText(index)
                    for index in range(widget.renderingOptionsWidget.comboRamp.count())
                    if len(widget.renderingOptionsWidget.comboRamp.itemText(index)) > 0
                ]
                ramp_option = random.choice(ramp_options)  # nosec
                widget.renderingOptionsWidget.set_ramp(ramp_option)
                qgis_debug_wait(qtbot, qgis_debug_enabled)
                self.assertEqual(layer.customProperty(PLANET_MOSAIC_RAMP), ramp_option)

    def test_basemaps_order_partial(
        self,
        qtbot,
        qgis_debug_enabled,
        basemaps_widget,
        sample_aoi,
        order_monitor_widget,
        qgis_version,
    ):
        """
        Verifies:
            - PLQGIS-TC14
        """
        if str(qgis_version).startswith("322") or str(qgis_version).startswith("324"):
            self.skipTest("This test causes a seg fault on QGIS 3.22 and 3.24")
        dock_widget, basemaps_widget = basemaps_widget
        order_name = f"test-qgis-basemaps-order-{get_random_string()}"

        filter_basemaps_by_name(
            "Global Monthly", qtbot, basemaps_widget, qgis_debug_enabled
        )
        mosaics_list = basemaps_widget.mosaicsList
        qtbot.mouseClick(
            mosaics_list.itemWidget(mosaics_list.item(0)).checkBox, QtCore.Qt.LeftButton
        )
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        qtbot.mouseClick(basemaps_widget.btnOrder, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        qtbot.mouseClick(basemaps_widget.radioDownloadAOI, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(basemaps_widget.btnNextOrderMethodPage, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        qtbot.keyClicks(basemaps_widget.aoi_filter.leAOI, sample_aoi)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(basemaps_widget.btnFindQuads, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(basemaps_widget.btnNextQuadsPage, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        qtbot.keyClicks(basemaps_widget.txtOrderName, order_name)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        if qgis_version > 32600:
            qtbot.mouseClick(basemaps_widget.btnSubmitOrder, QtCore.Qt.LeftButton)
            qgis_debug_wait(qtbot, qgis_debug_enabled)
            qtbot.mouseClick(basemaps_widget.btnCloseConfirmation, QtCore.Qt.LeftButton)
            qgis_debug_wait(qtbot, qgis_debug_enabled)

            if qgis_debug_enabled:
                dock_widget.hide()

            order_monitor = order_monitor_widget(dock_widget)
            order_names = []
            item_widget = None
            for index in range(order_monitor.listOrders.count()):
                item = order_monitor.listOrders.item(index)
                item_widget = order_monitor.listOrders.itemWidget(item)
                if isinstance(item_widget.order, QuadOrder):
                    order_names.append(item_widget.order.name)
                    if order_name == item_widget.order.name:
                        break
            self.assertIn(
                order_name,
                order_names,
                f"New order missing from orders list: {order_names}",
            )
            self.assertIsNotNone(
                item_widget, "item_widget is None, cannot download basemap"
            )
            item_widget.download(is_unit_test=True)
            qtbot.waitUntil(item_widget.order.downloaded, timeout=60 * 1000)  # noqa


# ...other
