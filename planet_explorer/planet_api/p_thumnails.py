# -*- coding: utf-8 -*-
"""
***************************************************************************
    p_thumbnails.py
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
import tempfile
# import pyproj
from osgeo import osr

from functools import partial
from typing import (
    Optional,
    Union,
    Tuple,
    List,
)

# noinspection PyPackageRequirements
# from PIL import Image

# noinspection PyPackageRequirements
from requests.models import Response as ReqResponse

# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    pyqtSignal,
    pyqtSlot,
    QObject,
    QRect,
)
# noinspection PyPackageRequirements
from PyQt5.QtGui import (
    QPixmap,
)
# noinspection PyPackageRequirements
from PyQt5.QtWidgets import (
    QGraphicsPixmapItem,
)

from planet.api.client import (
    ClientV1,
)
from planet.api import models as api_models
# from planet.api.exceptions import (
#     APIException,
#     OverQuota,
#     InvalidAPIKey,
#     NoPermission,
#     MissingResource,
#     TooManyRequests,
#     ServerError,
#     RequestCancelled,
# )

from .p_network import (
    PlanetCallbackWatcher,
    dispatch_callback,
    RESPONSE_TIMEOUT,
    # requests_response_metadata,
)

from .p_specs import (
    THUMB_GEOREF_FIELDS_IMAGE,
    ITEM_TYPE_SPECS,
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

TEMP_CACHE_DIR = tempfile.mkdtemp(
    prefix='p_thumbcache_', dir=tempfile.gettempdir())

THUMB_EXT = '.png'

GEOREFERENCE_PNG = False
THUMB_GEO = '_geo'
WORLDFILE_EXT = '.pgw'
AUX_EXT = '.aux.xml'
AUX_TMPL = """<PAMDataset><SRS>{wkt}</SRS></PAMDataset>"""
# WIDTH_512 = 'width=512&'
WIDTH_512 = ''


def is_writable_dir(dir_path: str) -> bool:
    """
    :param dir_path: Absolute path to possibly writeable directory
    """
    if not os.path.exists(dir_path):
        return False
    if not os.path.isdir(dir_path):
        return False
    try:
        # Attempt a temp file write, instead of checking for permissions
        temp = tempfile.TemporaryFile(dir=dir_path)
        temp.close()
    except (OSError, IOError):
        # No need to check for specific error of re-raise here, for our needs
        return False
    return True


class PlanetRenderJob(QObject):
    """
    Base class for external map renderer jobs
    """

    jobCancelled = pyqtSignal()
    jobCancelledWithId = pyqtSignal(str)
    jobTimedOut = pyqtSignal()
    jobTimedOutWithId = pyqtSignal(str)
    jobFinished = pyqtSignal()
    jobFinishedWithId = pyqtSignal(str, str)  # item_key, item_path

    # noinspection PyUnusedLocal
    def __init__(self, *args, parent: Optional[QObject] = None, **kwargs):

        super().__init__(parent=parent)

    def id(self) -> str:
        raise NotImplementedError

    def has_job(self) -> bool:
        raise NotImplementedError

    @pyqtSlot()
    def start(self) -> None:
        raise NotImplementedError

    @pyqtSlot()
    @pyqtSlot(str)
    def cancel(self, item_key: Optional[str] = None) -> None:
        """Should eventually emit jobCancelled and jobCancelledWithId"""
        raise NotImplementedError

    @staticmethod
    def create_job(*args, **kwargs):
        """Job factory for PlanetThumbnailCache
        e.g. return MySubClass(*args, **kwargs)
        """
        raise NotImplementedError


class PlanetThumbnailCache(QObject):
    """
    Filesystem cache with async download and world file generation support.

    Note: As per Planet API thumbnail spec, only PNG is supported at this time.
    https://developers.planet.com/docs/api/item-previews/
    """

    thumbnailAvailable = pyqtSignal(str, str)
    thumbnailFetchStarted = pyqtSignal(str)
    thumbnailFetchFailed = pyqtSignal(str)
    thumbnailFetchCancelled = pyqtSignal(str)
    thumbnailFetchTimedOut = pyqtSignal(str, int)  # timeout in seconds
    fetchShouldCancel = pyqtSignal(str)

    _cache_dir: str
    _client: Union[ClientV1]
    _watchers: dict
    _jobs: dict

    def __init__(self, cache_dir: str,
                 client: Union[ClientV1],
                 job_subclass=None,
                 parent: Optional[QObject] = None):
        """
        :param parent: QObject parent
        :param cache_dir: Path to existing directory to store thumbnails
        """
        super().__init__(parent=parent)

        if cache_dir:
            cache_dir_abs = os.path.abspath(cache_dir)
            if is_writable_dir(cache_dir_abs):
                self._cache_dir = cache_dir_abs
            else:
                log.debug(f'Passed cache_dir not writeable: {cache_dir_abs}')
                self._cache_dir = TEMP_CACHE_DIR

        else:
            self._cache_dir = TEMP_CACHE_DIR

        log.debug(f'Thumbnail cache directory:\n{self._cache_dir}')

        self._client = client

        self._watchers = {}

        # External (non-API client) render jobs that still utilize cache
        # See PlanetRenderJob base class above
        self._job_subclass = job_subclass
        self._jobs = {}

    def cache_dir(self):
        return self._cache_dir

    def set_job_subclass(self, subclass) -> None:
        self._job_subclass = subclass

    # noinspection DuplicatedCode
    def fetch_thumbnail(self, item_key: str,
                        item_id: Optional[str] = None,
                        item_type: Optional[str] = None,
                        thumb_url: Optional[str] = None,
                        item_properties: Optional[dict] = None) -> bool:
        if not item_key:
            log.debug('No item_key passed to fetch thumbnail')
            # TODO: Raise an exception?
            return False

        self.thumbnailFetchStarted.emit(item_key)

        item_path = os.path.join(self._cache_dir, f'{item_key}{THUMB_EXT}')
        if os.path.exists(item_path):
            self.thumbnailAvailable.emit(item_key, item_path)
            return True

        if item_key in self._watchers:
            log.debug(f'Watcher for item_key {item_key} already registered')
            # TODO: Let things ride for caller, or return some fetching state?
            return True

        watcher = self._add_watcher(item_key, item_properties=item_properties)

        url = thumb_url

        api_key = self._client.auth.value if self._client.auth else None

        if item_id is not None and item_type is not None:
            if not api_key:
                log.warning('No API key found for thumbnail fetching')
                return False
            url = f'https://tiles.planet.com/data/v1/item-types/{item_type}/' \
                  f'items/{item_id}/thumb?{WIDTH_512}api_key={api_key}'

        if url is None:
            log.warning('No valid URL for thumbnail fetching')
            return False

        # Set up async download
        self._watchers[item_key]['response'] = \
            self._client.dispatcher.response(
                api_models.Request(
                    url,
                    self._client.auth,
                    body_type=api_models.Body,
                    method='GET',
                )
            )

        resp: api_models.Response = self._watchers[item_key]['response']

        # try:
        resp.get_body_async(
            handler=partial(dispatch_callback, watcher=watcher))
        # except (
        #     APIException,
        #     OverQuota,
        #     InvalidAPIKey,
        #     NoPermission,
        #     MissingResource,
        #     TooManyRequests,
        #     ServerError,
        #     RequestCancelled,
        # ) as exc:
        #     log.critical(f'Thumbnail fetch failed, exception:\n{exc}')
        #     return False

        watcher.register_response(resp)

        return True

    # TODO: Pass item_resource instead, to get geometry, etc.
    def _add_watcher(self, item_key: str,
                     item_properties: Optional[dict] = None
                     ) -> PlanetCallbackWatcher:

        self._watchers[item_key] = {
            'watcher': PlanetCallbackWatcher(parent=self, watcher_id=item_key),
            'item_properties': item_properties or {},
        }
        w: PlanetCallbackWatcher = self._watchers[item_key]['watcher']
        w.responseFinishedWithId[str, 'PyQt_PyObject'].\
            connect(self._thumbnail_fetched)
        w.responseCancelledWithId[str].connect(self._fetch_cancelled)
        w.responseTimedOutWithId[str, int].connect(self._fetch_timed_out)

        self.fetchShouldCancel[str].connect(w.cancel_response)
        return w

    def _remove_watcher(self, item_key) -> None:
        if item_key in self._watchers:
            w: PlanetCallbackWatcher = self._watchers[item_key]['watcher']
            w.disconnect()
            del self._watchers[item_key]

    # @staticmethod
    # def trim_transparent_pixels(orig_path, trimmed_path) -> Tuple[int, int]:
    #     """Using PIL (pillow, actually)"""
    #
    #     null_size = (0, 0)  # w, h
    #
    #     image: Image = Image.open(orig_path)
    #     image.load()
    #     image_size = image.size
    #     # image_box = image.getbbox()
    #     image_bands = image.getbands()
    #
    #     if len(image_bands) == 1:
    #         # Probably 'P' (paletted), convert nodata to alpha channel
    #         image = image.convert("RGBA")
    #     image_bands = image.getbands()
    #
    #     if len(image_bands) < 4:
    #         # Skip images with no apparent alpha band
    #         log.debug('Image has less than 4 bands')
    #         return null_size
    #
    #     # Convert all rgba(n, n, n, 0) to rgba(0, 0, 0, 0) so getbbox() works
    #     rgb_image: Image = Image.new("RGBA", image_size, (0, 0, 0, 0))
    #     try:
    #         alpha_channel = image.getchannel('A')
    #     except ValueError:
    #         log.debug(f'Failed to get alpha channel for:\n{orig_path}')
    #         return null_size
    #     try:
    #         rgb_image.paste(image, mask=alpha_channel)
    #     except ValueError:
    #         log.debug(f'Failed to paste alpha channel for:\n{orig_path}')
    #         return null_size
    #
    #     cropped_box = rgb_image.getbbox()
    #     cropped: Image = image.crop(cropped_box)
    #     log.debug(f'For {orig_path}:\n  '
    #               f'original size:{image_size}, trimmed size: {cropped_box}')
    #     try:
    #         cropped.save(trimmed_path)
    #     except ValueError:
    #         log.debug(f'Failed to save trimmed image:\n{trimmed_path}')
    #         return null_size
    #
    #     return cropped.size  # w, h

    @staticmethod
    def opaque_image_rect(pxm: QPixmap) -> QRect:
        """
        Using only Qt's QGraphicsPixmapItem
        Culled from https://stackoverflow.com/a/3722051
        """
        gpi: QGraphicsPixmapItem = QGraphicsPixmapItem(pxm)
        return gpi.opaqueArea().boundingRect().toAlignedRect()

    def trim_transparent_pixels(
            self, orig_path, trimmed_path) -> Tuple[int, int]:

        pxm: QPixmap = QPixmap(orig_path)
        opq_rect = self.opaque_image_rect(pxm)

        pxm_geo = pxm.copy(opq_rect)
        pxm_geo.save(trimmed_path, format='PNG')

        return pxm_geo.width(), pxm_geo.height()  # w, h

    @pyqtSlot(str, 'PyQt_PyObject')
    def _thumbnail_fetched(self, item_key: str, body: api_models.Body):

        if not item_key:
            log.debug('Fetching thumbnail failed, no item_key')
            self._remove_watcher(item_key)
            self.thumbnailFetchFailed.emit(item_key)
            return

        if body is None or not hasattr(body, 'response'):
            log.debug('Fetching thumbnail failed, no body')
            self._remove_watcher(item_key)
            self.thumbnailFetchFailed.emit(item_key)
            return

        resp: ReqResponse = body.response
        # log.debug(requests_response_metadata(resp))

        if not resp.ok:
            log.debug('Fetching thumbnail failed')
            self._remove_watcher(item_key)
            self.thumbnailFetchFailed.emit(item_key)
            return

        if ('content-type' not in resp.headers
                or resp.headers['content-type'] != 'image/png'):
            log.debug('Fetching thumbnail failed, not image/png')
            self._remove_watcher(item_key)
            self.thumbnailFetchFailed.emit(item_key)
            return

        # Try to load image data into QPixmap
        image_data = resp.content  # consume response data

        qp = QPixmap()
        if not qp.loadFromData(image_data, 'PNG'):
            log.debug('Fetching thumbnail failed, could not load PNG data')
            self._remove_watcher(item_key)
            self.thumbnailFetchFailed.emit(item_key)
            return

        # Write .png image to cache directory
        item_path = os.path.join(self._cache_dir,
                                 f'{item_key}{THUMB_EXT}')

        if os.path.exists(item_path):
            os.remove(item_path)

        qp.save(item_path, 'PNG')

        if GEOREFERENCE_PNG:
            # noinspection PyBroadException
            try:
                self._georeference_thumbnail(item_key, item_path)
            except:
                # TODO: Figure out all possibly thrown exceptions
                pass

        self._remove_watcher(item_key)

        self.thumbnailAvailable.emit(item_key, item_path)

    def _georeference_thumbnail(self, item_key, item_path):
        skip = 'Skipping thumb georeferencing'

        item_type_id = item_key.split('__')
        if not item_type_id or len(item_type_id) < 2:
            log.debug(f'{skip}, no resolvable item type and id')
            return
        item_type = item_type_id[0]
        i_specs: dict = ITEM_TYPE_SPECS.get(item_type, None)
        if not i_specs:
            log.debug(f'{skip}, no item type specs')
            return
        georef_fields: List[str] = i_specs.get('thumb_georef_fields', None)
        if not georef_fields:
            log.debug(f'{skip}, no georef fields found')
            return

        # See: planet_api/thumbnails/trim_transparent_pixels.py
        item_name_geo = f'{item_key}{THUMB_GEO}'
        item_geo_path = os.path.join(self._cache_dir,
                                     f'{item_name_geo}{THUMB_EXT}')

        if os.path.exists(item_geo_path):
            os.remove(item_geo_path)

        geo_w, geo_h = \
            self.trim_transparent_pixels(item_path, item_geo_path)

        if not (geo_w > 0 and geo_h > 0):
            log.debug(f'{skip}, trimmed image missing rows or columns')
            return

        props = self._watchers[item_key]['item_properties']

        if not props or not all([f in props for f in georef_fields]):
            log.debug(f'{skip}, item georef properties not found or missing')
            os.remove(item_geo_path)
            return

        if georef_fields == THUMB_GEOREF_FIELDS_IMAGE:

            # Write projection file
            epsg_code = props.get('epsg_code', None)
            if epsg_code:
                item_geo_aux_path = \
                    os.path.join(
                        self._cache_dir,
                        f'{item_name_geo}{THUMB_EXT}{AUX_EXT}')

                if os.path.exists(item_geo_aux_path):
                    os.remove(item_geo_aux_path)

                # crs = pyproj.CRS.from_epsg(epsg_code)
                # crs_wkt = crs.to_wkt()
                prj_srs = osr.SpatialReference()
                prj_srs.ImportFromEPSG(int(epsg_code))

                with open(item_geo_aux_path, 'w') as f:
                    f.write(AUX_TMPL.format(wkt=prj_srs.ExportToWkt()))
                    f.write('\n')
            else:
                log.debug(f'{skip}, EPSG code not resolved')
                os.remove(item_geo_path)
                return

            # Write world file
            i_cols = int(props['columns'])
            i_rows = int(props['rows'])
            i_pr = int(props['pixel_resolution'])
            p_x = i_cols / geo_w * i_pr
            p_y = i_rows / geo_h * i_pr
            ulx = int(props['origin_x'])
            uly = int(props['origin_y'])

            item_pgw_path = os.path.join(
                self._cache_dir, f'{item_name_geo}{WORLDFILE_EXT}')

            if os.path.exists(item_pgw_path):
                os.remove(item_pgw_path)

            with open(item_pgw_path, 'w') as f:
                # pixel size in x-direction map units
                f.write(f'{p_x}\n')
                # rotation about y-axis
                f.write('0\n')
                # rotation about x-axis
                f.write('0\n')
                # pixel size in y-direction map units, negative
                f.write(f'-{p_y}\n')
                # x-coordinate of center of upper left pixel
                f.write(f'{ulx}\n')
                # y-coordinate of center of upper left pixel
                f.write(f'{uly}\n')
                f.write(f'\n')

        else:
            log.debug(f'{skip}, no item georef properties matched')
            os.remove(item_geo_path)
            return

    @pyqtSlot(str, int)
    def _fetch_timed_out(self, item_key, timeout: int = RESPONSE_TIMEOUT):
        self._remove_watcher(item_key)
        self.thumbnailFetchTimedOut.emit(item_key, timeout)

    @pyqtSlot(str)
    def _fetch_cancelled(self, item_key):
        self._remove_watcher(item_key)
        self.thumbnailFetchCancelled.emit(item_key)

    @pyqtSlot(str)
    def cancel_fetch(self, item_key):
        self.fetchShouldCancel.emit(item_key)

    # Render jobs API below ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    # noinspection DuplicatedCode
    def fetch_job_thumbnail(self, *args, **kwargs):

        item_key = args[0] if len(args) > 0 and '__' in args[0] else None
        if not item_key:
            log.debug('No item_key passed to fetch job thumbnail')
            # TODO: Raise an exception?
            self.thumbnailFetchFailed.emit(item_key)
            return False

        if not self._job_subclass:
            log.debug('No job_subclass set in thmbnail cache')
            self.thumbnailFetchFailed.emit(item_key)
            return False

        self.thumbnailFetchStarted.emit(item_key)

        item_path = os.path.join(self._cache_dir, f'{item_key}{THUMB_EXT}')
        if os.path.exists(item_path):
            self.thumbnailAvailable.emit(item_key, item_path)
            return True

        if item_key in self._jobs:
            log.debug(f'Job for item_key {item_key} already registered')
            # TODO: Let things ride for caller, or return some fetching state?
            return True

        log.debug(f'Creating job for item_key: {item_key}')
        self._jobs[item_key] = \
            self._job_subclass.create_job(
                *args,
                api_client=self._client,
                cache_dir=self._cache_dir,
                parent=self,
                **kwargs
            )  # type: PlanetRenderJob

        self._jobs[item_key].jobFinishedWithId[str, str]\
            .connect(self._thumbnail_job_finished)

        self.fetchShouldCancel[str].connect(self._jobs[item_key].cancel)

        self._jobs[item_key].start()

        return True

    def _remove_job(self, item_key) -> None:
        if item_key in self._jobs:
            self._jobs[item_key].disconnect()
            del self._jobs[item_key]

    @pyqtSlot(str)
    def _job_cancelled(self, item_key):
        self._remove_job(item_key)
        self.thumbnailFetchCancelled.emit(item_key)

    @pyqtSlot(str, str)
    def _thumbnail_job_finished(self, item_key: str, item_path: str):

        if not item_key:
            log.debug('Fetching job thumbnail failed, no item_key')
            self._remove_job(item_key)
            self.thumbnailFetchFailed.emit(item_key)
            return

        if not item_path or not os.path.exists(item_path):
            log.debug(f'Fetching job thumbnail failed, '
                      f'image path missing or does not exist:\n{item_path}')
            self._remove_job(item_key)
            self.thumbnailFetchFailed.emit(item_key)
            return

        self._remove_job(item_key)

        self.thumbnailAvailable.emit(item_key, item_path)
