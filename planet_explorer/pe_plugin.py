# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_plugin.py
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

from builtins import object

import os
import zipfile
import sys
import codecs
import traceback
import configparser

import analytics
import sentry_sdk

from qgis.core import (
    Qgis,
    QgsProject
)

from qgis.gui import QgsGui

from qgis.PyQt.QtCore import (
    QSettings,
    QTranslator,
    QCoreApplication,
    Qt,
    QTimer,
    QUrl,
    QSize
)

from qgis.PyQt.QtGui import (
    QIcon,
    QDesktopServices,
    QPalette
)

from qgis.PyQt.QtWidgets import (
    QAction,
    QToolButton,
    QPushButton,
    QMenu,
    QTextBrowser,
    QWidget,
    QHBoxLayout,
    QSizePolicy,
    QLabel
)

from qgiscommons2.settings import (
    readSettings
)
from qgiscommons2.gui.settings import (
    addSettingsMenu,
    removeSettingsMenu,
)
from qgiscommons2.gui import (
    addAboutMenu,
    removeAboutMenu
)

# Initialize Qt resources from file resources.py
# noinspection PyUnresolvedReferences
from planet_explorer.resources import resources

from planet_explorer.gui.pe_explorer_dockwidget import (
    show_explorer,
    remove_explorer,
    toggle_mosaics_search,
    toggle_images_search
)

from planet_explorer.pe_utils import (
    sentry_dsn,
    segments_write_key,
    is_sentry_dsn_valid,
    is_segments_write_key_valid,
    add_menu_section_action,
    BASE_URL,
    open_link_with_browser,
    add_widget_to_layer,
    PLANET_COLOR
)

from planet_explorer.planet_api import PlanetClient

from planet_explorer.gui.pe_basemap_layer_widget import (
    BasemapLayerWidgetProvider
)

from planet_explorer.gui.pe_orders_monitor_dockwidget import (
    toggle_orders_monitor,
    hide_orders_monitor,
    remove_orders_monitor
)

from planet_explorer.gui.pe_planet_inspector_dockwidget import (
    toggle_inspector,
    hide_inspector,
    remove_inspector
)

from planet_explorer.gui.pe_tasking_dockwidget import (
    toggle_tasking_widget,
    remove_tasking_widget
)

PLANET_COM = 'https://planet.com'
SAT_SPECS_PDF = 'https://assets.planet.com/docs/' \
                'Planet_Combined_Imagery_Product_Specs_letter_screen.pdf'
PLANET_SUPPORT_COMMUNITY = 'https://support.planet.com'
PLANET_EXPLORER = f'{PLANET_COM}/explorer'
PLANET_INTEGRATIONS = "https://developers.planet.com/tag/integrations.html"
PLANET_SALES = "https://www.planet.com/contact-sales"

EXT_LINK = ':/plugins/planet_explorer/external-link.svg'
ACCOUNT_URL = f'{BASE_URL}/account'

plugin_path = os.path.dirname(__file__)

P_E = 'Planet Explorer'
PE = P_E.replace(' ', '')

DOCK_SHOWN_STATE = 'dockShownState'

PLUGIN_NAMESPACE = "planet_explorer"

