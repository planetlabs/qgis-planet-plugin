# -*- coding: utf-8 -*-
import json
import os

from qgis.PyQt import uic
from qgis.PyQt.QtGui import QGuiApplication

from ..pe_analytics import CURL_REQUEST_COPIED, analytics_track
from ..planet_api import PlanetClient

python_template = """
import json
import requests

PLANET_ACCESS_TOKEN = "%s"

request = %s

headers = {
    "Authorization": f"Bearer {PLANET_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

# fire off the POST request
search_result = \
  requests.post(
    'https://api.planet.com/data/v1/quick-search',
    headers=headers,
    json=request)

print(json.dumps(search_result.json(), indent=2))
"""

curl_template = (
    """$ curl -H "Authorization: Bearer %s" -d '%s' -H "Content-Type: application/json" """
    """-X POST https://api.planet.com/data/v1/quick-search"""
)

WIDGET, BASE = uic.loadUiType(
    os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "ui", "show_curl_dialog.ui"
    )
)


class ShowCurlDialog(BASE, WIDGET):
    def __init__(self, request, parent=None):
        super(ShowCurlDialog, self).__init__(parent)
        self.request = request
        self.setupUi(self)

        self.btnCopy.clicked.connect(self.copyClicked)
        self.btnClose.clicked.connect(self.close)
        self.comboType.currentIndexChanged.connect(self.setText)

        self.setText()

    def setText(self):
        access_token = PlanetClient.getInstance().get_access_token()

        if self.comboType.currentText() == "cURL":
            txt = curl_template % (
                access_token,
                json.dumps(self.request),
            )
        else:
            txt = python_template % (
                access_token,
                json.dumps(self.request, indent=4),
            )
        self.textBrowser.setPlainText(txt)

    def copyClicked(self):
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.textBrowser.toPlainText())
        analytics_track(CURL_REQUEST_COPIED)
