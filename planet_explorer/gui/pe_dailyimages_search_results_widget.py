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
import logging
import iso8601

from qgis.PyQt import uic

from qgis.PyQt.QtCore import (
    pyqtSignal,
    pyqtSlot,
    Qt,
    QSize,
    QUrl,
    QThread
)

from qgis.PyQt.QtGui import (
    QIcon,
    QColor,
    QPixmap,
    QImage
)

from qgis.PyQt.QtWidgets import (
    QAction,
    QLabel,
    QFrame,
    QMenu,
    QListWidgetItem,
    QCheckBox,
    QHBoxLayout,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QFileDialog
)

from PyQt5.QtNetwork import (
    QNetworkAccessManager,
    QNetworkRequest
)

from qgis.core import (
    QgsGeometry,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsWkbTypes,
    QgsRectangle
)

from qgis.gui import (
    QgsRubberBand
)

from qgis.utils import(
    iface
)

plugin_path = os.path.split(os.path.dirname(__file__))[0]

from ..gui.pe_save_search_dialog import SaveSearchDialog

from ..gui.pe_results_configuration_dialog import (
    ResultsConfigurationDialog,
    PlanetNodeMetadata
)

from ..pe_utils import (
    qgsgeometry_from_geojson,
    add_menu_section_action,
    zoom_canvas_to_geometry,
    create_preview_group,
    SEARCH_AOI_COLOR,
    PLANET_COLOR
)

from ..planet_api.p_client import (
    PlanetClient
)

from ..planet_api.p_utils import (
    geometry_from_request,
)
from ..planet_api.p_specs import (
    DAILY_ITEM_TYPES_DICT,
    ITEM_ASSET_DL_REGEX
) 

from .pe_gui_utils import (
    waitcursor
)

from .pe_thumbnails import(
    createCompoundThumbnail
)

TOP_ITEMS_BATCH = 250
CHILD_COUNT_THRESHOLD_FOR_PREVIEW = 500

ID = "id"
SATELLITE_ID = "satellite_id"
PROPERTIES = "properties"
GEOMETRY = "geometry"
ITEM_TYPE = "item_type"
PERMISSIONS = "_permissions"

SUBTEXT_STYLE = 'color: rgb(100,100,100);'
SUBTEXT_STYLE_WITH_NEW_CHILDREN = 'color: rgb(157,0,165);'

COG_ICON = QIcon(':/plugins/planet_explorer/cog.svg')
LOCK_ICON = QIcon(':/plugins/planet_explorer/lock-light.svg')
PLACEHOLDER_THUMB = ':/plugins/planet_explorer/thumb-placeholder-128.svg'

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

RESULTS_WIDGET, RESULTS_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'pe_search_results_base.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)

