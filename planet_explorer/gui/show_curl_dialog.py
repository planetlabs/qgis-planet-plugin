import os
import json

from qgis.PyQt import uic

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "show_curl_dialog.ui"))

class ShowCurlDialog(BASE, WIDGET):

    def __init__(self, request, parent=None):
        super(ShowCurlDialog, self).__init__(parent)
        self.request = request
        self.setupUi(self)

        txt = json.dumps(request, indent = 4)
        self.textBrowser.setPlainText(txt)
        self.btnCopy.clicked.connect(self.copyClicked)
        self.btnClose.clicked.connect(self.close)
    
    def copyClicked(self):
    	pass
        