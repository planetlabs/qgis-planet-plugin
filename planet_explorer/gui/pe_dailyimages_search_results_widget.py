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
__author__ = "Planet Federal"
__date__ = "August 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import logging
import os

import iso8601
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
    QgsRectangle,
    QgsWkbTypes,
)
from qgis.gui import QgsRubberBand
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal, pyqtSlot
from qgis.PyQt.QtGui import QColor, QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
)

from ..gui.pe_results_configuration_dialog import (
    PlanetNodeMetadata,
    ResultsConfigurationDialog,
)
from ..gui.pe_save_search_dialog import SaveSearchDialog
from ..pe_analytics import (
    analytics_track,
    send_analytics_for_preview,
    SAVED_SEARCH_CREATED,
)

from ..pe_utils import (
    PLANET_COLOR,
    SEARCH_AOI_COLOR,
    area_coverage_for_image,
    create_preview_group,
    iface,
    qgsgeometry_from_geojson,
)
from ..planet_api.p_client import PlanetClient, ITEM_ASSET_DL_REGEX
from .pe_gui_utils import waitcursor
from .pe_thumbnails import createCompoundThumbnail, download_thumbnail

plugin_path = os.path.split(os.path.dirname(__file__))[0]


def iconPath(f):
    return os.path.join(plugin_path, "resources", f)


TOP_ITEMS_BATCH = 250
CHILD_COUNT_THRESHOLD_FOR_PREVIEW = 100

ID = "id"
SATELLITE_ID = "satellite_id"
INSTRUMENT = "instrument"
PROPERTIES = "properties"
ASSETS = "assets"
GEOMETRY = "geometry"
ITEM_TYPE = "item_type"
PERMISSIONS = "_permissions"

SUBTEXT_STYLE = "color: rgb(100,100,100);"
SUBTEXT_STYLE_WITH_NEW_CHILDREN = "color: rgb(157,0,165);"

ADD_PREVIEW_ICON = QIcon(iconPath("mActionAddXyzLayer.svg"))
SAVE_ICON = QgsApplication.getThemeIcon("/mActionFileSave.svg")
ZOOMTO_ICON = QIcon(":/plugins/planet_explorer/zoom-target.svg")
SORT_ICON = QIcon(iconPath("sort.svg"))
LOCK_ICON = QIcon(":/plugins/planet_explorer/lock-light.svg")
PLACEHOLDER_THUMB = ":/plugins/planet_explorer/thumb-placeholder-128.svg"

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get("PYTHON_LOG_VERBOSE", None)

RESULTS_WIDGET, RESULTS_BASE = uic.loadUiType(
    os.path.join(plugin_path, "ui", "pe_search_results_base.ui"),
    from_imports=True,
    import_from=f"{os.path.basename(plugin_path)}",
    resource_suffix="",
)


