import pytest
from qgis.PyQt import QtCore
from planet_explorer.gui.pe_open_saved_search_dialog import OpenSavedSearchDialog
from planet_explorer.gui.pe_save_search_dialog import SaveSearchDialog
from planet_explorer.tests.utils import qgis_debug_wait, get_random_string

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]


SAMPLE_AOI_SAVED_SEARCH_NAME = "QGIS Plugin Tests - Sample AOI"


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
    assert daily_images_widget._aoi_filter.leAOI.toPlainText() == sample_aoi


def test_create(qtbot, logged_in_explorer_dock_widget, qgis_debug_enabled, sample_aoi):
    """
    Verifies:
        - PLQGIS-TC08
    """
    dock_widget = logged_in_explorer_dock_widget()
    daily_images_widget = dock_widget.daily_images_widget
    saved_search_name = f"test-qgis-saved-search-{get_random_string()}"
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    # execute some search
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.keyClicks(daily_images_widget._aoi_filter.leAOI, sample_aoi)
    qgis_debug_wait(qtbot, qgis_debug_enabled)
    qtbot.mouseClick(daily_images_widget.btnSearch, QtCore.Qt.LeftButton)
    qgis_debug_wait(qtbot, qgis_debug_enabled)

    dlg = SaveSearchDialog(daily_images_widget._request)
    qtbot.add_widget(dlg)

    def _dlg_interact():
        # do stuff to save search
        qtbot.keyClicks(dlg.txtName, saved_search_name)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        # get the save button
        save_button = None
        for btn in dlg.buttonBox.buttons():
            if "Save" in btn.text():
                save_button = btn
                break
        # save the search
        qtbot.mouseClick(save_button, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

    QtCore.QTimer.singleShot(1000, _dlg_interact)
    daily_images_widget.searchResultsWidget._save_search(dlg=dlg)

    # Verify the search was created and delete it
    dlg = OpenSavedSearchDialog()
    qtbot.add_widget(dlg)

    def _dlg_interact():
        # verify the search was added to the list
        saved_searches = [
            dlg.comboSavedSearch.itemText(index)
            for index in range(dlg.comboSavedSearch.count())
        ]
        assert saved_search_name in saved_searches
        dlg.comboSavedSearch.setCurrentIndex(saved_searches.index(saved_search_name))
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        # delete the search
        qtbot.mouseClick(dlg.btnDelete, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        saved_searches = [
            dlg.comboSavedSearch.itemText(index)
            for index in range(dlg.comboSavedSearch.count())
        ]
        assert saved_search_name not in saved_searches

        qtbot.mouseClick(dlg.btnCancel, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

    QtCore.QTimer.singleShot(1000, _dlg_interact)
    daily_images_widget.open_saved_searches(dlg=dlg)