# noinspection PyUnresolvedReferences
class PlanetExplorer(object):

    def __init__(self, iface):

        self.iface = iface

        # Initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # Initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            '{0}Plugin_{1}.qm'.format(PE, locale)
        )

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr('&{0}'.format(P_E))
        self.toolbar = None

        # noinspection PyTypeChecker
        self.explorer_dock_widget = None
        self._terms_browser = None

        readSettings()

        if is_segments_write_key_valid():
            analytics.write_key = segments_write_key()
        if is_sentry_dsn_valid():
            sentry_sdk.init(sentry_dsn(), default_integrations=False)

        self.qgis_hook = sys.excepthook

        def plugin_hook(t, value, tb):
            trace = "".join(traceback.format_exception(t, value, tb))
            if PLUGIN_NAMESPACE in trace.lower():
                try:
                    sentry_sdk.capture_exception(value)
                except:
                    pass # we swallow all exceptions here, to avoid entering an endless loop
            self.qgis_hook(t, value, tb)

        sys.excepthook = plugin_hook

        metadataFile = os.path.join(os.path.dirname(__file__), "metadata.txt")
        cp = configparser.ConfigParser()
        with codecs.open(metadataFile, "r", "utf8") as f:
            cp.read_file(f)

        if is_sentry_dsn_valid():
            version = cp["general"]["version"]
            with sentry_sdk.configure_scope() as scope:
                scope.set_context("plugin_version", version)
                scope.set_context("qgis_version", Qgis.QGIS_VERSION)

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate(PE, message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToWebMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    # noinspection PyPep8Naming
    def initGui(self):

        self.toolbar = self.iface.addToolBar(P_E)
        self.toolbar.setObjectName(P_E)

        self.showdailyimages_act = self.add_action(
            os.path.join(plugin_path, "resources", "search.svg"),
            text=self.tr(P_E),
            callback=toggle_images_search,
            add_to_menu=True,
            add_to_toolbar=True,
            parent=self.iface.mainWindow())

        self.showbasemaps_act = self.add_action(
            os.path.join(plugin_path, "resources", "basemap.svg"),
            text=self.tr("Show Basemaps Search"),
            callback=toggle_mosaics_search,
            add_to_menu=True,
            add_to_toolbar=True,
            parent=self.iface.mainWindow())

        self.showinspector_act = self.add_action(
            os.path.join(plugin_path, "resources", "inspector.svg"),
            text=self.tr("Show Planet Inspector..."),
            callback=toggle_inspector,
            add_to_menu=False,
            add_to_toolbar=True,
            parent=self.iface.mainWindow())

        self.showtasking_act = self.add_action(
            os.path.join(plugin_path, "resources", "tasking.svg"),
            text=self.tr("Show Tasking..."),
            callback=toggle_tasking_widget,
            add_to_menu=False,
            add_to_toolbar=True,
            parent=self.iface.mainWindow())

        self.add_central_toolbar_button()

        self.showorders_act = self.add_action(
            os.path.join(plugin_path, "resources", "orders.svg"),
            text=self.tr("Show Orders Monitor..."),
            callback=toggle_orders_monitor,
            add_to_menu=False,
            add_to_toolbar=True,
            parent=self.iface.mainWindow())

        self.add_user_button()
        self.add_info_button()

        addSettingsMenu(P_E, self.iface.addPluginToWebMenu)
        addAboutMenu(P_E, self.iface.addPluginToWebMenu)

        self.provider = BasemapLayerWidgetProvider()
        QgsGui.layerTreeEmbeddedWidgetRegistry().addProvider(self.provider)

        QgsProject.instance().projectSaved.connect(self.project_saved)
        QgsProject.instance().layersAdded.connect(self.layers_added)
        QgsProject.instance().layerRemoved.connect(self.layer_removed)

        PlanetClient.getInstance().loginChanged.connect(self.login_changed)

        self.enable_buttons(False)

    def add_central_toolbar_button(self):
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QHBoxLayout()
        layout.addStretch()
        self.btnLogin = QPushButton()
        palette = self.btnLogin.palette()
        palette.setColor(QPalette.Button, PLANET_COLOR)
        self.btnLogin.setPalette(palette)
        self.btnLogin.setText("Log in")
        #self.btnLogin.setAutoRaise(True)
        self.btnLogin.setAttribute(Qt.WA_TranslucentBackground)
        self.btnLogin.clicked.connect(self.btn_login_clicked)
        icon = QIcon(os.path.join(plugin_path, "resources", "planet-logo-p.svg"))
        labelIcon = QLabel()
        labelIcon.setPixmap(icon.pixmap(QSize(16, 16)))
        layout.addWidget(labelIcon)
        self.labelLoggedIn = QLabel()
        self.labelLoggedIn.setText("")
        layout.addWidget(self.labelLoggedIn)
        layout.addWidget(self.btnLogin)
        layout.addStretch()
        widget.setLayout(layout)
        self.toolbar.addWidget(widget)

    def btn_login_clicked(self):
        if PlanetClient.getInstance().has_api_key():
            self.logout()
        else:
            self.login()

    def layer_removed(self, layer):
        self.provider.layerWasRemoved(layer)

    def layers_added(self, layers):
        for layer in layers:
            add_widget_to_layer(layer)

    def login_changed(self, loggedin):
        self.provider.updateLayerWidgets()
        self.enable_buttons(loggedin)
        if not loggedin:
            hide_orders_monitor()
            hide_inspector()

    def add_info_button(self):
        info_menu = QMenu()

        p_sec_act = add_menu_section_action('Planet', info_menu)

        p_com_act = QAction(QIcon(EXT_LINK),
                            'planet.com', info_menu)
        p_com_act.triggered[bool].connect(
            lambda: open_link_with_browser(PLANET_COM)
        )
        info_menu.addAction(p_com_act)

        p_explorer_act = QAction(QIcon(EXT_LINK),
                                 'Planet Explorer web app', info_menu)
        p_explorer_act.triggered[bool].connect(
            lambda: open_link_with_browser(PLANET_EXPLORER)
        )
        info_menu.addAction(p_explorer_act)

        p_sat_act = QAction(QIcon(EXT_LINK),
                            'Satellite specs PDF', info_menu)
        p_sat_act.triggered[bool].connect(
            lambda: open_link_with_browser(SAT_SPECS_PDF)
        )
        info_menu.addAction(p_sat_act)

        p_support_act = QAction(QIcon(EXT_LINK),
                                'Support Community', info_menu)
        p_support_act.triggered[bool].connect(
            lambda: open_link_with_browser(PLANET_SUPPORT_COMMUNITY)
        )
        info_menu.addAction(p_support_act)

        p_whatsnew_act = QAction(QIcon(EXT_LINK),
                                "What's new", info_menu)
        p_whatsnew_act.triggered[bool].connect(
            lambda: open_link_with_browser(PLANET_INTEGRATIONS)
        )
        info_menu.addAction(p_whatsnew_act)

        p_sales_act = QAction(QIcon(EXT_LINK),
                                "Sales", info_menu)
        p_sales_act.triggered[bool].connect(
            lambda: open_link_with_browser(PLANET_SALES)
        )
        info_menu.addAction(p_sales_act)

        add_menu_section_action('Documentation', info_menu)

        terms_act = QAction('Terms', info_menu)
        terms_act.triggered[bool].connect(self.show_terms)
        info_menu.addAction(terms_act)

        btn = QToolButton()
        btn.setIcon(QIcon(os.path.join(plugin_path, "resources", "info.svg"),))
        btn.setMenu(info_menu)

        btn.setPopupMode(QToolButton.MenuButtonPopup)
        # Also show menu on click, to keep disclosure triangle visible
        btn.clicked.connect(btn.showMenu)

        self.toolbar.addWidget(btn)

    def add_user_button(self):
        user_menu = QMenu()

        self.acct_act = QAction(QIcon(EXT_LINK),
                           'Account', user_menu)
        self.acct_act.triggered[bool].connect(
            lambda: QDesktopServices.openUrl(QUrl(ACCOUNT_URL))
        )
        user_menu.addAction(self.acct_act)

        self.logout_act = QAction('Logout', user_menu)
        self.logout_act.triggered[bool].connect(self.logout)
        user_menu.addAction(self.logout_act)

        self.user_button = QToolButton()
        self.user_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);
        self.user_button.setIcon(QIcon(os.path.join(plugin_path, "resources", "account.svg"),))
        self.user_button.setMenu(user_menu)

        self.user_button.setPopupMode(QToolButton.MenuButtonPopup)
        # Also show menu on click, to keep disclosure triangle visible
        self.user_button.clicked.connect(self.user_button.showMenu)

        self.toolbar.addWidget(self.user_button)

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        PlanetClient.getInstance().log_out()
        self.provider.updateLayerWidgets()

        removeSettingsMenu(P_E, self.iface.removePluginWebMenu)
        # removeHelpMenu(P_E, self.iface.removePluginWebMenu)
        removeAboutMenu(P_E, self.iface.removePluginWebMenu)

        for action in self.actions:
            self.iface.removePluginWebMenu(
                self.tr('&{0}'.format(P_E)), action)
            self.iface.removeToolBarIcon(action)

        # remove the toolbar
        if self.toolbar is not None:
            del self.toolbar

        remove_inspector()
        remove_explorer()
        remove_orders_monitor()
        remove_tasking_widget()

        QgsGui.layerTreeEmbeddedWidgetRegistry().removeProvider(self.provider.id())

        sys.excepthook = self.qgis_hook

        QgsProject.instance().projectSaved.disconnect(self.project_saved)
        QgsProject.instance().layersAdded.disconnect(self.layers_added)
        QgsProject.instance().layerRemoved.disconnect(self.layer_removed)

    # -----------------------------------------------------------

    def show_terms(self, _):
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

    def login(self):
        show_explorer()

    def logout(self):
        PlanetClient.getInstance().log_out()

    def enable_buttons(self, loggedin):
        self.btnLogin.setVisible(not loggedin)
        labelText = ("<b>Welcome to Planet</b>" if not loggedin else "<b>Planet</b>")
        self.labelLoggedIn.setText(labelText)
        self.showdailyimages_act.setEnabled(loggedin)
        self.showbasemaps_act.setEnabled(loggedin)
        self.showinspector_act.setEnabled(loggedin)
        self.showorders_act.setEnabled(loggedin)
        self.showtasking_act.setEnabled(loggedin)
        self.user_button.setEnabled(loggedin)
        self.user_button.setText(
            PlanetClient.getInstance().user()['user_name']
            if loggedin else "")
        if loggedin:
            self.showdailyimages_act.setToolTip("Show / Hide the Planet Imagery Search Panel")
            self.showbasemaps_act.setToolTip("Show / Hide the Planet Basemaps Search Panel")
            self.showorders_act.setToolTip("Show / Hide the Order Status Panel")
            self.showinspector_act.setToolTip("Show / Hide the Planet Inspector Panel")
            self.showtasking_act.setToolTip("Show / Hide the Tasking Panel")
        else:
            self.showdailyimages_act.setToolTip("Login to access Imagery Search")
            self.showbasemaps_act.setToolTip("Login to access Basemaps Search")
            self.showorders_act.setToolTip("Login to access Order Status")
            self.showinspector_act.setToolTip("Login to access Planet Inspector")
            self.showtasking_act.setToolTip("Login to access Tasking Panel")

    def project_saved(self):
        if PlanetClient.getInstance().has_api_key():
            def resave():
                path = QgsProject.instance().absoluteFilePath()
                if path.lower().endswith(".qgs"):
                    with open(path) as f:
                        s = f.read()
                    with open(path, "w") as f:
                        f.write(s.replace(PlanetClient.getInstance().api_key(), ""))
                else:
                    tmpfilename = path + ".temp"
                    qgsfilename = os.path.splitext(os.path.basename(path))[0] + ".qgs"
                    with zipfile.ZipFile(path, 'r') as zin:
                        with zipfile.ZipFile(tmpfilename, 'w') as zout:
                            zout.comment = zin.comment
                            for item in zin.infolist():
                                if not item.filename.lower().endswith(".qgs"):
                                    zout.writestr(item, zin.read(item.filename))
                                else:
                                    s = zin.read(item.filename).decode("utf-8")
                                    s = s.replace(PlanetClient.getInstance().api_key(), "")
                                    qgsfilename = item.filename
                    os.remove(path)
                    os.rename(tmpfilename, path)
                    with zipfile.ZipFile(path, mode='a', compression=zipfile.ZIP_DEFLATED) as zf:
                        zf.writestr(qgsfilename, s)
            QTimer.singleShot(100, resave)