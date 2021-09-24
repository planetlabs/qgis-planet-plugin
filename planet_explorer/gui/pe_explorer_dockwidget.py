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

import sentry_sdk
from qgis.core import Qgis, QgsApplication, QgsMessageLog
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSettings, Qt, pyqtSlot
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDialogButtonBox, QLineEdit

from ..pe_analytics import analytics_track, is_sentry_dsn_valid
from ..pe_utils import (
    BASE_URL,
    SETTINGS_NAMESPACE,
    open_link_with_browser,
    iface,
    plugin_version,
)
from ..planet_api import API_KEY_DEFAULT, LoginException, PlanetClient
from .pe_basemaps_widget import BasemapsWidget
from .pe_dailyimages_widget import DailyImagesWidget

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get("PYTHON_LOG_VERBOSE", None)

plugin_path = os.path.split(os.path.dirname(__file__))[0]
WIDGET, BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_explorer_dockwidget.ui"),
    from_imports=True,
    import_from=f"{os.path.basename(plugin_path)}",
    resource_suffix="",
)

LOG_NAME = "PlanetExplorer"

AUTH_CREDS_KEY = "pe_plugin_auth"
AUTH_SEP = "|||"
AUTH_STRING = "{user}{sep}{password}{sep}{api_key}"
SAVE_CREDS_KEY = "saveCreds"
AUTO_RECOVER_VALUES = "recoverSearchValues"

PLANET_COM = "https://planet.com"
SAT_SPECS_PDF = (
    "https://assets.planet.com/docs/"
    "Planet_Combined_Imagery_Product_Specs_letter_screen.pdf"
)
PLANET_SUPPORT_COMMUNITY = "https://support.planet.com"
PLANET_EXPLORER = f"{PLANET_COM}/explorer"

SIGNUP_URL = f"{BASE_URL}/contact"
TOS_URL = "https://learn.planet.com/QGIS-terms-conditions.html"
FORGOT_PASS_URL = f"{BASE_URL}/login?mode=reset-password"


