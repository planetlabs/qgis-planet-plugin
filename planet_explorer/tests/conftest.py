import os
import json
import pytest

from planet_explorer import classFactory
from unittest.mock import MagicMock
from qgis.PyQt import QtCore
from qgis.testing import start_app


if os.environ.get("IS_DOCKER_CONTAINER") and os.environ["IS_DOCKER_CONTAINER"].lower()[
    0
] in ["t", "y", "1"]:
    # when running in a docker container, we use the start_app provided by qgis rather
    # than that of pytest-qgis. pytest-qgis does not cleanup the application properly
    # and results in a seg-fault
    start_app()


@pytest.hookimpl(tryfirst=True)
def pytest_addoption(parser) -> None:
    """Add some custom ini values"""
    parser.addini(
        "qgis_window_height",
        "Set the window height for QGIS",
        type="string",
        default="800",
    )
    parser.addini(
        "qgis_window_width",
        "Set the window width for QGIS",
        type="string",
        default="800",
    )


@pytest.fixture(scope="session")
def qgis_debug_enabled(request, pytestconfig):
    gui_enabled = request.config._plugin_settings.gui_enabled
    yield gui_enabled


@pytest.fixture
def pe_qgis_iface(qgis_iface):
    """
    Patch the pytest-qgis's qgis_iface to include some specific methods
    for the Planet Explorer plugin.
    """
    for method in [
        "addPluginToWebMenu",
        "messageTimeout",
        "removePluginWebMenu",
        "removeDockWidget",
        "layerTreeView",
    ]:
        setattr(qgis_iface, method, MagicMock)

    yield qgis_iface


@pytest.fixture
def plugin(pytestconfig, pe_qgis_iface, qgis_parent, qgis_new_project):
    """
    Initialize and return the plugin object.

    Resize the parent window according to config.
    """
    qgis_parent.resize(
        QtCore.QSize(
            int(pytestconfig.getini("qgis_window_width")),
            int(pytestconfig.getini("qgis_window_height")),
        )
    )

    plugin = classFactory(pe_qgis_iface)
    plugin.initGui()
    yield plugin
    plugin.unload()


@pytest.fixture
def plugin_toolbar(pytestconfig, plugin, qgis_debug_enabled, qtbot):
    toolbar = plugin.toolbar
    toolbar.resize(int(pytestconfig.getini("qgis_window_width")), 70)
    if qgis_debug_enabled:
        toolbar.show()
    qtbot.add_widget(toolbar)
    yield toolbar


@pytest.fixture
def sample_aoi():
    yield json.dumps(
        {
            "coordinates": [
                [
                    [-0.334369, 40.151264],
                    [-0.276291, 40.151264],
                    [-0.276291, 40.172081],
                    [-0.334369, 40.172081],
                    [-0.334369, 40.151264],
                ]
            ],
            "type": "Polygon",
        }
    )


@pytest.fixture
def large_aoi():
    yield json.dumps(
        {
            "coordinates": [
                [
                    [-94.317626953125, 28.748396571187406],
                    [-88.8134765625, 28.748396571187406],
                    [-88.8134765625, 32.045332838858506],
                    [-94.317626953125, 32.045332838858506],
                    [-94.317626953125, 28.748396571187406],
                ]
            ],
            "type": "Polygon",
        }
    )


@pytest.fixture
def explorer_dock_widget(
    plugin, plugin_toolbar, qgis_debug_enabled, qtbot, pe_qgis_iface
):
    """
    Convenience fixture for instantiating the explorer dock widget
    """

    def _get_widget():
        from planet_explorer.tests.utils import get_explorer_dockwidget

        dock_widget = get_explorer_dockwidget(plugin_toolbar, login=False)
        qtbot.add_widget(dock_widget)
        # Show the widget if debug mode is enabled
        if qgis_debug_enabled:
            dock_widget.show()
        return dock_widget

    yield _get_widget

    # reset the dockwidget_instance at the end of the test (since it's cleaned up by qtbot)
    from planet_explorer.tests.utils import pe_explorer_dockwidget

    pe_explorer_dockwidget.dockwidget_instance = None


@pytest.fixture
def logged_in_explorer_dock_widget(
    plugin, plugin_toolbar, qgis_debug_enabled, qtbot, pe_qgis_iface
):
    """
    Convenience fixture for instantiating the explorer dock widget
    """

    def _get_widget():
        from planet_explorer.tests.utils import get_explorer_dockwidget

        dock_widget = get_explorer_dockwidget(plugin_toolbar, login=True)
        qtbot.add_widget(dock_widget)
        # Show the widget if debug mode is enabled
        if qgis_debug_enabled:
            dock_widget.show()
        return dock_widget

    yield _get_widget

    # reset the dockwidget_instance at the end of the test (since it's cleaned up by qtbot)
    from planet_explorer.tests.utils import pe_explorer_dockwidget

    pe_explorer_dockwidget.dockwidget_instance = None


@pytest.fixture
def order_monitor_widget(qgis_debug_enabled, qtbot):
    """
    Convenience fixture for getting the order monitor widget
    """

    def _get_widget(explorer_dockwidget):
        from planet_explorer.tests.utils import get_order_monitor_widget

        order_widget = get_order_monitor_widget(explorer_dockwidget)
        qtbot.add_widget(order_widget)
        if qgis_debug_enabled:
            order_widget.show()
        return order_widget

    yield _get_widget

    # reset the dockwidget_instance at the end of the test (since it's cleaned up by qtbot)
    from planet_explorer.tests.utils import pe_orders_monitor_dockwidget

    pe_orders_monitor_dockwidget.dockwidget_instance = None


@pytest.fixture
def tasking_widget(qgis_debug_enabled, qtbot):
    """
    Convenience fixture for getting the order monitor widget
    """

    def _get_widget(explorer_dockwidget):
        from planet_explorer.tests.utils import get_tasking_widget

        task_widget = get_tasking_widget(explorer_dockwidget)
        qtbot.add_widget(task_widget)
        if qgis_debug_enabled:
            task_widget.show()
        return task_widget

    yield _get_widget

    # reset the dockwidget_instance at the end of the test (since it's cleaned up by qtbot)
    from planet_explorer.tests.utils import pe_tasking_dockwidget

    pe_tasking_dockwidget.dockwidget_instance = None
