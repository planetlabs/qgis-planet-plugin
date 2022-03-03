# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_dockwidget.py
    ---------------------
    Date                 : August 2019
    Copyright            : (C) 2019 Planet Inc, https://planet.com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
__author__ = "Planet Federal"
__date__ = "August 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import logging
import os

from planet.api.filters import and_filter, or_filter, build_search_request
from qgis.core import Qgis, QgsApplication
from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSlot
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QVBoxLayout

from ..pe_analytics import (
    analytics_track,
    send_analytics_for_search,
    ITEM_IDS_COPIED,
    API_KEY_COPIED,
)

from ..pe_utils import add_menu_section_action
from ..planet_api import PlanetClient
from .pe_dailyimages_search_results_widget import DailyImagesSearchResultsWidget
from .pe_filters import PlanetDailyFilter, PlanetAOIFilter, filters_from_request
from .pe_orders import PlanetOrdersDialog
from .pe_show_curl_dialog import ShowCurlDialog
from .pe_legacy_warning_widget import LegacyWarningWidget
from .pe_open_saved_search_dialog import OpenSavedSearchDialog
from .pe_gui_utils import waitcursor

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get("PYTHON_LOG_VERBOSE", None)

plugin_path = os.path.split(os.path.dirname(__file__))[0]
WIDGET, BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "dailyimages_widget.ui"),
    from_imports=True,
    import_from=os.path.basename(plugin_path),
    resource_suffix="",
)

SEARCH_HIGHLIGHT = "QToolButton {color: rgb(16, 131, 138);}"


