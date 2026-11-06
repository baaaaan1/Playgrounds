from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, QSettings, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QDialog, QMessageBox

from app import __version__
from app.core import updates
from app.core.config import Config
from app.core.updates import MANIFEST_URL, RELEASES_URL, Release, trusted_url, verify_installer
from app.net.updates import UpdateClient
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog
from app.ui.theme import tokens_for
from app.ui.update_panel import UpdatePanel

MSI_URL = "https://github.com/baaaaan1/Playgrounds/releases/download/v0.2.0/Playgrounds-0.2.0-x64.msi"
PAYLOAD = b"test installer data"


def manifest(**changes):
    version = changes.get("version", "0.2.0")
    data = dict(version=version, url=MSI_URL.replace("0.2.0", str(version)), sha256=hashlib.sha256(PAYLOAD).hexdigest(), notes="Bug fixes")
    data.update(changes)
    return json.dumps(data).encode()


@pytest.mark.parametrize("changes", [
    {"version": "0.2.0-beta.1"}, {"version": None}, {"version": "256.0.0"}, {"sha256": "nope"},
    {"url": "http://github.com/baaaaan1/Playgrounds/releases/download/v1/a.msi"},
    {"url": "https://github.com/other/repo/releases/download/v1/a.msi"},
    {"url": MSI_URL.replace(".msi", ".exe")}, {"notes": []},
    {"url": MSI_URL.replace("v0.2.0/", "v0.3.0/")},
    {"url": MSI_URL.replace("Playgrounds-0.2.0", "Playgrounds-0.3.0")},
    {"url": MSI_URL.replace("x64.msi", "arm64.msi")},
    {"url": MSI_URL.replace("download/v0.2.0", "latest/download")},
    {"url": MSI_URL + "?download=1"}, {"url": MSI_URL + "#asset"},
])
def test_rejects_invalid_manifest(changes):
    with pytest.raises(ValueError):
        Release.parse(manifest(**changes))


def test_release_comparison_and_checksum(workdir):
    release = Release.parse(manifest(version="0.10.0"))
    assert release.newer_than("0.9.0")
    assert not release.newer_than("0.10.0")
    assert not release.newer_than("1.0.0")
    path = workdir / "installer.msi"
    with pytest.raises(OSError):
        verify_installer(path, release)


@pytest.mark.parametrize("prefix", ["", "v"])
def test_release_page_matches_versioned_msi(prefix):
    url = MSI_URL.replace("/v0.2.0/", f"/{prefix}0.2.0/")
    release = Release.parse(manifest(url=url))
    assert release.page_url == f"{RELEASES_URL}tag/{prefix}0.2.0"


def test_installer_verification_revalidates_direct_release_objects(workdir):
    path = workdir / "update.msi"
    path.write_bytes(PAYLOAD)
    checksum = hashlib.sha256(PAYLOAD).hexdigest().upper()
    verify_installer(path, Release("0.2.0", MSI_URL, checksum))
    with pytest.raises(ValueError, match="match the version"):
        verify_installer(path, Release("0.3.0", MSI_URL, checksum))


@pytest.mark.parametrize("url", [
    "https://github.com.evil.test/baaaaan1/Playgrounds/releases/download/v1/a.msi",
    "https://user:pass@github.com/baaaaan1/Playgrounds/releases/download/v1/a.msi",
    "https://github.com:444/baaaaan1/Playgrounds/releases/download/v1/a.msi",
    "https://evil.test/a.msi", "file:///C:/a.msi",
])
def test_untrusted_urls(url):
    assert not trusted_url(url, redirect=True)


class Reply(QObject):
    readyRead = pyqtSignal()
    finished = pyqtSignal()
    downloadProgress = pyqtSignal(int, int)

    def __init__(self, request):
        super().__init__()
        self.request = request
        self.body = b""
        self.status = 200
        self.target = None
        self.aborted = False

    def attribute(self, key):
        if key == QNetworkRequest.Attribute.HttpStatusCodeAttribute:
            return self.status
        if key == QNetworkRequest.Attribute.RedirectionTargetAttribute:
            return self.target

    def readAll(self):
        data, self.body = self.body, b""
        return data

    def url(self):
        return self.request.url()

    def error(self):
        return QNetworkReply.NetworkError.NoError

    def errorString(self):
        return "test response"

    def abort(self):
        self.aborted = True


