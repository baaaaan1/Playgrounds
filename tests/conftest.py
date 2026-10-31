from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture()
def workdir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="playgrounds-test-") as tmp:
        yield Path(tmp)
