# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_gui_utils.py
    ---------------------
    Date                 : September 2019
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
__date__ = "September 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import logging
import os

from qgis.PyQt.QtCore import QEvent, Qt, pyqtSignal  # pyqtSlot,
from qgis.PyQt.QtGui import QMouseEvent
from qgis.PyQt.QtWidgets import QApplication, QLabel, QToolTip

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

plugin_path = os.path.split(os.path.dirname(__file__))[0]


# noinspection PyPep8Naming
class PlanetClickableLabel(QLabel):

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        """
        Clickable QLabel
        """
        super().__init__(parent=parent)

        self._show_tooltip_on_hover = False
        self.setAttribute(Qt.WA_Hover)

    def set_show_tooltip_on_hover(self, show) -> None:
        self._show_tooltip_on_hover = show

    def shows_tooltip_on_hover(self) -> bool:
        return self._show_tooltip_on_hover

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        self.clicked.emit()

    def event(self, event: QEvent) -> bool:
        if self._show_tooltip_on_hover and self.toolTip():
            if event.type() == QEvent.HoverEnter:
                # noinspection PyUnresolvedReferences
                QToolTip.showText(self.mapToGlobal(event.pos()), self.toolTip(), self)
            event.accept()

        return QLabel.event(self, event)


def waitcursor(method):
    def func(*args, **kw):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            return method(*args, **kw)
        except Exception as ex:
            raise ex
        finally:
            QApplication.restoreOverrideCursor()

    return func
