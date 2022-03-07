import pytest

from planet_explorer import classFactory
from qgis.PyQt import QtCore


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

    def dummy_method(*args, **kwargs):
        pass

    class DummyClass:
        pass

    for method in [
        "addPluginToWebMenu",
        "messageTimeout",
        "removePluginWebMenu",
        "removeDockWidget",
    ]:
        setattr(qgis_iface, method, dummy_method)

    qgis_iface.layerTreeView = DummyClass
    qgis_iface.layerTreeView.layerTreeModel = DummyClass
    qgis_iface.layerTreeView.layerTreeModel.refreshLayerLegend = dummy_method
    qgis_iface.layerTreeView.currentNode = DummyClass
    qgis_iface.layerTreeView.currentNode.setExpanded = dummy_method
    qgis_iface.messageTimeout.return_value = 5
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
def plugin_toolbar(pytestconfig, plugin, qgis_debug_enabled):
    toolbar = plugin.toolbar
    toolbar.resize(int(pytestconfig.getini("qgis_window_width")), 70)
    if qgis_debug_enabled:
        toolbar.show()
    yield toolbar


@pytest.fixture
def sample_aoi():
    yield (
        '{"coordinates":['
        "[[-0.334369,40.151264],[-0.276291,40.151264],[-0.276291,40.172081],"
        '[-0.334369,40.172081],[-0.334369,40.151264]]],"type":"Polygon"}'
    )
