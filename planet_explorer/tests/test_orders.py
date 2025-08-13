import os
import shutil
import unittest

import pytest
from qgis.core import QgsProject
from qgis.PyQt import QtCore
from qgis.PyQt.QtWidgets import QPushButton

from planet_explorer.gui.pe_orders import PlanetOrdersDialog
from planet_explorer.gui.pe_orders_monitor_dockwidget import OrderWrapper
from planet_explorer.planet_api.p_quad_orders import QuadOrder
from planet_explorer.tests.utils import get_random_string, qgis_debug_wait

from ..pe_utils import orders_download_folder

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]


@pytest.fixture
def checked_images(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, sample_aoi
):
    dock_widget = logged_in_explorer_dock_widget()
    daily_images_widget = dock_widget.daily_images_widget
    qtbot.add_widget(daily_images_widget)

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(daily_images_widget._aoi_filter.leAOI, sample_aoi)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(daily_images_widget.btnSearch, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # order the first result
    results_tree = daily_images_widget.searchResultsWidget.tree
    checkbox = results_tree.itemWidget(results_tree.topLevelItem(0), 0).checkBox
    qtbot.mouseClick(
        checkbox, QtCore.Qt.LeftButton, pos=QtCore.QPoint(2, int(checkbox.height() / 2))
    )
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    yield dock_widget, daily_images_widget


def get_order_dialog(qtbot, daily_images_widget):
    images = daily_images_widget.searchResultsWidget.selected_images()

    tool_resources = {}
    if daily_images_widget._aoi_filter.leAOI.text():  # noqa
        tool_resources["aoi"] = daily_images_widget._aoi_filter.leAOI.text()  # noqa
    else:
        tool_resources["aoi"] = None

    dlg = PlanetOrdersDialog(images, tool_resources=tool_resources)
    qtbot.add_widget(dlg)

    dlg.setMinimumWidth(700)
    dlg.setMinimumHeight(750)
    return dlg


class TestOrders(unittest.TestCase):
    def test_order_download(
        self,
        qtbot,
        logged_in_explorer_dock_widget,
        qgis_debug_enabled,
        order_monitor_widget,
        qgis_version,
    ):
        """
        Verifies:
            - PLQGIS-TC07
        """
        dock_widget = logged_in_explorer_dock_widget()
        order_monitor = order_monitor_widget(dock_widget)
        dock_widget.hide()
        # show only downloadable orders
        checkbox = order_monitor.chkOnlyDownloadable
        qtbot.mouseClick(
            checkbox,
            QtCore.Qt.LeftButton,
            pos=QtCore.QPoint(2, int(checkbox.height() / 2)),
        )
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        for index in range(order_monitor.listOrders.count()):
            item = order_monitor.listOrders.item(index)
            item_widget = order_monitor.listOrders.itemWidget(item)
            download_button = [
                widget
                for widget in item_widget.children()
                if isinstance(widget, QPushButton)
            ][0]
            self.assertIn("download", download_button.text().lower())

        order_item = order_monitor.listOrders.item(0)
        order_item_widget = order_monitor.listOrders.itemWidget(order_item)

        # Note: using the UI to click the button was flaky and unnecessarily complicated
        # just call the method to explicitly download and check it that way

        # We only download for the latest version of QGIS because when these run in
        # CI trying to download multiple orders at the same time posed problems.
        if qgis_version > 32600:
            # TODO: better workaround?
            order_item_widget.download(is_unit_test=True)
            qtbot.waitUntil(order_item.order.downloaded, timeout=60 * 1000)

    @pytest.mark.parametrize(
        "image_id, image_name, root_dir",
        [
            pytest.param(
                "5c9e6c59-eb35-485d-ab7d-04a75e9e0f14",
                "20221221_084022_18_2414_3B_AnalyticMS_SR.tif",
                "/usr/src/planet_explorer/tests/data/test_add_to_map/planet_orders",
            ),
        ],
    )
    def test_order_add_to_map(
        self,
        qtbot,
        logged_in_explorer_dock_widget,
        qgis_debug_enabled,
        order_monitor_widget,
        qgis_version,
        image_id,
        image_name,
        root_dir,
    ):
        """This test is performed on the 'Add to map' button of the orders monitor widget.
        An image is copied from the plugin directory/repo to the Planet orders directory.
        This directory stores the downloaded orders. The widget of a particular download is
        initilalized and added to the QGIS canvas instance. If the image could not be added,
        the test will fail. If the image cannot be found in the map layers list of the canvas
        after adding the image, the test will also fail.
        """
        dock_widget = logged_in_explorer_dock_widget()
        order_monitor = order_monitor_widget(dock_widget)
        dock_widget.hide()

        # The test data for this function is stored here:
        # planet_explorer/tests/Data/test_add_to_map
        daily_imagery_dir = "{}/{}".format(root_dir, image_id)
        orders_folder = "{}/daily".format(orders_download_folder())
        copy_folder = "{}/{}".format(orders_folder, image_id)

        if not os.path.exists(copy_folder):
            # Copies the test data to the orders folder use
            shutil.copytree(daily_imagery_dir, copy_folder)
        else:
            # The test data is missing
            self.fail("The test data is missing")

        count = order_monitor.listOrders.count()
        found = False
        i = 0
        while i < count:
            # Loops through each of the layers stored in the QGIS instance
            # This is done to ensure the correct order is used for the test, as other tests might
            # also add to the orders list
            item = order_monitor.listOrders.item(i)
            item_order = item.order
            item_id = item_order.id()
            if item_id == image_id:
                # Add to map test data found
                item_widget = order_monitor.listOrders.itemWidget(item)
                success = item_widget.add_to_map()

                # Could not add the image to the QGIS canvas
                # Either the manifest or the image could not be found
                self.assertTrue(success, "Could not add the image to the QGIS canvas")

                map_layers = QgsProject.instance().mapLayers()
                keys = map_layers.keys()
                for key in keys:
                    # Checks each of the layers in the QGIS instance
                    # Using this approach as other tests might also add layers to the canvas
                    layer = map_layers.get(key)
                    layer_name = layer.name()
                    if image_name in layer_name:
                        # The image has been found in the QGIS instance,
                        # and therefore added successfully
                        found = True
                break

            i = i + 1

        # True if found, otherwise False
        self.assertTrue(found)

    @pytest.mark.xfail(reason="Known issue: test is currently failing")
    def test_order_scene(
        self,
        qtbot,
        qgis_debug_enabled,
        checked_images,
        order_monitor_widget,
        qgis_version,
    ):
        """
        Verifies:
            - PLQGIS-TC06
        """
        dock_widget, daily_images_widget = checked_images

        # make sure button no longer says 0 images selected
        self.assertNotIn("0", daily_images_widget.btnOrder.text())

        order_dialog = get_order_dialog(qtbot, daily_images_widget)
        order_name = f"test-qgis-order-{get_random_string()}"

        def _order_dialog_interact():
            # name page
            self.assertFalse(order_dialog.btnContinueName.isEnabled())
            qtbot.keyClicks(order_dialog.txtOrderName, order_name)
            qgis_debug_wait(qtbot, qgis_debug_enabled)
            self.assertTrue(order_dialog.btnContinueName.isEnabled())
            qtbot.mouseClick(order_dialog.btnContinueName, QtCore.Qt.LeftButton)
            qgis_debug_wait(qtbot, qgis_debug_enabled)

            # assets page
            qtbot.mouseClick(order_dialog.btnContinueAssets, QtCore.Qt.LeftButton)
            qgis_debug_wait(qtbot, qgis_debug_enabled)

            # check STAC button state
            stac_order = order_dialog.stac_order
            qtbot.mouseClick(order_dialog.metadata_widget.btnSTAC, QtCore.Qt.LeftButton)
            self.assertNotEqual(order_dialog.stac_order, stac_order)

            # review page and place the order. note we only actually place the order
            # on the latest version of QGIS to keep the total number of orders down.
            if qgis_version > 32600:
                qtbot.mouseClick(order_dialog.btnPlaceOrder, QtCore.Qt.LeftButton)
                qgis_debug_wait(qtbot, qgis_debug_enabled)
            order_dialog.close()

        QtCore.QTimer.singleShot(1000, _order_dialog_interact)
        order_dialog.exec_()

        # make sure the new order is shown in the order_monitor page
        if qgis_version > 32600:
            order_monitor = order_monitor_widget(dock_widget)
            order_names = []
            orders = []
            for index in range(order_monitor.listOrders.count()):
                item = order_monitor.listOrders.item(index)
                item_widget = order_monitor.listOrders.itemWidget(item)
                orders.append(item_widget.order)
                if isinstance(item_widget.order, OrderWrapper):
                    order_names.append(item_widget.order.order["name"])

            self.assertTrue(
                any(order_name == o_name for o_name in order_names),
                f"New order missing from orders list: {order_names}",
            )

            # Check for all order metadata except QuadOrder orders
            order_metadata = [
                order.metadata() if not isinstance(order, QuadOrder) else None
                for order in orders
            ]
            stac_metadata = {"stac": {}}

            if order_dialog.stac_order:
                self.assertIn(stac_metadata, order_metadata)
            else:
                self.assertNotIn(stac_metadata, order_metadata)
