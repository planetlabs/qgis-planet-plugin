import copy
import json
import os

from qgis.core import Qgis, QgsCoordinateReferenceSystem
from qgis.gui import QgsMapCanvas, QgsMessageBar
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QDateTime, Qt
from qgis.PyQt.QtWidgets import QDialogButtonBox, QInputDialog, QSizePolicy, QVBoxLayout

from ..pe_utils import qgsgeometry_from_geojson, iface
from ..planet_api.p_client import PlanetClient
from .pe_filters import filters_as_text_from_request, filters_from_request

WIDGET, BASE = uic.loadUiType(
    os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "ui", "save_search_dialog.ui"
    )
)


class SaveSearchDialog(BASE, WIDGET):
    def __init__(self, request, parent=None):
        super(SaveSearchDialog, self).__init__(parent)
        self.request = request
        self.request_to_save = None

        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar)

        self.buttonBox.button(QDialogButtonBox.Save).clicked.connect(self.save)
        self.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)

        self.btnCreateFolder.clicked.connect(self.createFolder)

        self.set_from_request()

        self.populate_folders()

    def createFolder(self):
        name, _ = QInputDialog.getText(self, "Save Search", "Enter folder name")
        if name and name not in self._folder_names:
            self._folder_names.append(name)
            self.populate_folders()

    def populate_folders(self):
        self.comboFolder.clear()
        self.comboFolder.addItems(self._folders())

    _folder_names = None

    def _folders(self):
        if self._folder_names is None:
            self._folder_names = [""]
            client = PlanetClient.getInstance()
            res = client.get_searches().get()
            for search in res["searches"]:
                tokens = search["name"].split("/")
                if len(tokens) > 1 and tokens[0] not in self._folder_names:
                    self._folder_names.append(tokens[0])

        return self._folder_names

    def set_from_request(self):
        filters = filters_from_request(self.request, "geometry")
        if filters:
            geom = filters[0].get("config")
            aoi_txt = json.dumps(geom)
            extent = qgsgeometry_from_geojson(aoi_txt).boundingBox()
        else:
            extent = iface.mapCanvas().fullExtent()

        layout = QVBoxLayout()
        layout.setMargin(0)
        self.canvas = QgsMapCanvas()
        layers = iface.mapCanvas().mapSettings().layers()
        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        self.canvas.setLayers(layers)
        self.canvas.setDestinationCrs(crs)
        self.canvas.setExtent(extent)
        layout.addWidget(self.canvas)
        self.widgetAOI.setLayout(layout)

        filters = filters_from_request(self.request, "acquired")
        if filters:
            gte = filters[0]["config"].get("gte")
            if gte is not None:
                self.lblStartDate.setText(
                    QDateTime.fromString(gte, Qt.ISODate).date().toString()
                )
            else:
                self.lblStartDate.setText("---")
                self.chkExcludeStart.setEnabled(False)
            lte = filters[0]["config"].get("lte")
            if lte is not None:
                self.lblEndDate.setText(
                    QDateTime.fromString(lte, Qt.ISODate).date().toString()
                )
            else:
                self.lblEndDate.setText("---")
                self.chkExcludeEnd.setEnabled(False)
        self.txtFilters.setPlainText(filters_as_text_from_request(self.request))

    def save(self):
        name = self.txtName.text()
        if len(name) == 0:
            self.bar.pushMessage("", "Invalid name", Qgis.Warning)
            return

        folder = self.comboFolder.currentText()
        if folder:
            name = f"{folder}/{name}"

        self.request_to_save = copy.deepcopy(self.request)
        self.request_to_save["name"] = name
        filters = filters_from_request(self.request, "acquired")
        if filters:
            config = filters[0]["config"]
            if self.chkExcludeStart.isChecked() and "gte" in config:
                del config["gte"]
            if self.chkExcludeEnd.isChecked() and "lte" in config:
                del config["lte"]
            self.replace_date_filter(self.request_to_save, config)
        self.accept()

    def replace_date_filter(self, request, newfilter):
        def process_filter(filterdict):
            if filterdict["type"] in ["AndFilter", "OrFilter"]:
                for subfilter in filterdict["config"]:
                    process_filter(subfilter)
            elif filterdict.get("field_name") == "acquired":
                filterdict["config"] == newfilter

        process_filter(request["filter"])
