from __future__ import annotations

import json

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from ..core.profiles import endpoint_url
from .client import error_message


def parse_models(body: bytes) -> list[str]:
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Expected an OpenAI-compatible model list: {data: [{id: ...}]}.")
    return sorted({
        item["id"].strip() for item in payload["data"]
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip()
    }, key=str.casefold)


class ModelDiscovery(QObject):
    models_ready = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._body = bytearray()

    @property
    def busy(self) -> bool:
        return self._reply is not None

    def fetch(self, base_url: str, api_key: str = "") -> None:
        self.cancel()
        try:
            url = endpoint_url(base_url, "models")
        except ValueError as exc:
            self.failed.emit(str(exc))
            return
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"Accept", b"application/json")
        if api_key:
            request.setRawHeader(b"Authorization", f"Bearer {api_key}".encode())
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        request.setTransferTimeout(15_000)
        self._body = bytearray()
        self._reply = self._manager.get(request)
        self._reply.readyRead.connect(self._read)
        self._reply.finished.connect(self._finished)

    def cancel(self) -> None:
        reply, self._reply = self._reply, None
        if reply is not None:
            reply.readyRead.disconnect(self._read)
            reply.finished.disconnect(self._finished)
            reply.abort()
            reply.deleteLater()

    def _read(self) -> None:
        if self._reply is None:
            return
        self._body.extend(bytes(self._reply.readAll()))
        if len(self._body) > 4 * 1024 * 1024:
            self.cancel()
            self.failed.emit("Model list exceeds the 4 MB limit.")

    def _finished(self) -> None:
        self._read()
        reply, self._reply = self._reply, None
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = reply.error()
        reason = reply.errorString()
        reply.deleteLater()
        if status is not None and 300 <= int(status) < 400:
            self.failed.emit("Endpoint redirected. Set its final base URL before fetching models.")
        elif error != QNetworkReply.NetworkError.NoError or status != 200:
            detail = error_message(bytes(self._body)) or reason
            self.failed.emit(f"Could not fetch models (HTTP {status or 'n/a'}): {detail}")
        else:
            try:
                models = parse_models(bytes(self._body))
            except (ValueError, UnicodeError) as exc:
                self.failed.emit(f"Invalid model list: {exc}")
            else:
                self.models_ready.emit(models)
