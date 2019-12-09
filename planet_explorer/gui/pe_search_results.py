# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_search_results.py
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
"""
__author__ = 'Planet Federal'
__date__ = 'August 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import json
import sys
import logging

# noinspection PyPackageRequirements
from typing import (
    Optional,
    Any,
    List,
    Set,
)

from qgiscommons2.settings import (
    pluginSetting,
)

# noinspection PyPackageRequirements
from qgis.PyQt import uic

# noinspection PyPackageRequirements
from qgis.PyQt.QtCore import (
    pyqtSignal,
    pyqtSlot,
    Qt,
    # QObject,
    QModelIndex,
    QAbstractItemModel,
    QItemSelectionModel,
    # QItemSelection,
    QRect,
    QSize,
    QMargins,
    QTextCodec,
    QEvent,
    QPoint,
)
# noinspection PyPackageRequirements
from qgis.PyQt.QtGui import (
    QIcon,
    QCursor,
    QColor,
    QPen,
    QBrush,
    QMouseEvent,
    QKeyEvent,
    QTextDocument,
    QAbstractTextDocumentLayout,
    QPalette,
)
# noinspection PyPackageRequirements
from qgis.PyQt.QtWidgets import (
    QApplication,
    QAction,
    QLabel,
    QFrame,
    QMenu,
    QToolButton,
    QPlainTextEdit,
    QAbstractItemView,
    QTreeView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
    # QTabWidget,
    QGroupBox,
)

from qgis.core import (
    QgsApplication,
    QgsGeometry,
    # QgsGeometryCollection,
    # QgsFeature,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsWkbTypes,
    QgsJsonUtils,
    QgsFields,
    QgsRectangle,
    # QgsLayerTreeNode,
)

from qgis.gui import (
    QgsCollapsibleGroupBox,
    QgsRubberBand,
)

from planet_explorer.pe_utils import(
    ITEM_BACKGROUND_COLOR
)

plugin_path = os.path.split(os.path.dirname(__file__))[0]

if __name__ == "__main__":
    print(plugin_path)
    sys.path.insert(0, plugin_path)
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from planet_explorer.resources import resources
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from pe_thumbnails import (
        PlanetQgisRenderJob,
    )
    # noinspection PyUnresolvedReferences
    from planet_explorer.pe_utils import (
        qgsgeometry_from_geojson,
        # qgsmultipolygon_from_geojsons,
        add_menu_section_action,
        remove_maplayers_by_name,
        zoom_canvas_to_aoi,
        preview_local_item_raster,
        # clear_local_item_raster_preview,
        create_preview_group,
        temp_preview_group,
        PE_PREVIEW,
        SETTINGS_NAMESPACE,
    )
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from gui.waiting_spinner.waitingspinnerwidget import QtWaitingSpinner
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from planet_api.p_client import (
        ITEM_GROUPS,
    )
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from planet_api.p_node import (
        PlanetNode,
        PlanetNodeType as NodeT,
    )
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from planet_api.p_models import (
        PlanetSearchResultsModel,
    )
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from planet_api.p_thumnails import (
        THUMB_EXT,
        THUMB_GEO,
    )
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from planet_api.p_utils import (
        geometry_from_request,
    )
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from planet_api.p_specs import (
        # RESOURCE_MOSAICS,
        RESOURCE_DAILY,
        # DAILY_ITEM_TYPES_DICT,
    )
else:
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from ..resources import resources
    from ..gui.waiting_spinner.waitingspinnerwidget import QtWaitingSpinner
    from .pe_thumbnails import (
        PlanetQgisRenderJob,
    )
    from ..pe_utils import (
        qgsgeometry_from_geojson,
        # qgsmultipolygon_from_geojsons,
        add_menu_section_action,
        remove_maplayers_by_name,
        zoom_canvas_to_aoi,
        preview_local_item_raster,
        # clear_local_item_raster_preview,
        create_preview_group,
        temp_preview_group,
        PE_PREVIEW,
        SETTINGS_NAMESPACE,
        SEARCH_AOI_COLOR,
        PLANET_COLOR
    )
    # noinspection PyUnresolvedReferences
    from ..planet_api.p_client import (
        ITEM_GROUPS,
    )
    from ..planet_api.p_node import (
        PlanetNode,
        PlanetNodeType as NodeT,
    )
    from ..planet_api.p_models import (
        PlanetSearchResultsModel,
    )
    from ..planet_api.p_thumnails import (
        THUMB_EXT,
        THUMB_GEO,
    )
    from ..planet_api.p_utils import (
        geometry_from_request,
    )
    from ..planet_api.p_specs import (
        # RESOURCE_MOSAICS,
        RESOURCE_DAILY,
        # DAILY_ITEM_TYPES_DICT,
    )

CHILD_COUNT_THRESHOLD_FOR_PREVIEW = 500

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

RESULTS_WIDGET, RESULTS_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_search_results_base.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)


COG_ICON = QIcon(':/plugins/planet_explorer/cog.svg')

LOCK_ICON = QIcon(':/plugins/planet_explorer/lock-light.svg')

RESPONSE_TIMEOUT = 60


class PlanetNodeItemDelegate(QStyledItemDelegate):

    previewFootprint = pyqtSignal('PyQt_PyObject')
    clearFootprint = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)

    # noinspection DuplicatedCode
    def paint(self, painter, option, index):
        if index.column() != 0:
            QStyledItemDelegate.paint(self, painter, option, index)
            return
        model: Any[PlanetSearchResultsModel | QAbstractItemModel] = \
            index.model()
        node: PlanetNode = model.get_node(index)

        # TODO: Style these, too?
        # if node.node_type() in [NodeT.LOADING, NodeT.LOAD_MORE]:
        #     QStyledItemDelegate.paint(self, painter, option, index)
        #     return

        option_vi = QStyleOptionViewItem(option)
        self.initStyleOption(option_vi, index)

        # noinspection PyUnusedLocal
        style = QApplication.style() \
            if option_vi.widget is None else option_vi.widget.style()
        # style = self.parent().style()

        opt_rect = option_vi.rect

        doc = QTextDocument()
        doc.setHtml(option_vi.text)
        #print(option_vi.text)

        option_vi.text = ''
        style.drawControl(QStyle.CE_ItemViewItem, option_vi, painter)

        ctx = QAbstractTextDocumentLayout.PaintContext()

        # Highlighting text if item is selected
        # if option_vi.state & QStyle.State_Selected:
        #     ctx.palette.setColor(
        #         QPalette.Text,
        #         option_vi.palette.color(
        #             QPalette.Active, QPalette.HighlightedText))

        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, option_vi)
        painter.save()

        painter.translate(text_rect.topLeft())
        painter.setClipRect(text_rect.translated(-text_rect.topLeft()))
        doc.documentLayout().draw(painter, ctx)

        painter.restore()

        if option.state & QStyle.State_MouseOver:
            if node.has_footprint() or node.has_group_footprint():
                painter.save()

                painter.setPen(
                    QPen(QBrush(QColor.fromRgb(0, 157, 165, 245)), 1.5))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(opt_rect.marginsRemoved(QMargins(1, 1, 1, 1)))

                painter.restore()

            if node.has_footprint() or node.has_group_footprint():
                # noinspection PyUnresolvedReferences
                self.previewFootprint.emit(node)
            else:
                # noinspection PyUnresolvedReferences
                self.clearFootprint.emit()

        if not node.can_be_downloaded():
            # Note: Needs to come last, so it covers checkbox control
            # TODO: Figure out way of having checkbox not drawn, but still
            #       set Node's unchecked state

            # opt_btn = QStyleOptionButton()
            # opt_btn.operator = option
            ci_rect: QRect = style.subElementRect(
                QStyle.SE_ViewItemCheckIndicator, option_vi)

            # opt_btn.rect = ci_rect
            # but_opt = QStyleOptionButton(option)
            # opt_btn.state = QStyle.State_Off
            # style.drawControl(QStyle.CE_CheckBox, opt_btn, painter)

            painter.save()

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor.fromRgb(250, 250, 250, 255)))
            painter.drawRoundedRect(ci_rect,
                                    ci_rect.height() / 6,
                                    ci_rect.height() / 6)

            LOCK_ICON.paint(painter, ci_rect, Qt.AlignCenter, QIcon.Normal)

            painter.restore()

    def sizeHint(self, option, index):
        # node: PlanetNode = index.model().get_node(index)
        option_vi = QStyleOptionViewItem(option)
        self.initStyleOption(option_vi, index)

        doc = QTextDocument()
        doc.setHtml(option_vi.text)
        doc.setTextWidth(option_vi.rect.width())
        return QSize(int(doc.idealWidth()), int(doc.size().height()))


class PlanetNodeActionDelegate(QStyledItemDelegate):

    def __init__(self, parent=None):
        super().__init__(parent)

    # noinspection DuplicatedCode
    def paint(self, painter, option, index):
        if index.column() != 1:
            QStyledItemDelegate.paint(self, painter, option, index)
            return
        model: Any[PlanetSearchResultsModel | QAbstractItemModel] = \
            index.model()
        node = model.get_node(index)
        if node.node_type() in [NodeT.LOADING, NodeT.LOAD_MORE]:
            QStyledItemDelegate.paint(self, painter, option, index)
            return
        rect = option.rect

        painter.save()

        btn = QStyleOptionButton()
        btn.icon = COG_ICON
        btn.iconSize = QSize(18, 18)
        btn.features = QStyleOptionButton.Flat
        # btn.features |= QStyleOptionButton.HasMenu

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        btn.state = QStyle.State_Enabled

        btn.rect = QRect(rect.left() + rect.width() - 26,
                         rect.top(), 26, rect.height())

        QApplication.style().drawControl(
            QStyle.CE_PushButton, btn, painter)

        painter.restore()

    # def editorEvent(self,
    #                 event: QEvent,
    #                 model: QAbstractItemModel,
    #                 option: 'QStyleOptionViewItem',
    #                 index: QModelIndex) -> bool:
    #     if (event.type() in
    #             [QEvent.MouseButtonPress, QEvent.MouseButtonRelease]):
    #         event: QMouseEvent
    #         if event.button() == Qt.LeftButton:
    #             log.debug('Swapping left button for right')
    #             event = QMouseEvent(
    #                 event.type(),
    #                 event.localPos(), event.windowPos(), event.screenPos(),
    #                 Qt.RightButton, Qt.RightButton, Qt.NoModifier)
    #     return QStyledItemDelegate.editorEvent(
    #         self, event, model, option, index)


class PlanetSearchResultsView(QTreeView):
    """
    """

    checkedCountChanged = pyqtSignal(int)

    def __init__(self, parent, iface=None, api_key=None,
                 request_type=None, request=None,
                 response_timeout=RESPONSE_TIMEOUT,
                 sort_order=None):
        super().__init__(parent=parent)

        # noinspection PyTypeChecker
        self._parent: PlanetSearchResultsWidget = parent

        self._iface = iface
        self._api_key = api_key
        self._request_type = request_type
        self._request = request
        self._response_timeout = response_timeout
        self._sort_order = sort_order

        self._footprint = None
        self._setup_footprint()

        self._thumb_cache_dir: str = pluginSetting(
            'thumbCachePath', namespace=SETTINGS_NAMESPACE)

        self._checked_count = 0
        self._checked_queue = {}

        self._search_model = PlanetSearchResultsModel(
            parent=self,
            api_key=api_key,
            request_type=request_type,
            request=request,
            thumb_cache_dir=self._thumb_cache_dir,
            sort_order=self._sort_order
        )

        # Generic model, as background, until results come in
        # self._search_model = QStandardItemModel(0, 2, self)

        self._search_model.thumbnail_cache().set_job_subclass(
            PlanetQgisRenderJob
        )

        p = self.palette()
        p.setColor(QPalette.Highlight, ITEM_BACKGROUND_COLOR)
        self.setPalette(p)

        self.setModel(self._search_model)

        self.setIconSize(QSize(48, 48))
        self.setAlternatingRowColors(True)
        self.setHeaderHidden(False)

        # self.setColumnWidth(0, 250)
        self.setColumnWidth(1, 26)

        self.setIndentation(int(self.indentation() * 0.75))

        hv = self.header()
        hv.setStretchLastSection(False)
        hv.setSectionResizeMode(0, QHeaderView.Stretch)
        hv.setSectionResizeMode(1, QHeaderView.Fixed)
        if len(sort_order) > 1:
            if sort_order[1] == 'asc':
                sort_indicator = Qt.AscendingOrder
            else:
                sort_indicator = Qt.DescendingOrder
            hv.setSortIndicator(0, sort_indicator)
            hv.setSortIndicatorShown(True)

        self.viewport().setAttribute(Qt.WA_Hover)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

        # self.setWordWrap(True)
        # self.setTextElideMode(Qt.ElideNone)
        self.item_delegate = PlanetNodeItemDelegate(parent=self)
        # noinspection PyUnresolvedReferences
        self.item_delegate.previewFootprint['PyQt_PyObject'].connect(
            self.preview_footprint)
        # noinspection PyUnresolvedReferences
        self.item_delegate.clearFootprint.connect(self.clear_footprint)
        self.setItemDelegateForColumn(0, self.item_delegate)
        self.act_delegate = PlanetNodeActionDelegate(parent=self)
        self.setItemDelegateForColumn(1, self.act_delegate)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        # noinspection PyUnresolvedReferences
        self.customContextMenuRequested['QPoint'].connect(self.open_menu)

        # noinspection PyUnresolvedReferences
        self.clicked['QModelIndex'].connect(self.item_clicked)

        # noinspection PyUnresolvedReferences
        self.expanded['QModelIndex'].connect(self.item_expanded)

    def search_model(self):
        return self._search_model

    def checked_count(self):
        return self._checked_count

    def checked_queue(self):
        return self._checked_queue

    def _setup_footprint(self):
        if self._iface:
            log.debug('iface is available, adding footprint support')
            self._footprint = QgsRubberBand(
                self._iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
            self._footprint.setFillColor(QColor(255, 255, 255, 10))
            self._footprint.setStrokeColor(PLANET_COLOR)
            self._footprint.setWidth(2)
        else:
            log.debug('iface is None, skipping footprint support')
            self._footprint = None

    # noinspection PyMethodMayBeStatic
    def qgsfeature_feature_from_node(self, node: PlanetNode):

        # TODO: Resolve geometry by node_type or do that under node.geometry()?
        # geom = None
        # if node.node_type() == NodeT.DAILY_SCENE_IMAGE:
        #     geom = node.geometry()

        # TODO: Add node
        # feature_collect = {
        #     'type': 'FeatureCollection',
        #     'features': [
        #         {
        #             'type': 'Feature',
        #             'geometry': node.geometry(),
        #             'properties': {
        #                 'id': node.item_id()
        #             }
        #         }
        #     ]
        # }

        feature_collect = {
            'type': 'FeatureCollection',
            'features': [
                node.resource()
            ]
        }

        feature_collect_json = json.dumps(feature_collect)

        # noinspection PyUnusedLocal
        features = []
        # noinspection PyBroadException
        try:
            utf8 = QTextCodec.codecForName('UTF-8')
            # TODO: Add node id, properties as fields?
            fields = QgsFields()
            features = QgsJsonUtils().stringToFeatureList(
                string=feature_collect_json, fields=fields, encoding=utf8)
        except Exception:
            log.debug('Footprint GeoJSON could not be parsed')
            return

        if not len(features) > 0:
            log.debug('GeoJSON parsing created no features')
            return

        return features[0]

    @pyqtSlot()
    def clear_footprint(self):
        if self._footprint:
            self._footprint.reset(QgsWkbTypes.PolygonGeometry)

    @pyqtSlot('PyQt_PyObject')
    def preview_footprint(self, node: PlanetNode):
        if not self._footprint:
            if LOG_VERBOSE:
                log.debug('Footprint is None, skipping footprint preview')
            return

        if node.has_group_footprint():
            geoms = node.geometries()
        else:
            geoms = [node.geometry()]

        self.clear_footprint()

        qgs_geoms = [qgsgeometry_from_geojson(g) for g in geoms]

        for qgs_geom in qgs_geoms:
            self._footprint.addGeometry(
                qgs_geom,
                QgsCoordinateReferenceSystem("EPSG:4326")
            )

        if LOG_VERBOSE:
            log.debug('Footprint sent to canvas')

    @pyqtSlot(list)
    def zoom_to_footprint(self, nodes: [PlanetNode]):
        skip = 'skipping zoom to footprint'
        if not self._footprint:
            log.debug(f'Footprint is None, {skip}')
            return

        if len(nodes) < 1:
            log.debug('No nodes available, skipping zoom to footprint')
            return

        first_node = nodes[0]
        if first_node.has_group_footprint():
            json_geoms = first_node.geometries()
        else:
            json_geoms = [node.geometry() for node in nodes]

        qgs_geoms: [QgsGeometry] = \
            [qgsgeometry_from_geojson(j) for j in json_geoms]

        if len(qgs_geoms) < 1:
            log.debug(f'Geometry collection empty, {skip}')
            return

        rect_geoms: QgsRectangle = qgs_geoms[0].boundingBox()
        for i in range(len(qgs_geoms)):
            if i == 0:
                continue
            r: QgsRectangle = qgs_geoms[i].boundingBox()
            rect_geoms.combineExtentWith(r)

        if rect_geoms.isNull():
            log.debug(f'Footprint geometry is null, {skip}')
            return

        # noinspection PyArgumentList
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().crs(),
            QgsProject.instance()
        )
        rect_footprint: QgsRectangle = \
            transform.transformBoundingBox(rect_geoms)

        if not rect_footprint.isEmpty():
            rect_footprint.scale(1.05)
            self._iface.mapCanvas().setExtent(rect_footprint)
            self._iface.mapCanvas().refresh()

    @pyqtSlot('PyQt_PyObject')
    def preview_thumbnail(
            self, node, name=PE_PREVIEW, remove_existing=True):
        item_name_geo = f'{node.item_type_id_key()}{THUMB_GEO}'
        item_geo_path = os.path.join(
            self.search_model().thumbnail_cache().cache_dir(),
            f'{item_name_geo}{THUMB_EXT}')
        if not preview_local_item_raster(
                item_geo_path, name, remove_existing=remove_existing):
            log.warning(f'Item preview {item_name_geo} failed to load')

    @pyqtSlot(dict)
    def update_preview_thumbnails(self, selected_nodes):
        group = temp_preview_group()

        tree_node_names: List[str] = \
            [t_node.name() for t_node in group.children()]
        for name in tree_node_names:
            if name.endswith('_thumb'):
                name_sans = name.replace('_thumb', '')
                if name_sans not in selected_nodes:
                    remove_maplayers_by_name(name, only_first=True)
                if name_sans in selected_nodes:
                    # Keep already loaded layer, skip reloading it
                    selected_nodes[name_sans] = None

        for _, node in selected_nodes.items():
            if node is not None:
                self.preview_thumbnail(node)

        # for node in deselected_nodes:
        #     if f'{node.item_type_id_key()}_thumb'.lower() in node_names:
        #         remove_maplayers_by_name(
        #             f'{node.item_type_id_key()}_thumb'.lower(),
        #             only_first=True)
        #
        # node_names = [t_node.name() for t_node in group.children()]
        # for node in selected_nodes:
        #     if f'{node.item_type_id_key()}_thumb'.lower() not in node_names:
        #         self.preview_thumbnail(node)

    @pyqtSlot(list)
    def add_preview_groups(self, nodes: List[PlanetNode]):
        if len(nodes) < 1 or not isinstance(nodes[0], PlanetNode):
            log.debug('No nodes found to add to preview group')
            return

        if nodes[0].is_group_node():
            log.debug('Adding preview group for group')
            # Grouping tree items are only singularly passed
            self.add_preview_group_for_group(nodes[0])
        else:
            log.debug('Adding preview group for items')
            self.add_preview_groups_for_items(nodes)

    @pyqtSlot(list)
    def add_preview_group_for_group(self, node: PlanetNode):
        name = None
        child_node_type = None
        if node.node_type() == NodeT.DAILY_SCENE:
            child_node_type = NodeT.DAILY_SCENE_IMAGE
            item_type = node.name() or ''
            title = ['Daily', item_type, 'Scene']
            name = f'{" ".join(title)} ' \
                   f'{node.formatted_date_time(node.sort_date())}'
        elif node.node_type() == NodeT.DAILY_SAT_GROUP:
            child_node_type = NodeT.DAILY_SCENE_IMAGE
            item_type = node.parent().name() or ''
            title = ['Daily', item_type, f'Satellite {node.name()} Group']
            name = f'{" ".join(title)} ' \
                   f'{node.formatted_date_time(node.sort_date())}'

        if child_node_type is None:
            log.debug('No node type found for tree group searching')
            return

        item_nodes = node.children_of_node_type(child_node_type)
        if item_nodes:
            create_preview_group(
                name, item_nodes,
                self._search_model.p_client().api_key(),
                tile_service='xyz',
                search_query=self._request,
                sort_order=self._sort_order
            )
        else:
            log.debug(f"No items found for node type '{child_node_type.name}' "
                      f"in tree group '{name}'")

    @pyqtSlot(list)
    def add_preview_groups_for_items(self, nodes: List[PlanetNode]) -> None:
        prev_types = []  # maintain some sort order
        prev_type_nodes = {}
        for node in nodes:
            item_type = node.item_type()
            if item_type not in prev_types:
                prev_types.append(item_type)
                prev_type_nodes[item_type] = []
            prev_type_nodes[item_type].append(node)

        for prev_type in sorted(prev_types):
            prev_nodes: List[PlanetNode] = prev_type_nodes[prev_type]
            # if prev_type in DAILY_ITEM_TYPES_DICT:
            #     # Group imagery by type
            #     item_keys = [n.item_type_id() for n in prev_nodes]
            #     tile_url = self._search_model.p_client().get_tile_url(
            #         item_keys)
            #     create_preview_group(prev_type, prev_nodes, tile_url)
            # else:
            #     # For groups, use any item type listing
            #     for prev_node in prev_nodes:
            #         item_keys = prev_node.item_type_id_list()
            #         if item_keys:
            #             tile_url = \
            #                 self._search_model.p_client().get_tile_url(
            #                     item_keys)
            #             create_preview_group(prev_type, [], tile_url)

            create_preview_group(
                prev_type, prev_nodes,
                self._search_model.p_client().api_key(),
                tile_service='xyz',
                search_query=self._request,
                sort_order=self._sort_order
            )

    @pyqtSlot(list)
    def copy_ids_to_clipboard(self, nodes):
        node_ids = [n.item_type_id() for n in nodes if n.item_id()]
        if node_ids:
            cb = QgsApplication.clipboard()
            cb.setText(','.join(node_ids))

    @pyqtSlot('QPoint')
    def open_menu(self, pos):
        """
        :type pos: QPoint
        :return:
        """
        index = self.indexAt(pos)
        node: PlanetNode = self.model().get_node(index)
        if (node.node_type() == NodeT.LOAD_MORE
                and node.parent() == self.model().root):
            return
        menu = QMenu()

        # Single, current Item's index
        add_menu_section_action('Current item', menu)

        if node.has_footprint() or node.has_group_footprint():
            zoom_fp_act = QAction('Zoom to footprint', menu)
            # noinspection PyUnresolvedReferences
            zoom_fp_act.triggered[bool].connect(
                lambda: self.zoom_to_footprint([node]))
            menu.addAction(zoom_fp_act)

        if node.can_load_preview_layer():
            prev_layer_act = QAction('Add preview layer to map', menu)
            # noinspection PyUnresolvedReferences
            prev_layer_act.triggered[bool].connect(
                lambda: self.add_preview_groups([node]))
            if node.child_images_count() > CHILD_COUNT_THRESHOLD_FOR_PREVIEW:
                prev_layer_act.setEnabled(False)
                prev_layer_act.setToolTip("The node contains too many images to preview")
                menu.setToolTipsVisible(True)

            menu.addAction(prev_layer_act)

        if node.item_id() and node.has_resource():
            copy_id_act = QAction('Copy ID to clipboard', menu)
            # noinspection PyUnresolvedReferences
            copy_id_act.triggered[bool].connect(
                lambda: self.copy_ids_to_clipboard([node]))
            menu.addAction(copy_id_act)

        # Selected Items
        sel_model = self.selectionModel()
        model = self.model()
        # Ensure to grab only first column of indexes (or will get duplicates)
        all_nodes = [model.get_node(i) for i in sel_model.selectedIndexes()
                     if i.column() == 0]
        log.debug(f'Selected items: {len(all_nodes)}')

        if len(all_nodes) == 1 and all_nodes[0] == node:
            menu.exec_(self.viewport().mapToGlobal(pos))
            return

        nodes_have_footprints = \
            [node for node in all_nodes if node.has_footprint()]
        nodes_w_ids = \
            [node for node in all_nodes
             if node.item_id() and node.has_resource()]
        nodes_can_prev = \
            [node for node in all_nodes
             if node.can_load_preview_layer() and node.has_resource()]

        if any([nodes_have_footprints, nodes_w_ids, nodes_can_prev]):
            add_menu_section_action(f'Selected images', menu)

        if nodes_have_footprints:
            zoom_fps_act = QAction(
                f'Zoom to total footprint '
                f'({len(nodes_have_footprints)} items)', menu)
            # noinspection PyUnresolvedReferences
            zoom_fps_act.triggered[bool].connect(
                lambda: self.zoom_to_footprint(nodes_have_footprints))
            menu.addAction(zoom_fps_act)

        if nodes_can_prev:
            prev_layers_act = QAction(
                f'Add preview layer to map '
                f'({len(nodes_can_prev)} items)', menu)
            # noinspection PyUnresolvedReferences
            prev_layers_act.triggered[bool].connect(
                lambda: self.add_preview_groups(nodes_can_prev))
            menu.addAction(prev_layers_act)

        if nodes_w_ids:
            copy_ids_act = QAction(
                f'Copy IDs to clipboard ({len(nodes_w_ids)} items)', menu)
            # noinspection PyUnresolvedReferences
            copy_ids_act.triggered[bool].connect(
                lambda: self.copy_ids_to_clipboard(nodes_w_ids))
            menu.addAction(copy_ids_act)

        menu.exec_(self.viewport().mapToGlobal(pos))

    @pyqtSlot('QModelIndex')
    def item_clicked(self, index):
        node: PlanetNode = self.model().get_node(index)
        log.debug(f'Index clicked: row {index.row()}, col {index.column()}, '
                  f'{node.item_type_id()}')
        if index.column() == 0:
            if (node.node_type() == NodeT.LOAD_MORE
                    and node.parent() == self.model().root):
                self.model().fetch_more_top_items(index)
        elif index.column() == 1:
            self.open_menu(self.viewport().mapFromGlobal(QCursor.pos()))

    @pyqtSlot('QModelIndex')
    def item_expanded(self, index: QModelIndex):
        node: PlanetNode = self.model().get_node(index)
        log.debug(f'Index expanded: row {index.row()}, col {index.column()}, '
                  f'{node.item_type_id()}')
        # log.debug(
        #     f'Node traversed: {node.is_traversed()} {node.item_type_id()}')
        # if index.column() == 0:
        #     if (node.node_type() == NodeT.DAILY_SCENE
        #             and not node.is_traversed()):
        #         log.debug(
        #             f'Traversing node: {node.item_type_id()}')
        #         for sat_grp in node.children():
        #             sat_grp: PlanetNode
        #             self.expand(sat_grp.index())
        #
        #             for image in sat_grp.children():
        #                 if image.has_thumbnail():
        #                     self.search_model().add_to_thumb_queue(
        #                         image.item_type_id_key(), image.index())
        #                     self.search_model().fetch_thumbnail(image)
        #
        #         node.set_is_traversed(True)

    def _update_checked_queue(self,
                              checked_nodes: Set[PlanetNode],
                              unchecked_nodes: Set[PlanetNode]):
        for c_node in checked_nodes:
            it_id = c_node.item_type_id()
            self._checked_queue[it_id] = c_node

        for u_node in unchecked_nodes:
            it_id = u_node.item_type_id()
            if it_id in self._checked_queue:
                del self._checked_queue[it_id]

        self._checked_count = len(self._checked_queue)
        log.debug(f'checked_count: {self._checked_count}')

        if LOG_VERBOSE:
            sorted_item_ids = sorted(self._checked_queue.keys())
            nl = '\n'
            log.debug(f'checked_queue:\n'
                      f'  {"{0}  ".format(nl).join(sorted_item_ids)}')

            # When using with {'item_type': set(nodes)}
            # for it_id in self._checked_queue:
            #     log.debug(f'\n  - {it_id}: '
            #               f'{len(self._checked_queue[it_id])}\n')
            #
            #     # Super verbose output...
            #     nl = '\n'
            #     i_types = \
            #         [n.item_id() for n in self._checked_queue[it_id]]
            #     log.debug(f'\n  - {it_id}: '
            #               f'{len(self._checked_queue[it_id])}\n'
            #               f'    - {"{0}    - ".format(nl).join(i_types)}')

        self.checkedCountChanged.emit(self._checked_count)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Leave:
            if self._iface:
                self.clear_footprint()
                event.accept()

        return QTreeView.event(self, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.pos())
        sel_model: QItemSelectionModel = self.selectionModel()
        if (index.column() == 1
                and event.button() == Qt.LeftButton
                and sel_model.isSelected(index)):
            log.debug('Ignoring mouse press')
            return

        return QTreeView.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.pos())
        sel_model: QItemSelectionModel = self.selectionModel()
        if (index.column() == 1
                and event.button() == Qt.LeftButton
                and sel_model.isSelected(index)):
            log.debug('Swapping left button for right, on release')
            self.open_menu(event.pos())
            return

        return QTreeView.mouseReleaseEvent(self, event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        index = self.currentIndex()
        if (index.column() == 0
                and event.key() in [Qt.Key_Enter, Qt.Key_Return]):
            node: PlanetNode = self.model().get_node(index)
            if (node.node_type() == NodeT.LOAD_MORE
                    and node.parent() == self.model().root):
                self.model().fetch_more_top_items(index)

        return QTreeView.keyReleaseEvent(self, event)

    def dataChanged(self, t_l: QModelIndex, b_r: QModelIndex,
                    roles: Optional[List[int]] = None) -> None:

        # This may need to go at end of slot
        super().dataChanged(t_l, b_r, roles=roles)

        # Note: empty roles indicates *everything* has changed, not nothing
        if roles is not None and (roles == [] or Qt.CheckStateRole in roles):
            if LOG_VERBOSE:
                log.debug('Node (un)checked')
            checked = set()
            unchecked = set()

            def update_queues(indx):
                node: PlanetNode = self._search_model.get_node(indx)
                if node.is_base_image() and node.can_be_downloaded():
                    if node.checked_state() == Qt.Checked:
                        checked.add(node)
                    elif node.checked_state() == Qt.Unchecked:
                        unchecked.add(node)

            # Note: if parent of t_l and b_r differ, we ignore undefined input
            if t_l == b_r:
                if LOG_VERBOSE:
                    log.debug('Nodes (un)checked is single')
                update_queues(t_l)
            elif t_l.parent() == b_r.parent():
                if LOG_VERBOSE:
                    log.debug('Nodes (un)checked have same parent')
                parent = t_l.parent()
                col = t_l.column()
                for row in range(b_r.row(), t_l.row() + 1):
                    m_indx = self._search_model.index(row, col, parent=parent)
                    update_queues(m_indx)

            if checked or unchecked:
                if LOG_VERBOSE:
                    log.debug(f'Nodes checked: {checked}')
                    log.debug(f'Nodes unchecked: {unchecked}')
                self._update_checked_queue(checked, unchecked)

    # This works, but is disabled until thumbnail georeferencing works OK
    # def currentChanged(self, current: QModelIndex,
    #                    previous: QModelIndex) -> None:
    #     node: PlanetNode = self.model().get_node(current)
    #     log.debug(f'Current item: row {current.row()}, '
    #               f'col {current.column()},'
    #               f' {node.item_id()}')
    #     if current.column() == 0:
    #         if node.has_thumbnail() and node.thumbnail_loaded():
    #             self.preview_thumbnail(node)
    #         else:
    #             clear_local_item_raster_preview()
    #
    #     return QTreeView.currentChanged(self, current, previous)

    # def selectionChanged(self, selected: QItemSelection,
    #                      deselected: QItemSelection) -> None:
    #     selected_nodes = {}
    #     for si in selected.indexes():
    #         if si.column() == 0:
    #             si_node = self._search_model.get_node(si)
    #             selected_nodes[si_node.item_type_id_key()] = si_node
    #
    #     deselected_nodes = {}
    #     for di in deselected.indexes():
    #         if di.column() == 0:
    #             di_node = self._search_model.get_node(di)
    #             deselected_nodes[di_node.item_type_id_key()] = di_node
    #
    #     self.update_preview_thumbnails(selected_nodes)
    #
    #     return QTreeView.selectionChanged(self, selected, deselected)

    @pyqtSlot()
    def clean_up(self):
        self.clear_footprint()

        # TODO: Clean up model?


class PlanetSearchResultsWidget(RESULTS_BASE, RESULTS_WIDGET):
    """
    """

    zoomToAOIRequested = pyqtSignal()
    setAOIRequested = pyqtSignal(dict)
    setSearchParamsRequested = pyqtSignal(dict, tuple)
    checkedCountChanged = pyqtSignal(int)

    grpBoxQuery: QGroupBox
    teQuery: QPlainTextEdit
    frameSearching: QFrame
    btnCancel: QToolButton
    btnShowQuery: QToolButton
    btnZoomToAOI: QToolButton
    btnSetAOI: QToolButton
    btnSetSearchParams: QToolButton
    lblSearching: QLabel
    frameResults: QFrame

    def __init__(self, parent=None, iface=None, api_key=None,
                 request_type=None, request=None,
                 response_timeout=RESPONSE_TIMEOUT,
                 sort_order=None):
        super().__init__(parent=parent)

        self.setupUi(self)

        self._parent = parent

        self._iface = iface
        # TODO: Grab responseTimeOut from plugin settings and override default
        self._response_timeout = response_timeout
        self._request_type = request_type
        self._request = request
        self.sort_order = sort_order

        self.teQuery.setPlainText(json.dumps(request, indent=2))

        # self.grpBoxQuery.setSaveCollapsedState(False)
        # self.grpBoxQuery.setCollapsed(True)
        self.grpBoxQuery.hide()

        self.btnZoomToAOI.clicked.connect(self._zoom_to_request_aoi)
        self.btnSetAOI.clicked.connect(self._set_aoi_from_request)
        self.btnSetSearchParams.clicked.connect(self._set_search_params_from_request)
        self.btnShowQuery.clicked.connect(self._toggle_query)

        self._aoi_box = None
        self._setup_request_aoi_box()

        self.results_tree = PlanetSearchResultsView(
            parent=self, iface=iface, api_key=api_key,
            request_type=request_type, request=request,
            response_timeout=self._response_timeout,
            sort_order=sort_order
        )

        self.results_tree.checkedCountChanged[int].connect(
            self.checked_count_changed)

        self.frameResults.layout().addWidget(self.results_tree)
        self.results_tree.setHidden(True)

        search_model = self.results_tree.search_model()
        if self.results_tree.search_model():
            search_model.searchFinished.connect(self._search_finished)
            search_model.searchNoResults.connect(self._search_no_results)
            search_model.searchCancelled.connect(self._search_cancelled)
            search_model.searchTimedOut[int].connect(self._search_timed_out)

            self.btnCancel.clicked.connect(search_model.cancel_search)

        self.waiting_spinner = QtWaitingSpinner(
            self.frameResults,
            centerOnParent=True,
            disableParentWhenSpinning=False,
            modality=Qt.NonModal
        )

        self.waiting_spinner.setRoundness(80.0)
        self.waiting_spinner.setMinimumTrailOpacity(15.0)
        self.waiting_spinner.setTrailFadePercentage(75.0)
        self.waiting_spinner.setNumberOfLines(15)
        self.waiting_spinner.setLineLength(14.0)
        self.waiting_spinner.setLineWidth(3.0)
        self.waiting_spinner.setInnerRadius(8.0)
        self.waiting_spinner.setRevolutionsPerSecond(1.0)
        self.waiting_spinner.setColor(PLANET_COLOR)

        self.waiting_spinner.start()
        self.waiting_spinner.show()

        search_model.start_api_search()
        # QTimer.singleShot(0, search_model.start_api_search)

    def _nix_waiting_spinner(self):
        self.waiting_spinner.stop()
        self.waiting_spinner.hide()

    def checked_count(self):
        return self.results_tree.checked_count()

    def checked_queue(self):
        return self.results_tree.checked_queue()

    @pyqtSlot(int)
    def checked_count_changed(self, count):
        if type(self._parent).__name__ == 'QTabWidget':
            # self._parent: QTabWidget
            tab_indx = self._parent.indexOf(self)

            if tab_indx != -1:
                txt = f'{self._request_type.capitalize()}'
                if count > 0:
                    txt += f' ({count})'
                self._parent.setTabText(tab_indx, txt)

        self.checkedCountChanged.emit(count)

    @pyqtSlot()
    def _toggle_query(self):
        if self.grpBoxQuery.isVisible():
            self.grpBoxQuery.hide()
            self.btnShowQuery.setIcon(
                QIcon(':/plugins/planet_explorer/expand-triangle.svg')
            )
        else:
            self.grpBoxQuery.show()
            self.btnShowQuery.setIcon(
                QIcon(':/plugins/planet_explorer/collapse-triangle.svg')
            )

    @pyqtSlot()
    def _search_finished(self):
        self._nix_waiting_spinner()
        self.frameSearching.hide()
        self.results_tree.show()

    @pyqtSlot()
    def _search_no_results(self):
        self._nix_waiting_spinner()
        self.lblSearching.setText('No results found')
        self.btnCancel.hide()
        self.results_tree.hide()

    @pyqtSlot()
    def _search_cancelled(self):
        self._nix_waiting_spinner()
        self.lblSearching.setText('Search cancelled')
        self.btnCancel.hide()
        self.results_tree.hide()

    @pyqtSlot(int)
    def _search_timed_out(self, timeout):
        self._nix_waiting_spinner()
        self.lblSearching.setText(f'Search timed out ({timeout} seconds)')
        self.btnCancel.hide()
        self.results_tree.hide()

    def _setup_request_aoi_box(self):
        if self._iface:
            log.debug('iface is available, adding aoi box support')
            self._aoi_box = QgsRubberBand(
                self._iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
            self._aoi_box.setFillColor(QColor(0, 0, 0, 0))
            self._aoi_box.setStrokeColor(SEARCH_AOI_COLOR)
            self._aoi_box.setWidth(2)
            self._aoi_box.setLineStyle(Qt.DashLine)
        else:
            log.debug('iface is None, skipping footprint support')
            self._aoi_box = None

    @pyqtSlot()
    def clear_aoi_box(self):
        if self._aoi_box:
            self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)

    @pyqtSlot()
    def _zoom_to_request_aoi(self):
        if not self._iface:
            log.debug('No iface object, skipping AOI extent')
            return

        aoi_geom = None
        if self._request_type == RESOURCE_DAILY:
            aoi_geom = geometry_from_request(self._request)

        if not aoi_geom:
            log.debug('No AOI geometry defined, skipping zoom to AOI')
            return

        qgs_geom: QgsGeometry = qgsgeometry_from_geojson(aoi_geom)
        self._aoi_box.setToGeometry(
            qgs_geom,
            QgsCoordinateReferenceSystem("EPSG:4326")
        )        

        self.show_aoi()

        zoom_canvas_to_aoi(aoi_geom, iface_obj=self._iface)

        self.zoomToAOIRequested.emit()

    def hide_aoi_if_matches_geom(self,geom):       
        if self._aoi_box is not None:
            color = (QColor(0, 0, 0, 0) if self._aoi_box.asGeometry().equals(geom) 
                    else SEARCH_AOI_COLOR)
            self._aoi_box.setStrokeColor(color)

    def show_aoi(self):
        if self._aoi_box is not None:
            self._aoi_box.setStrokeColor(SEARCH_AOI_COLOR)

    def aoi_geom(self):
        if self._aoi_box is not None:
            return self._aoi_box.asGeometry()

    @pyqtSlot()
    def _set_aoi_from_request(self):
        self.setAOIRequested.emit(self._request)

    @pyqtSlot()
    def _set_search_params_from_request(self):
        self.setSearchParamsRequested.emit(self._request, self.sort_order)

    @pyqtSlot()
    def clean_up(self):
        self.results_tree.clean_up()
        self.clear_aoi_box()

    # noinspection PyPep8Naming
    def closeEvent(self, event):
        self.clean_up()
        super().closeEvent(self, event)

    def request_query(self):
        return self._request


if __name__ == "__main__":
    from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout
    from qgiscommons2.settings import (
        readSettings,
    )

    sys.path.insert(0, plugin_path)

    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from planet_explorer.gui.resources import qgis_resources

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

    search_request = json.loads('''{"item_types": 
    ["PSScene4Band", "PSScene3Band"], 
    "filter": {"type": "AndFilter", "config": [{"field_name": "geometry", 
    "type": "GeometryFilter", "config": {"type": "Polygon", "coordinates": [
    [[-124.60010884388858, 36.207866384307614], [-119.61878664869495, 
    36.207866384307614], [-119.61878664869495, 39.705780131667844], 
    [-124.60010884388858, 39.705780131667844], [-124.60010884388858, 
    36.207866384307614]]]}}, {"field_name": "cloud_cover", "type": 
    "RangeFilter", "config": {"gte": 0, "lte": 100}}]}}''')

    readSettings(settings_path=os.path.join(plugin_path, 'settings.json'))
    SETTINGS_NAMESPACE = None

    # tree = PlanetSearchResultsView(
    #     parent=None, iface=None, api_key=apikey,
    #     request_type=RESOURCE_DAILY, request=search_request)
    # tree.show()

    wdgt = PlanetSearchResultsWidget(
        parent=None, iface=None, api_key=apikey,
        request_type=RESOURCE_DAILY, request=search_request,
        sort_order=('acquired', 'desc'))

    # wrap in dialog
    dlg = QDialog()
    layout = QVBoxLayout(dlg)
    image_lbl = QLabel(dlg)
    layout.addWidget(wdgt)
    # layout.setMargin(0)

    dlg.setMinimumHeight(700)

    dlg.exec_()

    qgs.exitQgis()

    sys.exit(0)
