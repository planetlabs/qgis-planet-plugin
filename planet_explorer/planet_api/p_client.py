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
import random
import json

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
from qgis.core import (QgsAuthMethodConfig,
                        QgsApplication,
                        QgsMessageLog,
                        Qgis
)

# noinspection PyPackageRequirements
# from PyQt5.QtGui import QPixmap

from planet.api import ClientV1, auth
from planet.api import models as api_models
from planet.api.exceptions import APIException, InvalidIdentity

from ..gui.pe_gui_utils import (
    waitcursor
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

API_KEY_DEFAULT = 'SKIP_ENVIRON'

QUOTA_URL = 'https://api.planet.com/auth/v1/experimental' \
            '/public/my/subscriptions'

TILE_SERVICE_URL = 'https://tiles{0}.planet.com/data/v1/layers'


class LoginException(Exception):
    """Issues raised during client login"""
    pass


# noinspection PyPep8Naming,PyUnresolvedReferences
class PlanetClient(QObject, ClientV1):
    """
    Wrapper class for ``planet`` Python package, to abstract calls and make it
    a Qt object.
    """

    loginChanged = pyqtSignal(bool)

    __instance = None
    @staticmethod
    def getInstance():
        if PlanetClient.__instance is None:
            PlanetClient()

        PlanetClient.__instance.set_proxy_values()
        return PlanetClient.__instance

    def __init__(self):
        if PlanetClient.__instance is not None:
            raise Exception("Singleton class")

        QObject.__init__(self)
        # NOTE: We pass in API_KEY_DEFAULT to keep the API client from looking
        #       elsewhere on the system or within the environ
        ClientV1.__init__(self, api_key=API_KEY_DEFAULT)

        PlanetClient.__instance = self

        self._user_quota = {
            'enabled': False,
            'sqkm': 0.0,
            'used': 0.0,
        }

    def set_proxy_values(self):
        settings = QSettings()
        proxyEnabled = settings.value("proxy/proxyEnabled")
        base_url = self.base_url.lower()
        excluded = False
        noProxyUrls = settings.value("proxy/noProxyUrls") or []
        excluded = any([base_url.startswith(url.lower()) for url in noProxyUrls])
        if proxyEnabled and not excluded:
            proxyType = settings.value("proxy/proxyType")
            if proxyType != "HttpProxy":
                QgsMessageLog.logMessage("Planet Explorer: Only HttpProxy is supported "
                                         "for connecting to the Planet API",
                                         level=Qgis.Warning)
                return

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

            self.dispatcher.session.proxies["http"] = url
            self.dispatcher.session.proxies["https"] = url
        else:
            self.dispatcher.session.proxies = {}

    @waitcursor
    def log_in(self, user, password, api_key=None):
        old_api_key = self.api_key()

        if api_key:
            # TODO: Sanitize?
            self.auth = auth.APIKey(api_key)
        else:
            # Do login. Propogate captured errors to caller
            # TODO: swap with new auth endpoint?
            #       auth/v1/experimental/public/users/authenticate

            try:
                res = self.login(user, password)
            except (APIException, InvalidIdentity) as exc:
                raise LoginException from exc

            if 'user_id' in res:
                self.p_user = res
                self.auth = auth.APIKey(self.p_user['api_key'])
                self.update_user_quota()
            else:
                raise LoginException()

        if old_api_key != self.api_key():
            self.loginChanged.emit(self.has_api_key())

    def log_out(self):
        old_api_key = self.api_key()

        # Do log out
        self.auth = auth.APIKey(API_KEY_DEFAULT)
        self.p_user = None

        if old_api_key != self.api_key():
            self.loginChanged.emit(self.has_api_key())

    def user(self):
        return self.p_user

    def api_key(self):
        if hasattr(self.auth, 'value'):
            return self.auth.value
        return None

    def has_api_key(self):
        if hasattr(self.auth, 'value'):
            return self.auth.value not in [None, '', API_KEY_DEFAULT]
        return False

    def has_access_to_mosaics(self):
        url = self._url('basemaps/v1/mosaics')
        params = {'_page_size': 1}
        response = self._get(url, api_models.Mosaics, params=params).get_body().get()
        return len(response) > 0

    def list_mosaic_series(self, name_contains=None):
        '''List all available mosaic series
        :returns: :py:Class:`planet.api.models.JSON`
        '''
        params = {}
        if name_contains:
            params['name__contains'] = name_contains
        url = self._url('basemaps/v1/series/')
        return self._get(url, api_models.Mosaics, params=params).get_body()

    @waitcursor
    def get_mosaics(self, name_contains=None):
        '''List all available mosaics
        :returns: :py:Class:`planet.api.models.JSON`
        '''
        params = {"v":"1.5", "_page_size": 10000}
        if name_contains:
            params['name__contains'] = name_contains
        url = self._url('basemaps/v1/mosaics')
        return self._get(url, api_models.Mosaics, params=params).get_body()

    def get_mosaics_for_series(self, series_id):
        url = self._url('basemaps/v1/series/{}/mosaics?v=1.5'.format(series_id))
        return self._get(url, api_models.Mosaics).get_body()

    def get_quads_for_mosaic(self, mosaic, bbox=None, minimal=False):
        '''List all available quad for a given mosaic
        :returns: :py:Class:`planet.api.models.JSON`
        '''
        if isinstance(mosaic, str):
            mosaicid = mosaic
        else:
            mosaicid = mosaic["id"]

        url = self._url(f'basemaps/v1/mosaics/{mosaicid}/quads?bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}')
        if bbox is None:
            if isinstance(mosaic, str):
                bbox = [-180, -85, 180, 85]
            else:
                bbox = mosaic['bbox']
        bbox = (max(-180, bbox[0]), max(-85, bbox[1]),
                min(180, bbox[2]), min(85, bbox[3]))
        url = url.format(lx=bbox[0], ly=bbox[1], ux=bbox[2], uy=bbox[3])
        if minimal:
            url += "&minimal=true"
        return self._get(url, api_models.MosaicQuads).get_body()

    def get_one_quad(self, mosaic):
        url = self._url(f'basemaps/v1/mosaics/{mosaic["id"]}/quads')
        params = {"_page_size":1,
                    "bbox": ",".join(str(v) for v in mosaic['bbox'])}
        response = self._get(url, api_models.MosaicQuads, params=params)
        quad = response.get_body().get().get("items")[0]
        return quad

    def get_items_for_quad(self, mosaicid, quadid):
        url = self._url(f'basemaps/v1/mosaics/{mosaicid}/quads/{quadid}/items')
        response = self._get(url, api_models.JSON)
        item_descriptions = []
        items = response.get_body().get().get("items")
        for item in items:
            if item['link'].startswith("https://api.planet.com"):
                response = self._get(item["link"], api_models.JSON)
                item_descriptions.append(response.get_body().get())

        return item_descriptions

    def create_order(self, request):
        api_key = PlanetClient.getInstance().api_key()
        url = self._url('compute/ops/orders/v2')
        headers = {"X-Planet-App": "qgis"}
        session = PlanetClient.getInstance().dispatcher.session
        res = session.post(url, auth=(api_key, ''), json=request,
                           headers=headers)
        return res.json()

    def create_search(self, request):
        '''Updates a saved search from the specified request.
        The request must contain a ``name`` property.

        :param request: see :ref:`api-search-request`
        :returns: :py:class:`planet.api.models.JSON`
        :raises planet.api.exceptions.APIException: On API error.
        '''
        body = json.dumps(request)
        return self.dispatcher.response(api_models.Request(
            self._url('data/v1/searches/'), self.auth,
            body_type=api_models.JSON, data=body, method='PUT')).get_body()

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
        # response = self.dispatcher.dispatch_request(
        #     method="GET", url=QUOTA_URL, auth=self.auth)

        resp: api_models.JSON = self.dispatcher.response(
            api_models.Request(
                QUOTA_URL,
                auth=self.auth,
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

        area_total = 0.0
        quota_remaining = self.user_quota_remaining()

        if quota_remaining is None:
            return False

        area_total = self.area_km_from_geometry(geometries)

        return area_total >= quota_remaining


def tile_service_hash(item_type_ids: List[str]) -> Optional[str]:
    """
    :param item_type_ids: List of item Type:IDs
    :param api_key: API key string
    :return: Tile service hash that can be used in tile URLs
    """

    api_key = PlanetClient.getInstance().api_key()

    if not item_type_ids:
        log.debug('No item type:ids passed, skipping tile hash')
        return None

    item_type_ids.reverse()
    data = {'ids': ','.join(item_type_ids)}

    tile_url = TILE_SERVICE_URL.format('')

    session = PlanetClient.getInstance().dispatcher.session
    res = session.post(tile_url, auth=(api_key, ''), data=data)
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
        tile_hash: Optional[str] = None,
        service: str = 'xyz') -> Optional[str]:
    """
    :param item_type_ids: List of item 'Type:IDs'
    :param api_key: Planet API key
    :param tile_hash: Tile service hash
    :param service: Either 'xyz' or 'wmts'
    :return: Tile service URL
    """
    api_key = PlanetClient.getInstance().api_key()

    if not tile_hash:
        if not item_type_ids:
            log.debug('No item type:ids passed, skipping tile URL')
            return None
        tile_hash = tile_service_hash(item_type_ids)

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
