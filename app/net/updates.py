from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from ..core.updates import MANIFEST_URL, Release, trusted_url


class UpdateClient(QObject):
    release_ready = pyqtSignal(object)
    downloaded = pyqtSignal(object)
    failed = pyqtSignal(str)
    unavailable = pyqtSignal()
    progress = pyqtSignal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply = None
        self._directory: Path | None = None
        self._file = None
        self._release: Release | None = None
        self._body = bytearray()
        self._size = 0
        self._redirects = 0
        self._hash = hashlib.sha256()

    @property
    def busy(self) -> bool:
        return self._reply is not None

    def check(self) -> None:
        self.cancel()
        self._request(MANIFEST_URL)

    def download(self, release: Release) -> None:
        self.cancel()
        try:
            # Revalidate even when called by a consumer other than the manifest parser.
            release.validate()
            self._directory = Path(tempfile.mkdtemp(prefix="playgrounds-update-"))
            self._file = (self._directory / "update.msi").open("wb")
            self._release = release
            self._request(release.url)
        except (OSError, ValueError) as exc:
            self._fail(str(exc))

    def _request(self, url: str) -> None:
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", b"Playgrounds-Updater")
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setTransferTimeout(30_000)
        self._reply = self._manager.get(request)
        self._reply.readyRead.connect(self._read)
        self._reply.finished.connect(self._finished)
        self._reply.downloadProgress.connect(self._progress)

    def _progress(self, received: int, total: int) -> None:
        if total > 0:
            self.progress.emit(min(100, received * 100 // total))

    def _read(self) -> None:
        reply = self._reply
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status != 200:
            reply.readAll()
            return
        data = bytes(reply.readAll())
        self._size += len(data)
        limit = 512 * 1024 * 1024 if self._release else 1024 * 1024
        if self._size > limit:
            self._fail(self.tr("Update response exceeds the allowed size."))
            return
        try:
            if self._file:
                self._file.write(data)
                self._hash.update(data)
            else:
                self._body.extend(data)
        except OSError as exc:
            self._fail(self.tr("Could not save update: {detail}").format(detail=exc))

    def _finished(self) -> None:
        self._read()
        reply, self._reply = self._reply, None
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        target = reply.attribute(QNetworkRequest.Attribute.RedirectionTargetAttribute)
        error, reason = reply.error(), reply.errorString()
        url = reply.url()
        reply.deleteLater()
        if status in (301, 302, 303, 307, 308) and target is not None:
            destination = url.resolved(target).toString()
            if self._redirects >= 5 or not trusted_url(destination, redirect=True):
                self._fail(self.tr("Update redirected to an untrusted destination or too many times."))
                return
            self._redirects += 1
            self._request(destination)
            return
        if status != 200 or error != QNetworkReply.NetworkError.NoError:
            if status == 404 and self._release is None:
                self.cancel()
                self.unavailable.emit()
                return
            self._fail(self.tr("Update request failed (HTTP {status}): {detail}").format(
                status=status or self.tr("n/a"), detail=reason,
            ))
            return
        try:
            if self._release:
                self._file.close()
                self._file = None
                if self._hash.hexdigest() != self._release.sha256.lower():
                    raise ValueError(self.tr("Installer checksum mismatch. Please download again."))
                self.downloaded.emit(self._directory / "update.msi")
            else:
                self.release_ready.emit(Release.parse(bytes(self._body)))
        except (OSError, ValueError, UnicodeError) as exc:
            self._fail(self.tr("Invalid update: {detail}").format(detail=exc))

    def detach_download(self) -> None:
        """Transfer temporary-directory ownership to the installer helper."""
        self._directory = None

    def cancel(self) -> None:
        reply, self._reply = self._reply, None
        if reply is not None:
            reply.readyRead.disconnect(self._read)
            reply.finished.disconnect(self._finished)
            reply.downloadProgress.disconnect(self._progress)
            reply.abort()
            reply.deleteLater()
        if self._file:
            self._file.close()
            self._file = None
        if self._directory:
            shutil.rmtree(self._directory, ignore_errors=True)
            self._directory = None
        self._body.clear()
        self._release = None
        self._hash = hashlib.sha256()
        self._size = self._redirects = 0

    def _fail(self, message: str) -> None:
        self.cancel()
        self.failed.emit(message)
