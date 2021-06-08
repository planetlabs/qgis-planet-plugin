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
__author__ = 'Planet Federal'
__date__ = 'September 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import logging
import json

from collections import OrderedDict, defaultdict

import analytics

from qgis.PyQt import uic

from qgis.PyQt.QtCore import (
    pyqtSignal,
    pyqtSlot,
    Qt,
    QSize
)

from qgis.PyQt.QtGui import (
    QIcon
)

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QWidget,
    QFrame,
    QRadioButton,
    QGridLayout,
    QPushButton,
    QSizePolicy
)

from qgis.core import (
    QgsMessageLog,
    Qgis
)

from qgis.gui import (
    QgsMessageBar
)

from qgis.utils import iface

from ..pe_utils import (
    is_segments_write_key_valid,
    resource_file
)
from ..planet_api.p_client import (
    PlanetClient,
)
from ..planet_api.p_specs import (
    ITEM_TYPE_SPECS,
)
from ..planet_api.p_bundles import (
    PlanetOrdersV2Bundles,
)
from .pe_orders_monitor_dockwidget import (
    show_orders_monitor
)
from .pe_gui_utils import (
    waitcursor
)

from .pe_thumbnails import (
    createCompoundThumbnail,
)

plugin_path = os.path.split(os.path.dirname(__file__))[0]
bundles_file = os.path.join(plugin_path, 'planet_api', 'resources', 'bundles.json')
order_bundles = PlanetOrdersV2Bundles(bundles_file)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

ORDERS_WIDGET, ORDERS_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_orders.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)

PLACEHOLDER_THUMB = ':/plugins/planet_explorer/thumb-placeholder-128.svg'

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

    def __init__(self,
                 bundleid,
                 name,
                 description,
                 udm
                 ):
        super().__init__()

        self.bundleid = bundleid
        self.name = name
        self.description = description
        self.udm = udm

        layout = QVBoxLayout()
        hlayout = QHBoxLayout()
        hlayout.setMargin(0)
        self.labelName = QLabel(f"<b>{name}</b>")
        hlayout.addWidget(self.labelName)
        hlayout.addStretch()
        self.chkSelected = QCheckBox()
        self.chkSelected.stateChanged.connect(self.checkStateChanged)
        hlayout.addWidget(self.chkSelected)
        layout.addLayout(hlayout)
        self.labelDescription = QLabel(description)
        self.labelDescription.setWordWrap(True)
        layout.addWidget(self.labelDescription)
        hlayouttype = QHBoxLayout()
        hlayouttype.setMargin(0)
        self.radioTiff = QRadioButton("GeoTIFF")
        self.radioTiff.setChecked(True)
        hlayouttype.addWidget(self.radioTiff)
        self.radioNitf = QRadioButton("NITF")
        hlayouttype.addWidget(self.radioNitf)
        hlayouttype.addStretch()
        layout.addLayout(hlayouttype)
        if udm:
            hlayoutudm = QHBoxLayout()
            hlayoutudm.setMargin(0)
            self.labelUdm = IconLabel("UDM2", UDM_ICON)
            hlayoutudm.addWidget(self.labelUdm)
            hlayoutudm.addStretch()
            layout.addLayout(hlayoutudm)

        self.setFrameStyle(QFrame.Panel | QFrame.Raised)
        self.setLayout(layout)
        self.checkStateChanged()

    def checkStateChanged(self):
        self.radioTiff.setEnabled(self.chkSelected.isChecked())
        self.radioNitf.setEnabled(self.chkSelected.isChecked())
        self.labelName.setEnabled(self.chkSelected.isChecked())
        self.labelDescription.setEnabled(self.chkSelected.isChecked())
        if self.udm:
            self.labelUdm.setEnabled(self.chkSelected.isChecked())
        self.selectionChanged.emit()

    def selected(self):
        return self.chkSelected.isChecked()

    def setSelected(self, selected):
        self.chkSelected.setChecked(selected)

    def filetype(self):
        if self.radioTiff.isChecked():
            return "GeoTIFF"
        else:
            return "NITF"


