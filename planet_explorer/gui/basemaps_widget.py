import os
import math
import json
import iso8601

from collections import defaultdict

from PyQt5.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QApplication,
    QCheckBox,
    QFrame,
    QToolButton,
    QAction,
    QMenu
)

from PyQt5.QtGui import (
    QPixmap,
    QIcon,
    QImage,
    QCursor,
    QPalette,
    QColor,
)

from PyQt5.QtNetwork import (
    QNetworkAccessManager,
    QNetworkRequest
)

from PyQt5 import QtCore

from PyQt5.QtCore import (
    QUrl,
    Qt,
    pyqtSignal,
    QCoreApplication,
    QThread,
    QObject,
    QSize,
    QEvent
)

from planet.api.models import (
    Mosaics,
    MosaicQuads
)

from planet_explorer.pe_utils import (
    ITEM_BACKGROUND_COLOR
)

from qgis.core import (
    QgsRasterLayer,
    QgsProject,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsWkbTypes,
    QgsGeometry,
    QgsDistanceArea,
    QgsRectangle,
    QgsUnitTypes
)

from qgis.gui import(
    QgsRubberBand
)

from qgis.utils import iface
from qgis.PyQt import uic

from ..planet_api import (
    PlanetClient
)

from ..planet_api.quad_orders import (
    create_quad_order_from_quads
)

from ..planet_api.p_node import (
    PLACEHOLDER_THUMB
)

from .pe_filters import (
    PlanetMainFilters
)

from ..pe_utils import (
    QUADS_AOI_COLOR,
    QUADS_AOI_BODY_COLOR,
    NAME,
    LINKS,
    TILES,
    FIRST_ACQUIRED,    
    ONEMONTH,
    THREEMONTHS,
    WEEK,
    INTERVAL,
    qgsrectangle_for_canvas_from_4326_bbox_coords,
    add_xyz,
    add_mosaics_to_qgis_project,
    mosaic_title,
    date_interval_from_mosaics,
    add_menu_section_action
)

from .pe_gui_utils import (
    waitcursor
)

from .pe_orders_monitor_dockwidget import (
    show_orders_monitor,
    refresh_orders
)

from .extended_combobox import ExtendedComboBox

ID = "id"
SERIES = "series"
THUMB = "thumb"
THUMBNAIL = "thumbnail"
PERCENT_COVERED = "percent_covered"
BBOX = "bbox"

QUADS_PER_PAGE = 50

MAX_QUADS_TO_DOWNLOAD = 100


plugin_path = os.path.split(os.path.dirname(__file__))[0]
WIDGET, BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'basemaps_widget.ui'),
    from_imports=True, import_from=os.path.basename(plugin_path),
    resource_suffix=''
)

COG_ICON = QIcon(':/plugins/planet_explorer/cog.svg')