class PlanetExplorerDockWidget(BASE, WIDGET):
    def __init__(self, parent=None, visible=False):
        super(PlanetExplorerDockWidget, self).__init__(parent)

        self.setupUi(self)
        self.setVisible(visible)

        self._auth_man = QgsApplication.authManager()

        self.p_client = None
        self.api_key = None
        self._save_creds = bool(
            QSettings().value(f"{SETTINGS_NAMESPACE}/{SAVE_CREDS_KEY}")
        )

        self.leUser.addAction(
            QIcon(":/plugins/planet_explorer/envelope-gray.svg"),
            QLineEdit.LeadingPosition,
        )

        self.lblSignUp.linkActivated[str].connect(
            lambda: open_link_with_browser(SIGNUP_URL)
        )
        self.lblTermsOfService.linkActivated[str].connect(
            lambda: open_link_with_browser(TOS_URL)
        )
        self.lblForgotPass.linkActivated[str].connect(
            lambda: open_link_with_browser(FORGOT_PASS_URL)
        )

        self.btn_ok = self.buttonBoxLogin.button(QDialogButtonBox.Ok)
        self.btn_ok.setText("Sign In")
        self.btn_api_key = self.buttonBoxLogin.button(QDialogButtonBox.Abort)
        self.btn_api_key.setText("Use API key")
        self.btn_api_key.hide()
        self.buttonBoxLogin.accepted.connect(self.login)
        self.buttonBoxLogin.rejected.connect(self.api_key_login)

        self.tabWidgetResourceType.currentChanged[int].connect(self._item_group_changed)

        self.setWindowTitle(f"Planet Explorer [{plugin_version()}]")

        self.daily_images_widget = None
        # self._setup_daily_images_panel()
        self._setup_mosaics_panel()

        # Set default group type and filter widget
        self.tabWidgetResourceType.setCurrentIndex(0)

        self._terms_browser = None
        self.msg_log = QgsMessageLog()
        self.msgBar.hide()

    def showEvent(self, event):
        if self.logged_in():
            self.stckdWidgetViews.setCurrentIndex(1)
        else:
            self._setup_client()

    def _setup_client(self):
        # Init api client
        self.p_client = PlanetClient.getInstance()
        self.p_client.loginChanged[bool].connect(self.login_changed)

        # Retrieve any login/key settings
        self.switch_to_login_panel()
        if not self.logged_in():
            self.api_key = API_KEY_DEFAULT
            self._set_credential_fields()
            self.chkBxSaveCreds.stateChanged.connect(self.save_credentials_changed)

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
                self.leUser.text(), self.lePass.text(), api_key=api_key
            )
            self.p_client.blockSignals(False)
        except LoginException as e:
            self.show_message(
                "Login failed!", show_more=str(e.__cause__), level=Qgis.Warning
            )
            # Stay on login panel if error
            return

        # Login OK
        self.api_key = self.p_client.api_key()

        user = self.p_client.user()
        if is_sentry_dsn_valid():
            with sentry_sdk.configure_scope() as scope:
                scope.user = {"email": user["email"]}

        analytics_track("user_login")

        # Store settings
        if self.chkBxSaveCreds.isChecked():
            self._store_auth_creds()
            analytics_track("save_credentials")

        # For debugging
        specs = (
            f"logged_in={self.logged_in()}\n\n"
            f"api_key = {self.p_client.api_key()}\n\n"
            f"user: {self.p_client.user()}\n\n"
        )
        log.debug(f"Login successful:\n{specs}")

        # Now switch panels
        self.p_client.loginChanged.emit(self.p_client.has_api_key())
        # self.login_changed()

    @pyqtSlot()
    def login_changed(self):
        if self.logged_in():
            self._setup_daily_images_panel()
            self.lePass.setText("")
            self.leUser.setText("")
            self.clean_up()
            self.switch_to_browse_panel()
        else:
            self._set_credential_fields()
            self.switch_to_login_panel()

    @pyqtSlot()
    def switch_to_login_panel(self):
        self.stckdWidgetViews.setCurrentIndex(0)

    @pyqtSlot()
    def switch_to_browse_panel(self):
        self.stckdWidgetViews.setCurrentIndex(1)
        self.tabWidgetResourceType.setCurrentWidget(self.tabWidgetResourceTypePage1)

    @pyqtSlot(int)
    def _item_group_changed(self, indx):
        if indx == 1:
            self.basemaps_widget.init()

    def _setup_daily_images_panel(self):
        if self.daily_images_widget is None:
            self.daily_images_widget = DailyImagesWidget(self)
            self.tabWidgetResourceTypePage1.layout().addWidget(self.daily_images_widget)

    def _setup_mosaics_panel(self):
        self.basemaps_widget = BasemapsWidget(self)
        self.tabWidgetResourceTypePage2.layout().addWidget(self.basemaps_widget)

    def show_daily_images_panel(self):
        self.tabWidgetResourceType.setCurrentIndex(0)

    def show_mosaics_panel(self):
        self.tabWidgetResourceType.setCurrentIndex(1)

    def show_message(self, message, level=Qgis.Info, duration=None, show_more=None):
        """Skips bold title, i.e. sets first param (below) to empty string"""
        if duration is None:
            duration = iface.messageTimeout()

        if show_more is not None:
            self.msgBar.pushMessage("", message, show_more, level, duration)
        else:
            self.msgBar.pushMessage("", message, level, duration)

    @pyqtSlot(int)
    def save_credentials_changed(self, state):
        if state == 0:
            self._remove_auth_creds()
        self._save_creds = state > 0
        QSettings().setValue(f"{SETTINGS_NAMESPACE}/{SAVE_CREDS_KEY}", self._save_creds)

    def _store_auth_creds(self):
        auth_creds_str = AUTH_STRING.format(
            user=self.leUser.text(),
            password=self.lePass.text(),
            api_key=self.p_client.api_key(),
            sep=AUTH_SEP,
        )
        self._auth_man.storeAuthSetting(AUTH_CREDS_KEY, auth_creds_str, True)

    def _retrieve_auth_creds(self):
        auth_creds_str = (
            self._auth_man.authSetting(AUTH_CREDS_KEY, defaultValue="", decrypt=True)
            or ""
        )
        creds = auth_creds_str.split(AUTH_SEP)
        return {
            "user": creds[0] if len(creds) > 0 else None,
            "password": creds[1] if len(creds) > 1 else None,
            "api_key": creds[2] if len(creds) > 2 else None,
        }

    def _set_credential_fields(self):
        self.lePass.setPasswordVisibility(False)
        if not self._save_creds:
            self.chkBxSaveCreds.setChecked(False)
        else:
            self.chkBxSaveCreds.setChecked(True)
            auth_creds = self._retrieve_auth_creds()
            self.leUser.setText(auth_creds["user"])
            self.lePass.setText(auth_creds["password"])
            self.api_key = auth_creds["api_key"]

    def _remove_auth_creds(self):
        if not self._auth_man.removeAuthSetting(AUTH_CREDS_KEY):
            self.show_message(
                "Credentials setting removal failed", level=Qgis.Warning, duration=10
            )

    def clean_up(self):
        self.daily_images_widget.clean_up()
        self.basemaps_widget.reset()

    def closeEvent(self, event):
        self.clean_up()
        event.accept()


dockwidget_instance = None


def _get_widget_instance():
    global dockwidget_instance
    if dockwidget_instance is None:
        dockwidget_instance = PlanetExplorerDockWidget(parent=iface.mainWindow())
        dockwidget_instance.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )

        iface.addDockWidget(Qt.RightDockWidgetArea, dockwidget_instance)

        dockwidget_instance.hide()
    return dockwidget_instance


def toggle_explorer():
    instance = _get_widget_instance()
    instance._set_credential_fields()
    instance.setVisible(instance.isHidden())


def show_explorer():
    instance = _get_widget_instance()
    instance._set_credential_fields()
    instance.show()


def show_explorer_and_search_daily_images(request):
    instance = _get_widget_instance()
    instance.daily_images_widget.set_filters_from_request(request)
    instance.daily_images_widget.perform_search()
    instance.show()
    instance.show_daily_images_panel()


def remove_explorer():
    if dockwidget_instance is not None:
        iface.removeDockWidget(dockwidget_instance)


def toggle_images_search():
    instance = _get_widget_instance()
    instance.show_daily_images_panel()
    toggle_explorer()


def toggle_mosaics_search():
    instance = _get_widget_instance()
    instance.show_mosaics_panel()
    toggle_explorer()
