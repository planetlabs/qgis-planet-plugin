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
    QPushButton
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

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

ORDER_ITEM_WIDGET, ORDER_ITEM_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_orders_item_type.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)

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

ASSET_TYPES = [("Surface Reflectance", "description", True),
               ("Analytic Radiance (TOAR)", "description", True)]

UDM_ICON = resource_file("udm.svg")
FILETYPE_ICON = resource_file("filetype.svg")
NITEMS_ICON = resource_file("nitems.svg")
SATELLITE_ICON = resource_file("satellite.svg")
CLIP_ICON = resource_file("crop.svg")


class IconLabel(QWidget):

    def __init__(self, text, icon):
        super().__init__()

        layout = QHBoxLayout()
        layout.setMargin(0)

        iconlabel = QLabel()
        iconlabel.setPixmap(QIcon(icon).pixmap(QSize(24, 24)))
        layout.addWidget(iconlabel)

        label = QLabel(text)
        layout.addWidget(label)
        layout.addStretch()

        self.setLayout(layout)


class PlanetOrderAssetWidget(QFrame):

    selectionChanged = pyqtSignal()

    def __init__(self,
                 name,
                 description,
                 udm
                 ):
        super().__init__()

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
        layout.addWidget(self.labelDescription)
        hlayouttype = QHBoxLayout()
        hlayouttype.setMargin(0)
        self.radioTiff = QRadioButton("GeoTIFF")
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

        self.btnDetails = QPushButton("Show details")
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
        self.assetWidgets = []
        layout = QGridLayout()
        layout.setMargin(0)
        for i, typ in enumerate(ASSET_TYPES):
            w = PlanetOrderAssetWidget(*typ)
            row = i // 2
            col = i % 2
            layout.addWidget(w, row, col)
            w.setSelected(i == 0)
            w.selectionChanged.connect(lambda: self.selectionChanged.emit())
            self.assetWidgets.append(w)

        self.widgetDetails.setLayout(layout)

    def _btnDetailsClicked(self):
        if self.widgetDetails.isVisible():
            self.widgetDetails.hide()
            self.btnDetails.setText("Show Details")
        else:
            self.widgetDetails.show()
            self.btnDetails.setText("Hide Details")
        self.updateGeometry()

    def get_order(self):
        order_details = {}
        valid = self.validate()

        ids = self.selected_images_ids()
        order_details['valid'] = valid
        order_details['item_ids'] = ids
        order_details['bundle_name'] = self._order_bundle_name
        order_details['bundle'] = self._order_bundle

        tools = []
        tool_ckbxs = self.grpBoxTools.findChildren(QCheckBox)
        for tool in tool_ckbxs:
            if tool.isChecked():
                tools.append(tool.property('tool'))

        order_details['tools'] = tools

        log.debug(
            f'Ordering {self.item_type}...\n'
            f'  valid: {valid}\n'
            f'  item count: {len(ids)}\n'
            f'  type_ids: {ids}\n'
            f'  bundle_name: {self._order_bundle_name}\n'
            f'  tools: {tools}'
        )

        return order_details

    def assets(self):
        assets = []
        for w in self.assetWidgets:
            if w.selected():
                asset = {}
                asset["name"] = w.name
                asset["filetype"] = w.filetype()
                asset["udm"] = w.udm
                assets.append(asset)
        return assets


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
                 asset_type,
                 images,
                 thumbnails,
                 add_clip
                 ):
        super().__init__()

        self.item_type = item_type
        self.asset_type = asset_type
        self.images = images
        self.thumbnails = thumbnails
        self.add_clip = add_clip

        layout = QVBoxLayout()
        layout.setMargin(0)
        labelName = IconLabel(f"<b>{ITEM_TYPE_SPECS[self.item_type]['name']} - {asset_type}</b>",
                              SATELLITE_ICON)
        labelNumItems = IconLabel(f"{len(images)} items", NITEMS_ICON)
        gridlayout = QGridLayout()
        gridlayout.setMargin(0)
        gridlayout.addWidget(labelNumItems, 0, 0)
        self.btnDetails = QPushButton("Show images")
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
            self.btnDetails.setText("Show Images")
        else:
            self.widgetDetails.show()
            self.btnDetails.setText("Hide Images")
        self.updateGeometry()