class Manager:
    def __init__(self):
        self.replies = []

    def get(self, request):
        reply = Reply(request)
        self.replies.append(reply)
        return reply


@pytest.fixture()
def client(qt_app):
    updater = UpdateClient()
    updater._manager = Manager()
    yield updater
    updater.cancel()


def respond(client, body=b"", status=200, target=None):
    reply = client._manager.replies[-1]
    reply.body, reply.status = body, status
    reply.target = QUrl(target) if target else None
    reply.readyRead.emit()
    reply.finished.emit()
    return reply


def test_manifest_redirects_and_download_checksum(client):
    releases, downloads, errors = [], [], []
    client.release_ready.connect(releases.append)
    client.downloaded.connect(downloads.append)
    client.failed.connect(errors.append)
    client.check()
    assert client._manager.replies[-1].request.url().toString() == MANIFEST_URL
    respond(client, status=302, target=MSI_URL.replace("Playgrounds-0.2.0-x64.msi", "update.json"))
    respond(client, manifest())
    assert len(releases) == 1 and not errors
    client.download(releases[0])
    respond(client, status=302, target="https://release-assets.githubusercontent.com/release.msi?token=test")
    respond(client, PAYLOAD)
    assert downloads[0].read_bytes() == PAYLOAD
    verify_installer(downloads[0], releases[0])
    directory = downloads[0].parent
    client.cancel()
    assert not directory.exists()


def test_mismatch_deletes_download(client):
    errors, downloads = [], []
    client.failed.connect(errors.append)
    client.downloaded.connect(downloads.append)
    client.download(Release.parse(manifest()))
    directory = client._directory
    respond(client, b"tampered")
    assert errors and "checksum" in errors[0]
    assert not downloads and not directory.exists()


@pytest.mark.parametrize("status,target", [(403, None), (500, None), (302, "http://github.com/a"), (302, "https://evil.test/a")])
def test_failed_requests(client, status, target):
    errors = []
    client.failed.connect(errors.append)
    client.check()
    respond(client, status=status, target=target)
    assert errors and not client.busy


def test_missing_published_manifest_is_not_a_network_error(client):
    unavailable, errors, releases = [], [], []
    client.unavailable.connect(lambda: unavailable.append(True))
    client.failed.connect(errors.append)
    client.release_ready.connect(releases.append)
    client.check()
    respond(client, status=404)
    assert unavailable == [True]
    assert not errors and not releases and not client.busy


def test_missing_installer_is_still_an_error_and_cleans_download(client):
    unavailable, errors = [], []
    client.unavailable.connect(lambda: unavailable.append(True))
    client.failed.connect(errors.append)
    client.download(Release.parse(manifest()))
    directory = client._directory
    respond(client, status=404)
    assert errors and not unavailable and not client.busy
    assert not directory.exists()


def test_download_revalidates_versioned_asset_before_request(client):
    errors = []
    client.failed.connect(errors.append)
    client.download(Release("0.3.0", MSI_URL, hashlib.sha256(PAYLOAD).hexdigest()))
    assert errors and not client.busy and client._directory is None
    assert not client._manager.replies


def test_check_after_download_resets_download_context(client):
    releases, unavailable = [], []
    client.release_ready.connect(releases.append)
    client.unavailable.connect(lambda: unavailable.append(True))
    client.download(Release.parse(manifest()))
    respond(client, PAYLOAD)
    directory = client._directory
    client.check()
    respond(client, status=404)
    assert not directory.exists()
    assert client._release is None and unavailable == [True] and not releases


def test_cancel_aborts_without_emitting(client):
    errors = []
    client.failed.connect(errors.append)
    client.check()
    reply = client._manager.replies[-1]
    client.cancel()
    assert reply.aborted and not client.busy and not errors


