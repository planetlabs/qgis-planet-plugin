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

__author__ = "Planet Federal"
__date__ = "August 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import gzip
import json
import logging
import os
import re
import secrets
from typing import (
    List,
    Optional,
)

import requests
from planet import Auth, Session
from planet.exceptions import InvalidAPIKey, InvalidIdentity
from planet.sync.client import Planet

"""
from planet.api import ClientV1, auth
from planet.api import models as api_models
from planet.api.exceptions import APIException, InvalidIdentity
"""
from qgis.core import Qgis, QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QMetaObject, QObject, Qt, QUrl, pyqtSignal, pyqtSlot
from qgis.PyQt.QtNetwork import QNetworkRequest

from ..gui.pe_gui_utils import waitcursor

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

ITEM_ASSET_DL_REGEX = re.compile(r"^assets\.(.*):download$")
ITEM_STREAM_REGEX = re.compile(r"^webtiles?:stream$")

QUOTA_URL = "https://api.planet.com/auth/v1/experimental" "/public/my/subscriptions"

TILE_SERVICE_URL = "https://tiles{0}.planet.com/data/v1/layers"

# TODO: Replace once a custom Client ID is provided
# PROFILE_NAME = "planet-qgis-plugin"
PROFILE_NAME = "planet-user"


class LoginException(Exception):
    """Issues raised during client login"""

    pass


class QGISAdapter:

    _offline = False
    _message_bar_item = None

    def send(self, request: requests.PreparedRequest, **kwargs):
        error = 0
        req = QNetworkRequest(QUrl(request.url))
        for h in request.headers:
            req.setRawHeader(h.encode(), request.headers[h].encode())
        req.setRawHeader("Accept-Encoding".encode(), "gzip".encode())

        breq = QgsBlockingNetworkRequest()
        if request.method == "GET":
            error = breq.get(req)
        elif request.method == "POST":
            body = request.body
            if not isinstance(body, bytes):
                body = body.encode()
            error = breq.post(req, body)
        if error > 0:
            msg = breq.errorMessage()
            if not QGISAdapter._offline:
                QGISAdapter._offline = True
                msg_lower = msg.lower()
                if "ssl" in msg_lower or "tls" in msg_lower:
                    if "proxy" in msg_lower:
                        bar_msg = (
                            "SSL/TLS error connecting to Planet via proxy. "
                            "Your proxy may be interfering with HTTPS. "
                            "Check Settings > Options > Network."
                        )
                    else:
                        bar_msg = (
                            "SSL/TLS error connecting to Planet. If you are "
                            "using a proxy, it may be interfering with HTTPS "
                            "connections."
                        )
                elif "proxy" in msg_lower:
                    bar_msg = (
                        "Proxy connection refused. Check your proxy "
                        "settings under Settings > Options > Network."
                    )
                elif error == 2 or "timed out" in msg_lower or "timeout" in msg_lower:
                    bar_msg = (
                        "Connection to Planet timed out. The plugin will "
                        "resume automatically when connectivity is restored."
                    )
                else:
                    bar_msg = (
                        "Cannot access the internet. The plugin will resume "
                        "automatically when connectivity is restored."
                    )
                QGISAdapter._offline_msg = bar_msg
                QMetaObject.invokeMethod(
                    PlanetClient.getInstance(),
                    "_show_offline_message",
                    Qt.ConnectionType.QueuedConnection,
                )
            if error == 1:
                raise requests.exceptions.ConnectionError(msg)
            elif error == 2:
                raise requests.exceptions.ConnectTimeout(msg)
            elif error == 3:
                raise requests.exceptions.RequestException(msg)

        if QGISAdapter._offline:
            QGISAdapter._offline = False
            QMetaObject.invokeMethod(
                PlanetClient.getInstance(),
                "_clear_offline_message",
                Qt.ConnectionType.QueuedConnection,
            )

        content = breq.reply()
        resp = requests.Response()
        for h in content.rawHeaderList():
            header = h.data().decode()
            resp.headers[header] = content.rawHeader(h).data().decode()
        data = content.content().data()
        if resp.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        resp._content = data
        resp.status_code = content.attribute(
            QNetworkRequest.Attribute.HttpStatusCodeAttribute
        )
        return resp


