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
import iso8601

from typing import (
    Optional,
    List
)

from collections import OrderedDict, defaultdict

import analytics

# noinspection PyPackageRequirements
from qgis.PyQt import uic

# noinspection PyPackageRequirements
from qgis.PyQt.QtCore import (
    pyqtSignal,
    pyqtSlot,
    Qt,
    QSize,
    QUrl
)
# noinspection PyPackageRequirements
from qgis.PyQt.QtGui import (
    QImage,
    QPixmap
)
# noinspection PyPackageRequirements
from qgis.PyQt.QtWidgets import (
    QLabel,
    QComboBox,
    QCheckBox,
    QDialogButtonBox,
    QFrame,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QWidget,
    QToolButton,
    QTextBrowser,
    QListWidget,
    QListWidgetItem,
    QHBoxLayout
)

from PyQt5.QtNetwork import (
    QNetworkAccessManager,
    QNetworkRequest
)

from qgis.core import (
    QgsApplication,
)

from qgis.utils import iface

from qgis.gui import (
    QgsCollapsibleGroupBox,
)

from .pe_gui_utils import (
    PlanetClickableLabel,
)
from ..pe_utils import (
    is_segments_write_key_valid
)
from ..planet_api.p_client import (
    PlanetClient,
)

from ..planet_api.p_bundles import (
    PlanetOrdersV2Bundles,
)
from ..planet_api.p_specs import (
    ITEM_TYPE_SPECS,
)
from .pe_orders_monitor_dockwidget import (
    show_orders_monitor
)

from ..planet_api.p_specs import (
    DAILY_ITEM_TYPES_DICT
)

from .pe_gui_utils import (
    waitcursor
)

plugin_path = os.path.split(os.path.dirname(__file__))[0]

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

ORDER_ITEM_WIDGET, ORDER_ITEM_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_orders_v2_source_base.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)

ORDERS_WIDGET, ORDERS_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_orders_v2_base.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)

PLACEHOLDER_THUMB = ':/plugins/planet_explorer/thumb-placeholder-128.svg'

ITEM_MAX = 100

ID = "id"
PERMISSIONS = "_permissions"


class ImageItem(QListWidgetItem):

    def __init__(self, image):
        super().__init__()
        self.image = image


class ImageItemWidget(QFrame):

    checked_state_changed = pyqtSignal()

    def __init__(self, image, sort_criteria):
        QFrame.__init__(self)
        self.image = image
        self.properties = image['properties']

        datetime = iso8601.parse_date(self.properties[sort_criteria])
        self.time = datetime.strftime('%H:%M:%S')
        self.date = datetime.strftime('%b %d, %Y')

        text = f"""{self.date}<span style="color: rgb(100,100,100);"> {self.time} UTC</span><br>
                        <b>{DAILY_ITEM_TYPES_DICT[self.properties['item_type']]}</b><br>
                    """
        url = f"{image['_links']['thumbnail']}?api_key={PlanetClient.getInstance().api_key()}"

        self.checkBox = QCheckBox("")
        self.checkBox.setChecked(True)
        self.checkBox.stateChanged.connect(self.checked_state_changed.emit)
        self.nameLabel = QLabel(text)
        self.iconLabel = QLabel()

        layout = QHBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.checkBox)
        pixmap = QPixmap(PLACEHOLDER_THUMB, 'SVG')
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.iconLabel.setFixedSize(48, 48)
        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self.iconDownloaded)
        self.nam.get(QNetworkRequest(QUrl(url)))
        layout.addWidget(self.iconLabel)
        layout.addWidget(self.nameLabel)
        layout.addStretch()
        self.setLayout(layout)

    def iconDownloaded(self, reply):
        img = QImage()
        img.loadFromData(reply.readAll())
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)

    def set_selected(self, checked):
        self.checkBox.setChecked(checked)

    def is_selected(self):
        return self.checkBox.isChecked()