class DailyImagesSearchResultsWidget(RESULTS_BASE, RESULTS_WIDGET):

    setAOIRequested = pyqtSignal(dict)
    checkedCountChanged = pyqtSignal(int)

    def __init__(self):
        super().__init__()

        self.setupUi(self)

        self._p_client = PlanetClient.getInstance()

        self._has_more = True

        self._metadata_to_show = [
            PlanetNodeMetadata.CLOUD_PERCENTAGE,
            PlanetNodeMetadata.GROUND_SAMPLE_DISTANCE,
        ]

        self._image_count = 0
        self._total_count = 0

        self._request = None
        self._local_filters = None
        self._response_iterator = None

        self.btnSaveSearch.setIcon(SAVE_ICON)
        self.btnSort.setIcon(SORT_ICON)
        self.btnAddPreview.setIcon(ADD_PREVIEW_ICON)
        self.btnAddPreview.setEnabled(False)

        self.btnSaveSearch.clicked.connect(self._save_search)
        self.btnAddPreview.clicked.connect(self._add_preview_clicked)
        self.btnSort.clicked.connect(self._sort_order_changed)
        self.btnSettings.clicked.connect(self._open_settings)
        self.lblImageCount.setOpenExternalLinks(False)
        self.lblImageCount.linkActivated.connect(self.load_more_link_clicked)

        self._aoi_box = None
        self._setup_request_aoi_box()

        self._set_widgets_visibility(False)
        self.labelNoResults.setText("""
                <p><b>Perform a search to get results.</b></p>
                """)

    def _set_widgets_visibility(self, search_ok):
        self.tree.setVisible(search_ok)
        self.widgetActions.setVisible(search_ok)
        self.widgetNoResults.setVisible(not search_ok)
        if not search_ok:
            self.labelNoResults.setText("""
                <p><b>Sorry, no results found</b></p>
                <p>Try refining your filter, extending your date range,<br/>
                or searching in another location to see more imagery.</p>
                """)

    def search_has_been_performed(self):
        return self._request is not None

    def _open_settings(self):
        dlg = ResultsConfigurationDialog(self._metadata_to_show)
        if dlg.exec_():
            self._metadata_to_show = dlg.selection
            self.update_image_items()

    def _add_preview_clicked(self):
        self.add_preview()

    @waitcursor
    def add_preview(self):
        imgs = self.selected_images()
        send_analytics_for_preview(imgs)
        create_preview_group("Selected images", imgs)

    def update_image_items(self):
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            if isinstance(item, SceneItem):
                w = self.tree.itemWidget(item, 0)
                w.set_metadata_to_show(self._metadata_to_show)
            it += 1

    def _save_search(self):
        dlg = SaveSearchDialog(self._request)
        if dlg.exec_():
            self._p_client.create_search(dlg.request_to_save)
            analytics_track(SAVED_SEARCH_CREATED)

    def sort_order(self):
        order = ["acquired"]
        if self.btnSort.isChecked():
            order.append("asc")
        else:
            order.append("desc")
        return order

    def _sort_order_changed(self):
        self.update_request(self._request, {})

    def load_more_link_clicked(self):
        self.load_more()

    @waitcursor
    def update_request(self, request, local_filters):
        self._image_count = 0
        self._request = request
        self._local_filters = local_filters
        self.tree.clear()
        stats_request = {"interval": "year"}
        stats_request.update(self._request)
        resp = self._p_client.stats(stats_request).get()
        self._total_count = sum([b["count"] for b in resp["buckets"]])
        if self._total_count:
            response = self._p_client.quick_search(
                self._request,
                page_size=TOP_ITEMS_BATCH,
                sort=" ".join(self.sort_order()),
            )
            self._response_iterator = response.iter()
            self.load_more()
            self._set_widgets_visibility(True)
        else:
            self._set_widgets_visibility(False)

    @waitcursor
    def load_more(self):
        page = next(self._response_iterator, None)
        if page is not None:
            for i in range(self.tree.topLevelItemCount()):
                date_item = self.tree.topLevelItem(i)
                date_widget = self.tree.itemWidget(date_item, 0)
                date_widget.has_new = False
                for j in range(date_item.childCount()):
                    satellite_item = date_item.child(j)
                    satellite_widget = self.tree.itemWidget(satellite_item, 0)
                    satellite_widget.has_new = False

            links = page.get()[page.LINKS_KEY]
            next_ = links.get(page.NEXT_KEY, None)
            self._has_more = next_ is not None
            images = page.get().get(page.ITEM_KEY)
            for i, image in enumerate(images):
                if self._passes_area_coverage_filter(image):
                    sort_criteria = "acquired"
                    date_item, satellite_item = self._find_items_for_satellite(image)
                    date_widget = self.tree.itemWidget(date_item, 0)
                    satellite_widget = self.tree.itemWidget(satellite_item, 0)
                    item = SceneItem(image, sort_criteria)
                    widget = SceneItemWidget(
                        image,
                        sort_criteria,
                        self._metadata_to_show,
                        item,
                        self._request,
                    )
                    widget.checkedStateChanged.connect(self.checked_count_changed)
                    widget.thumbnailChanged.connect(satellite_widget.update_thumbnail)
                    item.setSizeHint(0, widget.sizeHint())
                    satellite_item.addChild(item)
                    self.tree.setItemWidget(item, 0, widget)
                    date_widget.update_for_children()
                    self._image_count += 1

            for i in range(self.tree.topLevelItemCount()):
                date_item = self.tree.topLevelItem(i)
                date_widget = self.tree.itemWidget(date_item, 0)
                for j in range(date_item.childCount()):
                    satellite_item = date_item.child(j)
                    satellite_widget = self.tree.itemWidget(satellite_item, 0)
                    satellite_widget.update_for_children()
                    satellite_widget.update_thumbnail()
                    satellite_item.sortChildren(0, Qt.AscendingOrder)
                date_widget.update_for_children()
                date_widget.update_thumbnail()
            self.item_count_changed()
        else:
            self._has_more = False
            self.item_count_changed()

    def _local_filter(self, name):
        for f in self._local_filters:
            if f.get("field_name") == name:
                return f

    def _passes_area_coverage_filter(self, image):
        area_coverage = area_coverage_for_image(image, self._request)
        if area_coverage is None:
            return True  # an ID filter is begin used, so it makes no sense to
            # check for are acoverage
        filt = self._local_filter("area_coverage")
        if filt:
            minvalue = filt["config"].get("gte", 0)
            maxvalue = filt["config"].get("lte", 100)
            return area_coverage > minvalue and area_coverage < maxvalue
        return True

    def _find_item_for_date(self, image):
        sort_criteria = "acquired"
        date = iso8601.parse_date(image[PROPERTIES][sort_criteria]).date()
        itemtype = image[PROPERTIES][ITEM_TYPE]
        count = self.tree.topLevelItemCount()
        for i in range(count):
            child = self.tree.topLevelItem(i)
            if child.date == date and child.itemtype == itemtype:
                return child
        date_item = DateItem(image, sort_criteria)
        widget = DateItemWidget(image, sort_criteria, date_item)
        widget.checkedStateChanged.connect(self.checked_count_changed)
        date_item.setSizeHint(0, widget.sizeHint())
        self.tree.addTopLevelItem(date_item)
        self.tree.setItemWidget(date_item, 0, widget)
        return date_item

    def _find_items_for_satellite(self, image):
        date_item = self._find_item_for_date(image)
        date_widget = self.tree.itemWidget(date_item, 0)
        satellite = image[PROPERTIES][SATELLITE_ID]
        instrument = image[PROPERTIES].get(INSTRUMENT, "")
        count = date_item.childCount()
        for i in range(count):
            child = date_item.child(i)
            if child.satellite == satellite:
                return date_item, child
        satellite_item = SatelliteItem(satellite)
        widget = SatelliteItemWidget(satellite, instrument, satellite_item)
        widget.thumbnailChanged.connect(date_widget.update_thumbnail)
        widget.checkedStateChanged.connect(self.checked_count_changed)
        satellite_item.setSizeHint(0, widget.sizeHint())
        date_item.addChild(satellite_item)
        self.tree.setItemWidget(satellite_item, 0, widget)
        return date_item, satellite_item

    def selected_images(self):
        selected = []
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            if isinstance(item, SceneItem):
                w = self.tree.itemWidget(item, 0)
                w.set_metadata_to_show(self._metadata_to_show)
                if w.is_selected():
                    selected.append(w.image)
            it += 1
        return selected

    def checked_count_changed(self):
        numimages = len(self.selected_images())
        self.btnAddPreview.setEnabled(numimages)
        self.checkedCountChanged.emit(numimages)

    def item_count_changed(self):
        if self._image_count < self._total_count:
            self.lblImageCount.setText(
                f"{self._image_count} images. <a href='#'>Load more</a>"
            )
        else:
            self.lblImageCount.setText(f"{self._image_count} images")

    def _setup_request_aoi_box(self):
        self._aoi_box = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
        self._aoi_box.setFillColor(QColor(0, 0, 0, 0))
        self._aoi_box.setStrokeColor(SEARCH_AOI_COLOR)
        self._aoi_box.setWidth(2)
        self._aoi_box.setLineStyle(Qt.DashLine)

    @pyqtSlot()
    def clear_aoi_box(self):
        if self._aoi_box:
            self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)

    def clean_up(self):
        self.clear_aoi_box()
        self.tree.clear()
        self.lblImageCount.setText("")
        self._set_widgets_visibility(False)
        self.labelNoResults.setText("""
                <p><b>Perform a search to get results.</b></p>
                """)

    def closeEvent(self, event):
        self.clean_up()
        super().closeEvent(self, event)

    def request_query(self):
        return self._request


