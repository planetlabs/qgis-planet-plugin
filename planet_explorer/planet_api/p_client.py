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

import asyncio
import gzip
import logging
import os
import re
import secrets
import threading
from collections.abc import Coroutine
from pathlib import Path
from typing import (
    Any,
    TypeVar,
)

import requests
from planet import Auth, PlanetOAuthScopes, Session
from planet.exceptions import InvalidAPIKey, InvalidIdentity
from planet.sync.client import Planet
from planet_auth.storage_utils import _SOPSAwareFilesystemObjectStorageProvider
from qgis.core import Qgis, QgsApplication, QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QMetaObject, QObject, Qt, QUrl, pyqtSignal, pyqtSlot
from qgis.PyQt.QtNetwork import QNetworkRequest

from ..gui.pe_gui_utils import waitcursor
from .p_decorators import verify_async_runner, verify_mosaics_client, verify_session

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

ITEM_ASSET_DL_REGEX = re.compile(r"^assets\.(.*):download$")
ITEM_STREAM_REGEX = re.compile(r"^webtiles?:stream$")

QUOTA_URL = "https://api.planet.com/auth/v1/experimental" "/public/my/subscriptions"

TILE_SERVICE_URL = "https://tiles{0}.planet.com/data/v1/layers"

CLIENT_ID = "v4diVLw0ykprJeGEybxt3aiOVSwMVvjC"
PROFILE_NAME = "planet-qgis-plugin"

API_KEY_DEFAULT = "SKIP_ENVIRON"

T = TypeVar("T")


class LoginException(Exception):
    """Raised when the Planet API login process fails."""

    pass


class QGISAdapter:
    """Bridges the Planet SDK's HTTP requests through QGIS's network stack.

    Replaces the default requests transport so all network calls go through
    ``QgsBlockingNetworkRequest``, respecting QGIS proxy and SSL settings.
    Displays a message bar item when the connection is lost and clears it
    when connectivity is restored.
    """

    _offline = False
    _message_bar_item = None

    def _make_network_request(
        self, breq: QgsBlockingNetworkRequest, request: requests.PreparedRequest
    ) -> int:
        """Execute the network request via QGIS blocking network stack.

        Args:
            breq (QgsBlockingNetworkRequest): The QGIS blocking network request.
            request (requests.PreparedRequest): The prepared HTTP request.

        Returns:
            int: Error code (0 = success).
        """
        if request.method == "GET":
            return breq.get(self._build_qnetwork_request(request))
        elif request.method == "POST":
            body = request.body
            if not isinstance(body, bytes):
                body = body.encode()
            return breq.post(self._build_qnetwork_request(request), body)
        return 0

    def _build_qnetwork_request(
        self, request: requests.PreparedRequest
    ) -> QNetworkRequest:
        """Build a QNetworkRequest from a prepared requests object.

        Args:
            request (requests.PreparedRequest): The prepared HTTP request.

        Returns:
            QNetworkRequest: The QGIS network request.
        """
        req = QNetworkRequest(QUrl(request.url))
        for h in request.headers:
            req.setRawHeader(h.encode(), request.headers[h].encode())
        req.setRawHeader("Accept-Encoding".encode(), "gzip".encode())
        return req

    def _get_offline_message(self, error: int, msg: str) -> str:
        """Get the appropriate offline message for the error.

        Args:
            error (int): Error code.
            msg (str): Error message from QGIS.

        Returns:
            str: User-facing message bar text.
        """
        msg_lower = msg.lower()
        if "ssl" in msg_lower or "tls" in msg_lower:
            if "proxy" in msg_lower:
                return (
                    "SSL/TLS error connecting to Planet via proxy. "
                    "Your proxy may be interfering with HTTPS. "
                    "Check Settings > Options > Network."
                )
            return (
                "SSL/TLS error connecting to Planet. If you are "
                "using a proxy, it may be interfering with HTTPS "
                "connections."
            )
        if "proxy" in msg_lower:
            return (
                "Proxy connection refused. Check your proxy "
                "settings under Settings > Options > Network."
            )
        if error == 2 or "timed out" in msg_lower or "timeout" in msg_lower:
            return (
                "Connection to Planet timed out. The plugin will "
                "resume automatically when connectivity is restored."
            )
        return (
            "Cannot access the internet. The plugin will resume "
            "automatically when connectivity is restored."
        )

    def _handle_network_error(self, error: int, msg: str) -> None:
        """Handle a network error by showing a message bar and raising an exception.

        Args:
            error (int): Error code.
            msg (str): Error message from QGIS.

        Raises:
            ConnectionError: If error code is 1.
            ConnectTimeout: If error code is 2.
            RequestException: If error code is 3.
        """
        if not QGISAdapter._offline:
            QGISAdapter._offline = True
            QGISAdapter._offline_msg = self._get_offline_message(error, msg)
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

    def _build_response(self, breq: QgsBlockingNetworkRequest) -> requests.Response:
        """Build a requests.Response from a completed QGIS network request.

        Args:
            breq (QgsBlockingNetworkRequest): The completed QGIS network request.

        Returns:
            requests.Response: The HTTP response.
        """
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

    def send(self, request: requests.PreparedRequest, **kwargs) -> requests.Response:
        """Execute a prepared HTTP request via QGIS's blocking network stack.

        Handles GET and POST methods. On network error, shows a QGIS message
        bar notification and raises the appropriate ``requests`` exception.

        Args:
            request (requests.PreparedRequest): The prepared HTTP request to send.
            **kwargs: Unused; present for ``requests`` transport API compatibility.

        Returns:
            requests.Response: The HTTP response with headers, status code, and content.
        """
        breq = QgsBlockingNetworkRequest()
        error = self._make_network_request(breq, request)

        if error > 0:
            self._handle_network_error(error, breq.errorMessage())

        if QGISAdapter._offline:
            QGISAdapter._offline = False
            QMetaObject.invokeMethod(
                PlanetClient.getInstance(),
                "_clear_offline_message",
                Qt.ConnectionType.QueuedConnection,
            )

        return self._build_response(breq)


