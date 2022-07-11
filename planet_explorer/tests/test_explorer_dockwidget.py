import pytest

from qgis.core import QgsProject
from qgis.PyQt import QtCore

from planet_explorer.gui import pe_explorer_dockwidget
from planet_explorer.tests.utils import qgis_debug_wait
from planet_explorer.tests.utils import get_testing_credentials
from planet_explorer.tests.utils import get_explorer_dockwidget

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]


TOOLBAR_BUTTONS = [
    "showdailyimages_act",
    "showbasemaps_act",
    "showinspector_act",
    "showorders_act",
    "showtasking_act",
    "user_button",
]


@pytest.fixture
def explorer_dock_widget(
    plugin, plugin_toolbar, qgis_debug_enabled, qtbot, pe_qgis_iface
):
    """
    Convenience fixture for instantiating the explorer dock widget
    """
    dock_widget = get_explorer_dockwidget(plugin_toolbar, login=False)
    qtbot.add_widget(dock_widget)
    # Show the widget if debug mode is enabled
    if qgis_debug_enabled:
        dock_widget.show()
    yield dock_widget
    # reset the dockwidget_instance at the end of the test (since it's cleaned up by qtbot)
    pe_explorer_dockwidget.dockwidget_instance = None


@pytest.fixture
def logged_in_explorer_dock_widget(
    plugin, plugin_toolbar, qgis_debug_enabled, qtbot, pe_qgis_iface
):
    """
    Convenience fixture for instantiating a logged in version of the explorer dock widget
    """
    dock_widget = get_explorer_dockwidget(plugin_toolbar, login=True)
    qtbot.add_widget(dock_widget)
    # Show the widget if debug mode is enabled
    if qgis_debug_enabled:
        dock_widget.show()
    yield dock_widget
    # reset the dockwidget_instance at the end of the test (since it's cleaned up by qtbot)
    pe_explorer_dockwidget.dockwidget_instance = None


@pytest.mark.parametrize("use_mouse", [True, False], ids=["Mouse Click", "Hit Enter"])
def test_explorer_login(qtbot, explorer_dock_widget, qgis_debug_enabled, use_mouse):
    """
    Verifies:
        - PLQGIS-TC03
    """
    username, password = get_testing_credentials()

    dock_widget = explorer_dock_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget.leUser, username)

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget.lePass, password)

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    if use_mouse:
        qtbot.mouseClick(dock_widget.btn_ok, QtCore.Qt.LeftButton)
    else:
        qtbot.keyClick(dock_widget.lePass, QtCore.Qt.Key_Enter)

    current = dock_widget.stckdWidgetViews.currentIndex()
    assert current == 1
    assert dock_widget.logged_in()


@pytest.mark.qt_no_exception_capture
def test_explorer_login_incorrect(qtbot, explorer_dock_widget, qgis_debug_enabled):
    """
    As this is a negative test case, we do not capture exceptions.

    Verifies:
        - PLQGIS-TC03
    """
    dock_widget = explorer_dock_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget.leUser, "Iam")

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget.lePass, "NotAUser")

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btn_ok, QtCore.Qt.LeftButton)

    current = dock_widget.stckdWidgetViews.currentIndex()
    assert current == 0
    assert not dock_widget.logged_in()


def test_explorer_reacts_to_login(qtbot, explorer_dock_widget, qgis_debug_enabled):
    """
    Verifies:
        - PLQGIS-TC03
    """
    dock_widget = explorer_dock_widget

    current = dock_widget.stckdWidgetViews.currentIndex()
    assert current == 0
    username, password = get_testing_credentials()
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    with qtbot.waitSignal(dock_widget.p_client.loginChanged):
        dock_widget.p_client.log_in(username, password)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    current = dock_widget.stckdWidgetViews.currentIndex()
    assert current == 1


def test_explorer_logout(
    qtbot, plugin, logged_in_explorer_dock_widget, qgis_debug_enabled
):
    """
    Unfortunately it is not possible to click the item in the QMenu, we can however trigger
    the event that would be emitted by a user click.

    cf. https://github.com/pytest-dev/pytest-qt/issues/195

    Verifies:
        - PLQGIS-TC20
    """
    assert not plugin.btnLogin.isVisible()
    # Verify things are enabled when logged in
    for btn in TOOLBAR_BUTTONS:
        assert getattr(plugin, btn).isEnabled()

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    logout_action = plugin.user_button.menu().actions()[1]
    logout_action.trigger()
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    qtbot.waitUntil(
        lambda: not logged_in_explorer_dock_widget.logged_in(), timeout=10 * 1000
    )

    if qgis_debug_enabled:
        assert plugin.btnLogin.isVisible()
    assert plugin.btnLogin.isEnabled()
    # Verify things are not enabled when logged out
    for btn in TOOLBAR_BUTTONS:
        assert not getattr(plugin, btn).isEnabled()


def test_explorer_search_daily_images(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, sample_aoi
):
    """
    Verifies:
        - PLQGIS-TC04
    """
    dock_widget = logged_in_explorer_dock_widget.daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, sample_aoi)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
    # just verify that at least some images are showing
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    assert dock_widget.searchResultsWidget.tree.topLevelItemCount() > 1
    images_found = int(
        dock_widget.searchResultsWidget.lblImageCount.text().split(" ")[0]
    )
    assert images_found > 1


def test_search_daily_images_wrong_aoi(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled
):
    """
    Verifies:
        - PLQGIS-TC04
    """
    dock_widget = logged_in_explorer_dock_widget.daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, "wrong AOI")
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)


def test_explorer_basemaps_shown(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled
):
    """
    Verifies:
        - PLQGIS-TC10
    """
    dock_widget = logged_in_explorer_dock_widget
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
    dock_widget = logged_in_explorer_dock_widget
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