class ItemWidgetBase(QFrame):

    checkedStateChanged = pyqtSignal()
    thumbnailChanged = pyqtSignal()

    def __init__(self, item):
        QFrame.__init__(self)
        self.item = item
        self.is_updating_checkbox = False
        self.setMouseTracking(True)
        self.setStyleSheet("ItemWidgetBase{border: 2px solid transparent;}")

    def _setup_ui(self, text, thumbnailurl):

        self.lockLabel = QLabel()
        iconSize = QSize(16, 16)
        self.lockLabel.setPixmap(LOCK_ICON.pixmap(iconSize))
        self.checkBox = QCheckBox("")
        self.checkBox.clicked.connect(self.check_box_state_changed)
        self.nameLabel = QLabel(text)
        self.iconLabel = QLabel()
        self.labelZoomTo = QLabel()
        self.labelZoomTo.setPixmap(ZOOMTO_ICON.pixmap(QSize(18, 18)))
        self.labelZoomTo.setToolTip("Zoom to extent")
        self.labelZoomTo.mousePressEvent = self.zoom_to_extent
        self.labelAddPreview = QLabel()
        self.labelAddPreview.setPixmap(ADD_PREVIEW_ICON.pixmap(QSize(18, 18)))
        self.labelAddPreview.setToolTip("Add preview layer to map")
        self.labelAddPreview.mousePressEvent = self._add_preview_clicked

        layout = QHBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.checkBox)
        layout.addWidget(self.lockLabel)
        pixmap = QPixmap(PLACEHOLDER_THUMB, "SVG")
        self.thumbnail = None
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.iconLabel.setFixedSize(48, 48)
        layout.addWidget(self.iconLabel)
        if thumbnailurl is not None:
            download_thumbnail(thumbnailurl, self)
        layout.addWidget(self.nameLabel)
        layout.addStretch()
        layout.addWidget(self.labelZoomTo)
        layout.addWidget(self.labelAddPreview)
        layout.addSpacing(10)
        self.setLayout(layout)

        self.footprint = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
        self.footprint.setStrokeColor(PLANET_COLOR)
        self.footprint.setWidth(2)

    def set_thumbnail(self, img):
        self.thumbnail = QPixmap(img)
        thumb = self.thumbnail.scaled(
            48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.iconLabel.setPixmap(thumb)
        self.thumbnailChanged.emit()

    def is_selected(self):
        return self.checkBox.checkState() == Qt.Checked

    def _geom_bbox_in_project_crs(self):
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().crs(),
            QgsProject.instance(),
        )
        return transform.transformBoundingBox(self.geom.boundingBox())

    def _geom_in_project_crs(self):
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().crs(),
            QgsProject.instance(),
        )
        geom = QgsGeometry(self.geom)
        geom.transform(transform)
        return geom

    def show_footprint(self):
        self.footprint.setToGeometry(self._geom_in_project_crs())

    def hide_footprint(self):
        self.footprint.reset(QgsWkbTypes.PolygonGeometry)

    def enterEvent(self, event):
        self.setStyleSheet("ItemWidgetBase{border: 2px solid rgb(0, 157, 165);}")
        self.show_footprint()

    def leaveEvent(self, event):
        self.setStyleSheet("ItemWidgetBase{border: 2px solid transparent;}")
        self.hide_footprint()

    def zoom_to_extent(self, evt):
        rect = QgsRectangle(self._geom_bbox_in_project_crs())
        rect.scale(1.05)
        iface.mapCanvas().setExtent(rect)
        iface.mapCanvas().refresh()

    def _add_preview_clicked(self, evt):
        self.add_preview()

    @waitcursor
    def add_preview(self):
        send_analytics_for_preview(self.item.images())
        create_preview_group(self.name(), self.item.images())

    def check_box_state_changed(self):
        self.update_children_items()
        self.update_parent_item()
        self.checkedStateChanged.emit()

    def update_parent_item(self):
        parent = self.item.parent()
        if parent is not None:
            w = parent.treeWidget().itemWidget(parent, 0)
            w.update_checkbox()

    def update_children_items(self):
        total = self.item.childCount()
        if self.checkBox.isTristate():
            self.checkBox.setTristate(False)
            self.checkBox.setChecked(False)
        for i in range(total):
            w = self.item.treeWidget().itemWidget(self.item.child(i), 0)
            w.set_checked(self.checkBox.isChecked())

    def update_checkbox(self):
        selected = 0
        total = self.item.childCount()
        for i in range(total):
            w = self.item.treeWidget().itemWidget(self.item.child(i), 0)
            if w.is_selected():
                selected += 1
        if selected == total:
            self.checkBox.setTristate(False)
            self.checkBox.setCheckState(Qt.Checked)
        elif selected == 0:
            self.checkBox.setTristate(False)
            self.checkBox.setCheckState(Qt.Unchecked)
        else:
            self.checkBox.setTristate(True)
            self.checkBox.setCheckState(Qt.PartiallyChecked)

    def set_checked(self, checked):
        self.checkBox.setChecked(checked)
        self.update_children_items()

    def update_thumbnail(self):
        thumbnails = self.scene_thumbnails()
        if thumbnails and None not in thumbnails:
            bboxes = [img[GEOMETRY] for img in self.item.images()]
            pixmap = createCompoundThumbnail(bboxes, thumbnails)
            thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.iconLabel.setPixmap(thumb)
            self.thumbnailChanged.emit()

    def scene_thumbnails(self):
        thumbnails = []
        try:
            for i in range(self.item.childCount()):
                w = self.item.treeWidget().itemWidget(self.item.child(i), 0)
                thumbnails.extend(w.scene_thumbnails())
        except RuntimeError:
            # item might not exist anymore. In this case, we just return
            # an empty list
            pass
        return thumbnails


