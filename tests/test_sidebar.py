from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QSettings, Qt
from PyQt6.QtTest import QTest

from app.core.config import Config
from app.core.store import ConversationStore
from app.ui.main_window import MainWindow


@pytest.mark.parametrize("width", [880, 1180])
def test_sidebar_toggle_restores_width_and_expands_chat(qt_app, workdir, credentials, width) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    window.resize(width, 560)
    window.show()
    qt_app.processEvents()
    try:
        window._splitter.setSizes([300, width - 300])
        sidebar_width = window._sidebar.width()
        chat_width = window._splitter.widget(1).width()
        assert window._sidebar_button.accessibleName() == "Hide sidebar"
        button_position = window._sidebar_button.mapTo(window, QPoint())
        assert button_position.x() <= 16
        assert window._title_bar.isAncestorOf(window._sidebar_button)

        QTest.mouseClick(window._sidebar_button, Qt.MouseButton.LeftButton)
        qt_app.processEvents()
        assert window._sidebar.isHidden()
        assert window._sidebar_button.isVisible()
        assert window._sidebar_button.mapTo(window, QPoint()) == button_position
        assert window._splitter.widget(1).width() > chat_width
        assert window._sidebar_button.accessibleName() == "Show sidebar"
        assert config.get("sidebar_visible") is False

        QTest.mouseClick(window._sidebar_button, Qt.MouseButton.LeftButton)
        qt_app.processEvents()
        assert window._sidebar.isVisible()
        assert window._sidebar_button.mapTo(window, QPoint()) == button_position
        assert abs(window._sidebar.width() - sidebar_width) <= 1
        assert config.get("sidebar_visible") is True
    finally:
        window.close()


@pytest.mark.parametrize("sidebar_visible", [True, False])
def test_sidebar_visibility_and_expanded_size_survive_restart(qt_app, workdir, credentials, sidebar_visible) -> None:
    path = str(workdir / "settings.ini")
    config = Config(QSettings(path, QSettings.Format.IniFormat))
    store = ConversationStore(workdir / "chats")
    window = MainWindow(config, store, credentials)
    window.resize(880, 560)
    window.show()
    qt_app.processEvents()
    window._splitter.setSizes([310, 568])
    sidebar_width = window._sidebar.width()
    if not sidebar_visible:
        window._sidebar_button.click()
    window.close()

    restored = MainWindow(Config(QSettings(path, QSettings.Format.IniFormat)), store, credentials)
    restored.show()
    qt_app.processEvents()
    try:
        assert restored._sidebar.isVisible() is sidebar_visible
        if not sidebar_visible:
            assert restored._sidebar_button.toolTip() == "Show sidebar (Ctrl+B)"
            restored._sidebar_button.click()
            qt_app.processEvents()
        assert restored._sidebar.isVisible()
        assert abs(restored._sidebar.width() - sidebar_width) <= 1
    finally:
        restored.close()


def test_sidebar_shortcut_and_theme_refresh(qt_app, workdir, credentials) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    window.show()
    window.activateWindow()
    qt_app.processEvents()
    try:
        window._composer.focus_input()
        QTest.keyClick(window._composer._input, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
        assert window._sidebar.isHidden()
        original_icon = window._sidebar_button.icon().cacheKey()
        window._toggle_theme()
        assert window._sidebar_button.icon().cacheKey() != original_icon
        assert not window._sidebar_button.icon().isNull()
        assert window._sidebar_button.accessibleName() == "Show sidebar"
        QTest.keyClick(window._composer._input, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
        assert window._sidebar.isVisible()
    finally:
        window.close()