def test_redirect_loop_is_bounded(client):
    errors = []
    client.failed.connect(errors.append)
    client.check()
    for _ in range(6):
        respond(client, status=302, target=MANIFEST_URL)
    assert len(client._manager.replies) == 6
    assert errors and not client.busy


def test_manifest_size_limit(client):
    errors = []
    client.failed.connect(errors.append)
    client.check()
    reply = client._manager.replies[-1]
    reply.body = b"x" * (1024 * 1024 + 1)
    reply.readyRead.emit()
    assert errors and not client.busy


def test_installer_helper_waits_and_restarts_only_on_success(client, monkeypatch):
    release = Release.parse(manifest())
    client.download(release)
    respond(client, PAYLOAD)
    path = client._directory / "update.msi"
    launched = []
    monkeypatch.setattr(updates, "can_install", lambda: True)
    monkeypatch.setattr(updates.subprocess, "Popen", lambda *args, **kwargs: launched.append(args[0]))
    updates.launch_installer(path, release)
    command = launched[0]
    script = base64.b64decode(command[-1]).decode("utf-16-le")
    assert script.index("WaitForExit") < script.index("msiexec.exe")
    assert "ExitCode -in @(0, 3010)" in script
    assert "-Wait -PassThru" in script
    assert "Get-FileHash" in script


def test_source_install_is_rejected(monkeypatch):
    monkeypatch.setattr(updates, "can_install", lambda: False)
    with pytest.raises(ValueError, match="packaged Windows"):
        updates.launch_installer(Path("missing.msi"), Release.parse(manifest()))


def test_update_panel_skip_and_manual_check(qt_app, workdir):
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    dialog = UpdatePanel(config)
    release = Release.parse(manifest(version="200.0.0"))
    dialog._available(release)
    assert "200.0.0" in dialog._status.text()
    dialog._skip_version()
    assert config.get("updates/skipped_version", "") == "200.0.0"
    dialog._automatic = True
    dialog._release = None
    dialog._available(release)
    assert dialog._release is None
    dialog._automatic = False
    dialog._available(release)
    assert dialog._release == release
    dialog._available(Release.parse(manifest(version=__version__)))
    assert "latest stable" in dialog._status.text()
    dialog.cancel()


@pytest.fixture()
def update_dialog(qt_app, workdir):
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    dialog = UpdatePanel(config)
    dialog.client._manager = Manager()
    yield dialog
    dialog.cancel()


