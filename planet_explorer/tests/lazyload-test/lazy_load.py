import sys
import os

# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    Qt,
    pyqtSlot,
    # QModelIndex,
    QPoint,
    QSize
)
# noinspection PyPackageRequirements
from PyQt5.QtGui import (
    QCursor
)

# noinspection PyPackageRequirements
from PyQt5.QtWidgets import (
    QApplication,
    QTreeView,
    QHeaderView,
    QMenu
)

script_path = os.path.split(__file__)[0]
sys.path.insert(0, script_path)

try:
    from .node import Node
    from .model import FileSystemTreeModel, ActionDelegate
except (ImportError, ModuleNotFoundError):
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from node import Node
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from model import FileSystemTreeModel, ActionDelegate

if __name__ == "__main__":
    app = QApplication(sys.argv)

    model = FileSystemTreeModel(Node('Filename'), path='/')

    tree = QTreeView()
    tree.setModel(model)
    tree.setIconSize(QSize(48, 48))

    tree.setHeaderHidden(False)
    # tree.setColumnWidth(0, 250)
    tree.setColumnWidth(1, 30)

    hv = tree.header()
    hv.setStretchLastSection(False)
    hv.setSectionResizeMode(0, QHeaderView.Stretch)
    hv.setSectionResizeMode(1, QHeaderView.Fixed)

    tree.setWordWrap(True)
    tree.setTextElideMode(Qt.ElideNone)
    act_delegate = ActionDelegate()
    tree.setItemDelegateForColumn(1, act_delegate)
    # tree.setFixedSize(700, 900)
    tree.setMinimumSize(700, 900)

    @pyqtSlot('QPoint')
    def open_menu(pos):
        """
        :type pos: QPoint
        :return:
        """
        index = tree.indexAt(pos)
        node = model.getNode(index)
        if node.is_fetch_more and node.parent() == model.root:
            return
        menu = QMenu()
        menu.addAction('Add preview')
        menu.addAction('Load footprints')

        menu.exec_(tree.viewport().mapToGlobal(pos))

    @pyqtSlot('QModelIndex')
    def item_clicked(index):
        if index.column() == 0:
            model.fetchMoreTopItems(index)
        elif index.column() == 1:
            open_menu(tree.viewport().mapFromGlobal(QCursor.pos()))

    tree.setContextMenuPolicy(Qt.CustomContextMenu)
    # noinspection PyUnresolvedReferences
    tree.customContextMenuRequested['QPoint'].connect(open_menu)

    # noinspection PyUnresolvedReferences
    tree.clicked['QModelIndex'].connect(item_clicked)

    tree.show()

    sys.exit(app.exec_())
