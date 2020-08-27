# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_client.py
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
import json
import random

# noinspection PyPackageRequirements
from requests import post

from typing import (
    Optional,
    List,
)

# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    pyqtSignal,
    pyqtSlot,
    QObject,
    QSettings
)
from qgis.core import QgsAuthMethodConfig, QgsApplication
# noinspection PyPackageRequirements
# from PyQt5.QtGui import QPixmap

from planet.api import ClientV1, auth
from planet.api import models as api_models
from planet.api.exceptions import APIException, InvalidIdentity

# from .p_models import
from .p_specs import (
    RESOURCE_SINGLE_MOSAICS,
    RESOURCE_MOSAIC_SERIES,
    RESOURCE_DAILY,
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

API_KEY_DEFAULT = 'SKIP_ENVIRON'

ITEM_GROUPS = [
    {'display_name': 'Daily Imagery',
     'filter_widget': None,
     'resource_type': RESOURCE_DAILY},
    {'display_name': 'Mosaic Series',
     'filter_widget': None,
     'resource_type': RESOURCE_MOSAIC_SERIES},
    {'display_name': 'Single Mosaics',
     'filter_widget': None,
     'resource_type': RESOURCE_SINGLE_MOSAICS}
]

QUOTA_URL = 'https://api.planet.com/auth/v1/experimental' \
            '/public/my/subscriptions'

TILE_SERVICE_URL = 'https://tiles{0}.planet.com/data/v1/layers'

class LoginException(Exception):
    """Issues raised during client login"""
    pass


# noinspection PyPep8Naming,PyUnresolvedReferences
class PlanetClient(QObject):
    """
    Wrapper class for ``planet`` Python package, to abstract calls and make it
    a Qt object.

    .. note:: This class should only use Python or Qt APIs.
    """

    loginChanged = pyqtSignal(bool)

    __instance = None
    @staticmethod 
    def getInstance():
        if PlanetClient.__instance is None:
            PlanetClient()

        PlanetClient.__instance.set_proxy_values()
        return PlanetClient.__instance

    def __init__(self, parent=None,
                 api_key=API_KEY_DEFAULT,
                 area_km_func=None):

        if PlanetClient.__instance != None:
            raise Exception("Singleton class")
        """
        :param api_key:
        :param area_km_func: External function for calculating area of GeoJSON
        geometry, with signature `func(geometry)`, where geometry can be either
        a text or dict (from `json` module) GeoJSON geometry representation.
        Passed geometry should be in EPSG:4326.
        """
        super(PlanetClient, self).__init__(parent=parent)
        PlanetClient.__instance = self

        # NOTE: We pass in API_KEY_DEFAULT to keep the API client from looking
        #       elsewhere on the system or within the environ
        self.client_v1 = ClientV1(api_key=api_key)
        # TODO: add client_v2 when available

        # Generic client for swapping context relative to Planet item type
        self.client = self.client_v1

        # A Planet user
        self.p_user = None

        self._user_quota = {
            'enabled': False,
            'sqkm': 0.0,
            'used': 0.0,
        }

        self._area_km_func = area_km_func

        # if not callable(self._area_km_func):
        #     log.info('No external geometry area calc function registered')
        #     # TODO: Create/register internal func based upon `ogr` module

    def set_proxy_values(self):
        settings = QSettings()
        proxyEnabled = settings.value("proxy/proxyEnabled")
        if proxyEnabled:
            proxyHost = settings.value("proxy/proxyHost")
            proxyPort = settings.value("proxy/proxyPort")
            url = f"{proxyHost}:{proxyPort}"
            
            authid = settings.value("proxy/authcfg", "")
            if authid:
                authConfig = QgsAuthMethodConfig()
                QgsApplication.authManager().loadAuthenticationConfig(
                    authid, authConfig, True)
                username = authConfig.config('username')
                password = authConfig.config('password')
            else:
                username = settings.value("proxy/proxyUser")
                password = settings.value("proxy/proxyPassword")
            
            if username:                
                tokens = url.split("://")
                url = f"{tokens[0]}://{username}:{password}@{tokens[-1]}"

            self.client.dispatcher.session.proxies["http"] = url
        else:
            self.client.dispatcher.session.proxies = {}


    def _url(self, path):
        if path.startswith('http'):
            url = path
        else:
            url = self.client.base_url + path
        return url

    def api_client(self):
        return self.client

    def log_in(self, user, password, api_key=None):
        old_api_key = self.api_key()

        if api_key:
            # TODO: Sanitize?
            self.client.auth = auth.APIKey(api_key)
        else:
            # Do login. Propogate captured errors to caller
            # TODO: swap with new auth endpoint?
            #       auth/v1/experimental/public/users/authenticate

            try:
                res = self.client.login(user, password)
            except (APIException, InvalidIdentity) as exc:
                raise LoginException from exc

            if 'user_id' in res:
                self.p_user = res
                self.client.auth = auth.APIKey(self.p_user['api_key'])
                # self.update_user_quota()
            else:
                raise LoginException()

        if old_api_key != self.api_key():
            self.loginChanged.emit(self.has_api_key())

    def log_out(self):
        old_api_key = self.api_key()

        # Do log out
        self.client.auth = auth.APIKey(API_KEY_DEFAULT)
        self.p_user = None

        if old_api_key != self.api_key():
            self.loginChanged.emit(self.has_api_key())

    def user(self):
        return self.p_user

    def api_key(self):
        if hasattr(self.client.auth, 'value'):
            return self.client.auth.value
        return None

    def set_api_key(self, api_key):
        self.client.auth = auth.APIKey(api_key)

    def has_api_key(self):
        if hasattr(self.client.auth, 'value'):
            return self.client.auth.value not in [None, '', API_KEY_DEFAULT]
        return False

    # def thumbnail_image(self, thumb_url=None, item_type=None, item_id=None):
    #     url = thumb_url
    #
    #     if item_type is not None and item_id is not None:
    #         if not self.has_api_key():
    #             log.warning('No API key for thumbnail image download')
    #             return QPixmap()
    #         url = f'https://tiles.planet.com/data/v1/item-types/' \
    #               f'{item_type}/items/{item_id}/thumb' \
    #               f'?api_key={self.api_key()}'
    #
    #     if url is None:
    #         log.warning('No valid URL for thumbnail image download')
    #         return QPixmap()
    #
    #     dispatcher = self.client.dispatcher
    #
    #     # TODO: This should download the thumb instead, to cache on disk
    #     #       and to allow generation of thumb.pgw world files
    #     # TODO: Try/catch requests errors
    #     result = dispatcher.dispatch_request(method="GET", url=url)
    #     # TODO: This blocks, needs ...
    #     #       result.get_body_async(callback)
    #     #       and the callback func/method
    #     # TODO: This *should* use QgsNetworkContentFetcherRegistry, but this
    #     #       class should not include qgis modules. Maybe test to see if
    #     #       qgis.core has been imported globally, then conditionally use?
    #     image_data = result.content
    #
    #     qp = QPixmap()
    #     qp.loadFromData(image_data)
    #
    #     # Previously returned QImage, but QPixmap is a better base UI image
    #     return qp

    def quick_search(self, request, callback=None, **kwargs):
        """
        Note: Duplicated from `planet.api.client.ClientV1.quick_search` so
        that async requests can be supported.

        IMPORTANT: Unlike `ClientV1.quick_search`, this returns just the
        `planet.api.models.Response`. For non-async calls, you will need to
        use my_response.get_body() for the `planet.api.models.Items` body.

        Execute a quick search with the specified request.

        :param request: see :ref:`api-search-request`
        :param callback: Optional callback for when async requests finish
        :param kwargs: See Options below
        :returns: :py:class:`planet.api.models.Response`
        :raises planet.api.exceptions.APIException: On API error.

        :Options:

        * page_size (int): Size of response pages
        * sort (string): Sorting order in the form `field (asc|desc)`

        """
        def qs_params(kw):
            _params = {}
            if 'page_size' in kw:
                _params['_page_size'] = kw['page_size']
            if 'sort' in kw and kw['sort']:
                _params['_sort'] = ''.join(kw['sort'])
            return _params

        body = json.dumps(request)
        params = qs_params(kwargs)
        response = self.client.dispatcher.response(
            api_models.Request(
                self._url('data/v1/quick-search'),
                self.client.auth,
                params=params,
                body_type=api_models.Items,
                data=body,
                method='POST'
            )
        )
        if callback:
            response.get_body_async(callback)

        return response

    # noinspection PyUnusedLocal
    def create_order(self, request, callback=None, **kwargs):
        """Create an order.

        :param request: see :ref:`api-search-request`
        :param callback: Optional callback for when async requests finish
        :returns: :py:Class:`planet.api.models.Orders` containing a
                  :py:Class:`planet.api.models.Body` of the order response.
        :raises planet.api.exceptions.APIException: On API error.
        """
        url = self._url('compute/ops/orders/v2')
        body = json.dumps(request)
        response = self.client.dispatcher.response(
            api_models.Request(
                url, self.client.auth,
                body_type=api_models.Order,
                data=body,
                method='POST'
            )
        )

        if callback:
            response.get_body_async(callback)
            return response
        else:
            return response.get_body()

    def list_mosaic_series(self):
        '''List all available mosaic series
        :returns: :py:Class:`planet.api.models.JSON`
        '''
        url = self._url('basemaps/v1/series/')
        response = self.client.dispatcher.response(
            api_models.Request(
                url, self.client.auth,
                body_type=api_models.JSON,                
            )
        )
        return response.get_body()

    def get_mosaics(self, name_contains=None):
        '''List all available mosaic series
        :returns: :py:Class:`planet.api.models.JSON`
        '''
        params = {"v":"1.5"}
        if name_contains:
            params['name__contains'] = name_contains
        url = self._url('basemaps/v1/mosaics')
        response = self.client.dispatcher.response(
            api_models.Request(
                url, self.client.auth,
                body_type=api_models.Mosaics,                
                params=params,
            )
        )
        return response.get_body()        

    def get_mosaics_for_series(self, series_id):
        '''List all available mosaics for a given series
        :returns: :py:Class:`planet.api.models.JSON`
        '''
        url = self._url('basemaps/v1/series/{}/mosaics?v=1.5'.format(series_id))
        response = self.client.dispatcher.response(
            api_models.Request(
                url, self.client.auth,
                body_type=api_models.Mosaics                
            )
        )
        return response.get_body()

    def register_area_km_func(self, func):
        self._area_km_func = func

    def area_calc_func_registered(self):
        return callable(self._area_km_func)

    def area_km_from_geometry(self, geometry):
        """
        :param geometry: JSON geometry (as string or `json` object)
        :rtype geometry: str | dict
        :return:
        """
        if not self.area_calc_func_registered():
            log.warning('No geometry area calc function registered')
            return None
        return self._area_km_func(geometry)

    @pyqtSlot(result=bool)
    def update_user_quota(self):
        """
        Example quota response

        [
          {
            "active_from": "2019-08-01T00:00:00+00:00",
            "active_to": null,
            "basemap_quad_quota": null,
            "basemap_tile_quota": null,
            "created_at": "2019-08-01T18:33:11.551737+00:00",
            "datadrop_anchor_date": "2019-08-01T00:00:00+00:00",
            "datadrop_enabled": false,
            "datadrop_interval": null,
            "deleted_at": null,
            "id": 301722,
            "organization": {
              "id": 150098,
              "name": "Planet Federal"
            },
            "organization_id": 150098,
            "plan": {
              "id": 1262,
              "name": "Timelapse Basemaps Web Service",
              "state": "active"
            },
            "plan_id": 1262,
            "quota_anchor_date": "2019-08-01T00:00:00+00:00",
            "quota_enabled": false,
            "quota_interval": null,
            "quota_reset_at": null,
            "quota_sqkm": null,
            "quota_style": "consumption",
            "quota_used": 0.0,
            "reference": "PL-0123456",
            "selected_operations": null,
            "state": "active",
            "updated_at": "2019-08-01T18:33:11.551737+00:00",
            "url": "https://api.planet.com/auth/v1/experimental/public/"
                   "subscriptions/301722"
          },
          ...
        ]
        """
        if not self.api_key():
            log.warning('No API key found for getting quota')
            return False

        # TODO: Catch errors
        # TODO: Switch to async call
        # response = self.client.dispatcher.dispatch_request(
        #     method="GET", url=QUOTA_URL, auth=self.client.auth)

        resp: api_models.JSON = self.client.dispatcher.response(
            api_models.Request(
                QUOTA_URL,
                auth=self.client.auth,
                body_type=api_models.JSON,
                method='GET')
        ).get_body()

        resp_data = resp.get()
        log.debug(f'resp_data:\n{resp_data}')
        if not resp_data:
            log.warning('No response data found for getting quota')
            return False

        quota_keys = ['quota_enabled', 'quota_sqkm', 'quota_used']
        has_quota_data = all([q in resp_data for q in quota_keys])

        if has_quota_data:
            quota_enabled = bool(resp_data['quota_enabled'])
            self._user_quota['enabled'] = quota_enabled
            self._user_quota['sqkm'] = resp_data['quota_sqkm']
            self._user_quota['used'] = resp_data['quota_used']
            log.debug(f""" Quota (sqkm)
              Enabled: {str(self.user_quota_enabled())}
              Size: {str(self.user_quota_size())}
              Used: {str(self.user_quota_used())}
              Remaining: {str(self.user_quota_remaining())}
            """)
        else:
            log.warning('No quota keys found in response for getting quota')
            return False

        return True

    def user_quota_enabled(self):
        return bool(self._user_quota['enabled'])

    def user_quota_size(self):
        return bool(self._user_quota['sqkm'])

    def user_quota_used(self):
        return bool(self._user_quota['used'])

    def user_quota_remaining(self):
        # if not self.update_user_quota():
        #     return None

        if self.user_quota_enabled():
            return float(self._user_quota['sqkm']) - \
                   float(self._user_quota['used'])

        return None

    def exceedes_quota(self, geometries):
        """
        :param geometries: List of JSON geometries (as string or `json` object)
        :type geometries: list[str|dict]
        :rtype: bool
        """
        if not self.area_calc_func_registered():
            log.warning('No geometry area calc function registered')
            return False

        area_total = 0.0
        quota_remaining = self.user_quota_remaining()

        if not quota:
            return False

        for geometry in geometries:
            area_total += float(self.area_km_from_geometry(geometry))

        return area_total >= quota_remaining


def tile_service_hash(item_type_ids: List[str], api_key: str) -> Optional[str]:
    """
    :param item_type_ids: List of item Type:IDs
    :param api_key: API key string
    :return: Tile service hash that can be used in tile URLs
    """
    if not api_key:
        log.debug('No API key, skipping tile hash')
        return None

    if not item_type_ids:
        log.debug('No item type:ids passed, skipping tile hash')
        return None

    item_type_ids.reverse()
    data = {'ids': ','.join(item_type_ids)}

    tile_url = TILE_SERVICE_URL.format('')

    # resp: api_models.Response = self.client.dispatcher.response(
    #     api_models.Request(
    #         tile_url,
    #         self.client.auth,
    #         params={},
    #         body_type=api_models.JSON,
    #         data=json.dumps(data),
    #         method='POST'
    #     )
    # )
    # log.debug(f'resp.request.auth.value: {resp.request.auth.value}')
    # body: api_models.JSON = resp.get_body()
    #
    # if body and hasattr(body, 'response'):
    #     res: ReqResponse = body.response
    #     if res.ok:
    #         res_json = body.get()
    #         if 'name' in res_json:
    #             return res_json['name']

    # Via requests
    # FIXME: Should be using the above code, not direct call to requests
    res = post(tile_url, auth=(api_key, ''), data=data)
    if res.ok:
        res_json = res.json()
        if 'name' in res_json:
            return res_json['name']
    else:
        log.debug(f'Tile service hash request failed:\n'
                  f'status_code: {res.status_code}\n'
                  f'reason: {res.reason}')

    return None


def tile_service_url(
        item_type_ids: List[str],
        api_key: str,
        tile_hash: Optional[str] = None,
        service: str = 'xyz') -> Optional[str]:
    """
    :param item_type_ids: List of item 'Type:IDs'
    :param api_key: Planet API key
    :param tile_hash: Tile service hash
    :param service: Either 'xyz' or 'wmts'
    :return: Tile service URL
    """
    if not api_key:
        log.debug('No API key, skipping tile URL')
        return None

    if not tile_hash:
        if not item_type_ids:
            log.debug('No item type:ids passed, skipping tile URL')
            return None
        tile_hash = tile_service_hash(item_type_ids, api_key)

    if not tile_hash:
        log.debug('No tile URL hash passed, skipping tile URL')
        return None

    url = None
    if service.lower() == 'wmts':
        tile_url = TILE_SERVICE_URL.format('')
        url = f'{tile_url}/wmts/{tile_hash}?api_key={api_key}'
    elif service.lower() == 'xyz':
        tile_url = TILE_SERVICE_URL.format(random.randint(0, 3))
        url = \
            f'{tile_url}/{tile_hash}/{{z}}/{{x}}/{{y}}?' \
            f'api_key={api_key}'

    return url

if __name__ == "__main__":
    import sys
    from qgis.PyQt.QtWidgets import (
        QApplication,
    )

    plugin_path = os.path.split(os.path.dirname(__file__))[0]
    print(plugin_path)
    sys.path.insert(0, plugin_path)

    from ..pe_utils import (
        area_from_geojsons,
    )

    app = QApplication(sys.argv)

    apikey = os.getenv('PL_API_KEY')

    # Init api client
    p_client = PlanetClient(
        api_key=apikey, area_km_func=area_from_geojsons,)
    # noinspection PyUnresolvedReferences
    # p_client.loginChanged[bool].connect(self.login_changed)
    # p_client.update_user_quota()

    sys.exit(app.exec_())
