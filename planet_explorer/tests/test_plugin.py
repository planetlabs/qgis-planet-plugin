# -*- coding: utf-8 -*-

from qgis import utils
from qgis.testing import start_app, unittest

from planet_explorer.gui.pe_explorer_dockwidget import (
    show_explorer,
)
from planet_explorer.tests import testinterface

start_app()

utils.iface = testinterface.iface


class TestPlugin(unittest.TestCase):
    def test_import_planet(self):
        try:
            import planet  # noqa: F401
            assert True
        except ImportError:
            assert False

    def test_show_explorer(self):
        show_explorer()
