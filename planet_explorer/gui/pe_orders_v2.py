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
import sys
import logging
import json
import re

from typing import (
    Optional,
    # Union,
    List,
    # Tuple,
)

from collections import OrderedDict
from functools import partial

import analytics

# noinspection PyPackageRequirements
from requests.models import Response as ReqResponse

from qgiscommons2.settings import (
    pluginSetting,
    readSettings,
)

from planet.api import models

# noinspection PyPackageRequirements
from qgis.PyQt import uic

# noinspection PyPackageRequirements
from qgis.PyQt.QtCore import (
    pyqtSignal,
    pyqtSlot,
    Qt,
    QModelIndex,
    QSize,
)
# noinspection PyPackageRequirements
from qgis.PyQt.QtGui import (
    QImage,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
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
    QListView,
    QSizePolicy,
    QWidget,
    QToolButton,
    QTextBrowser,
)

from qgis.core import (
    QgsApplication,
)

from qgis.gui import (
    QgsCollapsibleGroupBox,
)

if __name__ == "__main__":
    from planet_explorer.gui.pe_gui_utils import (
        PlanetClickableLabel,
    )
    from planet_explorer.pe_utils import (
        SETTINGS_NAMESPACE,
    )
    from planet_explorer.planet_api.p_client import (
        PlanetClient,
    )
    from planet_explorer.planet_api.p_node import (
        PlanetNode,
        # PlanetNodeType,
    )
    from planet_explorer.planet_api.p_thumnails import (
        PlanetThumbnailCache,
    )
    from planet_explorer.planet_api.p_network import (
        PlanetCallbackWatcher,
        dispatch_callback,
        RESPONSE_TIMEOUT,
        # requests_response_metadata,
    )
    from planet_explorer.planet_api.p_bundles import (
        PlanetOrdersV2Bundles,
    )
    from planet_explorer.planet_api.p_specs import (
        ITEM_TYPE_SPECS,
    )
