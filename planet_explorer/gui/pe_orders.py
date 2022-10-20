# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_orders_v2.py
    ---------------------
    Date                 : September 2019
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
__date__ = "September 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import json
import logging
import os
from collections import OrderedDict, defaultdict
from functools import partial

from qgis.core import Qgis, QgsMessageLog
from qgis.gui import QgsMessageBar
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal, pyqtSlot, QSettings
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..pe_analytics import send_analytics_for_order
from ..pe_utils import (
    resource_file,
    iface,
    ENABLE_CLIP_SETTING,
    ENABLE_HARMONIZATION_SETTING,
    SETTINGS_NAMESPACE,
)
from ..planet_api.p_client import PlanetClient
from .pe_gui_utils import waitcursor
from .pe_orders_monitor_dockwidget import show_orders_monitor
from .pe_thumbnails import createCompoundThumbnail, download_thumbnail

plugin_path = os.path.split(os.path.dirname(__file__))[0]
default_bundles_file = os.path.join(
    plugin_path, "planet_api", "resources", "productBundleDefaults.json"
)
with open(default_bundles_file, "r", encoding="utf-8") as fp:
    default_bundles = json.load(fp)

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get("PYTHON_LOG_VERBOSE", None)

ORDERS_WIDGET, ORDERS_BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_orders.ui"),
    from_imports=True,
    import_from=f"{os.path.basename(plugin_path)}",
    resource_suffix="",
)

PLACEHOLDER_THUMB = ":/plugins/planet_explorer/thumb-placeholder-128.svg"

ITEM_MAX = 100

ID = "id"
GEOMETRY = "geometry"
PERMISSIONS = "_permissions"


def _icon(f):
    return QIcon(resource_file(f))


UDM_ICON = _icon("udm.svg")
FILETYPE_ICON = _icon("filetype.svg")
NITEMS_ICON = _icon("nitems.svg")
SATELLITE_ICON = _icon("satellite.svg")
CLIP_ICON = _icon("crop.svg")
HARMONIZE_ICON = _icon("harmonize.svg")
EXPAND_MORE_ICON = _icon("expand_more.svg")
EXPAND_LESS_ICON = _icon("expand_less.svg")


class IconLabel(QWidget):
    def __init__(self, text, icon):
        super().__init__()

        layout = QHBoxLayout()
        layout.setMargin(0)

        iconlabel = QLabel()
        iconlabel.setPixmap(icon.pixmap(QSize(24, 24)))
        layout.addWidget(iconlabel)

        label = QLabel(text)
        layout.addWidget(label)
        layout.addStretch()

        self.setLayout(layout)


