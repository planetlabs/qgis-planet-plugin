import pytest

from qgis.PyQt import QtCore
from planet_explorer.gui.pe_open_saved_search_dialog import OpenSavedSearchDialog
from planet_explorer.gui.pe_saved_search_dialog import SaveSearchDialog
from planet_explorer.tests.utils import qgis_debug_wait

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]


SAMPLE_AOI_SAVED_SEARCH_NAME = "QGIS Plugin Tests - Sample AOI"


def test_create_saved_search(
    qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, large_aoi
):
    """
    Verifies:
        - PLQGIS-TC08
    """

    dock_widget = logged_in_explorer_dock_widget().daily_images_widget
    daily_images_widget = dock_widget.daily_images_widget
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    dlg = SaveSearchDialog()
    qtbot.add_widget(dlg)

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



def test_load(qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, sample_aoi):
    """
    Verifies:
        - PLQGIS-TC15
    """
    dock_widget = logged_in_explorer_dock_widget()
    daily_images_widget = dock_widget.daily_images_widget
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    dlg = OpenSavedSearchDialog()
    qtbot.add_widget(dlg)

    def _dlg_interact():
        # find the saved search corresponding to the sample AOI
        for index in range(dlg.comboSavedSearch.count()):
            if dlg.comboSavedSearch.itemText(index) == SAMPLE_AOI_SAVED_SEARCH_NAME:
                dlg.comboSavedSearch.setCurrentIndex(index)
                break
        qtbot.mouseClick(dlg.btnLoad, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

    QtCore.QTimer.singleShot(1000, _dlg_interact)
    daily_images_widget.open_saved_searches(dlg=dlg)

    # make sure the proper AOI from the saved search is loaded by checking the filter
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    assert daily_images_widget._aoi_filter.leAOI.text() == sample_aoi