class DateItem(QTreeWidgetItem):
    def __init__(self, image, sort_criteria):
        QListWidgetItem.__init__(self)
        properties = image[PROPERTIES]
        self.date = iso8601.parse_date(properties[sort_criteria]).date()
        self.itemtype = properties[ITEM_TYPE]

    def images(self):
        images = []
        for i in range(self.childCount()):
            item = self.child(i)
            images.extend(item.images())
        return images


class DateItemWidget(ItemWidgetBase):
    def __init__(self, image, sort_criteria, item):
        ItemWidgetBase.__init__(self, item)
        self.has_new = True
        self.image = image
        self.properties = image[PROPERTIES]
        datetime = iso8601.parse_date(self.properties[sort_criteria])
        self.date = datetime.strftime("%b %d, %Y")

        self._setup_ui("", None)
        self.update_for_children()

    def update_for_children(self):
        size = 0
        for i in range(self.item.childCount()):
            child = self.item.child(i)
            size += child.childCount()
        count_style = (
            SUBTEXT_STYLE if not self.has_new else SUBTEXT_STYLE_WITH_NEW_CHILDREN
        )
        self.children_count = size
        text = f"""{self.date}<br>
                    <b>{PlanetClient.getInstance().item_types_names()[self.properties[ITEM_TYPE]]}</b><br>
                    <span style="{count_style}">{size} images</span>"""
        self.nameLabel.setText(text)

        geoms = []
        self.downloadable = False
        for i in range(self.item.childCount()):
            child = self.item.child(i)
            w = self.item.treeWidget().itemWidget(child, 0)
            geoms.append(w.geom)
            if w.downloadable:
                self.downloadable = True
        self.geom = QgsGeometry.collectGeometry(geoms)
        self.lockLabel.setVisible(not self.downloadable)
        self.checkBox.setEnabled(self.downloadable)
        self.labelAddPreview.setEnabled(self.downloadable)

        nscenes = 0
        for i in range(self.item.childCount()):
            nscenes += self.item.child(i).childCount()

        self.setToolTip("")
        if not self.downloadable:
            self.labelAddPreview.setToolTip(
                "Contact sales to purchase access.\nUse the link in the ⓘ menu."
            )
            self.setToolTip(
                "Contact sales to purchase access.\nUse the link in the ⓘ menu."
            )
        elif nscenes > CHILD_COUNT_THRESHOLD_FOR_PREVIEW:
            self.labelAddPreview.setToolTip("Too many images to preview")
            self.labelAddPreview.setEnabled(False)
        else:
            self.labelAddPreview.setToolTip("Add preview layer to map")

        # self._update_thumbnail()

    def name(self):
        item_types_names = PlanetClient.getInstance().item_types_names()
        return f"{self.date} | {item_types_names[self.properties[ITEM_TYPE]]}"