def test_source_build_opens_release_page_instead_of_downloading(update_dialog, monkeypatch):
    from app.ui import update_panel as module

    opened = []
    monkeypatch.setattr(module, "can_install", lambda: False)
    monkeypatch.setattr(module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    release = Release.parse(manifest(version="200.0.0", notes=""))
    update_dialog._available(release)
    assert update_dialog._action.isEnabled()
    assert update_dialog._action.text() == "Open GitHub release"
    assert "source code" in update_dialog._notes.toPlainText()
    update_dialog._activate()
    assert opened == [release.page_url]
    assert not update_dialog.client.busy and not update_dialog.client._manager.replies


def test_dialog_missing_manifest_offers_retry_and_github(update_dialog, monkeypatch):
    from app.ui import update_panel as module

    opened = []
    monkeypatch.setattr(module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    update_dialog.check(automatic=True)
    respond(update_dialog.client, status=404)
    assert "No published stable update manifest" in update_dialog._status.text()
    assert "Draft" in update_dialog._status.text()
    assert update_dialog._action.isEnabled() and not update_dialog._skip.isEnabled()
    assert update_dialog._release is None and not update_dialog.isVisible()
    update_dialog._release_link.click()
    assert opened == [RELEASES_URL]
    update_dialog._action.click()
    assert update_dialog.client.busy


def test_browser_failure_shows_copyable_release_url(update_dialog, monkeypatch):
    from app.ui import update_panel as module

    monkeypatch.setattr(module.QDesktopServices, "openUrl", lambda url: False)
    update_dialog._open_release()
    assert RELEASES_URL in update_dialog._status.text()


def test_newer_local_build_is_not_reported_as_latest_published_release(update_dialog):
    update_dialog._available(Release.parse(manifest(version="0.0.0")))
    assert "newer than" in update_dialog._status.text()
    assert update_dialog._release is None
    assert update_dialog._action.text() == "Check for updates"


def test_packaged_update_download_verify_confirm_and_handoff(update_dialog, monkeypatch):
    from app.ui import update_panel as module

    monkeypatch.setattr(module, "can_install", lambda: True)
    release = Release.parse(manifest(version="200.0.0"))
    update_dialog._available(release)
    assert update_dialog._action.text() == "Download update"
    update_dialog._action.click()
    assert update_dialog.client.busy and not update_dialog._action.isEnabled()
    assert update_dialog._progress.maximum() == 100
    assert not update_dialog._progress.isTextVisible()
    assert not update_dialog._progress_label.isHidden()
    update_dialog.client.progress.emit(45)
    assert update_dialog._progress_label.text() == "45% downloaded"
    respond(update_dialog.client, PAYLOAD)
    assert update_dialog._path.read_bytes() == PAYLOAD
    assert "SHA-256 verified" in update_dialog._status.text()
    assert update_dialog._skip.isEnabled() and update_dialog._check.isEnabled()
    assert update_dialog._cancel.isHidden() and update_dialog._progress_label.isHidden()
    requests, confirmations = [], []
    update_dialog.install_requested.connect(lambda *args: requests.append(args))

    def confirm(*args):
        confirmations.append(args[2])
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", confirm)
    update_dialog._action.click()
    assert not requests and "publisher signature" in confirmations[0]
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    update_dialog._action.click()
    assert requests == [(update_dialog._path, release)]


def test_recheck_clears_previous_download_state(update_dialog, monkeypatch):
    from app.ui import update_panel as module

    monkeypatch.setattr(module, "can_install", lambda: True)
    release = Release.parse(manifest(version="200.0.0"))
    update_dialog._available(release)
    update_dialog._activate()
    respond(update_dialog.client, PAYLOAD)
    directory = update_dialog._path.parent
    update_dialog._check.click()
    assert update_dialog._path is None and update_dialog._release is None
    assert not directory.exists()
    assert update_dialog._notes.toPlainText() == ""
    assert not update_dialog._progress.isHidden()
    assert update_dialog._progress.maximum() == 0
    respond(update_dialog.client, manifest(version=__version__))
    assert "latest stable" in update_dialog._status.text()
    assert update_dialog._action.text() == "Check for updates"
    assert not update_dialog._skip.isEnabled()


def test_failed_download_can_retry_without_stale_install_path(update_dialog, monkeypatch):
    from app.ui import update_panel as module

    monkeypatch.setattr(module, "can_install", lambda: True)
    update_dialog._available(Release.parse(manifest(version="200.0.0")))
    update_dialog._activate()
    respond(update_dialog.client, b"incorrect checksum")
    assert update_dialog._path is None and update_dialog._action.text() == "Download again"
    assert update_dialog._skip.isEnabled()
    update_dialog._activate()
    respond(update_dialog.client, PAYLOAD)
    assert update_dialog._path.read_bytes() == PAYLOAD


def test_settings_reuses_automatic_check_without_popup(qt_app, workdir, credentials, monkeypatch):
    from app.core.store import ConversationStore

    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    config.set("updates/automatic", False)
    config.set("updates/skipped_version", "200.0.0")
    window = MainWindow(config, ConversationStore(workdir / "conversations"), credentials)
    panel = window._updates()
    panel.client._manager = Manager()
    panel.check(automatic=True)
    respond(panel.client, manifest(version="200.0.0"))
    assert panel._release is None and not panel.isVisible()

    def execute(dialog):
        dialog.show()
        dialog._updates_button.click()
        assert dialog._update_panel is panel
        assert panel.isVisible() and not panel.isWindow()
        assert panel.window() is dialog
        panel.check()
        assert not panel._automatic and panel.client.busy
        respond(panel.client, manifest(version="200.0.0"))
        assert panel._release.version == "200.0.0"
        dialog.reject()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(SettingsDialog, "exec", execute)
    window._open_settings()
    assert panel.parent() is window and not panel.isVisible()
    window._open_settings()
    assert panel.parent() is window and window._settings_dialog is None
    window.close()


def test_settings_update_preference_save_and_discard(qt_app, workdir, credentials, monkeypatch):
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    dialog = SettingsDialog(config, credentials, tokens_for("dark"))
    assert dialog._auto_updates.isChecked()
    dialog._auto_updates.setChecked(False)
    assert dialog._has_changes()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    dialog.reject()
    assert config.get("updates/automatic")
    dialog = SettingsDialog(config, credentials, tokens_for("dark"))
    dialog._auto_updates.setChecked(False)
    assert dialog._save()
    assert not config.get("updates/automatic")


def test_check_updates_stays_in_settings_and_preserves_drafts(qt_app, workdir, credentials, monkeypatch):
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    dialog = SettingsDialog(config, credentials, tokens_for("dark"))
    panel = dialog._update_panel
    panel.client._manager = Manager()
    dialog.show()
    dialog._updates_button.click()
    dialog._auto_updates.setChecked(False)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: pytest.fail("Checking must not prompt to close Settings"))
    panel._action.click()
    assert dialog.isVisible() and panel.window() is dialog
    assert panel._progress.isVisible() and panel._progress.maximum() == 0
    assert not panel._action.isEnabled()
    assert dialog._has_changes() and config.get("updates/automatic")
    respond(panel.client, manifest(version="200.0.0"))
    assert dialog.isVisible() and panel._notes.toPlainText() == "Bug fixes"
    assert panel._progress.isHidden() and panel._action.isEnabled()
    panel._skip.click()
    assert dialog.isVisible() and dialog._has_changes()
    assert not panel._skip.isEnabled() and panel._release is None
    dialog.done(QDialog.DialogCode.Rejected)


@pytest.mark.parametrize("result", ["current", "older", "new", "skipped", "missing", "error"])
def test_version_check_loading_stops_for_every_result(update_dialog, result):
    panel = update_dialog
    panel._config.set("updates/skipped_version", "200.0.0")
    panel.check(automatic=result == "skipped")
    assert not panel._progress.isHidden()
    assert panel._progress.minimum() == panel._progress.maximum() == 0
    assert not panel._action.isEnabled()
    if result in ("missing", "error"):
        respond(panel.client, status=404 if result == "missing" else 500)
    else:
        version = {"current": __version__, "older": "0.0.0"}.get(result, "200.0.0")
        respond(panel.client, manifest(version=version))
    assert panel._progress.isHidden() and panel._action.isEnabled()
    assert not panel.client.busy
    assert not panel.isVisible()


@pytest.mark.parametrize("download", [False, True])
def test_closing_settings_cancels_update_and_cleans_download(qt_app, workdir, credentials, monkeypatch, download):
    from app.ui import update_panel

    monkeypatch.setattr(update_panel, "can_install", lambda: True)
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    dialog = SettingsDialog(config, credentials, tokens_for("dark"))
    panel = dialog._update_panel
    panel.client._manager = Manager()
    dialog.show()
    dialog._updates_button.click()
    panel.check()
    directory = None
    if download:
        respond(panel.client, manifest(version="200.0.0"))
        panel._action.click()
        directory = panel.client._directory
    reply = panel.client._manager.replies[-1]
    dialog.reject()
    assert reply.aborted and not panel.client.busy
    assert panel._progress.isHidden() and panel._action.isEnabled()
    assert panel._path is None
    assert directory is None or not directory.exists()


@pytest.mark.parametrize("answer", ["Save", "Discard", "Cancel"])
def test_inline_install_handles_unsaved_settings_without_deleting_installer(qt_app, workdir, credentials, monkeypatch, answer):
    from app.ui import update_panel

    monkeypatch.setattr(update_panel, "can_install", lambda: True)
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    dialog = SettingsDialog(config, credentials, tokens_for("dark"))
    panel = dialog._update_panel
    panel.client._manager = Manager()
    panel._available(Release.parse(manifest(version="200.0.0")))
    panel._activate()
    respond(panel.client, PAYLOAD)
    path = panel._path
    dialog.show()
    dialog._auto_updates.setChecked(False)
    requests = []
    dialog.install_requested.connect(lambda *args: requests.append(args))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: getattr(QMessageBox.StandardButton, answer))
    dialog._request_install(path, panel._release)
    assert dialog.isVisible() and path.exists()
    assert len(requests) == (0 if answer == "Cancel" else 1)
    assert config.get("updates/automatic") == (answer != "Save")
    if answer == "Save":
        assert not dialog._has_changes()
    dialog.done(QDialog.DialogCode.Rejected)
    assert not path.exists()