else:
    from .pe_gui_utils import (
        PlanetClickableLabel,
    )
    from ..pe_utils import (
        SETTINGS_NAMESPACE,
        is_segments_write_key_valid
    )
    from ..planet_api.p_client import (
        PlanetClient,
    )
    from ..planet_api.p_node import (
        PlanetNode,
        # PlanetNodeType,
    )
    from ..planet_api.p_thumnails import (
        PlanetThumbnailCache,
    )
    from ..planet_api.p_network import (
        PlanetCallbackWatcher,
        dispatch_callback,
        RESPONSE_TIMEOUT,
        # requests_response_metadata,
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


class PlanetOrderItem(QStandardItem):
    """
    """
    def __init__(self, node: PlanetNode):
        super().__init__()

        self._node = node

        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.setFlags(
            Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)

        def remove_html_tags(txt):
            txt.replace('<br>', '\n')
            reg = re.compile('<.*?>')
            return re.sub(reg, '', txt)

        # self.setText(node.formatted_date_time(node.acquired()))
        self.setText(remove_html_tags(node.description()))
        self.setIcon(node.icon())
        # self.setToolTip(node.description())

    def node(self):
        return self._node

    def type(self) -> int:
        return Qt.UserRole + 1


class PlanetOrderItemModel(QStandardItemModel):
    """
    """

    thumbnailFetchShouldCancel = pyqtSignal(str)

    def __init__(self, node_queue: List[PlanetNode],
                 thumb_cache_dir: str,
                 api_client,
                 parent=None):
        super().__init__(parent=parent)

        self._nodes = node_queue

        self._thumb_cache = PlanetThumbnailCache(
            thumb_cache_dir, api_client, parent=self)
        self._thumb_cache.thumbnailFetchStarted[str].connect(
            self._thumbnail_fetch_started)
        self._thumb_cache.thumbnailAvailable[str, str].connect(
            self._thumbnail_available)
        self._thumb_cache.thumbnailFetchFailed[str].connect(
            self._thumbnail_fetch_failed)
        self._thumb_cache.thumbnailFetchTimedOut[str, int].connect(
            self._thumbnail_fetch_timed_out)
        self._thumb_cache.thumbnailFetchCancelled[str].connect(
            self._thumbnail_fetch_cancelled)

        self.thumbnailFetchShouldCancel[str].connect(
            self._thumb_cache.cancel_fetch, type=Qt.UniqueConnection)

        self._thumb_queue = {}
        self._thumbs_fetched = False

    def load_nodes(self):
        for node in self._nodes:
            item = PlanetOrderItem(node)
            self.appendRow(item)

    @pyqtSlot()
    def fetch_missing_thumbnails(self):
        log.debug(f'rowCount: {self.rowCount()}')
        for i in range(self.rowCount()):
            item = self.item(i)

            # noinspection PyUnresolvedReferences
            node = item.node()
            if node.has_thumbnail() and not node.thumbnail_loaded():
                self.add_to_thumb_queue(
                    node.item_type_id_key(), item.index())
                self.fetch_thumbnail(node)

        self._thumbs_fetched = True

    def thumbnails_fetched(self) -> bool:
        return self._thumbs_fetched

    def add_to_thumb_queue(self, item_key, item_indx):
        if item_key not in self._thumb_queue:
            self._thumb_queue[item_key] = item_indx

    def _in_thumb_queue(self, item_key):
        return item_key in self._thumb_queue

    def _thumb_queue_index(self, item_key):
        if item_key in self._thumb_queue:
            return self._thumb_queue[item_key]
        return QModelIndex()

    def _remove_from_thumb_queue(self, item_key):
        if item_key in self._thumb_queue:
            del self._thumb_queue[item_key]

    def thumbnail_cache(self):
        return self._thumb_cache

    def fetch_thumbnail(self, node: PlanetNode):
        self._thumb_cache.fetch_thumbnail(
            node.item_type_id_key(),
            item_id=node.item_id(),
            item_type=node.item_type(),
            item_properties=node.item_properties()
        )

    @pyqtSlot(str)
    def _thumbnail_fetch_started(self, item_key):
        log.debug(f'Thumbnail fetch started for {item_key}')

    @pyqtSlot(str)
    def _thumbnail_fetch_failed(self, item_key):
        log.debug(f'Thumbnail fetch failed for {item_key}')
        self._remove_from_thumb_queue(item_key)

    @pyqtSlot(str, int)
    def _thumbnail_fetch_timed_out(self, item_key, timeout):
        log.debug(f'Thumbnail fetch timed out for {item_key} '
                  f'in {timeout} seconds')
        self._remove_from_thumb_queue(item_key)

    @pyqtSlot(str)
    def _thumbnail_fetch_cancelled(self, item_key):
        log.debug(f'Thumbnail fetch cancelled for {item_key}')
        self._remove_from_thumb_queue(item_key)

    @pyqtSlot(str, str)
    def _thumbnail_available(self, item_key, thumb_path):
        log.debug(f'Thumbnail available for {item_key} at {thumb_path}')
        if not self._in_thumb_queue(item_key):
            log.debug(f'Thumbnail queue does not contain {item_key}')
            return

        indx = self._thumb_queue_index(item_key)
        if not indx.isValid():
            log.debug(f'Thumbnail queue index invalid for: {item_key}')
            self._remove_from_thumb_queue(item_key)
            return
        item = self.itemFromIndex(indx)
        # noinspection PyUnresolvedReferences
        node = item.node()
        if node.thumbnail_loaded():
            log.debug(f'Thumbnail already loaded for: {item_key}')
            self._remove_from_thumb_queue(item_key)
            return

        # q_file_thumb = QFile(thumb_path)
        # timeout = 3
        # while not q_file_thumb.open(QIODevice.ReadOnly):
        #     log.debug(f'Local PNG not readable ({timeout}):\n{thumb_path}')
        #     if timeout == 0:
        #         log.debug(f'Local PNG unreadable:\n{thumb_path}')
        #         break
        #     time.sleep(1)
        #     timeout -= 1

        # DON"T USE THIS: apparently has issues with semaphore locking
        # png = QPixmap(thumb_path, 'PNG')
        # Load into QImage instead, then convert to QPixmap
        png = QImage(thumb_path, 'PNG')
        if not png.isNull():
            log.debug(f'Local PNG icon loaded for {item_key}:\n'
                      f'{thumb_path}')
            pm = QPixmap.fromImage(png)
            node.set_thumbnail(pm, local_url=thumb_path)
            item.setIcon(node.icon())
            # noinspection PyUnresolvedReferences
            # self.dataChanged.emit(indx, indx, [Qt.DecorationRole])
        else:
            log.debug(
                f'Local PNG icon could not be loaded for {item_key}:\n'
                f'{thumb_path}')
        self._remove_from_thumb_queue(item_key)

    @pyqtSlot(bool)
    def _cancel_thumbnail_fetch(self, _):
        items = [i for i in self._thumb_queue]
        for item in items:
            self.thumbnailFetchShouldCancel.emit(item)
        # self._thumb_queue.clear()


class PlanetOrderItemTypeWidget(ORDER_ITEM_BASE, ORDER_ITEM_WIDGET):
    """
    """

    grpBxItemType: QgsCollapsibleGroupBox
    listViewItems: QListView
    btnCheckAll: QCheckBox
    btnCheckNone: QCheckBox

    lblAssetCount: QLabel
    grpBxAssets: QgsCollapsibleGroupBox
    grpBoxTools: QgsCollapsibleGroupBox

    chkBxSelectAllAssets: QCheckBox
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
                 node_queue: List[PlanetNode],
                 thumb_cache_dir: str,
                 api_client,
                 tool_resources,
                 parent=None,
                 ):
        super().__init__(parent=parent)

        self.setupUi(self)
        self._parent: PlanetOrdersDialog = parent

        self._item_type = item_type
        self._node_queue = node_queue
        self._api_client = api_client
        self._thumb_cache_dir = thumb_cache_dir
        self._tool_resources = tool_resources

        self._display_name = ITEM_TYPE_SPECS[self._item_type]['name']
        self.grpBxItemType.setSaveCollapsedState(False)
        self.grpBxItemType.setSaveCheckedState(False)
        self.grpBxItemType.setCheckable(True)
        self.grpBxItemType.setChecked(True)

        # log.debug(f'{self._item_type}, node_queue:\n{self._node_queue}')

        self._item_model: PlanetOrderItemModel = \
            PlanetOrderItemModel(
                self._node_queue, self._thumb_cache_dir,
                self._api_client, parent=self)

        self._item_model.load_nodes()

        self.listViewItems.setModel(self._item_model)

        # noinspection PyUnresolvedReferences
        self._item_model.itemChanged['QStandardItem*'].connect(
            self._item_changed)

        # noinspection PyUnresolvedReferences
        self.listViewItems.doubleClicked['QModelIndex']\
            .connect(self._item_clicked)

        self.btnCheckAll.clicked.connect(
            lambda: self._batch_check_items(check_all=True))
        self.btnCheckNone.clicked.connect(
            lambda: self._batch_check_items(check_all=False))

        # Get smaple permissions from first node
        self._permissions = self._node_queue[0].permissions()

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
        self._checked_items = []
        self._order_bundle = None
        self._order_bundle_name = None

        self._update_checked_items()
        self._update_groupbox_title()
        # noinspection PyUnresolvedReferences
        self.grpBxItemType.collapsedStateChanged[bool].connect(
            self._group_box_collapsed_changed)
        # noinspection PyUnresolvedReferences
        self.grpBxItemType.clicked.connect(self._groupbox_clicked)

        # noinspection PyUnresolvedReferences
        self.chkBxSelectAllAssets.stateChanged.connect(
            self._update_bundle_options)
        self._filter_opts_cmbboxes = [
            self.cmbBoxBands, self.cmbBoxRadiometry,
            self.cmbBoxRectification, self.cmbBoxOutput
        ]
        for cmbox in self._filter_opts_cmbboxes:
            # noinspection PyUnresolvedReferences
            cmbox.currentTextChanged.connect(self._update_bundle_options)

        self._filter_info_labels = []
        self._info_buttons_set_up = False
        self._setup_info_buttons()

        self._tools_set_up = False
        self._set_up_tools()

        self._update_bundle_options()

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
        if self.chkBxSelectAllAssets.isChecked():
            self.frameBundleOptions.setDisabled(True)
            self._update_order_bundle('all')
            return
        else:
            self.frameBundleOptions.setEnabled(True)

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
        chkd_cnt = len(self._checked_items)
        title = f'{self._display_name}   |   ' \
                f'{chkd_cnt}/{ITEM_MAX} images selected'
        self.grpBxItemType.setTitle(title)

    @pyqtSlot()
    def _update_checked_items(self) -> None:
        self._checked_items = []
        for indx in range(self._item_model.rowCount()):
            item = self._item_model.item(indx)
            if item.checkState() == Qt.Checked:
                self._checked_items.append(item)

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

    def checked_item_ids(self) -> list:
        if not self._checked_items:
            return []
        return [i.node().item_id() for i in self._checked_items]

    def validate(self) -> bool:
        chkd_cnt = len(self._checked_items)
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

        order_details['valid'] = valid
        order_details['item_ids'] = self.checked_item_ids()
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
            f'  item count: {len(self._checked_items)}\n'
            f'  type_ids: {self.checked_item_ids()}\n'
            f'  bundle_name: {self._order_bundle_name}\n'
            f'  tools: {tools}'
        )

        return order_details

    # noinspection PyUnusedLocal
    @pyqtSlot('QStandardItem*')
    def _item_changed(self, item):
        self._update_checked_items()
        self._update_groupbox_title()
        self.validate()

    @pyqtSlot('QModelIndex')
    def _item_clicked(self, indx):
        item = self._item_model.itemFromIndex(indx)

        # Toggle checked status
        if item.checkState() == Qt.Checked:
            item.setCheckState(Qt.Unchecked)
        else:
            item.setCheckState(Qt.Checked)

    @pyqtSlot(bool)
    def _batch_check_items(self, check_all: bool = True):
        for indx in range(self._item_model.rowCount()):
            item = self._item_model.item(indx)
            if check_all:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
        self.listViewItems.setFocus()

    @pyqtSlot(bool)
    def _group_box_collapsed_changed(self, collapsed):
        if collapsed:
            return
        sender = self.sender()
        if sender.__class__.__name__ == 'QgsCollapsibleGroupBox':
            if sender.isChecked():
                # noinspection PyTypeChecker
                listwdgt: QListView = sender.findChild(QListView)
                if listwdgt:
                    listwdgt.setFocus()
        if not collapsed and not self._item_model.thumbnails_fetched():
            self._item_model.fetch_missing_thumbnails()


