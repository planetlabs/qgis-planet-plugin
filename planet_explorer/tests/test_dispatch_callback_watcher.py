# -*- coding: utf-8 -*-
"""
***************************************************************************
    test_dispatch_callback_watcher.py
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
import sys
import logging
import json
from functools import partial
from typing import (
    Optional,
)

# noinspection PyPackageRequirements
from requests import Response as ReqResponse

# noinspection PyPackageRequirements
from PyQt5 import uic
# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    pyqtSlot,
)

# noinspection PyPackageRequirements
from PyQt5.QtWidgets import (
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
)

# from planet.api import ClientV1
from planet.api import models as api_models
# from planet.api.exceptions import APIException, InvalidIdentity

from planet_explorer.planet_api.p_client import PlanetClient

plugin_path = os.path.split(os.path.dirname(__file__))[0]

if __name__ == "__main__":
    print(plugin_path)
    sys.path.insert(0, plugin_path)
    # noinspection PyUnresolvedReferences
    from planet_explorer.planet_api.p_network import (
        PlanetCallbackWatcher,
        dispatch_callback,
    )
else:
    from ..planet_api.p_network import (
        PlanetCallbackWatcher,
        dispatch_callback,
    )
    # from ..planet_api import p_client

DLG_WIDGET, DLG_BASE = uic.loadUiType(
    os.path.join(plugin_path, 'ui', 'test_dispatch_callback_watcher.ui'),
    from_imports=True, import_from=f'{os.path.basename(plugin_path)}',
    resource_suffix=''
)

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

QUOTA_URL = 'https://api.planet.com/auth/v1/experimental' \
            '/public/my/subscriptions'
QUICK_SEARCH_URL = 'https://api.planet.com/data/v1/quick-search'

search_request = json.loads('''{"item_types": ["PSScene4Band"], 
    "filter": {"type": "AndFilter", "config": [{"field_name": "geometry", 
    "type": "GeometryFilter", "config": {"type": "Polygon", "coordinates": [
    [[-124.60010884388858, 36.207866384307614], [-119.61878664869495, 
    36.207866384307614], [-119.61878664869495, 39.705780131667844], 
    [-124.60010884388858, 39.705780131667844], [-124.60010884388858, 
    36.207866384307614]]]}}, {"field_name": "cloud_cover", "type": 
    "RangeFilter", "config": {"gte": 0, "lte": 100}}]}}''')


class AsyncDialog(DLG_BASE, DLG_WIDGET):
    btnStart: QPushButton
    btnCancel: QPushButton
    progressBar: QProgressBar
    teBody: QPlainTextEdit

    def __init__(self, parent=None, api_key=None):
        super().__init__(parent=parent)

        self.setupUi(self)
        self._api_key = api_key
        self._response: Optional[api_models.Response] = None
        self._watcher = PlanetCallbackWatcher(parent=self, timeout=5)
        self._watcher.responseRegistered.connect(self.dispatch_started)
        self._watcher.responseFinished['PyQt_PyObject'].connect(
            self.dispatch_finished)

        self.btnCancel.setEnabled(False)
        self.progressBar.hide()

        # self.teBody.setLineWrapMode(QPlainTextEdit.NoWrap)

        # noinspection PyUnresolvedReferences
        self.btnStart.clicked[bool].connect(self.do_dispatch_async_call)

        # noinspection PyUnresolvedReferences
        self.btnCancel.clicked[bool].connect(self.cancel_dispatch_async)

        # self._client = ClientV1(api_key=self._api_key)
        self._p_client = PlanetClient(api_key=self._api_key)

    @pyqtSlot()
    def dispatch_started(self):
        log.debug('Dispatch call started')
        self.btnCancel.setEnabled(True)
        self.progressBar.show()

    @pyqtSlot('PyQt_PyObject')
    def dispatch_finished(self, body):
        log.debug('Dispatch call finished')
        self.btnCancel.setEnabled(False)
        self.progressBar.hide()

        if hasattr(body, 'response'):
            resp: ReqResponse = body.response

            # Because f-strings can't cope with \n in {} expressions
            nl = '\n'
            headers = [f'    {k}:  {v}' for k, v in resp.headers.items()]
            history = [f'    {u}' for u in resp.history]

            self.teBody.setPlainText(
                f'Requests response data:\n'
                f'  url: {resp.url}\n'
                f'  ok: {resp.ok}\n'
                f'  status_code: {resp.status_code}\n'
                f'  reason: {resp.reason}\n'
                f'  elapsed: {resp.elapsed}\n'
                f'  apparent_encoding: {resp.apparent_encoding}\n'
                f'  headers:\n{nl.join(headers)}\n'
                f'  history:\n{nl.join(history)}\n'
                f'\n'
            )

            if resp.ok:
                self.teBody.appendPlainText(
                    f'Body: \n'
                    f'{json.dumps(body.get(), indent=2)}'
                )
        else:
            log.debug(f'No body with response returned')

    @pyqtSlot()
    def cancel_dispatch_async(self):
        self._watcher.cancel_response()

    @staticmethod
    def _params(kw):
        params = {}
        if 'page_size' in kw:
            params['_page_size'] = kw['page_size']
        if 'sort' in kw and kw['sort']:
            params['_sort'] = ''.join(kw['sort'])
        return params

    @pyqtSlot()
    def do_dispatch_async_call(self):

        # self._response = self._client.dispatcher.response(
        #     api_models.Request(
        #         QUOTA_URL,
        #         auth=self._client.auth,
        #         body_type=api_models.JSON,
        #         method='GET'
        #     )
        # )

        # body = json.dumps(search_request)
        # params = self._params({'page_size': 10})
        # self._response = self._client.dispatcher.response(
        #     api_models.Request(
        #         QUICK_SEARCH_URL,
        #         self._client.auth,
        #         params=params,
        #         body_type=api_models.Items,
        #         data=body,
        #         method='POST',
        #     )
        # )
        #
        # self._response.get_body_async(
        #     handler=partial(dispatch_callback, watcher=self._watcher))

        self._response = self._p_client.quick_search(
            search_request,
            page_size=250,
            callback=partial(dispatch_callback, watcher=self._watcher),
        )
        self._watcher.register_response(self._response)


if __name__ == "__main__":
    # noinspection PyPackageRequirements
    from PyQt5.QtWidgets import (
        QApplication,
        QDialog,
    )

    app = QApplication(sys.argv)

    apikey = os.getenv('PL_API_KEY')

    async_dlg: QDialog = AsyncDialog(api_key=apikey)

    async_dlg.show()

    sys.exit(app.exec_())