class SatelliteItem(QTreeWidgetItem):
    def __init__(self, satellite):
        QListWidgetItem.__init__(self)
        self.satellite = satellite

    def images(self):
        images = []
        for i in range(self.childCount()):
            item = self.child(i)
            images.extend(item.images())
        return images


class SatelliteItemWidget(ItemWidgetBase):
    def __init__(self, satellite, instrument, item):
        ItemWidgetBase.__init__(self, item)
        self.has_new = True
        self.satellite = satellite
        self.instrument = instrument
        self._setup_ui("", None)
        self.update_for_children()

    def update_for_children(self):
        size = self.item.childCount()
        count_style = (
            SUBTEXT_STYLE if not self.has_new else SUBTEXT_STYLE_WITH_NEW_CHILDREN
        )
        self.children_count = size
        text = f"""<span style="{SUBTEXT_STYLE}"> Satellite {self.satellite} {self.instrument} </span>
                    <span style="{count_style}">({size} images)</span>"""
        self.nameLabel.setText(text)

        geoms = []
        self.ids = []
        self.downloadable = False
        for i in range(size):
            child = self.item.child(i)
            w = self.item.treeWidget().itemWidget(child, 0)
            geoms.append(w.geom)
            if w.downloadable:
                self.downloadable = True
            self.ids.append(child.image[ID])
        self.geom = QgsGeometry.collectGeometry(geoms)
        self.lockLabel.setVisible(not self.downloadable)
        self.checkBox.setEnabled(self.downloadable)
        self.labelAddPreview.setEnabled(self.downloadable)

        if not self.downloadable:
            self.labelAddPreview.setToolTip("Contact sales to purchase access")
            self.labelAddPreview.setEnabled(False)
        elif self.item.childCount() > CHILD_COUNT_THRESHOLD_FOR_PREVIEW:
            self.labelAddPreview.setToolTip("Too many images to preview")
            self.labelAddPreview.setEnabled(False)
        else:
            self.labelAddPreview.setToolTip("Add preview layer to map")

    def name(self):
        return f"Satellite {self.satellite}"


