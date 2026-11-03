from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture()
def workdir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="playgrounds-test-") as tmp:
        yield Path(tmp)


@pytest.fixture(scope="session")
def qt_app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    app = app if isinstance(app, QApplication) else QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


class MemoryCredentials:
    def __init__(self) -> None:
        self.secrets: dict[str, str] = {}
        self.fail_writes = False

    def get_secret(self, name: str) -> str | None:
        return self.secrets.get(name)

    def has_secret(self, name: str) -> bool:
        return bool(self.get_secret(name))

    def set_secret(self, name: str, secret: str) -> bool:
        if self.fail_writes:
            return False
        self.secrets[name] = secret
        return True

    def delete_secret(self, name: str) -> bool:
        self.secrets.pop(name, None)
        return True


@pytest.fixture()
def credentials() -> MemoryCredentials:
    return MemoryCredentials()