def test_main_window_blocks_install_when_busy_or_settings_fail(qt_app, workdir, credentials, monkeypatch):
    from app.core.store import ConversationStore
    from app.ui import main_window

    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    window = MainWindow(config, ConversationStore(workdir / "conversations"), credentials)
    calls, messages = [], []
    monkeypatch.setattr(main_window, "launch_installer", lambda *args: calls.append(args))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[-1]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[-1]))
    monkeypatch.setattr(type(window._controller), "busy", property(lambda self: True))
    window._install_update(Path("unused.msi"), Release.parse(manifest()))
    assert messages and not calls
    monkeypatch.setattr(type(window._controller), "busy", property(lambda self: False))
    monkeypatch.setattr(config, "sync", lambda: False)
    window._install_update(Path("unused.msi"), Release.parse(manifest()))
    assert "Could not save settings" in messages[-1] and not calls
    window.close()


@pytest.mark.parametrize("stage", ["available", "failed", "downloaded"])
def test_recheck_is_reachable_from_every_release_state(update_dialog, monkeypatch, stage):
    from app.ui import update_panel

    monkeypatch.setattr(update_panel, "can_install", lambda: True)
    panel = update_dialog
    panel._available(Release.parse(manifest(version="200.0.0")))
    if stage != "available":
        panel._action.click()
        respond(panel.client, PAYLOAD if stage == "downloaded" else b"invalid")
    assert not panel._check.isHidden() and panel._check.isEnabled()
    panel._check.click()
    assert panel.client.busy and panel._release is None and panel._path is None
    assert panel._notes_group.isHidden() and not panel._cancel.isHidden()
    respond(panel.client, manifest(version=__version__))
    assert panel._title.text() == "You're up to date"
    assert panel._notes_group.isHidden() and panel._check.isHidden()


