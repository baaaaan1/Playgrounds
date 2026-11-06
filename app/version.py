"""Canonical application version and strict stable release parsing."""

from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import QCoreApplication

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse stable MAJOR.MINOR.PATCH; reject prefixes, prereleases and metadata."""
    if not isinstance(version, str) or re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version
    ) is None:
        raise ValueError(QCoreApplication.translate(
            "Version", "Expected stable MAJOR.MINOR.PATCH version, got {version!r}",
        ).format(version=version))
    return tuple(int(part) for part in version.split("."))


def get_version() -> str:
    """Read bundled or source pyproject, never installed distribution metadata."""
    bundled = Path(__file__).with_name("pyproject.toml")
    project = bundled if bundled.is_file() else Path(__file__).resolve().parents[1] / "pyproject.toml"
    with project.open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    parse_version(version)
    return version


def validate_msi_version(version: str) -> tuple[int, int, int]:
    """Validate Windows Installer's 255.255.65535 component limits."""
    parts = parse_version(version)
    if any(part > limit for part, limit in zip(parts, (255, 255, 65535), strict=True)):
        raise ValueError(QCoreApplication.translate(
            "Version", "Version {version!r} exceeds MSI limits (255.255.65535)",
        ).format(version=version))
    return parts