class BasemapsWidget(BASE, WIDGET):

    def __init__(self, parent):
        super(BasemapsWidget, self).__init__(parent)

        self.parent = parent

        self.p_client = PlanetClient.getInstance()

        self._series = None
        self._initialized = False

        self.oneoff = None

        self.setupUi(self)

        self.comboSeriesName = ExtendedComboBox()
        self.comboSeriesName.lineEdit().setPlaceholderText("Select a basemap series or type to filter")
        self.grpBoxFilter.layout().addWidget(self.comboSeriesName, 0, 1)

        self.mosaicsList = BasemapsListWidget()
        self.frameResults.layout().addWidget(self.mosaicsList)
        self.mosaicsList.setVisible(False)
        self.mosaicsList.basemapsSelectionChanged.connect(self.selection_changed)

        self.quadsTree = QuadsTreeWidget()
        self.quadsTree.quadsSelectionChanged.connect(self.quads_selection_changed)
        self.grpBoxQuads.layout().addWidget(self.quadsTree)

        self.aoi_filter = PlanetMainFilters(iface, self, self.parent, 
                                            True, QUADS_AOI_COLOR)        
        self.grpBoxAOI.layout().addWidget(self.aoi_filter)

        self.radioDownloadComplete.setChecked(True)

        self.buttons = [self.btnOneOff, self.btnQuaterly, 
                        self.btnMonthly, self.btnWeekly, 
                        self.btnAll]

        self.btnOneOff.clicked.connect(lambda: self.btn_filter_clicked(self.btnOneOff))
        self.btnQuaterly.clicked.connect(lambda: self.btn_filter_clicked(self.btnQuaterly))
        self.btnMonthly.clicked.connect(lambda: self.btn_filter_clicked(self.btnMonthly))
        self.btnWeekly.clicked.connect(lambda: self.btn_filter_clicked(self.btnWeekly))        
        self.btnAll.clicked.connect(lambda: self.btn_filter_clicked(self.btnAll))

        self.btnOrder.clicked.connect(self.order)
        self.btnExplore.clicked.connect(self.explore)

        self.btnNextOrderMethodPage.clicked.connect(self.next_order_method_page_clicked)
        self.btnBackOrderMethodPage.clicked.connect(
                lambda: self.stackedWidget.setCurrentWidget(self.searchPage))
        self.btnBackAOIPage.clicked.connect(self.back_aoi_page_clicked)
        self.btnBackNamePage.clicked.connect(self.back_name_page_clicked)
        self.btnBackStreamingPage.clicked.connect(self.back_streaming_page_clicked)
        self.btnBackQuadsPage.clicked.connect(self.back_quads_page_clicked)
        self.btnNextQuadsPage.clicked.connect(self.next_quads_page_clicked)
        self.btnFindQuads.clicked.connect(self.find_quads_clicked)
        self.btnSubmitOrder.clicked.connect(self.submit_button_clicked)
        self.btnCloseConfirmation.clicked.connect(self.close_aoi_page)
        self.btnSubmitOrderStreaming.clicked.connect(self.submit_streaming_button_clicked)
        self.chkMinZoomLevel.stateChanged.connect(self.min_zoom_level_checked)
        self.chkMaxZoomLevel.stateChanged.connect(self.max_zoom_level_checked)

        levels = [str(x) for x in range(19)]
        self.comboMinZoomLevel.addItems(levels)
        self.comboMaxZoomLevel.addItems(levels)
        self.comboMaxZoomLevel.setCurrentIndex(len(levels) - 1)

        self.textBrowserOrderConfirmation.setOpenExternalLinks(False)
        self.textBrowserOrderConfirmation.anchorClicked.connect(show_orders_monitor)

        self.comboSeriesName.currentIndexChanged.connect(self.serie_selected)

        self.grpBoxFilter.collapsedStateChanged.connect(self.collapse_state_changed)

        self.chkSelectAll.stateChanged.connect(self.select_all)
        self.chkSelectAllQuads.stateChanged.connect(self.select_all_quads)

    def init(self):
        if not self._initialized:
            self.stackedWidget.setCurrentWidget(self.searchPage)
            self.btnAll.setChecked(True)
            self.btn_filter_clicked(self.btnAll)
            self._initialized = True

    def select_all(self):
        self.mosaicsList.setAllChecked(self.chkSelectAll.isChecked())

    def select_all_quads(self):
        self.quadsTree.setAllChecked(self.chkSelectAllQuads.isChecked())

    def collapse_state_changed(self, collapsed):
        if not collapsed:
            self.set_filter_visibility()

    def set_filter_visibility(self):
        is_one_off = self.btnOneOff.isChecked()
        self.grpBoxFilter.setVisible(not is_one_off)

    def btn_filter_clicked(self, selectedbtn):
        for btn in self.buttons:
            if btn != selectedbtn:
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.setEnabled(True)
                btn.blockSignals(False)
            selectedbtn.setEnabled(False)
        self.populate(selectedbtn)

    @waitcursor
    def series(self):
        if self._series is None:
            self._series = self.p_client.list_mosaic_series().get()[SERIES]          
        return self._series
    
    def populate(self, category_btn = None):
        category_btn = category_btn or self.btnAll
        
        self.set_filter_visibility()
        
        self.comboSeriesName.clear()
        self.comboSeriesName.addItem("", None)
        self.chkSelectAll.setChecked(False)
        self.btnOrder.setText("Order (0 instances)")
        if category_btn == self.btnAll:
            series = self.series()
        elif category_btn == self.btnMonthly:
            series = self.series_for_interval(ONEMONTH)
        elif category_btn == self.btnQuaterly:
            series = self.series_for_interval(THREEMONTHS)
        elif category_btn == self.btnWeekly:
            series = self.series_for_interval(WEEK)
        elif category_btn == self.btnOneOff:
            mosaics = self.one_off_mosaics()             
            self.mosaicsList.populate(mosaics)
            self.lblSelectBasemapName.setVisible(False)
            self.mosaicsList.setVisible(True)
        if category_btn != self.btnOneOff:            
            for s in series:
                self.comboSeriesName.addItem(s[NAME], s)                

    def min_zoom_level_checked(self):
        self.comboMinZoomLevel.setEnabled(self.chkMinZoomLevel.isChecked())

    def max_zoom_level_checked(self):
        self.comboMaxZoomLevel.setEnabled(self.chkMaxZoomLevel.isChecked())

    @waitcursor
    def one_off_mosaics(self):
        if self.oneoff is None:
            series_mosaics = {}
            series_mosaic_ids = []
            series = self.p_client.list_mosaic_series().get()[SERIES]
            mosaics = []
            for serie in series:
                response = self.p_client.get_mosaics_for_series(serie[ID])
                for page in response.iter():
                    mosaics.extend(page.get().get(Mosaics.ITEM_KEY))
                series_mosaics[serie[ID]] = mosaics
                series_mosaic_ids.extend([m[ID] for m in mosaics])
            all_mosaics = []            
            response = self.p_client.get_mosaics()
            for page in response.iter():
                all_mosaics.extend(page.get().get(Mosaics.ITEM_KEY))
            
            self.oneoff = [m for m in all_mosaics if m[ID] not in series_mosaic_ids]

        return self.oneoff
        

    def series_for_interval(self, interval):
        series = []
        for s in self.series():
            interv = s.get(INTERVAL)
            if interv == interval:
                series.append(s)
        return series

    @waitcursor
    def mosaics_for_serie(self, serie):        
        mosaics = self.p_client.get_mosaics_for_series(serie[ID])
        all_mosaics = []
        for page in mosaics.iter():
            all_mosaics.extend(page.get().get(Mosaics.ITEM_KEY))        
        return all_mosaics

    def serie_selected(self):
        self.mosaicsList.clear()
        series = self.comboSeriesName.currentData()
        self.lblSelectBasemapName.setVisible(series is None)
        self.mosaicsList.setVisible(series is not None)
        if series:
            mosaics = self.mosaics_for_serie(series)
            self.mosaicsList.populate(mosaics)            

    def selection_changed(self):
        selected = self.mosaicsList.selected_mosaics()
        n = len(selected)
        self.btnOrder.setText(f'Order ({n} items)')

    def quads_selection_changed(self):
        selected = self.quadsTree.selected_quads()
        n = len(selected)
        total = self.quadsTree.quads_count()
        self.labelQuadsSelected.setText(f'{n}/{total} quads selected')

    def _check_has_items_checked(self):
        selected = self.mosaicsList.selected_mosaics()
        if selected:
            if self.btnOneOff.isChecked() and len(selected) > 1:
                self.parent.show_message(f'Only one single serie can be selected in "one off" mode.',
                              level=Qgis.Warning,
                              duration=10)
                return False
            else:
                return True
        else:
            self.parent.show_message(f'No checked items to order',
                              level=Qgis.Warning,
                              duration=10)
            return False

    def explore(self):
        if self._check_has_items_checked():
            selected = self.mosaicsList.selected_mosaics()        
            add_mosaics_to_qgis_project(selected, self.comboSeriesName.currentText())

    def order(self):
        if self._check_has_items_checked():
            self.stackedWidget.setCurrentWidget(self.orderMethodPage)

    def next_order_method_page_clicked(self):
        if self.radioDownloadComplete.isChecked():
            mosaics = self.mosaicsList.selected_mosaics()
            quad = self.p_client.get_one_quad(mosaics[0])
            quadarea = self._area_from_bbox_coords(quad[BBOX])
            mosaicarea = self._area_from_bbox_coords(mosaics[0][BBOX])
            numquads = int(mosaicarea / quadarea)
            if numquads > MAX_QUADS_TO_DOWNLOAD:
                self.parent.show_message('Basemap is too large for complete download.',
                                          level=Qgis.Warning,
                                          duration=10)
                return
            self.show_order_name_page()
        elif self.radioDownloadAOI.isChecked():
            self.labelWarningQuads.setText("")
            self.widgetProgressFindQuads.setVisible(False)       
            self.stackedWidget.setCurrentWidget(self.orderAOIPage)
        elif self.radioStreaming.isChecked():
            self.show_order_streaming_page()            

    def find_quads_clicked(self):
        self.find_quads()

    @waitcursor
    def find_quads(self):
        selected = self.mosaicsList.selected_mosaics()
        if not self.aoi_filter.leAOI.text():
            self.labelWarningQuads.setText('⚠️ No area of interest (AOI) defined')
            return
        self.labelWarningQuads.setText("")
        self.widgetProgressFindQuads.setVisible(True)        
        geom = self.aoi_filter.aoi_geom()
        quad = self.p_client.get_one_quad(selected[0])
        quadarea = self._area_from_bbox_coords(quad[BBOX])
        qgsarea = QgsDistanceArea()
        area = qgsarea.convertAreaMeasurement(qgsarea.measureArea(geom), 
                                        QgsUnitTypes.AreaSquareKilometers)
        numpages = math.ceil(area / quadarea / QUADS_PER_PAGE)

        self.progressBarInstances.setMaximum(len(selected))
        self.progressBarQuads.setMaximum(numpages)
        self.objThread = QThread()
        self.finder = QuadFinder()
        self.finder.setup(self.p_client, selected, geom)
        
        #self.finder.moveToThread(self.objThread)
        self.finder.finished.connect(self.objThread.quit)
        self.finder.finished.connect(self._populate_quads)
        self.finder.mosaicStarted.connect(self._mosaic_started)
        self.finder.pageRead.connect(self._page_read)
        #self.objThread.started.connect(self.finder.find_quads)
        #self.objThread.start()
        self.finder.find_quads()
        
    def _mosaic_started(self, i, name):
        self.labelProgressInstances.setText(f"Processing basemap '{name}' " 
                            f"({i}/{self.progressBarInstances.maximum()})")
        self.progressBarInstances.setValue(i)
        QApplication.processEvents()

    def _page_read(self, i):
        total = self.progressBarQuads.maximum()
        self.labelProgressQuads.setText(f"Downloading quads (page {i} of an estimated total of {total})")
        self.progressBarQuads.setValue(i)
        QApplication.processEvents()
        
    def _populate_quads(self, quads):
        selected = self.mosaicsList.selected_mosaics()
        self.quadsTree.populate(selected, quads)
        total_quads = self.quadsTree.quads_count()
        self.labelQuadsSummary.setText(
            f'{total_quads} quads from {len(selected)} basemap instances '
            'intersect your AOI for this basemap')
        self.chkSelectAllQuads.setChecked(True)
        self.select_all_quads()
        self.quads_selection_changed()
        self.widgetProgressFindQuads.setVisible(False)
        self.stackedWidget.setCurrentWidget(self.orderQuadsPage) 

    def next_quads_page_clicked(self):
        selected = self.quadsTree.selected_quads()
        if selected:            
            self.show_order_name_page()            
        else:
            self.parent.show_message(f'No checked quads to order',
                              level=Qgis.Warning,
                              duration=10) 

    def back_quads_page_clicked(self):
        self.quadsTree.clear()
        self.stackedWidget.setCurrentWidget(self.orderAOIPage)

    def show_order_streaming_page(self):
        selected = self.mosaicsList.selected_mosaics()
        name = selected[0][NAME]
        dates = date_interval_from_mosaics(selected)
        description = (f'<span style="color:black;"><b>{name}</b></span><br>'
                            f'<span style="color:grey;">{len(selected)} instances | {dates}</span>')
        self.labelStreamingOrderDescription.setText(description)
        iconurl = selected[0][LINKS][THUMB]
        self.set_summary_icon(iconurl)
        self.chkMinZoomLevel.setChecked(False)
        self.chkMaxZoomLevel.setChecked(False)
        self.comboMinZoomLevel.setEnabled(False)
        self.comboMaxZoomLevel.setEnabled(False)
        self.stackedWidget.setCurrentWidget(self.orderStreamingPage)

    def _quads_summary(self):
        selected = self.mosaicsList.selected_mosaics()
        dates = date_interval_from_mosaics(selected)
        selected_quads = self.quadsTree.selected_quads()
        return f"{len(selected_quads)} quads | {dates}"

    def _quads_quota(self):
        selected_quads = self.quadsTree.selected_quads()
        total_area = 0
        for quad in selected_quads:            
            total_area += self._area_from_bbox_coords(quad[BBOX])
        return total_area


    def _area_from_bbox_coords(self, bbox):
        qgsarea = QgsDistanceArea()
        extent = QgsRectangle(*bbox)
        geom = QgsGeometry.fromRect(extent)
        area = qgsarea.convertAreaMeasurement(qgsarea.measureArea(geom), 
                                                    QgsUnitTypes.AreaSquareKilometers)
        return area

    def show_order_name_page(self):
        QUAD_SIZE = 1
        selected = self.mosaicsList.selected_mosaics()
        if not self.btnOneOff.isChecked():
            name = self.comboSeriesName.currentText()
        else:
            name = selected[0][NAME]
        dates = date_interval_from_mosaics(selected)
        if self.radioDownloadComplete.isChecked():
            description = (f'<span style="color:black;"><b>{name}</b></span><br>'
                            f'<span style="color:grey;">{len(selected)} instances | {dates}</span>') 
            
            title = "Order Complete Basemap"            
            total_area = self._area_from_bbox_coords(selected[0][BBOX]) * len(selected)
            quad = self.p_client.get_one_quad(selected[0])
            quadarea = self._area_from_bbox_coords(quad[BBOX])            
            numquads = total_area / quadarea
        elif self.radioDownloadAOI.isChecked():
            selected_quads = self.quadsTree.selected_quads()
            numquads = len(selected_quads)
            title = "Order Partial Basemap"
            description = (f'<span style="color:black;"><b>{name}</b></span><br>'
                            f'<span style="color:grey;">{self._quads_summary()}</span>')            
            total_area = self._quads_quota()
            
        iconurl = selected[0][LINKS][THUMB]
        self.set_summary_icon(iconurl)
        self.labelOrderDescription.setText(description)
        self.grpBoxNamePage.setTitle(title)
        self.stackedWidget.setCurrentWidget(self.orderNamePage)
        self.txtOrderName.setText("")         
        quota = self.p_client.user_quota_remaining()
        size = numquads * QUAD_SIZE
        if quota is not None:
            self.labelOrderInfo.setText(f"This Order will use {total_area:.2f} square km"
                                        f" of your remaining {quota} quota.\n\n"
                                        f"This Order's download size will be approximately {size} GB.")
            self.labelOrderInfo.setVisible(True)
        else:
            self.labelOrderInfo.setVisible(False)

    def set_summary_icon(self, iconurl):
        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self.iconDownloaded)
        self.nam.get(QNetworkRequest(QUrl(iconurl)))

    def iconDownloaded(self, reply):
        img = QImage()
        img.loadFromData(reply.readAll())
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                            QtCore.Qt.SmoothTransformation)
        if self.radioStreaming.isChecked():
            self.labelStreamingOrderIcon.setPixmap(thumb)
        else:
            self.labelOrderIcon.setPixmap(thumb)

    def back_streaming_page_clicked(self):
        self.stackedWidget.setCurrentWidget(self.orderMethodPage)

    def back_name_page_clicked(self):
        if self.radioDownloadComplete.isChecked():
            self.stackedWidget.setCurrentWidget(self.orderMethodPage)
        elif self.radioDownloadAOI.isChecked():
            self.quadsTree.show_footprints()
            self.stackedWidget.setCurrentWidget(self.orderQuadsPage)

    def back_aoi_page_clicked(self):
        self.stackedWidget.setCurrentWidget(self.orderMethodPage)
        self.aoi_filter.reset_aoi_box()

    def submit_streaming_button_clicked(self):
        selected = self.mosaicsList.selected_mosaics()        
        zmin = self.comboMinZoomLevel.currentText() if self.chkMinZoomLevel.isChecked() else 0
        zmax = self.comboMaxZoomLevel.currentText() if self.chkMaxZoomLevel.isChecked() else 18
        for mosaic in selected:
            name = f"{self.comboSeriesName.currentText()} - {mosaic_title(mosaic)}"
            add_xyz(name, mosaic[LINKS][TILES], zmin, zmax)
        selected = self.mosaicsList.selected_mosaics()
        base_html= ("<p>Your Connection(s) have been established</p>")        
        self.grpBoxOrderConfirmation.setTitle("Order Streaming Download")
        dates = date_interval_from_mosaics(selected)       
        description = f'{len(selected)} | {dates}'
        values = {"Series Name": self.comboSeriesName.currentText(),
                    "Series Instances": description}
        self.set_order_confirmation_summary(values, base_html)
        self.stackedWidget.setCurrentWidget(self.orderConfirmationPage)


    def submit_button_clicked(self):        
        name = self.txtOrderName.text()
        if not bool(name.strip()):
            self.parent.show_message(f'Enter a name for the order',
                              level=Qgis.Warning,
                              duration=10)
            return
        if self.radioDownloadComplete.isChecked():
            self.order_complete_submit()
        elif self.radioDownloadAOI.isChecked():
            self.order_partial_submit()

    def set_order_confirmation_summary(self, values, base_html=None):
        html = base_html or ("<p>Your order has been successfully submitted for processing."
                "You may monitor its progress and availability in the <a href='#'>Order Status panel</a>.</p>")
        html += "<p><table>"
        for k,v in values.items():
            html += f"<tr><td>{k}</td><td><b>{v}</b></td></tr>"
        html += "</table>"
        self.textBrowserOrderConfirmation.setHtml(html)
    
    @waitcursor
    def order_complete_submit(self):
        selected = self.mosaicsList.selected_mosaics() 
        name = self.txtOrderName.text()
        load_as_virtual = self.chkLoadAsVirtualLayer.isChecked()

        all_quads = {}
        numquads = 0
        for mosaic in selected:                                   
            json_quads = []
            quads = self.p_client.get_quads_for_mosaic(mosaic)         
            for page in quads.iter():
                json_quads.extend(page.get().get(MosaicQuads.ITEM_KEY))
            all_quads[mosaic[NAME]] = json_quads
            numquads += len(json_quads)

        self.grpBoxOrderConfirmation.setTitle("Order Complete Download")
        dates = date_interval_from_mosaics(selected)        
        description = f'{numquads} quads | {dates}'
        create_quad_order_from_quads(name, description, all_quads, load_as_virtual)
        refresh_orders()
        values = {"Order Name": self.txtOrderName.text(),
                    "Series Name": self.comboSeriesName.currentText(),
                    "Series Instances": description}
        self.set_order_confirmation_summary(values)
        self.stackedWidget.setCurrentWidget(self.orderConfirmationPage)

    def order_partial_submit(self):
        self.grpBoxOrderConfirmation.setTitle("Order Partial Download")
        mosaics = self.mosaicsList.selected_mosaics()
        dates = date_interval_from_mosaics(mosaics)        
        quads = self.quadsTree.selected_quads_classified()
        name = self.txtOrderName.text()
        load_as_virtual = self.chkLoadAsVirtualLayer.isChecked()
        description = f'{len(self.quadsTree.selected_quads())} quads | {dates}'
        create_quad_order_from_quads(name, description, quads, load_as_virtual)
        refresh_orders()
        values = {"Order Name": self.txtOrderName.text(),
                    "Series Name": self.comboSeriesName.currentText(),
                    "Quads": self._quads_summary(),
                    "Quota": self._quads_quota()}
        self.set_order_confirmation_summary(values)
        self.quadsTree.clear()
        self.stackedWidget.setCurrentWidget(self.orderConfirmationPage)

    def close_aoi_page(self):
        self.aoi_filter.reset_aoi_box()
        self.quadsTree.clear()
        self.stackedWidget.setCurrentWidget(self.searchPage)

        
