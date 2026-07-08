# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_settings_dialog.py
    ---------------------
    Date                 : May 2026
    Copyright            : (C) 2026 Planet Inc, https://planet.com
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
__date__ = "May 2026"
__copyright__ = "(C) 2026 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import json
import os

from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from planet_explorer.pe_utils import SETTINGS_NAMESPACE, iface, log

BOOL = "bool"
STRING = "string"
PASSWORD = "password"  # nosec
TEXT = "text"  # a multiline string
NUMBER = "number"
FILES = "files"
FOLDER = "folder"
CHOICE = "choice"
VECTOR = "vector"
RASTER = "raster"


def parameterFromName(params, name):
    for param in params:
        if param["name"] == name:
            return param


class TextBoxWithLink(QWidget):
    def __init__(self, text, func, value, editable=True):
        self._value = value
        QWidget.__init__(self)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.lineEdit = QLineEdit()
        if not editable:
            self.lineEdit.setReadOnly(True)
        self.lineEdit.setText(value)
        self.lineEdit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.lineEdit)
        if text:
            linkLabel = QLabel()
            linkLabel.setText("<a href='#'> %s</a>" % text)
            layout.addWidget(linkLabel)
            linkLabel.linkActivated.connect(lambda: func(self))
        self.setLayout(layout)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        self.lineEdit.setText(value)


