from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PyQt6.QtCore import QEventLoop, QSettings, QTimer
from PyQt6.QtWidgets import QMessageBox

from app.core.config import Config
from app.net.models import ModelDiscovery, parse_models
from app.ui import theme
from app.ui.settings_dialog import SettingsDialog


def test_parse_models_deduplicates_and_sorts() -> None:
    body = json.dumps({"data": [{"id": "beta"}, {"id": "alpha"}, {"id": "beta"}, {}, {"id": 7}]}).encode()
    assert parse_models(body) == ["alpha", "beta"]


@pytest.mark.parametrize("body", [b"<html>Error</html>", b"[]", b'{"data":"wrong"}'])
def test_invalid_models_payload(body) -> None:
    with pytest.raises(ValueError):
        parse_models(body)


@contextmanager
def model_server(status=200, body=b'{"data":[{"id":"remote-model"}]}'):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get("Authorization")))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if status == 302:
                self.send_header("Location", "/not-allowed")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def fetch_result(client, url):
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    results, errors = [], []
    client.models_ready.connect(lambda models: (results.append(models), loop.quit()))
    client.failed.connect(lambda message: (errors.append(message), loop.quit()))
    timer.start(5000)
    client.fetch(url, "test-token")
    loop.exec()
    timer.stop()
    client.cancel()
    assert results or errors, "Model discovery timed out"
    return results, errors


def test_discovery_fetches_with_authorization(qt_app) -> None:
    with model_server() as (url, requests):
        client = ModelDiscovery()
        results, errors = fetch_result(client, url)
        assert results == [["remote-model"]]
        assert not errors
        assert requests == [("/v1/models", "Bearer test-token")]


def test_settings_fetch_only_persists_after_explicit_save(qt_app, workdir, credentials, monkeypatch) -> None:
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    with model_server() as (url, requests):
        config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
        dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
        original = config.active_profile()
        dialog._base_url.setText(url)
        dialog._key.setText("test-token")
        dialog._key.setModified(True)
        dialog.show()
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        dialog._discovery.models_ready.connect(loop.quit)
        dialog._discovery.failed.connect(loop.quit)
        try:
            timer.start(5000)
            dialog._fetch_button.click()
            loop.exec()
            assert not dialog.connections_saved, dialog._status.text()
            assert dialog.isVisible()
            assert dialog._save_button.isEnabled()
            assert requests == [("/v1/models", "Bearer test-token")]
            assert config.active_profile() == original
            assert not credentials.secrets
            assert dialog._save()
            assert dialog.connections_saved
            assert config.active_profile().base_url == url
            assert config.active_profile().model == "remote-model"
            assert config.active_profile().models == ["remote-model"]
            assert credentials.get_secret(config.active_profile().credential_name) == "test-token"
        finally:
            timer.stop()
            if dialog.isVisible():
                dialog.reject()
        reopened = SettingsDialog(config, credentials, theme.tokens_for("dark"))
        assert reopened._model.currentText() == "remote-model"
        assert reopened._available_models == ["remote-model"]
        reopened.reject()


@pytest.mark.parametrize("status,body", [(401, b'{"error":{"message":"Invalid key"}}'), (200, b"not-json"), (302, b"")])
def test_model_discovery_errors_and_redirects(qt_app, status, body) -> None:
    with model_server(status, body) as (url, requests):
        results, errors = fetch_result(ModelDiscovery(), url)
        assert not results
        assert errors
        assert len(requests) == 1


def test_cancel_releases_request_without_signals(qt_app) -> None:
    client = ModelDiscovery()
    results = []
    client.models_ready.connect(results.append)
    client.failed.connect(results.append)
    client.fetch("http://127.0.0.1:9/v1", "test-token")
    client.cancel()
    qt_app.processEvents()
    assert not client.busy
    assert not results
