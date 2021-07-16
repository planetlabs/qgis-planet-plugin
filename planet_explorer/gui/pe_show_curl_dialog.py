import os
import json

from qgis.PyQt import uic
from qgis.PyQt.QtGui import QGuiApplication

from ..planet_api import (
    PlanetClient
)

from ..pe_analytics import(
    analytics_track
)

python_template = '''
import os
import requests
from requests.auth import HTTPBasicAuth

PLANET_API_KEY = %s

request = %s

# fire off the POST request
search_result = \
  requests.post(
    'https://api.planet.com/data/v1/quick-search',
    auth=HTTPBasicAuth(PLANET_API_KEY, ''),
    json=request)

'''

curl_template = '''
$ curl -u '%s: ' -d '%s' -H "Content-Type: application/json" -X POST https://api.planet.com/data/v1/quick-search
'''

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "show_curl_dialog.ui"))


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
        if self.comboType.currentText() == "cURL":
            txt = curl_template % (PlanetClient.getInstance().api_key(),
                                    json.dumps(self.request))
        else:
            txt = python_template % (PlanetClient.getInstance().api_key(),
                                    json.dumps(self.request, indent=4))
        self.textBrowser.setPlainText(txt)

    def copyClicked(self):
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.textBrowser.toPlainText())
        analytics_track("curl_request_copied")