class SettingsDialog(QDialog):
    def __init__(self):
        QDialog.__init__(self, iface.mainWindow())
        filepath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "settings.json"
        )
        with open(filepath) as f:
            self.params = json.load(f)
        self.widgets = {}
        self.setWindowTitle("Settings")
        self.setupUi()

    def setupUi(self):
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.resize(640, 450)
        verticalLayout = QVBoxLayout()

        for param in self.params:
            name = param["name"]
            horizontalLayout = QHBoxLayout()
            if param["type"] not in [BOOL]:
                horizontalLayout.addWidget(QLabel(param["label"]))
            self.widgets[name] = self.widgetFromParameter(param)
            horizontalLayout.addWidget(self.widgets[name])
            value = QSettings().value(f"{SETTINGS_NAMESPACE}/{name}", None)
            if value:
                self.setValueInWidget(self.widgets[name], param["type"], value)
            verticalLayout.addLayout(horizontalLayout)

        horizontalLayout = QHBoxLayout()
        self.buttonBox = QDialogButtonBox()
        self.buttonBox.setOrientation(Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        horizontalLayout.addWidget(self.buttonBox)
        verticalLayout.addStretch()
        verticalLayout.addLayout(horizontalLayout)

        self.setLayout(verticalLayout)

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _widget_for_files(self, param) -> TextBoxWithLink:
        """Create a file browser widget.

        Args:
            param (dict): Parameter definition.

        Returns:
            TextBoxWithLink: File browser widget.
        """

        def edit(textbox):
            f = QFileDialog.getOpenFileNames(self, "Select file", "", "*.*")
            if f:
                textbox.value = ",".join(f)

        return TextBoxWithLink("Browse", edit, None, True)

    def _widget_for_folder(self, param) -> TextBoxWithLink:
        """Create a folder browser widget.

        Args:
            param (dict): Parameter definition.

        Returns:
            TextBoxWithLink: Folder browser widget.
        """

        def edit(textbox):
            f = QFileDialog.getExistingDirectory(self, "Select folder", "")
            if f:
                textbox.value = f

        return TextBoxWithLink("Browse", edit, None, True)

    def _widget_for_bool(self, param) -> QCheckBox:
        """Create a checkbox widget.

        Args:
            param (dict): Parameter definition.

        Returns:
            QCheckBox: Checkbox widget.
        """
        check = QCheckBox(param["label"])
        if param["default"]:
            check.setCheckState(Qt.CheckState.Checked)
        else:
            check.setCheckState(Qt.CheckState.Unchecked)
        return check

    def _widget_for_choice(self, param) -> QComboBox:
        """Create a combo box widget.

        Args:
            param (dict): Parameter definition.

        Returns:
            QComboBox: Combo box widget.
        """
        combo = QComboBox()
        for option in param["options"]:
            combo.addItem(option)
        idx = combo.findText(str(param["default"]))
        combo.setCurrentIndex(idx)
        return combo

    def _widget_for_text(self, param) -> QTextEdit:
        """Create a text edit widget.

        Args:
            param (dict): Parameter definition.

        Returns:
            QTextEdit: Text edit widget.
        """
        textEdit = QTextEdit()
        textEdit.setPlainText(param["default"])
        return textEdit

    def _widget_for_vector(self, param) -> QgsMapLayerComboBox:
        """Create a vector layer combo box widget.

        Args:
            param (dict): Parameter definition.

        Returns:
            QgsMapLayerComboBox: Vector layer combo box widget.
        """
        combo = QgsMapLayerComboBox()
        combo.setFilters(QgsMapLayerProxyModel.Filter.VectorLayer)
        return combo

    def _widget_for_raster(self, param) -> QgsMapLayerComboBox:
        """Create a raster layer combo box widget.

        Args:
            param (dict): Parameter definition.

        Returns:
            QgsMapLayerComboBox: Raster layer combo box widget.
        """
        combo = QgsMapLayerComboBox()
        combo.setFilters(QgsMapLayerProxyModel.Filter.RasterLayer)
        return combo

    def _widget_for_password(self, param) -> QLineEdit:
        """Create a password line edit widget.

        Args:
            param (dict): Parameter definition.

        Returns:
            QLineEdit: Password line edit widget.
        """
        lineEdit = QLineEdit()
        lineEdit.setEchoMode(QLineEdit.EchoMode.Password)
        return lineEdit

    def _widget_default(self, param) -> QLineEdit:
        """Create a default line edit widget.

        Args:
            param (dict): Parameter definition.

        Returns:
            QLineEdit: Line edit widget.
        """
        lineEdit = QLineEdit()
        lineEdit.setText(str(param["default"]))
        return lineEdit

    def widgetFromParameter(self, param: dict) -> QWidget:
        """Create a widget for the given parameter.

        Args:
            param (dict): Parameter definition.

        Returns:
            QWidget: Widget for the parameter.
        """
        widget_builders = {
            FILES: self._widget_for_files,
            FOLDER: self._widget_for_folder,
            BOOL: self._widget_for_bool,
            CHOICE: self._widget_for_choice,
            TEXT: self._widget_for_text,
            VECTOR: self._widget_for_vector,
            RASTER: self._widget_for_raster,
            PASSWORD: self._widget_for_password,
        }
        builder = widget_builders.get(param["type"], self._widget_default)
        return builder(param)

    def valueFromWidget(self, widget, paramtype):
        try:
            if paramtype == BOOL:
                return widget.isChecked()
            elif paramtype == NUMBER:
                return float(widget.text())
            elif paramtype == CHOICE:
                return widget.currentText()
            elif paramtype == TEXT:
                return widget.toPlainText()
            elif paramtype == STRING:
                return widget.text()
            elif paramtype in [FILES, FOLDER]:
                return widget.value
            elif paramtype in [RASTER, VECTOR]:
                return widget.currentLayer()
            else:
                return widget.text()
        except Exception:
            raise  # WrongValueException()

    def setValueInWidget(self, widget, paramtype, value):
        try:
            if paramtype == BOOL:
                widget.setChecked(str(value).lower() == str(True).lower())
            elif paramtype == CHOICE:
                widget.setCurrentText(value)
            elif paramtype == TEXT:
                widget.setPlainText(value)
            elif paramtype in [FILES, FOLDER]:
                widget.value = value
            elif paramtype in [RASTER, VECTOR]:
                widget.currentLayer()  # TODO
            else:
                widget.setText(str(value))
        except Exception:
            log(f"Error setting value {value} in widget {widget} of type {paramtype}")
            pass

    def accept(self):
        for name, widget in self.widgets.items():
            try:
                value = self.valueFromWidget(
                    widget, parameterFromName(self.params, name)["type"]
                )
                QSettings().setValue(f"{SETTINGS_NAMESPACE}/{name}", value)
            except WrongValueException:
                # show warning
                return

        QDialog.accept(self)

    def reject(self):
        QDialog.reject(self)


class WrongValueException(Exception):
    pass