class PlanetOrderBundleWidget(QFrame):

    selectionChanged = pyqtSignal()

    def __init__(self, bundleid, bundle, item_type):
        super().__init__()
        self.bundleid = bundleid
        self.name = bundle["name"]
        self.description = bundle["description"]
        self.udm = bundle.get("auxiliaryFiles", "").lower().startswith("udm2")
        assets = bundle["assets"]
        self.can_harmonize = (
            "ortho_analytic_4b_sr" in assets or "ortho_analytic_8b_sr" in assets
        )
        self.can_harmonize = bundle.get("canHarmonize", False)
        self.can_clip = bundle.get("canClip", False)
        self.rectified = bundle["rectification"] == "orthorectified"
        bands = []
        asset_def = PlanetClient.getInstance().asset_types_for_item_type_as_dict(
            item_type
        )
        for asset in assets:
            asset_bands = asset_def[asset].get("bands", [])
            for band in asset_bands:
                bands.append(band["name"])
        bands = set(bands)
        layout = QVBoxLayout()
        hlayout = QHBoxLayout()
        hlayout.setMargin(0)
        self.labelName = QLabel(f"<b>{self.name}</b>")
        hlayout.addWidget(self.labelName)
        hlayout.addStretch()
        self.chkSelected = QCheckBox()
        self.chkSelected.stateChanged.connect(self.checkStateChanged)
        hlayout.addWidget(self.chkSelected)
        layout.addLayout(hlayout)
        self.labelDescription = QLabel(self.description)
        self.labelDescription.setWordWrap(True)
        layout.addWidget(self.labelDescription)
        self.labelBands = QLabel(f"Bands: {', '.join([str(b) for b in bands])}")
        layout.addWidget(self.labelBands)
        hlayouttype = QHBoxLayout()
        hlayouttype.setMargin(0)
        self.radioTiff = QRadioButton("GeoTIFF")
        self.radioTiff.setChecked(True)
        self.radioTiff.toggled.connect(self.selectionChanged.emit)
        hlayouttype.addWidget(self.radioTiff)
        self.radioNitf = QRadioButton("NITF")
        self.radioNitf.toggled.connect(self.selectionChanged.emit)
        hlayouttype.addWidget(self.radioNitf)
        hlayouttype.addStretch()
        layout.addLayout(hlayouttype)
        if self.udm:
            hlayoutudm = QHBoxLayout()
            hlayoutudm.setMargin(0)
            self.labelUdm = IconLabel("UDM2", UDM_ICON)
            hlayoutudm.addWidget(self.labelUdm)
            hlayoutudm.addStretch()
            layout.addLayout(hlayoutudm)
        layout.addStretch()
        self.setFrameStyle(QFrame.Panel | QFrame.Raised)
        self.setLayout(layout)
        self.checkStateChanged()

    def checkStateChanged(self):
        self.radioTiff.setEnabled(self.chkSelected.isChecked())
        self.radioNitf.setEnabled(self.chkSelected.isChecked())
        self.labelName.setEnabled(self.chkSelected.isChecked())
        self.labelDescription.setEnabled(self.chkSelected.isChecked())
        self.labelBands.setEnabled(self.chkSelected.isChecked())
        if self.udm:
            self.labelUdm.setEnabled(self.chkSelected.isChecked())
        self.selectionChanged.emit()

    def selected(self):
        return self.chkSelected.isChecked()

    def setSelected(self, selected, emit=False):
        if not emit:
            self.blockSignals(True)
        self.chkSelected.setChecked(selected)
        self.blockSignals(False)

    def filetype(self):
        if self.radioTiff.isChecked():
            return "GeoTIFF"
        else:
            return "NITF"


