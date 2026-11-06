from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from string import Formatter

import pytest
from PyQt6.QtCore import QLocale, QSettings, Qt, QTranslator
from PyQt6.QtWidgets import QLabel, QPushButton

from app.core.config import Config
from app.core.models import Conversation, Message
from app.core.store import ConversationStore
from app.i18n import SOURCE_LOCALE, initialize_english
from app.net.client import StreamClient
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog
from app.ui.update_panel import UpdatePanel

ROOT = Path(__file__).resolve().parents[1]

# Literal-bearing argument positions for Qt and project presentation helpers.
TEXT_ARGUMENTS = {
    "QLabel": (0,), "QPushButton": (0,), "QToolButton": (0,),
    "QCheckBox": (0,), "QRadioButton": (0,), "QGroupBox": (0,),
    "QListWidgetItem": (0,), "QAction": (0,),
    "setText": (0,), "setWindowTitle": (0,), "setToolTip": (0,),
    "setStatusTip": (0,), "setPlaceholderText": (0,),
    "setAccessibleName": (0,), "setAccessibleDescription": (0,),
    "setTitle": (0,), "setInformativeText": (0,), "setDetailedText": (0,),
    "addAction": (0, 1), "addTab": (1,), "addItem": (0,),
    "_button": (0,), "_control": (1,), "_add_field": (1, 4),
    "_set_result": (0,), "_on_error": (0,), "_fail": (0,),
    "question": (1, 2), "information": (1, 2), "warning": (1, 2), "critical": (1, 2),
}
# Canonical brands, technical examples and attribution tokens, not prose.
LITERAL_EXCEPTIONS = {"Playgrounds", "OpenAI", "https://api.example.com/v1"}


def _name(call: ast.Call) -> str:
    name = getattr(call.func, "attr", getattr(call.func, "id", ""))
    if name == "translate" and isinstance(call.func, ast.Attribute):
        owner = call.func.value
        if not isinstance(owner, ast.Name) or owner.id not in {"QCoreApplication", "QApplication"}:
            return ""  # QPainter.translate() moves coordinates; it does not translate UI copy.
    return name


@pytest.mark.parametrize("source, expected", [
    ('QCoreApplication.translate("Context", "Text")', "translate"),
    ('QApplication.translate("Context", "Text")', "translate"),
    ('self.tr("Text")', "tr"),
    ("painter.translate(rect.center())", ""),
])
def test_copy_scanner_distinguishes_painter_coordinate_translation(source, expected):
    assert _name(ast.parse(source, mode="eval").body) == expected


def _raw_strings(node: ast.AST):
    if isinstance(node, ast.Call) and _name(node) in {"tr", "translate"}:
        return
    if isinstance(node, ast.IfExp):
        # Conditions contain identifiers/sentinels, not displayed text.
        yield from _raw_strings(node.body)
        yield from _raw_strings(node.orelse)
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.FormattedValue):
        yield from _raw_strings(node.value)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "format":
            yield from _raw_strings(node.func.value)
    elif not isinstance(node, ast.Call):
        for child in ast.iter_child_nodes(node):
            yield from _raw_strings(child)


def test_application_copy_is_extractable() -> None:
    failures = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            name = _name(call)
            if name in {"tr", "translate"}:
                index = 1 if name == "translate" else 0
                assert len(call.args) > index and isinstance(call.args[index], ast.Constant), (
                    f"{path.relative_to(ROOT)}:{call.lineno}: translate a literal before formatting"
                )
            indexes = TEXT_ARGUMENTS.get(name, ())
            if name == "_button" and path.name == "window_chrome.py":
                indexes = (1,)
            if name == "emit" and isinstance(call.func, ast.Attribute):
                if getattr(call.func.value, "attr", "") in {"failed", "error"}:
                    indexes = (0,)
            if name in {"ValueError", "OSError"} and path.name not in {"icons.py", "window_chrome.py"}:
                # Invalid icon/resize inputs are programming errors, not UI copy.
                indexes = (0,)
            for index in indexes:
                if index >= len(call.args):
                    continue
                for text in _raw_strings(call.args[index]):
                    if any(char.isalpha() for char in text) and text not in LITERAL_EXCEPTIONS:
                        failures.append(f"{path.relative_to(ROOT)}:{call.lineno}: {text!r}")
    assert not failures, "Wrap application-owned copy in tr()/translate():\n" + "\n".join(failures)


def test_english_policy_ignores_system_locale(qt_app) -> None:
    previous_locale = QLocale()
    previous_direction = qt_app.layoutDirection()
    try:
        QLocale.setDefault(QLocale("ar_SA"))
        qt_app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        initialize_english(qt_app)
        assert QLocale().name() == SOURCE_LOCALE
        assert qt_app.layoutDirection() == Qt.LayoutDirection.LeftToRight
        assert QLocale().toString(1.5, "f", 1) == "1.5"
    finally:
        QLocale.setDefault(previous_locale)
        qt_app.setLayoutDirection(previous_direction)


