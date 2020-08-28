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
__author__ = 'Planet Federal'
__date__ = 'August 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'


import os
import logging

from collections import ChainMap
from operator import attrgetter

import analytics
import sentry_sdk

from qgis.PyQt import uic
from qgis.PyQt.QtCore import (
    pyqtSlot
)

from qgis.PyQt.QtGui import (
    QIcon
)
from qgis.PyQt.QtWidgets import (
    QMenu,
    QAction,
    QVBoxLayout
)

from qgis.core import (
    QgsApplication,
    Qgis
)

from qgis.utils import iface

from planet.api.filters import (
    and_filter,
    build_search_request
)

from .show_curl_dialog import (
    ShowCurlDialog
)

from ..planet_api import (
    PlanetClient
)

from .pe_orders_v2 import (
    PlanetOrdersDialog
)

from .pe_filters import (
    PlanetMainFilters,
    PlanetDailyFilter
)

from .pe_search_results import PlanetSearchResultsWidget

from ..pe_utils import (
    area_from_geojsons,
    add_menu_section_action,
    SETTINGS_NAMESPACE,
    is_segments_write_key_valid
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

plugin_path = os.path.split(os.path.dirname(__file__))[0]
WIDGET, BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'dailyimages_widget.ui'),
    from_imports=True, import_from=os.path.basename(plugin_path),
    resource_suffix=''
)

SEARCH_HIGHLIGHT = 'QToolButton {color: rgb(16, 131, 138);}'

