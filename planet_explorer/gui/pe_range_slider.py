# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_range_slider.py
    ---------------------
    Date                 : August 2019
    Copyright            : (C) 2019 Planet Inc, https://planet.com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
__author__ = "Planet Federal"
__date__ = "August 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import logging
import os
import sys

from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSignal, pyqtSlot
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import QLabel, QStyleFactory

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

plugin_path = os.path.split(os.path.dirname(__file__))[0]

try:
    from .range_slider import RangeSlider
except ModuleNotFoundError:
    sys.path.insert(0, os.path.abspath(os.path.join(plugin_path, "gui")))
    # noinspection PyUnresolvedReferences
    from range_slider import RangeSlider

SLIDER_WIDGET, SLIDER_BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_range_slider_base.ui"),
    from_imports=True,
    import_from=f"{os.path.basename(plugin_path)}",
    resource_suffix="",
)


# noinspection PyPep8Naming
class PlanetExplorerRangeSlider(SLIDER_BASE, SLIDER_WIDGET):

    rangeSlider: RangeSlider
    lblTitle: QLabel
    lblRange: QLabel
    lblMin: QLabel
    lblMax: QLabel

    rangeChanged = pyqtSignal(float, float)

    def __init__(
        self,
        parent=None,
        title="",
        filter_key="",
        prefix="",
        suffix="",
        minimum=0.0,
        maximum=100.0,
        low=None,
        high=None,
        step=None,
        precision=1,
    ):
        """
        Widget that wraps two QSliders (based upon RangeSlider) that produce a
        control widget for defining a value range. Offers visual feedback on
        active vaule range and minimum and maximum values.

        :param parent: Parent widget
        :type parent: QWidget
        :param title: Title of value range
        :param suffix: Any suffix to the value, e.g. km, miles, degrees
        :param prefix: Any prefix to all vaule labels (need to include spaces)
        :param minimum: Minimum value for slider
        :type minimum: float | int
        :param maximum: Maximum value for the slider
        :type maximum: float | int
        :param low: Low value for the slider range
        :type low: float | int
        :param high: High value for the slider range
        :type high: float | int
        :param step: Slider step increment (will be adjusted by precision)
        :type step: int
        :param precision: A 10-based value to apply to the value range to
        ensure its result is an integer (as slider only works with integers),
        e.g. precision of 10 makes -0.5 -> 0.5 floats become -5 -> 5 integers.
        :type precision: int
        """
        super().__init__(parent=parent)

        self.filter_key = filter_key
        self.suffix = suffix
        self.prefix = prefix
        self.min = minimum
        self.max = maximum
        self.precision = precision

        self.setupUi(self)

        self.lblTitle.setText(title)

        # Verify precision; nix further setup if invalid and disable slider,
        #   but... keep UI so dev/user is informed
        min_test = minimum * self.precision
        max_test = maximum * self.precision
        if not (int(min_test) == min_test and int(max_test) == max_test):
            self.lblRange.setText("(precision invalid)")
            self.rangeSlider.setEnabled(False)
            return

        # noinspection PyUnresolvedReferences
        self.rangeSlider.rangeChanged[int, int].connect(self.updateMinMaxLabels)
        self.rangeSlider.activeRangeChanged[int, int].connect(self.updateRangeLabel)
        self.rangeSlider.finalRangeChanged[int, int].connect(self.emitRangeChanged)

        # Set some defaults for low, high
        init_low = low or minimum
        init_high = high or maximum

        # Block signals only for this widget
        # Let setting defaults for rangeSlider auto-update labels
        self.blockSignals(True)

        self.rangeSlider.setSingleStep(
            int(step * self.precision if step else 1 * self.precision)
        )
        self.rangeSlider.setPageStep(
            int(step * self.precision if step else 1 * self.precision)
        )
        self.rangeSlider.setMinimum(int(minimum * self.precision))
        self.rangeSlider.setMaximum(int(maximum * self.precision))
        self.rangeSlider.setLow(int(init_low * self.precision))
        self.rangeSlider.setHigh(int(init_high * self.precision))
        self.updateRangeLabel()

        self.blockSignals(False)

        # This makes the slider look OK (and like Planet Explorer web app's)
        #   across multiple platforms
        self.rangeSlider.setTickPosition(self.rangeSlider.TicksBelow)
        self.rangeSlider.setTickInterval(
            int((self.rangeSlider.maximum() - self.rangeSlider.minimum()) / 2)
        )

        # Scale down min/max and low/high font size
        fnt: QFont = self.lblTitle.font()
        fnt.setPointSizeF(fnt.pointSizeF() - 1.0)
        fnt.setBold(False)

        self.lblMin.setFont(fnt)
        self.lblMax.setFont(fnt)
        self.lblRange.setFont(fnt)

    def validRange(self, value, minimum=None, maximum=None):
        min_n = minimum or self.rangeSlider.minimum()
        max_n = maximum or self.rangeSlider.maximum()
        return min_n <= value <= max_n

    def range(self):
        return (
            int(self.rangeSlider.low() / self.precision),
            int(self.rangeSlider.high() / self.precision),
        )

    @pyqtSlot(float, float)
    def setRange(self, low, high):
        self.setRangeLow(low)
        self.setRangeHigh(high)

    @pyqtSlot(float)
    def setRangeLow(self, low):
        self.rangeSlider.setLow(int(low * self.precision))

    @pyqtSlot(float)
    def setRangeHigh(self, high):
        self.rangeSlider.setHigh(int(high * self.precision))

    @pyqtSlot(int, int)
    def emitRangeChanged(self, low, high):
        # noinspection PyUnresolvedReferences
        self.rangeChanged.emit(low / self.precision, high / self.precision)

    def updateRangeLabel(self):
        # Validate range values
        invalid = ""
        if not (
            self.validRange(self.rangeSlider.low())
            and self.validRange(self.rangeSlider.high())
        ):
            invalid = " (invalid)"
            self.rangeSlider.blockSignals(True)
            self.rangeSlider.setLow(self.rangeSlider.minimum())
            self.rangeSlider.setHigh(self.rangeSlider.maximum())
            self.rangeSlider.blockSignals(False)

        self.lblRange.setText(
            f"{self.prefix}"
            f"{self.rangeSlider.low() / self.precision}"
            " - "
            f"{self.rangeSlider.high() / self.precision}"
            f"{self.suffix}"
            f"{invalid}"
        )

    def updateMinimumLabel(self):
        self.lblMin.setText(
            f"{self.prefix}{self.rangeSlider.minimum() / self.precision}{self.suffix}"
        )

    def updateMaximumLabel(self):
        self.lblMax.setText(
            f"{self.prefix}{self.rangeSlider.maximum() / self.precision}{self.suffix}"
        )

    def updateMinMaxLabels(self):
        self.updateMinimumLabel()
        self.updateMaximumLabel()

    def updateLabels(self):
        self.updateMinimumLabel()
        self.updateMaximumLabel()
        self.updateRangeLabel()


if __name__ == "__main__":
    import sys

    from qgis.PyQt.QtWidgets import QApplication, QDialog, QVBoxLayout

    @pyqtSlot(float, float)
    def echo_final_range(low, high):
        print(f"final... low: {low}, high: {high}")

    app = QApplication(sys.argv)

    # app.setStyle(QStyleFactory.create("Macintosh"))
    app.setStyle(QStyleFactory.create("Fusion"))
    # app.setStyle(QStyleFactory.create("Windows"))
    print(f"app styles: {QStyleFactory.keys()}")
    print(f"app style: {app.style().metaObject().className()}")

    # wrap in dialog
    dlg = QDialog()
    dlg.setWindowTitle("RangeSlider test")
    layout = QVBoxLayout(dlg)

    range_slider = PlanetExplorerRangeSlider(
        parent=dlg,
        title="My value",
        filter_key="my_value",
        prefix="",
        suffix="˚",
        minimum=0,
        maximum=360,
        low=0,
        high=360,
        step=1,
        precision=1,
    )

    # noinspection PyUnresolvedReferences
    range_slider.rangeChanged.connect(echo_final_range)

    layout.addWidget(range_slider)
    # layout.setMargin(0)

    dlg.show()
    app.exec_()
