# -*- coding: utf-8 -*-

from qgis.testing import unittest

class TestPlugin(unittest.TestCase):
    def test_import_planet(self):
        try:
            import planet  # noqa: F401
            assert True
        except ImportError:
            assert False

    '''
    def test_show_explorer(self):
        show_explorer()
    '''
