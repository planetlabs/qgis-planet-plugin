import os
import json
import copy

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialogButtonBox,
    QSizePolicy
)

from ..planet_api.p_node import PlanetNodeMetadata

WIDGET, BASE = uic.loadUiType(os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        "ui", "results_configuration_dialog.ui"))

class ResultsConfigurationDialog(BASE, WIDGET):

    def __init__(self, selection, parent=None):
        super(ResultsConfigurationDialog, self).__init__(parent)
        self.selection = selection
        print(selection)
        
        self.setupUi(self)

        self.checkboxes = {PlanetNodeMetadata.CLOUD_PERCENTAGE: self.chkCloudPercentage, 
                          PlanetNodeMetadata.GROUND_SAMPLE_DISTANCE: self.chkGroundSampleDistance,
                          PlanetNodeMetadata.GROUND_CONTROL: self.chkGroundControl,
                          PlanetNodeMetadata.OFF_NADIR_ANGLE: self.chkOffNadirAngle,
                          PlanetNodeMetadata.QUALITY_CATEGORY: self.chkQualityCategory, 
                          PlanetNodeMetadata.SATELLITE_ID: self.chkSatelliteId,
                          PlanetNodeMetadata.SUN_AZIMUTH: self.chkSunAzimuth,
                          PlanetNodeMetadata.SUN_ELEVATION: self.chkSunElevation}

        for chk in self.checkboxes.values():
            chk.clicked.connect(self.selection_changed)
        self._set_selected()
        
        self.btnRestoreDefaults.clicked.connect(self.restore_default)
        self.buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self.accepted)
        self.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.rejected)

    def selection_changed(self, state):
        if len(self.selection) > 3 and state != Qt.Unchecked:
            self._set_selected()          
        else:
            self.selection = []
            for key, chk in self.checkboxes.items():           
                if chk.isChecked():
                    self.selection.append(key)

    def restore_default(self):
        self.selection = [PlanetNodeMetadata.CLOUD_PERCENTAGE, PlanetNodeMetadata.GROUND_SAMPLE_DISTANCE]
        self._set_selected()

    def _set_selected(self):
        for key, chk in self.checkboxes.items():
            chk.setChecked(key in self.selection)


        

    