# -*- coding: utf-8 -*-
"""
***************************************************************************
    p_node.py
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
import enum
import logging
import locale
from datetime import (
    date,
    datetime,
    time,
)
from uuid import uuid4
from typing import (
    Optional,
    Union,
    # List,
)
import iso8601

# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    Qt,
    QObject,
    pyqtSignal,
    QModelIndex,
)

# noinspection PyPackageRequirements
from PyQt5.QtGui import (
    QIcon,
    QPixmap
)

# from .p_client import (
#     PlanetClient,
# )
from .p_specs import (
    RESOURCE_DAILY,
    DAILY_ITEM_TYPES,
    DAILY_ITEM_TYPES_DICT,
    MOSAIC_ITEM_TYPES,
    # MOSAIC_ITEM_TYPES_DICT,
    MOSAIC_PRODUCT_TYPES,
    # MOSAIC_SERIES_PRODUCT_TYPES,
    ITEM_ASSET_DL_REGEX,
)

from planet.api import models

try:
    # noinspection PyUnresolvedReferences
    from ..resources import resources
except ValueError:
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from planet_explorer.resources import resources

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

DAILY_NODE_ITEM_TYPES = [a for a, b in DAILY_ITEM_TYPES]
MOSAIC_NODE_ITEM_TYPES = [a for a, b in MOSAIC_ITEM_TYPES]

SUBTEXT_STYLE = 'color: rgb(100,100,100);'
SUBTEXT_STYLE_WITH_NEW_CHILDREN = 'color: rgb(157,0,165);'
PE_STYLE = 'color: rgb(0,157,165);'
LRG_TEXT_STYLE = 'font-size: 150%;'
TIME_FORMAT = '%H:%M:%S'
DATE_FORMAT = '%b %d, %Y'

PLACEHOLDER_THUMB = ':/plugins/planet_explorer/thumb-placeholder-128.svg'


class PlanetNodeException(Exception):
    """Exceptions raised during population of nodes"""
    pass


class PlanetNodeType(enum.Enum):
    UNDEFINED = enum.auto()
    ROOT = enum.auto()
    LOADING = enum.auto()
    LOAD_MORE = enum.auto()
    DAILY_SCENE = enum.auto()
    DAILY_SAT_GROUP = enum.auto()
    DAILY_SCENE_IMAGE = enum.auto()
    MOSAIC = enum.auto()
    MOSAIC_SERIES = enum.auto()
    MOSAIC_QUAD = enum.auto()


class PlanetNode(QObject):
    """
    Base resource returned from Planet API search, expressed as a tree node
    """

    iconUpdated = pyqtSignal()

    # noinspection PyUnusedLocal
    def __init__(self, name: str = None,
                 node_type=None,
                 resource_type=None,
                 resource=None,
                 parent=None,
                 index=None,
                 sort_field=None,
                 q_parent: QObject = None,
                 **kwargs) -> None:
        super().__init__(parent=q_parent)

        self._name = name
        self._children = []
        self._parent = parent
        self._index: QModelIndex = index
        self._resource = resource
        self._resource_type: Union[RESOURCE_DAILY] = \
            resource_type
        # 'published desc' sort order is API default
        self._sort_field = sort_field \
            if sort_field in ['published', 'acquired'] else 'published'

        self._thumb: Optional[QPixmap] = None
        self._thumb_url: Optional[str] = None
        self._thumb_url_local: Optional[str] = None
        self._thumbnail_loaded: bool = False
        self._item_id: Optional[str] = None
        self._item_type: Optional[str] = None
        self._description: Optional[str] = None
        self._alt_description: Optional[str] = None
        self._geometry = None
        self._geometries = None  # for group-of-nodes types
        self._permissions = None
        self._properties = None
        self._acquired: Optional[datetime] = None
        self._published: Optional[datetime] = None
        self._sort_date = None

        self._item_type_id_list: list = []
        self._percent_coverage: int = 0
        self._downloadable = True

        self._product_type = None

        self._node_type: PlanetNodeType = node_type
        self._is_traversed: bool = False
        self._checked_state: Qt.CheckState = Qt.Unchecked

        # to indicate that it has been updated after a 'load more' request
        self._has_new_children: bool = False 

        if self._parent is not None:
            self._parent.add_child(self)

        if self._resource is not None:
            self.load_resource()
        else:
            # Always set item type and id, so even groups have identifiers,
            #   for thumb caching, etc.
            if self._node_type:
                self._item_type = self._node_type.name
            else:
                self._item_type = PlanetNodeType.UNDEFINED.name
            # Random uuid
            self._item_id = str(uuid4())
            # Need a date to generate description
            self._sort_date = datetime.utcnow()

        # Note: node_type may be None here
        if self.has_thumbnail():
            thumb = QPixmap(PLACEHOLDER_THUMB, 'SVG')
            if not thumb.isNull():
                self._thumb = thumb

    def resource(self):
        return self._resource

    def has_resource(self):
        return self._resource is not None

    def name(self) -> str:
        return self._name

    def set_name(self, name):
        self._name = name

    def icon(self) -> QIcon:
        return QIcon(self._thumb)

    def thumbnail(self) -> QPixmap:
        return self._thumb

    def set_thumbnail(self, pixmap: QPixmap, local_url: Optional[str] = None):
        self._thumb = pixmap
        self._thumbnail_loaded = True
        if local_url and os.path.exists(local_url):
            self._thumb_url_local = local_url
        else:
            log.debug(f'Thumbnail local url does not exist:\n{local_url}')

    def thumbnail_url(self) -> str:
        return self._thumb_url

    def thumbnail_local_url(self) -> str:
        return self._thumb_url_local

    def thumbnail_loaded(self) -> bool:
        return self._thumbnail_loaded

    def item_id(self):
        return self._item_id

    def item_type(self):
        return self._item_type

    def item_type_id(self):
        """Generic Planet API item identifier"""
        return f'{self._item_type}:{self._item_id}'

    def item_type_id_key(self):
        """Item identifier for dict keys and file names"""
        return f'{self._item_type}__{self._item_id}'

    def item_properties(self):
        return self._properties

    def published(self):
        return self._published

    def acquired(self):
        return self._acquired

    def sort_date(self):
        return self._sort_date

    def set_sort_date(self, sort_date):
        self._sort_date = sort_date
        # Sort date is used in all descriptions, regardless of node_type
        self.update_description()

    @staticmethod
    def formatted_date(obj: Union[date, datetime]) -> str:
        return obj.strftime(DATE_FORMAT)

    @staticmethod
    def formatted_time(obj: Union[time, datetime]) -> str:
        return obj.strftime(TIME_FORMAT)

    @staticmethod
    def formatted_date_time(obj: datetime, suffix='UTC') -> str:
        return obj.strftime(f'{DATE_FORMAT} {TIME_FORMAT} {suffix}')

    def item_type_id_list(self):
        return self._item_type_id_list

    def set_item_type_id_list(self, item_type_ids: list):
        self._item_type_id_list = item_type_ids
        self.update_description()

    def add_item_type_id(self, item_type_id):
        self._item_type_id_list.append(item_type_id)
        self.update_description()

    def description(self) -> str:
        if self._description is None:
            return self._name
        return self._description

    def alternate_description(self) -> str:
        if self._description is None:
            return self._name
        return self._alt_description

    def geometry(self):
        return self._geometry

    def geometries(self):
        return self._geometries

    def add_geometry(self, geom):
        if self._geometries is None:
            self._geometries = [geom]
        else:
            self._geometries.append(geom)

    def set_geometries(self, geometries):
        self._geometries = geometries

    def permissions(self):
        return self._permissions

    def _resolve_node_type(self):
        if self._item_type and self._item_type in DAILY_NODE_ITEM_TYPES:
            return PlanetNodeType.DAILY_SCENE_IMAGE
        if self._product_type and 'quad_download' in self._resource:
            return PlanetNodeType.MOSAIC
        if self._product_type and 'selector' in self._resource:
            return PlanetNodeType.MOSAIC_SERIES
        if 'percent_covered' in self._resource:
            return PlanetNodeType.MOSAIC_QUAD

        return PlanetNodeType.UNDEFINED

    def node_type(self) -> PlanetNodeType:
        return self._node_type

    def set_node_type(self, node_type):
        self._node_type = node_type
        if self._resource is None:
            # For group nodes, etc.
            self._item_type = self._node_type.name

    def parent(self):
        return self._parent if self._parent else None

    def set_parent(self, node) -> None:
        self._parent = node

    def index(self):
        return self._index

    def set_index(self, index):
        self._index = index

    def has_new_children(self):
        return self._has_new_children

    def set_has_new_children(self, has_new_children):
        self._has_new_children = has_new_children
        self.update_description()

    def load_resource(self, resource=None, resource_type=None):
        if resource is not None:
            self._resource = resource
        if not self._resource:
            raise PlanetNodeException('Node has no resource to load')
        if resource_type is not None:
            self._resource_type = resource_type
        if not self._resource_type:
            raise PlanetNodeException('Node has no resource type to load')

        if self._resource_type == RESOURCE_DAILY:

            self._item_id = self._resource['id']
            self._geometry = self._resource['geometry']  # as GeoJSON
            self._permissions = self._resource['_permissions']
            self._properties = self._resource['properties']
            self._item_type = self._properties['item_type']
            self._thumb_url = \
                self._resource[models.Items.LINKS_KEY]['thumbnail']

            if not self._node_type:
                self._node_type = self._resolve_node_type()

            # Generate description
            self._published: datetime = iso8601.parse_date(
                self._properties['published'])
            self._acquired: datetime = iso8601.parse_date(
                self._properties['acquired'])

            if self._sort_field == 'published':
                self._sort_date = self._published
            else:
                self._sort_date = self._acquired

            self.update_description()

            if len(self._permissions) == 0:
                self._downloadable = False
            else:
                matches = [ITEM_ASSET_DL_REGEX.match(s) is not None
                           for s in self._permissions]
                self._downloadable = any(matches)

        elif self._resource_type == RESOURCE_MOSAICS:
            # TODO: Implement mosaics node resource loading

            if not self._node_type:
                self._node_type = self._resolve_node_type()

    def update_description(self):
        d_date = self._sort_date.strftime(DATE_FORMAT)
        d_time = self._sort_date.strftime(TIME_FORMAT)
        d_tz = 'UTC'

        count_style = (SUBTEXT_STYLE_WITH_NEW_CHILDREN 
            if self._has_new_children else SUBTEXT_STYLE)
        # Alternate description, e.g. on mouse hover
        # TODO: Add converted date/time to sor_date time zone using pytz
        # local_tz =  # get from self._geometry centroid
        # local_date =  # converted date/time
        # d_date_local = f"{local_sort_date} {local_tz}\n"
        # d_tz_local = local_tz
        # self._alt_description = ...

        if self._node_type == PlanetNodeType.DAILY_SCENE_IMAGE:
            self._description = f"""
