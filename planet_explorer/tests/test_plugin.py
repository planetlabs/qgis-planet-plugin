# -*- coding: utf-8 -*-

from qgis.testing import unittest, start_app
from planet_explorer.gui.pe_explorer_dockwidget import show_explorer

start_app()


class TestPlugin(unittest.TestCase):
    def test_import_planet(self):
        try:
            import planet  # noqa: F401
            assert True
        except ImportError:
            assert False

    def test_show_explorer(self):
        show_explorer()