class PlanetOrderItemTypeWidget(ORDER_ITEM_BASE, ORDER_ITEM_WIDGET):

    grpBxItemType: QgsCollapsibleGroupBox
    listWidget: QListWidget
    btnCheckAll: QCheckBox
    btnCheckNone: QCheckBox

    lblAssetCount: QLabel
    grpBxAssets: QgsCollapsibleGroupBox
    grpBoxTools: QgsCollapsibleGroupBox

    frameBundleOptions: QFrame
    frameBands: QFrame
    frameRadiometry: QFrame
    frameRectification: QFrame
    frameOutput: QFrame
    cmbBoxBands: QComboBox
    cmbBoxRadiometry: QComboBox
    cmbBoxRectification: QComboBox
    cmbBoxOutput: QComboBox
    lblBandsInfo: QLabel
    lblRadiometryInfo: QLabel
    lblRectificationInfo: QLabel
    lblOutputInfo: QLabel

    teBundleInfo: QPlainTextEdit
    chkBoxClipToAOI: QCheckBox

    validationPerformed = pyqtSignal(bool)

    GROUPBOX_HIGHLIGHT = \
        'QGroupBox::title#grpBxItemType { color: rgb(175, 0, 0); }'

    def __init__(self,
                 item_type: str,
                 images: List[dict],
                 sort_criteria,
                 tool_resources,
                 parent=None
                 ):
        super().__init__(parent=parent)

        self.setupUi(self)
        self._parent: PlanetOrdersDialog = parent

        self._item_type = item_type
        self.images = images
        self.sort_criteria = sort_criteria
        self._tool_resources = tool_resources

        self._display_name = ITEM_TYPE_SPECS[self._item_type]['name']
        self.grpBxItemType.setSaveCollapsedState(False)
        self.grpBxItemType.setSaveCheckedState(False)
        self.grpBxItemType.setCheckable(True)
        self.grpBxItemType.setChecked(True)

        self.populate_list()

        self.lblSelectAll.linkActivated.connect(self._batch_check_items)

        # Get sample permissions from first node
        self._permissions = images[0][PERMISSIONS]

        self._order_bundles = self._parent.order_bundles()
        self._item_bundles: OrderedDict = \
            self._order_bundles.bundles_per_item_type(
                self._item_type, permissions=self._permissions)
        self._bundle_opt_tree: OrderedDict = \
            self._order_bundles.filter_tree_from_bundles(self._item_bundles)
        self._filter_keyed_bundle_names = \
            self._order_bundles.filter_keyed_bundles(self._item_bundles)
        self._bundle_keyed_filters = \
            self._order_bundles.bundle_keyed_filters(self._item_bundles)
        self._order_valid = True
        self._order_bundle = None
        self._order_bundle_name = None

        self._update_groupbox_title()
        self.grpBxItemType.collapsedStateChanged[bool].connect(
            self._group_box_collapsed_changed)
        self.grpBxItemType.clicked.connect(self._groupbox_clicked)

        self._filter_opts_cmbboxes = [
            self.cmbBoxBands, self.cmbBoxRadiometry,
            self.cmbBoxRectification, self.cmbBoxOutput
        ]
        for cmbox in self._filter_opts_cmbboxes:
            cmbox.currentTextChanged.connect(self._update_bundle_options)

        self._filter_info_labels = []
        self._info_buttons_set_up = False
        self._setup_info_buttons()

        self._tools_set_up = False
        self._set_up_tools()

        self._update_bundle_options()

    def populate_list(self):
        for img in self.images:
            item = ImageItem(img)
            widget = ImageItemWidget(img, self.sort_criteria)
            widget.checked_state_changed.connect(self.selection_changed)
            item.setSizeHint(widget.sizeHint())
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)

    @pyqtSlot(str)
    def _update_order_bundle(self, bundle_name) -> None:
        self._order_bundle = None
        self._order_bundle_name = None
        if not bundle_name:
            msg = 'Resolved bundle not found'
            log.debug(msg)
            self._update_bundle_info(msg)
            self.validate()
            return
        bundle = self._item_bundles.get(bundle_name)
        if not bundle:
            msg = f'Bundle not found: {bundle_name}'
            log.debug(msg)
            self._update_bundle_info(msg)
            self.validate()
            return

        self._order_bundle = bundle
        self._order_bundle_name = bundle_name
        nl = '\n'
        info = (
            f'Bundle: {bundle_name}\n'
            f'Assets:\n'
            f'  {"{0}  ".format(nl).join(bundle.get("assets"))}'
        )
        self._update_bundle_info(info)
        self.validate()

    @pyqtSlot()
    def _update_bundle_options(self) -> None:
        c_s = self._filter_opts_cmbboxes
        l_s = self._filter_info_labels
        t_s = [c.currentText() for c in c_s]  # type: List[str]

        if not t_s[0]:
            # Nothing set yet, add default for bundle
            bundle_name = \
                self._order_bundles.item_default_bundle_name(self._item_type)
            bundle_key = self._bundle_keyed_filters.get(bundle_name)
            t_s = list(bundle_key)

        for cmbox in self._filter_opts_cmbboxes:
            cmbox.blockSignals(True)

        t_r: OrderedDict = self._bundle_opt_tree
        for i in range(0, 4):
            c_s[i].clear()
            c_s[i].setEnabled(True)

            first_k = list(t_r.keys())[0]
            t_k = t_r[first_k]
            t_t = first_k
            for k in list(t_r.keys()):  # type: str
                c_s[i].addItem(k)
                if t_s[i] == k:
                    t_k = t_r[k]
                    t_t = k

            c_s[i].setCurrentText(t_t)
            l_s[i].setToolTip(
                self._order_bundles.filter_option_description(i, t_t))

            if len(t_r) == 1:
                c_s[i].setEnabled(False)

            t_r = t_k  # set new branch

        for cmbox in self._filter_opts_cmbboxes:
            cmbox.blockSignals(False)

        new_t_s = [c.currentText() for c in c_s]  # type: List[str]

        bundle_key = tuple(new_t_s)
        bundle_name = \
            self._filter_keyed_bundle_names.get(bundle_key)

        log.debug(f'new bundle_key: {bundle_key}')
        log.debug(f'_filter_keyed_bundle_names: '
                  f'{self._filter_keyed_bundle_names}')
        log.debug(f'new bundle name: {bundle_name}')

        self._update_order_bundle(bundle_name)

    @pyqtSlot(str)
    def _update_bundle_info(self, info: str) -> None:
        self.teBundleInfo.clear()
        self.teBundleInfo.setPlainText(str(info))

    @pyqtSlot()
    def _update_groupbox_title(self):
        chkd_cnt = len(self.selected_images())
        title = f'{self._display_name}   |   ' \
                f'{chkd_cnt}/{ITEM_MAX} images selected'
        self.grpBxItemType.setTitle(title)

    def selected_images(self) -> List:
        selected_images = []
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            w = self.listWidget.itemWidget(item)
            if w.is_selected():
                selected_images.append(item.image)
        return selected_images

    # noinspection PyUnusedLocal
    @pyqtSlot(bool)
    def _groupbox_clicked(self, checked):
        self._update_groupbox_title()
        self.validate()

    def _setup_info_buttons(self):
        if self._info_buttons_set_up:
            return
        self.lblBandsInfo = \
            PlanetClickableLabel(self.frameBands)
        self.lblRadiometryInfo = \
            PlanetClickableLabel(self.frameRadiometry)
        self.lblRectificationInfo = \
            PlanetClickableLabel(self.frameRectification)
        self.lblOutputInfo = \
            PlanetClickableLabel(self.frameOutput)

        self._filter_info_labels = [
            self.lblBandsInfo,
            self.lblRadiometryInfo,
            self.lblRectificationInfo,
            self.lblOutputInfo,
        ]
        n = 1
        for lbl in self._filter_info_labels:  # type: PlanetClickableLabel
            size_policy = QSizePolicy(QSizePolicy.Maximum,
                                      QSizePolicy.Preferred)
            size_policy.setHorizontalStretch(0)
            size_policy.setVerticalStretch(0)
            size_policy.setHeightForWidth(lbl.sizePolicy().hasHeightForWidth())
            lbl.setSizePolicy(size_policy)
            lbl.setMaximumSize(QSize(20, 20))
            lbl.setText('')
            lbl.setPixmap(QPixmap(':/plugins/planet_explorer/info-light.svg'))
            lbl.setScaledContents(True)
            lbl.setObjectName(f'infoLabel{n}')
            n += 1

            lbl.set_show_tooltip_on_hover(True)

        self.frameBands.layout().addWidget(self.lblBandsInfo)
        self.frameRadiometry.layout().addWidget(self.lblRadiometryInfo)
        self.frameRectification.layout().addWidget(self.lblRectificationInfo)
        self.frameOutput.layout().addWidget(self.lblOutputInfo)

        self._info_buttons_set_up = True

    def _set_up_tools(self):
        if self._tools_set_up:
            return
        for a, b in self._order_bundles.tools():
            # Strip ' Scene' to reduce horizontal width of 2-column layout
            cb = QCheckBox(b, parent=self.grpBoxTools)
            cb.setChecked(False)
            cb.setProperty('tool', a)
            cb.setToolTip(b)
            self.grpBoxTools.layout().addWidget(cb)

        self._tools_set_up = True

    def selected_images_ids(self) -> list:
        return [img[ID] for img in self.selected_images()]

    def validate(self) -> bool:
        chkd_cnt = len(self.selected_images())
        val = True

        # TODO: Add more checks?
        invalid = (
            (chkd_cnt == 0 or chkd_cnt > ITEM_MAX)
            or not self.grpBxItemType.isChecked()
            or self._order_bundle is None
            or self._order_bundle_name is None
        )

        style_sheet = None
        if invalid:
            val = False
            if self.GROUPBOX_HIGHLIGHT not in self.grpBxItemType.styleSheet():
                style_sheet = self.grpBxItemType.styleSheet() + \
                              self.GROUPBOX_HIGHLIGHT
        else:
            style_sheet = self.grpBxItemType.styleSheet().replace(
                self.GROUPBOX_HIGHLIGHT, '')

        if style_sheet is not None:
            self.grpBxItemType.setStyleSheet(style_sheet)

        self.validationPerformed.emit(val)

        return val

    @pyqtSlot()
    def get_order(self) -> dict:
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
            f'Ordering {self._item_type}...\n'
            f'  valid: {valid}\n'
            f'  item count: {len(ids)}\n'
            f'  type_ids: {ids}\n'
            f'  bundle_name: {self._order_bundle_name}\n'
            f'  tools: {tools}'
        )

        return order_details

    def selection_changed(self):
        self._update_groupbox_title()
        self.validate()

    @pyqtSlot(str)
    def _batch_check_items(self, url):
        checked = url == "all"
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            widget = self.listWidget.itemWidget(item)
            widget.blockSignals(True)
            widget.set_selected(checked)
            widget.blockSignals(False)
        self.selection_changed()
        self.listWidget.setFocus()

    @pyqtSlot(bool)
    def _group_box_collapsed_changed(self, collapsed):
        if collapsed:
            return
        sender = self.sender()
        if sender.__class__.__name__ == 'QgsCollapsibleGroupBox':
            if sender.isChecked():
                # noinspection PyTypeChecker
                listwdgt: QListWidget = sender.findChild(QListWidget)
                if listwdgt:
                    listwdgt.setFocus()


