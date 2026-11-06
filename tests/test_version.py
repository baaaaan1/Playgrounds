from __future__ import annotations

import hashlib
import importlib.metadata
import json
import runpy
from pathlib import Path

import pytest

import app
import app.version as version_module
from app.core.updates import Release
from app.version import get_version, parse_version, validate_msi_version

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0.0.0", (0, 0, 0)), ("0.1.0", (0, 1, 0)), ("12.34.567", (12, 34, 567))],
)
def test_parse_stable_version(value, expected):
    assert parse_version(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "", "1", "1.2", "1.2.3.4", "v1.2.3", "01.2.3", "1.02.3", "1.2.03",
        "1.2.3rc1", "1.2.3-rc.1", "1.2.3+build.1", "1.2.3.dev1", "1.2.3.post1",
        " 1.2.3", "1.2.3 ", "1.2.3\n", "-1.2.3", "1.2.+3", "１.2.3", None, 123,
    ],
)
def test_reject_non_stable_versions(value):
    with pytest.raises(ValueError, match="stable MAJOR.MINOR.PATCH"):
        parse_version(value)


def test_versions_compare_numerically():
    assert parse_version("1.10.0") > parse_version("1.9.99")


def test_msi_limits():
    assert validate_msi_version("255.255.65535") == (255, 255, 65535)
    for value in ("256.0.0", "0.256.0", "0.0.65536", "1.0.0-rc.1"):
        with pytest.raises(ValueError):
            validate_msi_version(value)


def test_source_version_ignores_distribution_metadata(monkeypatch):
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "999.999.999")
    with (ROOT / "pyproject.toml").open("rb") as stream:
        canonical = version_module.tomllib.load(stream)["project"]["version"]
    assert get_version() == app.__version__ == canonical


def test_project_uses_gpl_v3_only():
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = version_module.tomllib.load(stream)["project"]
    assert project["license"] == "GPL-3.0-only"
    assert project["license-files"] == ["LICENSE"]
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3, 29 June 2007" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text


def test_bundled_pyproject_wins_over_source_and_metadata(workdir, monkeypatch):
    package = workdir / "app"
    package.mkdir()
    (workdir / "pyproject.toml").write_text('[project]\nversion = "9.9.9"\n')
    (package / "pyproject.toml").write_text('[project]\nversion = "2.3.4"\n')
    monkeypatch.setattr(version_module, "__file__", str(package / "version.py"))
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "999.999.999")
    assert get_version() == "2.3.4"


def test_missing_version_fails_instead_of_using_stale_metadata(workdir, monkeypatch):
    monkeypatch.setattr(version_module, "__file__", str(workdir / "app" / "version.py"))
    with pytest.raises(FileNotFoundError):
        get_version()


@pytest.fixture()
def release():
    return runpy.run_path(str(ROOT / "build" / "release.py"))


def test_release_tags(release):
    validate = release["validate_release_tag"]
    assert validate("1.2.3") == "v1.2.3"
    for tag in ("1.2.3", "v1.2.3"):
        assert validate("1.2.3", tag) == tag
    for tag in ("v1.2.4", "v1.2.3-rc.1", "vv1.2.3", "", "../1.2.3"):
        with pytest.raises(ValueError):
            validate("1.2.3", tag)


def test_generated_exe_version_matches_msi(workdir, release):
    output = workdir / "generated" / "version_info.txt"
    version = release["generate_version_info"](output)
    text = output.read_text(encoding="utf-8")
    parts = (*validate_msi_version(version), 0)
    assert f"filevers={parts}" in text
    assert f"prodvers={parts}" in text
    assert f"StringStruct(u'FileVersion', u'{version}')" in text
    assert f"StringStruct(u'ProductVersion', u'{version}')" in text
    assert "GNU GPL version 3 only (GPL-3.0-only)" in text
    compile(text, str(output), "eval")


@pytest.mark.parametrize("tag_prefix", ["", "v"])
def test_update_manifest(workdir, release, tag_prefix):
    version = get_version()
    asset = workdir / f"Playgrounds-{version}-x64.msi"
    asset.write_bytes(b"test MSI contents\x00\xff")
    output = workdir / "update.json"
    tag = f"{tag_prefix}{version}"
    manifest = release["write_update_manifest"](
        asset, output, tag=tag, notes="Release notes\nSecond line"
    )
    assert json.loads(output.read_text(encoding="utf-8")) == manifest == {
        "version": version,
        "url": f"https://github.com/baaaaan1/Playgrounds/releases/download/{tag}/{asset.name}",
        "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
        "notes": "Release notes\nSecond line",
    }
    parsed = Release.parse(output.read_bytes())
    assert parsed.version == version
    assert parsed.page_url == f"https://github.com/baaaaan1/Playgrounds/releases/tag/{tag}"


def test_manifest_rejects_wrong_or_missing_asset(workdir, release):
    output = workdir / "update.json"
    with pytest.raises(ValueError, match="Expected release asset"):
        release["write_update_manifest"](workdir / "wrong.msi", output)
    with pytest.raises(FileNotFoundError):
        release["write_update_manifest"](
            workdir / f"Playgrounds-{get_version()}-x64.msi", output
        )
    assert not output.exists()