class PlanetOrdersDialog(ORDERS_BASE, ORDERS_WIDGET):
    """
    """

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

    def __init__(self, item_node_queue: dict,
                 p_client: Optional[PlanetClient] = None,
                 tool_resources: Optional[dict] = None,
                 parent=None,
                 iface=None,
                 ):
        super().__init__(parent=parent)

        self.setupUi(self)

        self._parent = parent
        self._iface = iface

        self._p_client = p_client
        self._api_client = self._p_client.api_client()
        self._api_key = self._p_client.api_key()
        # TODO: Grab responseTimeOut from plugin settings and override default
        self._response_timeout = RESPONSE_TIMEOUT
        self._tool_resources = tool_resources

        bundles_file = os.path.join(
            plugin_path, 'planet_api', 'resources', 'bundles.json')
        self._order_bundles = PlanetOrdersV2Bundles(bundles_file)
        self._item_orders = OrderedDict()

        self.setMinimumWidth(640)
        self.setMinimumHeight(720)

        self.lblName.setStyleSheet(self.NAME_HIGHLIGHT)
        # noinspection PyUnresolvedReferences
        self.leName.textChanged.connect(self.validate)

        self._watchers = {}

        self.frameOrderLog.hide()
        self.btnOrderLogClose.clicked.connect(self._close_order_log)
        self.btnCopyLog.clicked.connect(self._copy_log_to_clipboard)

        self.tbOrderLog.setOpenExternalLinks(False)
        self.tbOrderLog.anchorClicked.connect(self._open_orders_monitor_dialog)

        self._orders = OrderedDict()
        self.btnPlaceOrder = self.buttonBox.button(QDialogButtonBox.Ok)
        self.btnPlaceOrder.setText(
            f'Place Order{"s" if len(item_node_queue) > 1 else ""}')
        # noinspection PyUnresolvedReferences
        self.buttonBox.accepted.connect(self.place_orders)
        # noinspection PyUnresolvedReferences
        self.buttonBox.rejected.connect(self.reject)

        self._thumb_cache_dir: str = pluginSetting(
            'thumbCachePath', namespace=SETTINGS_NAMESPACE)

        first = None
        self._item_type_widgets = {}
        for it_nq in sorted(item_node_queue.keys()):
            oi_w = PlanetOrderItemTypeWidget(
                it_nq,
                item_node_queue[it_nq],
                self._thumb_cache_dir,
                self._api_client,
                self._tool_resources,
                parent=self,
            )
            oi_w.grpBxItemType.setCollapsed(True)
            if not first:
                first = oi_w
            oi_w.validationPerformed.connect(self.validate)
            self._item_type_widgets[it_nq] = oi_w
            self.scrollAreaItemTypesContents.layout().addWidget(
                self._item_type_widgets[it_nq])

        self.scrollAreaItemTypesContents.layout().addStretch(3)

        # Trigger thumbnail updating for first item type widget
        first.grpBxItemType.setCollapsed(False)

        self.validate()

    def order_bundles(self):
        return self._order_bundles

    def thumb_cache(self):
        return self._thumb_cache

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
        self._item_orders.clear()
        for i_type in ITEM_TYPE_SPECS:
            if i_type not in self._item_type_widgets:
                continue
            it_wgdt: PlanetOrderItemTypeWidget = \
                self._item_type_widgets[i_type]
            self._item_orders[i_type] = it_wgdt.get_order()

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

        name = str(self.leName.text())

        for io_k, io_v in self._item_orders.items():
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
                    if self._tool_resources['aoi'] is None:
                        self._log('Clip tool is missing AOI, skipping')
                        continue
                    order['tools'].append(
                        {
                            'clip': {
                                'aoi': json.loads(self._tool_resources['aoi'])
                            }
                        }
                    )

            self._orders[io_k] = order

            log.debug(f'{io_k} order...\n{json.dumps(order, indent=2)}')

        # return

        # Submit orders asynchronously
        self._log('Submitting orders...')
        for item_type, order in self._orders.items():

            if item_type in self._watchers:
                self._log(
                    f'Order for {item_type} already registered, skipping')
                continue

            watcher = self._add_watcher(item_type)

            # Set up async order request
            self._watchers[item_type]['response'] = \
                self._p_client.create_order(
                    order,
                    callback=partial(dispatch_callback, watcher=watcher)
                )

            resp: models.Response = self._watchers[item_type]['response']
            watcher.register_response(resp)

            self._log(f'Order for {item_type} submitted')
            if is_segments_write_key_valid():
                analytics.track(self._p_client.user()["email"], "Order placed", 
                                {
                                "name": order["name"], 
                                "numItems": order["products"][0]["item_ids"]
                                }
            )

        self._log('----------------------- '
                  'LEAVE THIS WINDOW OPEN FOR RESPONSE'
                  ' -----------------------')

    @pyqtSlot(str, 'PyQt_PyObject')
    def _order_response(self, item_type: str, body: models.Order):

        if not item_type:
            self._log('Requesting order failed: no item_type')
            # self._remove_watcher(item_type)
            return

        if body is None or not hasattr(body, 'response'):
            self._log(f'Requesting {item_type} order failed: '
                      f'no body or response')
            self._remove_watcher(item_type)
            return

        resp: ReqResponse = body.response
        # log.debug(requests_response_metadata(resp))

        if not resp.ok:
            # TODO: Add the error reason
            self._log(f'Requesting {item_type} order failed: response error')
            self._remove_watcher(item_type)
            return

        # Process JSON response
        resp_data = body.get()
        log.debug(f'Order resp_data:\n{resp_data}')
        if not resp_data:
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

        if not resp_data.get("id"):
            self._log(f'Requesting {item_type} order failed: '
                      f'response data contains no Order ID')
            return

        # Queued
        self._remove_watcher(item_type)

        bundle = 'unknown'
        itemtype = 'Unknown type'
        itemids = []
        itemids_cnt = '_'
        products: list = resp_data.get('products')
        if products and len(products) > 0:
            bundle = products[0].get('product_bundle')
            itemtype = products[0].get('item_type')
            itemids = products[0].get('item_ids')

        if itemids:
            itemids_cnt = len(itemids)

        self._log(
            f'<br><br>'
            f'<b>Order for {item_type} successfully QUEUED:</b><br>'
            f' --  Name: {resp_data.get("name")}<br>'
            f' --  Created on: {resp_data.get("created_on")}<br>'
            f' -- Order ID: <b>{resp_data.get("id")}</b> '
            f'SAVE THIS FOR REFERENCE<br>'
            f' -- Order type: {itemtype} ({itemids_cnt} items)<br>'
            f' -- Bundle: {bundle}<br>'
            f' -- State: {resp_data.get("state")}<br>'
            f' -- Service message: {resp_data.get("last_message")}<br><br>'
            f'<b>IMPORTANT:</b> Open the <a href="opendlg">Orders monitor'
            f'dialog</a> to monitor your order status and download it when '
            f'possible.<br>'
            f'You also should receive an email when your order is ready to '
            f'download.<br>'
        )

    def _add_watcher(self, item_type: str) -> PlanetCallbackWatcher:

        self._watchers[item_type] = {
            'watcher': PlanetCallbackWatcher(
                parent=self, watcher_id=item_type),
        }
        w: PlanetCallbackWatcher = self._watchers[item_type]['watcher']
        w.responseFinishedWithId[str, 'PyQt_PyObject']. \
            connect(self._order_response)
        w.responseCancelledWithId[str].connect(self._order_cancelled)
        w.responseTimedOutWithId[str, int].connect(self._order_timed_out)

        self.orderShouldCancel[str].connect(w.cancel_response)
        return w

    def _remove_watcher(self, item_type) -> None:
        if item_type in self._watchers:
            w: PlanetCallbackWatcher = self._watchers[item_type]['watcher']
            w.disconnect()
            del self._watchers[item_type]

    @pyqtSlot(str, int)
    def _order_timed_out(self, item_type, timeout: int = RESPONSE_TIMEOUT):
        self._log(f'Requesting {item_type} order failed: '
                  f'timed out ({timeout} seconds)')
        self._remove_watcher(item_type)

    @pyqtSlot(str)
    def _order_cancelled(self, item_type):
        self._log(f'Requesting {item_type} order cancelled')
        self._remove_watcher(item_type)

    @pyqtSlot(str)
    def cancel_order(self, item_type):
        self._log(f'Attempting to cancel {item_type} order...')
        self.orderShouldCancel.emit(item_type)

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