class PlanetOrdersDialog(ORDERS_BASE, ORDERS_WIDGET):

    orderShouldCancel = pyqtSignal(str)

    frameName: QFrame
    lblName: QLabel
    frameOrderLog: QFrame
    tbOrderLog: QTextBrowser
    btnOrderLogClose: QToolButton
    btnCopyLog: QToolButton
    leName: QLineEdit
    scrollAreaItemTypes: QScrollArea
    scrollAreaItemTypesContents: QWidget
    buttonBox: QDialogButtonBox

    _watchers: dict

    NAME_HIGHLIGHT = 'QLabel { color: rgb(175, 0, 0); }'

    def __init__(self, images: list,
                 sort_criteria,
                 tool_resources: Optional[dict] = None,
                 parent=None
                 ):
        super().__init__(parent=parent)

        self.setupUi(self)

        self._parent = parent
        self._iface = iface

        self._p_client = PlanetClient.getInstance()

        self._tool_resources = tool_resources

        bundles_file = os.path.join(
            plugin_path, 'planet_api', 'resources', 'bundles.json')
        self._order_bundles = PlanetOrdersV2Bundles(bundles_file)

        self.setMinimumWidth(640)
        self.setMinimumHeight(720)

        self.lblName.setStyleSheet(self.NAME_HIGHLIGHT)
        self.leName.textChanged.connect(self.validate)

        self.frameOrderLog.hide()
        self.btnOrderLogClose.clicked.connect(self._close_order_log)
        self.btnCopyLog.clicked.connect(self._copy_log_to_clipboard)

        self.tbOrderLog.setOpenExternalLinks(False)
        self.tbOrderLog.anchorClicked.connect(self._open_orders_monitor_dialog)

        self.btnPlaceOrder = self.buttonBox.button(QDialogButtonBox.Ok)
        self.btnPlaceOrder.setText(
            f'Place Order{"s" if len(images) > 1 else ""}')
        self.buttonBox.accepted.connect(self.place_orders)
        self.buttonBox.rejected.connect(self.reject)

        first = None
        images_dict = defaultdict(list)
        for img in images:
            images_dict[img['properties']['item_type']].append(img)
        self._item_type_widgets = {}
        for item_type, images in images_dict.items():
            oi_w = PlanetOrderItemTypeWidget(
                item_type,
                images,
                sort_criteria,
                self._tool_resources,
                parent=self
            )
            oi_w.grpBxItemType.setCollapsed(True)
            if not first:
                first = oi_w
            oi_w.validationPerformed.connect(self.validate)
            self._item_type_widgets[item_type] = oi_w
            self.scrollAreaItemTypesContents.layout().addWidget(
                self._item_type_widgets[item_type])

        self.scrollAreaItemTypesContents.layout().addStretch(3)

        # Trigger thumbnail updating for first item type widget
        first.grpBxItemType.setCollapsed(False)

        self.validate()

    def order_bundles(self):
        return self._order_bundles

    @pyqtSlot()
    def validate(self):
        if not self.leName.text():
            self.lblName.setStyleSheet(self.NAME_HIGHLIGHT)
            self.btnPlaceOrder.setEnabled(False)
            # No sense even parsing item orders at this point
            return

        self.lblName.setStyleSheet('')

        valid_orders = []
        for i_type in ITEM_TYPE_SPECS:
            if i_type not in self._item_type_widgets:
                continue
            it_wgdt: PlanetOrderItemTypeWidget = \
                self._item_type_widgets[i_type]
            it_wgdt.blockSignals(True)
            valid_orders.append(it_wgdt.validate())
            it_wgdt.blockSignals(False)

        self.btnPlaceOrder.setEnabled(any(valid_orders))

    @pyqtSlot()
    def _log(self, msg):
        self.tbOrderLog.append(msg)

    @pyqtSlot()
    def place_orders(self):
        log.debug('Placing orders...')
        orders = OrderedDict()
        for i_type in ITEM_TYPE_SPECS:
            if i_type not in self._item_type_widgets:
                continue
            it_wgdt: PlanetOrderItemTypeWidget = \
                self._item_type_widgets[i_type]
            orders[i_type] = it_wgdt.get_order()

        self.frameName.setEnabled(False)
        self.scrollAreaItemTypes.setEnabled(False)
        self.btnPlaceOrder.setEnabled(False)
        self.frameOrderLog.show()

        self._log('Collecting and validating orders...')

        # From item order
        # ['valid'] = valid
        # ['item_ids'] = self.checked_item_ids()
        # ['bundle_name'] = self._order_bundle_name
        # ['bundle'] = self._order_bundle

        self._process_orders(orders)

    @waitcursor
    def _process_orders(self, item_orders):
        name = str(self.leName.text())
        orders = OrderedDict()
        aoi = None
        if self._tool_resources.get('aoi') is not None:
            aoi = json.loads(self._tool_resources.get('aoi'))
        for io_k, io_v in item_orders.items():
            if not bool(io_v['valid']):
                self._log(f'Skipping item order {io_k} (not valid)')
                continue

            # IMPORTANT: The '_QGIS' suffix is needed, for the user to see
            #            their order in Explorer web app
            order = OrderedDict()  # necessary to maintain toolchain order
            order['name'] = f'{name.replace(" ", "_")}_{io_k}'
            order['order_type'] = 'partial'
            order['products'] = [
                    {
                        'item_ids': io_v['item_ids'],
                        'item_type': io_k,
                        'product_bundle': io_v['bundle_name']
                    }
                ]
            order['delivery'] = {
                    'archive_filename': '{{name}}_QGIS.zip',
                    'archive_type': 'zip',
                    'single_archive': True,
                }
            order['notifications'] = {
                    'email': True
                }

            if io_v['tools']:
                order['tools'] = []

            for tool in io_v['tools']:
                if tool == 'clip':
                    if aoi is None:
                        self._log('Clip tool is missing AOI, skipping')
                        continue
                    order['tools'].append(
                        {
                            'clip': {
                                'aoi': aoi
                            }
                        }
                    )

            orders[io_k] = order

            log.debug(f'{io_k} order...\n{json.dumps(order, indent=2)}')

        for item_type, order in orders.items():

            resp = self._p_client.create_order(order)
            self._order_response(item_type, resp)

            if is_segments_write_key_valid():
                analytics.track(self._p_client.user()["email"], "Order placed",
                                {
                                "name": order["name"],
                                "numItems": order["products"][0]["item_ids"],
                                "clipAoi": aoi
                                }
            )

        self._log(f'<br><br>'
            f'<b>IMPORTANT:</b> Open the <a href="opendlg">Orders monitor'
            f'dialog</a> to monitor your order status and download it when '
            f'possible.<br>'
            f'You also should receive an email when your order is ready to '
            f'download.<br>')

    def _order_response(self, item_type: str, response: dict):

        if not item_type:
            self._log('Requesting order failed: no item_type')
            return

        log.debug(f'Order resp_data:\n{response}')
        if not response:
            self._log(f'Requesting {item_type} order failed: '
                      f'no response data found')
            return

        # Rsponse sample
        # {
        #     "created_on": "2018-01-09T19:11:51.566Z",
        #     "id": "66139753-60e4-4926-a8ad-c556048aabce",
        #     "last_message": "Preparing order",
        #     "last_modified": "2018-01-09T19:11:51.566Z",
        #     "name": "simple order",
        #     "products": [
        #         {
        #             "item_ids": [
        #                 "20151119_025740_0c74",
        #                 "20151119_025741_0c74"
        #             ],
        #             "item_type": "PSScene4Band",
        #             "product_bundle": "analytic"
        #         }
        #     ],
        #     "state": "queued"
        # }
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
    def _copy_log_to_clipboard(self):
        cb = QgsApplication.clipboard()
        cb.setText(self.tbOrderLog.toPlainText())
        self.tbOrderLog.append('Log copied to clipboard')

    @pyqtSlot()
    def _close_order_log(self):
        # TODO: Warn user they will lose any order IDs if they close log

        self.tbOrderLog.clear()
        self.frameOrderLog.hide()
        self.btnPlaceOrder.setEnabled(True)
        self.frameName.setEnabled(True)
        self.scrollAreaItemTypes.setEnabled(True)

    @pyqtSlot()
    def _open_orders_monitor_dialog(self):
        show_orders_monitor()