class PlanetOrderItemTypeWidget(QWidget):

    selectionChanged = pyqtSignal()

    def __init__(self, item_type, images):
        super().__init__()

        self.thumbnails = []

        self.item_type = item_type
        self.images = images

        layout = QGridLayout()
        layout.setMargin(0)

        self.labelThumbnail = QLabel()
        pixmap = QPixmap(PLACEHOLDER_THUMB, "SVG")
        thumb = pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.labelThumbnail.setPixmap(thumb)
        self.labelThumbnail.setFixedSize(96, 96)
        layout.addWidget(self.labelThumbnail, 0, 0, 3, 1)

        for image in images:
            url = f"{image['_links']['thumbnail']}?api_key={PlanetClient.getInstance().api_key()}"
            download_thumbnail(url, self)

        labelName = IconLabel(
            f"<b>{PlanetClient.getInstance().item_types_names()[self.item_type]}</b>",
            SATELLITE_ICON,
        )
        labelNumItems = IconLabel(f"{len(images)} items", NITEMS_ICON)
        layout.addWidget(labelNumItems, 0, 1)
        layout.addWidget(labelName, 1, 1)

        self.btnDetails = QPushButton()
        self.btnDetails.setFlat(True)
        self.btnDetails.setIcon(EXPAND_MORE_ICON)
        self.btnDetails.clicked.connect(self._btnDetailsClicked)
        layout.addWidget(self.btnDetails, 0, 2)

        self.widgetDetails = QWidget()
        layout.addWidget(self.widgetDetails, 3, 0, 1, 3)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line, 4, 0, 1, 3)

        self.setLayout(layout)

        self.widgetDetails.hide()
        self.updateGeometry()

        self.populate_details()

    def populate_details(self):
        self.bundleWidgets = []

        client = PlanetClient.getInstance()
        permissions = [img[PERMISSIONS] for img in self.images]
        item_bundles = client.bundles_for_item_type_and_permissions(
            self.item_type, permissions=permissions
        )
        default = default_bundles.get(self.item_type, [])

        def _center(obj):
            hlayout = QHBoxLayout()
            hlayout.addStretch()
            hlayout.addWidget(obj)
            hlayout.addStretch()
            return hlayout

        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.setSpacing(20)

        layout.addLayout(_center(QLabel("<b>RECTIFIED ASSETS</b>")))

        gridlayout = QGridLayout()
        gridlayout.setMargin(0)

        assets = PlanetClient.getInstance().asset_types_for_item_type(self.item_type)
        assets_and_bands = {}
        for a in assets:
            if "bands" in a:
                assets_and_bands[a["id"]] = len(a["bands"])

        widgets = {}
        i = 0
        for bundleid, bundle in item_bundles.items():
            if bundle["rectification"] == "orthorectified":
                w = PlanetOrderBundleWidget(bundleid, bundle, self.item_type)
                gridlayout.addWidget(w, i // 2, i % 2)
                w.setSelected(False)
                widgets[bundleid] = w
                w.selectionChanged.connect(partial(self._bundle_selection_changed, w))
                self.bundleWidgets.append(w)
                i += 1

        selected = False
        for defaultid in default:
            for bundleid, w in widgets.items():
                if defaultid == bundleid:
                    w.setSelected(True)
                    selected = True
                    break
            if selected:
                break

        layout.addLayout(gridlayout)

        self.labelUnrectified = QLabel("<b>UNRECTIFIED ASSETS</b>")
        layout.addLayout(_center(self.labelUnrectified))

        self.widgetUnrectified = QWidget()

        gridlayoutUnrect = QGridLayout()
        gridlayoutUnrect.setMargin(0)

        i = 0
        for bundleid, bundle in item_bundles.items():
            if bundle["rectification"] != "orthorectified":
                w = PlanetOrderBundleWidget(bundleid, bundle, self.item_type)
                gridlayoutUnrect.addWidget(w, i // 2, i % 2)
                w.selectionChanged.connect(partial(self._bundle_selection_changed, w))
                self.bundleWidgets.append(w)
                i += 1

        self.widgetUnrectified.setLayout(gridlayoutUnrect)
        layout.addWidget(self.widgetUnrectified)

        self.labelMore = QLabel('<a href="#">+ Show More</a>')
        self.labelMore.setOpenExternalLinks(False)
        self.labelMore.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.labelMore.linkActivated.connect(self._showMoreClicked)
        layout.addLayout(_center(self.labelMore))

        self.widgetUnrectified.hide()
        self.labelUnrectified.hide()
        self.widgetDetails.setLayout(layout)

    def _bundle_selection_changed(self, widget):
        for w in self.bundleWidgets:
            if widget != w:
                w.setSelected(False, False)
        self.selectionChanged.emit()

    def _showMoreClicked(self):
        visible = self.widgetUnrectified.isVisible()
        self.widgetUnrectified.setVisible(not visible)
        self.labelUnrectified.setVisible(not visible)
        if visible:
            self.labelMore.setText('<a href="#">+ Show More</a>')
        else:
            self.labelMore.setText('<a href="#">- Show Less</a>')

    def expand(self):
        self.widgetDetails.show()
        self.btnDetails.setIcon(EXPAND_LESS_ICON)
        self.updateGeometry()

    def _btnDetailsClicked(self):
        if self.widgetDetails.isVisible():
            self.widgetDetails.hide()
            self.btnDetails.setIcon(EXPAND_MORE_ICON)
        else:
            self.widgetDetails.show()
            self.btnDetails.setIcon(EXPAND_LESS_ICON)
        self.updateGeometry()

    def bundles(self):
        bundles = []
        for w in self.bundleWidgets:
            if w.selected():
                bundle = {}
                bundle["id"] = w.bundleid
                bundle["name"] = w.name
                bundle["filetype"] = w.filetype()
                bundle["udm"] = w.udm
                bundle["rectified"] = w.rectified
                bundle["canharmonize"] = w.can_harmonize
                bundle["canclip"] = w.can_clip
                bundles.append(bundle)
        return bundles

    def set_thumbnail(self, img):
        thumbnail = QPixmap(img)
        self.thumbnails.append(
            thumbnail.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

        if len(self.images) == len(self.thumbnails):
            bboxes = [img[GEOMETRY] for img in self.images]
            pixmap = createCompoundThumbnail(bboxes, self.thumbnails)
            thumb = pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.labelThumbnail.setPixmap(thumb)


class ImageReviewWidget(QFrame):

    selectedChanged = pyqtSignal()

    def __init__(self, image):
        super().__init__()

        self.image = image
        self.checkBox = QCheckBox()
        self.checkBox.setChecked(True)
        self.checkBox.stateChanged.connect(self.checkStateChanged)
        hlayout = QHBoxLayout()
        hlayout.setMargin(0)
        hlayout.addStretch()
        hlayout.addWidget(self.checkBox)
        vlayout = QVBoxLayout()
        vlayout.setMargin(0)
        vlayout.addLayout(hlayout)
        self.label = QLabel()
        pixmap = QPixmap(PLACEHOLDER_THUMB, "SVG")
        thumb = pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(thumb)
        self.label.setFixedSize(96, 96)

        url = f"{image['_links']['thumbnail']}?api_key={PlanetClient.getInstance().api_key()}"
        download_thumbnail(url, self)
        vlayout.addWidget(self.label)
        self.setLayout(vlayout)

        self.setFrameStyle(QFrame.Panel | QFrame.Raised)

    def checkStateChanged(self):
        self.selectedChanged.emit()
        self.label.setEnabled(self.checkBox.isChecked())

    def selected(self):
        return self.checkBox.isChecked()

    def set_thumbnail(self, img):
        self.thumbnail = QPixmap(img)
        thumb = self.thumbnail.scaled(
            96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.label.setPixmap(thumb)


class PlanetOrderReviewWidget(QWidget):

    selectedImagesChanged = pyqtSignal()

    def __init__(self, item_type, bundle_type, images, add_clip, add_harmonize):
        super().__init__()

        self.item_type = item_type
        self.bundle_type = bundle_type
        self.images = images
        self.add_clip = add_clip
        self.add_harmonize = add_harmonize

        layout = QVBoxLayout()
        layout.setMargin(0)
        item_types_names = PlanetClient.getInstance().item_types_names()
        labelName = IconLabel(
            f"<b>{item_types_names[self.item_type]} - {bundle_type}</b>",
            SATELLITE_ICON,
        )
        labelNumItems = IconLabel(f"{len(images)} items", NITEMS_ICON)
        gridlayout = QGridLayout()
        gridlayout.setMargin(0)
        gridlayout.addWidget(labelNumItems, 0, 0)
        self.btnDetails = QPushButton()
        self.btnDetails.setFlat(True)
        self.btnDetails.setIcon(EXPAND_MORE_ICON)
        self.btnDetails.clicked.connect(self._btnDetailsClicked)
        gridlayout.addWidget(self.btnDetails, 0, 2)
        gridlayout.addWidget(labelName, 1, 0, 1, 3)
        layout.addLayout(gridlayout)
        self.widgetDetails = QWidget()
        layout.addWidget(self.widgetDetails)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        self.setLayout(layout)

        self.widgetDetails.hide()
        self.updateGeometry()

        self.populate_details()

    def populate_details(self):
        self.imgWidgets = []
        layout = QGridLayout()
        layout.setMargin(0)
        layout.setVerticalSpacing(15)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(2, 1)
        self.chkClip = None
        self.chkHarmonize = None
        if self.add_clip:
            layout.addWidget(QLabel("<b>Clipping</b>"), 0, 1, Qt.AlignCenter)
            layout.addWidget(
                QLabel("Only get items delivered within your AOI"), 1, 1, Qt.AlignCenter
            )
            self.chkClip = QCheckBox("Clip items to AOI")
            enabled = QSettings().value(
                f"{SETTINGS_NAMESPACE}/{ENABLE_CLIP_SETTING}", False
            )
            self.chkClip.setChecked(str(enabled).lower() == str(True).lower())
            self.chkClip.stateChanged.connect(self.checkStateChanged)
            layout.addWidget(self.chkClip, 2, 1, Qt.AlignCenter)
        if self.add_harmonize:
            layout.addWidget(QLabel("<b>Harmonization</b>"), 3, 1, Qt.AlignCenter)
            layout.addWidget(
                QLabel(
                    "Radiometrically harmonize imagery captured by one satellite "
                    "instrument type to imagery capture by another"
                ),
                4,
                1,
                Qt.AlignCenter,
            )
            self.chkHarmonize = QCheckBox("Harmonize")
            enabled = QSettings().value(
                f"{SETTINGS_NAMESPACE}/{ENABLE_HARMONIZATION_SETTING}", False
            )
            self.chkHarmonize.setChecked(str(enabled).lower() == str(True).lower())
            self.chkHarmonize.stateChanged.connect(self.checkStateChanged)
            layout.addWidget(self.chkHarmonize, 5, 1, Qt.AlignCenter)
        layout.addWidget(QLabel("<b>Review Items</b>"), 6, 1, Qt.AlignCenter)
        layout.addWidget(
            QLabel("We recommend deselecting items that appear to have no pixels"),
            7,
            1,
            Qt.AlignCenter,
        )

        sublayout = QGridLayout()
        sublayout.setMargin(0)
        for i, img in enumerate(self.images):
            w = ImageReviewWidget(img)
            w.selectedChanged.connect(self.selectedImagesChanged.emit)
            row = i // 4
            col = i % 4 + 1
            sublayout.addWidget(w, row, col)
            self.imgWidgets.append(w)
        layout.addLayout(sublayout, 8, 1, Qt.AlignCenter)

        self.widgetDetails.setLayout(layout)

    def checkStateChanged(self):
        self.selectedImagesChanged.emit()

    def selected_images(self):
        return [w.image for w in self.imgWidgets if w.selected()]

    def clipping(self):
        if self.chkClip is None:
            return False
        else:
            return self.chkClip.isChecked()

    def harmonize(self):
        if self.chkHarmonize is None:
            return False
        else:
            return self.chkHarmonize.isChecked()

    def _btnDetailsClicked(self):
        if self.widgetDetails.isVisible():
            self.widgetDetails.hide()
            self.btnDetails.setIcon(EXPAND_MORE_ICON)
        else:
            self.widgetDetails.show()
            self.btnDetails.setIcon(EXPAND_LESS_ICON)
        self.updateGeometry()

    def expand(self):
        self.widgetDetails.show()
        self.btnDetails.setIcon(EXPAND_LESS_ICON)
        self.updateGeometry()


class PlanetOrderSummaryOrderWidget(QWidget):
    def __init__(self, summary):
        super().__init__()

        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(
            QLabel(
                f"<h3>{PlanetClient.getInstance().item_types_names()[summary['type']]}</h3>"
            )
        )
        for bundle in summary["bundles"]:
            frame = QFrame()
            framelayout = QVBoxLayout()
            framelayout.addWidget(IconLabel(f"{bundle['numitems']} items", NITEMS_ICON))
            framelayout.addWidget(QLabel(f"<b>{bundle['name']}</b>"))
            hlayout = QHBoxLayout()
            hlayout.setMargin(0)
            fileLabel = IconLabel(bundle["filetype"], FILETYPE_ICON)
            hlayout.addWidget(fileLabel)
            if bundle["udm"]:
                udmLabel = IconLabel("UDM2", UDM_ICON)
                hlayout.addWidget(udmLabel)
            if bundle["clipping"]:
                clipLabel = IconLabel("", CLIP_ICON)
                hlayout.addWidget(clipLabel)
            if bundle["harmonize"]:
                harmonizeLabel = IconLabel("", HARMONIZE_ICON)
                hlayout.addWidget(harmonizeLabel)
            hlayout.addStretch()
            framelayout.addLayout(hlayout)
            frame.setLayout(framelayout)
            frame.setFrameStyle(QFrame.Panel | QFrame.Raised)
            layout.addWidget(frame)
        layout.addStretch()
        self.setLayout(layout)


class PlanetOrdersDialog(ORDERS_BASE, ORDERS_WIDGET):

    NAME_HIGHLIGHT = "QLabel { color: rgb(175, 0, 0); }"
    PLANET_COLOR_CSS = (
        "QLabel { border-radius: 10px; background-color: rgba(0, 157, 165, 0.25);}"
    )
    TRANSPARENT_CSS = ""

    def __init__(self, images, tool_resources=None):
        super().__init__(parent=iface.mainWindow())

        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar)

        layout = QVBoxLayout()
        layout.setMargin(0)
        self.widgetSummaryItems = QWidget()
        self.widgetSummaryItems.setLayout(layout)
        self.scrollAreaSummary.setWidget(self.widgetSummaryItems)

        self._p_client = PlanetClient.getInstance()
        self.tool_resources = tool_resources

        self.txtOrderName.textChanged.connect(self._nameChanged)
        self.btnPlaceOrder.clicked.connect(self._btnPlaceOrderClicked)
        self.btnPlaceOrderReview.clicked.connect(self._btnPlaceOrderClicked)
        self.btnSTAC.clicked.connec(self._btnSTACClicked)
        self.btnContinueName.clicked.connect(
            lambda: self.stackedWidget.setCurrentIndex(1)
        )
        self.btnContinueAssets.clicked.connect(
            lambda: self.stackedWidget.setCurrentIndex(2)
        )
        self.btnBackReview.clicked.connect(
            lambda: self.stackedWidget.setCurrentIndex(1)
        )
        self.btnBackAssets.clicked.connect(
            lambda: self.stackedWidget.setCurrentIndex(0)
        )
        self.labelPageReview.linkActivated.connect(self._pageLabelClicked)
        self.labelPageAssets.linkActivated.connect(self._pageLabelClicked)
        self.labelPageName.linkActivated.connect(self._pageLabelClicked)


        self.stac_order = False

        images_dict = defaultdict(list)
        # thumbnails_dict = defaultdict(list)
        for img in images:
            item_type = img["properties"]["item_type"]
            images_dict[item_type].append(img)
            # thumbnails_dict[item_type].append(thumbnail)

        widget = QWidget()
        self._item_type_widgets = {}
        layout = QVBoxLayout()
        layout.setMargin(0)
        for i, item_type in enumerate(images_dict.keys()):
            w = PlanetOrderItemTypeWidget(item_type, images_dict[item_type])
            if i == 0:
                w.expand()
            w.selectionChanged.connect(self.selectionChanged)
            self._item_type_widgets[item_type] = w
            layout.addWidget(w)

        layout.addStretch()
        widget.setLayout(layout)

        self.scrollArea.setWidget(widget)

        self.stackedWidget.currentChanged.connect(self._panelChanged)

        self.stackedWidget.setCurrentIndex(0)
        self._panelChanged(0)
        self._nameChanged()

        self.selectionChanged()

    def _pageLabelClicked(self, url):
        page = int(url)
        self.stackedWidget.setCurrentIndex(page)

    def _panelChanged(self, current):
        labels = [self.labelPageName, self.labelPageAssets, self.labelPageReview]
        for label in labels:
            label.setStyleSheet(self.TRANSPARENT_CSS)
        labels[current].setStyleSheet(self.PLANET_COLOR_CSS)

    def _nameChanged(self):
        textOk = bool(self.txtOrderName.text())
        if not textOk:
            self.labelOrderName.setStyleSheet(self.NAME_HIGHLIGHT)
            self.labelOrderNameSummary.setText("Undefined")
        else:
            self.labelOrderName.setStyleSheet("")
            self.labelOrderNameSummary.setText(self.txtOrderName.text())

        self.btnPlaceOrder.setEnabled(textOk)
        self.btnContinueName.setEnabled(textOk)
        self.labelPageAssets.setEnabled(textOk)
        self.labelPageReview.setEnabled(textOk)

    @pyqtSlot()
    def _btnPlaceOrderClicked(self):
        self.stackedWidget.setEnabled(False)
        self.btnPlaceOrder.setEnabled(False)

        self._process_orders()

        self.stackedWidget.setEnabled(True)
        self.btnPlaceOrder.setEnabled(True)

    def _btnSTACClicked(self):
        self.stac_order = not self.stac_order

    def selectionChanged(self):
        self.update_review_items()
        self.update_summary_items()

    def update_review_items(self):
        self._order_review_widgets = []
        scrollWidget = QWidget()
        layout = QVBoxLayout()
        layout.setMargin(0)
        first = True
        for item_type, widget in self._item_type_widgets.items():
            bundles = widget.bundles()
            images = widget.images
            for bundle in bundles:
                add_clip = self.tool_resources["aoi"] is not None and bundle["canclip"]
                w = PlanetOrderReviewWidget(
                    item_type, bundle["name"], images, add_clip, bundle["canharmonize"]
                )
                w.selectedImagesChanged.connect(self.update_summary_items)
                if first:
                    w.expand()
                    first = False
                self._order_review_widgets.append(w)
                layout.addWidget(w)
        layout.addStretch()
        scrollWidget.setLayout(layout)
        self.scrollAreaReview.setWidget(scrollWidget)

    def _review_widget_for_bundle(self, item_type, bundle_type):
        for w in self._order_review_widgets:
            if w.item_type == item_type and w.bundle_type == bundle_type:
                return w

    def update_summary_items(self):
        layout = self.widgetSummaryItems.layout()
        for i in reversed(range(layout.count())):
            widget = layout.takeAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        norders = 0
        for item_type, widget in self._item_type_widgets.items():
            summary = {}
            summary["type"] = item_type
            summary["bundles"] = widget.bundles()
            for bundle in summary["bundles"]:
                w = self._review_widget_for_bundle(item_type, bundle["name"])
                images = w.selected_images()
                bundle["numitems"] = len(images)
                bundle["clipping"] = w.clipping()
                bundle["harmonize"] = w.harmonize()
                norders += 1
            w = PlanetOrderSummaryOrderWidget(summary)
            layout.addWidget(w)
        layout.addStretch()

        self.labelNumberOfOrders.setText(f"{norders}")

    @waitcursor
    def _process_orders(self):
        allbundles = []
        for widget in self._item_type_widgets.values():
            allbundles.extend(widget.bundles())
        if not allbundles:
            self.bar.pushMessage("", "No bundles have been selected", Qgis.Warning)
            return
        name = self.txtOrderName.text()

        aoi = None
        if self.tool_resources.get("aoi") is not None:
            aoi = json.loads(self.tool_resources.get("aoi"))
        orders = []
        for item_type, widget in self._item_type_widgets.items():
            for bundle in widget.bundles():
                w = self._review_widget_for_bundle(item_type, bundle["name"])
                images = w.selected_images()
                ids = [img["id"] for img in images]
                # IMPORTANT: The '_QGIS' suffix is needed, for the user to see
                #            their order in Explorer web app
                order = OrderedDict()  # necessary to maintain toolchain order
                order["name"] = f'{name.replace(" ", "_")}_{item_type}'
                order["order_type"] = "partial"
                order["products"] = [
                    {
                        "item_ids": ids,
                        "item_type": item_type,
                        "product_bundle": bundle["id"],
                    }
                ]
                order["delivery"] = {
                    "archive_filename": f"{name}_QGIS.zip",
                    "archive_type": "zip",
                    "single_archive": True,
                }
                order["notifications"] = {"email": True}

                if self.stac_order:
                    order["metadata"] = {
                        "stac": {}
                    }
                tools = []
                if w.clipping():
                    tools.append({"clip": {"aoi": aoi}})
                if w.harmonize():
                    tools.append({"harmonize": {"target_sensor": "Sentinel-2"}})
                if bundle["filetype"] == "NITF":
                    tools.append({"file_format": {"format": "PL_NITF"}})
                order["tools"] = tools
                orders.append(order)

        responses_ok = True
        for order in orders:
            resp = self._p_client.create_order(order)
            responses_ok = responses_ok and resp
            send_analytics_for_order(order)

        if responses_ok:
            self.bar.pushMessage(
                "",
                "All orders correctly processed. Open the Order Monitor to check their"
                " status",
                Qgis.Success,
            )
        else:
            self.bar.pushMessage(
                "",
                "Not all orders correctly processed. Open the QGIS log for more"
                " information",
                Qgis.Warning,
            )

    def _log(self, msg):
        QgsMessageLog.logMessage(msg, level=Qgis.Warning)

    def _process_response(self, item_type: str, response: dict):
        if not item_type:
            self._log("Requesting order failed: no item_type")
            return False

        if not response:
            self._log(f"Requesting {item_type} order failed: no response data found")
            return False

        if not response.get("id"):
            self._log(
                f"Requesting {item_type} order failed: "
                "response data contains no Order ID.\n"
                f"Order resp_data:\n{response}"
            )
            return False

        return True

    @pyqtSlot()
    def _open_orders_monitor_dialog(self):
        show_orders_monitor()
