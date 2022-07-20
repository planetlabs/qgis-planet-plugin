import pytest

from PyQt5.QtWidgets import QPushButton
from qgis.PyQt import QtCore
from planet_explorer.gui.pe_orders import PlanetOrdersDialog
from planet_explorer.tests.utils import get_random_string


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


def test_order_scene(qtbot, qgis_debug_enabled, checked_images, order_monitor_widget):
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

        # review page and place the order
        qtbot.mouseClick(order_dialog.btnPlaceOrder, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        order_dialog.close()

    QtCore.QTimer.singleShot(1000, _order_dialog_interact)
    order_dialog.exec_()

    # make sure the new order is shown in the order_monitor page
    order_monitor = order_monitor_widget(dock_widget)
    order_names = []
    for index in range(order_monitor.listOrders.count()):
        item = order_monitor.listOrders.item(index)
        item_widget = order_monitor.listOrders.itemWidget(item)
        order_names.append(item_widget.order.order["name"])

    assert any(
        order_name in o_name for o_name in order_names
    ), f"New order not present in orders list: {order_names}"


def test_order_download(
    qtbot,
    logged_in_explorer_dock_widget,
    qgis_debug_enabled,
    sample_aoi,
    order_monitor_widget,
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

    # download the first item and wait until the text changes to re-download
    item_widget = order_monitor.listOrders.itemWidget(order_monitor.listOrders.item(0))
    download_button = [
        widget for widget in item_widget.children() if isinstance(widget, QPushButton)
    ][0]

    qtbot.mouseClick(download_button, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # check that the text has changed
    def check_download_text():
        widget = order_monitor.listOrders.itemWidget(order_monitor.listOrders.item(0))
        button = [
            widget for widget in widget.children() if isinstance(widget, QPushButton)
        ][0]
        return button.text() == "Re-Download"

    qtbot.waitUntil(check_download_text, timeout=20 * 1000)
