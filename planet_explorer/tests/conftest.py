# -*- coding: utf-8 -*-
import json
import os
import sys
import types
from unittest.mock import MagicMock

import pytest
from qgis.PyQt import QtCore
from qgis.testing import start_app

from planet_explorer import classFactory

if os.environ.get("IS_DOCKER_CONTAINER") and os.environ["IS_DOCKER_CONTAINER"].lower()[
    0
] in ["t", "y", "1"]:
    # when running in a docker container, we use the start_app provided by qgis rather
    # than that of pytest-qgis. pytest-qgis does not cleanup the application properly
    # and results in a seg-fault
    start_app()

if "resources_rc" not in sys.modules:
    sys.modules["resources_rc"] = types.ModuleType("resources_rc")


@pytest.hookimpl(tryfirst=True)
def pytest_addoption(parser) -> None:
    """Add some custom ini values.

    Args:
        parser: The pytest command line and ini file parser
            object.
    """
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
    """Determine if QGIS GUI debugging/interaction is enabled for the session.

    Args:
        request: The pytest _pytest.fixtures.FixtureRequest object.
        pytestconfig: The pytest _pytest.config.Config object.

    Yields:
        bool: True if GUI debugging is enabled, False otherwise.
    """
    plugin_settings = getattr(request.config, "_plugin_settings", None)
    if plugin_settings and hasattr(plugin_settings, "gui_enabled"):
        gui_enabled = plugin_settings.gui_enabled
    else:
        gui_enabled = False  # Safe default when pytest-qgis internals shift
    yield gui_enabled


@pytest.fixture
def pe_qgis_iface(qgis_iface):
    """
    Patch the pytest-qgis's qgis_iface to include some specific methods
    for the Planet Explorer plugin. Adds required mock methods to the
    standard QGIS interface fixture needed by the Planet Explorer plugin.

    Args:
        qgis_iface: The base QGIS interface fixture provided by pytest-qgis.

    Yields:
        MagicMock: The patched QGIS interface with mocked plugin methods.
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

    Args:
        pytestconfig: The pytest configuration object used to read ini settings.
        pe_qgis_iface: The patched QGIS interface fixture.
        qgis_parent: The parent QGIS main window widget.
        qgis_new_project: Fixture that ensures a fresh QGIS project state.

    Yields:
        PlanetExplorer: The initialized instance of the Planet Explorer plugin.

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
    """Retrieve and configure the plugin's toolbar for testing.

    Resizes the toolbar according to the project's configuration settings,
    handles conditional visibility for debugging, and registers the widget
    with qtbot for automated UI interactions.

    Args:
        pytestconfig: The pytest configuration object used to read ini settings.
        plugin: The initialized instance of the Planet Explorer plugin.
        qgis_debug_enabled: Boolean flag indicating if GUI debugging is active.
        qtbot: The pytest-qt bot instance for managing Qt widgets during tests.

    Yields:
        QToolBar: The configured and registered plugin toolbar widget.
    """
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
    """Provide a factory function to instantiate the explorer dock widget.

    This convenience fixture returns a callable that safely creates, configures,
    and registers the dock widget with qtbot. On teardown, it ensures the internal
    singleton reference is cleanly reset to prevent cross-test state leakage.

    Args:
        plugin: The initialized instance of the Planet Explorer plugin.
        plugin_toolbar: The configured plugin toolbar widget.
        qgis_debug_enabled: Boolean flag indicating if GUI debugging is active.
        qtbot: The pytest-qt bot instance for managing Qt widgets during tests.
        pe_qgis_iface: The patched QGIS interface fixture.

    Yields:
        callable: A factory function (`_get_widget`) that returns an initialized
            explorer dock widget instance when called.
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
    """Provide a factory function to instantiate an authenticated explorer dock widget.

    This convenience fixture returns a callable that safely creates, logs into,
    configures, and registers the dock widget with qtbot. On teardown, it ensures
    the internal singleton reference is cleanly reset to prevent cross-test state
    leakage.

    Args:
        plugin: The initialized instance of the Planet Explorer plugin.
        plugin_toolbar: The configured plugin toolbar widget.
        qgis_debug_enabled: Boolean flag indicating if GUI debugging is active.
        qtbot: The pytest-qt bot instance for managing Qt widgets during tests.
        pe_qgis_iface: The patched QGIS interface fixture.

    Yields:
        callable: A factory function (`_get_widget`) that returns an authenticated
            explorer dock widget instance when called.
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
    """Provide a factory function to instantiate the order monitor widget.

    This convenience fixture returns a callable that handles the creation,
    UI automation bot registration, and conditional display configuration
    for the plugin's order monitoring sub-panel. On teardown, it ensures
    the internal singleton instance is safely cleaned up.

    Args:
        qgis_debug_enabled: Boolean flag indicating if GUI debugging is active.
        qtbot: The pytest-qt bot instance for managing Qt widgets during tests.

    Yields:
        callable: A factory function (`_get_widget`) that accepts a parent
            explorer dock widget and returns an initialized order monitor widget.
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
    """Provide a factory function to instantiate the tasking order monitor widget.

    This convenience fixture returns a callable that handles the instantiation,
    Qt bot tracking, and dynamic visibility settings for the tasking panel.
    On teardown, it safely cleans up the internal singleton instance.

    Args:
        qgis_debug_enabled: Boolean flag indicating if GUI debugging is active.
        qtbot: The pytest-qt bot instance for managing Qt widgets during tests.

    Yields:
        callable: A factory function (`_get_widget`) that accepts a parent
            explorer dock widget and returns an initialized tasking widget.
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


def pytest_configure(config):
    # Prints the exact QGIS version being used at the start of the test session.
    try:
        from qgis.core import Qgis

        print(f"\n[QGIS VERSION CHECK] Running tests on QGIS Version: {Qgis.version()}")
    except ImportError:
        print("\n[QGIS VERSION CHECK] Failed to import qgis.core")
