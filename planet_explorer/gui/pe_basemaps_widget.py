# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_basemaps_widget.py
    ---------------------
    Date                 : August 2020
    Author               : Planet Federal
    Copyright            : (C) 2017 Boundless, http://boundlessgeo.com
                         : (C) 2019 Planet Inc, https://planet.com
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
__date__ = 'August 2020'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import math

from PyQt5.QtWidgets import (
    QApplication,
    QMessageBox,
    QVBoxLayout
)

from PyQt5.QtGui import (
    QPixmap,
    QImage,
)

from PyQt5.QtNetwork import (
    QNetworkAccessManager,
    QNetworkRequest
)

from PyQt5 import QtCore

from PyQt5.QtCore import (
    QUrl,
    pyqtSignal,
    QThread,
    QObject
)

from planet.api.models import (
    Mosaics,
    MosaicQuads
)


from qgis.core import (
    Qgis,
    QgsGeometry,
    QgsDistanceArea,
    QgsRectangle,
    QgsUnitTypes
)

from qgis.utils import iface
from qgis.PyQt import uic

from ..planet_api import (
    PlanetClient
)

from ..planet_api.p_quad_orders import (
    create_quad_order_from_quads,
    create_quad_order_from_mosaics
)

from .pe_filters import (
    PlanetMainFilters
)

from ..pe_utils import (
    QUADS_AOI_COLOR,
    NAME,
    LINKS,
    ONEMONTH,
    THREEMONTHS,
    WEEK,
    INTERVAL,
    add_mosaics_to_qgis_project,
    mosaic_title,
    date_interval_from_mosaics,
    open_link_with_browser
)

from .pe_gui_utils import (
    waitcursor
)

from .pe_orders_monitor_dockwidget import (
    show_orders_monitor,
    refresh_orders
)

from .pe_quads_treewidget import QuadsTreeWidget
from .pe_basemaps_list_widget import BasemapsListWidget
from .pe_basemap_layer_widget import BasemapRenderingOptionsWidget

ID = "id"
SERIES = "series"
THUMB = "thumb"
BBOX = "bbox"
DATATYPE = "datatype"
PRODUCT_TYPE = "product_type"
TIMELAPSE = "timelapse"

QUADS_PER_PAGE = 50
MAX_QUADS_TO_DOWNLOAD = 100

PLACEHOLDER_THUMB = ':/plugins/planet_explorer/thumb-placeholder-128.svg'

plugin_path = os.path.split(os.path.dirname(__file__))[0]
WIDGET, BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'basemaps_widget.ui'),
    from_imports=True, import_from=os.path.basename(plugin_path),
    resource_suffix=''
)