class QGISProfileStorageProvider(_SOPSAwareFilesystemObjectStorageProvider):
    """Custom Planet storage provider inheriting directly from the SDK code,

    forcing the file storage root into the active QGIS profile directory.
    """

    def __init__(self):
        active_profile_dir = QgsApplication.qgisSettingsDirPath()
        if not bool(active_profile_dir):
            planet_auth_dir = Path.home() / ".planet"
            log.info(f"Using default Planet auth storage directory: {planet_auth_dir}")
        else:
            planet_auth_dir = Path(active_profile_dir)
            log.info(
                f"Using QGIS profile directory for Planet auth storage: {planet_auth_dir}"
            )
        super().__init__(root=planet_auth_dir)


class PlanetClient(QObject):
    """
    Wrapper class for ``planet`` Python package, to abstract calls and make it
    a Qt object.

    Manages authentication, session lifecycle, and all Planet API calls.
    Exposes both async (``_aget_*``) and synchronous (``get_*``) methods;
    sync methods block by running the coroutine on a dedicated ``AsyncRunner``.

    Signals:
        loginChanged (bool): Emitted when the login state changes.
            True on login, False on logout.
    """

    loginChanged = pyqtSignal(bool)

    __instance = None

    @staticmethod
    def getInstance():
        """Return the singleton ``PlanetClient`` instance, creating it if needed.

        Returns:
            PlanetClient: The singleton instance.
        """
        if PlanetClient.__instance is None:
            PlanetClient()

        return PlanetClient.__instance

    def __init__(self):
        """
        Initialize the singleton client.

        Raises:
            Exception: If this singleton class initialization is called
                more than once.
        """
        if PlanetClient.__instance is not None:
            raise Exception("Singleton class")

        QObject.__init__(self)

        PlanetClient.__instance = self

        os.environ["PL_AUTH_PROFILE"] = PROFILE_NAME
        self.profile_name = PROFILE_NAME

        # Base url needed for basemaps API
        self.base_url = "https://api.planet.com"

        # Login
        self.api_key = API_KEY_DEFAULT
        self.auth_storage_provider = None
        self.auth = None
        self.auth_storage_dir = None
        self.session = None
        self.mosaics_client = None
        self.client = None
        self.runner = None

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
        """Display a QGIS message bar item indicating loss of connectivity."""
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
        """Remove the offline connectivity message bar item if present."""
        from qgis.PyQt import sip

        from ..pe_utils import iface

        if QGISAdapter._message_bar_item is not None:
            try:
                if not sip.isdeleted(QGISAdapter._message_bar_item):
                    iface.messageBar().popWidget(QGISAdapter._message_bar_item)
            except RuntimeError:
                pass
            QGISAdapter._message_bar_item = None

    def get_auth_context(self) -> Auth:
        """Return the OAuth auth context, creating it if it does not exist.

        Returns:
            Auth: The initialized Planet OAuth auth object.
        """
        if not self.auth_storage_provider:
            self.auth_storage_provider = QGISProfileStorageProvider()
        if not self.auth:
            # NOTE: if profile name not provided profile defaults to client id
            self.auth = Auth.from_oauth_user_device_code(
                client_id=CLIENT_ID,
                requested_scopes=[
                    # Request access to Planet APIs
                    PlanetOAuthScopes.PLANET,
                    # Request a refresh token so repeated browser logins are not required
                    PlanetOAuthScopes.OFFLINE_ACCESS,
                ],
                profile_name=PROFILE_NAME,
                save_state_to_storage=True,
                storage_provider=self.auth_storage_provider,
            )
        if not self.auth_storage_dir:
            self.auth_storage_dir = (
                self.auth_storage_provider._storage_root / PROFILE_NAME
            )
        return self.auth

    @waitcursor
    def complete_log_in(self, login_info):
        """Complete the OAuth device code login flow and initialize the client.

        Finalizes the device code exchange, builds the API engines, fetches
        the user quota, and emits ``loginChanged`` if the session changed.

        Args:
            login_info: The login info object returned by the device code flow.
        """
        old_session = self.session

        self.auth.device_user_login_complete(login_info)

        self.build_engines()

        # WARNING: Use of API Keys is strongly discouraged in v3 of the
        # planet sdk but required here for tile urls to be added
        # to QGIS.
        # TODO: Find work around for tile urls and remove
        # this.
        self.api_key = self.get_api_key()

        self.update_user_quota()

        if old_session != self.session:
            self.loginChanged.emit(True)

    def validate_credentials(self):
        """Confirm the current credentials are accepted by the Planet API.

        Raises:
            LoginException: If the API key or identity is rejected.
        """
        log.debug("Validating Client ...")
        try:
            for _ in self.client.data.list_searches(limit=1):
                break
            log.debug("Success! Your Credentials are valid.")
        except (InvalidAPIKey, InvalidIdentity) as exc:
            raise LoginException from exc

    def log_out(self):
        """
        Logout of the Planet API by clearing the auth context and shut down all API engines.

        Emits ``loginChanged(False)`` if the session was active.
        """
        old_session = self.session

        self.api_key = None
        self.auth_storage_provider = None
        self.auth = None
        self.auth_storage_dir = None
        self.session = None
        self.mosaics_client = None
        self.client = None
        if self.runner is not None:
            self.runner.close()
            self.runner = None
        # TODO: full logout , file should go into QGIS profile in use
        # auth should revoke token server side and delete file
        if old_session != self.session:
            self.loginChanged.emit(False)

    def auth_is_valid(self) -> bool:
        """Return True if the auth context exists and is initialized.

        Returns:
            bool: True if auth is ready for use.
        """
        if not self.auth:
            return False

        return self.auth.is_initialized()

    def client_is_setup(self) -> bool:
        """Returns True if the download engines are built and the token is active.

        Returns:
            bool: True if the client is ready for API calls.
        """
        if not self.auth:
            self.get_auth_context()

        if not self.auth_is_valid():
            return False

        if self.client is None or self.mosaics_client is None or self.session is None:
            return False

        return True

    def build_engines(self) -> bool:
        """Initialize the session, mosaics client, Planet client, and async runner.

        Returns:
            bool: True on success, False if auth is invalid or initialization fails.
        """
        if not self.auth_is_valid():
            log.warning(
                "Cannot build engines: Authentication context is missing or invalid."
            )
            return False

        try:
            self.session = Session(self.auth)
            self.mosaics_client = self.session.client("mosaics")
            self.client = Planet(self.session)
            if self.runner is None:
                self.runner = AsyncRunner()
            return True
        except Exception as e:
            log.error(f"Failed to assemble client engine instances: {str(e)}")
            self.log_out()  # Clean up half-baked state safely
            return False

    async def _aget_one_mosaic(self) -> dict[str, Any] | None:
        try:
            mosaics = self.mosaics_client.list_mosaics()
            first_mosaic = await anext(mosaics, None)
            return first_mosaic
        except Exception:
            log.exception("Failed to get one mosaic")
            return None

    @verify_mosaics_client
    @verify_async_runner
    def has_access_to_mosaics(self) -> bool:
        """Return True if the current user has access to the mosaics.

        Returns:
            bool: True if mosaics are accessible.
        """
        first_mosaic = self.runner.run(self._aget_one_mosaic())

        return first_mosaic is not None

    async def _alist_mosaic_series(
        self, name_contains: str | None = None
    ) -> list[dict[str, Any]]:
        try:
            mosaic_series = self.mosaics_client.list_series(name_contains=name_contains)
            return [series async for series in mosaic_series]
        except Exception:
            log.exception(
                f"Failed to list available mosaic series with filter: {name_contains}"
            )
            return []

    @verify_mosaics_client
    @verify_async_runner
    def list_mosaic_series(
        self, name_contains: str | None = None
    ) -> list[dict[str, Any]]:
        """
        List available mosaic series, optionally filtered by name.

        Args:
            name_contains (str | None): Optional string to filter mosaic series by name.

        Returns:
            list[dict[str, Any]]: List of mosaic series as dictionaries.
        """
        name_filter = name_contains.strip() if name_contains else None

        return self.runner.run(self._alist_mosaic_series(name_filter))

    async def _aget_mosaics(
        self, name_contains: str | None = None
    ) -> list[dict[str, Any]]:
        try:
            mosaics = self.mosaics_client.list_mosaics(name_contains=name_contains)
            return [mosaic async for mosaic in mosaics]
        except Exception:
            log.exception(
                f"Failed to list available mosaics with filter: {name_contains}"
            )
            return []

    @waitcursor
    @verify_mosaics_client
    @verify_async_runner
    def get_mosaics(self, name_contains: str | None = None) -> list[dict[str, Any]]:
        """List available mosaics, optionally filtered by name.

        Args:
            name_contains (str | None): Substring to filter mosaic names by.

        Returns:
            list[dict[str, Any]]: List of mosaic dictionaries.
        """
        name_filter = name_contains.strip() if name_contains else None
        return self.runner.run(self._aget_mosaics(name_filter))

    async def _aget_mosaics_for_series(self, series_id: str) -> list[dict[str, Any]]:
        try:
            mosaics = self.mosaics_client.list_series_mosaics(series_id)
            return [mosaic async for mosaic in mosaics]
        except Exception:
            log.exception(f"Failed to list mosaics for the series with id {series_id}")
            return []

    @verify_mosaics_client
    @verify_async_runner
    def get_mosaics_for_series(self, series_id: str) -> list[dict[str, Any]]:
        """List all mosaics belonging to a specific series.

        Args:
            series_id (str): ID of the mosaic series.

        Returns:
            list[dict[str, Any]]: List of mosaic dictionaries.
        """
        return self.runner.run(self._aget_mosaics_for_series(series_id))

    async def _aget_mosaic(self, mosaic_name_or_id: str) -> dict[str, Any] | None:
        try:
            mosaic = await self.mosaics_client.get_mosaic(mosaic_name_or_id)
            return mosaic
        except Exception:
            log.exception(f"Failed to fetch mosaic with name/id {mosaic_name_or_id}")
            return None

    @verify_mosaics_client
    @verify_async_runner
    def get_mosaic(self, mosaic_name_or_id: str) -> dict[str, Any] | None:
        """Fetch a single mosaic by name or ID.

        Args:
            mosaic_name_or_id (str): Name or ID of the mosaic.

        Returns:
            dict[str, Any] | None: Mosaic dictionary, or None if not found.
        """
        return self.runner.run(self._aget_mosaic(mosaic_name_or_id))

    def _url(self, endpoint: str) -> str:
        """Build a full Planet API URL from a relative endpoint.

        Args:
            endpoint (str): Relative API endpoint path.

        Returns:
            str: Full URL.
        """
        return "{}/{}".format(self.base_url, endpoint)

    async def _aget(
        self, url: str, params: dict[Any, Any] | None = None
    ) -> dict[Any, Any]:
        try:
            if params:
                response = await self.session.request(
                    method="GET", url=url, params=params
                )
            else:
                response = await self.session.request(method="GET", url=url)
            return response.json()
        except Exception:
            log_base = f"Async raw GET request failed for URL: {url}"
            if params:
                log.exception(f"{log_base} with params: {params}")
            else:
                log.exception(log_base)
            raise

    @verify_session
    @verify_async_runner
    def _get(self, url: str, **params) -> dict[Any, Any]:
        """
        Sends a GET request to a Planet API url

        Args:
            url (str): Full URL to send the GET request to.
            **params: Optional query parameters to include in the request.

        Returns:
            dict[Any, Any] | None: JSON response as a dictionary, or None on failure.

        Example:
            self._get(url, minimal=True, page_size=50)
        """
        query_params = params if params else None
        return self.runner.run(self._aget(url, query_params))

    async def _apage_iterator(self, endpoint: str, key: str, params: dict[str, Any]):
        url = self._url(endpoint)
        counter = 1
        while url:
            if counter > 1:
                response_data = await self._aget(url=url)
            else:
                response_data = await self._aget(url=url, params=params)

            if response_data is None:
                break

            items = response_data.get(key, None)
            if items is None:
                break
            else:
                yield items

            links = response_data.get("_links", {})
            if "_next" in links:
                url = links["_next"]
                counter += 1
            else:
                break

    @verify_session
    @verify_async_runner
    def _consume_pages(self, endpoint: str, key: str, **params):
        """
        Walk a paginated Planet API endpoint, yielding individual items.

        Args:
            endpoint (str): Relative API endpoint to paginate.
            key (str): Key to extract items from the response.
            **params: Optional query parameters to include in the request.

        Yields:
            dict[str, Any]: Individual items across all pages.
        """
        async_gen = self._apage_iterator(endpoint, key, params)
        while True:
            try:
                page_items = self.runner.run(async_gen.__anext__())

                for item in page_items:
                    yield item

            except StopAsyncIteration:
                break

    async def _aget_one_quad(self, mosaic_id: str) -> dict[str, Any]:
        try:
            quads = self.mosaics_client.list_quads(mosaic_id, full_extent=True)
            first_quad = await anext(quads, {})
            return first_quad
        except Exception:
            log.debug(f"Failed to get one quad for the mosaic with id {mosaic_id}")
            return {}

    @verify_mosaics_client
    @verify_async_runner
    def get_one_quad(self, mosaic: str | dict[str, Any]) -> dict[str, Any]:
        """
        Fetch a single quad from a mosaic.

        Args:
            mosaic (str | dict[str, Any]): Mosaic ID or mosaic dictionary.

        Returns:
            dict[str, Any]: Quad as a dictionary, or empty dict if none found.
        """
        if isinstance(mosaic, str):
            mosaic_id = mosaic
        else:
            mosaic_id = mosaic["id"]

        return self.runner.run(self._aget_one_quad(mosaic_id))

    async def _ahas_access_to_quads(self) -> bool:
        """Return True if the current user can access quads.

        Returns:
            bool: True if at least one quad is accessible.
        """
        mosaic = await self._aget_one_mosaic()
        if not mosaic:
            return False

        mosaic_id = mosaic["id"]
        quad = await self._aget_one_quad(mosaic_id)
        return bool(quad)

    @verify_mosaics_client
    @verify_async_runner
    def has_access_to_quads(self) -> bool:
        """Check if the logged in user has access to quads

        Returns:
            bool: True if the user has access to at least one quad, False otherwise.
        """

        return self.runner.run(self._ahas_access_to_quads())

    # NOTE: User may have access to mosaics but unable to download the quads.
    # Using the SDK functions in this case throws an error. The quad functions
    # below use raw API calls using the SDK Session request module.
    # to be able to preview the quads even if a user cannot download them.
    def get_quads_for_mosaic(
        self,
        mosaic: str | dict[str, Any],
        bbox: list | None = None,
        minimal: bool = False,
    ) -> list[dict[str, Any]]:
        """List all quads for a mosaic, optionally clipped to a bounding box.

        Args:
            mosaic (str | dict[str, Any]): Mosaic ID or mosaic dictionary.
            bbox (list | None): Bounding box as [min_lon, min_lat, max_lon, max_lat].
                Defaults to the mosaic's full extent if omitted.
            minimal (bool): If True, return minimal quad metadata.

        Returns:
            list[dict[str, Any]]: List of quad dictionaries.
        """
        if isinstance(mosaic, str):
            mosaic_id = mosaic
        else:
            mosaic_id = mosaic["id"]

        if bbox is None:
            if isinstance(mosaic, str):
                bbox = [-180, -85, 180, 85]
            else:
                bbox = mosaic["bbox"]
        else:
            bbox = [
                max(-180, bbox[0]),
                max(-84.99, bbox[1]),
                min(180, bbox[2]),
                min(84.99, bbox[3]),
            ]

        bbox_str = "{lx},{ly},{ux},{uy}"
        bbox_str = bbox_str.format(lx=bbox[0], ly=bbox[1], ux=bbox[2], uy=bbox[3])

        endpoint = f"basemaps/v1/mosaics/{mosaic_id}/quads"
        key = "items"

        quads = self._consume_pages(endpoint, key, bbox=bbox_str, minimal=minimal)

        return list(quads)

    @verify_session
    @verify_async_runner
    def get_items_for_quad(self, mosaic_id: str, quad_id: str) -> list[dict[str, Any]]:
        """
        Fetch a mosaic's quad information. It fetches all items contributing to
        a specific quad.

        Args:
            mosaic_id (str): Mosaic ID.
            quad_id (str): Quad ID.

        Returns:
            list[dict[str, Any]]: List of item dictionaries.
        """
        endpoint = f"basemaps/v1/mosaics/{mosaic_id}/quads/{quad_id}/items"
        key = "items"
        items = self._consume_pages(endpoint, key)
        items = list(items)

        async def get_item_descriptions(
            items: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:
            item_descriptions = []
            for item in items:
                url = item["link"]
                response = await self._aget(url=url)
                item_descriptions.append(response)
            return item_descriptions

        return self.runner.run(get_item_descriptions(items))

    @pyqtSlot(result=bool)
    def update_user_quota(self) -> bool:
        """Fetch and cache the current user's area quota from the Planet API.

        Returns:
            bool: True if quota data was retrieved and cached, False otherwise.

        Example quota response:

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
        response = self._get(url=QUOTA_URL)
        if not response:
            log.warning("No response data found for getting quota")
            return False

        response_data = response[0]
        log.debug(f"resp_data:\n{response_data}")  # noqa: E231

        quota_keys = ["quota_enabled", "quota_sqkm", "quota_used"]
        has_quota_data = all([q in response_data for q in quota_keys])

        if has_quota_data:
            quota_enabled = bool(response_data["quota_enabled"])
            self._user_quota["enabled"] = quota_enabled
            self._user_quota["sqkm"] = response_data["quota_sqkm"]
            self._user_quota["used"] = response_data["quota_used"]
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

    def user_quota_enabled(self) -> bool:
        """Return True if the user's area quota is enabled.

        Returns:
            bool: True if quota tracking is active.
        """
        return bool(self._user_quota["enabled"])

    def user_quota_size(self) -> bool:
        """Return True if the user's quota size is enabled.

        Returns:
            bool: True if quota size tracking is active.
        """
        return bool(self._user_quota["sqkm"])

    def user_quota_used(self) -> bool:
        """Return True if the user's quota usage is enabled.

        Returns:
            bool: True if quota usage tracking is active.
        """
        return bool(self._user_quota["used"])

    def user_quota_remaining(self):
        """Return the user's remaining quota in square kilometres.

        Returns:
            float | None: Remaining quota in sqkm, or None if quota is not enabled.
        """
        # if not self.update_user_quota():
        #     return None

        if self.user_quota_enabled():
            return float(self._user_quota["sqkm"]) - float(self._user_quota["used"])

        return None

    async def aget_image_bytes(self, image_url: str) -> bytes | None:
        response = await self.session._client.request(method="GET", url=image_url)
        try:
            response.raise_for_status()
        except Exception as e:
            log.exception(
                f"Failed to fetch image from url: {image_url} due to: {str(e)}"
            )
            return None

        raw_bytes = response.content
        return raw_bytes

    @verify_session
    @verify_async_runner
    def get_image_bytes(self, image_url: str) -> bytes | None:
        """Fetch raw image bytes from a URL.

        Args:
            image_url (str): The URL of the image to fetch.

        Returns:
            bytes | None: Raw image bytes, or None if the request failed.
        """
        return self.runner.run(self.aget_image_bytes(image_url))

    def update_search(self, request: dict[str, Any], search_id: str) -> dict[str, Any]:
        """Update an existing saved search.

        Args:
            request (dict[str, Any]): The request data for updating the search.
            search_id (str): Saved search identifier.

        Returns:
            dict[str, Any]: Description of the saved search.

        """
        search = self.p_client.client.data.update_search(
            search_id=search_id,
            item_types=request["item_types"],
            search_filter=request["filter"],
            name=request["name"],
        )

        return search

    def create_search(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new saved structured item search.

        Args:
            request (dict[str, Any]): _description_

        Returns:
            dict[str, Any]: Description of the saved search.

        """

        return self.p_client.client.data.create_search(
            item_types=request["item_types"],
            search_filter=request["search_filter"],
            name=request["name"],
        )

    def asset_types_for_item_type(self, item_type: str) -> list[dict[str, Any]]:
        """Return the available asset types for a given item type.

        Args:
            item_type: The item type ID (e.g. ``"PSScene"``).

        Returns:
            A list of asset type objects as returned by the Planet Data API.
        """
        if item_type not in self._asset_types:
            url = self._url(f"data/v1/item-types/{item_type}/asset-types")
            response_data = self._get(url)
            asset_types = response_data["asset_types"]
            self._asset_types[item_type] = asset_types
        return self._asset_types[item_type]

    def asset_types_for_item_type_as_dict(
        self, item_type: str
    ) -> dict[str, dict[str, Any]]:
        """
        Return the available asset types for a given item type,
        keyed by asset type ID.

        Convenience wrapper around :meth:`asset_types_for_item_type`
        that transforms the list into a dictionary for O(1)
        lookups by asset type ID.

        Args:
            item_type: The item type ID (e.g. ``"PSScene"``).

        Returns:
            A mapping of asset type ID to asset type object
            (e.g. ``{"ortho_analytic_4b": {...}}``).

        """
        asset_types = self.asset_types_for_item_type(item_type)
        return {a["id"]: a for a in asset_types}

    def psscene_asset_types_for_nbands(self, nbands):
        """Return PSScene asset type IDs that have at least
        the specified number of bands.

        Args:
            nbands: Minimum number of bands required.

        Returns:
            A list of asset type IDs whose band count is greater
            than or equal to ``nbands``.
        """
        asset_types = self.asset_types_for_item_type("PSScene")
        return [
            asset["id"]
            for asset in asset_types
            if "bands" in asset and len(asset.get("bands")) >= nbands
        ]

    def item_types(self) -> list[dict[str, Any]]:
        """Return all available item types,
        filtered to those with a multi-word display name.

        Returns:
            A list of item type objects as returned by the Planet Data API.
        """
        if self._item_types is None:
            url = self._url("data/v1/item-types")
            response_data = self._get(url)
            self._item_types = response_data["item_types"]
            self._item_types = [v for v in self._item_types if " " in v["display_name"]]
        return self._item_types

    def item_types_names(self) -> dict[str, str]:
        """Return a mapping of item type ID to display name.

        Convenience wrapper around :meth:`item_types`.

        Returns:
            A mapping of item type ID to display name
            (e.g. ``{"PSScene": "PlanetScope Scene"}``).
        """
        item_types = self.item_types()
        return {t["id"]: t["display_name"] for t in item_types}

    def bundles(self) -> dict[str, Any]:
        """Return the available product bundles from Planet's bundle registry.

        Returns:
            A mapping of bundle ID to bundle definition, as returned by the
            Planet product bundles endpoint.
        """
        url = "https://us-central1-planet-webapps-prod.cloudfunctions.net/productBundles/latest"
        if self._bundles is None:
            self._bundles = self._get(url)
        return self._bundles

    def bundles_for_item_type(self, item_type: str) -> dict[str, Any]:
        """Return available product bundles for a given item type,
        keyed by bundle ID.

        Excludes NITF bundles and bundles whose auxiliary files are UDM-only.

        Args:
            item_type: The item type ID (e.g. ``"PSScene"``).

        Returns:
            A mapping of bundle ID to bundle definition.
        """
        bundles = self.bundles()
        bndls_per_it = {
            b["id"]: b
            for b in bundles[item_type]
            if b.get("fileType") != "NITF" and b.get("auxiliaryFiles") != "udm"
        }
        return bndls_per_it

    def bundles_for_item_type_and_permissions(
        self, item_type: str, permissions: list[list[str]]
    ) -> dict[str, Any]:
        """Return bundles for an item type that are downloadable given
        a set of asset permissions.

        Filters the available bundles for ``item_type`` to only those
        whose required assets are all present in every set of permissions
        provided. Permissions are parsed via ``ITEM_ASSET_DL_REGEX``
        to extract the asset type ID from each permission string.

        Args:
            item_type: The item type ID (e.g. ``"PSScene"``).
            permissions: A list of per-image permission lists,
                where each inner list contains raw permission strings
                (e.g. ``["assets.ortho_analytic_4b:download"]``).
                A bundle is included only if all its assets are permitted
                across every image.

        Returns:
            A mapping of bundle ID to bundle definition for bundles that
            are fully accessible under the provided permissions.
        """
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

    async def _apost(
        self, url: str, json_data: dict[Any, Any], params: dict[Any, Any] | None = None
    ) -> dict[Any, Any]:
        try:
            response = await self.session.request(
                method="POST", url=url, json=json_data, params=params
            )
            return response.json()
        except Exception:
            log.exception(
                f"Async raw POST request failed for URL: {url} with parameters: {params}"
            )
            return {}

    @verify_session
    @verify_async_runner
    def _post(self, url: str, json_data: dict[Any, Any], **params) -> dict[Any, Any]:
        """
        Sends a POST request to a Planet API url

        Args:
            url: Full URL to send the POST request to
            json_data: JSON data to include in the POST request
            params: Optional query parameters to include in the request

        Returns:
            dict[Any, Any]: JSON response as a dictionary, or empty dict on failure

        Example usage: self._post(url, json_data={"key": "value"}, minimal=True, page_size=50)
        """
        return self.runner.run(self._apost(url, json_data, params))

    @verify_mosaics_client
    @verify_async_runner
    def get_api_key(self):
        # WARNING: This is a very hacky way to get the api key
        # for the tile service url for QGIS.
        # TODO: Work around needed for QGIS to be able to authenticate
        # a tile service url using the planet auth object.
        if self.has_access_to_mosaics():
            first_mosaic = self.runner.run(self._aget_one_mosaic())
            tile_url = first_mosaic["_links"]["tiles"]
            api_key = tile_url.split("?")[-1].strip("api_key=")
            return api_key
        else:
            # TODO: API Key if user only has access to daily imagery
            pass

        return ""

    def has_api_key(self):
        if hasattr(self, "api_key"):
            return self.api_key not in [None, "", API_KEY_DEFAULT]
        return False

    async def _aget_stats(self, request: dict[str, Any]) -> dict:
        url = "https://api.planet.com/data/v1/stats"
        payload = {
            "item_types": request["item_types"],
            "filter": request["filter"],
            "interval": request["interval"],
        }
        response = await self.session.request(method="POST", url=url, json=payload)
        return response.json()

    @verify_session
    @verify_async_runner
    def stats(self, request: dict[str, Any]) -> dict:
        # NOTE: Using direct API call instead of SDK get_stats method due
        # SDK get_stats method breaking background stream.
        try:
            return self.runner.run(self._aget_stats(request))
        except Exception as e:
            log.error(request)
            log.exception(f"Failed to get stats: {e}")
            raise

    def quick_search(self, request: dict[str, Any], sort: str):

        item_types = request["item_types"]
        search_filter = request["filter"]
        return self.client.data.search(
            item_types, search_filter=search_filter, limit=0, sort=sort
        )


def tile_service_hash(item_type_ids: list[str]) -> str | None:
    """Return a tile service hash for the given item type IDs.

    Registers the provided items with the Planet tile service and returns
    the resulting hash, which can be used to construct tile URLs. Items are
    registered in reverse order. Returns ``None`` if the list is empty or
    if the request fails.

    Args:
        item_type_ids: List of item type:ID strings (e.g. ``["PSScene:20221003_002705_38_2461"]``).

    Returns:
        The tile service hash string, or ``None`` if registration failed or
        no IDs were provided.
    """
    p_client = PlanetClient.getInstance()

    if not item_type_ids:
        log.debug("No item type:ids passed, skipping tile hash")
        return None

    item_type_ids.reverse()
    data = {"ids": ",".join(item_type_ids)}

    tile_url = TILE_SERVICE_URL.format("")

    try:
        res_json = p_client._post(tile_url, json_data=data)
        if "name" in res_json:
            return res_json["name"]
    except Exception as e:
        log.debug(
            f"Tile service hash request failed:\n"  # noqa: E231
            f"reason: {e}"
        )

    return None


def tile_service_url(
    item_type_ids: list[str], tile_hash: str | None = None, service: str = "xyz"
) -> str | None:
    """Return a tile service URL for the given items.

    Constructs a tile URL for either XYZ or WMTS tile services. If no
    ``tile_hash`` is provided, one is obtained by calling :func:`tile_service_hash`
    with ``item_type_ids``. Returns ``None`` if neither a hash nor valid item IDs
    are available, or if the hash cannot be obtained.

    Args:
        item_type_ids: List of item type:ID strings (e.g. ``["PSScene:20221003_002705_38_2461"]``).
            Only used if ``tile_hash`` is not provided.
        tile_hash: Pre-computed tile service hash. If provided, ``item_type_ids`` is ignored.
        service: Tile service type, either ``"xyz"`` (default) or ``"wmts"``.
            XYZ URLs include a random subdomain for load balancing.

    Returns:
        The tile service URL string, or ``None`` if a hash could not be
        obtained or no IDs were provided.
    """
    p_client = PlanetClient.getInstance()

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
        url = f"{tile_url}/wmts/{tile_hash}?api_key={p_client.api_key}"
    elif service.lower() == "xyz":
        tile_url = TILE_SERVICE_URL.format(secrets.choice([0, 1, 2, 3]))
        url = (
            f"{tile_url}/{tile_hash}/{{z}}/{{x}}/{{y}}?"
            f"api_key={p_client.api_key}"
            f"&ua={user_agent()}"
        )

    return url


class AsyncRunner:
    """Runs async coroutines from synchronous code using a dedicated background thread.

    Manages a persistent event loop running in a daemon thread, allowing
    synchronous callers to execute coroutines and block until they complete.
    This avoids the need to create a new event loop per call and is safe to
    use from any thread.

    Example::

        runner = AsyncRunner()
        result = runner.run(some_coroutine())
        runner.close()

    The runner should be closed when no longer needed. It can also be used
    as a context manager if wrapped accordingly. Once closed, calls to
    :meth:`run` will raise a ``RuntimeError``.
    """

    def __init__(self) -> None:
        """Start the background event loop thread
        and block until it is ready."""
        self._closed = False
        self._ready = threading.Event()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._start_loop,
            name="AsyncRunner",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait()

    def _start_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        """Submit a coroutine to the background event
        loop and block until it completes.

        Args:
            coro: The coroutine to execute.

        Returns:
            The return value of the coroutine.

        Raises:
            RuntimeError: If the runner has been closed.
        """
        if self._closed:
            raise RuntimeError(
                "Async runner is closed. "
                "Reconnect or reinitialize the client before making requests."
            )

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def close(self) -> None:
        """Stop the background event loop and join the thread.

        Safe to call multiple times.
        Subsequent calls after the first are no-ops.
        """
        if self._closed:
            return

        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
