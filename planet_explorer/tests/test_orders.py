import pytest

from PyQt5.QtWidgets import QPushButton
from qgis.PyQt import QtCore
from planet_explorer.gui.pe_orders import PlanetOrdersDialog
from planet_explorer.gui.pe_orders_monitor_dockwidget import OrderWrapper
from planet_explorer.tests.utils import get_random_string
from planet_explorer.planet_api.p_quad_orders import QuadOrder


from planet_explorer.tests.utils import qgis_debug_wait

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


def test_order_download(
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
        checkbox, QtCore.Qt.LeftButton, pos=QtCore.QPoint(2, int(checkbox.height() / 2))
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
        assert "download" in download_button.text().lower()

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


def test_order_scene(
    qtbot, qgis_debug_enabled, checked_images, order_monitor_widget, qgis_version
):
    """
    Verifies:
        - PLQGIS-TC06
    """
    dock_widget, daily_images_widget = checked_images

    # make sure button no longer says 0 images selected
    assert "0" not in daily_images_widget.btnOrder.text()

    order_dialog = get_order_dialog(qtbot, daily_images_widget)
    order_name = f"test-qgis-order-{get_random_string()}"

    def _order_dialog_interact():
        # name page
        assert not order_dialog.btnContinueName.isEnabled()
        qtbot.keyClicks(order_dialog.txtOrderName, order_name)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        assert order_dialog.btnContinueName.isEnabled()
        qtbot.mouseClick(order_dialog.btnContinueName, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        # assets page
        qtbot.mouseClick(order_dialog.btnContinueAssets, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        # check STAC button state
        stac_order = order_dialog.stac_order
        qtbot.mouseClick(order_dialog.metadata_widget.btnSTAC, QtCore.Qt.LeftButton)
        assert order_dialog.stac_order != stac_order

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

        assert any(
            order_name in o_name for o_name in order_names
        ), f"New order not present in orders list: {order_names}"

        # Check for all order metadata except QuadOrder orders
        order_metadata = [
            order.metadata() if not isinstance(order, QuadOrder) else None
            for order in orders
        ]
        stac_metadata = {"stac": {}}

        if order_dialog.stac_order:
            assert stac_metadata in order_metadata
        else:
            assert stac_metadata not in order_metadata
