# -*- coding: utf-8 -*-


from qgis.testing import unittest, start_app
from planet_explorer.gui.pe_explorer_dockwidget import (
    PlanetExplorerDockWidget
)
from planet_explorer.pe_utils import iface
from planet_explorer.tests.utils import patch_iface, get_testing_credentials
from planet_explorer.planet_api import PlanetClient
start_app()


class TestPlugin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch_iface()

    def setUp(self):
        self.dockwidget = PlanetExplorerDockWidget(iface.mainWindow())
        self.dockwidget._setup_client()
        PlanetClient.getInstance().log_out()

    def test_import_planet(self):
        try:
            import planet  # noqa: F401
            assert True
        except ImportError:
            assert False

    def test_explorer_login(self):
        self.dockwidget.chkBxSaveCreds.setChecked(False)
        current = self.dockwidget.stckdWidgetViews.currentIndex()
        assert current == 0
        user, password = get_testing_credentials()
        self.dockwidget.leUser.setText(user)
        self.dockwidget.lePass.setText(password)
        self.dockwidget.login()
        current = self.dockwidget.stckdWidgetViews.currentIndex()
        assert current == 1
        assert self.dockwidget.logged_in()

    def test_explorer_login_wrong_credentials(self):
        self.dockwidget.chkBxSaveCreds.setChecked(False)
        current = self.dockwidget.stckdWidgetViews.currentIndex()
        assert current == 0
        self.dockwidget.leUser.setText("user")
        self.dockwidget.lePass.setText("wrongpassword")
        self.dockwidget.login()
        current = self.dockwidget.stckdWidgetViews.currentIndex()
        assert current == 0

    def test_explorer_reacts_to_login(self):
        self.dockwidget.chkBxSaveCreds.setChecked(False)
        current = self.dockwidget.stckdWidgetViews.currentIndex()
        assert current == 0
        user, password = get_testing_credentials()
        PlanetClient.getInstance().log_in(user, password)
        current = self.dockwidget.stckdWidgetViews.currentIndex()
        assert current == 1
