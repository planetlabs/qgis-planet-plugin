import pytest

from qgis.PyQt import QtCore

from planet_explorer.gui.pe_open_saved_search_dialog import OpenSavedSearchDialog
from planet_explorer.tests.utils import qgis_debug_wait
from planet_explorer.tests.utils import get_testing_credentials


def test_saved_search(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi
):
    """
    Verifies:
        - PLQGIS-TC08
    """

    dock_widget = logged_in_explorer_dock_widget().daily_images_widget

    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(dock_widget._aoi_filter.leAOI, large_aoi)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(dock_widget.btnSearch, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    qtbot.mouseClick(dock_widget.open_saved_searches(), QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    saved_search_widget = dock_widget.open_saved_searches()
    qgis_debug_wait(qtbot, qgis_debug_enabled, wait=5000)
    OpenSavedSearchDialog.saved_search_selected(1)


    import pdb; pdb.set_trace()