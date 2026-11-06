from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.config import Config
from ..core.updates import RELEASES_URL, Release, can_install, verify_installer
from ..net.updates import UpdateClient


class UpdatePanel(QWidget):
    install_requested = pyqtSignal(object, object)

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._release: Release | None = None
        self._path: Path | None = None
        self._automatic = False
        self.setObjectName("UpdatePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self._card = QFrame()
        self._card.setObjectName("UpdateCard")
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(12)
        self._title = QLabel(self.tr("Ready to check"))
        self._title.setObjectName("UpdateTitle")
        self._title.setWordWrap(True)
        card_layout.addWidget(self._title)
        self._status = QLabel(self.tr("Check for the latest published stable release. Draft releases are not offered as updates."))
        self._status.setObjectName("UpdateDescription")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._status.setWordWrap(True)
        card_layout.addWidget(self._status)
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setAccessibleName(self.tr("Update progress"))
        self._progress.hide()
        card_layout.addWidget(self._progress)
        self._progress_label = QLabel()
        self._progress_label.setObjectName("SettingsHelp")
        self._progress_label.hide()
        card_layout.addWidget(self._progress_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._action = QPushButton(self.tr("Check for updates"))
        self._action.setObjectName("Primary")
        self._action.setAutoDefault(False)
        self._action.clicked.connect(self._activate)
        buttons.addWidget(self._action)
        self._check = QPushButton(self.tr("Recheck"))
        self._check.setAccessibleName(self.tr("Check for updates again"))
        self._check.setAutoDefault(False)
        self._check.clicked.connect(lambda: self.check())
        self._check.hide()
        buttons.addWidget(self._check)
        self._cancel = QPushButton(self.tr("Cancel request"))
        self._cancel.setAutoDefault(False)
        self._cancel.clicked.connect(self.cancel)
        self._cancel.hide()
        buttons.addWidget(self._cancel)
        buttons.addStretch(1)
        card_layout.addLayout(buttons)
        layout.addWidget(self._card)

        self._notes_group = QGroupBox(self.tr("What's new"))
        notes_layout = QVBoxLayout(self._notes_group)
        notes_layout.setContentsMargins(0, 8, 0, 0)
        self._notes = QPlainTextEdit()
        self._notes.setObjectName("UpdateNotes")
        self._notes.setAccessibleName(self.tr("Release notes"))
        self._notes.setReadOnly(True)
        self._notes.setMinimumHeight(120)
        self._notes.setMaximumHeight(180)
        notes_layout.addWidget(self._notes)
        self._notes_group.hide()
        layout.addWidget(self._notes_group)

        links = QHBoxLayout()
        self._release_link = QPushButton(self.tr("View on GitHub"))
        self._release_link.setObjectName("UpdateLink")
        self._release_link.setAutoDefault(False)
        self._release_link.clicked.connect(self._open_release)
        links.addWidget(self._release_link)
        links.addStretch(1)
        self._skip = QPushButton(self.tr("Skip this version"))
        self._skip.setAutoDefault(False)
        self._skip.setEnabled(False)
        self._skip.hide()
        self._skip.clicked.connect(self._skip_version)
        links.addWidget(self._skip)
        layout.addLayout(links)
        integrity = QLabel(self.tr(
            "Installer downloads are checked against the release manifest using SHA-256. "
            "This verifies file integrity, not publisher identity. Windows may warn about unsigned installers."
        ))
        integrity.setObjectName("SettingsHelp")
        integrity.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        integrity.setWordWrap(True)
        layout.addWidget(integrity)
        self.client = UpdateClient(self)
        self.client.release_ready.connect(self._available)
        self.client.failed.connect(self._failed)
        self.client.unavailable.connect(self._unavailable)
        self.client.progress.connect(self._download_progress)
        self.client.downloaded.connect(self._downloaded)

    def _set_status(self, title: str, message: str, kind: str = "idle") -> None:
        self._title.setText(title)
        self._status.setText(message)
        self._status.setAccessibleDescription(message)
        self._card.setProperty("status", kind)
        self._card.style().unpolish(self._card)
        self._card.style().polish(self._card)
        self._title.style().unpolish(self._title)
        self._title.style().polish(self._title)
        self._card.layout().invalidate()
        self.layout().invalidate()
        self.updateGeometry()

    def _set_busy(self, busy: bool) -> None:
        self._action.setEnabled(not busy)
        self._release_link.setEnabled(not busy)
        self._check.setEnabled(not busy)
        self._check.setVisible(not busy and self._release is not None)
        self._skip.setEnabled(not busy and self._release is not None)
        self._skip.setVisible(self._release is not None)
        self._cancel.setVisible(busy)
        self._progress.setVisible(busy)
        self._progress_label.setVisible(busy and self._release is not None)

    def check(self, *, automatic: bool = False) -> None:
        if self.client.busy:
            return
        self._automatic = automatic
        self._release = self._path = None
        self._notes.clear()
        self._notes_group.hide()
        self._progress.setRange(0, 0)
        self._progress.setAccessibleName(self.tr("Checking for updates"))
        self._set_busy(True)
        self._action.setText(self.tr("Checking..."))
        self._set_status(self.tr("Checking for updates"), self.tr("Looking for the latest stable release on GitHub..."), "busy")
        self.client.check()

    def _available(self, release: Release) -> None:
        self._release = self._path = None
        self._notes.clear()
        self._notes_group.hide()
        self._set_busy(False)
        self._action.setText(self.tr("Check for updates"))
        if not release.newer_than(__version__):
            self._set_status(self.tr("You're up to date"),
                self.tr("You are using the latest stable version.") if release.version == __version__ else
                self.tr("Your version ({current}) is newer than the latest published stable release ({latest}).").format(
                    current=__version__, latest=release.version,
                ), "success",
            )
            return
        if self._automatic and self._config.get("updates/skipped_version", "") == release.version:
            self._set_status(self.tr("Version skipped"), self.tr("Version {version} is skipped. Check manually to download it.").format(version=release.version))
            return
        self._release = release
        self._notes.setPlainText(release.notes or self.tr("See the GitHub release page for release notes, checksums, and source code."))
        self._notes_group.show()
        message = self.tr("Version {version} is available.").format(version=release.version)
        self._action.setText(self.tr("Download update"))
        if not can_install():
            self._action.setText(self.tr("Open GitHub release"))
            message = self.tr("Version {version} is available. Automatic installation requires the packaged Windows app.").format(version=release.version)
        self._set_status(self.tr("Update available"), message, "success")
        self._set_busy(False)

    def _activate(self) -> None:
        if self.client.busy:
            return
        if self._path:
            try:
                verify_installer(self._path, self._release)
            except (OSError, ValueError) as exc:
                self.client.cancel()
                self._failed(str(exc))
                return
            answer = QMessageBox.question(
                self, self.tr("Install update?"),
                self.tr("Playgrounds will close, install the update, and restart after a successful installation. "
                        "Your conversations and settings will be preserved. "
                        "Windows may show an unsigned publisher warning; SHA-256 verification is not a publisher signature. Continue?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.install_requested.emit(self._path, self._release)
        elif self._release:
            if not can_install():
                self._open_release()
                return
            self._path = None
            self._set_busy(True)
            self._action.setText(self.tr("Downloading..."))
            self._progress.setRange(0, 100)
            self._progress.setAccessibleName(self.tr("Downloading update"))
            self._progress.setValue(0)
            self._progress_label.setText(self.tr("Connecting to download..."))
            self._set_status(self.tr("Downloading update"), self.tr("Downloading Windows x64 MSI installer..."), "busy")
            self.client.download(self._release)
        else:
            self.check()

    def _downloaded(self, path: Path) -> None:
        self._path = path
        self._set_busy(False)
        self._progress.setValue(100)
        self._set_status(self.tr("Ready to install"), self.tr("Installer SHA-256 verified. Ready to install and restart."), "success")
        self._action.setText(self.tr("Install & restart"))

    def _download_progress(self, value: int) -> None:
        if self._release is not None:
            self._progress.setValue(value)
            self._progress_label.setText(self.tr("{percent}% downloaded").format(percent=value))

    def installation_failed(self, message: str) -> None:
        if self._path is None or self._release is None:
            self._failed(message)
            return
        try:
            verify_installer(self._path, self._release)
        except (OSError, ValueError):
            self.client.cancel()
            self._failed(message)
            return
        self._set_status(self.tr("Installation could not start"), message, "error")

    def _failed(self, message: str) -> None:
        self._path = None
        self._set_status(self.tr("Download failed") if self._release else self.tr("Couldn't check for updates"), message, "error")
        self._action.setText(self.tr("Download again") if self._release else self.tr("Check again"))
        self._set_busy(False)

    def _unavailable(self) -> None:
        self._release = self._path = None
        self._notes.clear()
        self._notes_group.hide()
        self._set_busy(False)
        self._action.setText(self.tr("Check again"))
        self._set_status(self.tr("No release published yet"), self.tr(
            "No published stable update manifest is available yet. "
            "Draft releases are not available to the updater. View GitHub Releases or try again later."
        ))

    def _open_release(self) -> None:
        url = self._release.page_url if self._release else RELEASES_URL
        if not QDesktopServices.openUrl(QUrl(url)):
            self._set_status(self.tr("Could not open GitHub"), self.tr("Could not open the browser. Open {url} manually.").format(url=url), "error")

    def _skip_version(self) -> None:
        if self._release and not self.client.busy:
            previous = self._config.get("updates/skipped_version", "")
            self._config.set("updates/skipped_version", self._release.version)
            if not self._config.sync():
                self._config.set("updates/skipped_version", previous)
                self._set_status(self.tr("Could not skip this version"), self.tr("The preference could not be saved. Please try again."), "error")
                return
            self._release = self._path = None
            self.client.cancel()
            self._notes.clear()
            self._notes_group.hide()
            self._set_busy(False)
            self._action.setText(self.tr("Check for updates"))
            self._set_status(self.tr("Version skipped"), self.tr("Version {version} is skipped. Check manually to download it.").format(
                version=self._config.get("updates/skipped_version", ""),
            ))

    def cancel(self) -> None:
        was_busy = self.client.busy
        self.client.cancel()
        self._path = None
        self._set_busy(False)
        self._action.setText(self.tr("Download update") if self._release and can_install() else
                             self.tr("Open GitHub release") if self._release else self.tr("Check for updates"))
        if was_busy:
            self._set_status(self.tr("Request canceled"), self.tr("Update request canceled. Try again when ready."))
        elif self._release:
            self._set_status(self.tr("Update available"), self.tr("Version {version} is available.").format(version=self._release.version), "success")
