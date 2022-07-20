import os
import random

from planet_explorer import pe_utils
from planet_explorer.gui import pe_explorer_dockwidget
from planet_explorer.gui import pe_orders_monitor_dockwidget
from planet_explorer.gui import pe_tasking_dockwidget


def patch_iface():
    pe_utils.iface.messageTimeout.return_value = 5


def test_aoi():
    return (
        '{"coordinates":[[[-0.334369,40.151264],[-0.276291,40.151264],'
        "[-0.276291,40.172081],[-0.334369,40.172081],[-0.334369,40.151264]]]"
        ',"type":"Polygon"}'
    )


def get_testing_credentials():
    if (
        os.environ.get("PLANET_USER") is None
        or os.environ.get("PLANET_PASSWORD") is None
    ):
        raise ValueError(
            "PLANET_USER and PLANET_PASSWORD env vars are undefined! Cannot run tests."
        )
    return os.environ["PLANET_USER"], os.environ["PLANET_PASSWORD"]


def qgis_debug_wait(qtbot, qgis_debug_enabled, wait=1000):
    """Helper function to see what is going on when running tests."""
    if qgis_debug_enabled:
        qtbot.wait(wait)


def get_explorer_dockwidget(plugin_toolbar, login=True):
    """
    Setup the explorer dock_widget for tests
    """
    dock_widget = pe_explorer_dockwidget._get_widget_instance()  # noqa
    current_geometry = dock_widget.geometry()
    toolbar_geometry = plugin_toolbar.geometry()
    dock_widget.setGeometry(
        current_geometry.x(),
        toolbar_geometry.height() + 1,
        current_geometry.width(),
        current_geometry.height(),
    )
    dock_widget._setup_client()
    dock_widget.chkBxSaveCreds.setChecked(False)
    if login:
        username, password = get_testing_credentials()
        dock_widget.p_client.log_in(username, password)
    return dock_widget


def get_order_monitor_widget(explorer_dockwidget):
    """
    Setup orders monitor dock_widget for tests
    """
    order_widget = pe_orders_monitor_dockwidget._get_widget_instance()  # noqa
    current_geometry = order_widget.geometry()
    order_widget.setGeometry(
        explorer_dockwidget.geometry().width() + 1,
        explorer_dockwidget.geometry().y(),
        current_geometry.width(),
        current_geometry.height(),
    )
    return order_widget


def get_tasking_widget(explorer_dockwidget):
    """
    Setup orders monitor dock_widget for tests
    """
    tasking_widget = pe_tasking_dockwidget._get_widget_instance()  # noqa
    current_geometry = tasking_widget.geometry()
    tasking_widget.setGeometry(
        explorer_dockwidget.geometry().width() + 1,
        explorer_dockwidget.geometry().y(),
        current_geometry.width(),
        current_geometry.height(),
    )
    return tasking_widget


def get_random_string(length=8):
    alphanumeric = "0123456789AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz"
    return "".join(random.choice(alphanumeric) for _ in range(length)).strip()
