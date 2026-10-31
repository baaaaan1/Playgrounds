from __future__ import annotations

import json
import logging
from typing import Any

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from ..core.providers.base import Provider
from .sse import SSEEvent, SSEParser

log = logging.getLogger(__name__)

_STATUS_HINTS = {
    400: "Permintaan ditolak server",
    401: "API key tidak valid atau belum diatur",
    402: "Kuota/kredit provider habis",
    403: "Akses ditolak untuk model atau key ini",
    404: "Endpoint atau model tidak ditemukan",
    408: "Server timeout",
    413: "Konteks percakapan terlalu panjang",
    429: "Rate limit tercapai, coba lagi sebentar",
    500: "Server provider error",
    502: "Bad gateway dari provider",
    503: "Layanan provider tidak tersedia",
    504: "Gateway timeout dari provider",
}


def error_message(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except ValueError:
        return text[:200]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message[:300]
        if isinstance(error, str):
            return error[:300]
        message = payload.get("message")
        if isinstance(message, str):
            return message[:300]
    return text[:200]


class StreamClient(QObject):
    """Streams chat completions over SSE using QNetworkAccessManager."""

    delta = pyqtSignal(str)
    completed = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._parser = SSEParser()
        self._provider: Provider | None = None
        self._error_body = bytearray()
        self._done = False

    @property
    def busy(self) -> bool:
        return self._reply is not None

    def start(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        provider: Provider,
    ) -> None:
        self.abort()
        self._provider = provider
        self._parser = SSEParser()
        self._error_body = bytearray()
        self._done = False

        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"Accept", b"text/event-stream")
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"
        )
        for name, value in headers.items():
            request.setRawHeader(name.encode("utf-8"), value.encode("utf-8"))
        request.setTransferTimeout(120_000)

        body = json.dumps(payload).encode("utf-8")
        log.info("POST %s (model=%s)", url, payload.get("model"))
        self._reply = self._manager.post(request, body)
        self._reply.readyRead.connect(self._on_ready_read)
        self._reply.finished.connect(self._on_finished)

    def abort(self) -> None:
        reply, self._reply = self._reply, None
        if reply is None:
            return
        for signal, slot in (
            (reply.readyRead, self._on_ready_read),
            (reply.finished, self._on_finished),
        ):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
        reply.abort()
        reply.deleteLater()

    def _on_ready_read(self) -> None:
        reply = self._reply
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        chunk = bytes(reply.readAll())
        if not chunk:
            return
        if status is not None and int(status) >= 400:
            self._error_body.extend(chunk)
            return
        for event in self._parser.feed(chunk):
            self._handle_event(event)

    def _handle_event(self, event: SSEEvent) -> None:
        data = event.data.strip()
        if not data or self._done:
            return
        if data == "[DONE]":
            self._done = True
            return
        if self._provider is None:
            return
        delta = self._provider.parse_delta(data)
        if delta:
            self.delta.emit(delta)

    def _on_finished(self) -> None:
        reply = self._reply
        if reply is None:
            return
        self._reply = None
        try:
            tail = bytes(reply.readAll())
        except RuntimeError:
            tail = b""
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        status_code = int(status) if status is not None else None
        error = reply.error()
        error_string = reply.errorString()
        reply.deleteLater()

        if tail:
            if status_code is not None and status_code >= 400:
                self._error_body.extend(tail)
            else:
                for event in self._parser.feed(tail):
                    self._handle_event(event)
                for event in self._parser.flush():
                    self._handle_event(event)

        if status_code is not None and status_code >= 400:
            self.failed.emit(self._describe_http(status_code, bytes(self._error_body)))
            return
        if error != QNetworkReply.NetworkError.NoError:
            self.failed.emit(self._describe_network(error, error_string))
            return
        self.completed.emit()

    @staticmethod
    def _describe_http(status: int, body: bytes) -> str:
        hint = _STATUS_HINTS.get(status, f"HTTP {status}")
        detail = error_message(body)
        return f"{hint}: {detail}" if detail else hint

    @staticmethod
    def _describe_network(error: QNetworkReply.NetworkError, message: str) -> str:
        if error == QNetworkReply.NetworkError.HostNotFoundError:
            return "Host tidak ditemukan. Periksa base URL dan koneksi internet."
        if error == QNetworkReply.NetworkError.ConnectionRefusedError:
            return "Koneksi ditolak. Pastikan server lokal berjalan."
        if error in (
            QNetworkReply.NetworkError.TimeoutError,
            QNetworkReply.NetworkError.OperationCanceledError,
        ):
            return "Permintaan timeout. Coba lagi."
        if error == QNetworkReply.NetworkError.SslHandshakeFailedError:
            return "TLS handshake gagal. Periksa sertifikat endpoint."
        return f"Koneksi gagal: {message or 'unknown error'}"