@pytest.mark.parametrize("download", [False, True])
def test_cancel_button_stops_request_and_allows_retry(update_dialog, monkeypatch, download):
    from app.ui import update_panel

    monkeypatch.setattr(update_panel, "can_install", lambda: True)
    panel = update_dialog
    panel._action.click()
    if download:
        respond(panel.client, manifest(version="200.0.0"))
        panel._action.click()
    reply = panel.client._manager.replies[-1]
    count = len(panel.client._manager.replies)
    panel._activate()
    panel.check()
    assert len(panel.client._manager.replies) == count
    panel._cancel.click()
    assert reply.aborted and not panel.client.busy
    assert panel._progress.isHidden() and panel._cancel.isHidden()
    assert panel._action.isEnabled() and panel._path is None
    assert panel._title.text() == "Request canceled"
    panel._action.click()
    assert panel.client.busy


def test_skip_after_download_removes_installer_without_closing_panel(update_dialog, monkeypatch):
    from app.ui import update_panel

    monkeypatch.setattr(update_panel, "can_install", lambda: True)
    panel = update_dialog
    panel._available(Release.parse(manifest(version="200.0.0")))
    panel._action.click()
    respond(panel.client, PAYLOAD)
    directory = panel._path.parent
    panel._skip.click()
    assert not directory.exists() and panel._path is None
    assert panel._notes_group.isHidden() and panel._skip.isHidden()
    assert panel._action.text() == "Check for updates"