class PlanetClient(QObject):
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

        return PlanetClient.__instance

    def __init__(self):
        if PlanetClient.__instance is not None:
            raise Exception("Singleton class")

        QObject.__init__(self)

        PlanetClient.__instance = self

        os.environ["PL_AUTH_PROFILE"] = PROFILE_NAME

        # Login
        self.auth = None
        self.session = None
        self.mosaics_client = None
        self.client = None

        self._user_quota = {
            "enabled": False,
            "sqkm": 0.0,
            "used": 0.0,
        }

        self._psscene_asset_types = None
        self._item_types = None
        self._bundles = None
        self._asset_types = {}
        # self.dispatcher.session.mount("https://", QGISAdapter())

    @pyqtSlot()
    def _show_offline_message(self):
        from ..pe_utils import PLANET_COLOR, iface

        if QGISAdapter._message_bar_item is None:
            msg = getattr(QGISAdapter, "_offline_msg", "Cannot access the internet.")
            QGISAdapter._message_bar_item = iface.messageBar().createMessage(
                "Planet Explorer",
                msg,
            )
            QGISAdapter._message_bar_item.setStyleSheet(
                "QgsMessageBarItem {{ background-color: rgb({r},{g},{b}); "
                "color: white; }}".format(
                    r=PLANET_COLOR.red(), g=PLANET_COLOR.green(), b=PLANET_COLOR.blue()
                )
            )
            iface.messageBar().pushWidget(
                QGISAdapter._message_bar_item, Qgis.MessageLevel.Warning, 0
            )

    @pyqtSlot()
    def _clear_offline_message(self):
        from qgis.PyQt import sip

        from ..pe_utils import iface

        if QGISAdapter._message_bar_item is not None:
            try:
                if not sip.isdeleted(QGISAdapter._message_bar_item):
                    iface.messageBar().popWidget(QGISAdapter._message_bar_item)
            except RuntimeError:
                pass
            QGISAdapter._message_bar_item = None

    def get_auth_context(self):
        """Create auth context to use to log in to Planet API"""
        if not self.auth:
            # This is a placeholder until a custom Client ID is provided
            # TODO: Remove this once a custom Client ID is provided
            self.auth = Auth.from_user_default_session()
            """
            self.auth = Auth.from_oauth_user_device_code(
                client_id="__MUST_BE_APP_DEVELOPER_SUPPLIED__",
                requested_scopes=[
                    # Request access to Planet APIs
                    planet.PlanetOAuthScopes.PLANET,
                    # Request a refresh token so repeated browser logins are not required
                    planet.PlanetOAuthScopes.OFFLINE_ACCESS,
                ],
                profile_name=PROFILE_NAME,
                save_state_to_storage=True,
                )
            """
        return self.auth

    @waitcursor
    def complete_log_in(self, login_info):
        """
        Complete the login process started in the Authentication Dialog.
        """
        old_session = self.session

        self.auth.device_user_login_complete(login_info)

        self.session = Session(self.auth)
        self.mosaics_client = self.session.client("mosaics")
        self.client = Planet(self.session)

        if old_session != self.session:
            self.loginChanged.emit(True)

    def validate_credentials(self):
        """Validate the current credentials by making a simple API call."""
        log.debug("Validating Client ...")
        try:
            for _ in self.client.data.list_searches(limit=1):
                break
            log.debug("Success! Your Credentials are valid.")
        except (InvalidAPIKey, InvalidIdentity) as exc:
            raise LoginException from exc

    def log_out(self):
        """
        Logout of the Planet API by clearing the auth context and Planet SDK client.
        """
        old_session = self.session

        self.auth = None
        self.session = None
        self.mosaics_client = None
        self.client = None

        if old_session != self.session:
            self.loginChanged.emit(False)

    def is_initialized(self):
        """Returns True if the download engines are built and the token is active."""
        if not self.auth:
            self.get_auth_context()

        if self.auth and self.auth.is_initialized():
            if not self.client or not self.session:
                try:
                    self.session = Session(self.auth)
                    self.mosaics_client = self.session.client("mosaics")
                    self.client = Planet(self.session)
                except Exception:
                    return False
            try:
                self.validate_credentials()
                return True  # Success! The token on disk is alive and valid.
            except Exception as e:
                log.warning(f"Saved token found, but validation failed: {str(e)}")
                # Clear out invalid configuration state so a fresh login can fix it
                self.session = None
                self.mosaics_client = None
                self.client = None
                return False

        return False

    """
    def user(self):
        return self.p_user

    def api_key(self):
        if hasattr(self.auth, "value"):
            return self.auth.value
        return None

    def has_api_key(self):
        if hasattr(self.auth, "value"):
            return self.auth.value not in [None, "", API_KEY_DEFAULT]
        return False
    """
    '''
    def has_access_to_mosaics(self):
        url = self._url("basemaps/v1/moe and self.session is not None and self.asaics")
        params = {"_page_size": 1}
        response = self._get(url, api_models.Mosaics, params=params).get_body().get()
        return len(response) > 0

    def list_mosaic_series(self, name_contains=None):
        """List all available mosaic series
        :returns: :py:Class:`planet.api.models.JSON`
        """
        params = {}
        if name_contains:
            params["name__contains"] = name_contains
        url = self._url("basemaps/v1/series/")
        return self._get(url, api_models.Mosaics, params=params).get_body()

    @waitcursor
    def get_mosaics(self, name_contains=None):
        """List all available mosaics
        :returns: :py:Class:`planet.api.models.JSON`
        """
        params = {"v": "1.5", "_page_size": 10000}
        if name_contains:
            params["name__contains"] = name_contains
        url = self._url("basemaps/v1/mosaics")
        return self._get(url, api_models.Mosaics, params=params).get_body()

    def get_mosaics_for_series(self, series_id):
        url = self._url("basemaps/v1/series/{}/mosaics?v=1.5".format(series_id))
        return self._get(url, api_models.Mosaics).get_body()

    def get_quads_for_mosaic(self, mosaic, bbox=None, minimal=False):
        """List all available quad for a given mosaic
        :returns: :py:Class:`planet.api.models.JSON`
        """
        if isinstance(mosaic, str):
            mosaicid = mosaic
        else:
            mosaicid = mosaic["id"]

        url = self._url(
            f"basemaps/v1/mosaics/{mosaicid}/quads?bbox="
            f"{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}"
        )
        if bbox is None:
            if isinstance(mosaic, str):
                bbox = [-180, -85, 180, 85]
            else:
                bbox = mosaic["bbox"]
        bbox = (
            max(-180, bbox[0]),
            max(-84.99, bbox[1]),
            min(180, bbox[2]),
            min(84.99, bbox[3]),
        )
        url = url.format(lx=bbox[0], ly=bbox[1], ux=bbox[2], uy=bbox[3])
        if minimal:
            url += "&minimal=true"
        return self._get(url, api_models.MosaicQuads).get_body()

    def get_one_quad(self, mosaic):
        url = self._url(f'basemaps/v1/mosaics/{mosaic["id"]}/quads')
        params = {"_page_size": 1, "bbox": ",".join(str(v) for v in mosaic["bbox"])}
        response = self._get(url, api_models.MosaicQuads, params=params)
        quad = response.get_body().get().get("items")[0]
        return quad

    def get_items_for_quad(self, mosaicid, quadid):
        url = self._url(f"basemaps/v1/mosaics/{mosaicid}/quads/{quadid}/items")
        response = self._get(url, api_models.JSON)
        item_descriptions = []
        items = response.get_body().get().get("items")
        for item in items:
            if item["link"].startswith("https://api.planet.com"):
                response = self._get(item["link"], api_models.JSON)
                item_descriptions.append(response.get_body().get())

        return item_descriptions

    def create_order(self, request):
        api_key = PlanetClient.getInstance().api_key()
        url = self._url("compute/ops/orders/v2")
        headers = {"X-Planet-App": "qgis"}
        session = PlanetClient.getInstance().dispatcher.session
        res = session.post(url, auth=(api_key, ""), json=request, headers=headers)

        return res

    def update_search(self, request, searchid):
        body = json.dumps(request)
        return self.dispatcher.response(
            api_models.Request(
                self._url(f"data/v1/searches/{searchid}"),
                self.auth,
                body_type=api_models.JSON,
                data=body,
                method="PUT",
            )
        ).get_body()

    def delete_search(self, searchid):
        return self.dispatcher.response(
            api_models.Request(
                self._url(f"data/v1/searches/{searchid}"),
                self.auth,
                body_type=api_models.JSON,
                method="DELETE",
            )
        ).get_body()

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
            log.warning("No API key found for getting quota")
            return False

        # TODO: Catch errors
        # TODO: Switch to async call
        # response = self.dispatcher.dispatch_request(
        #     method="GET", url=QUOTA_URL, auth=self.auth)

        resp: api_models.JSON = self.dispatcher.response(
            api_models.Request(
                QUOTA_URL, auth=self.auth, body_type=api_models.JSON, method="GET"
            )
        ).get_body()

        resp_data = resp.get()
        log.debug(f"resp_data:\n{resp_data}")  # noqa: E231
        if not resp_data:
            log.warning("No response data found for getting quota")
            return False

        quota_keys = ["quota_enabled", "quota_sqkm", "quota_used"]
        has_quota_data = all([q in resp_data for q in quota_keys])

        if has_quota_data:
            quota_enabled = bool(resp_data["quota_enabled"])
            self._user_quota["enabled"] = quota_enabled
            self._user_quota["sqkm"] = resp_data["quota_sqkm"]
            self._user_quota["used"] = resp_data["quota_used"]
            log.debug(
                f""" Quota (sqkm)
              Enabled: {str(self.user_quota_enabled())}
              Size: {str(self.user_quota_size())}
              Used: {str(self.user_quota_used())}
              Remaining: {str(self.user_quota_remaining())}
            """
            )
        else:
            log.warning("No quota keys found in response for getting quota")
            return False

        return True

    def user_quota_enabled(self):
        return bool(self._user_quota["enabled"])

    def user_quota_size(self):
        return bool(self._user_quota["sqkm"])

    def user_quota_used(self):
        return bool(self._user_quota["used"])

    def user_quota_remaining(self):
        # if not self.update_user_quota():
        #     return None

        if self.user_quota_enabled():
            return float(self._user_quota["sqkm"]) - float(self._user_quota["used"])

        return None

    def asset_types_for_item_type(self, item_type):
        if item_type not in self._asset_types:
            url = self._url(f"data/v1/item-types/{item_type}/asset-types")
            asset_types = (
                self._get(url, api_models.JSON).get_body().get()["asset_types"]
            )
            self._asset_types[item_type] = asset_types
        return self._asset_types[item_type]

    def asset_types_for_item_type_as_dict(self, item_type):
        asset_types = self.asset_types_for_item_type(item_type)
        return {a["id"]: a for a in asset_types}

    def psscene_asset_types_for_nbands(self, nbands):
        asset_types = self.asset_types_for_item_type("PSScene")
        return [
            asset["id"]
            for asset in asset_types
            if "bands" in asset and len(asset.get("bands")) >= nbands
        ]

    def item_types(self):
        if self._item_types is None:
            url = self._url("data/v1/item-types/")
            self._item_types = (
                self._get(url, api_models.JSON).get_body().get()["item_types"]
            )
            self._item_types = [v for v in self._item_types if " " in v["display_name"]]
        return self._item_types

    def item_types_names(self):
        item_types = self.item_types()
        return {t["id"]: t["display_name"] for t in item_types}

    def bundles(self):
        url = "https://us-central1-planet-webapps-prod.cloudfunctions.net/productBundles/latest"
        if self._bundles is None:
            self._bundles = self._get(url, api_models.JSON).get_body().get()
        return self._bundles

    def bundles_for_item_type(self, item_type):
        bundles = self.bundles()
        bndls_per_it = {
            b["id"]: b
            for b in bundles[item_type]
            if b.get("fileType") != "NITF" and b.get("auxiliaryFiles") != "udm"
        }
        return bndls_per_it

    def bundles_for_item_type_and_permissions(self, item_type, permissions):
        bundles = self.bundles_for_item_type(item_type)

        permissions_cleaned = []
        for img_permissions in permissions:
            img_permissions_cleaned = []
            for p in img_permissions:
                match = ITEM_ASSET_DL_REGEX.match(p)
                if match is not None:
                    img_permissions_cleaned.append(match.group(1))
            permissions_cleaned.append(img_permissions_cleaned)

        allowed_bundles = {}
        for name, b in bundles.items():
            add_bundle = True
            assets = b.get("assets", [])
            for asset in assets:
                for img_permissions in permissions_cleaned:
                    if asset not in img_permissions:
                        add_bundle = False
            if add_bundle:
                allowed_bundles[name] = b

        return allowed_bundles


def tile_service_hash(item_type_ids: List[str]) -> Optional[str]:
    """
    :param item_type_ids: List of item Type:IDs
    :param api_key: API key string
    :return: Tile service hash that can be used in tile URLs
    """

    api_key = PlanetClient.getInstance().api_key()

    if not item_type_ids:
        log.debug("No item type:ids passed, skipping tile hash")
        return None

    item_type_ids.reverse()
    data = {"ids": ",".join(item_type_ids)}

    tile_url = TILE_SERVICE_URL.format("")

    session = PlanetClient.getInstance().dispatcher.session
    res = session.post(tile_url, auth=(api_key, ""), data=data)
    if res.ok:
        res_json = res.json()
        if "name" in res_json:
            return res_json["name"]
    else:
        log.debug(
            f"Tile service hash request failed:\n"  # noqa: E231
            f"status_code: {res.status_code}\n"  # noqa: E231
            f"reason: {res.reason}"
        )

    return None


def tile_service_url(
    item_type_ids: List[str], tile_hash: Optional[str] = None, service: str = "xyz"
) -> Optional[str]:
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
            log.debug("No item type:ids passed, skipping tile URL")
            return None
        tile_hash = tile_service_hash(item_type_ids)

    if not tile_hash:
        log.debug("No tile URL hash passed, skipping tile URL")
        return None

    from ..pe_utils import user_agent

    url = None
    if service.lower() == "wmts":
        tile_url = TILE_SERVICE_URL.format("")
        url = f"{tile_url}/wmts/{tile_hash}?api_key={api_key}"
    elif service.lower() == "xyz":
        tile_url = TILE_SERVICE_URL.format(secrets.randbelow(4))
        url = (
            f"{tile_url}/{tile_hash}/{{z}}/{{x}}/{{y}}?"
            f"api_key={api_key}"
            f"&ua={user_agent()}"
        )

    return url
    '''
