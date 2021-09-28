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

from planet_explorer.pe_utils import SETTINGS_NAMESPACE, iface

BOOL = "bool"
STRING = "string"
PASSWORD = "password"
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
        self.lineEdit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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
        print(1)
        print(value)
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
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        horizontalLayout.addWidget(self.buttonBox)
        verticalLayout.addStretch()
        verticalLayout.addLayout(horizontalLayout)

        self.setLayout(verticalLayout)

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def widgetFromParameter(self, param):
        paramtype = param["type"]
        if paramtype == FILES:

            def edit(textbox):
                f = QFileDialog.getOpenFileNames(self, "Select file", "", "*.*")
                if f:
                    textbox.value = ",".join(f)

            return TextBoxWithLink("Browse", edit, None, True)
        elif paramtype == FOLDER:

            def edit(textbox):
                f = QFileDialog.getExistingDirectory(self, "Select folder", "")
                if f:
                    textbox.value = f

            return TextBoxWithLink("Browse", edit, None, True)
        elif paramtype == BOOL:
            check = QCheckBox(param["label"])
            if param["default"]:
                check.setCheckState(Qt.Checked)
            else:
                check.setCheckState(Qt.Unchecked)
            return check
        elif paramtype == CHOICE:
            combo = QComboBox()
            for option in param["options"]:
                combo.addItem(option)
            idx = combo.findText(str(param["default"]))
            combo.setCurrentIndex(idx)
            return combo
        elif paramtype == TEXT:
            textEdit = QTextEdit()
            textEdit.setPlainText(param["default"])
            return textEdit
        elif paramtype == VECTOR:
            combo = QgsMapLayerComboBox()
            combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
            return combo
        elif paramtype == RASTER:
            combo = QgsMapLayerComboBox()
            combo.setFilters(QgsMapLayerProxyModel.RasterLayer)
            return combo
        elif paramtype == PASSWORD:
            lineEdit = QLineEdit()
            lineEdit.setEchoMode(QLineEdit.Password)
            return lineEdit
        else:
            lineEdit = QLineEdit()
            lineEdit.setText(str(param["default"]))
            return lineEdit

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
                widget.setChecked(value)
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
