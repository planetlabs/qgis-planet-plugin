import os

from qgis.core import Qgis
from qgis.gui import QgsMessageBar
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QDateTime, Qt

from ..pe_analytics import SAVED_SEARCH_ACCESSED, analytics_track
from ..pe_utils import iface
from ..planet_api import PlanetClient
from .pe_filters import filters_as_text_from_request, filters_from_request
from .pe_gui_utils import waitcursor
from .pe_legacy_warning_dialog import LegacyWarningDialog

WIDGET, BASE = uic.loadUiType(
    os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "ui",
        "pe_open_saved_search_dialog.ui",
    )
)


class OpenSavedSearchDialog(BASE, WIDGET):
    def __init__(self):
        super(OpenSavedSearchDialog, self).__init__(iface.mainWindow())
        self.saved_search = None
        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.layout().insertWidget(0, self.bar)

        self.populate_saved_searches()

        self.comboSavedSearch.currentIndexChanged.connect(self.saved_search_selected)

        if self.comboSavedSearch.count():
            self.saved_search_selected(0)

        self.btnLoad.setEnabled(bool(self.comboSavedSearch.count()))
        self.btnLoad.clicked.connect(self.loadSearch)
        self.btnCancel.clicked.connect(self.reject)
        self.btnDelete.clicked.connect(self.delete_search)

    @waitcursor
    def populate_saved_searches(self):
        self.comboSavedSearch.blockSignals(True)
        self.comboSavedSearch.clear()
        res = PlanetClient.getInstance().get_searches().get()
        for search in res["searches"]:
            self.comboSavedSearch.addItem(search["name"], search)
        self.comboSavedSearch.blockSignals(False)

    def saved_search_selected(self, idx):
        request = self.comboSavedSearch.currentData()
        if request:
            analytics_track(SAVED_SEARCH_ACCESSED)
            self.set_from_request(request)
        else:
            self.txtFilters.setPlainText("")
            self.labelDateRange.setText("---")

    def delete_search(self):
        request = self.comboSavedSearch.currentData()
        if request:
            PlanetClient.getInstance().delete_search(request["id"])
            self.comboSavedSearch.removeItem(self.comboSavedSearch.currentIndex())
            self.bar.pushMessage(
                "Delete search", "Search was correctly deleted", Qgis.Success, 5
            )
        else:
            self.bar.pushMessage(
                "Delete search", "No search has been selected", Qgis.Warning, 5
            )

    def update_legacy_search(self):
        request = self.comboSavedSearch.currentData()
        cleared_request = {}
        cleared_request["filter"] = request["filter"]
        cleared_request["item_types"] = list(
            set(
                t if t not in ["PSScene3Band", "PSScene4Band"] else "PSScene"
                for t in request["item_types"]
            )
        )
        if (
            "PSScene4Band" in request["item_types"]
            or "PSScene3Band" in request["item_types"]
        ):
            if "PSScene3Band" in request["item_types"]:
                assets = PlanetClient.getInstance().psscene_asset_types_for_nbands(3)
            else:
                assets = PlanetClient.getInstance().psscene_asset_types_for_nbands(4)
            psscene_filter = {
                "config": [
                    {"config": assets, "type": "AssetFilter"},
                    {
                        "config": ["PSScene"],
                        "type": "StringInFilter",
                        "field_name": "item_type",
                    },
                ],
                "type": "AndFilter",
            }
            cleared_request["filter"] = {
                "config": [psscene_filter, request["filter"]],
                "type": "AndFilter",
            }
        cleared_request["name"] = request["name"]
        PlanetClient.getInstance().update_search(cleared_request, request["id"])
        return cleared_request

    def check_for_legacy_request(self, request):
        sources = request["item_types"]
        return "PSScene3Band" in sources or "PSScene4Band" in sources

    def set_from_request(self, request):
        filters = filters_from_request(request, "acquired")
        if filters:
            tokens = []
            gte = filters[0]["config"].get("gte")
            if gte is not None:
                tokens.append(QDateTime.fromString(gte, Qt.ISODate).date().toString())
            else:
                tokens.append("---")
            lte = filters[0]["config"].get("lte")
            if lte is not None:
                tokens.append(QDateTime.fromString(lte, Qt.ISODate).date().toString())
            else:
                tokens.append("---")
            self.labelDateRange.setText(" / ".join(tokens))
        self.txtFilters.setPlainText(filters_as_text_from_request(request))
        self.check_for_legacy_request(request)

    def loadSearch(self):
        request = self.comboSavedSearch.currentData()
        if request:
            if self.check_for_legacy_request(request):
                dlg = LegacyWarningDialog(request, self)
                ret = dlg.exec()
                if ret == dlg.Accepted:
                    self.saved_search = self.update_legacy_search()
                else:
                    self.saved_search = request
            else:
                self.saved_search = request
            self.accept()
        else:
            self.bar.pushMessage(
                "Saved search", "No search has been selected", Qgis.Warning, 5
            )
