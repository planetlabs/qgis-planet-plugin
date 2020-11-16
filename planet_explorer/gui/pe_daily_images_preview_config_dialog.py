import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QFileDialog


WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "ui", "pe_daily_images_preview_config_dialog.ui"))


class DailyImagesPreviewConfigDialog(BASE, WIDGET):

    def __init__(self, parent=None):
        super(DailyImagesPreviewConfigDialog, self).__init__(parent)
        self.footprintsFilename = None
        self.layerName = None
        self.setupUi(self)

        self.btnBrowse.clicked.connect(self.browse)
        self.chkAddToCatalog.stateChanged.connect(self.add_to_catalog_changed)
        self.radioGpkgLayer.toggled.connect(self.radio_changed)

        self.radio_changed()
        self.add_to_catalog_changed()

    def radio_changed(self):
        self.txtFilename.setEnabled(self.radioGpkgLayer.isChecked())

    def add_to_catalog_changed(self):
        self.txtLayerName.setEnabled(self.chkAddToCatalog.isChecked())

    def browse(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Footprints filename", "", "GPKG Files (*.gpkg)")
        if filename:
            self.txtFilename.setText(filename)

    def accept(self):
        if self.radioGpkgLayer.isChecked():
            filename = self.txtFilename.text()
            if filename:
                self.footprintsFilename = filename
            else:
                self.txtFilename.setStyleSheet(
                    "QLineEdit { background: rgba(255, 0, 0, 150); }")
                return
        if self.chkAddToCatalog.isChecked():
            name = self.txtLayerName.text()
            if name:
                self.layerName = name
            else:
                self.txtLayerName.setStyleSheet(
                    "QLineEdit { background: rgba(255, 0, 0, 150); }")
                return
        super().accept()