<span style="{LRG_TEXT_STYLE}">
{d_date}</span> <span style="{SUBTEXT_STYLE}">{d_time} {d_tz}</span><br>
<b>{DAILY_ITEM_TYPES_DICT[self._item_type]}</b><br>
<span style="{SUBTEXT_STYLE}">{self._item_id}</span>
"""

        elif self._node_type == PlanetNodeType.DAILY_SAT_GROUP:
            size = locale.format("%d", self.child_count(), grouping=True)
            self._description = f"""
<span style="{SUBTEXT_STYLE}"> {d_date} {d_time} {d_tz}</span>
<span style="{count_style}">({size})</span>
<span style="{SUBTEXT_STYLE}">: satellite {self._name}</span>
"""

        elif self._node_type == PlanetNodeType.DAILY_SCENE:
            size = locale.format("%d", len(self._item_type_id_list), grouping=True)
            self._description = f"""
<span style="{LRG_TEXT_STYLE}">
{d_date}</span> <span style="{SUBTEXT_STYLE}">{d_time} {d_tz}</span><br>
<b>{DAILY_ITEM_TYPES_DICT[self._name]}</b><br>
<span style="{count_style}">{size} images
</span>
"""
        # , {self._percent_coverage}% coverage

        else:
            self._description = None

    def child_images_count(self):
        if self._node_type == PlanetNodeType.DAILY_SAT_GROUP:
            return self.child_count()
        elif self._node_type == PlanetNodeType.DAILY_SCENE:
            return len(self._item_type_id_list)
        elif self._node_type == PlanetNodeType.DAILY_SCENE_IMAGE:
            return 1
        else:
            return 0

    def is_traversed(self) -> bool:
        return self._is_traversed

    def set_is_traversed(self, traversed: bool) -> None:
        self._is_traversed = traversed

    def resource_type(self):
        if self._resource_type:
            return self._resource_type
        else:
            if self._item_type in DAILY_ITEM_TYPES:
                return RESOURCE_DAILY
            elif self._product_type in MOSAIC_PRODUCT_TYPES:
                # TODO: Add test for mosaics types
                return RESOURCE_MOSAICS

    def is_undefined_node_type(self):
        return self.node_type() == PlanetNodeType.UNDEFINED

    def is_base_node(self):
        return self.node_type() in [
            PlanetNodeType.UNDEFINED,
            PlanetNodeType.ROOT,
            PlanetNodeType.LOADING,
            PlanetNodeType.LOAD_MORE
        ]

    def can_fetch_more(self) -> bool:
        return self.node_type() in [
            PlanetNodeType.DAILY_SCENE,
            PlanetNodeType.DAILY_SAT_GROUP,
            PlanetNodeType.MOSAIC,
            PlanetNodeType.MOSAIC_SERIES,
        ]

    def is_group_node(self):
        return self.node_type() in [
            PlanetNodeType.DAILY_SCENE,
            PlanetNodeType.DAILY_SAT_GROUP,
            PlanetNodeType.MOSAIC,
            PlanetNodeType.MOSAIC_SERIES,
        ]

    def is_base_image(self) -> bool:
        return self.node_type() in [
            PlanetNodeType.DAILY_SCENE_IMAGE,
            PlanetNodeType.MOSAIC_QUAD,
        ]

    def has_thumbnail(self) -> bool:
        return self.node_type() in [
            PlanetNodeType.DAILY_SCENE,
            PlanetNodeType.DAILY_SCENE_IMAGE,
            PlanetNodeType.MOSAIC,
            PlanetNodeType.MOSAIC_SERIES,
            PlanetNodeType.MOSAIC_QUAD,
        ]

    def has_footprint(self) -> bool:
        return self.node_type() in [
            PlanetNodeType.DAILY_SCENE_IMAGE,
            PlanetNodeType.MOSAIC_QUAD,
        ]

    def has_group_footprint(self) -> bool:
        return self.node_type() in [
            PlanetNodeType.DAILY_SCENE,
            PlanetNodeType.DAILY_SAT_GROUP,
        ]

    def can_load_preview_layer(self) -> bool:
        return (self.can_be_downloaded()
                and self.node_type() in [
                    PlanetNodeType.DAILY_SCENE,
                    PlanetNodeType.DAILY_SAT_GROUP,
                    PlanetNodeType.DAILY_SCENE_IMAGE,
                    PlanetNodeType.MOSAIC,
                    PlanetNodeType.MOSAIC_SERIES,
                    PlanetNodeType.MOSAIC_QUAD,
                    ]
                )

    def can_be_downloaded(self):
        return self._downloadable

    def set_can_be_downloaded(self, can_dl):
        self._downloadable = can_dl

    def children(self):
        return self._children

    def children_of_node_type(self, node_type: PlanetNodeType) -> list:
        nodes_w_type = []

        def find_node_type(node: PlanetNode, n_type: PlanetNodeType):
            nodes = []
            for child in node.children():
                child: PlanetNode
                if child.has_children():
                    find_node_type(child, n_type)
                elif child.node_type() == n_type:
                    nodes.append(child)

            if nodes:
                nodes_w_type.extend(nodes)

        find_node_type(self, node_type)

        return nodes_w_type

    def has_children(self) -> bool:
        # Should include children that have YET to be fetched
        return len(self._children) > 0 or self.can_fetch_more()

    def add_child(self, child) -> None:
        self._children.append(child)
        child.set_parent(self)

    def add_children(self, children) -> None:
        for child in children:
            self.add_child(child)

    def insert_child(self, position: int, child) -> bool:
        if position < 0 or position > self.child_count():
            return False

        self._children.insert(position, child)
        child.set_parent(self)

        return True

    def remove_child(self, index: int) -> bool:
        try:
            del self._children[index]
            return True
        except IndexError:
            return False

    # noinspection DuplicatedCode
    def remove_children(self, position: int, count: int) -> bool:
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

    def first_child(self):
        if len(self._children) > 0:
            return self._children[0]
        return None

    def last_child(self):
        if len(self._children) > 0:
            return self._children[-1]
        return None

    def remove_last_child(self) -> None:
        child = self.children().pop()
        del child

    def child(self, row: int):
        return self._children[row]

    def child_count(self) -> int:
        return len(self._children)

    def row(self) -> int:
        if self._parent is not None:
            return self._parent.children().index(self)
        return 0

    # Not sure if this is possible. May have to pass in model instance.
    # def resolved_index(self) -> QModelIndex:
    #     node = self
    #     parents = []
    #     while True:
    #         if not node.parent():
    #             break
    #         parents.append(node.parent())
    #         node = node.parent()
    #
    #     return

    def checked_state(self) -> Qt.CheckState:
        return self._checked_state

    def set_checked_state(self, state: Qt.CheckState = Qt.Unchecked) -> None:
        self._checked_state = state