class DailyImagesSearchResultsWidget(RESULTS_BASE, RESULTS_WIDGET):

    zoomToAOIRequested = pyqtSignal()
    setAOIRequested = pyqtSignal(dict)
    checkedCountChanged = pyqtSignal(int)
    searchSaved = pyqtSignal(dict)

    SORT_ORDER_DATE_TYPES = [
        ('acquired', 'Acquired'),
        ('published', 'Published'),
        # ('updated', 'Updated'),
    ]

    SORT_ORDER_TYPES = [
        ('desc', 'descending'),
        ('asc', 'ascending'),
    ]

    def __init__(self):
        super().__init__()

        self.setupUi(self)

        self._p_client = PlanetClient.getInstance()

        self._has_more = True

        self._metadata_to_show = [PlanetNodeMetadata.CLOUD_PERCENTAGE, 
                                  PlanetNodeMetadata.GROUND_SAMPLE_DISTANCE]

        self._image_count = 0
        self._total_count = 0

        self._request = None
        self._response_iterator = None

        self.btnZoomToAOI.clicked.connect(self._zoom_to_request_aoi)
        self.btnSaveSearch.clicked.connect(self._save_search)
        self.btnSettings.clicked.connect(self._open_settings)
        self.lblImageCount.setOpenExternalLinks(False)
        self.lblImageCount.linkActivated.connect(self.load_more_link_clicked)

        self._aoi_box = None
        self._setup_request_aoi_box()

        self.cmbBoxDateType.clear()
        for i, (a, b) in enumerate(self.SORT_ORDER_DATE_TYPES):
            self.cmbBoxDateType.insertItem(i, b, userData=a)
        self.cmbBoxDateType.setCurrentIndex(0)
        self.cmbBoxDateType.currentIndexChanged.connect(self._sort_order_changed)

        self.cmbBoxDateSort.clear()
        for i, (a, b) in enumerate(self.SORT_ORDER_TYPES):
            self.cmbBoxDateSort.insertItem(i, b, userData=a)
        self.cmbBoxDateSort.setCurrentIndex(0)
        self.cmbBoxDateSort.currentIndexChanged.connect(self._sort_order_changed)

        self._set_widgets_visibility(False)

    def _set_widgets_visibility(self, search_ok):
        self.tree.setVisible(search_ok)
        self.widgetActions.setVisible(search_ok)
        self.widgetNoResults.setVisible(not search_ok)

    def search_has_been_performed(self):
        return self._request is not None

    def _open_settings(self):
        settings = self._metadata_to_show
        dlg = ResultsConfigurationDialog(self._metadata_to_show)
        if dlg.exec_():
            self._metadata_to_show = dlg.selection
            self.update_image_items()

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
            self.searchSaved.emit(dlg.request_to_save)

    def sort_order(self):
        return (
            str(self.cmbBoxDateType.currentData()),
            str(self.cmbBoxDateSort.currentData())
        )

    def _sort_order_changed(self, idx):  
        self.update_request(self._request)

    def load_more_link_clicked(self):
        self.load_more()

    @waitcursor
    def update_request(self, request):
        self._image_count = 0
        self._request = request
        self.tree.clear()   
        stats_request = {"interval": "year"}
        stats_request.update(self._request)
        resp = self._p_client.stats(stats_request).get()
        self._total_count = sum([b["count"] for b in resp["buckets"]])
        if self._total_count:
            response = self._p_client.quick_search(
                self._request,
                page_size=TOP_ITEMS_BATCH,
                sort=' '.join(self.sort_order())                
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
            self._image_count += len(images)
            for image in images:
                sort_criteria = self.cmbBoxDateType.currentData()                
                date_item, satellite_item = self._find_items_for_satellite(image)
                date_widget = self.tree.itemWidget(date_item, 0)
                satellite_widget = self.tree.itemWidget(satellite_item, 0)
                item = SceneItem(image, sort_criteria)
                widget = SceneItemWidget(image, sort_criteria, self._metadata_to_show, item)
                widget.checkedStateChanged.connect(self.checked_count_changed)
                widget.checkedStateChanged.connect(satellite_widget.update_checkbox)
                widget.thumbnailChanged.connect(satellite_widget.update_thumbnail)
                item.setSizeHint(0, widget.sizeHint())
                satellite_item.addChild(item)
                self.tree.setItemWidget(item, 0, widget)
                date_widget.update_for_children()

            for i in range(self.tree.topLevelItemCount()):
                date_item = self.tree.topLevelItem(i)
                date_widget = self.tree.itemWidget(date_item, 0)
                for j in range(date_item.childCount()):
                    satellite_item = date_item.child(j)
                    satellite_widget = self.tree.itemWidget(satellite_item, 0)
                    satellite_widget.update_for_children()
                    satellite_item.sortChildren(0, Qt.AscendingOrder)
                date_widget.update_for_children()
            self.item_count_changed()
        else:
            self._has_more = False
            self.item_count_changed()

    def _find_item_for_date(self, image):
        sort_criteria = self.cmbBoxDateType.currentData()
        date = iso8601.parse_date(image[PROPERTIES][sort_criteria]).date() 
        itemtype = image[PROPERTIES][ITEM_TYPE]
        count = self.tree.topLevelItemCount()
        for i in range(count):
            child = self.tree.topLevelItem(i)
            if child.date == date and child.itemtype == itemtype:
                return child
        date_item = DateItem(image, sort_criteria)
        widget = DateItemWidget(image, sort_criteria, date_item)
        date_item.setSizeHint(0, widget.sizeHint())
        self.tree.addTopLevelItem(date_item)
        self.tree.setItemWidget(date_item, 0, widget)
        return date_item        

    def _find_items_for_satellite(self, image):
        date_item = self._find_item_for_date(image)
        date_widget = self.tree.itemWidget(date_item, 0)
        satellite = image[PROPERTIES][SATELLITE_ID]
        count = date_item.childCount()
        for i in range(count):
            child = date_item.child(i)
            if child.satellite == satellite:
                return date_item, child
        satellite_item = SatelliteItem(satellite)
        widget = SatelliteItemWidget(satellite, satellite_item)
        widget.checkedStateChanged.connect(date_widget.update_checkbox)
        widget.thumbnailChanged.connect(date_widget.update_thumbnail)
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
        self.checkedCountChanged.emit(len(self.selected_images()))

    def item_count_changed(self):
        if self._has_more:
            self.lblImageCount.setText(
                f"{self._image_count} of {self._total_count} images. <a href='#'>Load more</a>")
        else:
            self.lblImageCount.setText(
                f"{self._image_count} of {self._total_count} images")

    def _setup_request_aoi_box(self):
        self._aoi_box = QgsRubberBand(
            iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
        self._aoi_box.setFillColor(QColor(0, 0, 0, 0))
        self._aoi_box.setStrokeColor(SEARCH_AOI_COLOR)
        self._aoi_box.setWidth(2)
        self._aoi_box.setLineStyle(Qt.DashLine)

    @pyqtSlot()
    def clear_aoi_box(self):
        if self._aoi_box:
            self._aoi_box.reset(QgsWkbTypes.PolygonGeometry)

    @pyqtSlot()
    def _zoom_to_request_aoi(self):
        aoi_geom = geometry_from_request(self._request)

        geom: QgsGeometry = qgsgeometry_from_geojson(aoi_geom)
        self._aoi_box.setToGeometry(
            geom,
            QgsCoordinateReferenceSystem("EPSG:4326")
        )        

        zoom_canvas_to_geometry(geom)

    def clean_up(self):
        self.clear_aoi_box()

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
        self.checkBox = QCheckBox("")
        self.checkBox.stateChanged.connect(self.check_box_state_changed)
        self.nameLabel = QLabel(text)        
        self.iconLabel = QLabel()
        self.toolsButton = QLabel()
        self.toolsButton.setPixmap(COG_ICON.pixmap(QSize(18, 18)))
        self.toolsButton.mousePressEvent = self.show_context_menu

        layout = QHBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.checkBox)
        pixmap = QPixmap(PLACEHOLDER_THUMB, 'SVG')
        self.thumbnail = None
        thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio, 
                            Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.iconLabel.setFixedSize(48, 48)         
        layout.addWidget(self.iconLabel)
        if thumbnailurl is not None:
            self.nam = QNetworkAccessManager()
            self.nam.finished.connect(self.iconDownloaded)            
            self.nam.get(QNetworkRequest(QUrl(thumbnailurl)))        
        layout.addWidget(self.nameLabel)
        layout.addStretch()
        layout.addWidget(self.toolsButton)
        layout.addSpacing(10)
        self.setLayout(layout)

        self.footprint = QgsRubberBand(iface.mapCanvas(),
                              QgsWkbTypes.PolygonGeometry)        
        self.footprint.setStrokeColor(PLANET_COLOR)
        self.footprint.setWidth(2)

    def is_selected(self):
        return self.checkBox.isChecked()

    def _geom_bbox_in_project_crs(self):
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().crs(),
            QgsProject.instance()
        )        
        return transform.transformBoundingBox(self.geom.boundingBox())

    def _geom_in_project_crs(self):
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().crs(),
            QgsProject.instance()
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
    
    def zoom_to_extent(self):
        rect = QgsRectangle(self._geom_bbox_in_project_crs())
        rect.scale(1.05)
        iface.mapCanvas().setExtent(rect)
        iface.mapCanvas().refresh()

    def show_context_menu(self, evt):
        menu = self._context_menu()
        menu.exec_(self.toolsButton.mapToGlobal(evt.pos()))

    def _context_menu(self):
        menu = QMenu()
        add_menu_section_action('Current item', menu)
        zoom_act = QAction('Zoom to extent', menu)
        zoom_act.triggered.connect(self.zoom_to_extent)
        menu.addAction(zoom_act)
        prev_layer_act = QAction('Add preview layers to map (footprints as memory layer)', menu)
        prev_layer_act.triggered.connect(self._add_preview_memory_clicked)
        menu.addAction(prev_layer_act)
        prev_layer_act = QAction('Add preview layer to map(footprints as gpkg layer)', menu)        
        prev_layer_act.triggered.connect(self._add_preview_gpkg_clicked)
        menu.addAction(prev_layer_act)        
        if self.item.childCount() > CHILD_COUNT_THRESHOLD_FOR_PREVIEW:
            prev_layer_act.setEnabled(False)
            prev_layer_act.setToolTip("The node contains too many images to preview")
            menu.setToolTipsVisible(True)
        return menu

    def _add_preview_gpkg_clicked(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Footprints layer filename", "", '*.gpkg')
        if filename:
            self.add_preview(filename)

    def _add_preview_memory_clicked(self):
        self.add_preview(None)

    @waitcursor
    def add_preview(self, footprints_filename):
        create_preview_group(
            self.name(), 
            self.item.images(),
            footprints_filename,
            tile_service='xyz'
        )

    def iconDownloaded(self, reply):
        img = QImage()
        img.loadFromData(reply.readAll())
        self.thumbnail = QPixmap(img)
        thumb = self.thumbnail.scaled(48, 48, Qt.KeepAspectRatio, 
                            Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.thumbnailChanged.emit()

    def check_box_state_changed(self):
        self.checkedStateChanged.emit()        
        self.is_updating_checkbox = True
        total = self.item.childCount()
        if self.checkBox.isTristate():
            self.checkBox.setTristate(False)            
            self.checkBox.setChecked(False)
        else:
            for i in range(total):
                w = self.item.treeWidget().itemWidget(self.item.child(i), 0)
                w.set_checked(self.checkBox.isChecked())
        self.is_updating_checkbox = False            

    def update_checkbox(self):
        if self.is_updating_checkbox:
            return
        selected = 0
        total = self.item.childCount()
        for i in range(total):
            w = self.item.treeWidget().itemWidget(self.item.child(i), 0)
            if w.is_selected():
                selected += 1
        self.checkBox.blockSignals(True)
        if selected == total:
            self.checkBox.setTristate(False)
            self.checkBox.setCheckState(Qt.Checked)
        elif selected == 0:
            self.checkBox.setTristate(False)
            self.checkBox.setCheckState(Qt.Unchecked)
        else:
            self.checkBox.setTristate(True)
            self.checkBox.setCheckState(Qt.PartiallyChecked)
        self.checkBox.blockSignals(False)
        self.checkedStateChanged.emit()

    def set_checked(self, checked):                
        self.checkBox.setChecked(checked)

    def update_thumbnail(self):
        bbox = self.geom.boundingBox()

        item_ids = [f"{img[PROPERTIES][ITEM_TYPE]}:{img[ID]}" for img in self.item.images()]

        thumbnails =self.scene_thumbnails()
        bboxes = [img[GEOMETRY] for img in self.item.images()]

        if thumbnails and None not in thumbnails:
            pixmap = createCompoundThumbnail(bboxes, thumbnails)
            thumb = pixmap.scaled(48, 48, Qt.KeepAspectRatio, 
                            Qt.SmoothTransformation)
            self.iconLabel.setPixmap(thumb)
            self.thumbnailChanged.emit()


    def scene_thumbnails(self):                
        thumbnails = []
        for i in range(self.item.childCount()):
            w = self.item.treeWidget().itemWidget(self.item.child(i), 0)
            thumbnails.extend(w.scene_thumbnails())
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
        self.date = datetime.strftime('%b %d, %Y')

        self._setup_ui("", None)
        self.update_for_children()

    def update_for_children(self):
        size = 0
        ids = []
        for i in range(self.item.childCount()):
            child = self.item.child(i)
            size += child.childCount()            
        count_style = SUBTEXT_STYLE if not self.has_new else SUBTEXT_STYLE_WITH_NEW_CHILDREN
        self.children_count = size   
        text = f"""{self.date}<br>
                    <b>{DAILY_ITEM_TYPES_DICT[self.properties[ITEM_TYPE]]}</b><br>                    
                    <span style="{count_style}">{size} images</span>"""
        self.nameLabel.setText(text)

        geoms = []
        for i in range(self.item.childCount()):
            child = self.item.child(i)
            geoms.append(self.item.treeWidget().itemWidget(child, 0).geom)
        self.geom = QgsGeometry.collectGeometry(geoms)
        #self._update_thumbnail()

    def name(self):
        return f"{self.date} | {DAILY_ITEM_TYPES_DICT[self.properties[ITEM_TYPE]]}"

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

    def __init__(self, satellite, item):
        ItemWidgetBase.__init__(self, item)
        self.has_new = True
        self.satellite = satellite        
        self._setup_ui("", None)
        self.update_for_children()

    def update_for_children(self):
        size = self.item.childCount()
        count_style = SUBTEXT_STYLE if not self.has_new else SUBTEXT_STYLE_WITH_NEW_CHILDREN
        self.children_count = size
        text = f'''<span style="{SUBTEXT_STYLE}"> Satellite {self.satellite}</span>
                    <span style="{count_style}">({size} images)</span>'''
        self.nameLabel.setText(text)

        geoms = []
        self.ids = []
        for i in range(size):
            child = self.item.child(i)
            geoms.append(self.item.treeWidget().itemWidget(child, 0).geom)
            self.ids.append(child.image[ID])
        self.geom = QgsGeometry.collectGeometry(geoms) 
        #self._update_thumbnail()      

    def name(self):
        return f"Satellite {self.satellite}"

class SceneItem(QTreeWidgetItem):

    def __init__(self, image, sort_criteria):
        QListWidgetItem.__init__(self)
        self.image = image
        self.date = iso8601.parse_date(image[PROPERTIES][sort_criteria])

    def __lt__( self, other ):
        if (not isinstance(other, SceneItem)):
            return super(SceneItem, self).__lt__(other)

        return self.date < other.date

    def images(self):
        return [self.image]

class SceneItemWidget(ItemWidgetBase):

    def __init__(self, image, sort_criteria, metadata_to_show, item):
        ItemWidgetBase.__init__(self, item)
        self.image = image        
        self.metadata_to_show = metadata_to_show
        self.properties = image[PROPERTIES]

        datetime = iso8601.parse_date(self.properties[sort_criteria])
        self.time = datetime.strftime('%H:%M:%S')
        self.date = datetime.strftime('%b %d, %Y')
        
        text = self._get_text()
        url = f"{image['_links']['thumbnail']}?api_key={PlanetClient.getInstance().api_key()}"
        
        self._setup_ui(text, url)

        permissions = image[PERMISSIONS]
        if len(permissions) == 0:
            self.downloadable = False
        else:
            matches = [ITEM_ASSET_DL_REGEX.match(s) is not None
                       for s in permissions]
            self.downloadable = any(matches)

        self.checkBox.setEnabled(self.downloadable)
        self.geom = qgsgeometry_from_geojson(image[GEOMETRY])

    def set_metadata_to_show(self, metadata_to_show):
        self.metadata_to_show = metadata_to_show
        self.update_text()

    def update_text(self):
        self.nameLabel.setText(self._get_text())

    def _get_text(self):
        metadata = ""
        for i, value in enumerate(self.metadata_to_show):
            spacer = "<br>" if i == 1 else " "                
            metadata += f'{value.value}:{self.properties.get(value.value, "--")}{spacer}'          
            
        text = f"""{self.date}<span style="color: rgb(100,100,100);"> {self.time} UTC</span><br>
                        <b>{DAILY_ITEM_TYPES_DICT[self.properties[ITEM_TYPE]]}</b><br>
                        <span style="{SUBTEXT_STYLE}">{metadata}</span>
                    """

        return text

    def _context_menu(self):
        menu = super()._context_menu()

        #TODO
        return menu

    def name(self):
        return f"{self.date} {self.time} | {DAILY_ITEM_TYPES_DICT[self.properties[ITEM_TYPE]]}"

    def scene_thumbnails(self):  
        return [self.thumbnail]

