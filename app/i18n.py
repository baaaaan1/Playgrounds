"""English-first presentation policy; source messages are the fallback catalog."""

from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtWidgets import QApplication

SOURCE_LOCALE = "en_US"


def initialize_english(app: QApplication) -> None:
    """Apply before constructing widgets, independently of the OS language.

    Qt's built-in widget copy and our tr() calls use English source text without
    a QTranslator. Do not auto-load system-language catalogs in English-only builds.
    """
    QLocale.setDefault(QLocale(SOURCE_LOCALE))
    app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
