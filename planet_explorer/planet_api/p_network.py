# -*- coding: utf-8 -*-
"""
***************************************************************************
    p_network.py
    ---------------------
    Date                 : August 2019
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
__date__ = 'August 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import logging

from typing import (
    Optional,
    # Union,
)

# # noinspection PyPackageRequirements
# from requests import (
#     Response as ReqResponse,
# )

# noinspection PyPackageRequirements
from PyQt5.QtCore import (
    pyqtSignal,
    pyqtSlot,
    QObject,
    QTimer,
)

from planet.api import models as api_models
# from planet.api.client import (
#     ClientV1,
# )
# from planet.api.dispatch import (
#     RequestsDispatcher,
# )

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

RESPONSE_TIMEOUT = 60


class PlanetCallbackWatcher(QObject):
    """
    Callback QObject watcher for `planet.api.dispatch` async operations.

    Creates a Qt signal interface for registered callback.

    To use, see `dispatch_callback()` below.
    """

    responseRegistered = pyqtSignal('PyQt_PyObject')
    responseRegisteredWithId = pyqtSignal(str, 'PyQt_PyObject')
    responseCancelled = pyqtSignal()
    responseCancelledWithId = pyqtSignal(str)
    responseTimedOut = pyqtSignal(int)  # response timeout in seconds
    responseTimedOutWithId = pyqtSignal(str, int)  # timeout in seconds
    responseFinished = pyqtSignal('PyQt_PyObject')
    responseFinishedWithId = pyqtSignal(str, 'PyQt_PyObject')

    timerShouldStop = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None,
                 timeout: int = RESPONSE_TIMEOUT,
                 watcher_id: Optional[str] = None):
        """
        :param parent: QObject parent
        :param timeout: Network timeout for request through receiving
        complete response, in seconds
        :param watcher_id: Id for watcher, usually an item id
        """
        super().__init__(parent=parent)

        self._response: Optional[api_models.Response] = None

        # For `requests` timeout, since none is set in planet.api dispatcher
        self._timeout = timeout
        self._timeout_ms = timeout * 1000
        self._timer = QTimer()
        self._timer.setInterval(self._timeout_ms)

        # noinspection PyUnresolvedReferences
        self._timer.timeout.connect(self._response_timed_out)

        # Signal bounce, for when this obj directly called from dispatch thread
        self.timerShouldStop.connect(self._stop_timer)

        self._id = watcher_id

    def id(self) -> str:
        return self._id

    def register_response(self, response) -> Optional[api_models.Response]:
        if response:
            self._response = response
            log.debug('Watcher registered response')
            self._start_timer()
            self.responseRegistered.emit(response)
            self.responseRegisteredWithId.emit(self._id, response)
            return response
        else:
            log.debug('No response to register')
            return None

    @pyqtSlot()
    @pyqtSlot(str)
    def cancel_response(self, item_key: Optional[str] = None) -> None:
        if item_key and item_key != self._id:
            return
        if self._response:
            self._stop_timer()
            self._response.cancel()
            log.debug('Watcher registered response cancelled')
            self.responseFinished.emit(None)
            self.responseFinishedWithId.emit(self._id, None)
        else:
            log.debug('No registered response to cancel')

        self.responseCancelled.emit()
        self.responseCancelledWithId.emit(self._id)

    def _start_timer(self) -> None:
        self._timer.start()
        log.debug('Watcher timer started')

    def time_remaining(self) -> int:
        remaining = self._timer.remainingTime()
        if remaining > 0:
            return int(remaining / 1000)  # in seconds
        return remaining

    def _stop_timer(self) -> None:
        self._timer.stop()
        log.debug('Watcher timer stopped')

    @pyqtSlot()
    def _response_timed_out(self) -> None:
        self.cancel_response()
        log.debug(f'Watcher response timed out after {self._timeout} seconds')
        self.responseTimedOut.emit(self._timeout)
        self.responseTimedOutWithId.emit(self._id, self._timeout)

    @pyqtSlot('PyQt_PyObject')
    def emit_finished(self, body) -> None:
        self.timerShouldStop.emit()
        self.responseFinished.emit(body)
        self.responseFinishedWithId.emit(self._id, body)


def dispatch_callback(*args, watcher: PlanetCallbackWatcher = None) -> None:
    """
    To use, pass an instance of PlanetCallbackWatcher as part of a
    `functools.partial(dispatch_callback, watcher=self._mywatcher)` function.

    See: `tests/test_dispatch_callback_watcher.py`

    :param args: At least one, which is response body from `requests`
    :param watcher: PlanetCallbackWatcher instance
    :rtype: None
    """

    if not watcher or not isinstance(
            watcher, (PlanetCallbackWatcher, PlanetWriteCallbackWatcher)):
        log.debug('No watcher passed, or not PlanetDispatchCallback instance')
        return

    if not args:
        log.debug('No body parameter passed')
        return
    body = args[0]

    log.debug('Emitting finished for body')
    watcher.emit_finished(body)


class PlanetWriteCallbackWatcher(PlanetCallbackWatcher):
    """
    Callback QObject watcher for `planet.api.dispatch` async operations that
    write to a file.

    Creates a Qt signal interface for registered callback.

    To use, see `dispatch_callback()` above.
    """

    callbackStarted = pyqtSignal('PyQt_PyObject')
    callbackWroteBytes = pyqtSignal(int, int)
    callbackFinished = pyqtSignal('PyQt_PyObject')
    responseCancelled = pyqtSignal()

    _body: Optional[api_models.Body]
    _started: bool
    _wrote_bytes: int
    _total_bytes: int
    _finished: bool

    _response: Optional[api_models.Response]

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent=parent)

# TODO: Adapt this older approach (callback as instance method does not work,
#       has to be callable function) to method for PlanetCallbackWatcher
#
#         self._set_defaults()
#
#     def _set_defaults(self):
#         self._body = None
#         self._started = False
#         self._wrote_bytes = 0
#         self._total_bytes = 0
#         self._finished = False
#         self._response = None
#
#     def callback(self, **kw):
#         """
#         As per... planet.api.models.Body#write...
#
#         The callback will be invoked 3 different ways:
#
#         * First as ``callback(start=self)``
#         * For each chunk of data written as
#           ``callback(wrote=chunk_size_in_bytes, total=all_byte_cnt)``
#         * Upon completion as ``callback(finish=self)
#
#         Note: `total` is running total, not final sum (until finished)
#
#         :param kw: Keyword args
#         :rtype: None
#         """
#         start = kw.pop('start', None)
#         wrote_bytes = kw.pop('wrote', 0)
#         total_bytes = kw.pop('total', 0)
#         finish = kw.pop('finish', False)
#
#         if start and not self._started:
#             self._body = start
#             self._started = True
#             # noinspection PyUnresolvedReferences
#             self.callbackStarted.emit()
#             log.debug('Callback started')
#             return
#
#         if (self._started and not self._finished and
#                 self._total_bytes > 0):
#             self._wrote_bytes = wrote_bytes
#             self._total_bytes = total_bytes
#             # noinspection PyUnresolvedReferences
#             self.callbackWroteBytes.emit(self._wrote_bytes,
#                                          self._total_bytes)
#             log.debug(f'Callback wrote bytes: '
#                       f'{self._wrote_bytes}, {self._total_bytes}')
#             return
#
#         if finish and not self._finished:
#             self._body = finish
#             self._finished = True
#             self._started = False
#             # noinspection PyUnresolvedReferences
#             self.callbackFinished.emit()
#             log.debug('Callback finished')
#             return
#
#     def started(self):
#         return self._started
#
#     def set_started(self, started):
#         self._started = started
#
#     def wrote_bytes(self):
#         return self._wrote_bytes
#
#     def set_wrote_bytes(self, wrote_bytes):
#         self._wrote_bytes = wrote_bytes
#
#     def total_bytes(self):
#         return self._total_bytes
#
#     def set_total_bytes(self, total_bytes):
#         self._total_bytes = total_bytes
#
#     def finished(self):
#         return self._finished
#
#     def set_finished(self, finished):
#         self._finished = finished
#
#     def response(self):
#         return self._response
#
#     def set_response(self, response):
#         self._response = response
#
#     def body(self):
#         if self._finished and self._body:
#             return self._body
#
#     def set_body(self, body):
#         self._body = body
#         return None
#
#     def cancel(self):
#         if not self._response:
#             log.debug('No response to cancel')
#             return
#
#         self._response.cancel()
#
#         # noinspection PyUnresolvedReferences
#         self.responseCancelled.emit()
#         log.debug('Response cancelled')
#
#         self._set_defaults()
#
#     def reset(self):
#         self._set_defaults()


def requests_response_metadata(resp) -> str:
    # Because f-strings can't cope with \n in {} expressions
    nl = '\n'
    headers = [f'    {k}:  {v}' for k, v in resp.headers.items()]
    history = [f'    {u}' for u in resp.history]
    return (
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