if __name__ == "__main__":
    sys.path.insert(0, plugin_path)

    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from resources import qgis_resources

    from planet_explorer.planet_api.p_specs import RESOURCE_DAILY

    apikey = os.getenv('PL_API_KEY', None)
    if not apikey:
        log.debug('No API key in environ')
        sys.exit(1)

    # Supply path to qgis install location
    # QgsApplication.setPrefixPath(os.environ.get('QGIS_PREFIX_PATH'), True)

    # In python3 we need to convert to a bytes object (or should
    # QgsApplication accept a QString instead of const char* ?)
    try:
        argvb = list(map(os.fsencode, sys.argv))
    except AttributeError:
        argvb = sys.argv

    # Create a reference to the QgsApplication.  Setting the
    # second argument to False disables the GUI.
    qgs = QgsApplication(argvb, True)

    # Load providers
    qgs.initQgis()

    readSettings(settings_path=os.path.join(plugin_path, 'settings.json'))
    SETTINGS_NAMESPACE = None

    item_json_file = os.path.join(
        plugin_path, 'gui', 'resources', 'item-types.json')
    with open(item_json_file, 'r') as fp:
        json_of_items = json.load(fp)

    # log.debug(f'features in collection:\n{json_of_items}')

    nodes = []
    # for item_json in json_of_items:
    for item_json in json_of_items['features']:
        p_node = PlanetNode(
            resource=item_json,
            resource_type=RESOURCE_DAILY,
        )
        nodes.append(p_node)

    item_type_node_queue = {}
    for p_node in nodes:
        n_type = p_node.item_type()
        if n_type not in item_type_node_queue:
            item_type_node_queue[n_type] = []
        item_type_node_queue[n_type].append(p_node)

    # log.debug(f'item_type_node_queue:\n{item_type_node_queue}')

    pclient = PlanetClient(api_key=apikey)

    dlg = PlanetOrdersDialog(
        item_type_node_queue,
        p_client=pclient,
        parent=None,
        iface=None,
    )

    dlg.setMinimumHeight(400)

    dlg.exec_()

    qgs.exitQgis()

    sys.exit(0)

