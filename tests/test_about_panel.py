from pathlib import Path
from platform import python_version

import pytest
from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QCoreApplication, QEvent, QSettings, Qt
from PyQt6.QtWidgets import QGroupBox, QLabel

from app import __version__
from app.core.config import Config
from app.ui import theme
from app.ui.about_panel import AboutPanel
from app.ui.settings_dialog import SettingsDialog


@pytest.fixture()
def widgets(qt_app):
    created = []
    yield created
    for widget in created:
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_about_contains_tagline_version_credits_and_project_links(qt_app, widgets) -> None:
    panel = AboutPanel()
    widgets.append(panel)
    labels = panel.findChildren(QLabel)
    text = "\n".join(label.text() for label in labels)
    assert "\u201cLooks cool, ships fast, uses less RAM.\u201d \U0001f5ff" in text
    assert f"Version {__version__}" in text
    assert "Vjacheslav Trushkin" in text
    assert "Material Symbols" in text
    assert "by Google" in text
    assert "Apache License 2.0" in text
    assert "GPL-3.0-only" in text
    assert f"Runtime: Python {python_version()} / PyQt {PYQT_VERSION_STR} / Qt {QT_VERSION_STR}" in text
    for url in (
        "https://github.com/baaaaan1/Playgrounds",
        "https://github.com/baaaaan1/Playgrounds/issues",
        "https://github.com/baaaaan1/Playgrounds/pulls",
        "https://github.com/baaaaan1/Playgrounds/graphs/contributors",
        "https://icon-sets.iconify.design/line-md/",
        "https://icon-sets.iconify.design/material-symbols/",
    ):
        assert f'href="{url}"' in text
    for label in labels:
        if "href=" in label.text():
            assert label.openExternalLinks()
            assert label.textInteractionFlags() & Qt.TextInteractionFlag.LinksAccessibleByKeyboard
    panel.close()


def test_about_describes_current_features_data_storage_and_shortcuts(qt_app, widgets):
    panel = AboutPanel()
    widgets.append(panel)
    text = "\n".join(label.text() for label in panel.findChildren(QLabel))
    for feature in (
        "OpenAI-compatible connections", "retry failed requests", "regenerate answers",
        "archive conversations", "estimated costs", "not provider invoices",
        "Ctrl+N", "Ctrl+F", "Ctrl+B", "Ctrl+,", "Windows Credential Manager",
        "%APPDATA%\\Playgrounds\\conversations", "not encrypted by Playgrounds",
        "data handling depend on that provider", "Automatic update checks",
    ):
        assert feature in text
    titles = {group.title() for group in panel.findChildren(QGroupBox)}
    assert {"Your AI workspace", "Your data & connections", "Project & contributions", "License"} <= titles


@pytest.mark.parametrize("directory, attribute", [
    ("line-md", "_icon_license"), ("material-symbols", "_symbols_license"),
])
def test_bundled_icon_licenses_are_available_offline(qt_app, widgets, directory, attribute) -> None:
    panel = AboutPanel()
    widgets.append(panel)
    panel.show()
    editor = getattr(panel, attribute)
    assert not editor.isVisible()
    group = editor.parentWidget()
    assert isinstance(group, QGroupBox) and group.isCheckable()
    group.setChecked(True)
    assert editor.isVisible()
    assert editor.isReadOnly()
    assert editor.accessibleName()
    source = Path(__file__).resolve().parents[1] / "app/resources" / directory / "LICENSE.txt"
    assert editor.toPlainText() == source.read_text(encoding="utf-8")
    group.setChecked(False)
    assert not editor.isVisible()
    panel.close()


@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("width,height", [(600, 480), (820, 780)])
def test_about_navigation_layout_and_read_only_settings(
    qt_app, workdir, credentials, widgets, theme_name, width, height,
) -> None:
    original_style, original_palette = qt_app.styleSheet(), qt_app.palette()
    theme.apply(qt_app, theme_name)
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    config.theme = theme_name
    dialog = SettingsDialog(config, credentials, theme.tokens_for(theme_name))
    widgets.append(dialog)
    try:
        dialog.resize(width, height)
        dialog.show()
        dialog._about_button.click()
        qt_app.processEvents()
        panel = dialog._about
        assert dialog._pages.currentWidget() is panel
        assert panel.isVisible()
        assert dialog.size().width() == width
        assert dialog.size().height() == height
        assert panel.widget().width() <= panel.viewport().width()
        assert panel.horizontalScrollBar().maximum() == 0
        for editor in (panel._icon_license, panel._symbols_license):
            editor.parentWidget().setChecked(True)
        qt_app.processEvents()
        assert panel.widget().width() <= panel.viewport().width()
        assert panel.horizontalScrollBar().maximum() == 0
        for control in (dialog._about_button, dialog._cancel_button, dialog._save_button):
            assert dialog.rect().contains(control.mapTo(dialog, control.rect().topLeft()))
            assert dialog.rect().contains(control.mapTo(dialog, control.rect().bottomRight()))
        assert not dialog._has_changes()
        assert dialog._dirty_label.text() == "No unsaved changes"
    finally:
        dialog.reject()
        qt_app.setStyleSheet(original_style)
        qt_app.setPalette(original_palette)


@pytest.mark.parametrize("connections_editable", [True, False])
def test_about_is_available_without_saving_or_discarding_drafts(
    qt_app, workdir, credentials, widgets, connections_editable,
) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    original_theme = config.theme
    dialog = SettingsDialog(
        config, credentials, theme.tokens_for(original_theme),
        connections_editable=connections_editable,
    )
    widgets.append(dialog)
    if original_theme == "dark":
        dialog._theme_light.setChecked(True)
    else:
        dialog._theme_dark.setChecked(True)
    dialog._about_button.click()
    assert dialog._pages.currentWidget() is dialog._about
    assert dialog._has_changes()
    assert config.theme == original_theme
    dialog._appearance_button.click()
    assert dialog._has_changes()
    dialog._theme_light.setChecked(original_theme == "light")
    dialog._theme_dark.setChecked(original_theme == "dark")
    dialog.reject()
