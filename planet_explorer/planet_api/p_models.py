# -*- coding: utf-8 -*-
"""
***************************************************************************
    p_models.py
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

Some parts based upon work by Tim Wakeham...
***************************************************************************
http://blog.tjwakeham.com/lazy-loading-pyqt-data-models/
"""
__author__ = 'Planet Federal'
__date__ = 'August 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import json
import tempfile
import datetime
import logging
import time
import locale

from collections import OrderedDict

from typing import (
    Optional,
    List,
)
from functools import partial

# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    pyqtSignal,
    pyqtSlot,
    Qt,
    # QObject,
    QModelIndex,
    QAbstractItemModel,
    # QVariant,
    QTimer,
    QFile,
    QIODevice,
)

# noinspection PyPackageRequirements
from PyQt5.QtGui import (
    QPixmap,
    # QIcon,
    QImage,
)

from planet.api import models
from planet.api.exceptions import APIException

# from planet.api.models import JSON
from .p_client import (
    PlanetClient,
)
from .p_network import (
    PlanetCallbackWatcher,
    dispatch_callback,
    RESPONSE_TIMEOUT,
)
from .p_thumnails import PlanetThumbnailCache
from .p_node import PlanetNode, PlanetNodeMetadata
from .p_node import PlanetNodeType as NodeT
from .p_utils import geometry_from_request
from .p_specs import (
    # RESOURCE_MOSAICS,
    RESOURCE_DAILY,
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
if LOG_LEVEL == 'DEBUG':
    tstamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_file = tempfile.NamedTemporaryFile(
        prefix=f'pe_search_results_{tstamp}_')
    fh = logging.FileHandler(log_file.name)
    # fh.setLevel(logging.DEBUG)
    log.addHandler(fh)
    log.info(f"Debug log file:\n{log_file.name}")
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

TOP_ITEMS_BATCH_ENV = os.environ.get('TOP_ITEMS_BATCH', None)

LOAD_TEMPLATE = '<br><i><b><a href="link" style="color: rgb(0, 157, 165);">{name}</a></b></i><br>'

class SearchException(Exception):
    """Exceptions raised during API search operation"""
    pass


# noinspection PyPep8Naming
class PlanetSearchResultsModel(QAbstractItemModel):

    FLAGS_DEFAULT = Qt.ItemIsEnabled | Qt.ItemIsSelectable

    COLUMN_HEADERS = ['Item', '']

    # TODO: Make this default a user setting as well
    TOP_ITEMS_BATCH = TOP_ITEMS_BATCH_ENV if TOP_ITEMS_BATCH_ENV else 250

    ActionsRole = Qt.UserRole + 1
    # CheckedRole = Qt.UserRole + 2
    # ThumbRole = Qt.UserRole + 3
    _roles = {ActionsRole: b"actions"}

    searchStarted = pyqtSignal()
    searchFinished = pyqtSignal()
    searchNoResults = pyqtSignal()
    searchCancelled = pyqtSignal()
    searchTimedOut = pyqtSignal(int)  # response timeout in seconds    

    searchShouldCancel = pyqtSignal()

    thumbnailFetchShouldCancel = pyqtSignal(str)

    itemCountChanged = pyqtSignal()

    results: Optional[models.Items]
    _response: Optional[models.Response]
    page_to_add: Optional[models.Items]

    def __init__(self, api_key=None,
                 response_timeout=RESPONSE_TIMEOUT,
                 thumb_cache_dir=None,
                 sort_order=None,
                 parent=None):
        super().__init__(parent=parent)

        self._api_key = api_key
        self._request = None
        self._response = None
        self._response_timeout = response_timeout
        self._thumb_cache_dir = thumb_cache_dir

        self._metadata_to_show = [PlanetNodeMetadata.CLOUD_PERCENTAGE, 
                                  PlanetNodeMetadata.GROUND_SAMPLE_DISTANCE]

        self._set_sort_order(sort_order)

        self._reset()

        self._initial_search_done = False

        self._watcher = PlanetCallbackWatcher(
            parent=self, timeout=self._response_timeout)
        self._watcher.responseRegistered.connect(self.searchStarted)
        self._watcher.responseCancelled.connect(self.searchCancelled)
        self._watcher.responseTimedOut[int].connect(self.searchTimedOut)
        self._watcher.responseFinished['PyQt_PyObject'].connect(
            self.search_finished)
        self.searchShouldCancel.connect(self._watcher.cancel_response)

        # Instantiate wrapper and API clients
        self._p_client = PlanetClient.getInstance()
        self._api_client = self._p_client.api_client()

        self.root: PlanetNode = PlanetNode('Root', node_type=NodeT.ROOT)
        self.root.set_index(QModelIndex())

        self._thumb_cache = PlanetThumbnailCache(
            self._thumb_cache_dir, self._api_client, parent=self)
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

        # This is async now...
        # if self._request is not None:
        #     self.start_api_search()

    def update_request(self, request):
        self._request = request
        self.truncate()
        self.start_api_search()

    def _set_sort_order(self, sort_order):
        self._sort_order = sort_order or ('acquired', 'desc')
        self._sort_field = sort_order[0] if len(sort_order) > 0 else ''
        self._sort_direction = sort_order[1] if len(sort_order) > 1 else ''
        log.debug(f'sort_field: {self._sort_field}')
        self._column_headers = [
            f'Date {self._sort_field}',
            ''
        ]

    def update_sort_order(self, sort_order):
        self._set_sort_order(sort_order)
        self.truncate()
        self.start_api_search()


    def set_metadata_to_show(self, metadata_to_show):
        self._metadata_to_show = metadata_to_show
        def traverse(node):         
            if node.has_children():
                for child in node.children():
                    traverse(child)
            else:
                node.set_metadata_to_show(metadata_to_show)                
        traverse(self.root)

    def metadata_to_show(self):
        return self._metadata_to_show

    def results(self):
        return self._results

    def p_client(self):
        return self._p_client

    # takes a model index and returns the related Python node
    def get_node(self, index):
        if index.isValid():
            return index.internalPointer()
        else:
            return self.root

    @pyqtSlot('QModelIndex')
    def fetch_more_top_items(self, index):
        node = self.get_node(index)
        if (node.node_type() == NodeT.LOAD_MORE
                and node.parent() == self.root):
            node.set_name(LOAD_TEMPLATE.format(name='Loading...'))
            # node_index = node.index()
            # log.info(
            #     f'Node index clicked: '
            #     f'row {node_index.row()}, '
            #     f'col {node_index.column()}')
            # noinspection PyUnresolvedReferences
            self.dataChanged.emit(index, index, [Qt.DisplayRole])
            # This needs a non-0 timer, or 'Loading...' will not appear
            QTimer.singleShot(1, self.load_top_items)

    @pyqtSlot()
    def start_api_search(self):
        """
        Start search of Planet catalog with given request.
        :rtype: None
        """
        self.searchStarted.emit()
        if not self._p_client.has_api_key():
            raise SearchException('No API key defined for search')

        # TODO: Validate request object

        # Add placeholder 'Loading...' item
        # node = PlanetNode('<br>Loading...<br>',
        #                   node_type=NodeT.LOADING)
        # self.insertRows(0, [node])

        # Initialize search, then start callback watching timer
        try:

            stats_request = {"interval": "year"}
            stats_request.update(self._request)
            resp = self._p_client.client.stats(stats_request).get()
            self._total_count = sum([b["count"] for b in resp["buckets"]])

            self._response: models.Response = self._p_client.quick_search(
                self._request,
                page_size=self.TOP_ITEMS_BATCH,
                sort=' '.join(self._sort_order),
                callback=partial(dispatch_callback, watcher=self._watcher),
            )
            self._watcher.register_response(self._response)

        except APIException as exc:
            # TODO: Turn this into a user message and self-delete results tab
            # raise SearchException from exc
            log.critical(f'Quick Search failed, exception:\n{exc}')
            return

        if LOG_VERBOSE:
            log.debug(f"Request:\n{json.dumps(self._request, indent=2)}")

    @pyqtSlot()
    def cancel_search(self):
        self.searchShouldCancel.emit()

    @pyqtSlot('PyQt_PyObject')
    def search_finished(self, results):
        self._results = results

        if not hasattr(self._results, 'iter'):
            log.debug('Search results has no iterator')
            return

        # Iterate pages, not items (we need to know if _next link is there)
        self._page_iter = self._results.iter()

        self.searchFinished.emit()

        # Remove Loading... item
        # if not self.removeRows(0, 1):
        #     log.critical('Could not remove `Loading...` row')
        #     return

        QTimer.singleShot(0, self.load_top_items)

    @staticmethod
    def _page_contains_next(page: models.Items) -> bool:
        links = page.get()[page.LINKS_KEY]
        next_ = links.get(page.NEXT_KEY, None)
        return next_ is not None

    def load_top_items(self):
        # generate root node children up to n-count
        if not self._page_to_add:
            # TODO: Catch errors
            self._page_to_add = next(self._page_iter, None)

        if self._page_to_add is None and not self._initial_search_done:
            self.searchNoResults.emit()
            log.debug('Search returned no results')
            return
        self._initial_search_done = True

        if self._page_to_add is None and self.root:
            # Something went pear-shaped on request, page iter broken
            last_root_node = self.root.last_child()
            if last_root_node.node_type() == NodeT.LOAD_MORE:
                last_root_node.set_name('<br>Error: unable to load more<br>')
                last_root_node.set_node_type(NodeT.UNDEFINED)
                # noinspection PyUnresolvedReferences
                # self.dataChanged.emit(cur_index, cur_index, [Qt.DisplayRole])
            return

        self._page += 1
        if LOG_VERBOSE:
            log.debug(f"\nPage {self._page}\n"
                      f"{json.dumps(self._page_to_add.get(), indent=2)}")

        # log.info(f'Removing `Load more...` row at: {self.rowCount() - 1}')
        # if not self.remove_last_row():
        if self.rowCount() and not self.removeRows(self.rowCount() - 1, 1):
            log.critical('Could not remove `Load more...` row')

        nodes = []
        for item in self._page_to_add.get()[models.Items.ITEM_KEY]:
            node = PlanetNode(
                resource=item,
                resource_type=RESOURCE_DAILY,
                sort_field=self._sort_field,
                metadata_to_show = self._metadata_to_show
            )
            nodes.append(node)
            # self._top_items.append(node)
            # self._top_item_count += 1

        self._append_daily_items(nodes)

        # Test for next page
        if self._page_contains_next(self._page_to_add):
            loaded = locale.format("%d", self._item_count, grouping=True)
            total = locale.format("%d", self._total_count, grouping=True)
            if loaded != total:           
                node = PlanetNode(LOAD_TEMPLATE.format(
                            name='Load more... '
                            f'(Showing {loaded} of {total} results)'),
                            node_type=NodeT.LOAD_MORE)
                self.insertRows(self.rowCount(), [node])

        self.itemCountChanged.emit()

    # check if the node has data that has not been loaded yet
    def canFetchMore(self, index):

        node = self.get_node(index)

        if node.can_fetch_more() and not node.is_traversed():
            log.info('Can fetch more nodes...')
            return True

        return False

    # called if canFetchMore returns True, then dynamically inserts nodes
    # required for directory contents
    def fetchMore(self, index):
        parent_node: PlanetNode = self.get_node(index)

        if parent_node == self.root:
            pass
        else:
            # TODO: Mosaic quads lazy load thumbnails, or on view expanded()?

            log.debug('Fetching more nodes...')

            if parent_node.node_type() == NodeT.DAILY_SAT_GROUP:
                for child in parent_node.children():
                    child: PlanetNode
                    if child.has_thumbnail() and not child.thumbnail_loaded():
                        self.add_to_thumb_queue(
                            child.item_type_id_key(), child.index())
                        self.fetch_thumbnail(child)

                parent_node.set_is_traversed(True)

    # noinspection PyMethodMayBeStatic
    def _append_daily_items(self, nodes: List[PlanetNode]):
        # Note: sort_date of nodes should have already been set

        self._item_count += len(nodes)

        scenes = set()
        sat_groups = set()
        new_scenes = []
        new_sat_groups = []
        for node in nodes:
            n_type = node.item_type()
            n_date = node.sort_date().date()
            scene = self._find_scene_node(n_type, n_date)
            if scene is None:
                scene = PlanetNode(
                    name=n_type,
                    resource_type=RESOURCE_DAILY,
                    node_type=NodeT.DAILY_SCENE,
                    metadata_to_show = self._metadata_to_show
                )                                        
                self.insertRows(
                    self.root.child_count(), [scene], self.root.index())
                new_scenes.append(scene)
            scenes.add(scene)

            # TODO: combine geometries for % area coverage of AOI for scene
            n_images: List[PlanetNode]
            n_sat = node.item_properties()['satellite_id']

            sat_grp = self._find_satellite_node(scene, n_sat)
            if sat_grp is None:
                sat_grp = PlanetNode(
                    name=n_sat,
                    resource_type=RESOURCE_DAILY,
                    node_type=NodeT.DAILY_SAT_GROUP,
                )
                self.insertRows(
                    scene.child_count(), [sat_grp], scene.index())
                new_sat_groups.append(sat_grp)

            sat_groups.add(sat_grp)
            self.insertRows(
                sat_grp.child_count(), [node], sat_grp.index())
            
            sat_grp.add_item_type_id(node.item_type_id())
            sat_grp.add_geometry(node.geometry())            
            sat_grp.set_sort_date(sat_grp.first_child().sort_date())            
            sat_grp.set_can_be_downloaded(node.can_be_downloaded() 
                                        or sat_grp.can_be_downloaded())

            scene.add_item_type_id(node.item_type_id())
            scene.add_geometry(node.geometry())
            scene.set_sort_date(scene.first_child().sort_date())            
            scene.set_can_be_downloaded(node.can_be_downloaded() 
                                        or scene.can_be_downloaded())
                
        
        self._reset_has_new_children(self.root)
        for scene in scenes:
            if scene.has_thumbnail():
                self.add_to_thumb_queue(
                    scene.item_type_id_key(), scene.index())
                self.fetch_job_thumbnail(scene)
            scene.set_has_new_children(scene not in new_scenes)

        for sat_grp in sat_groups:
            sat_grp.set_has_new_children(sat_grp not in new_sat_groups)

        # return scenes

    def _reset_has_new_children(self, root):
        for child in root.children():
            child.set_has_new_children(False)
            self._reset_has_new_children(child)

    def _find_scene_node(self, scene, date):        
        for child in self.root.children():
            date2 = child.sort_date().date()
            if scene == child.name() and date == date2:
                return child

    def _find_satellite_node(self, parent, name):
        for child in parent.children():
            if name == child.name():
                return child                
        
    # returns True for directory nodes so that Qt knows to check if there is
    # more to load
    def hasChildren(self, index=QModelIndex(), *args, **kwargs):
        node = self.get_node(index)

        if node.has_children():
            # Includes children that have YET to be fetched
            return True

        return super().hasChildren(index)

    # should return 0 if there is data to fetch (handled implicitly by check
    # length of child list)
    def rowCount(self, parent=QModelIndex(), *args, **kwargs):
        node = self.get_node(parent)
        return node.child_count()

    def columnCount(self, parent=QModelIndex(), *args, **kwargs):
        return 2

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        flags = self.FLAGS_DEFAULT

        node = self.get_node(index)

        if node.is_undefined_node_type():
            return Qt.NoItemFlags

        if node.is_base_node():
            return flags

        if index.column() == 1:
            return flags

        if index.column() == 0:
            flags |= Qt.ItemIsUserCheckable
            # flags |= Qt.ItemIsUserTristate
            flags |= Qt.ItemIsAutoTristate
            # flags |= Qt.ItemIsEditable

        return flags

    def parent(self, index):
        node = self.get_node(index)

        parent_node = node.parent()
        if not parent_node or parent_node == self.root:
            return QModelIndex()

        return self.createIndex(parent_node.row(), 0, parent_node)

    def index(self, row, column, parent=QModelIndex(), *args, **kwargs):
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()

        node = self.get_node(parent)

        # if node == self.root:
        #     return QModelIndex()

        child = node.child(row)

        if not child:
            return QModelIndex()

        return self.createIndex(row, column, child)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if (orientation == Qt.Horizontal and role == Qt.DisplayRole):
            return self._column_headers[section]
        return super(PlanetSearchResultsModel, self).headerData(
            section, orientation, role=role)

    @staticmethod
    def _children_check_state(node):
        if node.has_children():
            states = [n.checked_state() for n in node.children()]
            if all([s == Qt.Unchecked for s in states]):
                return Qt.Unchecked
            if all([s == Qt.Checked for s in states]):
                return Qt.Checked
            return Qt.PartiallyChecked
        else:
            return node.checked_state()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        node = self.get_node(index)

        if index.column() == 0:
            if role == Qt.DecorationRole:
                return node.icon()
            if role == Qt.DisplayRole:
                return node.description()
            if role == Qt.ToolTipRole:
                return node._tooltip

        # if role == Qt.CheckStateRole and index.column() == 0:
        #     return node.checked_state
        if (index.column() == 0
                and role == Qt.CheckStateRole
                and node.node_type() != NodeT.LOAD_MORE):
            return self._children_check_state(node)

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if index.column() == 0:
            if role == Qt.EditRole:
                return False

            if role == Qt.CheckStateRole:
                # node = index.internalPointer()
                node = self.get_node(index)

                # if (int(self.flags(index)) & Qt.ItemIsAutoTristate and
                #         value != Qt.PartiallyChecked):
                if not node.can_be_downloaded():
                    node.set_checked_state(Qt.Unchecked)
                else:
                    node.set_checked_state(value)
                if value != Qt.PartiallyChecked:
                    def _set_childrencheckstate(val, parent_node, parent_indx):
                        # if node.checked_state() != value:
                        node_children = parent_node.children()
                        for i in range(len(node_children)):
                            child = node_children[i]
                            # if node_children[i].checked_state != value:
                            if not child.can_be_downloaded():
                                child.set_checked_state(Qt.Unchecked)
                            else:
                                child.set_checked_state(val)
                            child_indx = self.index(i, 0, parent_indx)
                            # noinspection PyUnresolvedReferences
                            self.dataChanged.emit(
                                child_indx, child_indx,
                                [Qt.CheckStateRole])
                            if child.has_children():
                                _set_childrencheckstate(val, child, child_indx)
                            # child = self.child(row, column)
                            # if node_child.checked_state() is not None:
                            #     flags = int(self.flags(index))
                            #     self.setFlags(flags & ~Qt.ItemIsAutoTristate)
                            #     child.setData(value, role)
                            #     self.setFlags(flags)
                    # noinspection PyUnresolvedReferences
                    # self.dataChanged.emit(
                    #     index, index, [Qt.CheckStateRole])
                    _set_childrencheckstate(value, node, index)

                parent_index = index
                while True:
                    child_index = parent_index
                    parent_index = parent_index.parent()
                    if child_index.isValid():
                        child_node = self.get_node(child_index)
                        child_node.set_checked_state(
                            self._children_check_state(child_node))
                        # noinspection PyUnresolvedReferences
                        self.dataChanged.emit(
                            child_index, child_index,
                            [Qt.CheckStateRole])
                    else:
                        break

        return super().setData(index, value, role)

    def insertRows(self, row, nodes, parent=QModelIndex()):
        parent_node = self.get_node(parent)

        # Inserts right *before* row, e.g. rowCount()
        self.beginInsertRows(parent, row, row + len(nodes) - 1)

        # for child in nodes:
        # Do not use i for nodes[i], it is for parent_node insertion
        for i, child in enumerate(nodes, start=row):
            child: PlanetNode
            # So delayed icon loading has dataChanged Qt.DecorationRole context
            # noinspection PyUnusedLocal
            success = parent_node.insert_child(i, child)
            # indx = self.index(row, 0, parent)
            indx = self.createIndex(i, 0, child)
            child.set_index(indx)

        self.endInsertRows()

        return True

    def remove_last_row(self, parent=QModelIndex()):
        parent_node = self.get_node(parent)

        # Account for index row count offset of 1
        last_index = len(parent_node.children()) - 2
        self.beginRemoveRows(parent, last_index, last_index)

        parent_node.remove_last_child()

        self.endRemoveRows()

        return True

    # noinspection DuplicatedCode
    def removeRows(self, row, count, parent=QModelIndex()):

        parent_node = self.get_node(parent)

        # Avoid IndexError
        if row < 0 or row >= parent_node.child_count():
            return False

        self.beginRemoveRows(parent, row, row + count - 1)

        for _ in range(count):
            if not parent_node.remove_child(row):
                break

        self.endRemoveRows()

        return True

    def truncate(self):
        self._reset()
        self.removeRows(0, self.rowCount())

    def _reset(self):
        # Parsed JSON items into a list
        self._top_items = []

        # Count for fetch more operations
        self._top_item_count = 0

        # Values for the 'showing X of Y results' label in the 'load more' node
        self._item_count = 0
        self._total_count = 0

        # self.insertRows(0, [self.root])
        self._page_iter = None
        self._page_to_add = None
        self._page = 0

        self._results = None

    def item_counts(self):
        return self._item_count, self._total_count

    def roleNames(self):
        return self._roles

    def add_to_thumb_queue(self, item_key, item_indx):
        if item_key not in self._thumb_queue:
            self._thumb_queue[item_key] = item_indx
        # if len(self._thumb_queue) > 0:
        #     self._start_progress()

    def _in_thumb_queue(self, item_key):
        return item_key in self._thumb_queue

    def _thumb_queue_index(self, item_key):
        if item_key in self._thumb_queue:
            return self._thumb_queue[item_key]
        return QModelIndex()

    def _remove_from_thumb_queue(self, item_key):
        if item_key in self._thumb_queue:
            del self._thumb_queue[item_key]
        # if len(self._thumb_queue) == 0:
        #     self._stop_progress()

    def thumbnail_cache(self):
        return self._thumb_cache

    def fetch_thumbnail(self, node: PlanetNode):
        self._thumb_cache.fetch_thumbnail(
            node.item_type_id_key(),
            item_id=node.item_id(),
            item_type=node.item_type(),
            item_properties=node.item_properties()
        )

    def fetch_job_thumbnail(self, node: PlanetNode):
        print(self._request)
        self._thumb_cache.fetch_job_thumbnail(
            node.item_type_id_key(),
            self._p_client.api_key(),
            extent_json=geometry_from_request(self._request),
            dest_crs='EPSG:3857',
            item_id=node.item_id(),
            item_type=node.item_type(),
            item_type_ids=node.item_type_id_list(),
            item_properties=node.item_properties(),
            node_type=node.node_type(),
            image_url=None,
            width=256,
            height=256,
            # parent=self,
        )
        # item_key: str,
        # api_key: str,
        # extent_json: Optional[Union[str, dict]] = None,
        # dest_crs: Optional[str] = 'EPSG:3857',
        # item_id: Optional[str] = None,
        # item_type: Optional[str] = None,
        # item_type_ids: Optional[List[str]] = None,
        # item_properties: Optional[dict] = None,
        # node_type: Optional[NodeT] = None,
        # image_url: Optional[str] = None,
        # width: int = 512,
        # height: int = 512,
        # parent: Optional[QObject] = None):

    @pyqtSlot(str)
    def _thumbnail_fetch_started(self, item_key):
        log.debug(f'Thumbnail fetch started for {item_key}')
        # self._start_progress()

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
        node = self.get_node(indx)
        if node.thumbnail_loaded():
            log.debug(f'Thumbnail already loaded for: {item_key}')
            return

        q_file_thumb = QFile(thumb_path)
        timeout = 3
        while not q_file_thumb.open(QIODevice.ReadOnly):
            log.debug(f'Local PNG not readable ({timeout}):\n{thumb_path}')
            if timeout == 0:
                log.debug(f'Local PNG unreadable:\n{thumb_path}')
                break
            time.sleep(1)
            timeout -= 1

        # DON"T USE THIS: apparently has issues with semaphore locking
        # png = QPixmap(thumb_path, 'PNG')
        # Load into QImage instead, then convert to QPixmap
        png = QImage(thumb_path, 'PNG')
        if not png.isNull():
            log.debug(f'Local PNG icon loaded for {item_key}:\n'
                      f'{thumb_path}')
            pm = QPixmap.fromImage(png)
            node.set_thumbnail(pm, local_url=thumb_path)
            # noinspection PyUnresolvedReferences
            self.dataChanged.emit(indx, indx, [Qt.DecorationRole])
        else:
            log.debug(f'Local PNG icon could not be loaded for {item_key}:\n'
                      f'{thumb_path}')
        self._remove_from_thumb_queue(item_key)

    @pyqtSlot(bool)
    def _cancel_thumbnail_fetch(self, _):
        items = [i for i in self._thumb_queue]
        for item in items:
            self.thumbnailFetchShouldCancel.emit(item)
        # self._thumb_queue.clear()
        # self._stop_progress()