class DailyImagesWidget(BASE, WIDGET):

    def __init__(self, parent):
        super(DailyImagesWidget, self).__init__()
        self.parent = parent

        self.p_client = PlanetClient.getInstance()

        self.setupUi(self)

        self._setup_main_filter()

        self._setup_daily_filters_widget()

        self.btnFilterResults.clicked.connect(self.show_filters)
        self.btnBackFromFilters.clicked.connect(self.hide_filters)
        self.btnClearFilters.clicked.connect(self.clear_filters)

        self.searchResultsWidget = PlanetSearchResultsWidget(
                iface=iface,
                api_key=self.p_client.api_key()
            )
        layout = QVBoxLayout()
        layout.setMargin(0)        
        self.grpBoxResults.setLayout(layout)
        self.grpBoxResults.layout().addWidget(self.searchResultsWidget)
        self.searchResultsWidget.checkedCountChanged.connect(self._update_checked_queue_set)
        self.searchResultsWidget.setAOIRequested.connect(self.set_aoi_from_request)
        #self.searchResultsWidget.zoomToAOIRequested.connect(self._prepare_for_zoom_to_search_aoi)
        self.searchResultsWidget.searchSaved.connect(self._search_saved)

        self._toggle_search_highlight(True)
        self.btnSearch.clicked[bool].connect(self.perform_search)

        # Collected sources/filters, upon search request
        self._sources = None
        self._filters = None
        self._request = None

        self.btnOrder.clicked.connect(self.order_checked)
        self._setup_actions_button()        

        self._checked_queue_set_count = 0
        self._checked_queue_set = set()
        self._checked_item_type_nodes = {}

        self.lblWarning.setText("")

        self._collect_sources_filters()
        self._default_filter_values = build_search_request(
                                self._filters, self._sources)

        
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
            self.btnSearch.setIcon(
                QIcon(':/plugins/planet_explorer/search_p.svg'))
        else:
            self.btnSearch.setStyleSheet('')
            self.btnSearch.setIcon(
                QIcon(':/plugins/planet_explorer/search.svg'))

    @pyqtSlot()
    def _update_checked_queue_set(self):
        tab_queues = []
        if self.searchResultsWidget.search_has_been_performed():            
            tab_queues.append(self.searchResultsWidget.checked_queue())

        # unique item_type:item_id key grouping set
        new_queue_set = set().union(*tab_queues)

        self._checked_queue_set = new_queue_set

        self._update_checked_queue_set_count()

    @pyqtSlot()
    def _update_checked_queue_set_count(self):
        self._checked_queue_set_count = len(self._checked_queue_set)

        self.btnOrder.setText(
            f'Order ({self._checked_queue_set_count} items)')

    # noinspection PyUnusedLocal
    @pyqtSlot()
    def _collect_sources_filters(self):
        main_filters = self._main_filters.filters()
        if not main_filters:
            main_filters = []

        self._sources = self._daily_filters_widget.sources()

        item_filters = self._daily_filters_widget.filters()
        if not item_filters:
            item_filters = []

        all_filters = main_filters + item_filters

        self._filters = and_filter(*all_filters)

        # TODO: Validate filters

    # noinspection PyUnusedLocal
    @pyqtSlot(bool)
    def perform_search(self, clicked=True):
        log.debug('Search initiated')

        # Remove highlight on search button
        self._toggle_search_highlight(False)

        self._collect_sources_filters()

        if not self._main_filters.leAOI.text():
            self.lblWarning.setText('⚠️ No area of interest (AOI) defined')
            return

        self.lblWarning.setText("")
        # TODO: Also validate GeoJSON prior to performing search

        search_request = build_search_request(
            self._filters, self._sources)

        self._request = search_request
        if is_segments_write_key_valid():
            analytics.track(self.p_client.user()["email"], 
                            "Daily images search executed", 
                            {"query": search_request})


        self.searchResultsWidget.update_request(search_request)

    def _setup_main_filter(self):
        """Main filters: AOI visual extent, date range and text"""
        self._main_filters = PlanetMainFilters(parent=self.grpBoxMainFilters,
                                               plugin=self.parent,
                                               iface=iface)
        self.grpBoxMainFilters.layout().addWidget(self._main_filters)
        self._main_filters.filtersChanged.connect(self._filters_have_changed)
        self._main_filters.savedSearchSelected.connect(self.set_filters_from_request)

    def _setup_daily_filters_widget(self):
        self._daily_filters_widget = \
             PlanetDailyFilter(
                parent=self.widgetFilters,
                plugin=self.parent
            )
        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self._daily_filters_widget)
        self.widgetFilters.setLayout(layout)                

    def _setup_actions_button(self):
        actions_menu = QMenu(self)

        add_menu_section_action('API', actions_menu)

        ids_act = QAction('Copy Selected IDs to clipboard', actions_menu)
        ids_act.triggered[bool].connect(self.copy_checked_ids)
        actions_menu.addAction(ids_act)


        api_act = QAction('Copy API Key to clipboard', actions_menu)
        api_act.triggered[bool].connect(self.copy_api_key)
        actions_menu.addAction(api_act)

        curl_act = QAction('View cURL Request', actions_menu)
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
        self._main_filters.null_out_saved_search()
        log.debug('Filters have changed')


    @pyqtSlot(dict)
    def set_filters_from_request(self, request):        
        self._daily_filters_widget.set_from_request(request)
        self._main_filters.set_from_request(request)

    @pyqtSlot(dict)
    def set_aoi_from_request(self, request):
        self._main_filters.set_from_request(request)        

    def _search_saved(self, request):
        self._main_filters.add_saved_search(request)
        
    def _collect_checked_nodes(self):
        tab_queues = []
        
        tab_queues.append(self.searchResultsWidget.checked_queue())

        # Per-tab checked_queue() are a 1-to-1 dict of {'item_type:id': node}

        # An item_type:id may be checked in trees across multiple tabs.
        # Use a ChainMap view to resolve dupes and for faster iteration;
        # because, although the nodes in each tree's model may be different
        # (e.g. index), the actual metadata and thumbnail are the same.
        # This means the earliest found item_type:id will be used regardless
        # of the which tabs it is checked in.
        tab_queue_chainmap = ChainMap(*tab_queues)

        # _checked_queue_set is a set of unique, checked item_type:item_id keys

        # A dict of {'item_type': [nodes]}
        self._checked_item_type_nodes.clear()

        for chkd_it_id in sorted(self._checked_queue_set, reverse=True):
            if ':' not in chkd_it_id:
                log.debug(f'Item type:id is not valid')
                continue
            it_type = chkd_it_id.split(':')[0]

            if it_type not in self._checked_item_type_nodes:
                self._checked_item_type_nodes[it_type] = []
            if chkd_it_id in tab_queue_chainmap:
                self._checked_item_type_nodes[it_type].append(
                    tab_queue_chainmap[chkd_it_id]
                )
            else:
                # This should not happen
                log.debug('Item type:id in checked queue, but NOT in any tab')

        # Now sort each item_type's node list by date acquired, descending,
        # even though tabs may have been sorted acquired|published, asc|desc
        for item_type in self._checked_item_type_nodes:
            self._checked_item_type_nodes[item_type].sort(
                key=attrgetter('_acquired'), reverse=True)

        # When using with {'item_type': set(nodes)}
        if LOG_VERBOSE:
            for it_id in self._checked_item_type_nodes:
                # Possibly super verbose output...
                nl = '\n'
                i_types = \
                    [n.item_id() for n in self._checked_item_type_nodes[it_id]]
                log.debug(f'\n  - {it_id}: '
                          f'{len(self._checked_item_type_nodes[it_id])}\n'
                          f'    - {"{0}    - ".format(nl).join(i_types)}')


    @pyqtSlot()
    def order_checked(self):
        log.debug('Order initiated')

        self._collect_checked_nodes()

        if not self._checked_item_type_nodes:
            self.parent.show_message(f'No checked items to order',
                              level=Qgis.Warning,
                              duration=10)
            return

        tool_resources = {}
        if self._main_filters.leAOI.text():
            tool_resources['aoi'] = self._main_filters.leAOI.text()
        else:
            tool_resources['aoi'] = None

        dlg = PlanetOrdersDialog(
            self._checked_item_type_nodes,
            p_client=self.p_client,
            tool_resources=tool_resources,
            parent=self,
            iface=iface,
        )

        dlg.setMinimumWidth(700)
        dlg.setMinimumHeight(750)

        dlg.exec_()

    @pyqtSlot()
    def copy_checked_ids(self):
        if not self._checked_queue_set:
            self.parent.show_message(f'No checked IDs to copy',
                              level=Qgis.Warning,
                              duration=10)
            return

        sorted_checked = sorted(self._checked_queue_set)
        cb = QgsApplication.clipboard()
        cb.setText(','.join(sorted_checked))
        self.parent.show_message('Checked IDs copied to clipboard')

    @pyqtSlot()
    def view_curl(self):
        if self.searchResultsWidget.search_has_been_performed():
            request = self.searchResultsWidget.request_query()
            dlg = ShowCurlDialog(request)
            dlg.exec_()
        else:
            self.parent.show_message('No search has been performed', level=Qgis.Warning)

    @pyqtSlot()
    def copy_api_key(self):
        cb = QgsApplication.clipboard()
        cb.setText(self.p_client.api_key())
        self.parent.show_message('API key copied to clipboard')


    def clean_up(self):
        self._main_filters.clean_up()
        if self.searchResultsWidget.search_has_been_performed():            
            self.searchResultsWidget.clean_up()
