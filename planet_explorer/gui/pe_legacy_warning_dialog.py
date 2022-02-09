import os

from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSignal, Qt

WIDGET, BASE = uic.loadUiType(
    os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "ui", "pe_legacy_warning_dialog.ui"
    )
)


class LegacyWarningDialog(BASE, WIDGET):

    updateLegacySearch = pyqtSignal()

    def __init__(self, request, parent=None):
        super(LegacyWarningDialog, self).__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint)
        self.setupUi(self)
        self.btnUpdate.clicked.connect(self.accept)
        self.btnContinue.clicked.connect(self.reject)

        sources = request["item_types"]
        self.label4Bands.setVisible("PSScene4Band" in sources)
        self.label3Bands.setVisible("PSScene3Band" in sources)