class SceneItem(QTreeWidgetItem):
    def __init__(self, image, sort_criteria):
        QListWidgetItem.__init__(self)
        self.image = image
        self.date = iso8601.parse_date(image[PROPERTIES][sort_criteria])

    def __lt__(self, other):
        if not isinstance(other, SceneItem):
            return super(SceneItem, self).__lt__(other)

        return self.date < other.date

    def images(self):
        return [self.image]


class SceneItemWidget(ItemWidgetBase):
    def __init__(self, image, sort_criteria, metadata_to_show, item, request):
        ItemWidgetBase.__init__(self, item)
        self.image = image
        self.request = request
        self.metadata_to_show = metadata_to_show
        self.properties = image[PROPERTIES]

        datetime = iso8601.parse_date(self.properties[sort_criteria])
        self.time = datetime.strftime("%H:%M:%S")
        self.date = datetime.strftime("%b %d, %Y")

        text = self._get_text()
        url = f"{image['_links']['thumbnail']}?api_key={PlanetClient.getInstance().api_key()}"

        self._setup_ui(text, url)

        permissions = image[PERMISSIONS]
        if len(permissions) == 0:
            self.downloadable = False
        else:
            matches = [ITEM_ASSET_DL_REGEX.match(s) is not None for s in permissions]
            self.downloadable = any(matches)

        self.lockLabel.setVisible(not self.downloadable)
        self.checkBox.setEnabled(self.downloadable)
        self.geom = qgsgeometry_from_geojson(image[GEOMETRY])

        if not self.downloadable:
            self.labelAddPreview.setToolTip("Contact sales to purchase access")
            self.labelAddPreview.setEnabled(False)

    def set_metadata_to_show(self, metadata_to_show):
        self.metadata_to_show = metadata_to_show
        self.update_text()

    def update_text(self):
        self.nameLabel.setText(self._get_text())

    def _get_text(self):
        metadata = ""
        for i, value in enumerate(self.metadata_to_show):
            spacer = "<br>" if i == 1 else " "
            if value == PlanetNodeMetadata.AREA_COVER:
                area_coverage = area_coverage_for_image(self.image, self.request)
                if area_coverage is not None:
                    metadata += f"{value.value}:{area_coverage:.0f}{spacer}"
                else:
                    metadata += f"{value.value}:--{spacer}"
            else:
                metadata += (
                    f'{value.value}:{self.properties.get(value.value, "--")}{spacer}'
                )
        text = f"""{self.date}<span style="color: rgb(100,100,100);"> {self.time} UTC</span><br>
                        <b>{PlanetClient.getInstance().item_types_names()[self.properties[ITEM_TYPE]]}</b><br>
                        <span style="{SUBTEXT_STYLE}">{metadata}</span>
                    """

        return text

    def name(self):
        return (
            f"{self.date} {self.time} |"
            f" {PlanetClient.getInstance().item_types_names()[self.properties[ITEM_TYPE]]}"
        )

    def scene_thumbnails(self):
        return [self.thumbnail]

    def set_checked(self, checked):
        if self.downloadable:
            self.checkBox.setChecked(checked)
