# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    QObject,
    Qt
)
# noinspection PyPackageRequirements
# from PyQt5.QtGui import QStandardItem


# noinspection DuplicatedCode
class Node(QObject):

    def __init__(self, name, path=None, parent=None):
        super().__init__()

        self._name = name
        self._children: [Node] = []
        self._parent = parent

        self.is_dir = False
        self._path = path
        self.is_traversed = False
        self.is_fetch_more = False
        self.checked_state = Qt.Unchecked

        if parent is not None:
            parent.add_child(self)

    def name(self):
        return self._name

    def path(self):
        return self._path

    def parent(self):
        return self._parent if self._parent else None

    def set_parent(self, node):
        self._parent = node

    def children(self):
        return self._children

    def has_children(self):
        return len(self._children) > 0

    def add_child(self, child):
        self._children.append(child)
        child.set_parent(self)

    def insert_child(self, position, child):
        if position < 0 or position > self.child_count():
            return False

        self._children.insert(position, child)
        child.set_parent(self)

        return True

    def remove_child(self, index):
        try:
            del self._children[index]
            return True
        except IndexError:
            return False

    def remove_children(self, position, count):
        index = position
        if (index < 0 or
                index >= self.child_count() or
                index + count > self.child_count()):
            return False

        try:
            # self._children[position - 1].deleteLater()
            del self._children[index:index + count]
        except IndexError:
            return False

        return True

    def last_child(self):
        if len(self._children) > 0:
            return self._children[-1]
        return None

    def remove_last_child(self):
        child = self.children().pop()
        del child

    def child(self, row):
        return self._children[row]

    def child_count(self):
        return len(self._children)

    def row(self):
        if self._parent is not None:
            return self._parent.children().index(self)
        return 0