class QuadsTreeWidget(QTreeWidget):

    quadsSelectionChanged = pyqtSignal()

    def __init__(self):
        QTreeWidget.__init__(self, None)
        self.setColumnCount(1)
        self.header().hide()        
        self.setAutoScroll(True)
        self.setMouseTracking(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(self.NoSelection)
        self.widgets = {}

    
    def quad_widgets(self):
        all_widgets = []
        for widgets in self.widgets.values():
            all_widgets.extend(widgets)
        return all_widgets

    def clear(self):
        for w in self.quad_widgets():
            w.remove_footprint()
        self.widgets = {}
        super().clear()

    def show_footprints(self):        
        for w in self.quad_widgets():
            w.show_footprint()

    def hide_footprints(self):        
        for w in self.quad_widgets():
            w.hide_footprint()    

    def quads_count(self):
        return len(self.quad_widgets())

    def selected_quads(self):
        selected = []
        for widgets in self.widgets.values():
            selected.extend([w.quad for w in widgets if w.isSelected()])
        return selected

    def selected_quads_classified(self):
        selected = {}
        for mosaic, widgets in self.widgets.items():
            selected[mosaic] = [w.quad for w in widgets if w.isSelected()]
        return selected

    def setAllChecked(self, checked):
        for w in self.quad_widgets():
            w.setChecked(checked)

    def populate(self, mosaics, quads):
        self.clear()
        for mosaic, mosaicquads in zip(mosaics, quads):
            item = BasemapTreeItem(mosaic)            
            self.addTopLevelItem(item)
            widgets = []
            for quad in mosaicquads:
                subitem = QuadTreeItem(quad)
                item.addChild(subitem)
                widget = QuadItemWidget(quad)
                self.setItemWidget(subitem, 0, widget)
                subitem.setSizeHint(0, widget.sizeHint())
                widget.quadSelected.connect(self._quad_selection_changed)
                widgets.append(widget)
            self.widgets[mosaic.get(NAME)] = widgets
            item.update_name()

    def _quad_selection_changed(self):
        self.quadsSelectionChanged.emit()
        for i in range(self.topLevelItemCount()):
            self.topLevelItem(i).update_name()

class BasemapTreeItem(QTreeWidgetItem):

    def __init__(self, mosaic):
        QTreeWidgetItem.__init__(self)
        self.mosaic = mosaic
        font = self.font(0)
        font.setBold(True)
        self.setFont(0, font)
        self.update_name()

    def update_name(self):
        selected = 0
        total = self.childCount()
        for i in range(total):
            if self.treeWidget().itemWidget(self.child(i), 0).isSelected():
                selected += 1
        self.setText(0, f"{mosaic_title(self.mosaic)} - {selected} of {total} selected")

class QuadTreeItem(QTreeWidgetItem):

    def __init__(self, quad):
        QTreeWidgetItem.__init__(self)
        self.quad = quad

class QuadItemWidget(QFrame):

    quadSelected = pyqtSignal()

    def __init__(self, quad):
        QWidget.__init__(self)
        self.setMouseTracking(True)
        self.quad = quad
        self.nameLabel = QLabel(f'<b>{quad[ID]}</b><br><span style="color:grey;">'
                            f'{quad[PERCENT_COVERED]} % covered</span>')
        self.iconLabel = QLabel()
        pixmap = QPixmap(PLACEHOLDER_THUMB, 'SVG')
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                            QtCore.Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.checkBox = QCheckBox("")
        self.checkBox.stateChanged.connect(self.checkBoxstateChanged)
        layout = QHBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.checkBox)
        vlayout = QVBoxLayout()
        vlayout.setMargin(0)
        vlayout.addWidget(self.iconLabel)
        self.iconWidget = QWidget()
        self.iconWidget.setFixedSize(48, 48)
        self.iconWidget.setLayout(vlayout)
        layout.addWidget(self.iconWidget)        
        layout.addWidget(self.nameLabel)
        layout.addStretch()
        self.setLayout(layout)
        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self.iconDownloaded)
        self.nam.get(QNetworkRequest(QUrl(quad[LINKS][THUMBNAIL])))
        self.footprint = QgsRubberBand(iface.mapCanvas(),
                              QgsWkbTypes.PolygonGeometry)        
        self.footprint.setFillColor(QUADS_AOI_COLOR)
        self.footprint.setStrokeColor(QUADS_AOI_COLOR)
        self.footprint.setWidth(2)

        self.footprintfill = QgsRubberBand(iface.mapCanvas(),
                              QgsWkbTypes.PolygonGeometry)        
        self.footprintfill.setFillColor(QUADS_AOI_BODY_COLOR)        
        self.footprintfill.setWidth(0)

        self.update_footprint_brush()
        self.hide_solid_interior()
        self.show_footprint()

        self.setStyleSheet("QuadItemWidget{border: 2px solid transparent;}")

    def checkBoxstateChanged(self):
        self.update_footprint_brush()
        self.quadSelected.emit()        

    def show_footprint(self):
        coords = self.quad[BBOX]
        extent = qgsrectangle_for_canvas_from_4326_bbox_coords(coords)      
        self.geom = QgsGeometry.fromRect(extent)        
        self.footprint.setToGeometry(self.geom)
        self.footprintfill.setToGeometry(self.geom)

    def hide_footprint(self):
        self.footprint.reset(QgsWkbTypes.PolygonGeometry)
        self.footprintfill.reset(QgsWkbTypes.PolygonGeometry)

    def show_solid_interior(self):                        
        self.footprintfill.setBrushStyle(Qt.SolidPattern)        
        self.footprintfill.updateCanvas()

    def hide_solid_interior(self):
        self.footprintfill.setBrushStyle(Qt.NoBrush)
        self.footprintfill.updateCanvas()
    
    def update_footprint_brush(self):
        self.footprint.setBrushStyle(Qt.CrossPattern if self.checkBox.isChecked() else Qt.NoBrush)
        self.footprint.updateCanvas()

    def remove_footprint(self):
        iface.mapCanvas().scene().removeItem(self.footprint)
        iface.mapCanvas().scene().removeItem(self.footprintfill)
        
    def iconDownloaded(self, reply):
        img = QImage()
        img.loadFromData(reply.readAll())
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                            QtCore.Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.iconLabel.setStyleSheet("")

    def isSelected(self):
        return self.checkBox.isChecked()

    def setChecked(self, checked):
        self.checkBox.setChecked(checked)

    def enterEvent(self, event):
        self.setStyleSheet("QuadItemWidget{border: 2px solid rgb(157, 165, 0);}")
        self.show_solid_interior()

    def leaveEvent(self, event):
        self.setStyleSheet("QuadItemWidget{border: 2px solid transparent;}")
        self.hide_solid_interior()