def test_failed_skip_preserves_release_and_saved_preference(update_dialog, monkeypatch):
    panel = update_dialog
    panel._config.set("updates/skipped_version", "100.0.0")
    panel._available(Release.parse(manifest(version="200.0.0")))
    monkeypatch.setattr(panel._config, "sync", lambda: False)
    panel._skip.click()
    assert panel._config.get("updates/skipped_version") == "100.0.0"
    assert panel._release.version == "200.0.0" and panel._skip.isEnabled()
    assert panel._card.property("status") == "error"


def test_missing_installer_is_detected_before_confirmation(update_dialog, monkeypatch):
    from app.ui import update_panel

    monkeypatch.setattr(update_panel, "can_install", lambda: True)
    panel = update_dialog
    panel._available(Release.parse(manifest(version="200.0.0")))
    panel._action.click()
    respond(panel.client, PAYLOAD)
    panel._path.unlink()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: pytest.fail("Missing installer must not prompt to install"))
    panel._action.click()
    assert panel._path is None and panel._action.text() == "Download again"
    assert panel._card.property("status") == "error"
    panel._action.click()
    assert panel.client.busy


@pytest.mark.parametrize("invalid", [False, True])
def test_install_handoff_failure_has_a_recoverable_state(qt_app, workdir, credentials, monkeypatch, invalid):
    from app.core.store import ConversationStore
    from app.ui import main_window, update_panel

    monkeypatch.setattr(update_panel, "can_install", lambda: True)
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    config.set("updates/automatic", False)
    window = MainWindow(config, ConversationStore(workdir / "conversations"), credentials)
    panel = window._updates()
    panel.client._manager = Manager()
    panel._available(Release.parse(manifest(version="200.0.0")))
    panel._action.click()
    respond(panel.client, PAYLOAD)
    path = panel._path

    def fail_install(*args):
        if invalid:
            path.unlink()
        raise OSError("Installation could not start")

    monkeypatch.setattr(main_window, "launch_installer", fail_install)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
    window._install_update(path, panel._release)
    assert panel._card.property("status") == "error"
    assert panel._action.isEnabled() and panel._check.isEnabled()
    if invalid:
        assert panel._path is None and panel._action.text() == "Download again"
    else:
        assert panel._path == path and path.exists()
        assert panel._action.text() == "Install & restart"
    window.close()


def test_successful_inline_install_transfers_download_before_settings_closes(qt_app, workdir, credentials, monkeypatch):
    from app.core.store import ConversationStore
    from app.net import updates as network
    from app.ui import main_window, update_panel

    monkeypatch.setattr(update_panel, "can_install", lambda: True)
    directory = workdir / "download"
    directory.mkdir()
    monkeypatch.setattr(network.tempfile, "mkdtemp", lambda **kwargs: str(directory))
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    config.set("updates/automatic", False)
    window = MainWindow(config, ConversationStore(workdir / "conversations"), credentials)
    panel = window._updates()
    panel.client._manager = Manager()
    release = Release.parse(manifest(version="200.0.0"))
    panel._available(release)
    panel._action.click()
    respond(panel.client, PAYLOAD)
    path = panel._path
    launched, quits = [], []
    monkeypatch.setattr(main_window, "launch_installer", lambda *args: launched.append(args))
    monkeypatch.setattr(qt_app, "quit", lambda: quits.append(True))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)

    def execute(dialog):
        dialog.show()
        dialog._updates_button.click()
        panel._action.click()
        assert not dialog.isVisible() and path.exists()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", execute)
    window._open_settings()
    assert launched == [(path, release)] and quits == [True]
    assert panel.client._directory is None and panel._path is None
    window.close()
    assert path.read_bytes() == PAYLOAD