class DailyImagesWidget(BASE, WIDGET):
    def __init__(self, parent):
        super(DailyImagesWidget, self).__init__()
        self.parent = parent

        self.setupUi(self)

        self._setup_aoi_filter()

        self._setup_daily_filters_widget()

        self.btnFilterResults.clicked.connect(self.show_filters)
        self.btnBackFromFilters.clicked.connect(self.hide_filters)
        self.btnClearFilters.clicked.connect(self.clear_filters)

        self.searchResultsWidget = DailyImagesSearchResultsWidget()
        layout = QVBoxLayout()
        layout.setMargin(0)
        self.grpBoxResults.setLayout(layout)
        self.grpBoxResults.layout().addWidget(self.searchResultsWidget)
        self.searchResultsWidget.checkedCountChanged.connect(self._update_orders_button)
        self.searchResultsWidget.setAOIRequested.connect(self.set_aoi_from_request)

        layout = QVBoxLayout()
        layout.setMargin(0)
        self.legacyWarningWidget = LegacyWarningWidget()
        self.legacyWarningWidget.updateLegacySearch.connect(self.update_legacy_search)
        layout.addWidget(self.legacyWarningWidget)
        self.frameWarningLegacySearch.setLayout(layout)
        self.frameWarningLegacySearch.setVisible(False)

        self._toggle_search_highlight(True)
        self.btnSearch.clicked.connect(self.perform_search)

        self.labelSavedSearches.linkActivated.connect(self.open_saved_searches)

        # Collected sources/filters, upon search request
        self._sources = None
        self._filters = None
        self.local_filters = None
        self._request = None
        self.legacy_request = None
        self.current_saved_search = None

        self.btnOrder.clicked.connect(self.order_checked)
        self._setup_actions_button()

        self._checked_item_type_nodes = {}

        self.lblWarning.setHidden(True)

        self._collect_sources_filters()
        self._default_filter_values = build_search_request(self._filters, self._sources)

    def open_saved_searches(self):
        dlg = OpenSavedSearchDialog()
        if dlg.exec() == OpenSavedSearchDialog.Accepted:
            saved_search_request = dlg.saved_search
            request = {}
            if saved_search_request:
                if "filter" in saved_search_request:
                    request["filter"] = saved_search_request["filter"]
                if "item_types" in saved_search_request:
                    request["item_types"] = saved_search_request["item_types"]
                self.current_saved_search = saved_search_request
            self.set_filters_from_request(request)
            self.perform_search()
            self._aoi_filter.zoom_to_aoi()

    @waitcursor
    def update_legacy_search(self):
        if self.legacy_request is not None and self.current_saved_search is not None:
            self.legacy_request = None
            self._collect_sources_filters()
            request = build_search_request(self._filters, self._sources)
            request["name"] = self.current_saved_search["name"]
            PlanetClient.getInstance().update_search(
                request, self.current_saved_search["id"]
            )
            self.frameWarningLegacySearch.setVisible(False)
            self._daily_filters_widget.hide_legacy_search_elements()
            self.perform_search()
        else:
            self.legacy_request = None
            self.frameWarningLegacySearch.setVisible(False)
            self._daily_filters_widget.hide_legacy_search_elements()
            self._daily_filters_widget.clear_id_filter()
            self.clear_filters()

    def show_filters(self):
        self.stackedWidgetDailyImagery.setCurrentIndex(1)

    def hide_filters(self):
        self.stackedWidgetDailyImagery.setCurrentIndex(0)

    def clear_filters(self):
        self.set_filters_from_request(self._default_filter_values)

    @pyqtSlot(bool)
    def _toggle_search_highlight(self, on=True):
        if on:
            self.btnSearch.setStyleSheet(SEARCH_HIGHLIGHT)
            self.btnSearch.setIcon(QIcon(":/plugins/planet_explorer/search_p.svg"))
        else:
            self.btnSearch.setStyleSheet("")
            self.btnSearch.setIcon(QIcon(":/plugins/planet_explorer/search.svg"))

    def _update_orders_button(self, count):
        self.btnOrder.setText(f"Order ({count} items)")

    @pyqtSlot()
    def _collect_sources_filters(self):
        main_filters = self._aoi_filter.filters()
        if not main_filters:
            main_filters = []

        sources = self._daily_filters_widget.sources()

        item_filters, self.local_filters = self._daily_filters_widget.filters()
        if not item_filters:
            item_filters = []

        all_filters = main_filters + item_filters

        id_filters = [
            f for f in all_filters if "field_name" in f and f["field_name"] == "id"
        ]

        item_type_filters = []
        for item_type, assets in sources.items():
            if assets is not None:
                item_type_filter = {
                    "config": [
                        {"config": assets, "type": "AssetFilter"},
                        {
                            "config": [item_type],
                            "type": "StringInFilter",
                            "field_name": "item_type",
                        },
                    ],
                    "type": "AndFilter",
                }
            else:
                item_type_filter = {
                    "config": [item_type],
                    "type": "StringInFilter",
                    "field_name": "item_type",
                }
            item_type_filters.append(item_type_filter)

        all_filters.append(or_filter(*item_type_filters))

        if id_filters:
            all_filters = [id_filters[0]]

        self._filters = and_filter(*all_filters)
        self._sources = list(sources.keys())

    @pyqtSlot(bool)
    def perform_search(self, clicked=True):
        log.debug("Search initiated")

        # Remove highlight on search button
        self._toggle_search_highlight(False)

        if self.legacy_request is not None:
            search_request = self.legacy_request
            self.local_filters = []
            self.searchResultsWidget.update_request(search_request, self.local_filters)
            return

        self._collect_sources_filters()

        send_analytics_for_search(self._sources)

        if not self._aoi_filter.leAOI.text():
            id_filters = filters_from_request(self._filters, "id")
            if len(id_filters) == 0:
                self.lblWarning.setHidden(False)
                return

        self.lblWarning.setHidden(True)

        if not self._sources:
            self.parent.show_message(
                "No item types selected", level=Qgis.Warning, duration=10
            )
            return

        search_request = build_search_request(self._filters, self._sources)

        self._request = search_request

        self.searchResultsWidget.update_request(search_request, self.local_filters)

    def _setup_aoi_filter(self):
        self._aoi_filter = PlanetAOIFilter(
            parent=self.frameAOIFilter, plugin=self.parent
        )
        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self._aoi_filter)
        self.frameAOIFilter.setLayout(layout)
        self._aoi_filter.filtersChanged.connect(self._filters_have_changed)

    def _setup_daily_filters_widget(self):
        self._daily_filters_widget = PlanetDailyFilter(
            parent=self.widgetFilters, plugin=self.parent
        )
        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self._daily_filters_widget)
        self.widgetFilters.setLayout(layout)
        self._daily_filters_widget.updateLegacySearch.connect(self.update_legacy_search)
        self._daily_filters_widget.filtersChanged.connect(self._filters_have_changed)

    def _setup_actions_button(self):
        actions_menu = QMenu(self)

        add_menu_section_action("API", actions_menu)

        ids_act = QAction("Copy Selected IDs to clipboard", actions_menu)
        ids_act.triggered[bool].connect(self.copy_checked_ids)
        actions_menu.addAction(ids_act)

        api_act = QAction("Copy API Key to clipboard", actions_menu)
        api_act.triggered[bool].connect(self.copy_api_key)
        actions_menu.addAction(api_act)

        curl_act = QAction("View cURL Request", actions_menu)
        curl_act.triggered[bool].connect(self.view_curl)
        actions_menu.addAction(curl_act)

        self.btnActions.setMenu(actions_menu)

        # Also show menu on click, to keep disclosure triangle visible
        self.btnActions.clicked.connect(self.btnActions.showMenu)

    @pyqtSlot()
    def _filters_have_changed(self):
        """
        Main slot for when any filter value has changed.
        Planet API searches should not be initiated automatically on filter
        changes (i.e. here), but when the user clicks the search button.
        :return:
        """
        self._toggle_search_highlight(True)
        self._daily_filters_widget.hide_legacy_search_elements()
        self.frameWarningLegacySearch.setVisible(False)
        self.legacy_request = None
        log.debug("Filters have changed")

    @pyqtSlot(dict)
    def set_filters_from_request(self, request):
        if request is not None:
            self._daily_filters_widget.set_from_request(request)
            self._aoi_filter.set_from_request(request)
            sources = request["item_types"]
            legacy = "PSScene3Band" in sources or "PSScene4Band" in sources
            self.frameWarningLegacySearch.setVisible(legacy)
            has_image_id = bool(self._daily_filters_widget.leStringIDs.text())
            self.legacyWarningWidget.set_has_image_id(has_image_id)
            if has_image_id:
                self.current_saved_search = None
            if legacy:
                self.legacy_request = request
            else:
                self.legacy_request = None

    @pyqtSlot(dict)
    def set_aoi_from_request(self, request):
        if request is not None:
            self._aoi_filter.set_from_request(request)

    @pyqtSlot()
    def order_checked(self):
        log.debug("Order initiated")

        images = self.searchResultsWidget.selected_images()

        if not images:
            self.parent.show_message(
                "No checked items to order", level=Qgis.Warning, duration=10
            )
            return

        tool_resources = {}
        if self._aoi_filter.leAOI.text():
            tool_resources["aoi"] = self._aoi_filter.leAOI.text()
        else:
            tool_resources["aoi"] = None

        dlg = PlanetOrdersDialog(images, tool_resources=tool_resources)

        dlg.setMinimumWidth(700)
        dlg.setMinimumHeight(750)

        dlg.exec_()

    @pyqtSlot()
    def copy_checked_ids(self):
        selected = self.searchResultsWidget.selected_images()
        if not selected:
            self.parent.show_message(
                "No checked IDs to copy", level=Qgis.Warning, duration=10
            )
            return

        sorted_checked = sorted([img["id"] for img in selected])
        cb = QgsApplication.clipboard()
        cb.setText(",".join(sorted_checked))
        self.parent.show_message("Checked IDs copied to clipboard")
        analytics_track(ITEM_IDS_COPIED)

    @pyqtSlot()
    def view_curl(self):
        if self.searchResultsWidget.search_has_been_performed():
            request = self.searchResultsWidget.request_query()
            dlg = ShowCurlDialog(request)
            dlg.exec_()
        else:
            self.parent.show_message("No search has been performed", level=Qgis.Warning)

    @pyqtSlot()
    def copy_api_key(self):
        cb = QgsApplication.clipboard()
        cb.setText(PlanetClient.getInstance().api_key())
        self.parent.show_message("API key copied to clipboard")
        analytics_track(API_KEY_COPIED)

    def clean_up(self):
        self._aoi_filter.clean_up()
        if self.searchResultsWidget.search_has_been_performed():
            self.searchResultsWidget.clean_up()
