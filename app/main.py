from __future__ import annotations

import logging
import os
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from .core.config import Config
from .core.store import ConversationStore, default_data_dir
from .ui import theme
from .ui.main_window import MainWindow

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    try:
        log_dir = default_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "playgrounds.log",
            maxBytes=1_000_000,
            backupCount=2,
            encoding="utf-8",
        )
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    screenshot: str | None = None
    if "--screenshot" in args:
        index = args.index("--screenshot")
        if index + 1 < len(args):
            screenshot = args[index + 1]
            del args[index : index + 2]
        else:
            del args[index]
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    demo = "--demo" in args
    if demo:
        args = [arg for arg in args if arg != "--demo"]

    forced_theme: str | None = None
    if "--theme" in args:
        index = args.index("--theme")
        if index + 1 < len(args):
            forced_theme = args[index + 1]
            del args[index : index + 2]
        else:
            del args[index]

    native_smoke = "--smoke-native" in args
    smoke = "--smoke" in args or native_smoke or screenshot is not None
    if smoke:
        args = [arg for arg in args if arg not in {"--smoke", "--smoke-native"}]
        if not native_smoke:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(args)
    app.setApplicationName("Playgrounds")
    app.setOrganizationName("Playgrounds")
    app.setApplicationDisplayName("Playgrounds")

    if not smoke:
        _setup_logging()

    temporary = tempfile.TemporaryDirectory(prefix="playgrounds-smoke-") if smoke else None
    settings = QSettings(str(Path(temporary.name) / "settings.ini"), QSettings.Format.IniFormat) if temporary else None
    config = Config(settings)
    if forced_theme in {"dark", "light"}:
        config.theme = forced_theme
    theme.apply(app, config.theme)

    font = QFont("Segoe UI Variable Text")
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPointSizeF(10)
    app.setFont(font)

    store = ConversationStore(Path(temporary.name) / "conversations") if temporary else None
    window = MainWindow(config, store=store)
    if demo:
        window.show_demo()
    window.show()
    if screenshot:
        def _capture() -> None:
            window.grab().save(screenshot)
            app.quit()

        QTimer.singleShot(600, _capture)
    elif smoke:
        QTimer.singleShot(400, app.quit)
    result = app.exec()
    window.close()
    config.sync()
    if temporary:
        temporary.cleanup()
    return result
