# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_thumbnails.py
    ---------------------
    Date                 : September 2019
    Author               : Planet Federal
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
__date__ = 'September 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import logging
import json
import base64

from functools import partial
from typing import (
    Optional,
    Union,
    List,
)

# noinspection PyPackageRequirements
from requests import Response as ReqResponse
# noinspection PyPackageRequirements
from requests.auth import HTTPBasicAuth

# noinspection PyPackageRequirements
from qgis.PyQt.QtCore import (
    pyqtSignal,
    pyqtSlot,
    QObject,
    QSize,
)

from qgis.PyQt.QtGui import (
    QImage,
    # QPixmap,
)

from qgis.core import (
    QgsProject,
    QgsRectangle,
    # QgsGeometry,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsMapSettings,
    QgsRasterLayer,
    # QgsMapRendererQImageJob,
    QgsMapRendererParallelJob,
    # QgsMapRendererSequentialJob
)

from planet.api.client import ClientV1
from planet.api import models as api_models

try:
    from ..planet_api.p_client import (
        PlanetClient,
        TILE_SERVICE_URL,
    )

    from ..planet_api.p_node import (
        # PlanetNode,
        PlanetNodeType,
    )

    from ..planet_api.p_thumnails import (
        PlanetRenderJob,
        THUMB_EXT,
        TEMP_CACHE_DIR,
    )

    from ..planet_api.p_network import (
        PlanetCallbackWatcher,
        dispatch_callback,
        RESPONSE_TIMEOUT,
        requests_response_metadata,
    )

    from ..pe_network import (
        JsonDownloadHandler,
    )

    from ..pe_utils import (
        tile_service_data_src_uri,
        qgsgeometry_from_geojson,
    )
except ImportError:
    from planet_explorer.planet_api.p_client import (
        PlanetClient,
        TILE_SERVICE_URL,
    )

    from planet_explorer.planet_api.p_node import (
        # PlanetNode,
        PlanetNodeType,
    )

    from planet_explorer.planet_api.p_thumnails import (
        PlanetRenderJob,
        THUMB_EXT,
        TEMP_CACHE_DIR,
    )

    from planet_explorer.planet_api.p_network import (
        PlanetCallbackWatcher,
        dispatch_callback,
        RESPONSE_TIMEOUT,
        requests_response_metadata,
    )

    from planet_explorer.pe_network import (
        JsonDownloadHandler,
    )

    from planet_explorer.pe_utils import (
        tile_service_data_src_uri,
        qgsgeometry_from_geojson,
    )

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
LOG_VERBOSE = os.environ.get('PYTHON_LOG_VERBOSE', None)

USE_JSON_HANDLER = True


