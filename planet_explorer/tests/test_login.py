import pytest
import unittest

from qgis.PyQt import QtCore

from planet_explorer.tests.utils import qgis_debug_wait
from planet_explorer.tests.utils import get_testing_credentials

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]


TOOLBAR_BUTTONS = [
    "showdailyimages_act",
    "showbasemaps_act",
    "showinspector_act",
    "showorders_act",
    "showtasking_act",
    "user_button",
]


class TestExplorerLogin(unittest.TestCase):

    @pytest.mark.parametrize(
        "use_mouse", [True, False], ids=["Mouse Click", "Hit Enter"]
    )
    def test_explorer_login(
        self, qtbot, explorer_dock_widget, qgis_debug_enabled, use_mouse
    ):
        """
        Verifies:
            - PLQGIS-TC03
        """
        username, password = get_testing_credentials()
        dock_widget = explorer_dock_widget()

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
        self.assertEqual(current, 1)
        self.assertTrue(dock_widget.logged_in())

    @pytest.mark.qt_no_exception_capture
    def test_explorer_login_incorrect(
        self, qtbot, explorer_dock_widget, qgis_debug_enabled
    ):
        """
        As this is a negative test case, we do not capture exceptions.

        Verifies:
            - PLQGIS-TC03
        """
        dock_widget = explorer_dock_widget()

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget.leUser, "Iam")
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.keyClicks(dock_widget.lePass, "NotAUser")
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        qtbot.mouseClick(dock_widget.btn_ok, QtCore.Qt.LeftButton)

        current = dock_widget.stckdWidgetViews.currentIndex()
        self.assertEqual(current, 0)
        self.assertFalse(dock_widget.logged_in())

    def test_explorer_reacts_to_login(
        self, qtbot, explorer_dock_widget, qgis_debug_enabled
    ):
        """
        Verifies:
            - PLQGIS-TC03
        """
        dock_widget = explorer_dock_widget()
        current = dock_widget.stckdWidgetViews.currentIndex()
        self.assertEqual(current, 0)
        username, password = get_testing_credentials()
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        with qtbot.waitSignal(dock_widget.p_client.loginChanged):
            dock_widget.p_client.log_in(username, password)
        qgis_debug_wait(qtbot, qgis_debug_enabled)
        current = dock_widget.stckdWidgetViews.currentIndex()
        self.assertEqual(current, 1)

    def test_explorer_logout(
        self, qtbot, plugin, logged_in_explorer_dock_widget, qgis_debug_enabled
    ):
        """
        Unfortunately it is not possible to click the item in the QMenu, we can however trigger
        the event that would be emitted by a user click.

        cf. https://github.com/pytest-dev/pytest-qt/issues/195

        Verifies:
            - PLQGIS-TC20
        """
        dock_widget = logged_in_explorer_dock_widget()
        self.assertFalse(plugin.btnLogin.isVisible())
        # Verify things are enabled when logged in
        for btn in TOOLBAR_BUTTONS:
            self.assertTrue(getattr(plugin, btn).isEnabled())

        qgis_debug_wait(qtbot, qgis_debug_enabled)
        logout_action = plugin.user_button.menu().actions()[1]
        logout_action.trigger()
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        qtbot.waitUntil(lambda: not dock_widget.logged_in(), timeout=10 * 1000)

        if qgis_debug_enabled:
            self.assertTrue(plugin.btnLogin.isVisible())
        self.assertTrue(plugin.btnLogin.isEnabled())
        # Verify things are not enabled when logged out
        for btn in TOOLBAR_BUTTONS:
            self.assertFalse(getattr(plugin, btn).isEnabled())
