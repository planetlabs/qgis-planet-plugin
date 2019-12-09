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
# import json

from collections import ChainMap
from operator import attrgetter

import analytics
import sentry_sdk

from qgis.PyQt import uic
from qgis.PyQt.QtCore import (
    Qt,
    QUrl,
    pyqtSignal,
    pyqtSlot
)

from qgis.PyQt.QtGui import (
    QIcon,
    QDesktopServices,
)
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QStackedWidget,
    QLineEdit,
    QDialogButtonBox,
    QCheckBox,
    QToolButton,
    QMenu,
    QAction,
    QWidgetAction,
    QLabel,
    QTextBrowser,
    QComboBox,
    QTabWidget,
    QFrame,
)

from qgis.gui import (
    QgsMessageBar,
    QgsCollapsibleGroupBox
)
from qgis.core import (
    QgsApplication,
    Qgis,
    QgsAuthManager,
    QgsMessageLog
)

# from qgis.utils import iface

from qgiscommons2.settings import (
    pluginSetting,
    setPluginSetting
)

from planet.api.filters import (
    and_filter,
    build_search_request
)

# from ..gui.extent_maptool import ExtentMapTool

from .mosaics_widgets import(
    MosaicsListWidget,
    MosaicSeriesTreeWidget
)

from ..planet_api import (
    PlanetClient,
    API_KEY_DEFAULT,
    ITEM_GROUPS,
    LoginException,
)

from ..planet_api.p_specs import (
    RESOURCE_MOSAIC_SERIES,
    RESOURCE_SINGLE_MOSAICS,
    RESOURCE_DAILY,
)

from .pe_orders_v2 import (
    PlanetOrdersDialog
)

from .pe_orders_monitor_dialog import (
    PlanetOrdersMonitorDialog
)

from .pe_filters import (
    PlanetFilterMixin,
    PlanetMainFilters,
    # PlanetMosaicFilter,
    PlanetDailyFilter
)

from .pe_search_results import PlanetSearchResultsWidget

from ..pe_utils import (
    area_from_geojsons,
    add_menu_section_action,
    SETTINGS_NAMESPACE,
    open_orders_download_folder,
    is_sentry_dsn_valid,
    is_segments_write_key_valid
)

# from ..resources import resources

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

plugin_path = os.path.split(os.path.dirname(__file__))[0]
WIDGET, BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_dockwidget_base.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)

LOG_NAME = "PlanetExplorer"

AUTH_CREDS_KEY = 'pe_plugin_auth'
AUTH_SEP = '|||'
AUTH_STRING = '{user}{sep}{password}{sep}{api_key}'
SAVE_CREDS_KEY = 'saveCreds'
AUTO_RECOVER_VALUES = 'recoverSearchValues'

EXT_LINK = ':/plugins/planet_explorer/external-link.svg'
PLANET_COM = 'https://planet.com'
# TODO: This needs a more general, non-temporal link
SAT_SPECS_PDF = 'https://assets.planet.com/docs/' \
                'Planet_Combined_Imagery_Product_Specs_letter_screen.pdf'
PLANET_SUPPORT_COMMUNITY = 'https://support.planet.com'
PLANET_EXPLORER = f'{PLANET_COM}/explorer'

BASE_URL = 'https://www.planet.com'
SIGNUP_URL = f'{BASE_URL}/contact'
TOS_URL = 'https://learn.planet.com/QGIS-terms-conditions.html'
FORGOT_PASS_URL = f'{BASE_URL}/login?mode=reset-password'
ACCOUNT_URL = f'{BASE_URL}/account'
SEARCH_HIGHLIGHT = 'QToolButton {color: rgb(16, 131, 138);}'

# ITEM_GROUPS[0]['filter_widget'] = PlanetMosaicFilter
ITEM_GROUPS[0]['filter_widget'] = PlanetDailyFilter

