from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QPalette, QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QLineEdit, QPushButton, QVBoxLayout

from app.core.config import Config
from app.core.updates import Release
from app.ui import theme
from app.ui.chat_view import ChatView
from app.ui.composer import Composer
from app.ui.markdown import render_markdown
from app.ui.settings_dialog import SettingsDialog
from app.ui.sidebar import Sidebar


def _contrast(first: str, second: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    low, high = sorted((luminance(first), luminance(second)))
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("name", ["dark", "light"])
def test_accent_contrast_across_surfaces_and_states(name) -> None:
    tokens = theme.tokens_for(name)
    assert tokens["accent"] == "#FF896A"
    for background in ("accent", "accent_hover"):
        # Both gradient endpoints and filled-button states support small text/icons.
        assert _contrast(tokens["accent_text"], tokens[background]) >= 4.5
    for surface in (
        "bg", "bg_alt", "surface", "surface_hover", "surface_active",
        "user_surface", "assistant_surface",
    ):
        for text in ("text", "text_muted", "text_faint", "accent_strong"):
            assert _contrast(tokens[text], tokens[surface]) >= 4.5, (name, text, surface)
        assert _contrast(tokens["accent_strong"], tokens[surface]) >= 3
    for fill in ("accent", "accent_hover"):
        assert _contrast(tokens["accent_text"], tokens[fill]) >= 3
        if name == "light":
            assert _contrast(tokens["accent_strong"], tokens[fill]) >= 3
    assert "@" not in theme.build_qss(tokens)


@pytest.mark.parametrize("name", ["dark", "light"])
def test_edit_message_contrast(name) -> None:
    tokens = theme.tokens_for(name)
    for foreground, background, minimum in (
        ("text", "bg", 4.5),
        ("text_muted", "bg", 4.5),
        ("text", "surface", 4.5),
        ("text", "surface_hover", 4.5),
        ("text", "surface_active", 4.5),
        ("text_faint", "surface_active", 4.5),
        ("control_border", "bg", 3),
        ("control_border", "surface", 3),
        ("control_border", "surface_hover", 3),
        ("control_border", "surface_active", 3),
        ("accent_strong", "bg", 3),
        ("accent_strong", "surface", 3),
        ("accent_text", "accent", 4.5),
        ("accent_text", "accent_hover", 4.5),
    ):
        assert _contrast(tokens[foreground], tokens[background]) >= minimum, (
            name, foreground, background,
        )


def test_theme_switch_refreshes_native_and_styled_accents(qt_app) -> None:
    old_palette, old_qss = qt_app.palette(), qt_app.styleSheet()
    dialog = QDialog()
    dialog.setObjectName("SettingsDialog")
    layout = QVBoxLayout(dialog)
    button = QPushButton("Save")
    button.setObjectName("Primary")
    field = QLineEdit("Selected text")
    layout.addWidget(button)
    layout.addWidget(field)
    browser = ChatView(theme.tokens_for("dark"))
    layout.addWidget(browser)
    dialog.show()
    try:
        for name in ("dark", "light", "dark"):
            tokens = theme.apply(qt_app, name)
            browser.setHtml(render_markdown("[Link](https://example.com)", tokens))
            field.setFocus()
            QTest.mouseMove(field, field.rect().center())
            qt_app.processEvents()
            image = button.grab().toImage()
            assert image.pixelColor(image.width() // 2, 0).name().upper() == tokens["accent_strong"]
            assert image.pixelColor(image.width() // 2, 4).name().upper() == tokens["accent"]
            QTest.mouseMove(button, button.rect().center())
            qt_app.processEvents()
            image = button.grab().toImage()
            assert image.pixelColor(image.width() // 2, 4).name().upper() == tokens["accent_hover"]
            button.setFocus()
            qt_app.processEvents()
            image = button.grab().toImage()
            assert image.pixelColor(image.width() // 2, 0).name() == tokens["accent_text"]
            assert not dialog.grab().isNull()
            for widget in (qt_app, field, browser):
                palette = widget.palette()
                assert palette.color(QPalette.ColorRole.Highlight).name().upper() == tokens["accent"]
                assert palette.color(QPalette.ColorRole.HighlightedText).name() == tokens["accent_text"]
                assert palette.color(QPalette.ColorRole.Link).name().upper() == tokens["accent_strong"]
            cursor = browser.document().find("Link")
            assert not cursor.isNull()
            cursor.setPosition(cursor.selectionStart() + 1, QTextCursor.MoveMode.KeepAnchor)
            assert cursor.charFormat().foreground().color().name().upper() == tokens["accent_strong"]
            assert cursor.charFormat().fontUnderline()
    finally:
        dialog.close()
        qt_app.setPalette(old_palette)
        qt_app.setStyleSheet(old_qss)


@pytest.mark.parametrize("name", ["dark", "light"])
def test_navigation_and_composer_have_visible_states(qt_app, name):
    old_palette, old_qss = qt_app.palette(), qt_app.styleSheet()
    tokens = theme.apply(qt_app, name)
    sidebar = Sidebar(tokens)
    composer = Composer(tokens)
    sidebar.resize(210, 480)
    composer.resize(600, 260)
    sidebar.show()
    composer.show()
    try:
        sidebar.activateWindow()
        sidebar._search.setFocus()
        QTest.mouseMove(sidebar, sidebar.rect().topLeft())
        qt_app.processEvents()
        history_button = sidebar._archived_button.grab().toImage()
        sidebar._archived_button.click()
        qt_app.processEvents()
        back_button = sidebar._archived_button.grab().toImage()
        assert history_button != back_button
        assert not sidebar._archived_button.isCheckable()
        button = sidebar._archived_button
        assert button.width() >= button.sizeHint().width()
        assert sidebar._section.font().pointSizeF() >= 10
        assert sidebar._section.width() >= sidebar._section.sizeHint().width()
        assert sidebar.rect().contains(sidebar._archived_button.geometry())
        sidebar._list.setFocus()
        qt_app.processEvents()
        image = sidebar._list.grab().toImage()
        assert image.pixelColor(image.width() // 2, 0).name().upper() == tokens["accent_strong"]

        composer.activateWindow()
        composer.focus_input()
        qt_app.processEvents()
        image = composer._frame.grab().toImage()
        assert image.pixelColor(image.width() // 2, 0).name().upper() == tokens["accent_strong"]
        assert composer._hint.font().pointSizeF() >= 10
        for surface in ("bg", "bg_alt", "surface", "surface_hover", "surface_active"):
            assert _contrast(tokens["control_border"], tokens[surface]) >= 3
        assert _contrast(tokens["settings_error"], tokens["surface"]) >= 4.5
    finally:
        sidebar.close()
        composer.close()
        qt_app.setPalette(old_palette)
        qt_app.setStyleSheet(old_qss)


def test_update_page_tracks_native_and_styled_theme_colors(qt_app, workdir, credentials):
    old_palette, old_qss = qt_app.palette(), qt_app.styleSheet()
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    panel = dialog._update_panel
    dialog.show()
    dialog._updates_button.click()
    try:
        for name in ("dark", "light", "dark"):
            tokens = theme.apply(qt_app, name)
            panel._unavailable()
            qt_app.processEvents()
            assert panel._notes_group.isHidden()
            content = dialog._updates_scroll.widget().grab().toImage()
            assert content.pixelColor(content.width() - 3, content.height() - 3).name() == tokens["bg"]
            assert dialog._updates_scroll.viewport().palette().color(QPalette.ColorRole.Window).name() == tokens["bg"]
            panel._available(Release("200.0.0", "https://github.com/baaaaan1/Playgrounds/releases/download/v200.0.0/Playgrounds-200.0.0-x64.msi", "0" * 64, "Release notes"))
            qt_app.processEvents()
            assert panel._notes.isVisible()
            notes = panel._notes.viewport().grab().toImage()
            assert notes.pixelColor(notes.width() - 3, notes.height() - 3).name() == tokens["surface"]
            assert panel._notes.palette().color(QPalette.ColorRole.Text).name() == tokens["text"]
            assert panel._status.palette().color(QPalette.ColorRole.WindowText).name() == tokens["text_muted"]
            panel._action.setEnabled(False)
            qt_app.processEvents()
            palette = panel._action.palette()
            assert palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText).name() == tokens["text_faint"]
            assert _contrast(tokens["text_faint"], tokens["surface_active"]) >= 4.5
    finally:
        dialog.done(0)
        qt_app.setPalette(old_palette)
        qt_app.setStyleSheet(old_qss)


@pytest.mark.parametrize("size", [(820, 780), (600, 480)])
def test_update_layout_fits_available_width(qt_app, workdir, credentials, monkeypatch, size):
    from app.ui import update_panel

    old_palette, old_qss = qt_app.palette(), qt_app.styleSheet()
    tokens = theme.apply(qt_app, "dark")
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    dialog = SettingsDialog(config, credentials, tokens)
    dialog.resize(*size)
    dialog.show()
    dialog._updates_button.click()
    qt_app.processEvents()
    qt_app.processEvents()
    # Windows' custom frame may adjust the initial client height on first show.
    shown_size = (dialog.width(), dialog.height()) if qt_app.platformName() == "windows" else size
    panel = dialog._update_panel
    monkeypatch.setattr(panel.client, "check", lambda: None)
    monkeypatch.setattr(panel.client, "download", lambda release: None)
    try:
        for state in ("idle", "checking", "missing", "available", "long-error", "downloading"):
            if state == "checking":
                panel.check()
            elif state == "missing":
                panel._unavailable()
            elif state == "available":
                panel._available(Release("200.0.0", "https://github.com/baaaaan1/Playgrounds/releases/download/v200.0.0/Playgrounds-200.0.0-x64.msi", "0" * 64, "Changes\n" * 100))
            elif state == "long-error":
                panel._failed("https://example.com/" + "a" * 300)
            elif state == "downloading":
                monkeypatch.setattr(update_panel, "can_install", lambda: True)
                panel._action.click()
            qt_app.processEvents()
            # The scroll area's wrapped child layouts settle on the next layout pass.
            qt_app.processEvents()
            assert (dialog.width(), dialog.height()) == shown_size
            scroll = dialog._updates_scroll
            assert scroll.horizontalScrollBar().maximum() == 0, state
            assert scroll.widget().width() <= scroll.viewport().width()
            assert panel._card.width() <= scroll.viewport().width()
            assert panel._action.width() >= panel._action.sizeHint().width()
            assert panel._card.rect().contains(panel._action.geometry())
            assert dialog.rect().contains(dialog._cancel_button.mapTo(dialog, dialog._cancel_button.rect().bottomRight()))
            assert panel._status.height() >= panel._status.heightForWidth(panel._status.width()), state
    finally:
        dialog.done(0)
        qt_app.setPalette(old_palette)
        qt_app.setStyleSheet(old_qss)