class PlanetOrderSummaryOrderWidget(QWidget):

    def __init__(self,
                 summary
                 ):
        super().__init__()

        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(QLabel(f"<h3>{ITEM_TYPE_SPECS[summary['type']]['name']}</h3>"))
        for asset in summary["assets"]:
            frame = QFrame()
            framelayout = QVBoxLayout()
            framelayout.addWidget(IconLabel(f"{asset['numitems']} items", NITEMS_ICON))
            framelayout.addWidget(QLabel(f"<b>{asset['name']}</b>"))
            hlayout = QHBoxLayout()
            hlayout.setMargin(0)
            fileLabel = IconLabel(asset["filetype"], FILETYPE_ICON)
            hlayout.addWidget(fileLabel)
            if asset["udm"]:
                udmLabel = IconLabel("UDM2", UDM_ICON)
                hlayout.addWidget(udmLabel)
            if asset["clipping"]:
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
        self.btnContinueName.clicked.connect(self._btnContinueNameClicked)
        self.btnContinueAssets.clicked.connect(self._btnContinueAssetsClicked)
        self.btnBackReview.clicked.connect(self._btnBackReviewClicked)
        self.btnBackAssets.clicked.connect(self._btnBackAssetsClicked)
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

    def _btnBackReviewClicked(self):
        self.stackedWidget.setCurrentIndex(1)

    def _btnBackAssetsClicked(self):
        self.stackedWidget.setCurrentIndex(0)

    def _btnContinueNameClicked(self):
        self.stackedWidget.setCurrentIndex(1)

    def _btnContinueAssetsClicked(self):
        self.stackedWidget.setCurrentIndex(2)

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

    def selectionChanged(self):
        self.update_review_items()
        self.update_summary_items()

    def update_review_items(self):
        self._order_review_widgets = []
        scrollWidget = QWidget()
        layout = QVBoxLayout()
        layout.setMargin(0)
        for item_type, widget in self._item_type_widgets.items():
            assets = widget.assets()
            images = widget.images
            thumbnails = widget.thumbnails
            for asset in assets:
                w = PlanetOrderReviewWidget(item_type, asset["name"], images,
                                            thumbnails, self.tool_resources["aoi"] is not None)
                w.selectedImagesChanged.connect(self.update_summary_items)
                self._order_review_widgets.append(w)
                layout.addWidget(w)
        layout.addStretch()
        scrollWidget.setLayout(layout)
        self.scrollAreaReview.setWidget(scrollWidget)

    def _review_widget_for_asset(self, item_type, asset_type):
        for w in self._order_review_widgets:
            if w.item_type == item_type and w.asset_type == asset_type:
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
            summary["assets"] = widget.assets()
            for asset in summary["assets"]:
                w = self._review_widget_for_asset(item_type, asset["name"])
                images = w.selected_images()
                asset["numitems"] = len(images)
                asset["clipping"] = w.clipping()
                norders += 1
            w = PlanetOrderSummaryOrderWidget(summary)
            layout.addWidget(w)
        layout.addStretch()

        self.labelNumberOfOrders.setText(f"{norders}")

    @waitcursor
    def _process_orders(self):
        name = self.txtOrderName.text()

        orders = []
        for item_type, widget in self._item_type_widgets.items():
            for asset in widget.assets():
                w = self._review_widget_for_asset(item_type, asset["name"])
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

                if w.clipping():
                    order['tools'] = [{
                            'clip': {
                                'aoi': json.loads(self._tool_resources['aoi'])
                            }}]

                orders.append(order)

        return

        responses = []
        for order in orders:
            resp = self._p_client.create_order(order)
            responses.append(resp)

            if is_segments_write_key_valid():
                try:
                    clipAoi = order['tools']['clip']['aoi']
                except KeyError:
                    clipAoi = None
                analytics.track(self._p_client.user()["email"], "Order placed",
                                {
                                "name": order["name"],
                                "numItems": order["products"][0]["item_ids"],
                                "clipAoi": clipAoi
                                }
                                )



    def _order_response(self, item_type: str, response: dict):
        if not item_type:
            self._log('Requesting order failed: no item_type')
            return

        log.debug(f'Order resp_data:\n{response}')
        if not response:
            self._log(f'Requesting {item_type} order failed: '
                      f'no response data found')
            return

        if not response.get("id"):
            self._log(f'Requesting {item_type} order failed: '
                      f'response data contains no Order ID')
            return

        bundle = 'unknown'
        itemtype = 'Unknown type'
        itemids = []
        itemids_cnt = '_'
        products: list = response.get('products')
        if products and len(products) > 0:
            bundle = products[0].get('product_bundle')
            itemtype = products[0].get('item_type')
            itemids = products[0].get('item_ids')

        if itemids:
            itemids_cnt = len(itemids)

        self._log(
            f'<br><br>'
            f'<b>Order for {item_type} successfully QUEUED:</b><br>'
            f' --  Name: {response.get("name")}<br>'
            f' --  Created on: {response.get("created_on")}<br>'
            f' -- Order ID: <b>{response.get("id")}</b> '
            f'SAVE THIS FOR REFERENCE<br>'
            f' -- Order type: {itemtype} ({itemids_cnt} items)<br>'
            f' -- Bundle: {bundle}<br>'
            f' -- State: {response.get("state")}<br>'
            f' -- Service message: {response.get("last_message")}<br><br>'
        )

    @pyqtSlot()
    def _open_orders_monitor_dialog(self):
        show_orders_monitor()
