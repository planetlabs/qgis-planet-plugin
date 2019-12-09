# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_network.py
    ---------------------
    Date                 : March 2017, August 2019
    Author               : Alex Bruy, Planet Federal
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
__date__ = 'August 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import logging
import json
# import urllib.request
import urllib.parse
# import urllib.error
# import tempfile

from qgis.PyQt.QtCore import (
    pyqtSignal,
    pyqtSlot,
    # Qt,
    QObject,
    QUrl,
    # QEventLoop,
)

# from qgis.PyQt.QtGui import (
#     QPixmap,
# )

from qgis.PyQt.QtNetwork import (
    QNetworkRequest,
    QNetworkReply,
)

from qgis.core import (
    QgsNetworkAccessManager,
    QgsAuthManager,
    # QgsFeatureRequest,
    # QgsFileDownloader,
)

# from qgiscommons2.settings import (
#     pluginSetting,
# )

# from .pe_plugin import P_E

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)

DEBUG = True


class ImageDownloadRequest(object):
    def __init__(self, url, fid, image_id, file_path, method="GET"):
        self.url = url
        self.fid = fid
        self.image_id = image_id
        self.file_path = file_path
        self.method = method


def _prepare_request(url, headers=None, auth_id=None):
    request = QNetworkRequest()

    # Avoid double quoting form QUrl
    url = urllib.parse.unquote(url)
    request.setUrl(QUrl(url))

    if headers is not None:
        # This fixes a weird error with compressed content not being
        # correctly inflated.
        # If you set the header on the QNetworkRequest you are basically
        # telling QNetworkAccessManager "I know what I'm doing, please
        # don't do any content encoding processing".
        # See: https://bugs.webkit.org/show_bug.cgi?id=63696#c1
        try:
            del headers["Accept-Encoding"]
        except KeyError:
            pass

        for k, v in list(headers.items()):
            request.setRawHeader(k.encode(), v.encode())

    if auth_id:
        QgsAuthManager.instance().updateNetworkRequest(request, auth_id)

    headers_out = ['{0} = {1}'.format(k, v) for k, v in headers.items()]
    log.debug(f'QNetworkRequest:\n{headers_out}')

    return request


class JsonDownloadHandler(QObject):

    finished = pyqtSignal()
    errored = pyqtSignal(str)
    aborted = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.reply = None
        self.json = None

    def abort(self):
        if self.reply:
            self.reply.abort()

    def post(self, url, headers, data=None, auth_id=None):
        self.json = None
        data = data.encode() if data is not None else None
        request = _prepare_request(url, headers, auth_id)
        # noinspection PyArgumentList
        self.reply = QgsNetworkAccessManager.instance().post(request, data)

        if auth_id:
            QgsAuthManager.instance().updateNetworkReply(self.reply, auth_id)

        self.reply.finished.connect(self.json_reply_finished)

    def get(self, url, headers, auth_id=None):
        self.json = None

        request = _prepare_request(url, headers, auth_id)
        # noinspection PyArgumentList
        self.reply = QgsNetworkAccessManager.instance().get(request)

        if auth_id:
            QgsAuthManager.instance().updateNetworkReply(self.reply, auth_id)

        self.reply.finished.connect(self.json_reply_finished)

    def json_reply_finished(self):
        error = self.reply.error()

        if error == QNetworkReply.NoError:
            redirect = self.reply.attribute(
                QNetworkRequest.RedirectionTargetAttribute)
            if redirect is not None and redirect != self.reply.url():
                url = self.reply.url()
                if redirect.isRelative():
                    url = self.reply.url().resolved(redirect)

                log.debug(f'Redirected to {url.toString()}')
                self.reply.deleteLater()
                self.reply = None
                # noinspection PyArgumentList
                self.reply = QgsNetworkAccessManager.instance().get(
                    QNetworkRequest(url))
                self.reply.finished.connect(self.json_reply_finished)
                return

            status = self.reply.attribute(
                QNetworkRequest.HttpStatusCodeAttribute)
            msg = self.reply.attribute(
                QNetworkRequest.HttpReasonPhraseAttribute)
            log.debug(f'Request finished: {status} - {msg}')
            try:
                data = bytes(self.reply.readAll())
                self.json = json.loads(data)
            except Exception as e:
                log.debug(str(e))
            # noinspection PyUnresolvedReferences
            self.finished.emit()
        else:
            # report any errors except for the one we have caused
            # by cancelling the request
            if error != QNetworkReply.OperationCanceledError:
                msg = f'Network request failed: {self.reply.errorString()}'
                log.debug(msg)
                # noinspection PyUnresolvedReferences
                self.errored.emit(msg)
            else:
                # noinspection PyUnresolvedReferences
                self.aborted.emit()

            self.reply.deleteLater()
            self.reply = None