class PlanetQgisRenderJob(PlanetRenderJob):
    """
    Generic wrapper class for QGIS isolated map renderer jobs
    """

    fetchShouldCancel = pyqtSignal()

    # Base class for parallel and sequential jobs
    # _job: Type[QgsMapRendererQImageJob]
    _job: Optional[QgsMapRendererParallelJob]

    def __init__(self, item_key: str,
                 api_key: str,
                 extent_json: Optional[Union[str, dict]] = None,
                 dest_crs: Optional[str] = 'EPSG:3857',
                 item_id: Optional[str] = None,
                 item_type: Optional[str] = None,
                 item_type_ids: Optional[List[str]] = None,
                 item_properties: Optional[dict] = None,
                 node_type: Optional[PlanetNodeType] = None,
                 image_url: Optional[str] = None,
                 width: int = 256,
                 height: int = 256,
                 api_client: Optional[ClientV1] = None,
                 cache_dir: Optional[str] = None,
                 parent: Optional[QObject] = None):

        super().__init__(parent=parent)

        self._id = self._item_key = item_key
        self._api_key = api_key
        self._extent_json = extent_json
        self._dest_crs = dest_crs

        self._item_id = item_id
        self._item_type = item_type
        self._item_type_ids = item_type_ids
        self._item_properties = item_properties
        self._node_type = node_type
        self._image_url = image_url
        self._width = width
        self._height = height

        self._job = None
        self._has_job = False
        self._rlayer: Optional[QgsRasterLayer] = None

        self._tile_hash = None

        self._json_handler = JsonDownloadHandler()
        self._json_handler.aborted.connect(self._json_aborted)
        self._json_handler.errored.connect(self._json_errored)
        # connect 'finished' signal on a need-as basis

        self._api_client = api_client
        self._cache_dir = cache_dir

        self._watcher = PlanetCallbackWatcher(
            parent=self, timeout=RESPONSE_TIMEOUT)
        # self._watcher.responseRegistered.connect(self._some_slot)
        self._watcher.responseCancelled.connect(self._json_cancelled)
        self._watcher.responseTimedOut[int].connect(self._json_timed_out)
        self._watcher.responseFinished['PyQt_PyObject'].connect(
            self._json_tile_hash_finished_wbody)
        self.fetchShouldCancel.connect(self._watcher.cancel_response)

    def id(self) -> str:
        return self._id

    def has_job(self):
        return self._has_job

    @pyqtSlot()
    def start(self) -> None:
        if not self._api_key:
            log.debug('No API key, skip fetching tile hash')
            return None

        if not self._item_type_ids:
            log.debug('No item type:ids passed, skip fetching tile hash')
            return None

        # item_type_ids_reverse = list(self._item_type_ids)
        # item_type_ids_reverse.reverse()
        # data = {'ids': item_type_ids_reverse}
        data = {'ids': self._item_type_ids[::-1]}
        json_data = json.dumps(data)
        if LOG_VERBOSE:
            log.debug(f'json_data: {json_data}')

        tile_url = TILE_SERVICE_URL.format('')

        if USE_JSON_HANDLER:

            headers = dict()
            headers['Content-Type'] = 'application/json'
            bauth = bytes(f'{self._api_key}:', encoding='ascii')
            # auth = 'Basic {0}'.format(base64.b64encode(bauth))
            # headers['Authorization'] = f'Basic {self._api_key}:'
            base64_auth = base64.b64encode(bauth).decode("ascii")
            # headers['Authorization'] = f'api-key {base64_auth}'
            headers['Authorization'] = f'Basic {base64_auth}'

            self._json_handler.finished.connect(self._json_tile_hash_finished)

            self._json_handler.post(
                tile_url,
                headers,
                data=json_data,
            )
        else:  # use async dispatcher

            auth = HTTPBasicAuth(self._api_key, '')
            self._api_client.dispatcher.session.auth = auth

            resp = self._api_client.dispatcher.response(
                api_models.Request(
                    tile_url,
                    self._api_client.auth,
                    # None,
                    body_type=api_models.JSON,
                    method='POST',
                    data=json_data,
                )
            )

            resp.get_body_async(
                handler=partial(dispatch_callback, watcher=self._watcher))

            self._watcher.register_response(resp)

    @pyqtSlot()
    def _start_job(self):

        map_settings = None

        if self._node_type:
            log.debug(f'Rendering image for node type: {self._node_type}')

        # Not sure why this needs to be a string comparison, instead of enum
        if f'{self._node_type}' == 'PlanetNodeType.DAILY_SCENE':

            if not self._item_type_ids:
                log.debug('No item type_id keys list object passed')
                return
            if LOG_VERBOSE:
                log.debug(f'item_type_ids:\n{self._item_type_ids}')

            if not self._extent_json:
                log.debug('Extent is invalid')
                return
            if LOG_VERBOSE:
                log.debug(f'extent_json:\n{self._extent_json}')

            if not self._api_key:
                log.debug('No API in passed')
                return

            if self._width <= 0 or self._height <= 0:
                log.debug('Invalid output width or height')
                return

            log.debug(f'Starting render map setup for {self._item_key}')

            # noinspection PyArgumentList
            # p = QgsProject.instance()

            data_src_uri = tile_service_data_src_uri(
                self._item_type_ids, self._api_key, tile_hash=self._tile_hash)
            log.debug(f'Render data_src_uri:\n'
                      f'{data_src_uri}')

            if not data_src_uri:
                log.debug('Invalid data source URI returned')
                return

            self._rlayer: QgsRasterLayer = \
                QgsRasterLayer(data_src_uri, self._item_key, "wms")

            if not self._rlayer.isValid():
                log.debug('Render layer is not valid')
                return

            # p.addMapLayer(rlayer, False)

            ext: QgsRectangle = \
                qgsgeometry_from_geojson(self._extent_json).boundingBox()

            if ext.isEmpty():
                log.debug('Extent bounding box is empty or null')
                return

            if ext.width() > ext.height():
                self._height = int(ext.height() / ext.width() * self._height)
            elif ext.height() > ext.width():
                self._width = int(ext.width() / ext.height() * self._width)

            # noinspection PyArgumentList
            transform = QgsCoordinateTransform(
                QgsCoordinateReferenceSystem('EPSG:4326'),
                QgsCoordinateReferenceSystem(self._dest_crs),
                QgsProject.instance())

            transform_extent = transform.transformBoundingBox(ext)

            if transform_extent.isEmpty():
                log.debug('Transformed extent bounding box is empty or null')
                return

            map_settings = QgsMapSettings()
            map_settings.setExtent(transform_extent)
            map_settings.setOutputSize(QSize(self._width, self._height))
            map_settings.setLayers([self._rlayer])

            log.debug(f'QgsMapSettings set for {self._item_key}')

        if map_settings is not None:

            self._job = QgsMapRendererParallelJob(map_settings)

            # noinspection PyUnresolvedReferences
            self._job.finished.connect(self._job_finished)

            self._has_job = True

            log.debug(f'Render job initialized for {self._item_key}')
        else:
            log.debug(f'No render job initialized for {self._item_key}')

        self._job.start()

    @pyqtSlot()
    @pyqtSlot(str)
    def cancel(self, item_key: Optional[str] = None) -> None:
        self.fetchShouldCancel.emit()

        if self._job:
            self._job.cancelWithoutBlocking()
            log.debug('Job cancelled (without blocking)')
            # self.jobFinished.emit(None)
            # self.jobFinishedWithId.emit(self._id, None)
        else:
            log.debug('No job to cancel')

        # self._job = None
        # self._has_job = False
        self.jobCancelled.emit()
        if item_key and item_key != self._id:
            return
        self.jobCancelledWithId.emit(self._id)

    @pyqtSlot('PyQt_PyObject')
    def _json_tile_hash_finished_wbody(self, body: api_models.JSON):

        fetch = 'Render job JSON tile hash fetch'
        log.debug(f'{fetch} finished')

        if body is None or not hasattr(body, 'response'):
            log.debug(f'{fetch} failed: no response')
            return

        resp: ReqResponse = body.response
        log.debug(requests_response_metadata(resp))

        if not resp.ok:
            log.debug(f'{fetch} failed: response not ok')
            return

        json_body = body.get()
        if 'name' in json_body:
            log.debug(f'{fetch} succeeded')
            self._tile_hash = json_body['name']
            self._start_job()
        else:
            log.debug(f'{fetch} failed')
            return

    @pyqtSlot()
    def _json_tile_hash_finished(self):
        log.debug(f'Render job JSON tile hash fetch finished')
        self._json_handler.finished.disconnect(self._json_tile_hash_finished)

        json_body = self._json_handler.json
        if 'name' in json_body:
            log.debug(f'Render job JSON tile hash fetch succeeded')
            self._tile_hash = json_body['name']
            self._start_job()
        else:
            log.debug(f'Render job JSON tile hash fetch failed')
            return

    @pyqtSlot()
    def _json_cancelled(self):
        log.debug(f'Render job JSON fetch cancelled')
        self.jobCancelled.emit()
        self.jobCancelledWithId.emit(self._id)

    @pyqtSlot()
    def _json_aborted(self):
        log.debug(f'Render job JSON fetch aborted')
        self.jobCancelled.emit()
        self.jobCancelledWithId.emit(self._id)

    @pyqtSlot()
    def _json_errored(self):
        log.debug(f'Render job JSON fetch errored')
        self.jobCancelled.emit()
        self.jobCancelledWithId.emit(self._id)

    @pyqtSlot()
    def _json_timed_out(self) -> None:
        log.debug(f'Render job JSON fetch timed out')
        self.jobTimedOut.emit()
        self.jobTimedOutWithId.emit(self._id)

    @pyqtSlot()
    def _job_finished(self):

        log.debug(f'Job rendering time (seconds): '
                  f'{self._job.renderingTime() / 1000}')

        item_path = None

        if self._job:
            img: QImage = self._job.renderedImage()
            if not img.isNull():

                # TODO: Composite (centered) over top of full width/height
                #       Image is unlikely to be square at this point, after
                #       being clipped to transformed AOI bounding box.
                #
                #       Or, do this as a standard operation in
                #       PlanetThumbnailCache._thumbnail_job_finished()?

                cache_dir = self._cache_dir
                if f'{self._node_type}' in [
                    'PlanetNodeType.DAILY_SCENE',
                ]:
                    # Don't pollute user-defined cache with ephemeral thumbs
                    cache_dir = TEMP_CACHE_DIR

                # Write .png image to cache directory
                item_path = os.path.join(cache_dir, f'{self._id}{THUMB_EXT}')

                if os.path.exists(item_path):
                    log.debug(f'Removing existing job at:\n{item_path}')
                    os.remove(item_path)

                log.debug(f'Saving thumbnail job to:\n{item_path}')
                img.save(item_path, 'PNG')
            else:
                log.debug('Rendered QImage is null')

        self.jobFinished.emit()
        self.jobFinishedWithId.emit(self._id, item_path)

    def create_job(*args, **kwargs):
        """Job factory for PlanetThumbnailCache"""
        return PlanetQgisRenderJob(*args, **kwargs)
