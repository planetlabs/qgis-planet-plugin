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
    QTimer
)
from qgis.PyQt.QtGui import (
    QIcon,
)
from qgis.PyQt.QtWidgets import (
    QAction,
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

from planet_explorer.gui.pe_dockwidget import (
    PlanetExplorerDockWidget,
)

from planet_explorer.pe_utils import (
    SETTINGS_NAMESPACE,
    sentry_dsn,
    segments_write_key,
    is_sentry_dsn_valid,
    is_segments_write_key_valid
)

from planet_explorer.planet_api import PlanetClient

from planet_explorer.planet_api.apikey_replacer import replace_apikeys

from planet_explorer.gui.mosaic_layer_widget import (
    MosaicLayerWidgetProvider
)

# from planet_explorer.pe_functions import (
#     registerFunctions,
#     unregisterFunctions,
# )

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

        # try:
        #     from .tests import testerplugin
        #     from qgistester.tests import addTestModule
        #     addTestModule(testerplugin, P_E)
        # except:
        #     pass

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr('&{0}'.format(P_E))
        self.toolbar = None

        self.plugin_is_active = False
        # noinspection PyTypeChecker
        self.dock_widget = None
        self.action_toggle_panel = None

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
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

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

        icon_path = ':/plugins/planet_explorer/planet-logo-p.svg'
        self.toolbar = self.iface.addToolBar(P_E)
        self.toolbar.setObjectName(P_E)

        self.add_action(
            icon_path,
            text=self.tr(P_E),
            callback=self.run,
            add_to_menu=True,
            add_to_toolbar=True,
            parent=self.iface.mainWindow())

        addSettingsMenu(P_E, self.iface.addPluginToWebMenu)
        # addHelpMenu(P_E, self.iface.addPluginToWebMenu)
        addAboutMenu(P_E, self.iface.addPluginToWebMenu)

        # Register helper function for dealing with PlanetLabs catalog
        # metadata
        # registerFunctions()

        # noinspection PyBroadException
        # try:
        #     from lessons import addLessonsFolder, addGroup
        #     folder = os.path.join(os.path.dirname(__file__), "_lessons")
        #     addLessonsFolder(folder, "imagediscovery")
        #     group_description = os.path.join(folder, "group.md")
        #     addGroup("Planet Explorer plugin", group_description)
        # except:
        #     pass

        self.run()
        last_shown = bool(pluginSetting(DOCK_SHOWN_STATE,
                                        namespace=SETTINGS_NAMESPACE,
                                        typ='bool'))
        if self.dock_widget is not None:
            self.dock_widget.setVisible(last_shown)

        self.provider = MosaicLayerWidgetProvider()    
        QgsGui.layerTreeEmbeddedWidgetRegistry().addProvider(self.provider)

        QgsProject.instance().projectSaved.connect(self.project_saved)

        PlanetClient.getInstance().loginChanged.connect(replace_apikeys)

    # -------------------------------------------------------------------------

    def on_close_plugin(self):
        """Cleanup necessary items here when plugin dock_widget is closed"""

        # Disconnects
        # self.dock_widget.closingPlugin.disconnect(self.on_close_plugin)

        # Remove this statement if dock_widget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dock_widget = None

        self.plugin_is_active = False

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

        # noinspection PyBroadException
        # try:
        #     from .tests import testerplugin
        #     from qgistester.tests import removeTestModule
        #     removeTestModule(testerplugin, P_E)
        # except:
        #     pass

        # noinspection PyBroadException
        # try:
        #     from lessons import removeLessonsFolder
        #     folder = os.path.join(pluginPath, "_lessons")
        #     removeLessonsFolder(folder)
        # except:
        #     pass

        # unregisterFunctions()

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

        if self.dock_widget is not None:
            setPluginSetting(DOCK_SHOWN_STATE,
                             self.dock_widget.isVisible(),
                             namespace=SETTINGS_NAMESPACE)
            self.iface.removeDockWidget(self.dock_widget)
            del self.dock_widget

        sys.excepthook = self.qgis_hook

        QgsProject.instance().projectSaved.disconnect(self.project_saved)

        # self.plugin_is_active = False

    # -------------------------------------------------------------------------

    def run(self):
        """Run method that loads and starts the plugin"""

        if not self.plugin_is_active:
            self.plugin_is_active = True

            # dock_widget may not exist if:
            #    first run of plugin
            #    removed on close (see self.on_close_plugin method)
            if self.dock_widget is None:
                # Create the dock_widget (after translation) and keep reference
                self.dock_widget = PlanetExplorerDockWidget(
                    parent=self.iface.mainWindow(), iface=self.iface)
                """:type: QDockWidget"""

                self.dock_widget.setAllowedAreas(
                    Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

                # Connect to provide cleanup on closing of dock_widget
                self.dock_widget.closingPlugin.connect(self.on_close_plugin)

                self.iface.addDockWidget(Qt.RightDockWidgetArea,
                                         self.dock_widget)
                return

        if self.dock_widget is not None:
            self.dock_widget._set_credential_fields()
            self.dock_widget.setVisible(self.dock_widget.isHidden())

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