class ImageDownloadHandler(QObject):

    finished = pyqtSignal()
    errored = pyqtSignal(str)
    aborted = pyqtSignal()
    fileDownloaded = pyqtSignal(object)

    def __init__(self):
        super().__init__()

        self.replies = []

    def abort(self):
        for r in self.replies:
            r.abort()

        # noinspection PyUnresolvedReferences
        self.aborted.emit()

    def process_requests(self, requests, headers=None, auth_id=None):
        for r in requests:
            req = _prepare_request(r.url, headers, auth_id)
            req.setAttribute(QNetworkRequest.User, r.fid)
            req.setAttribute(QNetworkRequest.User + 1, r.image_id)
            req.setAttribute(QNetworkRequest.User + 2, r.file_path)

            if r.method.lower() == "get":
                # noinspection PyArgumentList
                reply = QgsNetworkAccessManager.instance().get(req)
            else:
                # noinspection PyArgumentList
                reply = QgsNetworkAccessManager.instance().post(req)

            if auth_id:
                QgsAuthManager.instance().updateNetworkReply(reply, auth_id)

            reply.finished.connect(self.image_reply_finished)
            self.replies.append(reply)

    @pyqtSlot()
    def image_reply_finished(self):
        reply = self.sender()
        error = reply.error()

        fid = reply.request().attribute(QNetworkRequest.User)
        image_id = reply.request().attribute(QNetworkRequest.User + 1)
        file_path = reply.request().attribute(QNetworkRequest.User + 2)

        if error == QNetworkReply.NoError:
            url = reply.attribute(QNetworkRequest.RedirectionTargetAttribute)
            if url is not None and url != reply.url():
                if url.isRelative():
                    url = reply.url().resolved(url)

                log.debug(f'Redirected to {url.toString()}')

                req = QNetworkRequest(url)
                req.setAttribute(QNetworkRequest.User, fid)
                req.setAttribute(QNetworkRequest.User + 1, image_id)
                req.setAttribute(QNetworkRequest.User + 2, file_path)

                self.replies.remove(reply)
                reply.deleteLater()
                # noinspection PyUnusedLocal
                reply = None

                # noinspection PyArgumentList
                reply = QgsNetworkAccessManager.instance().get(req)
                self.replies.append(reply)
                reply.finished.connect(self.image_reply_finished)
                return

            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            msg = reply.attribute(QNetworkRequest.HttpReasonPhraseAttribute)
            log.debug(f'Request finished: {status} - {msg}')

            with open(file_path, "wb") as f:
                data = reply.readAll()
                f.write(data)

            self.replies.remove(reply)
            reply.deleteLater()
            # noinspection PyUnusedLocal
            reply = None
            # noinspection PyUnresolvedReferences
            self.fileDownloaded.emit((fid, file_path))

            if len(self.replies) == 0:
                # noinspection PyUnresolvedReferences
                self.finished.emit()
        else:
            # report any errors except for the one we have caused
            # by cancelling the request
            if error != QNetworkReply.OperationCanceledError:
                msg = "Network request failed: {}".format(reply.errorString())
                log.debug(msg)
                # noinspection PyUnresolvedReferences
                self.errored.emit(msg)

                self.replies.remove(reply)
                reply.deleteLater()
                # noinspection PyUnusedLocal
                reply = None

                if len(self.replies) == 0:
                    # noinspection PyUnresolvedReferences
                    self.finished.emit()
