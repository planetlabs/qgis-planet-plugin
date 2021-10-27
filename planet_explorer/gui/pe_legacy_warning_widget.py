import os

from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QPalette

from planet_explorer.pe_utils import PLANET_COLOR, open_link_with_browser

WIDGET, BASE = uic.loadUiType(
    os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "ui", "pe_legacy_warning_widget.ui"
    )
)

text_without_id = """
<p><span style=" font-weight:600;">
Your saved search includes legacy imagery types</span></p>
<p>PSScene3Bands, PSScene4Bands</p>
"""
text_with_id = """
<p><span style=" font-weight:600;">
Legacy search filters are disabled because we've updated PlanetScope items to PSScene</span></p>
"""


class LegacyWarningWidget(BASE, WIDGET):

    updateLegacySearch = pyqtSignal()

    def __init__(self, parent=None):
        super(LegacyWarningWidget, self).__init__(parent)
        self.setupUi(self)
        palette = self.btnUpdate.palette()
        palette.setColor(QPalette.Button, PLANET_COLOR)
        self.btnUpdate.setPalette(palette)
        self.btnUpdate.clicked.connect(self.update_search)
        self.labelLink.linkActivated.connect(self.link_clicked)

    def link_clicked(self):
        url = "https://developers.planet.com/docs/data/psscene/faq"
        open_link_with_browser(url)

    def update_search(self):
        self.updateLegacySearch.emit()

    def set_has_image_id(self, has_id):
        if has_id:
            self.textBrowser.setHtml(text_with_id)
            self.btnUpdate.setText("Clear item Ids to enable filters")
        else:
            self.textBrowser.setHtml(text_without_id)
            self.btnUpdate.setText("Click here to update search")
