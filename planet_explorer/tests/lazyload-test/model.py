# -*- coding: utf-8 -*-

"""
***************************************************************************
    range_slider.py
    ---------------------
    Date                 : August 2019
    Copyright            : (C) 2019 Planet Inc, https://www.planet.com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************

Based upon work by Tim Wakeham...
***************************************************************************
http://blog.tjwakeham.com/lazy-loading-pyqt-data-models/

"""

import os
import logging

# noinspection PyPackageRequirements
from typing import (
    # Optional,
    Any
)

# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    pyqtSlot,
    Qt,
    QModelIndex,
    QAbstractItemModel,
    QRect,
    QSize
)
# noinspection PyPackageRequirements
from PyQt5.QtGui import (
    QIcon
)
# noinspection PyPackageRequirements
from PyQt5.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    # QStyleOptionToolButton,
    QStyleOptionButton
)

# noinspection PyUnresolvedReferences
from planet_explorer.resources import resources

try:
    from .node import Node
except (ImportError, ModuleNotFoundError):
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from node import Node

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

COG_ICON = QIcon(':/plugins/planet_explorer/cog.svg')


# noinspection DuplicatedCode
class ActionDelegate(QStyledItemDelegate):

    def paint(self, painter, option, index):
        if index.column() != 1:
            QStyledItemDelegate.paint(self, painter, option, index)
            return
        model: Any[FileSystemTreeModel | QAbstractItemModel] = index.model()
        node = model.getNode(index)
        if node.is_fetch_more:
            QStyledItemDelegate.paint(self, painter, option, index)
            return
        rect = option.rect
        # btn = QStyleOptionToolButton()
        # btn.rect = QRect(rect.left() + rect.width() - 30,
        #                  rect.top(), 30, rect.height())
        # btn.text = '...'
        # btn.toolButtonStyle = Qt.ToolButtonIconOnly
        # btn.icon = COG_ICON
        # btn.iconSize = QSize(16, 16)
        # btn.features = QStyleOptionToolButton.Menu | \
        #     QStyleOptionToolButton.MenuButtonPopup | \
        #     QStyleOptionToolButton.HasMenu
        # btn.features = QStyleOptionToolButton.Menu
        # btn.state = QStyle.State_Enabled | \
        #     (QStyle.State_MouseOver
        #      if option.state & QStyle.State_MouseOver
        #      else QStyle.State_None)
        # btn.state = QStyle.State_Enabled
        # QApplication.style().drawComplexControl(
        #     QStyle.CC_ToolButton, btn, painter)

        btn = QStyleOptionButton()
        btn.icon = COG_ICON
        btn.iconSize = QSize(16, 16)
        btn.features = QStyleOptionButton.Flat
        btn.features |= QStyleOptionButton.HasMenu

        btn.state = QStyle.State_Enabled
        btn.state |= (QStyle.State_MouseOver
                      if option.state & QStyle.State_MouseOver
                      else QStyle.State_Enabled)
        btn.state |= (QStyle.State_Selected
                      if option.state & QStyle.State_Selected
                      else QStyle.State_Enabled)
        btn.state |= (QStyle.State_Active
                      if option.state & QStyle.State_Active
                      else QStyle.State_Enabled)

        btn.rect = QRect(rect.left() + rect.width() - 30,
                         rect.top(), 30, rect.height())

        QApplication.style().drawControl(
            QStyle.CE_PushButton, btn, painter)