class PlanetOrderItemTypeWidget(QWidget):

    selectionChanged = pyqtSignal()

    def __init__(self,
                 item_type,
                 images,
                 thumbnails
                 ):
        super().__init__()

        self.item_type = item_type
        self.images = images
        self.thumbnails = thumbnails

        layout = QGridLayout()
        layout.setMargin(0)

        bboxes = [img[GEOMETRY] for img in images]
        pixmap = createCompoundThumbnail(bboxes, thumbnails)
        thumb = pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.labelThumbnail = QLabel()
        self.labelThumbnail.setPixmap(thumb)
        layout.addWidget(self.labelThumbnail, 0, 0, 3, 1)

        labelName = IconLabel(f"<b>{ITEM_TYPE_SPECS[self.item_type]['name']}</b>",
                              SATELLITE_ICON)
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

        permissions = self.images[0][PERMISSIONS]
        item_bundles = order_bundles.bundles_per_item_type(
                self.item_type, permissions=permissions)
        default = order_bundles.item_default_bundle_name(
                self.item_type)

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

        i = 0
        for bundleid in item_bundles.keys():
            bundle = item_bundles[bundleid]
            if bundle["rectification"] == "orthorectified":
                name = bundle["name"]
                description = bundle["description"]
                udm = "udm2" in bundle["auxiliaryFiles"]
                w = PlanetOrderBundleWidget(bundleid, name, description, udm)
                gridlayout.addWidget(w, i // 2, i % 2)
                w.setSelected(bundleid == default)
                w.selectionChanged.connect(lambda: self.selectionChanged.emit())
                self.bundleWidgets.append(w)
                i += 1

        layout.addLayout(gridlayout)

        self.labelUnrectified = QLabel("<b>UNRECTIFIED ASSETS</b>")
        layout.addLayout(_center(self.labelUnrectified))

        self.widgetUnrectified = QWidget()

        gridlayoutUnrect = QGridLayout()
        gridlayoutUnrect.setMargin(0)

        i = 0
        for bundleid in item_bundles.keys():
            bundle = item_bundles[bundleid]
            if bundle["rectification"] != "orthorectified":
                name = bundle["name"]
                description = bundle["description"]
                udm = "udm2" in bundle["auxiliaryFiles"]
                w = PlanetOrderBundleWidget(bundleid, name, description, udm)
                gridlayoutUnrect.addWidget(w, i // 2, i % 2)
                w.selectionChanged.connect(lambda: self.selectionChanged.emit())
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

    def _showMoreClicked(self):
        visible = self.widgetUnrectified.isVisible()
        self.widgetUnrectified.setVisible(not visible)
        self.labelUnrectified.setVisible(not visible)
        if visible:
            self.labelMore.setText('<a href="#">+ Show More</a>')
        else:
            self.labelMore.setText('<a href="#">- Show Less</a>')

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
                bundles.append(bundle)
        return bundles


class ImageReviewWidget(QFrame):

    selectedChanged = pyqtSignal()

    def __init__(self, image, thumb):
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
        self.label.setPixmap(thumb.scaled(96, 96))
        vlayout.addWidget(self.label)
        self.setLayout(vlayout)

        self.setFrameStyle(QFrame.Panel | QFrame.Raised)

    def checkStateChanged(self):
        self.selectedChanged.emit()
        self.label.setEnabled(self.checkBox.isChecked())

    def selected(self):
        return self.checkBox.isChecked()


class PlanetOrderReviewWidget(QWidget):

    selectedImagesChanged = pyqtSignal()

    def __init__(self,
                 item_type,
                 bundle_type,
                 images,
                 thumbnails,
                 add_clip
                 ):
        super().__init__()

        self.item_type = item_type
        self.bundle_type = bundle_type
        self.images = images
        self.thumbnails = thumbnails
        self.add_clip = add_clip

        layout = QVBoxLayout()
        layout.setMargin(0)
        labelName = IconLabel(f"<b>{ITEM_TYPE_SPECS[self.item_type]['name']} - {bundle_type}</b>",
                              SATELLITE_ICON)
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
        if self.add_clip:
            layout.addWidget(QLabel("<b>Clipping</b>"), 0, 1, Qt.AlignCenter)
            layout.addWidget(QLabel("Only get items delivered within your AOI"), 1, 1, Qt.AlignCenter)
            self.chkClip = QCheckBox("Clip items to AOI")
            self.chkClip.stateChanged.connect(self.checkStateChanged)
            layout.addWidget(self.chkClip, 2, 1, Qt.AlignCenter)
        layout.addWidget(QLabel("<b>Review Items</b>"), 3, 1, Qt.AlignCenter)
        layout.addWidget(QLabel("We recommend deselecting items that appear to have no pixels"), 4, 1, Qt.AlignCenter)

        sublayout = QGridLayout()
        sublayout.setMargin(0)
        for i, thumb in enumerate(self.thumbnails):
            w = ImageReviewWidget(self.images[i], thumb)
            w.selectedChanged.connect(self.selectedImagesChanged.emit)
            row = i // 4
            col = i % 4 + 1
            sublayout.addWidget(w, row, col)
            self.imgWidgets.append(w)
        layout.addLayout(sublayout, 5, 1, Qt.AlignCenter)

        self.widgetDetails.setLayout(layout)

    def checkStateChanged(self):
        self.selectedImagesChanged.emit()

    def selected_images(self):
        return [w.image for w in self.imgWidgets if w.selected()]

    def clipping(self):
        return self.chkClip.isChecked()

    def _btnDetailsClicked(self):
        if self.widgetDetails.isVisible():
            self.widgetDetails.hide()
            self.btnDetails.setIcon(EXPAND_MORE_ICON)
        else:
            self.widgetDetails.show()
            self.btnDetails.setIcon(EXPAND_LESS_ICON)
        self.updateGeometry()


class PlanetOrderSummaryOrderWidget(QWidget):

    def __init__(self,
                 summary
                 ):
        super().__init__()

        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(QLabel(f"<h3>{ITEM_TYPE_SPECS[summary['type']]['name']}</h3>"))
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
            hlayout.addStretch()
            framelayout.addLayout(hlayout)
            frame.setLayout(framelayout)
            frame.setFrameStyle(QFrame.Panel | QFrame.Raised)
            layout.addWidget(frame)
        layout.addStretch()
        self.setLayout(layout)


class PlanetOrdersDialog(ORDERS_BASE, ORDERS_WIDGET):

    NAME_HIGHLIGHT = 'QLabel { color: rgb(175, 0, 0); }'
    PLANET_COLOR_CSS = 'QLabel { border-radius: 10px; background-color: rgba(0, 157, 165, 0.25);}'
    TRANSPARENT_CSS = ''

    def __init__(self, images, thumbnails, tool_resources=None):
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
        self.btnContinueName.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        self.btnContinueAssets.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(2))
        self.btnBackReview.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        self.btnBackAssets.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.labelPageReview.linkActivated.connect(self._pageLabelClicked)
        self.labelPageAssets.linkActivated.connect(self._pageLabelClicked)
        self.labelPageName.linkActivated.connect(self._pageLabelClicked)

        images_dict = defaultdict(list)
        thumbnails_dict = defaultdict(list)
        for img, thumbnail in zip(images, thumbnails):
            item_type = img['properties']['item_type']
            images_dict[item_type].append(img)
            thumbnails_dict[item_type].append(thumbnail)

        widget = QWidget()
        self._item_type_widgets = {}
        layout = QVBoxLayout()
        layout.setMargin(0)
        for item_type in images_dict.keys():
            w = PlanetOrderItemTypeWidget(
                item_type,
                images_dict[item_type],
                thumbnails_dict[item_type]
            )
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
            self.labelOrderName.setStyleSheet('')
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

    def selectionChanged(self):
        self.update_review_items()
        self.update_summary_items()

    def update_review_items(self):
        self._order_review_widgets = []
        scrollWidget = QWidget()
        layout = QVBoxLayout()
        layout.setMargin(0)
        for item_type, widget in self._item_type_widgets.items():
            bundles = widget.bundles()
            images = widget.images
            thumbnails = widget.thumbnails
            for bundle in bundles:
                w = PlanetOrderReviewWidget(item_type, bundle["name"], images,
                                            thumbnails, self.tool_resources["aoi"] is not None)
                w.selectedImagesChanged.connect(self.update_summary_items)
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
                norders += 1
            w = PlanetOrderSummaryOrderWidget(summary)
            layout.addWidget(w)
        layout.addStretch()

        self.labelNumberOfOrders.setText(f"{norders}")

    @waitcursor
    def _process_orders(self):
        name = self.txtOrderName.text()

        aoi = None
        if self.tool_resources.get('aoi') is not None:
            aoi = json.loads(self.tool_resources.get('aoi'))
        orders = []
        for item_type, widget in self._item_type_widgets.items():
            for bundle in widget.bundles():
                w = self._review_widget_for_bundle(item_type, bundle["name"])
                images = w.selected_images()
                ids = [img["id"] for img in images]
                # IMPORTANT: The '_QGIS' suffix is needed, for the user to see
                #            their order in Explorer web app
                order = OrderedDict()  # necessary to maintain toolchain order
                order['name'] = f'{name.replace(" ", "_")}_{item_type}'
                order['order_type'] = 'partial'
                order['products'] = [
                        {
                            'item_ids': ids,
                            'item_type': item_type,
                            "product_bundle": bundle["id"]
                        }
                    ]
                order['delivery'] = {
                        'archive_filename': f'{name}_QGIS.zip',
                        'archive_type': 'zip',
                        'single_archive': True,
                    }
                order['notifications'] = {
                        'email': True
                    }

                tools = []
                if w.clipping():
                    tools.append({
                            'clip': {
                                'aoi': aoi
                            }})
                if bundle["filetype"] == "NITF":
                    tools.append({
                            "file_format": {
                                "format": "PL_NITF"
                            }})
                order['tools'] = tools
                orders.append(order)

        responses_ok = True
        for order in orders:
            resp = self._p_client.create_order(order)
            responses_ok = responses_ok and resp

            if is_segments_write_key_valid():
                analytics.track(self._p_client.user()["email"], "Order placed",
                                {
                                "name": order["name"],
                                "numItems": order["products"][0]["item_ids"],
                                "clipAoi": aoi
                                }
                                )

        if responses_ok:
            self.bar.pushMessage("", "All orders correctly processed. Open the Order Monitor to check their status", Qgis.Success)
        else:
            self.bar.pushMessage("", "Not all orders correctly processed. Open the QGIS log for more information", Qgis.Warning)

    def _log(self, msg):
        QgsMessageLog.logMessage(msg, level=Qgis.Warning)

    def _process_response(self, item_type: str, response: dict):
        if not item_type:
            self._log('Requesting order failed: no item_type')
            return False

        if not response:
            self._log(f'Requesting {item_type} order failed: '
                      f'no response data found')
            return False

        if not response.get("id"):
            self._log(f'Requesting {item_type} order failed: '
                      f'response data contains no Order ID.\n'
                      f'Order resp_data:\n{response}')
            return False

        return True

    @pyqtSlot()
    def _open_orders_monitor_dialog(self):
        show_orders_monitor()
