from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from PyQt6.QtCore import QCoreApplication

from .. import __version__
from ..version import parse_version, validate_msi_version

MANIFEST_URL = "https://github.com/baaaaan1/Playgrounds/releases/latest/download/update.json"
RELEASE_PREFIX = "/baaaaan1/Playgrounds/releases/"
RELEASES_URL = f"https://github.com{RELEASE_PREFIX}"


def trusted_url(value: str, *, redirect: bool = False) -> bool:
    try:
        url = urlsplit(value)
        if url.scheme != "https" or url.username or url.password or url.port not in (None, 443):
            return False
        if url.hostname == "github.com":
            return url.path.startswith((RELEASE_PREFIX + "download/", RELEASE_PREFIX + "latest/download/"))
        return redirect and url.hostname in {
            "release-assets.githubusercontent.com", "objects.githubusercontent.com",
        }
    except ValueError:
        return False


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    sha256: str
    notes: str = ""

    @classmethod
    def parse(cls, body: bytes) -> Release:
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError(QCoreApplication.translate("Updates", "Invalid update manifest."))
        release = cls(data.get("version"), data.get("url"), data.get("sha256"), data.get("notes", ""))
        release.validate()
        return cls(release.version, release.url, release.sha256.lower(), release.notes)

    def validate(self) -> None:
        validate_msi_version(self.version)
        expected_paths = {
            f"{RELEASE_PREFIX}download/{tag}/Playgrounds-{self.version}-x64.msi"
            for tag in (self.version, f"v{self.version}")
        }
        url = urlsplit(self.url) if isinstance(self.url, str) else None
        if (url is None or not trusted_url(self.url) or url.path not in expected_paths
                or url.query or url.fragment):
            raise ValueError(QCoreApplication.translate(
                "Updates", "Installer must match the version, release tag, and Windows x64 MSI filename from this project's GitHub releases.",
            ))
        if not isinstance(self.sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", self.sha256):
            raise ValueError(QCoreApplication.translate("Updates", "Missing or invalid SHA-256 checksum."))
        if not isinstance(self.notes, str) or len(self.notes) > 100_000:
            raise ValueError(QCoreApplication.translate("Updates", "Invalid release notes."))

    @property
    def page_url(self) -> str:
        tag = urlsplit(self.url).path.split("/")[-2]
        return f"{RELEASES_URL}tag/{tag}"

    def newer_than(self, current: str) -> bool:
        return parse_version(self.version) > parse_version(current)


def verify_installer(path: Path, release: Release) -> None:
    release.validate()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != release.sha256.lower():
        raise ValueError(QCoreApplication.translate(
            "Updates", "Installer checksum mismatch. The download will not be installed.",
        ))


def can_install() -> bool:
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def launch_installer(path: Path, release: Release) -> None:
    if not can_install():
        raise ValueError(QCoreApplication.translate(
            "Updates", "Automatic installation is available only in the packaged Windows application.",
        ))
    verify_installer(path, release)
    if not release.newer_than(__version__):
        raise ValueError(QCoreApplication.translate(
            "Updates", "Only a newer version can be installed through the updater.",
        ))
    # Capture this process before waiting, then install only once its files are unlocked.
    installer = str(path.resolve()).replace("'", "''")
    # The MSI installs here even when an update was started from a portable build.
    executable = str(Path(os.environ["LOCALAPPDATA"]) / "Playgrounds" / "Playgrounds.exe").replace("'", "''")
    script = (
        f"$app = Get-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; "
        "if ($app) { $app.WaitForExit() }; "
        f"$msi = '{installer}'; "
        f"if ((Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash -ne '{release.sha256}') {{ exit 1 }}; "
        "$result = Start-Process -FilePath msiexec.exe -ArgumentList "
        "@('/i', ('\"' + $msi + '\"'), '/qb', '/norestart') -Wait -PassThru; "
        f"if ($result.ExitCode -in @(0, 3010)) {{ Start-Process -FilePath '{executable}' }}; "
        "Remove-Item -LiteralPath (Split-Path -Parent $msi) -Recurse -Force"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    subprocess.Popen(
        [str(powershell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
    )