class BasemapsWidget(BASE, WIDGET):

    def __init__(self, parent):
        super(BasemapsWidget, self).__init__(parent)

        self.parent = parent

        self.p_client = PlanetClient.getInstance()

        self._series = None
        self._initialized = False
        self._quads = None

        self.oneoff = None

        self.setupUi(self)

        self.mosaicsList = BasemapsListWidget()
        self.frameResults.layout().addWidget(self.mosaicsList)
        self.mosaicsList.setVisible(False)
        self.mosaicsList.basemapsSelectionChanged.connect(self.selection_changed)

        self.quadsTree = QuadsTreeWidget()
        self.quadsTree.quadsSelectionChanged.connect(self.quads_selection_changed)
        self.grpBoxQuads.layout().addWidget(self.quadsTree)

        self.renderingOptions = BasemapRenderingOptionsWidget()
        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.renderingOptions)
        self.frameRenderingOptions.setLayout(layout)

        self.aoi_filter = PlanetMainFilters(iface, self, self.parent,
                                            True, QUADS_AOI_COLOR)
        self.grpBoxAOI.layout().addWidget(self.aoi_filter)

        self.radioDownloadComplete.setChecked(True)

        self.buttons = [self.btnOneOff, self.btnSeries,
                        self.btnAll]

        self.btnOneOff.clicked.connect(lambda: self.btn_filter_clicked(self.btnOneOff))
        self.btnSeries.clicked.connect(lambda: self.btn_filter_clicked(self.btnSeries))
        self.btnAll.clicked.connect(lambda: self.btn_filter_clicked(self.btnAll))

        self.btnOrder.clicked.connect(self.order)
        self.btnExplore.clicked.connect(self.explore)
        self.btnCancelQuadSearch.clicked.connect(self.cancel_quad_search)

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
        self.lblSelectAllMosaics.linkActivated.connect(self.batch_select_mosaics_clicked)
        self.lblSelectAllQuads.linkActivated.connect(self.batch_select_quads_clicked)
        self.chkGroupByQuad.stateChanged.connect(self._populate_quads)
        self.chkOnlySRBasemaps.stateChanged.connect(self._only_sr_basemaps_changed)
        self.btnBasemapsFilter.clicked.connect(self._apply_filter)

        self.comboCadence.currentIndexChanged.connect(self.cadence_selected)

        self.textBrowserNoAccess.setOpenLinks(False)
        self.textBrowserNoAccess.setOpenExternalLinks(False)
        self.textBrowserNoAccess.anchorClicked.connect(self._open_basemaps_website)
        
    def _open_basemaps_website(self):
        open_link_with_browser("https://www.planet.com/purchase")

    def init(self):
        if not self._initialized:
            if PlanetClient.getInstance().has_access_to_mosaics():
                self.stackedWidget.setCurrentWidget(self.searchPage)
                self.btnSeries.setChecked(True)
                self.btn_filter_clicked(self.btnSeries)
                self._initialized = True
            else:
                self.stackedWidget.setCurrentWidget(self.noBasemapsAccessPage)
                self._initialized = True

    def reset(self):
        self._initialized = False

    def batch_select_mosaics_clicked(self, url="all"):
        checked = url == "all"
        self.mosaicsList.setAllChecked(checked)

    def batch_select_quads_clicked(self, url="all"):
        checked = url == "all"
        self.quadsTree.setAllChecked(checked)

    def collapse_state_changed(self, collapsed):
        if not collapsed:
            self.set_filter_visibility()

    def set_filter_visibility(self):
        is_one_off = self.btnOneOff.isChecked()
        if is_one_off:
            self.grpBoxFilter.setVisible(False)
            mosaics = self.one_off_mosaics()
            self.mosaicsList.populate(mosaics)
            self.mosaicsList.setVisible(True)
            self.toggle_select_basemap_panel(False)
        else:
            is_all = self.btnAll.isChecked()
            self.grpBoxFilter.setVisible(True)
            self.labelBasemapsFilter.setVisible(is_all)
            self.textBasemapsFilter.setVisible(is_all)
            self.btnBasemapsFilter.setVisible(is_all)
            self.labelCadence.setVisible(not is_all)
            self.comboCadence.setVisible(not is_all)
            self.comboSeriesName.clear()                        
            if is_all:
                self.textBasemapsFilter.setText("")
                self.comboSeriesName.addItem("Apply a filter to populate this list of series", None)
            else:
                cadences = set([s[INTERVAL] for s in self.series()])
                self.comboCadence.blockSignals(True)
                self.comboCadence.clear()
                self.comboCadence.addItem("All", None)
                for cadence in cadences:
                    self.comboCadence.addItem(cadence, cadence)
                self.comboCadence.blockSignals(False)
                self.cadence_selected()

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

    def _apply_filter(self):
        text = self.textBasemapsFilter.text()
        mosaics = self._get_filtered_mosaics(text) 
        series = self._get_filtered_series(text)
        if len(mosaics) == 0 and len(series) == 0:
            self.parent.show_message('No results for current filter',
                                      level=Qgis.Warning,
                                      duration=10)
            return
        self.comboSeriesName.clear()
        self.comboSeriesName.addItem("Select a series or mosaic", None)
        for m in mosaics:
            self.comboSeriesName.addItem(m[NAME], (m, False))
        self.comboSeriesName.insertSeparator(len(mosaics))
        for s in series:
            self.comboSeriesName.addItem(s[NAME], (s, True))

    def _get_filtered_mosaics(self, text):
        mosaics = []
        response = self.p_client.get_mosaics(text)
        for page in response.iter():
            mosaics.extend(page.get().get(Mosaics.ITEM_KEY))
        mosaics = [m for m in mosaics if m[PRODUCT_TYPE] != TIMELAPSE]
        return mosaics

    def _get_filtered_series(self, text):
         return self.p_client.list_mosaic_series(text).get()[SERIES]

    def _only_sr_basemaps_changed(self):
        self.mosaicsList.set_only_sr_basemaps(self.chkOnlySRBasemaps.isChecked())

    def cadence_selected(self):
        cadence = self.comboCadence.currentData()
        self.comboSeriesName.blockSignals(True)
        self.comboSeriesName.clear()
        self.comboSeriesName.addItem("Select a series", None)
        series = self.series_for_interval(cadence)
        for s in series:
            self.comboSeriesName.addItem(s[NAME], (s, True))
        self.comboSeriesName.blockSignals(False)
        self.toggle_select_basemap_panel(True)

    def populate(self, category_btn = None):
        category_btn = category_btn or self.btnAll

        self.mosaicsList.clear()
        self.btnOrder.setText("Order (0 instances)")
        self.set_filter_visibility()

        self.batch_select_mosaics_clicked("none")

    def toggle_select_basemap_panel(self, show):
        self.lblSelectBasemapName.setVisible(show)
        self.lblSelectAllMosaics.setVisible(not show)
        self.lblCheckInstances.setVisible(not show)
        self.mosaicsList.setVisible(not show)

    def min_zoom_level_checked(self):
        self.comboMinZoomLevel.setEnabled(self.chkMinZoomLevel.isChecked())

    def max_zoom_level_checked(self):
        self.comboMaxZoomLevel.setEnabled(self.chkMaxZoomLevel.isChecked())

    @waitcursor
    def one_off_mosaics(self):
        if self.oneoff is None:
            all_mosaics = []
            response = self.p_client.get_mosaics()
            for page in response.iter():
                all_mosaics.extend(page.get().get(Mosaics.ITEM_KEY))
            self.oneoff = [m for m in all_mosaics if m[PRODUCT_TYPE] != TIMELAPSE]

        return self.oneoff

    def series_for_interval(self, interval):
        series = []
        for s in self.series():
            interv = s.get(INTERVAL)
            if interv == interval or interval is None:
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
        data = self.comboSeriesName.currentData()
        self.toggle_select_basemap_panel(data is None)
        self.mosaicsList.setVisible(data is not None)
        if data:
            if data[1]: #it is a series, not a single mosaic
                mosaics = self.mosaics_for_serie(data[0])
            else:
                mosaics = [data[0]]
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
            add_mosaics_to_qgis_project(selected,
                    self.comboSeriesName.currentText() or selected[0][NAME])

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
                ret = QMessageBox.question(self, "Complete Download", 
                                    f"The download will contain more than {MAX_QUADS_TO_DOWNLOAD} quads.\n"
                                    "Are your sure you want to proceed?")
                if ret != QMessageBox.Yes:
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
        self.labelWarningQuads.setText("")
        selected = self.mosaicsList.selected_mosaics()
        if not self.aoi_filter.leAOI.text():
            self.labelWarningQuads.setText('⚠️ No area of interest (AOI) defined')
            return
        geom = self.aoi_filter.aoi_as_4326_geom()
        mosaic_extent = QgsRectangle(*selected[0][BBOX])
        if not geom.intersects(mosaic_extent):
            self.parent.show_message(f'No mosaics in the selected area',
                              level=Qgis.Warning,
                              duration=10) 
            return

        quad = self.p_client.get_one_quad(selected[0])
        quadarea = self._area_from_bbox_coords(quad[BBOX])
        qgsarea = QgsDistanceArea()
        area = qgsarea.convertAreaMeasurement(qgsarea.measureArea(geom),
                                        QgsUnitTypes.AreaSquareKilometers)
        numpages = math.ceil(area / quadarea / QUADS_PER_PAGE)

        self.widgetProgressFindQuads.setVisible(True)
        self.progressBarInstances.setMaximum(len(selected))
        self.progressBarQuads.setMaximum(numpages)
        self.finder = QuadFinder()
        self.finder.setup(self.p_client, selected, geom)

        self.objThread = QThread()
        self.finder.moveToThread(self.objThread)
        self.finder.finished.connect(self.objThread.quit)
        self.finder.finished.connect(self._update_quads)
        self.finder.mosaicStarted.connect(self._mosaic_started)
        self.finder.pageRead.connect(self._page_read)
        self.objThread.started.connect(self.finder.find_quads)
        self.objThread.start()

    def cancel_quad_search(self):
        self.finder.cancel()
        self.objThread.quit()
        self.widgetProgressFindQuads.setVisible(False)

    def _mosaic_started(self, i, name):
        self.labelProgressInstances.setText(f"Processing basemap '{name}' " 
                            f"({i}/{self.progressBarInstances.maximum()})")
        self.progressBarInstances.setValue(i)
        QApplication.processEvents()

    def _page_read(self, i):
        total = self.progressBarQuads.maximum()
        self.labelProgressQuads.setText(f"Downloading quad footprints (page {i} of (estimated) {total})")
        self.progressBarQuads.setValue(i)
        QApplication.processEvents()

    def _update_quads(self, quads):
        self._quads = quads
        self._populate_quads()

    def _populate_quads(self):
        selected = self.mosaicsList.selected_mosaics()
        if self.chkGroupByQuad.isChecked():
            self.quadsTree.populate_by_quad(selected, self._quads)
        else:
            self.quadsTree.populate_by_basemap(selected, self._quads)
        total_quads = self.quadsTree.quads_count()
        self.labelQuadsSummary.setText(
            f'{total_quads} quads from {len(selected)} basemap instances '
            'intersect your AOI for this basemap')
        self.batch_select_quads_clicked("all")
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
        pixmap = QPixmap(PLACEHOLDER_THUMB, 'SVG')
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation)
        self.labelStreamingOrderIcon.setPixmap(thumb)
        if THUMB in selected[0][LINKS]: 
            self.set_summary_icon(selected[0][LINKS][THUMB])
        self.chkMinZoomLevel.setChecked(False)
        self.chkMaxZoomLevel.setChecked(False)
        self.comboMinZoomLevel.setEnabled(False)
        self.comboMaxZoomLevel.setEnabled(False)
        self.renderingOptions.set_datatype(selected[0][DATATYPE])
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

        pixmap = QPixmap(PLACEHOLDER_THUMB, 'SVG')
        thumb = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, 
                        QtCore.Qt.SmoothTransformation)
        self.labelOrderIcon.setPixmap(thumb)
        if THUMB in selected[0][LINKS]: 
            self.set_summary_icon(selected[0][LINKS][THUMB])
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
        mosaicname = self.comboSeriesName.currentText() or selected[0][NAME]
        proc = self.renderingOptions.process()
        ramp = self.renderingOptions.ramp()
        for mosaic in selected:
            name = f"{mosaicname} - {mosaic_title(mosaic)}"
            add_mosaics_to_qgis_project([mosaic], name, proc=proc, ramp=ramp,
                                        zmin=zmin, zmax=zmax, add_xyz_server=True)
        selected = self.mosaicsList.selected_mosaics()
        base_html = ("<p>Your Connection(s) have been established</p>")
        self.grpBoxOrderConfirmation.setTitle("Order Streaming Download")
        dates = date_interval_from_mosaics(selected)
        description = f'{len(selected)} | {dates}'
        values = {"Series Name": mosaicname,
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

        self.grpBoxOrderConfirmation.setTitle("Order Complete Download")
        dates = date_interval_from_mosaics(selected)
        description = f'{len(selected)} complete mosaics | {dates}'
        create_quad_order_from_mosaics(name, description, selected, load_as_virtual)
        refresh_orders()
        values = {"Order Name": self.txtOrderName.text(),
                    "Series Name": self.comboSeriesName.currentText() or selected[0][NAME],
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
                    "Series Name": self.comboSeriesName.currentText() or mosaics[0][NAME],
                    "Quads": self._quads_summary(),
                    "Quota": self._quads_quota()}
        self.set_order_confirmation_summary(values)
        self.quadsTree.clear()
        self.stackedWidget.setCurrentWidget(self.orderConfirmationPage)

    def close_aoi_page(self):
        self.aoi_filter.reset_aoi_box()
        self.quadsTree.clear()
        self.stackedWidget.setCurrentWidget(self.searchPage)


class QuadFinder(QObject):

    finished = pyqtSignal(list)
    pageRead = pyqtSignal(int)
    mosaicStarted = pyqtSignal(int, str)

    def setup(self, client, mosaics, geom):
        self.client = client
        self.mosaics = mosaics
        self.geom = geom

    def find_quads(self):
        self.canceled = False
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
                if self.canceled:
                    return
            all_quads.append(json_quads)
        self.finished.emit(all_quads)

    def cancel(self):
        self.canceled = True
