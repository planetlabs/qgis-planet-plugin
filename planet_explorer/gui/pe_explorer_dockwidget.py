# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_explorer_dockwidget.py
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

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, pyqtSlot
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QLineEdit

from ..pe_utils import (
    iface,
    plugin_version,
)
from ..planet_api import PlanetClient
from .pe_basemaps_widget import BasemapsWidget
from .pe_dailyimages_widget import DailyImagesWidget

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get("PYTHON_LOG_VERBOSE", None)

plugin_path = os.path.split(os.path.dirname(__file__))[0]
WIDGET, BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_explorer_dockwidget.ui")
)

LOG_NAME = "PlanetExplorer"

PLANET_COM = "https://planet.com"
SAT_SPECS_PDF = (
    "https://assets.planet.com/docs/"
    "Planet_Combined_Imagery_Product_Specs_letter_screen.pdf"
)
PLANET_SUPPORT_COMMUNITY = "https://support.planet.com"
PLANET_EXPLORER = f"{PLANET_COM}/explorer"

TOS_URL = "https://learn.planet.com/QGIS-terms-conditions.html"


class PlanetExplorerDockWidget(BASE, WIDGET):
    def __init__(self, parent=None, visible=False):
        super(PlanetExplorerDockWidget, self).__init__(parent)

        self.setupUi(self)

        self.p_client = None

        self.setVisible(visible)

        self.leUser.addAction(
            QIcon(":/plugins/planet_explorer/envelope-gray.svg"),
            QLineEdit.ActionPosition.LeadingPosition,
        )

        self.tabWidgetResourceType.currentChanged[int].connect(self._item_group_changed)

        self.setWindowTitle(f"Planet Explorer [{plugin_version()}]")

        self.daily_images_widget = None
        self._setup_daily_images_panel()
        self._setup_mosaics_panel()

        # Set default group type and filter widget
        self.tabWidgetResourceType.setCurrentIndex(0)

        self._terms_browser = None
        self.msg_log = QgsMessageLog()
        self.msgBar.hide()

    def showEvent(self, event):
        super().showEvent(event)
        if self.p_client is None:
            self.p_client = PlanetClient.getInstance()

        if self.p_client.client_is_setup():
            self.stckdWidgetViews.setCurrentIndex(1)
        else:
            pass

    def logged_in(self):
        return self.p_client is not None and self.p_client.client_is_setup()

    @pyqtSlot()
    def login_changed(self):
        if self.logged_in():
            self._setup_daily_images_panel()

            self.clean_up()
            self.switch_to_browse_panel()
        else:
            self.basemaps_widget.reset()

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

    def show_message(
        self, message, level=Qgis.MessageLevel.Info, duration=None, show_more=None
    ):
        """Displays a message in the QGIS message bar omitting the bold title.

        Args:
            message (str): The primary notification text to display.
            level (Qgis.MessageLevel, optional): The severity level of the message.
                Defaults to Qgis.MessageLevel.Info.
            duration (int, optional): Dismiss timeout in seconds. If None, falls
                back to the global QGIS message timeout. Defaults to None.
            show_more (str, optional): Detailed text or traceback displayed when
                clicking an interactive 'Show more' link. Defaults to None.
        """
        if duration is None:
            duration = iface.messageTimeout()

        if show_more is not None:
            self.msgBar.pushMessage("", message, show_more, level, duration)
        else:
            self.msgBar.pushMessage("", message, level, duration)

    def clean_up(self):
        if self.daily_images_widget is not None:
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
        dockwidget_instance.setObjectName("PlanetExplorerDockWidget")
        dockwidget_instance.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dockwidget_instance)

        dockwidget_instance.hide()
    return dockwidget_instance


def toggle_explorer():
    instance = _get_widget_instance()
    instance.setVisible(instance.isHidden())


def show_explorer():
    instance = _get_widget_instance()
    instance.show()


def hide_explorer():
    wdgt = _get_widget_instance()
    if wdgt is not None:
        wdgt.hide()


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
