# -*- coding: utf-8 -*-
"""
***************************************************************************
    test_thumbnail_cache.py
---------------------
Date                 : September 2019
Author               : Planet Federal
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
# from typing import (
#     Optional,
# )

# noinspection PyPackageRequirements
# from requests import Response as ReqResponse

# noinspection PyPackageRequirements
from PyQt5 import uic
# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    Qt,
    pyqtSlot,
    pyqtSignal,
    # QObject,
    QSize,
    QTimer,
    QModelIndex,
    # QVariant,
)
# noinspection PyPackageRequirements
from PyQt5.QtGui import (
    QIcon,
    QStandardItemModel,
    QStandardItem,
    QPixmap,
)
# noinspection PyPackageRequirements
from PyQt5.QtWidgets import (
    QPushButton,
    QProgressBar,
    QTreeView,
    QFrame,
)

from planet.api.client import (
    ClientV1,
)
# from planet.api import models as api_models
# from planet.api.exceptions import APIException, InvalidIdentity

plugin_path = os.path.split(os.path.dirname(__file__))[0]

if __name__ == "__main__":
    print(plugin_path)
    sys.path.insert(0, plugin_path)
    # noinspection PyUnresolvedReferences
    from planet_explorer.planet_api.p_thumnails import (
        PlanetThumbnailCache,
    )
    # noinspection PyUnresolvedReferences
    from planet_explorer.resources import resources
else:
    from ..planet_api.p_thumnails import (
        PlanetThumbnailCache,
    )
    # noinspection PyUnresolvedReferences
    from ..resources import resources

DLG_WIDGET, DLG_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'test_thumbnail_cache.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

ITEM_ICON = QIcon(':/plugins/planet_explorer/thumb-placeholder.svg')

ITEM_JSON = os.path.join(plugin_path,
                         'planet_api/thumbnails/thumbs.json')

ITEM_ID_USER_ROLE = Qt.UserRole + 1

# TODO: Pull from settings
THUMB_CACHE_DIR = '/opt/p_thumbcache'


class ThumbnailTestItem(QStandardItem):

    def __init__(self, item: dict):
        super().__init__()

        self._item_id = item['id']
        self._item_props = item['properties']
        self._item_type = self._item_props['item_type']

        self.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.setText(f'{self._item_type}\n{self._item_id}')
        self.setIcon(ITEM_ICON)
        self.setData(f'{self._item_type}__{self._item_id}', ITEM_ID_USER_ROLE)

    def item_id(self):
        return self._item_id

    def item_type(self):
        return self._item_type

    def item_properties(self):
        return self._item_props


class ThumbnailCacheTestDialog(DLG_BASE, DLG_WIDGET):

    thumbnailFetchShouldCancel = pyqtSignal(str)

    btnCancel: QPushButton
    progressBar: QProgressBar
    frameProgress: QFrame
    treeView: QTreeView

    def __init__(self, parent=None, api_key=None):
        super().__init__(parent=parent)

        self.setupUi(self)
        self._api_key = api_key

        self.btnCancel.setEnabled(False)
        self.progressBar.hide()

        self._model = QStandardItemModel(parent=self)
        self._root = self._model.invisibleRootItem()

        self.treeView.setIconSize(QSize(48, 48))
        self.treeView.setAlternatingRowColors(True)
        self.treeView.setHeaderHidden(True)

        self.treeView.setModel(self._model)

        # noinspection PyUnresolvedReferences
        self.btnCancel.clicked[bool].connect(self._cancel_thumbnail_fetch)

        self._client = ClientV1(api_key=self._api_key)

        self._thumb_cache = PlanetThumbnailCache(
            THUMB_CACHE_DIR, self._client, parent=self)
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
            self._thumb_cache.cancel_fetch)

        self._thumb_queue = {}

        # self.frameProgress.setHidden(True)

        QTimer.singleShot(2, self.load_items)

    def _start_progress(self):
        self.btnCancel.setEnabled(True)
        self.progressBar.show()

    def _stop_progress(self):
        self.btnCancel.setEnabled(False)
        self.progressBar.hide()

    def _add_to_thumb_queue(self, item_key, item_indx):
        if item_key not in self._thumb_queue:
            self._thumb_queue[item_key] = item_indx
        if len(self._thumb_queue) > 0:
            self._start_progress()

    def _in_thumb_queue(self, item_key):
        return item_key in self._thumb_queue

    def _thumb_queue_index(self, item_key):
        if item_key in self._thumb_queue:
            return self._thumb_queue[item_key]
        return QModelIndex()

    def _remove_from_thumb_queue(self, item_key):
        if item_key in self._thumb_queue:
            del self._thumb_queue[item_key]
        if len(self._thumb_queue) == 0:
            self._stop_progress()

    @pyqtSlot()
    def load_items(self):
        with open(ITEM_JSON, 'r') as fp:
            items = json.load(fp)

        for item in items['features']:
            std_item = ThumbnailTestItem(item)
            self._root.appendRow(std_item)
            self._add_to_thumb_queue(
                f'{std_item.item_type()}__{std_item.item_id()}',
                std_item.index())
            self._fetch_thumbnail(std_item)

    def _fetch_thumbnail(self, std_item: ThumbnailTestItem):
        self._thumb_cache.fetch_thumbnail(
            f'{std_item.item_type()}__{std_item.item_id()}',
            item_id=std_item.item_id(),
            item_type=std_item.item_type(),
            item_properties=std_item.item_properties()
        )

    @pyqtSlot(str)
    def _thumbnail_fetch_started(self, item_key):
        log.debug(f'Thumbnail fetch started for {item_key}')
        self._start_progress()

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

        # Too much overhead for this approach, use queue instead...
        #
        # match_indxs = self._model.match(
        #     self._root.child(0, 0).index(), ITEM_ID_USER_ROLE,
        #     QVariant(item_key), hits=1, flags=Qt.MatchExactly
        # )
        # if not match_indxs:
        #     log.debug(f'No matching model indexes for {item_key}')
        #
        # for indx in match_indxs:
        #     std_item = self._model.itemFromIndex(indx)
        #     png = QPixmap(thumb_path, 'PNG')
        #     std_item.setIcon(QIcon(png))

        indx = self._thumb_queue_index(item_key)
        if not indx.isValid():
            self._remove_from_thumb_queue(item_key)
            return
        std_item = self._model.itemFromIndex(indx)
        png = QPixmap(thumb_path, 'PNG')
        std_item.setIcon(QIcon(png))

        self._remove_from_thumb_queue(item_key)

    @pyqtSlot(bool)
    def _cancel_thumbnail_fetch(self, _):
        items = [i for i in self._thumb_queue]
        for item in items:
            self.thumbnailFetchShouldCancel.emit(item)
        # self._thumb_queue.clear()
        # self._stop_progress()


if __name__ == "__main__":
    # noinspection PyPackageRequirements
    from PyQt5.QtWidgets import (
        QApplication,
        QDialog,
    )

    app = QApplication(sys.argv)

    apikey = os.getenv('PL_API_KEY')

    thumb_tree_dlg: QDialog = ThumbnailCacheTestDialog(api_key=apikey)

    thumb_tree_dlg.setMaximumHeight(320)

    thumb_tree_dlg.show()

    sys.exit(app.exec_())
