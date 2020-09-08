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
import shutil
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
    QUrl
)
from qgis.PyQt.QtGui import (
    QIcon,
    QDesktopServices
)
from qgis.PyQt.QtWidgets import (
    QAction,
    QToolButton,
    QMenu,
    QTextBrowser
)

from qgiscommons2.settings import (
    readSettings,
    setPluginSetting,
    pluginSetting,
)
from qgiscommons2.gui.settings import (
    addSettingsMenu,
    removeSettingsMenu,
)
from qgiscommons2.gui import (
    addAboutMenu,
    removeAboutMenu,
    # addHelpMenu,
    # removeHelpMenu,
)

# Initialize Qt resources from file resources.py
# noinspection PyUnresolvedReferences
from planet_explorer.resources import resources

from planet_explorer.planet_api.p_thumnails import (
    TEMP_CACHE_DIR,
)

from planet_explorer.gui.pe_explorer_dockwidget import (
    show_explorer,
    toggle_explorer
)

from planet_explorer.pe_utils import (
    SETTINGS_NAMESPACE,
    sentry_dsn,
    segments_write_key,
    is_sentry_dsn_valid,
    is_segments_write_key_valid,
    add_menu_section_action,
    BASE_URL,
    open_link_with_browser)

from planet_explorer.planet_api import PlanetClient

from planet_explorer.planet_api.apikey_replacer import replace_apikeys

from planet_explorer.gui.basemap_layer_widget import (
    BasemapLayerWidgetProvider
)

from planet_explorer.gui.pe_orders_monitor_dockwidget import (
    toggle_orders_monitor
)

PLANET_COM = 'https://planet.com'
SAT_SPECS_PDF = 'https://assets.planet.com/docs/' \
                'Planet_Combined_Imagery_Product_Specs_letter_screen.pdf'
PLANET_SUPPORT_COMMUNITY = 'https://support.planet.com'
PLANET_EXPLORER = f'{PLANET_COM}/explorer'
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
        self.orders_dock_widget = None

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
                    pass #we swallow all exceptions here, to avoid entering an endless loop
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

        self.explorer_dock_widget = None
        
        self.toolbar = self.iface.addToolBar(P_E)
        self.toolbar.setObjectName(P_E)

        self.showexplorer_act = self.add_action(
            ':/plugins/planet_explorer/planet-logo-p.svg',
            text=self.tr(P_E),
            callback=toggle_explorer,
            add_to_menu=True,
            add_to_toolbar=True,
            parent=self.iface.mainWindow())

        self.showorders_act = self.add_action(
            ':/plugins/planet_explorer/download.svg',
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

        PlanetClient.getInstance().loginChanged.connect(replace_apikeys)

        PlanetClient.getInstance().loginChanged.connect(self.enable_buttons)

        self.enable_buttons(False)

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

        info_act = add_menu_section_action('Documentation', info_menu)

        terms_act = QAction('Terms', info_menu)
        terms_act.triggered[bool].connect(self.show_terms)
        info_menu.addAction(terms_act)

        btn = QToolButton()
        btn.setIcon(QIcon(':/plugins/planet_explorer/info.svg'))
        btn.setMenu(info_menu)

        # Also show menu on click, to keep disclosure triangle visible
        btn.clicked.connect(btn.showMenu) 

        self.toolbar.addWidget(btn) 

    def add_user_button(self):    
        user_menu = QMenu()

        self.user_act = add_menu_section_action('<b>Not Logged in<b/>', user_menu)

        self.acct_act = QAction(QIcon(EXT_LINK),
                           'Account', user_menu)
        self.acct_act.triggered[bool].connect(
            lambda: QDesktopServices.openUrl(QUrl(ACCOUNT_URL))
        )
        user_menu.addAction(self.acct_act)

        self.logout_act = QAction('Logout', user_menu)
        self.logout_act.triggered[bool].connect(self.logout)
        user_menu.addAction(self.logout_act)

        self.login_act = QAction('Login to Planet', user_menu)
        self.login_act.triggered[bool].connect(self.login)
        user_menu.addAction(self.login_act)

        btn = QToolButton()
        btn.setIcon(QIcon(':/plugins/planet_explorer/planet-user.svg'))
        btn.setMenu(user_menu)

        # Also show menu on click, to keep disclosure triangle visible
        btn.clicked.connect(btn.showMenu)

        self.toolbar.addWidget(btn)


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        self.provider.logoutLayerWidgets()
        
        # Delete the contents of the thumbnail temp directory
        if os.path.exists(TEMP_CACHE_DIR) and 'p_thumbcache' in TEMP_CACHE_DIR:
            for f_name in os.listdir(TEMP_CACHE_DIR):
                f_path = os.path.join(TEMP_CACHE_DIR, f_name)
                try:
                    shutil.rmtree(f_path)
                except OSError:
                    os.remove(f_path)

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

        if self.explorer_dock_widget is not None:
            self.iface.removeDockWidget(self.explorer_dock_widget)
            del self.explorer_dock_widget

        sys.excepthook = self.qgis_hook

        QgsProject.instance().projectSaved.disconnect(self.project_saved)

        # self.plugin_is_active = False

    #-----------------------------------------------------------        


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
        self.login_act.setVisible(not loggedin)
        self.logout_act.setVisible(loggedin)
        self.acct_act.setVisible(loggedin)
        if loggedin:
            self.user_act.defaultWidget().setText(
                f"<b>{PlanetClient.getInstance().user()['user_name']}<b/>")
        else:
            self.user_act.defaultWidget().setText("<b>Not Logged In<b/>")
        self.showexplorer_act.setEnabled(loggedin)
        if loggedin:
            self.showexplorer_act.setToolTip("Show / Hide the Planet Imagery Search Panel")
        else:
            self.showexplorer_act.setToolTip("Login to access Imagery Search")
        self.showorders_act.setEnabled(loggedin)
        if loggedin:
            self.showorders_act.setToolTip("Show / Hide the Order Status Panel")
        else:
            self.showorders_act.setToolTip("Login to access Order Status")

    def create_explorer(self):
        # Create the explorer_dock_widget (after translation) and keep reference
        self.explorer_dock_widget = PlanetExplorerDockWidget(
            parent=self.iface.mainWindow(), iface=self.iface)
        """:type: QDockWidget"""

        self.explorer_dock_widget.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.iface.addDockWidget(Qt.RightDockWidgetArea,
                                 self.explorer_dock_widget)

        self.explorer_dock_widget.hide()




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