def test_native_catalog_extraction_and_placeholders() -> None:
    # pylupdate stores relative source locations; source and TS must share a drive.
    with tempfile.TemporaryDirectory(prefix=".i18n-test-", dir=ROOT) as directory:
        catalog = Path(directory) / "playgrounds_en_US.ts"
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "PyQt6.lupdate.pylupdate", str(ROOT / "app"),
             "--ts", str(catalog), "--verbose"],
            capture_output=True, encoding="utf-8", timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        root = ET.parse(catalog).getroot()
    contexts = {item.findtext("name") for item in root.findall("context")}
    assert {"Composer", "Sidebar", "EmptyState", "ChatView", "ChatController",
            "MainWindow", "SettingsDialog", "UpdatePanel", "AboutPanel", "TitleBar",
            "StreamClient", "ModelDiscovery", "UpdateClient"} <= contexts
    sources = {message.findtext("source") for message in root.findall("context/message")}
    assert "Ask anything..." in sources
    assert 'Delete "{name}"? This cannot be undone.' in sources
    assert "Thought for {seconds:.1f}s" in sources
    for source in sources:
        # Parses every source template, including HTML/CSS escaped braces.
        list(Formatter().parse(source))


class _PseudoTranslator(QTranslator):
    def isEmpty(self) -> bool:  # noqa: N802
        return False

    def translate(self, context, source, disambiguation=None, n=-1):
        if context in {"Composer", "Sidebar", "EmptyState", "ChatView", "MainWindow", "StreamClient"}:
            return "[Expanded English test: " + source + "]"
        return ""


def test_display_time_translation_keeps_user_content(qt_app, workdir, credentials) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    config.set("updates/automatic", False)
    translator = _PseudoTranslator()
    assert qt_app.installTranslator(translator)
    window = None
    try:
        window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
        window.resize(720, 480)
        window.show()
        qt_app.processEvents()
        assert window._composer._input.placeholderText().startswith("[Expanded English test:")
        assert window._composer._send.accessibleName().startswith("[Expanded English test:")
        assert window._sidebar._new_button.text().startswith("  [Expanded English test:")
        assert all(label.wordWrap() for label in window._empty.findChildren(QLabel) if label.text())
        suggestions = window._empty.findChildren(QPushButton)
        assert len(suggestions) == 3
        assert all(button.accessibleName().startswith("[Expanded English test:") for button in suggestions)
        conversation = Conversation(title="User title", messages=[Message("user", "User content <b>")])
        window._chat.show_conversation(conversation)
        assert "User content <b>" in window._chat.toPlainText()
        assert conversation.title == "User title"
        assert conversation.messages[0].content == "User content <b>"
        window._chat.begin_stream()
        assert "[Expanded English test: ASSISTANT]" in window._chat.toPlainText()
        assert "[Expanded English test: Thinking... 0.0s]" in window._chat.toPlainText()
        assert "[Expanded English test:" in StreamClient._describe_http(401, b"")
    finally:
        if window is not None:
            window.close()
        qt_app.removeTranslator(translator)


@pytest.mark.parametrize("status, expected", [
    (401, "The API key is invalid or not set"),
    (429, "Rate limit reached. Please try again shortly"),
])
def test_english_network_copy_preserves_external_details(status, expected) -> None:
    assert StreamClient._describe_http(status, b'{"error":{"message":"External detail"}}') == (
        expected + ": External detail"
    )


def test_dialog_english_fallback_and_plural_counts(qt_app, workdir, credentials) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    settings = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    updates = UpdatePanel(config)
    try:
        assert settings.windowTitle() == "Settings"
        assert not updates._progress.isVisible()
        assert updates._action.text() == "Check for updates"
        settings._models_received(["model-one"])
        assert "1 model found." in settings._status.text()
        assert "does not verify inference access" in settings._status.text()
        assert settings._model_count.text() == "1 of 1 model"
        settings._models_received(["model-one", "model-two"])
        assert "2 models found." in settings._status.text()
        assert settings._model_count.text() == "2 of 2 models"
        settings._models_received([])
        assert "No models returned." in settings._status.text()
    finally:
        # Close test drafts without triggering the unsaved-changes confirmation.
        settings.done(0)
        updates.cancel()


def test_installer_uses_english_copy() -> None:
    root = ET.parse(ROOT / "build/installer/Product.wxs").getroot()
    upgrade = root.find(".//{http://wixtoolset.org/schemas/v4/wxs}MajorUpgrade")
    assert upgrade.attrib["DowngradeErrorMessage"] == (
        "A newer version of Playgrounds is already installed."
    )