class BasemapsListWidget(QListWidget):

    basemapsSelectionChanged = pyqtSignal()

    def __init__(self):
        QListWidget.__init__(self, None)
        self.setAutoScroll(True)
        self.setSortingEnabled(True) 
        self.setAlternatingRowColors(True)
        p = self.palette()
        p.setColor(QPalette.Highlight, ITEM_BACKGROUND_COLOR)
        self.setPalette(p)
        self.widgets = []

    def clear(self):
        self.widgets = []
        super().clear()

    def populate(self, mosaics):              
        self.widgets = []
        for mosaic in mosaics[::-1]:                
            item = BasemapListItem(mosaic)
            self.addItem(item)
            widget = BasemapItemWidget(mosaic)
            self.setItemWidget(item, widget)
            widget.setMaximumWidth(self.width())
            widget.setFixedWidth(self.width())
            item.setSizeHint(widget.sizeHint())
            widget.basemapSelected.connect(self.basemapsSelectionChanged.emit)
            self.widgets.append(widget)
        
        self.sortItems()

    def resizeEvent(self, evt):
        super().resizeEvent(evt)
        for widget in self.widgets:
            widget.setMaximumWidth(self.width())
            widget.setFixedWidth(self.width())

    def selected_mosaics(self):
        return sorted([w.mosaic for w in self.widgets if w.isSelected()], 
                        key=lambda x: x[FIRST_ACQUIRED])

    def setAllChecked(self, checked):
        for w in self.widgets:
            w.setChecked(checked)
        
