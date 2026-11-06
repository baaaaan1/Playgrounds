from __future__ import annotations

import json
import logging
from typing import Any

from PyQt6.QtCore import QCoreApplication, QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from ..core.providers.base import Provider
from .sse import SSEEvent, SSEParser

log = logging.getLogger(__name__)


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
        for name in ("message", "detail", "title"):
            message = payload.get(name)
            if isinstance(message, str) and message.strip():
                return message[:300]
    return text[:200]


class StreamClient(QObject):
    """Streams chat completions over SSE using QNetworkAccessManager."""

    delta = pyqtSignal(str)
    usage = pyqtSignal(object)
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
        self._stream_error = ""

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
        self._stream_error = ""

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
        if reply is None or (self.sender() is not None and self.sender() is not reply):
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
        if self._stream_error:
            message = self._stream_error
            self.abort()
            self.failed.emit(message)

    def _handle_event(self, event: SSEEvent) -> None:
        data = event.data.strip()
        if not data or self._done:
            return
        if data == "[DONE]":
            self._done = True
            return
        if self._provider is None:
            return
        try:
            payload = json.loads(data)
        except ValueError:
            payload = None
        if event.event == "error" or (isinstance(payload, dict) and payload.get("error")):
            self._stream_error = error_message(data.encode("utf-8")) or self.tr("The provider could not complete the response.")
            self._done = True
            return
        if not isinstance(payload, dict):
            return
        usage = payload.get("usage")
        if isinstance(usage, dict):
            counts = {}
            for source, target in (
                ("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens"),
                ("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
            ):
                value = usage.get(source)
                if type(value) is int and value >= 0:
                    counts[target] = value
            if counts:
                self.usage.emit(counts)
        delta = self._provider.parse_delta(data)
        if delta:
            self.delta.emit(delta)

    def _on_finished(self) -> None:
        reply = self._reply
        if reply is None or (self.sender() is not None and self.sender() is not reply):
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
        if status_code is None or status_code < 400:
            for event in self._parser.flush():
                self._handle_event(event)

        if self._stream_error:
            self.failed.emit(self._stream_error)
            return
        if status_code is not None and status_code >= 400:
            self.failed.emit(self._describe_http(status_code, bytes(self._error_body)))
            return
        if error != QNetworkReply.NetworkError.NoError:
            self.failed.emit(self._describe_network(error, error_string))
            return
        self.completed.emit()

    @staticmethod
    def _describe_http(status: int, body: bytes) -> str:
        detail = error_message(body)
        if (status == 404 and detail.casefold().startswith("function ")
                and "not found for account" in detail.casefold()):
            return QCoreApplication.translate(
                "StreamClient", "The provider's model deployment is unavailable for this API account. "
                "The model may be retired or access may be restricted. Choose another model or check "
                "access with the provider. Provider detail: {detail}",
            ).format(detail=detail)
        hints = {
            400: QCoreApplication.translate("StreamClient", "The server rejected the request"),
            401: QCoreApplication.translate("StreamClient", "The API key is invalid or not set"),
            402: QCoreApplication.translate("StreamClient", "The provider's quota or credits are exhausted"),
            403: QCoreApplication.translate("StreamClient", "Access denied for this model or API key"),
            404: QCoreApplication.translate(
                "StreamClient", "Endpoint or model not found. Check the base URL and choose a model "
                "available on this connection in Settings",
            ),
            408: QCoreApplication.translate("StreamClient", "The server timed out"),
            413: QCoreApplication.translate("StreamClient", "The conversation context is too long"),
            429: QCoreApplication.translate("StreamClient", "Rate limit reached. Please try again shortly"),
            500: QCoreApplication.translate("StreamClient", "Provider server error"),
            502: QCoreApplication.translate("StreamClient", "Bad gateway from the provider"),
            503: QCoreApplication.translate("StreamClient", "The provider's service is unavailable"),
            504: QCoreApplication.translate("StreamClient", "The provider's gateway timed out"),
        }
        hint = hints.get(status)
        if hint is None:
            hint = QCoreApplication.translate("StreamClient", "HTTP {status}").format(status=status)
        if not detail:
            return hint
        return QCoreApplication.translate("StreamClient", "{hint}: {detail}").format(
            hint=hint, detail=detail,
        )

    @staticmethod
    def _describe_network(error: QNetworkReply.NetworkError, message: str) -> str:
        if error == QNetworkReply.NetworkError.HostNotFoundError:
            return QCoreApplication.translate(
                "StreamClient", "Host not found. Check the base URL and your internet connection.",
            )
        if error == QNetworkReply.NetworkError.ConnectionRefusedError:
            return QCoreApplication.translate(
                "StreamClient", "Connection refused. Make sure the local server is running.",
            )
        if error in (
            QNetworkReply.NetworkError.TimeoutError,
            QNetworkReply.NetworkError.OperationCanceledError,
        ):
            return QCoreApplication.translate("StreamClient", "The request timed out. Please try again.")
        if error == QNetworkReply.NetworkError.SslHandshakeFailedError:
            return QCoreApplication.translate(
                "StreamClient", "TLS handshake failed. Check the endpoint's certificate.",
            )
        return QCoreApplication.translate("StreamClient", "Connection failed: {detail}").format(
            detail=message or QCoreApplication.translate("StreamClient", "Unknown error"),
        )