RESULTS_BKGRD = """\
QFrame#frameResults {{
    background-color: rgba(255, 255, 255, 200);
    {0}
}}"""
RESULTS_BKGRD_WHITE = RESULTS_BKGRD.format('')
RESULTS_BKGRD_PE = RESULTS_BKGRD.format(
    'image: url(:/plugins/planet_explorer/planet-explorer-inkscape.svg);')


# noinspection PyPep8Naming,PyUnresolvedReferences
class PlanetExplorerDockWidget(BASE, WIDGET):
    BASE: QDockWidget
    _auth_man: QgsAuthManager
    msgBar: QgsMessageBar
    stckdWidgetViews: QStackedWidget
    stckdWidgetResourceType: QStackedWidget
    leUser: QLineEdit
    lePass: QLineEdit
    leMosaicName: QLineEdit
    chkBxSaveCreds: QCheckBox
    lblSignUp: QLabel
    lblTermsOfService: QLabel
    lblForgotPass: QLabel
    cmbBoxItemGroupType: QComboBox
    btnSearch: QToolButton
    grpBoxMainFilters: QgsCollapsibleGroupBox
    grpBoxSeries: QgsCollapsibleGroupBox
    _main_filters: PlanetMainFilters
    grpBoxFilters: QgsCollapsibleGroupBox
    stckdWidgetFilters: QStackedWidget
    frameResults: QFrame
    tabWidgetResults: QTabWidget
    btnOrder: QToolButton
    btnCog: QToolButton
    btnInfo: QToolButton
    btnUser: QToolButton
    _user_act: QWidgetAction
    _terms_browser: QTextBrowser

    closingPlugin = pyqtSignal()

    def __init__(self, parent=None, iface=None, visible=False):
        super(PlanetExplorerDockWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://doc.qt.io/qt-5/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
        self.setVisible(visible)

        self._iface = iface
        # noinspection PyArgumentList
        self._auth_man = QgsApplication.authManager()

        self.p_client = None
        self.api_key = None
        self._save_creds = bool(pluginSetting(
            SAVE_CREDS_KEY, namespace=SETTINGS_NAMESPACE, typ='bool'))

        self.leUser.addAction(
            QIcon(':/plugins/planet_explorer/envelope-gray.svg'),
            QLineEdit.LeadingPosition
        )

        self.lblSignUp.linkActivated[str].connect(
            lambda: self._open_link_with_browser(SIGNUP_URL))
        self.lblTermsOfService.linkActivated[str].connect(
            lambda: self._open_link_with_browser(TOS_URL))
        self.lblForgotPass.linkActivated[str].connect(
            lambda: self._open_link_with_browser(FORGOT_PASS_URL))

        self.btn_ok = self.buttonBoxLogin.button(QDialogButtonBox.Ok)
        self.btn_ok.setText('Sign In')
        self.btn_api_key = self.buttonBoxLogin.button(QDialogButtonBox.Abort)
        """:type: QPushButton"""
        self.btn_api_key.setText('Use API key')
        self.btn_api_key.hide()
        self.buttonBoxLogin.accepted.connect(self.login)
        self.buttonBoxLogin.rejected.connect(self.api_key_login)

        self._setup_group_type_selector()

        self.cmbBoxItemGroupType.currentIndexChanged[int].connect(
            self._item_group_changed)

        self._toggle_search_highlight(True)
        self.btnSearch.clicked[bool].connect(self.perform_search)

        # Collected sources/filters, upon search request
        self._sources = None
        self._sort_order = None
        self._filters = None
        self._request = None

        # Set up the mosaics widget
        self._setup_mosaics_panel()
        
        # Set up AOI, date-range and text filters
        self._setup_main_filters()

        # Non-main, per-item-group control widget filters
        self._filter_widget_registry = {}
        self._setup_filter_widgets()

        # Set default group type and filter widget
        self.cmbBoxItemGroupType.setCurrentIndex(0)
        self.stckdWidgetFilters.setCurrentIndex(0)

        # Set up tabbed widget
        self.tabWidgetResults.tabCloseRequested[int].connect(
            self.tab_close_requested)

        # Set up lower button bar
        self.btnOrder.clicked.connect(self.order_checked)
        self._setup_cog_button()
        # noinspection PyTypeChecker
        self._user_act = None

        # noinspection PyTypeChecker
        self._terms_browser = None
        self._setup_info_button()

        self.msg_log = QgsMessageLog()
        # Local QgsMessageBar
        self.msgBar.hide()

        self.frameResults.setStyleSheet(RESULTS_BKGRD_PE)

        self._checked_queue_set_count = 0
        self._checked_queue_set = set()
        self._checked_item_type_nodes = {}

    # noinspection PyUnusedLocal
    def showEvent(self, event):
        if self.logged_in():
            self.stckdWidgetViews.setCurrentIndex(1)
        else:
            self._setup_client()

    def _setup_client(self):
        # Init api client
        self.p_client = PlanetClient.getInstance()
        self.p_client.register_area_km_func(area_from_geojsons)
        self.p_client.loginChanged[bool].connect(self.login_changed)        

        # Retrieve any login/key settings
        self.switch_to_login_panel()
        if not self.logged_in():
            self.api_key = API_KEY_DEFAULT
            self._set_credential_fields()
                # self.btn_api_key.setEnabled(bool(self.api_key))
            self.chkBxSaveCreds.stateChanged.connect(
                self.save_credentials_changed)

        self._setup_user_button()

        # Skip login panel if an API key was retrieved/accepted by client
        # self.login_changed()

    def logged_in(self):
        return self.p_client is not None and self.p_client.has_api_key()

    @pyqtSlot()
    def api_key_login(self):
        if self.api_key:
            self.login(api_key=self.api_key)

            # Now switch panels
            self.login_changed()

    @pyqtSlot()
    def login(self, api_key=None):
        if self.logged_in():
            return

        # Do login, push any error to message bar
        try:
            # Don't switch panels just yet
            self.p_client.blockSignals(True)
            self.p_client.log_in(
                self.leUser.text(), self.lePass.text(), api_key=api_key)
            self.p_client.blockSignals(False)
        except LoginException as e:
            self.show_message('Login failed!', show_more=str(e.__cause__),
                              level=Qgis.Warning)
            # Stay on login panel if error
            return

        # Login OK
        self.api_key = self.p_client.api_key()

        user = self.p_client.user()
        if is_segments_write_key_valid():
            analytics.identify(user["email"],
                                {
                                "email": user["email"],
                                "apiKey": user["api_key"],
                                "organizationId": user["organization_id"],
                                "programId": user["program_id"]
                                }
            )
            analytics.track(user["email"], "Log in to Explorer")
        if is_sentry_dsn_valid():
            with sentry_sdk.configure_scope() as scope:
                scope.user = {"email": user["email"]}

        # Store settings
        if self.chkBxSaveCreds.isChecked():
            self._store_auth_creds()

        # For debugging
        specs = f'logged_in={self.logged_in()}\n\n' \
            f'api_key = {self.p_client.api_key()}\n\n' \
            f'user: {self.p_client.user()}\n\n'
        log.debug(f'Login successful:\n{specs}')

        # Now switch panels
        self.p_client.loginChanged.emit(self.p_client.has_api_key())
        #self.login_changed()

    @pyqtSlot()
    def logout(self):
        if not self.logged_in():
            return
        # Do logout (switches to Login panel)
        self.p_client.log_out()
        # self.btn_api_key.setEnabled(bool(self.api_key))
        log.debug('User logged out')

    @pyqtSlot()
    def login_changed(self):
        user_name = 'User'
        if self.logged_in():
            p_user = self.p_client.user()
            if p_user and 'user_name' in p_user:
                user_name = p_user['user_name']
            self.lePass.setText("")
            self.leUser.setText("")
            self.switch_to_browse_panel()
        else:
            self._set_credential_fields()
            self.switch_to_login_panel()

        self._user_act.defaultWidget().setText(f"<b>{user_name}</b>")

    @pyqtSlot()
    def switch_to_login_panel(self):
        self.stckdWidgetViews.setCurrentIndex(0)

    @pyqtSlot()
    def switch_to_browse_panel(self):
        self.stckdWidgetViews.setCurrentIndex(1)

    def switch_to_daily_images_panel(self):
        self.stckdWidgetResourceType.setCurrentIndex(0)

    def switch_to_mosaic_series_panel(self):
        self.stckdWidgetResourceType.setCurrentIndex(1)

    def switch_to_single_mosaics_panel(self):
        self.stckdWidgetResourceType.setCurrentIndex(2)        

    @pyqtSlot(int)
    def _item_group_changed(self, indx):
        self.stckdWidgetResourceType.setCurrentIndex(indx)
        
        resource_type = self.cmbBoxItemGroupType.currentData()
        self.btnSearch.setEnabled(resource_type != RESOURCE_MOSAIC_SERIES)
        self.btnOrder.setVisible(resource_type == RESOURCE_DAILY)
        self.btnCog.setVisible(resource_type == RESOURCE_DAILY)
        if resource_type == RESOURCE_MOSAIC_SERIES:
            self.treeMosaicSeries.populate()
        elif resource_type == RESOURCE_SINGLE_MOSAICS:
            self.listSingleMosaics.populate_with_first_page()

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
        for i in range(self.tabWidgetResults.count()):
            # noinspection PyTypeChecker
            wdgt: PlanetSearchResultsWidget = self.tabWidgetResults.widget(i)
            tab_queues.append(wdgt.checked_queue())

        # unique item_type:item_id key grouping set
        new_queue_set = set().union(*tab_queues)

        # When using with {'item_type': set(nodes)}
        # new_queue_set = {}
        # tab_keys = set().union(*tab_queues)
        # for tk in tab_keys:
        #     new_queue_set[tk] = set()
        #
        # for tq in tab_queues:
        #     for tk in tq.keys():
        #         new_queue_set[tk] = new_queue_set[tk].union(tq[tk])

        self._checked_queue_set = new_queue_set

        self._update_checked_queue_set_count()

    @pyqtSlot()
    def _update_checked_queue_set_count(self):
        # self._checked_queue_set_count = \
        #     sum([len(n) for n in self._checked_queue_set.values()])

        self._checked_queue_set_count = len(self._checked_queue_set)

        self.btnOrder.setText(
            f'Order ({self._checked_queue_set_count} unique)')

    # noinspection PyUnusedLocal
    @pyqtSlot()
    def _collect_sources_filters(self):
        main_filters = self._main_filters.filters()
        if not main_filters:
            main_filters = []
        # main_filters_json = self._main_filters.filters_as_json()

        group_filters: PlanetFilterMixin = \
            self._filter_widget(self.cmbBoxItemGroupType.currentIndex())

        self._sources = group_filters.sources()

        self._sort_order = group_filters.sort_order()

        item_filters = group_filters.filters()
        if not item_filters:
            item_filters = []
        # item_filters_json = item_filters.filters_as_json()

        all_filters = main_filters + item_filters

        # Merge main and item filters
        self._filters = and_filter(*all_filters)

        # TODO: Validate filters

    # noinspection PyUnusedLocal
    @pyqtSlot(bool)
    def perform_search(self, clicked=True):
        log.debug('Search initiated')

        # Remove highlight on search button
        self._toggle_search_highlight(False)

        resource_type = self.cmbBoxItemGroupType.currentData()

        if resource_type == RESOURCE_DAILY:

            self._collect_sources_filters()

            if not self._main_filters.leAOI.text():
                self.show_message('No area of interest (AOI) defined',
                                  level=Qgis.Warning,
                                  duration=10)
                return
            # TODO: Also validate GeoJSON prior to performing search

            # TODO: replace hardcoded item type with dynamic item types
            search_request = build_search_request(
                self._filters, self._sources)

            self._request = search_request
            if is_segments_write_key_valid():
                analytics.track(self.p_client.user()["email"], 
                                "Daily images search executed", 
                                {"query": search_request})

            # self.msg_log.logMessage(
            #     f"Request:\n" \
            #     f"<pre>{json.dumps(self._request, indent=2)}</pre>",
            #     LOG_NAME)

            # Create new results tab, in results tab viewer, passing in request
            wdgt = PlanetSearchResultsWidget(
                parent=self.tabWidgetResults,
                iface=self._iface,
                api_key=self.api_key,
                request_type=resource_type,
                request=search_request,
                sort_order=self._sort_order,
            )
            wdgt.checkedCountChanged.connect(self._update_checked_queue_set)
            wdgt.setAOIRequested.connect(self.set_aoi_from_request)
            wdgt.setSearchParamsRequested.connect(self.set_search_params_from_request)
            wdgt.zoomToAOIRequested.connect(self._prepare_for_zoom_to_search_aoi)

            self.frameResults.setStyleSheet(RESULTS_BKGRD_WHITE)

            self.tabWidgetResults.setUpdatesEnabled(False)
            self.tabWidgetResults.addTab(wdgt, 'Daily')
            self.tabWidgetResults.setUpdatesEnabled(True)
            self.tabWidgetResults.setCurrentWidget(wdgt)

            # search_results = self.p_client.quick_search(search_request)

        if resource_type == RESOURCE_SINGLE_MOSAICS:
            search_text = self.leMosaicName.text()
            if is_segments_write_key_valid():
                analytics.track(self.p_client.user()["email"], 
                                "Mosaics search executed", 
                                {"text": search_text})
            self.listSingleMosaics.populate(search_text)

    @pyqtSlot(dict, tuple)
    def set_search_params_from_request(self, request, sort_order):
        for filter_widget in self._filter_widget_registry.values():
            filter_widget.set_from_request(request)
            filter_widget.set_sort_order(sort_order)
        self._main_filters.set_from_request(request)

    @pyqtSlot(dict)
    def set_aoi_from_request(self, request):
        self._main_filters.set_from_request(request)

    @pyqtSlot()
    def _prepare_for_zoom_to_search_aoi(self):
        active = self.tabWidgetResults.currentIndex()
        for i in range(self.tabWidgetResults.count()):
            if i != active:
                wdgt = self.tabWidgetResults.widget(i)
                wdgt.clear_aoi_box()
        wdgt = self.tabWidgetResults.widget(active)
        self._main_filters.hide_aoi_if_matches_geom(wdgt.aoi_geom())

    @pyqtSlot()
    def _prepare_for_zoom_to_main_aoi(self):        
        wdgt = self.tabWidgetResults.widget(self.tabWidgetResults.currentIndex())
        if wdgt:
            wdgt.hide_aoi_if_matches_geom(self._main_filters.aoi_geom())
        

    @pyqtSlot(int)
    def tab_close_requested(self, indx):

        wdgt: Optional[PlanetSearchResultsWidget] = \
            self.tabWidgetResults.widget(indx)

        if wdgt and hasattr(wdgt, 'clean_up'):
            wdgt.clean_up()

        self.tabWidgetResults.removeTab(indx)

        self._update_checked_queue_set()

        if self.tabWidgetResults.count() == 0:
            self.frameResults.setStyleSheet(RESULTS_BKGRD_PE)

    def _collect_checked_nodes(self):
        tab_queues = []
        for i in range(self.tabWidgetResults.count()):
            # noinspection PyTypeChecker
            wdgt: PlanetSearchResultsWidget = self.tabWidgetResults.widget(i)
            tab_queues.append(wdgt.checked_queue())

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
    def show_orders_monitor_dialog(self):
        dlg = PlanetOrdersMonitorDialog(
            p_client=self.p_client,
            parent = self
        )
        #dlg.setMinimumWidth(700)
        dlg.setMinimumHeight(750)

        dlg.exec_()

    @pyqtSlot()
    def order_checked(self):
        log.debug('Order initiated')

        self._collect_checked_nodes()

        if not self._checked_item_type_nodes:
            self.show_message(f'No checked items to order',
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
            iface=self._iface,
        )

        dlg.setMinimumWidth(700)
        dlg.setMinimumHeight(750)

        dlg.exec_()

    @pyqtSlot()
    def add_preview_layer(self):
        # TODO: Once checked IDs are avaiable
        log.debug('Preview layer added to map')

    @pyqtSlot()
    def copy_checked_ids(self):
        if not self._checked_queue_set:
            self.show_message('No checked IDs to copy',
                              level=Qgis.Warning,
                              duration=10)
            return

        sorted_checked = sorted(self._checked_queue_set)
        cb = QgsApplication.clipboard()
        cb.setText(','.join(sorted_checked))
        self.show_message('Checked IDs copied to clipboard')

    @pyqtSlot()
    def copy_curl(self):
        # TODO: Once checked IDs are avaiable
        self.show_message('cURL command copied to clipboard')

    @pyqtSlot()
    def copy_api_key(self):
        cb = QgsApplication.clipboard()
        cb.setText(self.p_client.api_key())
        self.show_message('API key copied to clipboard')

    def _setup_mosaics_panel(self):
        self.treeMosaicSeries = MosaicSeriesTreeWidget(self)
        self.grpBoxSeries.layout().addWidget(self.treeMosaicSeries)
        self.listSingleMosaics = MosaicsListWidget(self)
        self.grpBoxSingleMosaics.layout().addWidget(self.listSingleMosaics)
        self.leMosaicName.textChanged.connect(self._filters_have_changed)

    def _setup_group_type_selector(self):
        self.cmbBoxItemGroupType.clear()
        for i in range(len(ITEM_GROUPS)):
            self.cmbBoxItemGroupType.insertItem(
                i, ITEM_GROUPS[i]['display_name'],
                userData=ITEM_GROUPS[i]['resource_type'])

    def _setup_main_filters(self):
        """Main filters: AOI visual extent, date range and text"""
        self._main_filters = PlanetMainFilters(parent=self.grpBoxMainFilters,
                                               plugin=self,
                                               iface=self._iface)
        self.grpBoxMainFilters.layout().addWidget(self._main_filters)
        self._main_filters.filtersChanged.connect(self._filters_have_changed)
        self._main_filters.zoomToAOIRequested.connect(self._prepare_for_zoom_to_main_aoi)

    def _setup_filter_widgets(self):
        """Filters related to item groups"""
        for i in range(len(ITEM_GROUPS)):
            wdgt = ITEM_GROUPS[i]['filter_widget']
            if wdgt is not None:
                self._filter_widget_registry[i] = \
                    wdgt(
                        parent=self.stckdWidgetFilters,
                        plugin=self
                    )
                self._filter_widget(i).filtersChanged.connect(
                    self._filters_have_changed)
                self.stckdWidgetFilters.addWidget(self._filter_widget(i))

    def _filter_widget(self, indx):
        if indx in self._filter_widget_registry:
            return self._filter_widget_registry[indx]
        else:
            log.debug('Item group type filter widget not found')

    def _setup_cog_button(self):
        cog_menu = QMenu(self)

        # add_menu_section_action('Previews', cog_menu)
        #
        # add_prev_act = QAction('Add preview layer with checked',
        #                        cog_menu)
        # add_prev_act.triggered[bool].connect(self.add_preview_layer)
        # cog_menu.addAction(add_prev_act)

        add_menu_section_action('API', cog_menu)

        copy_menu = cog_menu.addMenu('Copy to clipboard')

        ids_act = QAction('Checked item IDs', cog_menu)
        ids_act.triggered[bool].connect(self.copy_checked_ids)
        copy_menu.addAction(ids_act)

        # curl_act = QAction('cURL command', cog_menu)
        # curl_act.triggered[bool].connect(self.copy_curl)
        # copy_menu.addAction(curl_act)

        api_act = QAction('API key', cog_menu)
        api_act.triggered[bool].connect(self.copy_api_key)
        copy_menu.addAction(api_act)

        self.btnCog.setMenu(cog_menu)

        # Also show menu on click, to keep disclosure triangle visible
        self.btnCog.clicked.connect(self.btnCog.showMenu)

    def _setup_info_button(self):
        info_menu = QMenu(self)

        self._p_sec_act = add_menu_section_action('Planet', info_menu)

        p_com_act = QAction(QIcon(EXT_LINK),
                            'planet.com', info_menu)
        p_com_act.triggered[bool].connect(
            lambda: self._open_link_with_browser(PLANET_COM)
        )
        info_menu.addAction(p_com_act)

        p_explorer_act = QAction(QIcon(EXT_LINK),
                                 'Planet Explorer web app', info_menu)
        p_explorer_act.triggered[bool].connect(
            lambda: self._open_link_with_browser(PLANET_EXPLORER)
        )
        info_menu.addAction(p_explorer_act)

        p_sat_act = QAction(QIcon(EXT_LINK),
                            'Satellite specs PDF', info_menu)
        p_sat_act.triggered[bool].connect(
            lambda: self._open_link_with_browser(SAT_SPECS_PDF)
        )
        info_menu.addAction(p_sat_act)

        p_support_act = QAction(QIcon(EXT_LINK),
                                'Support Community', info_menu)
        p_support_act.triggered[bool].connect(
            lambda: self._open_link_with_browser(PLANET_SUPPORT_COMMUNITY)
        )
        info_menu.addAction(p_support_act)

        self._info_act = add_menu_section_action('Documentation', info_menu)

        terms_act = QAction('Terms', info_menu)
        terms_act.triggered[bool].connect(self._show_terms)
        info_menu.addAction(terms_act)

        self.btnInfo.setMenu(info_menu)

        # Also show menu on click, to keep disclosure triangle visible
        self.btnInfo.clicked.connect(self.btnInfo.showMenu)

    def _setup_user_button(self):
        user_menu = QMenu(self)

        # user_menu.aboutToShow.connect(self.p_client.update_user_quota)

        self._user_act = add_menu_section_action('User', user_menu)

        acct_act = QAction(QIcon(EXT_LINK),
                           'Account', user_menu)
        acct_act.triggered[bool].connect(
            lambda: self._open_link_with_browser(ACCOUNT_URL)
        )
        user_menu.addAction(acct_act)

        # quota_menu = user_menu.addMenu('Quota (sqkm)')
        # quota_menu.addAction(
        #     f'Enabled: {str(self.p_client.user_quota_enabled())}')
        # quota_menu.addAction(
        #     f'Size: {str(self.p_client.user_quota_size())}')
        # quota_menu.addAction(
        #     f'Used: {str(self.p_client.user_quota_used())}')
        # quota_menu.addAction(
        #     f'Remaining: {str(self.p_client.user_quota_remaining())}')

        # quota_act.setMenu(quota_menu)
        # user_menu.addAction(quota_act)

        logout_act = QAction('Logout', user_menu)
        logout_act.triggered[bool].connect(self.logout)
        user_menu.addAction(logout_act)

        add_menu_section_action('Orders', user_menu)
        
        monitor_orders_act = QAction('Monitor orders',
                                    user_menu)
        monitor_orders_act.triggered[bool].connect(self.show_orders_monitor_dialog)
        user_menu.addAction(monitor_orders_act)

        open_orders_folder_act = QAction('Open orders folder',
                                    user_menu)
        open_orders_folder_act.triggered[bool].connect(open_orders_download_folder)
        user_menu.addAction(open_orders_folder_act)


        self.btnUser.setMenu(user_menu)

        # Also show menu on click, to keep disclosure triangle visible
        self.btnUser.clicked.connect(self.btnUser.showMenu)

    @pyqtSlot()
    def _filters_have_changed(self):
        """
        Main slot for when any filter value has changed.
        Planet API searches should not be initiated automatically on filter
        changes (i.e. here), but when the user clicks the search button.
        :return:
        """
        self._toggle_search_highlight(True)
        log.debug('Filters have changed')
        # TODO: Fix signal-triggered collection of filters
        # self._collect_sources_filters()

    @pyqtSlot('QString', str, 'PyQt_PyObject', 'PyQt_PyObject')
    def _passthru_message(self, msg, level, duration, show_more):
        if level == 'Warning':
            qgis_level = Qgis.Warning
        elif level == 'Critical':
            qgis_level = Qgis.Critical
        elif level == 'Success':
            qgis_level = Qgis.Success
        else:  # default
            qgis_level = Qgis.Info
        self.show_message(msg, level=qgis_level,
                          duration=duration, show_more=show_more)

    def show_message(self, message, level=Qgis.Info,
                     duration=None, show_more=None):
        """Skips bold title, i.e. sets first param (below) to empty string"""
        if duration is None:
            duration = self._iface.messageTimeout()

        if show_more is not None:
            self.msgBar.pushMessage(
                '',
                message,
                show_more,
                level,
                duration)
        else:
            self.msgBar.pushMessage(
                '',
                message,
                level,
                duration)

    @pyqtSlot(int)
    def save_credentials_changed(self, state):
        if state == 0:
            self._remove_auth_creds()
        self._save_creds = state > 0
        setPluginSetting(SAVE_CREDS_KEY, self._save_creds,
                         namespace=SETTINGS_NAMESPACE)

    def _store_auth_creds(self):
        auth_creds_str = AUTH_STRING.format(
            user=self.leUser.text(),
            password=self.lePass.text(),
            api_key=self.p_client.api_key(),
            sep=AUTH_SEP
        )
        self._auth_man.storeAuthSetting(
            AUTH_CREDS_KEY, auth_creds_str, True)

    def _retrieve_auth_creds(self):
        auth_creds_str = self._auth_man.authSetting(
            AUTH_CREDS_KEY, defaultValue='', decrypt=True)
        creds = auth_creds_str.split(AUTH_SEP)
        return {
            'user': creds[0] if len(creds) > 0 else None,
            'password': creds[1] if len(creds) > 1 else None,
            'api_key': creds[2] if len(creds) > 2 else None
        }

    def _set_credential_fields(self):
        self.lePass.setPasswordVisibility(False)
        if not self._save_creds:
            self.chkBxSaveCreds.setChecked(False)
        else:
            self.chkBxSaveCreds.setChecked(True)
            auth_creds = self._retrieve_auth_creds()
            self.leUser.setText(auth_creds['user'])
            self.lePass.setText(auth_creds['password'])
            self.api_key = auth_creds['api_key']

    def _remove_auth_creds(self):
        if not self._auth_man.removeAuthSetting(AUTH_CREDS_KEY):
            self.show_message(
                              'Credentials setting removal failed',
                              level=Qgis.Warning,
                              duration=10)

    # noinspection PyUnusedLocal
    @pyqtSlot(bool)
    def _show_terms(self, _):
        if self._terms_browser is None:
            self._terms_browser = QTextBrowser()
            self._terms_browser.setReadOnly(True)
            self._terms_browser.setOpenExternalLinks(True)
            self._terms_browser.setMinimumSize(600, 700)
            # TODO: Template terms.html first section, per subscription level
            #       Collect subscription info from self.p_client.user
            self._terms_browser.setSource(
                QUrl('qrc:/plugins/planet_explorer/terms.html'))
            self._terms_browser.setWindowModality(Qt.ApplicationModal)
        self._terms_browser.show()

    @pyqtSlot(str)
    def _open_link_with_browser(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def clean_up(self):
        self._main_filters.clean_up()
        for i in range(self.tabWidgetResults.count()):
            wdgt = self.tabWidgetResults.widget(i)
            if wdgt and hasattr(wdgt, 'clean_up'):
                wdgt.clean_up()

    def closeEvent(self, event):
        self.clean_up()
        self.closingPlugin.emit()
        event.accept()