class BasemapListItem(QListWidgetItem):

    def __init__(self, mosaic):
        QListWidgetItem.__init__(self)
        self.mosaic = mosaic
        self.enabled = TILES in mosaic[LINKS]

    def __lt__(self, other):
        if isinstance(other, BasemapListItem):
            return self.mosaic[FIRST_ACQUIRED] < other.mosaic[FIRST_ACQUIRED]
        else:
            return True        

class BasemapItemWidget(QWidget):

    basemapSelected = pyqtSignal()

    def __init__(self, mosaic):
        QWidget.__init__(self)
        self.mosaic = mosaic
        available = TILES in mosaic[LINKS]
        color = "black" if available else "grey"        
        title = mosaic_title(mosaic)
        self.nameLabel = QLabel(f'<span style="color:{color};"><b>{title}</b></span>'
                            f'<br><span style="color:grey;">{mosaic[NAME]}</span>')        
        self.iconLabel = QLabel()
        self.toolsButton = QLabel()
        self.toolsButton.setPixmap(COG_ICON.pixmap(QSize(18, 18)))
        self.toolsButton.mousePressEvent = self.showContextMenu

        pixmap = QPixmap(PLACEHOLDER_THUMB, 'SVG')
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                            QtCore.Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)
        self.checkBox = QCheckBox("")
        self.checkBox.setEnabled(available)
        self.checkBox.stateChanged.connect(self.basemapSelected.emit)
        layout = QHBoxLayout()
        layout.setMargin(2)
        layout.addWidget(self.checkBox)
        vlayout = QVBoxLayout()
        vlayout.setMargin(0)
        vlayout.addWidget(self.iconLabel)
        self.iconWidget = QWidget()
        self.iconWidget.setFixedSize(48, 48)
        self.iconWidget.setLayout(vlayout)
        layout.addWidget(self.iconWidget)
        layout.addWidget(self.nameLabel)
        layout.addStretch()
        layout.addWidget(self.toolsButton)
        layout.addSpacing(10)
        self.setLayout(layout)
        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self.iconDownloaded)
        self.nam.get(QNetworkRequest(QUrl(mosaic[LINKS][THUMB])))
        
    def showContextMenu(self, evt):
        menu = QMenu()
        add_menu_section_action('Current item', menu)
        zoom_act = QAction('Zoom to extent', menu)        
        zoom_act.triggered.connect(self.zoom_to_extent)
        menu.addAction(zoom_act)
        menu.exec_(self.toolsButton.mapToGlobal(evt.pos()))

    def zoom_to_extent(self):
        rect = qgsrectangle_for_canvas_from_4326_bbox_coords(self.mosaic[BBOX])
        rect.scale(1.05)
        iface.mapCanvas().setExtent(rect)
        iface.mapCanvas().refresh()

    def iconDownloaded(self, reply):
        img = QImage()
        img.loadFromData(reply.readAll())
        pixmap = QPixmap(img)
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                            QtCore.Qt.SmoothTransformation)
        self.iconLabel.setPixmap(thumb)

    def isSelected(self):
        return self.checkBox.isChecked()

    def setChecked(self, checked):
        self.checkBox.setChecked(checked)

class QuadFinder(QObject):

    finished = pyqtSignal(list)
    pageRead = pyqtSignal(int)
    mosaicStarted = pyqtSignal(int, str)

    def setup(self, client, mosaics, geom):
        self.client = client
        self.mosaics = mosaics
        self.geom = geom

    def find_quads(self):
        all_quads = []
        bbox_rect = self.geom.boundingBox()
        bbox = [bbox_rect.xMinimum(), bbox_rect.yMinimum(),
                bbox_rect.xMaximum(), bbox_rect.yMaximum()]
        for i, mosaic in enumerate(self.mosaics):            
            self.mosaicStarted.emit(i + 1, mosaic.get(NAME))                                    
            json_quads = []
            self.pageRead.emit(1)
            quads = self.client.get_quads_for_mosaic(mosaic, bbox)            
            for j, page in enumerate(quads.iter()):
                json_quads.extend(page.get().get(MosaicQuads.ITEM_KEY))
                self.pageRead.emit(j + 2)
            all_quads.append(json_quads)
        self.finished.emit(all_quads)