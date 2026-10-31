from __future__ import annotations

import os
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from app.core.config import Config
from app.core.credentials import CredentialStore
from app.ui import theme
from app.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if isinstance(app, QApplication):
        return app
    return QApplication([])


def _dialog(workdir: Path) -> SettingsDialog:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    return SettingsDialog(config, CredentialStore(), theme.tokens_for("dark"))


def test_custom_provider_allows_api_key(qt_app: QApplication, workdir: Path) -> None:
    dialog = _dialog(workdir)
    index = dialog._provider.findData("custom")
    dialog._provider.setCurrentIndex(index)
    assert dialog._key.isEnabled()
    dialog.close()


def test_openai_provider_allows_api_key(qt_app: QApplication, workdir: Path) -> None:
    dialog = _dialog(workdir)
    index = dialog._provider.findData("openai")
    dialog._provider.setCurrentIndex(index)
    assert dialog._key.isEnabled()
    dialog.close()