# noinspection PyPep8Naming,DuplicatedCode
class FileSystemTreeModel(QAbstractItemModel):

    FLAGS_DEFAULT = Qt.ItemIsEnabled | Qt.ItemIsSelectable

    COLUMN_HEADERS = ['Filename', '']

    TOP_ITEMS_BATCH = 6

    ActionsRole = Qt.UserRole + 1
    # CheckedRole = Qt.UserRole + 2
    # ThumbRole = Qt.UserRole + 3
    _roles = {ActionsRole: b"actions"}

    def __init__(self, root, path='/', parent=None):
        super().__init__()

        self.root: Node = root
        self.path = path
        self.parent = parent

        # self.top_item_count = 0
        # self.top_items = []

        # self.insertRows(0, [self.root])
        self.item_iter = None
        self.items_to_add = []
        self.loadTopItems()

    # takes a model index and returns the related Python node
    def getNode(self, index):
        if index.isValid():
            return index.internalPointer()
        else:
            return self.root

    @pyqtSlot('QModelIndex')
    def fetchMoreTopItems(self, index):
        node = self.getNode(index)
        if node.is_fetch_more and node.parent() == self.root:
            print(f'"Load more..." index row: {index.row()}')
            # if not self.removeLastRow():
            if not self.removeRows(index.row() - 1, 1):
                log.critical('Could not remove `Load more...` row')
            self.loadTopItems()

    @staticmethod
    def dir_gen(iterator, count):
        itr = iter(iterator)
        while True:
            nexts = []
            for _ in range(count):
                try:
                    nexts.append(next(itr))
                except StopIteration:
                    break
            if nexts:
                yield nexts
            else:
                break

    def loadTopItems(self):

        if self.item_iter is None:
            self.item_iter = self.dir_gen(
                os.listdir(self.path), self.TOP_ITEMS_BATCH)

        # generate root node children up to n-count
        if not self.items_to_add:
            self.items_to_add = next(self.item_iter, [])

        nodes = []
        for file in self.items_to_add:
            file_path = os.path.join(self.path, file)

            node = Node(file, file_path)
            if os.path.isdir(file_path):
                node.is_dir = True
            nodes.append(node)
            # self.top_items.append(node)
            # self.top_item_count += 1
        if nodes:
            self.insertRows(self.rowCount(), nodes)

        self.items_to_add.clear()

        # Prime next results set
        self.items_to_add = next(self.item_iter, [])
        if len(self.items_to_add) > 0:
            node = Node('Load more...', '')
            node.is_fetch_more = True
            self.insertRows(self.rowCount(), [node])

    # check if the node has data that has not been loaded yet
    def canFetchMore(self, index):
        node = self.getNode(index)

        # if len(self.items_to_add) > 0:
        #     return True
        # elif node == self.root:
        #     self.items_to_add = next(self.item_iter, [])
        #     if len(self.items_to_add) > 0:
        #         log.info('Can fetch more top items...')
        #         return True
        #     # return False
        # elif node.is_dir and not node.is_traversed:
        #     log.info('Can fetch more nodes...')
        #     return True

        if node.is_dir and not node.is_traversed:
            log.info('Can fetch more nodes...')
            return True

        return False

    # called if canFetchMore returns True, then dynamically inserts nodes
    # required for directory contents
    def fetchMore(self, index):
        parent: Node = self.getNode(index)

        if parent == self.root:
            # remainder = len(self.top_items) - self.top_item_count
            # items_to_fetch = min(self.TOP_ITEMS_BATCH, remainder)
            #
            # if items_to_fetch:
            #     log.debug('Fetching more nodes...')
            #     self.beginInsertRows(QModelIndex(), self.top_item_count,
            #                          self.top_item_count + items_to_fetch)
            #
            #     self.top_item_count += items_to_fetch
            #
            #     self.endInsertRows()

            # Works

            # items_to_fetch = len(self.items_to_add)
            # if items_to_fetch:
            #     log.debug('Fetching more top items...')
            #
            #     self.beginInsertRows(index, self.rowCount(),
            #                          self.rowCount() + items_to_fetch)
            #
            #     for file in self.items_to_add:
            #         file_path = os.path.join(self.path, file)
            #
            #         node = Node(file, file_path, parent=self.root)
            #         if os.path.isdir(file_path):
            #             node.is_dir = True
            #         # self.top_items.append(node)
            #         # self.top_item_count += 1
            #
            #     self.endInsertRows()
            #     self.items_to_add.clear()

            pass

        else:
            nodes = []
            for file in os.listdir(parent.path()):
                file_path = os.path.join(parent.path(), file)

                node = Node(file, file_path)
                if os.path.isdir(file_path):
                    node.is_dir = True
                if parent.checked_state != Qt.PartiallyChecked:
                    node.checked_state = parent.checked_state

                nodes.append(node)

            if nodes:
                log.debug('Fetching more nodes...')
                self.insertRows(0, nodes, index)
            parent.is_traversed = True

    # returns True for directory nodes so that Qt knows to check if there is
    # more to load
    def hasChildren(self, index=QModelIndex(), *args, **kwargs):
        node = self.getNode(index)

        if node.is_dir:
            return True

        return super().hasChildren(index)

    # should return 0 if there is data to fetch (handled implicitly by check
    # length of child list)
    def rowCount(self, parent=QModelIndex(), *args, **kwargs):
        node = self.getNode(parent)
        return node.child_count()

    def columnCount(self, parent=QModelIndex(), *args, **kwargs):
        return 2

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        flags = self.FLAGS_DEFAULT
        if index.column() == 0:
            flags |= Qt.ItemIsUserCheckable
            # flags |= Qt.ItemIsUserTristate
            flags |= Qt.ItemIsAutoTristate
            # flags |= Qt.ItemIsEditable

        return flags

    def parent(self, index):
        node = self.getNode(index)

        node_parent = node.parent()
        if not node_parent or node_parent == self.root:
            return QModelIndex()

        return self.createIndex(node_parent.row(), 0, node_parent)

    def index(self, row, column, parent=QModelIndex(), *args, **kwargs):
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()

        node = self.getNode(parent)

        # if node == self.root:
        #     return QModelIndex()

        child = node.child(row)

        if not child:
            return QModelIndex()

        return self.createIndex(row, column, child)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLUMN_HEADERS[section]
        return None

    @staticmethod
    def _childrenCheckState(node):
        if node.has_children():
            states = [n.checked_state for n in node.children()]
            if all([s == Qt.Unchecked for s in states]):
                return Qt.Unchecked
            if all([s == Qt.Checked for s in states]):
                return Qt.Checked
            return Qt.PartiallyChecked
        else:
            return node.checked_state

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        # node = index.internalPointer()
        node = self.getNode(index)

        if role == Qt.DisplayRole:
            if index.column() == 0:
                return f"{node.name()}\nSecond line\nThird line"
            elif index.column() == 1:
                return node.path()

        if role == Qt.DecorationRole:
            if index.column() == 0:
                return QIcon(':/plugins/planet_explorer/thumb-placeholder.svg')

        # if role == Qt.CheckStateRole and index.column() == 0:
        #     return node.checked_state
        if (index.column() == 0
                and role == Qt.CheckStateRole
                and not node.is_fetch_more):
            # return self._childrenCheckState(node)
            if node.has_children():
                states = [n.checked_state for n in node.children()]
                if all([s == Qt.Unchecked for s in states]):
                    return Qt.Unchecked
                if all([s == Qt.Checked for s in states]):
                    return Qt.Checked
                return Qt.PartiallyChecked
            else:
                return node.checked_state

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if index.column() == 0:
            if role == Qt.EditRole:
                return False
            # if role == Qt.CheckStateRole:
            #     node = index.internalPointer()
            #     node.checked_state = value
            #     # noinspection PyUnresolvedReferences
            #     self.dataChanged.emit(index, index)
            #     return True
            if role == Qt.CheckStateRole:
                # node = index.internalPointer()
                node = self.getNode(index)

                # if (int(self.flags(index)) & Qt.ItemIsAutoTristate and
                #         value != Qt.PartiallyChecked):
                node.checked_state = value
                if value != Qt.PartiallyChecked:
                    def _setChildrenCheckState(val, parent, parent_indx):
                        # if node.checked_state != value:
                        node_children = parent.children()
                        for i in range(len(node_children)):
                            child = node_children[i]
                            # if node_children[i].checked_state != value:
                            child.checked_state = val
                            child_indx = self.index(i, 0, parent_indx)
                            # noinspection PyUnresolvedReferences
                            self.dataChanged.emit(
                                child_indx, child_indx,
                                [Qt.CheckStateRole])
                            if child.has_children():
                                _setChildrenCheckState(val, child, child_indx)
                            # child = self.child(row, column)
                            # if node_child.checked_state is not None:
                            #     flags = int(self.flags(index))
                            #     self.setFlags(flags & ~Qt.ItemIsAutoTristate)
                            #     child.setData(value, role)
                            #     self.setFlags(flags)
                    # noinspection PyUnresolvedReferences
                    # self.dataChanged.emit(
                    #     index, index, [Qt.CheckStateRole])
                    _setChildrenCheckState(value, node, index)

                parent_index = index
                while True:
                    child_index = parent_index
                    parent_index = parent_index.parent()
                    if child_index.isValid():
                        child_node = self.getNode(child_index)
                        child_node.checked_state = \
                            self._childrenCheckState(child_node)
                        # noinspection PyUnresolvedReferences
                        self.dataChanged.emit(
                            child_index, child_index,
                            [Qt.CheckStateRole])
                    else:
                        break

                # model = self.model()
                # if model is not None:
                #     parent = self
                #     while True:
                #         parent = parent.parent()
                #         if (parent is not None and
                #                 parent.flags() & Qt.ItemIsAutoTristate):
                #             model.dataChanged.emit(
                #                 parent.index(), parent.index(),
                #                 [Qt.CheckStateRole])
                #         else:
                #             break

        return super().setData(index, value, role)

    def insertRows(self, row, nodes, parent=QModelIndex()):
        parent_node = self.getNode(parent)

        self.beginInsertRows(parent, row, row + len(nodes) - 1)

        for child in reversed(nodes):
            # noinspection PyUnusedLocal
            success = parent_node.insert_child(row, child)

        self.endInsertRows()

        return True

    def removeLastRow(self, parent=QModelIndex()):
        parent_node = self.getNode(parent)

        # Account for index row count offset of 1
        last_index = len(parent_node.children()) - 2
        self.beginRemoveRows(parent, last_index, last_index)

        parent_node.remove_last_child()

        self.endRemoveRows()

        return True

    def removeRows(self, row, count, parent=QModelIndex()):
        parent_node = self.getNode(parent)

        self.beginRemoveRows(parent, row, row + count - 1)

        # noinspection PyUnusedLocal
        success = []
        for i in range(count):
            # Account for index row count offset of 1
            index = row + 1 + i
            success.append(parent_node.remove_child(index))

        self.endRemoveRows()

        return True

    def roleNames(self):
        return self._roles
